"""Repeatable, admin-reviewed sync of the independently edited Maintenance Master.

The workbook remains authoritative for its source fields during the transition.
Three-way merge protects independent edits in Contracts OS. Unknown, repeated,
reclassified, removed, or blank Record IDs are NEVER silently matched, archived
or created. Source workbook bytes remain PRIVATE; no GitHub data is written.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import Counter
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .excel_io import ExcelSource, REGISTER_SHEETS
from .data_readiness import _amount_kind
from .master_roundtrip import normal, DERIVED
from .pilot_access import PILOT_MODE, actor, current_role
from .backups import create_local_backup
from .store import DB, DATA, TEMPLATE, connect, now
from .register_layout import current_layout

router = APIRouter(prefix="/api/pilot/master-sync", tags=["Recurring working Master synchronisation"])
MAX_UPLOAD = 35_000_000
MAX_ACTIONS = 250
REVIEW_HOURS = 24
EXCLUDED = set(DERIVED) | {"Record ID", "Original source", "Renewal status"}
SHEETS = {"Maintenance Database": "Active", "MOD": "Active", "Expired": "Expired"}


def present_registers(source):
    """Allow legacy 8-tab and current 10-tab Masters. Never parse Action Centre."""
    has_mod = "MOD" in getattr(source, "sheet_parts", {})
    return tuple(s for s in SHEETS if has_mod or s != "MOD")


class ApplyRequest(BaseModel):
    approved_items: list[int] = Field(default_factory=list, max_length=MAX_ACTIONS)


def _admin():
    if not PILOT_MODE or current_role() != "Admin":
        raise HTTPException(403, "Recurring Master uploads require a verified pilot administrator.")
    return actor()


def _tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS working_master_reviews (
      review_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
      filename TEXT NOT NULL, submitted_by TEXT NOT NULL,
      submitted_at TEXT NOT NULL, expires_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Pending', report_json TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS working_master_baselines (
      contract_id INTEGER PRIMARY KEY,
      sheet TEXT NOT NULL, fields_json TEXT NOT NULL,
      source_sha256 TEXT NOT NULL, updated_at TEXT NOT NULL,
      FOREIGN KEY(contract_id) REFERENCES contracts(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS working_master_actions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      review_id TEXT NOT NULL, contract_id INTEGER NOT NULL,
      source_sha256 TEXT NOT NULL, actor TEXT NOT NULL,
      fields_json TEXT NOT NULL, applied_at TEXT NOT NULL,
      FOREIGN KEY(review_id) REFERENCES working_master_reviews(review_id),
      FOREIGN KEY(contract_id) REFERENCES contracts(id)
    )""")


def _records(source):
    result = {}
    ids = Counter()
    for sheet in present_registers(source):
        headers, rows = source.records(sheet)
        if not {"Customer / site", "Record ID", "Contract number", "Contract / warranty type"}.issubset(set(headers)):
            raise ValueError("The uploaded workbook has incompatible register headings.")
        retained = [x for x in rows if normal(x["fields"].get("Customer / site"))]
        result[sheet] = retained
        ids.update(
            normal(row["fields"].get("Record ID"))
            for row in retained if normal(row["fields"].get("Record ID"))
        )
    return result, {key for key, count in ids.items() if count > 1}


def _index(records, duplicates):
    index = {}
    for sheet, rows in records.items():
        for item in rows:
            key = normal(item["fields"].get("Record ID"))
            if key and key not in duplicates:
                index[key] = {**item, "sheet": sheet}
    return index


def _live(db):
    rows = db.execute(
        "SELECT id,row_key,status,source_sheet,source_row,revision,fields "
        "FROM contracts"
    ).fetchall()
    return {row["row_key"]: {
        "id": row["id"], "row_key": row["row_key"],
        "revision": row["revision"], "status": row["status"],
        "sheet": row["source_sheet"], "source_row": row["source_row"],
        "fields": json.loads(row["fields"]),
    } for row in rows}


def _field_changes(old, incoming, current):
    result = []
    # New column names normally require review, not silent schema guessing.
    # Next action date is one explicitly approved, factual field introduced
    # by the revised Master. It may be added if the live value is blank.
    # Missing source columns must NEVER be interpreted as a blank update.
    eligible = (set(old) & set(incoming)) | (
        {"Next action date"} & set(incoming)
    )
    for field in sorted(eligible - EXCLUDED):
        prior = old.get(field, "")
        next_value = incoming.get(field, "")
        existing = current.get(field, "")
        if normal(prior) == normal(next_value):
            continue
        if normal(next_value) == normal(existing):
            # The platform already has the incoming value. No new write.
            continue
        result.append({
            "field": field, "before_source": prior,
            "in_workbook": next_value,
            "in_platform": existing,
            "conflict": (normal(existing) != normal(prior)
                         if field in old else bool(normal(existing))),
        })
    return result


