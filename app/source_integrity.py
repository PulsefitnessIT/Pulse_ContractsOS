"""Evidence-only audit of the privately staged Maintenance Master.

Never imports customer values into GitHub, overwrites an existing database, or
treats missing amounts as zero. All counts and source labels come from Excel.
"""
from __future__ import annotations

import collections
import hashlib
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .data_readiness import WORKSHEETS, workbook_check, _amount_kind
from .excel_io import ExcelSource, REGISTER_SHEETS
from .store import DB, TEMPLATE, connect
from .pilot_access import actor

router = APIRouter(prefix="/api/pilot", tags=["Factual source provenance"])
REQUIRED_COLUMNS = {
    "Maintenance Database": {"Customer / site", "Record ID", "Contract number",
        "Contract / warranty type", "Start date", "Expiry date",
        "Contract amount (£)", "Invoice Code"},
    "Expired": {"Customer / site", "Record ID", "Contract number",
        "Contract / warranty type", "Expiry date", "Contract amount (£)"},
}


def source_row_key(sheet: str, row: int, record_id: str, repeated_ids: set[str]) -> str:
    """Keep original IDs unless ambiguous. Never modify original field values."""
    if record_id and record_id not in repeated_ids:
        return record_id
    return f"SOURCE_ROW:{sheet}:{row}"


def source_audit(path):
    path = Path(path)
    structure = workbook_check(path)
    if not structure["valid"] or structure["sheet_names"] != WORKSHEETS:
        raise ValueError("The source must be the verified eight-sheet Maintenance Master.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    src = ExcelSource(path)
    try:
        rows = {}
        summaries = {}
        ids = collections.Counter()
        locations = collections.defaultdict(list)
        for sheet in REGISTER_SHEETS:
            headers, entries = src.records(sheet)
            missing = sorted(REQUIRED_COLUMNS[sheet] - set(headers))
            if missing:
                raise ValueError(f"{sheet} is missing required source columns: {', '.join(missing)}")
            selected = []
            covers = collections.Counter()
            amount_counts = collections.Counter()
            incomplete = collections.Counter()
            for item in entries:
                fields = item["fields"]
                if not str(fields.get("Customer / site") or "").strip():
                    continue
                selected.append(item)
                original_id = str(fields.get("Record ID") or "").strip()
                if original_id:
                    ids[original_id] += 1
                    locations[original_id].append((sheet, item["row"]))
                else:
                    incomplete["missing_source_record_id"] += 1
                cover = str(fields.get("Contract / warranty type") or "").strip()
                covers[cover or "(blank in source)"] += 1
                amount_counts[_amount_kind(fields.get("Contract amount (£)"))] += 1
                for source_key, target_key in (
                    ("Contract number", "missing_contract_reference"),
                    ("Start date", "missing_start_date"),
                    ("Expiry date", "missing_expiry_date"),
                    ("Invoice Code", "missing_invoice_code"),
                ):
                    if source_key in headers and not str(fields.get(source_key) or "").strip():
                        incomplete[target_key] += 1
            rows[sheet] = selected
            summaries[sheet] = {
                "populated_site_rows": len(selected),
                "amounts_as_recorded": {
                    kind: amount_counts[kind]
                    for kind in ("positive", "zero", "negative", "missing", "invalid")
                },
                "missing_fields": dict(incomplete),
                "cover_labels_as_recorded": dict(sorted(covers.items(),
                    key=lambda item: (-item[1], item[0]))),
                "cover_labels_are_not_contract_classifications": True,
            }
        repeats = {value for value, count in ids.items() if count > 1}
        internal_keys = [
            source_row_key(sheet, item["row"],
                str(item["fields"].get("Record ID") or "").strip(), repeats)
            for sheet, entries in rows.items() for item in entries
        ]
        if len(set(internal_keys)) != len(internal_keys):
            raise ValueError("Source record keys conflict after duplicate handling.")
        return {
            "workbook_sha256": digest.hexdigest(),
            "worksheet_names": list(WORKSHEETS),
            "source_status": "read from approved private Excel source; not ERP-certified",
            "source_id_duplicates": {
                "repeated_distinct_ids": len(repeats),
                "extra_duplicate_rows": sum(ids[x] - 1 for x in repeats),
                "affected_source_rows": [
                    {"sheet": sheet, "row": row}
                    for value in sorted(repeats) for sheet, row in locations[value]
                ],
            },
            "registers": summaries,
            "total_register_rows": sum(x["populated_site_rows"] for x in summaries.values()),
            "can_import_without_overwriting": True,
            "verified_financial_revenue": False,
        }
    finally:
        src.z.close()


def _loaded_source(con):
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='master_source_loads'"
    ).fetchone():
        return None
    row = con.execute(
        "SELECT sha256,source_rows_active,source_rows_expired,recorded_at "
        "FROM master_source_loads ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


@router.get("/master-source-audit")
def current_master_source_audit():
    actor()
    if not Path(TEMPLATE).is_file():
        raise HTTPException(503, "Approved private Maintenance Master is not configured.")
    try:
        source = source_audit(TEMPLATE)
        with closing(connect()) as con:
            db_rows = {
                r["status"]: r["n"]
                for r in con.execute(
                    "SELECT status,COUNT(*) AS n FROM contracts GROUP BY status"
                )
            }
            loaded = _loaded_source(con)
        source["database_rows"] = {
            "active": db_rows.get("Active", 0),
            "expired": db_rows.get("Expired", 0),
        }
        source["last_recorded_source_load"] = loaded
        source["source_file_matches_last_load"] = bool(
            loaded and loaded["sha256"] == source["workbook_sha256"]
        )
        source["record_counts_match"] = (
            db_rows.get("Active", 0) == source["registers"]["Maintenance Database"]["populated_site_rows"]
            and db_rows.get("Expired", 0) == source["registers"]["Expired"]["populated_site_rows"]
        )
        source["fully_reconciled"] = False  # Counts/hash cannot certify every customer or amount.
        return source
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
