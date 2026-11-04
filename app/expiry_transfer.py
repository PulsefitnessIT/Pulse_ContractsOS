"""Coordinator-reviewed, audited bulk transfer of expired contracts.

This is the equivalent of cut/paste from Maintenance Database or MOD into
Expired, but without positional column errors or silent removal. Only
past/current expiry dates are eligible, only explicit selected revisions
are moved, and all source fields/equipment links remain intact. Export uses
the approved Master template; this routine does not edit Excel itself.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import closing

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import pilot_access
from .backups import create_local_backup
from .register_layout import current_layout
from .store import connect, now, TEMPLATE

router = APIRouter(prefix="/api/contracts/expiry-transfer",
                   tags=["Coordinator expired-contract transfer"])
SHEETS = ("Maintenance Database", "MOD")
MAX_BATCH = 40
REASON_MIN = 12
REASON_MAX = 500
EXCEL_MAX = 1_048_575


def _coordinator():
    if (not pilot_access.PILOT_MODE or
            pilot_access.current_role() not in ("Admin", "Coordinator")):
        raise HTTPException(
            403, "A named Coordinator or Administrator is required to transfer contracts."
        )
    person = str(pilot_access.actor("") or "").strip()
    if len(person) < 2 or person in ("Viewer", "Coordinator"):
        raise HTTPException(403, "A named staff account is required.")
    return person


def _expiry(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


class TransferItem(BaseModel):
    contract_id: int = Field(gt=0)
    expected_revision: int = Field(ge=1)
    row_key: str = Field(min_length=1, max_length=200)
    source_sheet: str
    source_row: int = Field(ge=2, le=EXCEL_MAX)
    expiry_date: str


class TransferBatch(BaseModel):
    items: list[TransferItem] = Field(min_length=1, max_length=MAX_BATCH)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)
    confirm_verified_expiry_and_no_renewal: bool


def _valid_candidate(row, today):
    if row["status"] != "Active" or row["source_sheet"] not in SHEETS:
        return None
    fields = json.loads(row["fields"])
    if not isinstance(fields, dict):
        return None
    expiry = _expiry(fields.get("Expiry date"))
    if not expiry or expiry > today or not str(fields.get("Customer / site") or "").strip():
        return None
    if not str(fields.get("Record ID") or "").strip() or not str(row["row_key"] or "").strip():
        return None
    if str(fields["Record ID"]).strip() != str(row["row_key"]).strip():
        return None
    return fields, expiry


def _view(row, fields, expiry, today):
    return {
        "contract_id": row["id"],
        "expected_revision": row["revision"],
        "row_key": row["row_key"],
        "source_sheet": row["source_sheet"],
        "source_row": row["source_row"],
        "customer_site": str(fields.get("Customer / site") or "")[:300],
        "contract_number": str(fields.get("Contract number") or "")[:150],
        "contract_type": str(fields.get("Contract / warranty type") or "")[:200],
        "sales_manager": str(fields.get("Sales manager") or "")[:200],
        "expiry_date": expiry.isoformat(),
        "days_expired": (today-expiry).days,
        "requires_human_confirmation": True,
    }


@router.get("/preview")
def expiry_transfer_preview(
    source_sheet: str = Query("Maintenance Database"),
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
):
    """Pure/read-only candidate discovery; dates never trigger auto-archiving."""
    _coordinator()
    if source_sheet not in SHEETS:
        raise HTTPException(422, "Choose Maintenance Database or MOD.")
    layout = current_layout(TEMPLATE)
    if source_sheet not in layout["source_registers"]:
        raise HTTPException(409, "The source register is missing from the approved Master.")
    today=dt.date.today()
    with closing(connect()) as db:
        rows=db.execute(
            "SELECT id,row_key,revision,status,source_sheet,source_row,fields "
            "FROM contracts WHERE status='Active' AND source_sheet=?",
            (source_sheet,),
        ).fetchall()
    candidates=[]
    missing_date=0
    future=0
    mismatched_identity=0
    for record in rows:
        fields=json.loads(record["fields"])
        expiry=_expiry(fields.get("Expiry date")) if isinstance(fields,dict) else None
        if expiry is None:
            missing_date+=1
            continue
        if expiry > today:
            future+=1
            continue
        safe=_valid_candidate(record,today)
        if safe is None:
            mismatched_identity+=1
            continue
        fields,expiry=safe
        candidates.append(_view(record,fields,expiry,today))
    # Most recently expired first, then site; do not imply that old expiry is
    # confirmation of cancellation or an ended agreement.
    candidates.sort(key=lambda item: (
        item["days_expired"],item["customer_site"].casefold(),item["contract_id"]
    ))
    return {
        "source_sheet":source_sheet,
        "today":today.isoformat(),
        "total_candidates":len(candidates),
        "offset":offset,
        "limit":limit,
        "items":candidates[offset:offset+limit],
        "missing_or_invalid_expiry":missing_date,
        "not_yet_expired":future,
        "identity_exceptions":mismatched_identity,
        "columns": {
            "shared":layout["shared_column_count"],
            "historical_only":layout["expired_only_column_count"],
            "historical_extra_fields_preserved":True,
            "cut_paste_range":layout["safe_copy_paste_range"],
        },
        "no_automatic_transfers":True,
        "source_workbook_unchanged":True,
    }


@router.post("/apply")
def transfer_expired_contracts(payload: TransferBatch):
    """One atomic action with verified backup, explicit individual approvals."""
    who=_coordinator()
    if not payload.confirm_verified_expiry_and_no_renewal:
        raise HTTPException(
            422,"Confirm against the actual agreements that each selected contract has expired and not renewed."
        )
    reason=payload.reason.strip()
    if not REASON_MIN<=len(reason)<=REASON_MAX:
        raise HTTPException(422,"Provide a meaningful reason for the expiry transfer.")
    if len({x.contract_id for x in payload.items})!=len(payload.items):
        raise HTTPException(422,"Each contract may be selected only once.")

    layout=current_layout(TEMPLATE)
    today=dt.date.today()
    for item in payload.items:
        if item.source_sheet not in SHEETS or item.source_sheet not in layout["source_registers"]:
            raise HTTPException(422,"One selected contract is not from a current active register.")
        if _expiry(item.expiry_date) is None:
            raise HTTPException(422,"An invalid expiry date was submitted.")

    # Validate every candidate before a backup, then recheck inside an
    # immediate write transaction to stop two coordinators racing.
    with closing(connect()) as db:
        for selection in payload.items:
            row=db.execute(
                "SELECT id,row_key,revision,status,source_sheet,source_row,fields "
                "FROM contracts WHERE id=?", (selection.contract_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(409,"A selected contract no longer exists.")
            _validate_selection(row,selection,today)
    try:
        safety=create_local_backup(force=True)
        if not safety.get("created") or safety.get("integrity")!="ok":
            raise RuntimeError("No verified backup")
    except Exception as exc:
        raise HTTPException(503,
            "A verified recovery backup could not be created. No contracts were transferred."
        ) from exc

    with closing(connect()) as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            records=[]
            for selection in payload.items:
                row=db.execute(
                    "SELECT id,row_key,revision,status,source_sheet,source_row,fields "
                    "FROM contracts WHERE id=?", (selection.contract_id,),
                ).fetchone()
                if row is None:
                    raise HTTPException(409,"A selected contract disappeared before transfer.")
                fields,expiry=_validate_selection(row,selection,today)
                records.append((row,fields,expiry))
            maximum=db.execute(
                "SELECT COALESCE(MAX(source_row),1) FROM contracts "
                "WHERE source_sheet='Expired'"
            ).fetchone()[0]
            next_row=max(int(maximum),int(layout["template_last_expired_row"]))+1
            if next_row+len(records)-1>EXCEL_MAX:
                raise HTTPException(409,"Expired worksheet has insufficient free Excel rows.")
            result=[]
            for row,old,expiry in records:
                converted=dict(old)
                converted["Renewal status"]="Historical / archived"
                original_sheet=row["source_sheet"]
                original_row=row["source_row"]
                destination=next_row
                next_row+=1
                cursor=db.execute(
                    "UPDATE contracts SET status='Expired',source_sheet='Expired',"
                    "source_row=?,old_sheet=?,old_row=?,fields=?,"
                    "revision=revision+1,dirty=1,updated_at=? "
                    "WHERE id=? AND revision=? AND status='Active'",
                    (destination,original_sheet,original_row,
                     json.dumps(converted,ensure_ascii=False),now(),
                     row["id"],row["revision"]),
                )
                if cursor.rowcount!=1:
                    raise HTTPException(409,"Contract revision changed while archiving.")
                evidence={
                    "reason":reason,"verified_expiry":expiry.isoformat(),
                    "from_sheet":original_sheet,"from_row":original_row,
                    "to_sheet":"Expired","to_row":destination,
                    "record":converted,"transfer_mode":"Coordinator verified batch",
                }
                db.execute(
                    "INSERT INTO changes(contract_id,actor,action,before_data,"
                    "after_data,at) VALUES(?,?,?,?,?,?)",
                    (row["id"],who,"Transferred verified expired contract",
                     json.dumps(old,ensure_ascii=False),
                     json.dumps(evidence,ensure_ascii=False),now()),
                )
                result.append({
                    "contract_id":row["id"],"record_id":row["row_key"],
                    "from_sheet":original_sheet,"from_row":original_row,
                    "to_sheet":"Expired","to_row":destination,
                    "new_revision":row["revision"]+1,
                })
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "transferred":len(result),
        "items":result,
        "archived_records_not_deleted":True,
        "equipment_and_invoices_remain_linked":True,
        "original_workbook_not_modified":True,
        "visible_in_next_master_export":True,
        "verified_backup_created":True,
        "audit_actor":who,
        "shared_expired_columns":layout["shared_column_count"],
        "expired_extra_columns_preserved":layout["expired_only_column_count"],
    }


def _validate_selection(row,selected,today):
    if row["status"]!="Active" or row["source_sheet"] not in SHEETS:
        raise HTTPException(409,"The selected agreement is no longer in an active register.")
    if (row["id"]!=selected.contract_id or row["revision"]!=selected.expected_revision
            or row["row_key"]!=selected.row_key
            or row["source_sheet"]!=selected.source_sheet
            or row["source_row"]!=selected.source_row):
        raise HTTPException(409,"A selected contract changed since preview. Refresh the list.")
    valid=_valid_candidate(row,today)
    if valid is None:
        raise HTTPException(409,"The contract expiry or stable Record ID needs review.")
    fields,expiry=valid
    if expiry.isoformat()!=selected.expiry_date:
        raise HTTPException(409,"The contract expiry date changed since preview.")
    return fields,expiry