def plan(db, previous, incoming, sha256):
    """Construct a source-derived, non-destructive preview; no writes."""
    old_rows, old_ambiguous = _records(previous)
    new_rows, new_ambiguous = _records(incoming)
    old_index = _index(old_rows, old_ambiguous)
    new_index = _index(new_rows, new_ambiguous)
    current = _live(db)
    baselines = {}
    for row in db.execute("SELECT contract_id,sheet,fields_json FROM working_master_baselines"):
        baselines[row["contract_id"]] = {"sheet": row["sheet"],
                                        "fields": json.loads(row["fields_json"])}
    actions, blocked, totals = [], [], Counter()
    seen_ids = set()
    for sheet, rows in new_rows.items():
        for entry in rows:
            identifier = normal(entry["fields"].get("Record ID"))
            if not identifier or identifier in new_ambiguous or identifier in old_ambiguous:
                blocked.append({
                    "sheet": sheet, "source_row": entry["row"],
                    "reason": "Blank/repeated Record ID: human matching required",
                })
                totals["ambiguous_rows"] += 1
                continue
            if identifier in seen_ids:
                # Defensive block even if a damaged workbook bypassed duplicate indexing.
                blocked.append({"sheet": sheet, "source_row": entry["row"],
                                "reason": "Repeated ID within upload"})
                continue
            seen_ids.add(identifier)
            baseline_entry = old_index.get(identifier)
            live = current.get(identifier)
            if baseline_entry is None or live is None:
                blocked.append({
                    "sheet": sheet, "source_row": entry["row"],
                    "reason": "New/unmatched source record: requires new-record review",
                })
                totals["new_or_unmatched"] += 1
                continue
            if live["sheet"] != sheet or baseline_entry["sheet"] != sheet:
                blocked.append({
                    "sheet": sheet, "source_row": entry["row"],
                    "reason": "Status/worksheet changed: explicit contract lifecycle review required",
                })
                totals["moves_requiring_review"] += 1
                continue
            # A different stored Record ID means the local key was reused.
            if normal(live["fields"].get("Record ID")) != identifier:
                blocked.append({"sheet": sheet, "source_row": entry["row"],
                                "reason": "Source record identity no longer matches"})
                totals["identity_conflicts"] += 1
                continue
            baseline = baselines.get(live["id"], baseline_entry)
            if baseline["sheet"] != sheet:
                blocked.append({"sheet": sheet, "source_row": entry["row"],
                                "reason": "Previous approved source location differs"})
                continue
            old_fields = baseline["fields"]
            changes = _field_changes(old_fields, entry["fields"], live["fields"])
            if not changes:
                totals["unchanged_or_already_current"] += 1
                continue
            # Working Excel may contain incomplete or incorrect dates/amounts.
            # Such evidence stays visible for manual correction, never becomes
            # an unreviewed live financial value or false contract expiry.
            incoming_fields = entry["fields"]
            new_amount = incoming_fields.get("Contract amount (£)")
            if _amount_kind(new_amount) == "invalid":
                blocked.append({
                    "sheet":sheet,"source_row":entry["row"],
                    "contract_id":live["id"],"reason":"Invalid source contract amount; review Excel",
                })
                totals["invalid_financial_or_date_rows"] += 1
                continue
            dates = {}
            try:
                for name in ("Start date", "Expiry date"):
                    value = normal(incoming_fields.get(name))
                    if value:
                        dates[name] = dt.date.fromisoformat(value[:10])
                if dates.get("Start date") and dates.get("Expiry date") and (
                    dates["Expiry date"] < dates["Start date"]
                ):
                    raise ValueError("Expiry before start")
            except ValueError:
                blocked.append({
                    "sheet":sheet,"source_row":entry["row"],
                    "contract_id":live["id"],"reason":"Invalid contract date or expiry before start",
                })
                totals["invalid_financial_or_date_rows"] += 1
                continue
            if any(change["conflict"] for change in changes):
                blocked.append({
                    "sheet": sheet, "source_row": entry["row"], "contract_id": live["id"],
                    "reason": "Workbook and platform changed the same field",
                    "conflicting_fields": [c["field"] for c in changes if c["conflict"]],
                })
                totals["conflicts"] += 1
                continue
            actions.append({
                "contract_id": live["id"], "row_key": identifier,
                "sheet": sheet, "source_row": entry["row"],
                "revision": live["revision"],
                "changes": changes,
                "next_baseline": {**old_fields, **{
                    c["field"]: c["in_workbook"] for c in changes
                }},
            })
            totals["safe_updates"] += 1
    for key, previous_row in old_index.items():
        if key not in new_index:
            totals["missing_or_removed_from_workbook"] += 1
            # No removal/expiration is ever inferred from an absent source row.
    return {
        "source_sha256": sha256,
        "registers": {sheet: len(new_rows.get(sheet, [])) for sheet in SHEETS},
        "action_centre_rows_are_derived_only": True,
        "new_source_date_fields_never_inferred_from_action_text": True,
        "summary": {key: int(totals.get(key, 0)) for key in (
            "safe_updates","unchanged_or_already_current","new_or_unmatched",
            "ambiguous_rows","moves_requiring_review","identity_conflicts",
            "conflicts","missing_or_removed_from_workbook",
            "invalid_financial_or_date_rows",
        )},
        "items": actions,
        "review_required": blocked[:500],
        "review_required_total": len(blocked),
        "full_source_replacement": False,
        "deleted_or_archived_by_upload": 0,
        "ledger_updated_by_upload": False,
    }


