"""Source-based SmartQuote quick draft independent of legacy V10 service mappings.

This is intentionally INTERNAL ONLY. One current, administrator-activated
price book provides the equipment prices; staff supply or confirm maintenance
percentages/fixed charges. It cannot issue customer PDFs or approve cover.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from . import pilot_access
from .quote_price_book import active_book
from .quote_sage_reference import sage_machine_group_candidate

router = APIRouter(prefix="/api/quoting/quick-draft", tags=["Internal fast SmartQuote draft"])

MORE_MACHINE_GROUPS = frozenset({
    "Equipment with Serial Numbers",
    "Equipment without serial numbers",
})
PENNY = Decimal("0.01")


class QuickDraftLine(BaseModel):
    sku: str
    quantity: int = 1
    serials: str = ""
    notes: str = ""
    annual_rate_percent: Optional[Decimal] = None
    fixed_annual_unit_gbp: Optional[Decimal] = None


class QuickDraft(BaseModel):
    customer: str
    site: str
    package: str = "Gold"
    term_years: int = 1
    discount_percent: Decimal = Decimal("0")
    notes: str = ""
    lines: list[QuickDraftLine]
    expected_price_book_sha256: str = ""


def _staff():
    if (not pilot_access.PILOT_MODE
            or pilot_access.current_role() not in ("Coordinator", "Admin")):
        raise HTTPException(403, "Named SmartQuote staff account required.")
    who = pilot_access.actor("")
    if not isinstance(who, str) or len(who.strip()) < 2:
        raise HTTPException(403, "Named SmartQuote staff account required.")
    return who


def _machine_group(value):
    label = str(value or "").strip()
    return (sage_machine_group_candidate(label)
            or label.casefold() in {x.casefold() for x in MORE_MACHINE_GROUPS})


def _book():
    source = active_book()
    if source is None:
        raise HTTPException(
            503,
            "Unified Master Price List is not activated. An Admin must import "
            "the merged 2026 price list under Unified Master Price List first.",
        )
    return source


def _decimal(value, name, *, low=0, high=1000000):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not Decimal(str(low)) <= result <= Decimal(str(high)):
            raise InvalidOperation()
        return result
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise HTTPException(422, f"Invalid {name}.") from exc


def _money(value):
    return str(Decimal(value).quantize(PENNY, rounding=ROUND_HALF_UP))


@router.get("/status")
def quick_quote_source_status():
    """Coordinator-facing fingerprint check before printing an internal draft."""
    _staff()
    source = _book()
    return {
        "price_book_revision": source["revision"],
        "price_book_sha256": source["sha256"],
        "single_active_master": True,
        "customer_issue_enabled": False,
    }


@router.get("/search")
def search_equipment(
        q: str = Query(..., min_length=2, max_length=100),
        limit: int = Query(20, ge=1, le=50)):
    """Machine-group candidates only. Never advertise Sage parts as machines."""
    _staff()
    book = _book()
    term = str(q).strip().casefold()
    if len(term) < 2:
        raise HTTPException(422, "Enter at least two characters.")
    matches = []
    for sku, row in book["rows"].items():
        if not _machine_group(row.get("group")):
            continue
        name = str(row.get("description") or "")
        if term not in sku.casefold() and term not in name.casefold():
            continue
        cents = row.get("price_pence")
        if type(cents) is not int or cents <= 0 or row.get("status") != "REFERENCE":
            continue
        rank = (1000 if sku.casefold() == term
                else 800 if sku.casefold().startswith(term)
                else 500 if term in sku.casefold() else 100)
        matches.append((rank, sku, {
            "sku": sku,
            "name": name[:300],
            "group": str(row.get("group") or "")[:120],
            "equipment_price_gbp": _money(Decimal(cents) / 100),
            "source": str(row.get("origin") or "")[:120],
            "maintenance_eligible": False,
            "requires_rate_and_scope_approval": True,
        }))
    matches.sort(key=lambda x: (-x[0], x[1]))
    return {
        "results": [result for _, __, result in matches[:limit]],
        "matching_equipment_codes": len(matches),
        "price_book_revision": book["revision"],
        "price_book_sha256": book["sha256"],
        "inventory_parts_excluded": True,
        "read_only": True,
        "not_an_approved_maintenance_quotation": True,
    }


def calculate(draft: QuickDraft, book):
    if not 1 <= len(draft.lines) <= 250:
        raise HTTPException(422, "Select between 1 and 250 equipment lines.")
    if not 1 <= draft.term_years <= 5 or draft.package not in (
            "Silver", "Gold", "Platinum", "Custom"):
        raise HTTPException(422, "Invalid package or contract term.")
    discount = _decimal(draft.discount_percent, "discount", high=100)
    if not str(draft.customer).strip() or not str(draft.site).strip():
        raise HTTPException(422, "Enter a customer and site.")
    if draft.expected_price_book_sha256 and (
            draft.expected_price_book_sha256 != book["sha256"]):
        raise HTTPException(
            409, "The unified Master changed while preparing this quote. "
            "Recheck every equipment price before recalculating."
        )
    results = []
    issues = []
    annual_pence = 0
    for index, item in enumerate(draft.lines, 1):
        sku = str(item.sku or "").strip().upper()
        if len(sku) > 100 or not sku:
            raise HTTPException(422, f"Equipment line {index} needs a valid SKU.")
        if type(item.quantity) is not int or not 1 <= item.quantity <= 999:
            raise HTTPException(422, f"Equipment line {index}: invalid quantity.")
        source = book["rows"].get(sku)
        item_issues = []
        if not source:
            item_issues.append("Not found in the unified Master.")
        elif not _machine_group(source.get("group")):
            item_issues.append(
                "Sage inventory/spare-part classification; confirm a real machine "
                "before maintenance quotation."
            )
        if source:
            price = source.get("price_pence")
            if type(price) is not int or price <= 0 or source.get("status") != "REFERENCE":
                item_issues.append("Price is missing, zero or held for administrator review.")
        rate = None
        fixed = None
        if item.fixed_annual_unit_gbp is not None:
            fixed = _decimal(item.fixed_annual_unit_gbp, "fixed annual charge")
            fixed = fixed.quantize(PENNY, rounding=ROUND_HALF_UP)
            if fixed != item.fixed_annual_unit_gbp:
                raise HTTPException(422, "Fixed annual price must have at most two decimals.")
        elif item.annual_rate_percent is not None:
            rate = _decimal(item.annual_rate_percent, "annual percentage", high=100)
        else:
            item_issues.append("Enter an annual service percentage or fixed annual charge.")
        line_pence = None
        unit_pence = None
        if not item_issues:
            base_pence = (
                fixed * 100 if fixed is not None else
                (Decimal(price) * rate / 100)
            )
            after_discount = (
                base_pence * (Decimal("100") - discount) / 100
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            unit_pence = int(after_discount)
            line_pence = unit_pence * item.quantity
            annual_pence += line_pence
        if not str(item.serials or "").strip():
            issues.append(f"Line {index}: machine serial numbers require confirmation.")
        issues.extend(f"Line {index}: {reason}" for reason in item_issues)
        results.append({
            "line": index, "sku": sku,
            "name": str((source or {}).get("description") or sku)[:300],
            "group": str((source or {}).get("group") or "")[:120],
            "quantity": item.quantity,
            "serials": str(item.serials or "")[:1000],
            "notes": str(item.notes or "")[:1500],
            "reference_price_gbp": (
                _money(Decimal(price) / 100)
                if source and type(price) is int and price > 0 else None
            ),
            "price_origin": str((source or {}).get("origin") or "")[:100],
            "annual_unit_gbp": (
                _money(Decimal(unit_pence) / 100)
                if unit_pence is not None else None
            ),
            "annual_line_gbp": (
                _money(Decimal(line_pence) / 100)
                if line_pence is not None else None
            ),
            "rate_percent": str(rate) if rate is not None else None,
            "fixed_annual_unit_gbp": str(fixed) if fixed is not None else None,
            "priced": not item_issues, "issues": item_issues,
        })
    payload = draft.model_dump(mode="json")
    reference_digest = hashlib.sha256(
        json.dumps({"quote": payload, "master_sha": book["sha256"]},
                   sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "draft_reference": "INTERNAL-" + reference_digest[:12].upper(),
        "customer": str(draft.customer).strip()[:250],
        "site": str(draft.site).strip()[:250],
        "package": draft.package,
        "term_years": draft.term_years,
        "discount_percent": str(discount),
        "price_book_revision": book["revision"],
        "price_book_sha256": book["sha256"],
        "line_count": len(results),
        "priced_line_count": sum(1 for row in results if row["priced"]),
        "annual_partial_gbp": _money(Decimal(annual_pence) / 100),
        "monthly_partial_gbp": _money(Decimal(annual_pence) / 1200),
        "term_partial_gbp": _money(Decimal(annual_pence * draft.term_years) / 100),
        "complete_calculation": all(row["priced"] for row in results),
        "equipment": results,
        "issues": issues,
        "scope_review_needed": True,
        "pricing_tariffs_not_approved": True,
        "customer_issue_enabled": False,
        "watermark": "INTERNAL DRAFT - NOT AUTHORISED FOR CUSTOMER ISSUE",
        "warning": (
            "Source equipment prices only. Historical percentage guides or "
            "manual charges require Pulse commercial approval, confirmed "
            "machine eligibility, package scope, serials and agreed terms."
        ),
    }


@router.post("/internal-preview.pdf")
def quick_internal_pdf(draft: QuickDraft):
    """Download a branded internal estimate, never an authorised customer quote."""
    _staff()
    if not draft.expected_price_book_sha256:
        raise HTTPException(409, "Recalculate before downloading to lock price version.")
    current = _book()
    calculated = calculate(draft, current)
    if not calculated["complete_calculation"]:
        raise HTTPException(409, "Resolve all equipment prices/rates before downloading.")
    from .quote_quick_pdf import render_quick_internal_pdf
    pdf = render_quick_internal_pdf(draft, calculated)
    # Avoid returning stale pricing if an administrator changed the price
    # book while the branded document was being prepared.
    newest = _book()
    if newest["sha256"] != current["sha256"]:
        raise HTTPException(409, "Unified Master changed during PDF creation. Recalculate.")
    name = "Pulse_Fitness_Internal_" + calculated["draft_reference"] + ".pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/preview")
def quick_quote_preview(draft: QuickDraft):
    _staff()
    return calculate(draft, _book())
