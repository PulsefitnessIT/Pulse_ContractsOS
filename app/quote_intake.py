"""SmartQuote -> Contracts OS: controlled, idempotent, read-only accepted-quote intake.

This is NOT a Sage/Sicon import and does not mutate existing contract rows.
Only source-provenance records are stored in separate SQLite tables. All customer
payloads remain in the protected Contracts OS runtime database, not GitHub.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, HTTPException, Body
from .store import connect, now
from .pilot_access import actor

router = APIRouter(prefix="/api/smartquote", tags=["SmartQuote intake"])
SCHEMA = "pulse.smartquote.accepted.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 2000
REF_MAX = 160


class IntakeError(ValueError):
    pass


def _text(value: Any, *, maximum: int = 300) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int)):
        raise IntakeError("Unexpected object in text field.")
    value = str(value).strip()
    if len(value) > maximum:
        raise IntakeError("One of the imported text fields is too long.")
    return value


def _date(value: Any, *, required: bool = False) -> str:
    value = _text(value, maximum=10)
    if not value and not required:
        return ""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise IntakeError("Expected a valid YYYY-MM-DD coverage date.") from exc


def _amount(value: Any) -> Decimal:
    try:
        if isinstance(value, bool) or value is None:
            raise InvalidOperation()
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal("100000000"):
            raise InvalidOperation()
        return number.quantize(Decimal(".01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise IntakeError("Invalid or missing accepted price; no financial values were imported.") from exc


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise IntakeError(f"{name} must be a JSON object.")
    return value


def validate(payload: dict) -> dict:
    """Canonical minimal handoff. No priced machine or acceptance can be guessed."""
    data = _object(payload, "The quote")
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise IntakeError("Quote data is too large for the guarded pilot importer.")
    if data.get("schema_version") != SCHEMA or data.get("source_system") != "Pulse SmartQuote":
        raise IntakeError("Unsupported SmartQuote handoff format.")
    if data.get("acceptance_status") != "Accepted":
        raise IntakeError("Only quotes marked Accepted may enter the contract setup worklist.")
    source_id = _text(data.get("source_quote_id"), maximum=REF_MAX)
    quote_no = _text(data.get("quote_number"), maximum=REF_MAX)
    if not source_id or not quote_no:
        raise IntakeError("Quote source ID and quote number are both required.")
    customer = _object(data.get("customer"), "customer")
    contract = _object(data.get("contract"), "contract")
    pricing = _object(data.get("pricing"), "pricing")
    legal = _text(customer.get("legal_name"), maximum=250)
    site = _text(customer.get("site_name"), maximum=250)
    if not legal or not site:
        raise IntakeError("The customer and site names must be present in the accepted quote.")
    start = _date(contract.get("start_date"))
    end = _date(contract.get("end_date"))
    if start and end and start > end:
        raise IntakeError("Contract end date precedes commencement.")
    package = _text(contract.get("package"), maximum=20)
    if package not in ("Silver", "Gold", "Platinum", "Mixed"):
        raise IntakeError("Expected a recognised maintenance package.")
    lines = data.get("equipment")
    if not isinstance(lines, list) or not lines or len(lines) > MAX_LINES:
        raise IntakeError("Expected 1–2,000 equipment lines; nothing was imported.")
    seen = set()
    checked_lines = []
    sum_annual = Decimal("0.00")
    for ix, item in enumerate(lines, 1):
        line = _object(item, f"equipment line {ix}")
        line_id = _text(line.get("source_line_id"), maximum=100)
        if not line_id or line_id in seen:
            raise IntakeError("Equipment line IDs must be unique and non-empty.")
        seen.add(line_id)
        sku = _text(line.get("item_code"), maximum=110).upper()
        if not sku:
            raise IntakeError("A machine is missing its item code. Verify it in SmartQuote first.")
        try:
            qty = int(line.get("quantity"))
            if qty <= 0 or qty > 10000 or str(line.get("quantity")).strip() not in (str(qty),):
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise IntakeError("Equipment quantities must be positive whole numbers.") from exc
        serials = line.get("serial_numbers", [])
        if not isinstance(serials, list) or len(serials) > qty:
            raise IntakeError("Equipment serials must be a list with at most one per unit.")
        serials = [_text(s, maximum=120) for s in serials]
        if len(set(x for x in serials if x)) != len([x for x in serials if x]):
            raise IntakeError("An equipment line repeats a serial number.")
        annual = _amount(line.get("annual_total"))
        cover = _date(line.get("cover_start"))
        expiry = _date(line.get("cover_end"))
        if cover and expiry and cover > expiry:
            raise IntakeError("An equipment cover date is after its expiry.")
        if start and cover and cover < start:
            raise IntakeError("An equipment cover date precedes its contract start.")
        if end and expiry and expiry > end:
            raise IntakeError("An equipment cover date exceeds the contract end.")
        checked_lines.append({
            "source_line_id": line_id,
            "item_code": sku,
            "description": _text(line.get("description"), maximum=600),
            "model": _text(line.get("model"), maximum=160),
            "quantity": qty,
            "serial_numbers": serials,
            "cover_start": cover,
            "cover_end": expiry,
            "annual_total": float(annual),
            "first_period_total": float(_amount(line.get("first_period_total", annual))),
            "price_basis": _text(line.get("price_basis"), maximum=120),
        })
        sum_annual += annual
    if _amount(pricing.get("annual_total")) != sum_annual:
        raise IntakeError("The accepted annual total does not reconcile to the machine lines.")
    full = {
        "schema_version": SCHEMA,
        "source_system": "Pulse SmartQuote",
        "source_quote_id": source_id,
        "quote_number": quote_no,
        "source_revision": _text(data.get("source_revision"), maximum=100),
        "acceptance_status": "Accepted",
        "customer": {
            "legal_name": legal, "site_name": site,
            "sage_account_ref": _text(customer.get("sage_account_ref"), maximum=REF_MAX),
            "sicon_site_ref": _text(customer.get("sicon_site_ref"), maximum=REF_MAX),
            "billing_address": _text(customer.get("billing_address"), maximum=1200),
            "site_address": _text(customer.get("site_address"), maximum=1200),
            "contact_name": _text(customer.get("contact_name"), maximum=180),
            "contact_email": _text(customer.get("contact_email"), maximum=250),
        },
        "contract": {
            "reference": _text(contract.get("reference"), maximum=REF_MAX),
            "package": package, "start_date": start, "end_date": end,
            "payment_terms": _text(contract.get("payment_terms"), maximum=100),
            "visits": contract.get("visits"),
        },
        "pricing": {
            "annual_total": float(_amount(pricing.get("annual_total"))),
            "term_total": float(_amount(pricing.get("term_total"))),
            "currency": "GBP",
            "commercially_approved": pricing.get("commercially_approved") is True,
            "source_quote_pdf_sha256": _text(pricing.get("source_quote_pdf_sha256"), maximum=64),
        },
        "equipment": checked_lines,
    }
    return full


def fingerprint(quote: dict) -> str:
    blob = json.dumps(quote, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def assess(quote: dict) -> dict:
    """Ask for only blocking missing details; never fabricate source references."""
    c, contract, pricing = quote["customer"], quote["contract"], quote["pricing"]
    items = quote["equipment"]
    missing = []
    for value, label in [
        (c["sage_account_ref"], "Sage customer account reference"),
        (c["sicon_site_ref"], "Verified Sicon site/location reference"),
        (contract["start_date"], "Contract start date"),
        (contract["end_date"], "Contract end date"),
    ]:
        if not value:
            missing.append(label)
    if not pricing["commercially_approved"]:
        missing.append("Approved maintenance tariff / accepted price evidence")
    if not pricing["source_quote_pdf_sha256"]:
        missing.append("Archived accepted quote PDF fingerprint")
    unaccounted = sum(max(0, a["quantity"] - len([x for x in a["serial_numbers"] if x])) for a in items)
    if unaccounted:
        missing.append(f"{unaccounted} missing machine serial number(s)")
    if any(not a["cover_start"] or not a["cover_end"] for a in items):
        missing.append("Individual equipment start/end dates")
    return {
        "status": "Ready for coordinator review" if not missing else "Needs details",
        "ready_for_setup": not missing,
        "missing": missing,
        "equipment_lines": len(items),
        "equipment_units": sum(a["quantity"] for a in items),
        "staged_groups": sorted(set(a["cover_start"] for a in items if a["cover_start"])),
        "annual_amount": pricing["annual_total"],
        "term_amount": pricing["term_total"],
    }


def ensure_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS smartquote_intakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_quote_id TEXT NOT NULL,
            quote_number TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            source_revision TEXT NOT NULL DEFAULT '',
            source_status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            linked_contract_id INTEGER,
            payload_json TEXT NOT NULL,
            readiness_json TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            imported_by TEXT NOT NULL,
            FOREIGN KEY(linked_contract_id) REFERENCES contracts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_smartquote_intake_quote ON smartquote_intakes(source_quote_id,id);
        CREATE TABLE IF NOT EXISTS smartquote_intake_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intake_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            at TEXT NOT NULL,
            FOREIGN KEY(intake_id) REFERENCES smartquote_intakes(id)
        );
    """)