def _load_validated(path):
    from .data_readiness import workbook_check
    checked = workbook_check(path)
    if not checked["valid"]:
        raise ValueError("Expected the approved eight-sheet Maintenance Master layout.")
    # The modern Master must be safe for direct A:AE cut/paste. Reject a
    # reordered Expired layout before comparing or applying any imported edits.
    if "MOD" in checked.get("sheet_names", []):
        current_layout(path)
    src = ExcelSource(path)
    return src


def _baseline_verified(db):
    try:
        row = db.execute(
            "SELECT sha256 FROM master_source_loads ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(
            409, "A verified prior Master baseline is not recorded in this database. "
                 "IT must establish one without overwriting existing staff edits."
        ) from exc
    if row is None:
        raise HTTPException(
            409, "The previous workbook has no recorded source fingerprint. "
                 "IT must establish the baseline before recurring updates."
        )
    if not Path(TEMPLATE).is_file():
        raise HTTPException(503, "The original private approved Master is unavailable.")
    sha = hashlib.sha256(Path(TEMPLATE).read_bytes()).hexdigest()
    if sha != row["sha256"]:
        raise HTTPException(
            409, "The stored Master no longer matches its audited import fingerprint. "
                 "Do not apply updates until IT reconciles that change."
        )
    return sha


def _pending_path(sha):
    return Path(DATA) / "working_master_uploads" / (sha + ".xlsx")


@router.post("/preview")
async def preview_upload(file: UploadFile = File(...)):
    username = _admin()
    filename = Path(str(file.filename or "")).name[:120]
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Upload an original .xlsx Maintenance Master.")
    raw = await file.read(MAX_UPLOAD + 1)
    if not raw or len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "The Maintenance Master must be under 35 MB.")
    if not raw.startswith(b"PK"):
        raise HTTPException(422, "This file is not an Excel workbook.")
    sha = hashlib.sha256(raw).hexdigest()
    pending = _pending_path(sha)
    directory = pending.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not pending.is_file():
        temp = directory / ("." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("xb") as out:
                out.write(raw)
            os.chmod(temp, 0o600)
            os.replace(temp, pending)
        finally:
            temp.unlink(missing_ok=True)
    with closing(connect()) as db:
        _tables(db)
        _baseline_verified(db)
        try:
            incoming = _load_validated(pending)
            previous = _load_validated(TEMPLATE)
            try:
                data = plan(db, previous, incoming, sha)
            finally:
                previous.z.close()
                incoming.z.close()
        except (ValueError, KeyError, IndexError, OSError, json.JSONDecodeError) as exc:
            raise HTTPException(422, "Workbook content is incompatible: " + str(exc)[:250]) from exc
        review_id = uuid.uuid4().hex
        expiry = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=REVIEW_HOURS)).isoformat()
        db.execute(
            "INSERT INTO working_master_reviews"
            "(review_id,sha256,filename,submitted_by,submitted_at,expires_at,status,report_json)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (review_id,sha,filename,username,now(),expiry,"Pending",
             json.dumps(data,ensure_ascii=False)),
        )
        db.commit()
    return {
        "review_id": review_id, "expires_at": expiry,
        "sha256": sha, "filename": filename,
        "summary": data["summary"], "registers": data["registers"],
        "items": [{k:v for k,v in item.items() if k!="next_baseline"} for item in data["items"]],
        "review_required": data["review_required"],
        "review_required_total": data["review_required_total"],
        "fully_applied": False, "no_automatic_deletion": True,
    }


