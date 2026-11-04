"""Controlled first customer-quotation issue path for unified SmartQuote.

No customer PDF is issued unless: exact V10 sources and August master pinned,
Sage fallback sourced, every equipment price and cover validated, the exact
tariff SHA-256 commercially authorised, real maintenance terms supplied and
the pilot Admin approves that specific quote. Frozen PDFs and numeric source
evidence remain immutable; no email, Sage or Sicon action is performed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import uuid
from pathlib import Path

import fitz
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import pilot_access, quote_drafts, quote_pricing
from .store import connect, now
from .quote_customer_pdf import render_quote_pdf

router = APIRouter(prefix="/api/quoting", tags=["Commercial quotation approval and issue"])
APPROVAL_SOURCE_ENV = "PULSE_QUOTE_APPROVED_TARIFF_SHA256"
TERMS_FILE_ENV = "PULSE_QUOTE_TERMS_PDF"
TERMS_SHA_ENV = "PULSE_QUOTE_TERMS_SHA256"
ISSUE_ENV = "PULSE_QUOTE_LIVE_ISSUANCE"
ISSUER_FILE_ENV = "PULSE_QUOTE_ISSUER_JSON"
ISSUER_SHA_ENV = "PULSE_QUOTE_ISSUER_SHA256"
MAX_TERMS = 8 * 1024 * 1024
ALLOWED_PRICE_NOTES = {
    "August 2026 source List Price used; commercial maintenance tariff approval remains separate.",
    "Price taken from exact Sage item code; maintenance tariff approval remains separate.",
    "Administrator-adjusted equipment price; source revision recorded in price audit.",
}
NUMBER = re.compile(r"^PFQ-\d{4}-\d{6,9}$")


class QuoteApproval(BaseModel):
    expected_revision: int
    valid_until: str
    commercial_approval_ref: str
    confirm_customer_and_site: bool
    confirm_equipment_and_serials: bool
    confirm_package_price_and_discount: bool
    confirm_maintenance_scope_and_terms: bool
    confirm_vat_basis: bool
    serial_exception_reason: str = ""
    confirm_source_price_variances: bool = False  # Old pilot client compatibility; NOT required.


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Signed-in pilot pricing administrator required to issue a customer quotation.")
    name = pilot_access.actor("")
    if not name or name == "Coordinator":
        raise HTTPException(403, "Named commercial approver required.")
    return name


def _quote_reader():
    """Authenticated staff may check readiness and retrieve APPROVED PDFs.

    Only a named Administrator can issue a new PDF. Viewers must never
    receive commercial document downloads or approval status.
    """
    if (not pilot_access.PILOT_MODE or
            pilot_access.current_role() not in ("Admin", "Coordinator")):
        raise HTTPException(403, "Signed-in Coordinator or Administrator required.")
    identity = pilot_access.actor("")
    if not isinstance(identity, str) or len(identity.strip()) < 2:
        raise HTTPException(403, "A named staff account is required.")
    return identity


def _approved_tariff(fingerprint):
    pinned = os.environ.get(APPROVAL_SOURCE_ENV, "").strip().lower()
    if pinned:  # IT deployment override remains the highest authority.
        return (len(pinned) == 64 and all(c in "0123456789abcdef" for c in pinned)
                and fingerprint.lower() == pinned)
    from .quote_commercial_setup import tariff_is_approved
    return tariff_is_approved(fingerprint)


def _issuance_enabled():
    # Explicit IT disable overrides an in-app approval.
    override = os.environ.get(ISSUE_ENV)
    if override is not None:
        return override == "1"
    from .quote_commercial_setup import enabled
    return enabled()


def _terms():
    """IT-provisioned commercial terms; cannot be supplied by quote client."""
    configured = os.environ.get(TERMS_FILE_ENV, "").strip()
    expected = os.environ.get(TERMS_SHA_ENV, "").strip().lower()
    if not configured and not expected:
        from .quote_commercial_setup import verified_terms
        recorded = verified_terms()
        if recorded is None:
            raise HTTPException(503, "No approved maintenance terms PDF has been uploaded.")
        return recorded
    if not configured or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(503, "Approved maintenance terms PDF has not been staged and fingerprinted.")
    path = Path(configured).expanduser().resolve()
    try:
        if not path.is_file() or not 2 <= path.stat().st_size <= MAX_TERMS or path.suffix.lower() != ".pdf":
            raise ValueError("Invalid terms file")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected or not data.startswith(b"%PDF-"):
            raise ValueError("Terms source bytes do not match their signed-off fingerprint")
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.needs_pass or not 1 <= document.page_count <= 30:
                raise ValueError("Empty, password-protected or oversized terms")
        return data, actual
    except (OSError, ValueError, RuntimeError, fitz.FileDataError) as exc:
        raise HTTPException(503, "Approved maintenance terms PDF is missing, damaged or changed.") from exc


def _issuer():
    """Verify factual Pulse legal/company details, never guess them in code."""
    configured = os.environ.get(ISSUER_FILE_ENV, "").strip()
    expected = os.environ.get(ISSUER_SHA_ENV, "").strip().lower()
    if not configured and not expected:
        from .quote_commercial_setup import verified_issuer
        recorded = verified_issuer()
        if recorded is None:
            raise HTTPException(503, "Verified company issuer details have not been configured.")
        return recorded
    if not configured or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(503, "Verified Pulse Fitness issuer details have not been staged.")
    path = Path(configured).expanduser().resolve()
    try:
        if not path.is_file() or path.suffix.lower() != ".json" or not 2 <= path.stat().st_size <= 4096:
            raise ValueError("Invalid issuer identity file")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Issuer identity file differs from the IT-approved evidence")
        data = json.loads(raw.decode("utf-8"))
        required = ("legal_name", "registered_address", "contact_email", "company_number")
        if not isinstance(data, dict) or not all(
            isinstance(data.get(k), str) and 3 <= len(data[k].strip()) <= 250
            for k in required
        ):
            raise ValueError("Incomplete company identity")
        if "@" not in data["contact_email"] or not re.fullmatch(r"[A-Za-z0-9 .,&'()/#\\-]+", data["registered_address"]):
            raise ValueError("Unsupported company identity")
        return {key: data.get(key, "").strip()[:250] for key in (
            *required, "telephone", "vat_number"
        )}, expected
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Verified company identity is missing or changed.") from exc


def _price(draft):
    from .quote_rrp_priority import source_snapshot as august_snapshot, index
    from .quote_sage_reference import snapshot as sage_snapshot
    from .quote_price_overrides import active_overrides

    catalog, configs, policy, fingerprints = quote_pricing.source_snapshot()
    august = august_snapshot()   # Verifies the August source against manifest.
    sage = sage_snapshot()
    codes = [str(line.get("item_code") or "") for line in draft["equipment"]]
    preview = quote_pricing.preview(
        draft, catalog, configs, policy, fingerprints,
        master_by_sku=index(august), sage_source=sage,
        overrides=active_overrides(codes), august_source=august,
    )
    preview["rrp_master"] = {
        "original_sha256": august["source_file_sha256"],
        "staged_sha256": august["snapshot_sha256"],
    }
    preview["sage_sha256"] = sage["source_file_sha256"] if sage else None
    return preview, fingerprints


def _errors(draft, preview):
    errors = []
    if not draft["equipment"]:
        errors.append("Add the customer's equipment before issuing a quote.")
    if not preview["complete_price"] or preview["priced_count"] != preview["line_count"]:
        errors.append("Resolve every unpriced or ambiguous equipment line.")
    if preview["term_partial"] is None:
        errors.append("No valid proposed term value could be calculated.")
    if bool(draft.get("contract_start")) != bool(draft.get("contract_end")):
        errors.append("Confirm both start and end dates, or leave both to be agreed.")
    if draft.get("contract_start") and preview["staged"]["issues"]:
        errors.append("Resolve staged-cover calculation/date issues.")
    for line in preview["lines"]:
        number = line["line"]
        if not line["priced"]:
            continue
        if line.get("source_eligibility") != "Yes":
            errors.append(f"Line {number}: maintenance eligibility is not verified.")
        if line.get("rate_status") != "Active":
            errors.append(f"Line {number}: rate group is not approved in the source.")
        if line.get("rrp_source") not in (
            "august_2026_master_list_price", "sage_exact_sku_price",
            "managed_price_override",
        ):
            errors.append(f"Line {number}: equipment price source is not accepted.")
        if (line.get("rrp_source") == "sage_exact_sku_price"
                and line.get("sage_reference", {}).get("review_overdue")):
            errors.append(f"Line {number}: selected Sage price source is overdue for review.")
        if any(reason not in ALLOWED_PRICE_NOTES for reason in line.get("coverage_review", [])):
            errors.append(f"Line {number}: commercial or equipment coverage exception requires correction.")
        if line.get("annual", 0) < line.get("minimum_annual", 0) - 0.01:
            errors.append(f"Line {number}: discounted price falls below the source minimum.")
    return errors



def _unconfirmed_serials(draft):
    """One line can establish only one machine serial, even when quantity > 1.

    The application must not invent serials from invoice OCR or imply every
    unit was identified by a single serial number. Missing/illegible numbers
    are permitted only with a recorded human commercial exception.
    """
    missing=[]
    for i,item in enumerate(draft.get("equipment", []),1):
        quantity=item.get("quantity")
        if type(quantity) is not int or quantity<1:
            continue
        confirmed=1 if str(item.get("serial") or "").strip() else 0
        if quantity>confirmed:
            missing.append({"line":i,"unconfirmed_units":quantity-confirmed})
    return {
        "total":sum(row["unconfirmed_units"] for row in missing),
        "lines":missing,
    }


def _quote_flags(fingerprints, errors, terms_ready):
    return {
        "all_equipment_priced_and_unambiguous": not errors,
        "approved_tariff_fingerprint_matches": _approved_tariff(fingerprints["pricing"]),
        "approved_terms_available": terms_ready,
        "live_issuance_opted_in_by_it": _issuance_enabled(),
        "commercial_approval_required": True,
        "customer_email_not_sent": True,
    }


def _tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS unified_customer_quotes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote_no TEXT UNIQUE NOT NULL, draft_id TEXT NOT NULL,
        draft_revision INTEGER NOT NULL, issued_at TEXT NOT NULL,
        issued_by TEXT NOT NULL, commercial_approval_ref TEXT NOT NULL,
        valid_until TEXT NOT NULL, source_fingerprints_json TEXT NOT NULL,
        terms_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL, pdf_sha256 TEXT NOT NULL,
        pdf BLOB NOT NULL,
        UNIQUE(draft_id,draft_revision)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_customer_quote_draft ON unified_customer_quotes(draft_id,issued_at)")


def _readiness(draft):
    preview, fingerprints = _price(draft)
    errors = _errors(draft, preview)
    try:
        _terms()
        terms_ready = True
    except HTTPException:
        terms_ready = False
    try:
        _issuer()
        issuer_ready = True
    except HTTPException:
        issuer_ready = False
    flags = _quote_flags(fingerprints, errors, terms_ready)
    serials=_unconfirmed_serials(draft)
    flags["verified_company_issuer_details"] = issuer_ready
    return {
        "draft_id": draft["id"],
        "revision": draft["revision"],
        "pricing_complete": preview["complete_price"],
        "annual_gbp": preview["annual_partial"],
        "term_gbp": preview["term_partial"],
        "issues": errors,
        "gates": flags,
        "internal_draft_pdf_available": not errors,
        "customer_issue_configured": (
            not errors and flags["approved_tariff_fingerprint_matches"] and
            flags["approved_terms_available"] and flags["verified_company_issuer_details"]
            and flags["live_issuance_opted_in_by_it"]
        ),
        "status": "READY_FOR_COMMERCIAL_APPROVAL" if not errors else "PRICING_REVIEW_REQUIRED",
        "no_quotation_has_been_issued": True,
        "serials_unconfirmed": serials["total"],
        "serials_unconfirmed_lines": serials["lines"],
        "serial_exception_reason_needed": bool(serials["total"]),
        "price_source_variances_requiring_ack": 0,
        "price_source_comparisons_available": sum(
            bool(line.get("source_price_comparison"))
            for line in preview["lines"]
        ),
        "source_price_policy": (
            "Business-confirmed equipment price basis: current August Master "
            "first, exact Sage item-code price for machines absent from that "
            "Master. Any source difference is informational, not a separate "
            "approval requirement. The maintenance service tariff, terms "
            "and each customer quotation still require sign-off."
        ),
    }


@router.get("/release-check")
def commercial_release_check():
    """Staff-facing prerequisites for the FIRST genuine customer quotation.

    This does not certify a draft, imply a tariff is approved, or write data.
    Sage is optional for August-master SKUs, but essential for historic items
    without a current master price. Actual line eligibility is checked later.
    """
    _quote_reader()
    from .quote_rrp_priority import source_snapshot as august_snapshot
    from .quote_sage_reference import snapshot as sage_snapshot

    def verify(fn):
        try:
            return True, fn(), ""
        except (HTTPException, OSError, ValueError) as exc:
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            return False, None, str(message)[:190]

    v10_ok, source, source_error = verify(quote_pricing.source_snapshot)
    august_ok, _, august_error = verify(august_snapshot) if v10_ok else (
        False, None, "Stage original V10 source files first."
    )
    sage_ok, sage, sage_error = verify(sage_snapshot)
    sage_ok = sage_ok and sage is not None
    if not sage_ok and not sage_error:
        sage_error = "Import the latest verified Sage Sales Price export."
    tariff_ok = bool(v10_ok and _approved_tariff(source[3]["pricing"]))
    terms_ok, _, terms_error = verify(_terms)
    issuer_ok, _, issuer_error = verify(_issuer)
    issue_ok = _issuance_enabled()

    steps = [
        {
            "key": "original_v10",
            "title": "Original V10 equipment, service rules and tariff source",
            "ready": v10_ok, "required": True,
            "next_action": "Admin: Original V10 & August Price Source Setup",
            "details": source_error if not v10_ok else "Original source fingerprints verified.",
        },
        {
            "key": "august_2026_master",
            "title": "August 2026 current equipment List Prices",
            "ready": august_ok, "required": True,
            "next_action": "Admin: verify the Master source in V10 Source Setup",
            "details": august_error if not august_ok else "Master source identity verified.",
        },
        {
            "key": "sage",
            "title": "Sage prices for machines absent from the August Master",
            "ready": sage_ok, "required": False,
            "next_action": "Admin: Sage Price List Refresh",
            "details": (
                "Sage export date " + str(sage["source_date"]) +
                ("; price review overdue." if sage["review_overdue"] else "; current review window.")
                if sage_ok else sage_error
            ),
        },
        {
            "key": "commercial_rates",
            "title": "Silver / Gold / Platinum tariff commercially authorised",
            "ready": tariff_ok, "required": True,
            "next_action": "Admin: Customer Quotation — Commercial Setup / Tariff",
            "details": "Authorise the exact V10 tariff fingerprint after reviewing rates.",
        },
        {
            "key": "maintenance_terms",
            "title": "Signed-off maintenance terms PDF",
            "ready": terms_ok, "required": True,
            "next_action": "Admin: Commercial Setup / Maintenance terms",
            "details": terms_error if not terms_ok else "The approved original PDF is intact.",
        },
        {
            "key": "legal_issuer",
            "title": "Verified Pulse Fitness company details",
            "ready": issuer_ok, "required": True,
            "next_action": "Admin: Commercial Setup / Company details",
            "details": issuer_error if not issuer_ok else "Company identity source verified.",
        },
        {
            "key": "customer_pdf_release",
            "title": "Customer PDF issuance explicitly enabled",
            "ready": issue_ok, "required": True,
            "next_action": "Admin: Commercial Setup / Enable customer quotes",
            "details": "Enable only after first real-data acceptance testing.",
        },
    ]
    return {
        "required_ready": all(step["ready"] for step in steps if step["required"]),
        "sage_fallback_ready": sage_ok,
        "items": steps,
        "next_steps": [step["next_action"] for step in steps if
                       step["required"] and not step["ready"]],
        "customer_quote_requires_per_draft_admin_approval": True,
        "customer_emails_not_sent_by_app": True,
        "commercial_signoff_not_inferred": True,
    }


@router.get("/drafts/{draft_id}/customer-quote/readiness")
def customer_quote_readiness(draft_id: str):
    _quote_reader()
    record = quote_drafts.get_draft(draft_id)
    return _readiness(record)


@router.get("/drafts/{draft_id}/customer-quote/internal-preview.pdf")
def internal_customer_quote_pdf(draft_id: str):
    """Watermarked PDF for checking layout, sums and equipment with staff."""
    quote_drafts._check_access()
    record = quote_drafts.get_draft(draft_id)
    preview, _ = _price(record)
    errors = _errors(record, preview)
    if errors:
        raise HTTPException(409, "Internal PDF blocked: " + "; ".join(errors[:6]))
    data = render_quote_pdf(
        draft=record, pricing=preview,
        quote_no="INTERNAL-" + draft_id[:12].upper(),
        prepared_date=dt.date.today().isoformat(),
        valid_until="NOT APPROVED",
        approval_ref="", approved_by="", internal_draft=True,
    )
    return Response(
        data, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="PULSE-DRAFT-{draft_id[:12]}.pdf"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        },
    )


def _approval(payload, revision):
    if type(payload.expected_revision) is not int or payload.expected_revision != revision:
        raise HTTPException(409, "Draft revision changed. Reload and recheck prices.")
    fields = (
        "confirm_customer_and_site", "confirm_equipment_and_serials",
        "confirm_package_price_and_discount",
        "confirm_maintenance_scope_and_terms", "confirm_vat_basis",
    )
    if not all(getattr(payload, key) is True for key in fields):
        raise HTTPException(422, "Customer, equipment, approved prices, scope, terms and VAT must all be confirmed.")
    ref = payload.commercial_approval_ref.strip()
    if not 8 <= len(ref) <= 100 or any(ord(c) < 32 for c in ref):
        raise HTTPException(422, "Record the commercial approval reference (8–100 characters).")
    try:
        valid = dt.date.fromisoformat(payload.valid_until)
    except ValueError as exc:
        raise HTTPException(422, "Enter a valid quote expiry date.") from exc
    today = dt.date.today()
    if not today <= valid <= today + dt.timedelta(days=180):
        raise HTTPException(422, "Quote expiry must be today through 180 days from today.")
    return valid, ref


@router.post("/drafts/{draft_id}/customer-quote/issue")
def issue_customer_quotation(draft_id: str, payload: QuoteApproval):
    """Issue exactly once per draft revision, atomically with archived PDF."""
    admin = _admin()
    quote_drafts._validate_id(draft_id)
    if not _issuance_enabled():
        raise HTTPException(503, "Customer PDF issuance requires explicit release approval in Commercial Setup.")
    terms, terms_sha = _terms()
    issuer, issuer_sha = _issuer()

    con = connect()
    try:
        _tables(con)
        con.execute("BEGIN IMMEDIATE")
        raw = con.execute(
            "SELECT id,revision,payload_json FROM unified_quote_drafts WHERE id=?",
            (draft_id,),
        ).fetchone()
        if raw is None:
            raise HTTPException(404, "Quotation draft not found.")
        draft = {"id": raw["id"], "revision": raw["revision"], **json.loads(raw["payload_json"])}
        valid_until, approval_ref = _approval(payload, draft["revision"])
        serials=_unconfirmed_serials(draft)
        serial_reason=payload.serial_exception_reason.strip()
        if serials["total"] and (
            not 15 <= len(serial_reason) <= 500
            or any(ord(c)<32 and c not in "\t\n" for c in serial_reason)
        ):
            raise HTTPException(
                422, "This quotation includes "+str(serials["total"])+
                " equipment unit(s) without verified serial numbers. "
                "Record a clear reason (15–500 characters) for the manager's exception."
            )
        if not serials["total"]:
            serial_reason=""

        existing = con.execute(
            "SELECT quote_no FROM unified_customer_quotes "
            "WHERE draft_id=? AND draft_revision=?",
            (draft_id, draft["revision"]),
        ).fetchone()
        if existing:
            raise HTTPException(
                409, f"This draft revision was already issued as {existing['quote_no']}. "
                "Edit and save a new draft revision before issuing a replacement."
            )

        preview, fingerprints = _price(draft)
        errors = _errors(draft, preview)
        if errors:
            raise HTTPException(409, "Resolve quotation issues: " + "; ".join(errors[:6]))
        comparisons = [
            line for line in preview["lines"]
            if line.get("source_price_comparison")
        ]
        # The accepted price-source hierarchy is a business decision, not
        # an arbitrary 5% discrepancy threshold. Full source values and
        # fingerprints are already archived for the individual quote.
        if not _approved_tariff(fingerprints["pricing"]):
            raise HTTPException(
                409, "The exact V10 tariff source has not been commercially authorised. "
                "Obtain signed-off tariff SHA-256 before issuing to customers."
            )

        # The quote terms PDF is frozen now, never copied from staff-entered text.
        # A database write lock prevents concurrent local Sage imports, price
        # corrections or draft edits while this snapshot is priced and archived.
        issued_at = now()
        snapshot = {
            "draft": draft, "priced": preview,
            "issued_by": admin, "issued_at": issued_at,
            "commercial_approval_ref": approval_ref,
            "valid_until": valid_until.isoformat(),
            "terms_sha256": terms_sha, "approved_tariff_sha256": fingerprints["pricing"],
            "issuer_sha256": issuer_sha, "issuer": issuer,
            "source_fingerprints": fingerprints,
            "customer_email_sent": False,
            "serial_exception_reason": serial_reason,
            "unconfirmed_serial_count": serials["total"],
            "unconfirmed_serial_lines": serials["lines"],
            "source_price_comparisons_informational": True,
            "source_price_comparison_lines": [
                item["line"] for item in comparisons
            ],
            "price_basis": (
                "August 2026 Master current machine; exact Sage item "
                "price for equipment absent from Master"
            ),
        }
        serialised = json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":"))
        digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
        pending = "PENDING-" + uuid.uuid4().hex
        cur = con.execute(
            "INSERT INTO unified_customer_quotes "
            "(quote_no,draft_id,draft_revision,issued_at,issued_by,"
            "commercial_approval_ref,valid_until,source_fingerprints_json,"
            "terms_sha256,snapshot_json,snapshot_sha256,pdf_sha256,pdf) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pending, draft_id, draft["revision"], issued_at, admin,
             approval_ref, valid_until.isoformat(), json.dumps(fingerprints),
             terms_sha, serialised, digest, "", b""),
        )
        quote_no = f"PFQ-{dt.date.today().year}-{cur.lastrowid:06d}"
        pdf = render_quote_pdf(
            draft=draft, pricing=preview, quote_no=quote_no,
            prepared_date=dt.date.today().isoformat(),
            valid_until=valid_until.isoformat(),
            approval_ref=approval_ref, approved_by=admin,
            terms_pdf=terms, issuer=issuer, internal_draft=False,
        )
        pdf_digest = hashlib.sha256(pdf).hexdigest()
        con.execute(
            "UPDATE unified_customer_quotes SET quote_no=?,pdf_sha256=?,pdf=? WHERE id=?",
            (quote_no, pdf_digest, pdf, cur.lastrowid),
        )
        # Reverify immutable V10/August source after building the PDF.
        next_preview, next_fingerprints = _price(draft)
        if (not _issuance_enabled()
                or not _approved_tariff(fingerprints["pricing"])
                or _terms()[1] != terms_sha
                or _issuer()[1] != issuer_sha):
            raise HTTPException(409, "Commercial release, terms or issuer changed during issue. Recheck the quotation.")
        if (next_fingerprints != fingerprints
                or next_preview["rrp_master"] != preview["rrp_master"]
                or next_preview["sage_sha256"] != preview["sage_sha256"]
                or [(r.get("rrp"), r.get("annual"), r.get("rrp_source"),
                     r.get("price_override")) for r in next_preview["lines"]]
                   != [(r.get("rrp"), r.get("annual"), r.get("rrp_source"),
                        r.get("price_override")) for r in preview["lines"]]):
            raise HTTPException(409, "Equipment, Sage or Master price source changed while issuing. Recheck quotation.")
        con.commit()
        return {
            "issued": True, "quote_no": quote_no, "draft_id": draft_id,
            "draft_revision": draft["revision"],
            "issued_at": issued_at, "valid_until": valid_until.isoformat(),
            "annual_gbp": preview["annual_partial"],
            "term_gbp": preview["term_partial"],
            "pdf_sha256": pdf_digest, "terms_sha256": terms_sha,
            "download_url": f"/api/quoting/customer-quotes/{quote_no}/download.pdf",
            "customer_email_sent": False,
            "contract_activated": False, "sage_sicon_written": False,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@router.get("/drafts/{draft_id}/customer-quotes")
def issued_quotation_history(draft_id: str):
    _quote_reader()
    quote_drafts._validate_id(draft_id)
    con = connect()
    try:
        _tables(con)
        rows = con.execute(
            "SELECT quote_no,draft_revision,issued_at,issued_by,valid_until,"
            "commercial_approval_ref,pdf_sha256,terms_sha256 "
            "FROM unified_customer_quotes WHERE draft_id=? "
            "ORDER BY id DESC LIMIT 50",
            (draft_id,),
        ).fetchall()
    finally:
        con.close()
    return {
        "draft_id": draft_id,
        "items": [dict(r) for r in rows],
        "read_only_archive": True,
        "email_sent": False,
    }


@router.get("/customer-quotes/{quote_no}/download.pdf")
def download_issued_customer_quote(quote_no: str):
    _quote_reader()
    if not NUMBER.fullmatch(quote_no):
        raise HTTPException(422, "Invalid issued quote reference.")
    con = connect()
    try:
        _tables(con)
        row = con.execute(
            "SELECT pdf,pdf_sha256,snapshot_json,snapshot_sha256 "
            "FROM unified_customer_quotes WHERE quote_no=?", (quote_no,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise HTTPException(404, "Issued quotation not found.")
    pdf = bytes(row["pdf"])
    digest = hashlib.sha256(pdf).hexdigest()
    snapshot_digest = hashlib.sha256(row["snapshot_json"].encode("utf-8")).hexdigest()
    if (digest != row["pdf_sha256"] or
            snapshot_digest != row["snapshot_sha256"] or
            not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF")):
        raise HTTPException(409, "Archived quotation integrity check failed; do not distribute.")
    return Response(
        pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="PulseFitness-{quote_no}.pdf"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "X-Pulse-PDF-SHA256": digest,
        },
    )