def exact_matches(con: sqlite3.Connection, quote: dict) -> list[dict]:
    """Account/site/contract refs only. Never link by name similarity alone."""
    c, contract = quote["customer"], quote["contract"]
    account = c["sage_account_ref"].casefold()
    site = c["sicon_site_ref"].casefold()
    reference = contract["reference"].casefold()
    if not any((account, site, reference)):
        return []
    matches = []
    for r in con.execute("SELECT id,status,fields FROM contracts"):
        try:
            f = json.loads(r["fields"])
        except (TypeError, ValueError):
            continue
        invoice = _text(f.get("Invoice account")).casefold()
        location = _text(f.get("Site account")).casefold()
        number = _text(f.get("Contract number")).casefold()
        reasons = []
        if reference and number and reference == number:
            reasons.append("Exact contract reference")
        if account and site and invoice == account and location == site:
            reasons.append("Exact Sage account + site reference")
        if reasons:
            matches.append({"contract_id": r["id"], "status": r["status"], "match_reasons": reasons,
                            "customer_site": _text(f.get("Customer / site"))})
    return matches[:15]


def preview_data(con: sqlite3.Connection, payload: dict) -> dict:
    quote = validate(payload)
    ensure_tables(con)
    digest = fingerprint(quote)
    earlier = con.execute("SELECT id FROM smartquote_intakes WHERE fingerprint=?", (digest,)).fetchone()
    same_source = con.execute("SELECT id FROM smartquote_intakes WHERE source_quote_id=? ORDER BY id DESC LIMIT 1",
                              (quote["source_quote_id"],)).fetchone()
    return {"fingerprint": digest, "canonical": quote, "readiness": assess(quote),
            "exact_candidates": exact_matches(con, quote),
            "already_imported_id": earlier["id"] if earlier else None,
            "prior_revision_id": same_source["id"] if same_source else None}


