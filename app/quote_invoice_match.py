"""Batch-match extracted invoice item codes against ONE activated Master Price List.

Exact SKU matches are automatically accepted as *code matches*, not as
maintenance eligibility or commercial quote approval. Only nonmatches need a
coordinator code correction. Spare parts are never auto-added as machines.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import quote_quick_draft
from .store import connect

router = APIRouter(prefix="/api/quoting", tags=["SmartQuote invoice auto-matching"])
CODE = re.compile(r"^[A-Z0-9][A-Z0-9 ._/#*()&+\-]{0,99}$")
MAX_INVOICES = 12
MAX_CODES = 1800


class InvoiceMatchBatch(BaseModel):
    import_ids: list[int]


def _get_evidence(source_ids):
    """Use structured source rows when available; fall back for older uploads."""
    with connect() as con:
        output = []
        for source_id in source_ids:
            record = con.execute(
                "SELECT id,type,evidence_json FROM imports WHERE id=?",
                (source_id,),
            ).fetchone()
            if record is None or record["type"] != "pdf":
                raise HTTPException(409, f"PDF source {source_id} was not found.")
            try:
                evidence = json.loads(record["evidence_json"] or "{}")
            except (ValueError, TypeError) as exc:
                raise HTTPException(409, "Uploaded invoice evidence is corrupt.") from exc
            if not isinstance(evidence, dict):
                raise HTTPException(409, "Uploaded invoice evidence is invalid.")
            grouped = {}
            document = evidence.get("quote_document")
            lines = document.get("lines", []) if isinstance(document, dict) else []
            mode = str(document.get("document_type") or "") if isinstance(document, dict) else ""
            if isinstance(lines, list) and lines and mode in ("invoice", "delivery_note"):
                for item in lines:
                    if not isinstance(item, dict):
                        continue
                    sku = str(item.get("sku") or "").strip().upper()
                    if not CODE.fullmatch(sku):
                        continue
                    pages = {
                        page for page in (item.get("pages") or [])
                        if type(page) is int and 1 <= page <= 9999
                    }
                    quantity = item.get("quantity")
                    if type(quantity) is not int or quantity < 0 or quantity > 10000:
                        continue
                    row = grouped.setdefault(sku, {
                        "pages": set(), "quantity": 0,
                        "serial_numbers": [], "document_type": mode,
                        "description": "", "excluded_hint": False,
                        "quantity_sent": 0, "quantity_received": 0
                    })
                    row["pages"].update(pages)
                    row["quantity"] += quantity
                    row["quantity_sent"] += (
                        item.get("quantity_sent") if type(item.get("quantity_sent")) is int
                        else quantity
                    )
                    row["quantity_received"] += (
                        item.get("quantity_received") if type(item.get("quantity_received")) is int
                        else quantity
                    )
                    row["excluded_hint"] |= item.get("excluded_hint") is True
                    row["description"] = row["description"] or str(item.get("description") or "")[:350]
                    raw_serials = item.get("serial_numbers") or []
                    if isinstance(raw_serials, list):
                        for candidate in raw_serials[:500]:
                            candidate = str(candidate).strip()[:120]
                            if candidate and candidate not in row["serial_numbers"] and len(row["serial_numbers"]) < 500:
                                row["serial_numbers"].append(candidate)
            else:
                # Previously imported documents have only generic reference
                # candidates. Keep them supported, with no inferred quantities.
                for entry in evidence.get("equipment_codes", []):
                    if not isinstance(entry, dict):
                        continue
                    sku = str(entry.get("value") or "").strip().upper()
                    if not CODE.fullmatch(sku):
                        continue
                    row = grouped.setdefault(sku, {
                        "pages": set(), "quantity": None,
                        "serial_numbers": [], "document_type": "legacy_reference",
                        "description": "", "excluded_hint": False,
                        "quantity_sent": None, "quantity_received": None
                    })
                    row["pages"].update(
                        p for p in (entry.get("pages") or [])
                        if type(p) is int and 1 <= p <= 9999
                    )
            output.append((source_id, grouped))
        return output

def classify_sku(sku, book):
    """Exact code lookup. A parts match is a match, but never a machine."""
    record = book["rows"].get(sku)
    if record is None:
        return {"status": "unmatched", "requires_coordinator_review": True,
                "auto_add_equipment": False}
    cents = record.get("price_pence")
    has_price = (type(cents) is int and cents > 0
                 and record.get("status") == "REFERENCE")
    machine = quote_quick_draft._machine_group(record.get("group"))
    if not machine:
        status = "matched_inventory_not_machine"
    elif not has_price:
        status = "matched_unpriced_or_held"
    else:
        status = "matched_equipment"
    result = {
        "status": status,
        "requires_coordinator_review": False,
        "auto_add_equipment": status == "matched_equipment",
        "master_description": str(record.get("description") or "")[:350],
        "master_group": str(record.get("group") or "")[:140],
        "price_available": has_price,
        "exact_code_match": True,
    }
    return result


def match_invoices(source_ids, book):
    if (not isinstance(source_ids, list) or not 1 <= len(source_ids) <= MAX_INVOICES
            or any(type(x) is not int or x < 1 for x in source_ids)
            or len(set(source_ids)) != len(source_ids)):
        raise HTTPException(422, "Choose 1–12 different imported PDF invoices.")
    evidence = _get_evidence(source_ids)
    if sum(len(items) for _, items in evidence) > MAX_CODES:
        raise HTTPException(422, "Too many extracted item codes to review safely.")
    output = []
    for source_id, codes in evidence:
        for sku, row in sorted(codes.items()):
            match = classify_sku(sku, book)
            # Explicit non-equipment headings/warranty/installation entries
            # cannot become machines, even if the SKU exists in the book.
            if row["excluded_hint"]:
                match = {**match, "status": "matched_inventory_not_machine",
                         "auto_add_equipment": False,
                         "requires_coordinator_review": False}
            # A delivery note distinguishes sent from actually received.
            # Never automatically quote equipment marked TO FOLLOW / 0 received.
            if row["document_type"] == "delivery_note" and row["quantity_received"] == 0:
                match = {**match, "status": "delivery_not_received",
                         "auto_add_equipment": False,
                         "requires_coordinator_review": False}
            output.append({
                "sku": sku, "source_import_id": source_id,
                "source_pages": sorted(row["pages"])[:30],
                "source_document_type": row["document_type"],
                "source_description": row["description"],
                "quantity_suggested": row["quantity"],
                "quantity_sent": row["quantity_sent"],
                "quantity_received": row["quantity_received"],
                "serial_numbers_suggested": row["serial_numbers"],
                "quantity_requires_confirmation": True,
                **match,
            })
    counts = {key: sum(row["status"] == key for row in output) for key in (
        "matched_equipment", "matched_inventory_not_machine",
        "matched_unpriced_or_held", "unmatched"
    )}
    if any(row["status"] == "delivery_not_received" for row in output):
        counts["delivery_not_received"] = sum(
            row["status"] == "delivery_not_received" for row in output
        )
    return {
        "price_book_revision": book["revision"],
        "price_book_sha256": book["sha256"],
        "results": output,
        "counts": counts,
        "automatic_matches_require_no_code_confirmation": True,
        "manual_review_required_only_for_unmatched_codes": True,
        "quantity_and_serials_still_need_verification": True,
        "not_an_approved_customer_quotation": True,
    }


@router.post("/invoice-auto-match")
def invoice_auto_match(batch: InvoiceMatchBatch):
    quote_quick_draft._staff()
    book = quote_quick_draft._book()
    return match_invoices(batch.import_ids, book)
