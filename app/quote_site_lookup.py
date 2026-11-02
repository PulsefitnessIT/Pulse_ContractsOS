"""Source-record site lookup for SmartQuote. No synthetic customers or inferred legal names."""
from __future__ import annotations

import json
from contextlib import closing

from fastapi import APIRouter, HTTPException, Query

from .pilot_access import actor
from .store import connect

router = APIRouter(prefix="/api/quoting", tags=["Verified-source site lookup"])


def find_sites(term: str, limit: int = 20):
    phrase = str(term or "").strip().casefold()
    if len(phrase) < 2 or len(phrase) > 100:
        raise HTTPException(422, "Enter 2–100 characters of a site name.")
    limit = max(1, min(int(limit), 30))
    matches = []
    with closing(connect()) as db:
        for row in db.execute(
            "SELECT id,row_key,status,source_sheet,source_row,fields "
            "FROM contracts WHERE status IN ('Active','Expired')"
        ):
            try:
                fields = json.loads(row["fields"])
                if not isinstance(fields, dict):
                    continue
            except (TypeError, ValueError):
                continue
            name = str(fields.get("Customer / site") or "").strip()
            if not name or phrase not in name.casefold():
                continue
            matches.append({
                "contract_id": row["id"],
                "site_label": name[:300],
                "recorded_contract_reference": str(fields.get("Contract number") or "")[:100],
                "recorded_cover_label": str(fields.get("Contract / warranty type") or "")[:150],
                "recorded_invoice_account": str(fields.get("Invoice account") or "")[:100],
                "recorded_site_account": str(fields.get("Site account") or "")[:100],
                "status": row["status"],
                "source_sheet": row["source_sheet"],
                "source_row": row["source_row"],
                "source_record_id": str(fields.get("Record ID") or "")[:100],
                "evidence": "Recorded Contracts OS row — not independent Sage/Sicon or contract verification",
            })
    # Match exact labels first, then active records, then original source row.
    matches.sort(key=lambda r: (
        r["site_label"].casefold() != phrase,
        r["status"] != "Active",
        r["site_label"].casefold(),
        r["source_sheet"],
        r["source_row"],
    ))
    return {"items": matches[:limit], "total": len(matches),
            "exact_source_rows_only": True, "legal_customer_name_inferred": False}


@router.get("/sites")
def site_suggestions(q: str = Query(..., min_length=2, max_length=100),
                     limit: int = Query(20, ge=1, le=30)):
    actor()
    return find_sites(q, limit)