def register(con: sqlite3.Connection, payload: dict, username="Coordinator") -> dict:
    prepared = preview_data(con, payload)
    if prepared["already_imported_id"]:
        return {"id": prepared["already_imported_id"], "already_imported": True,
                "readiness": prepared["readiness"],
                "exact_candidates": prepared["exact_candidates"]}
    quote = prepared["canonical"]
    cur = con.execute("""
        INSERT INTO smartquote_intakes(source_quote_id,quote_number,fingerprint,source_revision,
           source_status,review_status,linked_contract_id,payload_json,readiness_json,imported_at,imported_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (quote["source_quote_id"], quote["quote_number"], prepared["fingerprint"],
          quote["source_revision"], "Accepted", prepared["readiness"]["status"], None,
          json.dumps(quote, ensure_ascii=False), json.dumps(prepared["readiness"], ensure_ascii=False),
          now(), _text(username, maximum=100)))
    con.execute("INSERT INTO smartquote_intake_history(intake_id,action,actor,notes,at) VALUES(?,?,?,?,?)",
                (cur.lastrowid, "IMPORTED_FOR_REVIEW", username,
                 "Source quote copied into separate review worklist, no contract or asset changes", now()))
    con.commit()
    return {"id": cur.lastrowid, "already_imported": False,
            "readiness": prepared["readiness"],
            "exact_candidates": prepared["exact_candidates"]}


@router.get("/intakes")
def list_intakes(limit: int = 50):
    limit = max(1, min(limit, 100))
    con = connect()
    try:
        ensure_tables(con)
        records = con.execute("""SELECT id,quote_number,review_status,imported_at,imported_by,
                  linked_contract_id,source_quote_id,readiness_json
                  FROM smartquote_intakes ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
        return {"items": [{**dict(r), "readiness": json.loads(r["readiness_json"])} for r in records]}
    finally:
        con.close()


@router.get("/intakes/{iid}")
def intake_detail(iid: int):
    con = connect()
    try:
        ensure_tables(con)
        r = con.execute("SELECT * FROM smartquote_intakes WHERE id=?", (iid,)).fetchone()
        if not r:
            raise HTTPException(404, "Accepted quote intake not found")
        quote = json.loads(r["payload_json"])
        return {
            "id": iid, "quote": quote, "review_status": r["review_status"],
            "linked_contract_id": r["linked_contract_id"],
            "readiness": json.loads(r["readiness_json"]),
            "candidates": exact_matches(con, quote),
            "history": [dict(x) for x in con.execute(
                "SELECT action,actor,notes,at FROM smartquote_intake_history WHERE intake_id=? ORDER BY id",
                (iid,))],
        }
    finally:
        con.close()


@router.post("/intakes/preview")
def preview_intake(payload: dict = Body(...)):
    try:
        con = connect()
        try:
            return preview_data(con, payload)
        finally:
            con.close()
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/intakes")
def import_intake(payload: dict = Body(...)):
    try:
        con = connect()
        try:
            return register(con, payload, actor())
        finally:
            con.close()
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/intakes/{iid}/link")
def link_existing(iid: int, request_body: dict = Body(...)):
    """Links to a verified register record without editing that record or its equipment."""
    try:
        target = int(request_body.get("contract_id"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Select a valid existing contract.") from exc
    note = _text(request_body.get("note"), maximum=500)
    if len(note) < 8:
        raise HTTPException(400, "Record brief evidence for the linkage.")
    con = connect()
    try:
        ensure_tables(con)
        item = con.execute("SELECT * FROM smartquote_intakes WHERE id=?", (iid,)).fetchone()
        if not item:
            raise HTTPException(404, "Accepted quote intake not found")
        if item["linked_contract_id"] is not None:
            if item["linked_contract_id"] == target:
                return {"id": iid, "linked_contract_id": target, "unchanged": True}
            raise HTTPException(409, "This intake is already linked. Investigate before changing the contract reference.")
        matches = exact_matches(con, json.loads(item["payload_json"]))
        if target not in {m["contract_id"] for m in matches}:
            raise HTTPException(409, "Cannot link by a name-only guess. Verify customer/site or exact contract reference first.")
        con.execute("UPDATE smartquote_intakes SET linked_contract_id=? WHERE id=?", (target, iid))
        con.execute("INSERT INTO smartquote_intake_history(intake_id,action,actor,notes,at) VALUES(?,?,?,?,?)",
                    (iid, "LINKED_TO_VERIFIED_CONTRACT", actor(), note, now()))
        con.commit()
        return {"id": iid, "linked_contract_id": target, "unchanged": False}
    finally:
        con.close()
