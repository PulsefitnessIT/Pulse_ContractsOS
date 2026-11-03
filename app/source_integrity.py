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
from .excel_io import ExcelSource, register_sheets
from .store import DB, TEMPLATE, connect
from .pilot_access import actor

router = APIRouter(prefix="/api/pilot", tags=["Factual source provenance"])
REQUIRED_COLUMNS = {
    "Maintenance Database": {"Customer / site", "Record ID", "Contract number",
        "Contract / warranty type", "Start date", "Expiry date",
        "Contract amount (£)", "Invoice Code"},
    "MOD": {"Customer / site", "Record ID", "Contract number",
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
    if not structure["valid"]:
        raise ValueError("The workbook must match a verified supported Maintenance Master layout.")
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
        for sheet in register_sheets(src):
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
            "worksheet_names": list(structure["sheet_names"]),
            "workbook_profile": structure.get("profile"),
            "computed_action_centre_is_not_a_contract_register": True,
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
            database_mod_rows = con.execute(
                "SELECT COUNT(*) AS n FROM contracts "
                "WHERE status='Active' AND source_sheet='MOD'"
            ).fetchone()["n"]
            loaded = _loaded_source(con)
            tables = {
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            recent_review = None
            applied = {"approved_field_update_actions": 0, "last_applied_at": None,
                       "latest_approved_source_sha256": None}
            if "working_master_reviews" in tables:
                last = con.execute(
                    "SELECT sha256,submitted_at,status FROM working_master_reviews "
                    "ORDER BY submitted_at DESC, rowid DESC LIMIT 1"
                ).fetchone()
                if last:
                    recent_review = dict(last)
            if "working_master_actions" in tables:
                count = con.execute(
                    "SELECT COUNT(*) AS n,MAX(applied_at) AS latest "
                    "FROM working_master_actions"
                ).fetchone()
                applied["approved_field_update_actions"] = count["n"]
                applied["last_applied_at"] = count["latest"]
                latest = con.execute(
                    "SELECT source_sha256 FROM working_master_actions "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
                applied["latest_approved_source_sha256"] = (
                    latest["source_sha256"] if latest else None
                )
        source["last_working_master_upload"] = recent_review
        source["reviewed_working_master_updates"] = applied
        source["record_source_warning"] = (
            "Original bootstrap workbook and any approved recurring field "
            "updates are separate sources; neither establishes ERP or signed-contract reconciliation."
        )
        source["database_mod_rows"] = database_mod_rows
        source["database_rows"] = {
            "active": db_rows.get("Active", 0),
            "expired": db_rows.get("Expired", 0),
        }
        source["last_recorded_source_load"] = loaded
        source["source_file_matches_last_load"] = bool(
            loaded and loaded["sha256"] == source["workbook_sha256"]
        )
        source["record_counts_match"] = (
            db_rows.get("Active", 0) == sum(
                source["registers"][name]["populated_site_rows"]
                for name in ("Maintenance Database", "MOD")
                if name in source["registers"]
            )
            and db_rows.get("Expired", 0) ==
                source["registers"]["Expired"]["populated_site_rows"]
        )
        source["fully_reconciled"] = False  # Counts/hash cannot certify every customer or amount.
        return source
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
