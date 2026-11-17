"""Read-only access to five additional worksheets in the 15-tab Pulse Master.

Source rows are evidence, NOT approved live contracts, confirmed PPM
entitlements, completed services, posted invoices or quoted machinery.
"""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Query

from .data_readiness import PULSE_15_SOURCE_SHEETS
from .quote_quick_draft import _staff
from .store import connect

router = APIRouter(prefix="/api/master-sources", tags=["Source worksheet review"])


def _metadata(db):
    tables={row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "auxiliary_source_rows" not in tables:
        return {}
    return {row[0]: {"records": row[1], "source_sha256": row[2]}
            for row in db.execute(
                "SELECT sheet,COUNT(*),MIN(source_sha256) "
                "FROM auxiliary_source_rows GROUP BY sheet"
            )}


@router.get("")
def list_master_source_registers():
    _staff()
    with connect() as db:
        count = _metadata(db)
    return {
        "sheets": [
            {"name":sheet, "records":count.get(sheet,{}).get("records",0)}
            for sheet in PULSE_15_SOURCE_SHEETS
        ],
        "has_15_tab_source": all(
            count.get(sheet,{}).get("records",0)>0
            for sheet in PULSE_15_SOURCE_SHEETS
        ),
        "read_only": True,
        "source_data_not_approved_entitlements": True,
        "warning": (
            "These are original Master source rows. VERIFY PPM and SICON ONLY "
            "are not confirmed maintenance obligations or new contracts."
        ),
    }


@router.get("/{sheet_name}")
def browse_master_source_register(
        sheet_name: str, q: str = Query("", max_length=100),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100000)):
    _staff()
    if sheet_name not in PULSE_15_SOURCE_SHEETS:
        raise HTTPException(404, "Unknown approved source worksheet")
    with connect() as db:
        if not _metadata(db):
            raise HTTPException(
                409, "15-tab source evidence is not loaded on this device"
            )
        term = str(q or "").strip()
        where = "sheet=?"
        arguments = [sheet_name]
        if term:
            where += " AND fields LIKE ? ESCAPE '\\'"
            # Literal substring, not an accidental wildcard expression.
            clean = term.replace("\\", "\\\\").replace("%","\\%").replace("_","\\_")
            arguments.append("%"+clean+"%")
        count = db.execute(
            "SELECT COUNT(*) FROM auxiliary_source_rows WHERE "+where,
            arguments
        ).fetchone()[0]
        data = db.execute(
            "SELECT source_row,fields,source_sha256 FROM auxiliary_source_rows "
            "WHERE "+where+" ORDER BY source_row LIMIT ? OFFSET ?",
            arguments+[limit,offset]
        ).fetchall()
    return {
        "sheet": sheet_name, "total": count, "offset": offset,
        "limit": limit,
        "source_sha256": data[0]["source_sha256"] if data else None,
        "rows": [
            {"source_row":row["source_row"], "fields":json.loads(row["fields"])}
            for row in data
        ],
        "read_only": True,
        "not_verified_commercial_or_service_records": True,
    }