@router.post("/{review_id}/apply")
def apply_review(review_id: str, body: ApplyRequest):
    username = _admin()
    if not re.fullmatch("[0-9a-f]{32}", review_id):
        raise HTTPException(422, "Invalid review reference.")
    if not body.approved_items:
        raise HTTPException(422, "Choose at least one safe change to apply.")
    if len(set(body.approved_items)) != len(body.approved_items):
        raise HTTPException(422, "Duplicate selections are not permitted.")
    with closing(connect()) as db:
        _tables(db)
        # Backup before starting the write transaction. The application must
        # not proceed if a consistent local recovery checkpoint fails.
        before = db.execute(
            "SELECT status,expires_at FROM working_master_reviews WHERE review_id=?",
            (review_id,)
        ).fetchone()
        if before is None:
            raise HTTPException(404, "Workbook review not found.")
        if before["status"] != "Pending":
            raise HTTPException(409, "This review was already processed.")
        if dt.datetime.fromisoformat(before["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            raise HTTPException(409, "This review expired. Upload the latest workbook again.")
        try:
            recovery = create_local_backup(force=True)
            if not recovery.get("created") or recovery.get("integrity") != "ok":
                raise RuntimeError("Local recovery checkpoint was not verified.")
        except Exception as exc:
            raise HTTPException(503, "No verified local backup; workbook changes were not applied.") from exc
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM working_master_reviews WHERE review_id=?",(review_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Workbook review not found.")
        if row["status"] != "Pending":
            raise HTTPException(409, "This review was already processed.")
        if dt.datetime.fromisoformat(row["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            raise HTTPException(409, "This review expired. Upload the latest workbook again.")
        source = _pending_path(row["sha256"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
            raise HTTPException(409, "Uploaded source file changed. Reupload before approval.")
        _baseline_verified(db)
        report = json.loads(row["report_json"])
        items = report["items"]
        indices = sorted(body.approved_items)
        if any(type(i) is not int or i < 0 or i >= len(items) for i in indices):
            raise HTTPException(422, "Only safe listed changes can be selected.")
        updated = []
        for i in indices:
            entry = items[i]
            if any(c["conflict"] for c in entry["changes"]):
                raise HTTPException(409, "A selected change has an unresolved field conflict.")
            live = db.execute(
                "SELECT * FROM contracts WHERE id=?",(entry["contract_id"],)
            ).fetchone()
            if (live is None or live["revision"] != entry["revision"] or
                live["row_key"] != entry["row_key"] or live["source_sheet"] != entry["sheet"]):
                raise HTTPException(409, "A selected record changed since preview. Upload again.")
            existing = json.loads(live["fields"])
            changes = {}
            for cell in entry["changes"]:
                field = cell["field"]
                if field in EXCLUDED or normal(existing.get(field)) != normal(cell["in_platform"]):
                    raise HTTPException(409, "Workbook field no longer matches its preview.")
                changes[field] = cell["in_workbook"]
            result = {**existing, **changes}
            if not normal(result.get("Customer / site")):
                raise HTTPException(422, "Site name cannot be cleared by source upload.")
            db.execute(
                "UPDATE contracts SET fields=?,revision=revision+1,dirty=1,updated_at=? "
                "WHERE id=? AND revision=?",
                (json.dumps(result,ensure_ascii=False),now(),live["id"],entry["revision"])
            )
            new_baseline = entry["next_baseline"]
            db.execute(
                "INSERT INTO working_master_baselines(contract_id,sheet,fields_json,source_sha256,updated_at)"
                " VALUES(?,?,?,?,?) ON CONFLICT(contract_id) DO UPDATE SET "
                "sheet=excluded.sheet,fields_json=excluded.fields_json,"
                "source_sha256=excluded.source_sha256,updated_at=excluded.updated_at",
                (live["id"],entry["sheet"],json.dumps(new_baseline,ensure_ascii=False),
                 row["sha256"],now())
            )
            db.execute(
                "INSERT INTO changes(contract_id,actor,action,before_data,after_data,at)"
                " VALUES(?,?,?,?,?,?)",
                (live["id"],username,"Reviewed working Master update",
                 json.dumps(existing,ensure_ascii=False),
                 json.dumps({"source_sha256":row["sha256"],"changed_fields":changes},
                            ensure_ascii=False),now())
            )
            db.execute(
                "INSERT INTO working_master_actions"
                "(review_id,contract_id,source_sha256,actor,fields_json,applied_at)"
                " VALUES(?,?,?,?,?,?)",
                (review_id,live["id"],row["sha256"],username,
                 json.dumps(changes,ensure_ascii=False),now())
            )
            updated.append(live["id"])
        db.execute(
            "UPDATE working_master_reviews SET status='Applied' WHERE review_id=?",
            (review_id,)
        )
        db.commit()
    return {
        "ok":True,"recovery_backup_created":True,
        "local_backup_is_not_offsite_disaster_recovery":True,
        "approved_records_updated":len(updated),
        "unapplied_safe_updates":len(items)-len(updated),
        "requires_new_upload_to_continue":len(items)>len(updated),
        "source_sha256":row["sha256"],
        "non_matched_and_conflicting_rows_still_require_manual_review":True,
        "automatically_deleted":0,"automatically_archived":0,
        "approved_by":username,
    }
