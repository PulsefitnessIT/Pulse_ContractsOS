"""Live coordinator Action Centre, derived from source-backed contract records.

Never imports the calculated Excel Action Centre as customers or asserts a
past-due reminder is unfinished. Completed work is a user action with an
auditable actor; records in Excel remain unaltered until normal reviewed sync.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter
from contextlib import closing

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .pilot_access import PILOT_MODE, actor, current_role
from .store import connect, now

router = APIRouter(prefix="/api/action-centre", tags=["Live contract actions"])
ALLOWED = {"Open", "In progress", "Awaiting Customer", "Awaiting PO",
           "Blocked", "Completed", "Not Applicable"}
KINDS = ("follow_up", "renewal_review", "missing_expiry")
SOURCE_SHEETS = ("Maintenance Database", "MOD")
TASK_PATTERN = re.compile(r"^(\d+):(follow_up|renewal_review|missing_expiry):([0-9a-f]{24})$")


class ActionUpdate(BaseModel):
    status: str
    note: str = Field(default="", max_length=1500)
    snooze_until: str | None = None


def _tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS action_tracking(
        contract_id INTEGER NOT NULL, kind TEXT NOT NULL,
        fingerprint TEXT NOT NULL, status TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '', snooze_until TEXT NOT NULL DEFAULT '',
        completed_by TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(contract_id,kind,fingerprint),
        FOREIGN KEY(contract_id) REFERENCES contracts(id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS action_tracking_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL, kind TEXT NOT NULL,
        fingerprint TEXT NOT NULL, old_status TEXT, new_status TEXT NOT NULL,
        note TEXT NOT NULL, snooze_until TEXT NOT NULL,
        actor TEXT NOT NULL, at TEXT NOT NULL
    )""")


def _date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


def _kind_record(cid, kind, label, date, fields, sheet, today):
    sig = hashlib.sha256(json.dumps([
        kind, label, date.isoformat() if date else "",
        fields.get("Expiry date") if kind == "renewal_review" else "",
    ], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return {
        "task_id": f"{cid}:{kind}:{sig}",
        "contract_id": cid,
        "kind": kind,
        "fingerprint": sig,
        "customer_site": str(fields.get("Customer / site") or "")[:300],
        "sales_manager": str(fields.get("Sales manager") or "")[:200],
        "recorded_cover": str(fields.get("Contract / warranty type") or "")[:200],
        "contract_reference": str(fields.get("Contract number") or "")[:100],
        "sheet": sheet,
        "description": label,
        "recorded_due_date": date.isoformat() if date else None,
        "date_is_source_backed": bool(date),
        "days_until_due": (date - today).days if date else None,
        "source_status": "Recorded in Contracts OS; not Sage or signed-agreement verified",
    }


def _derive(db, today):
    records = db.execute(
        "SELECT id,status,source_sheet,fields FROM contracts WHERE status='Active'"
    )
    tasks = []
    for r in records:
        if r["source_sheet"] not in SOURCE_SHEETS:
            # Earlier pilot migrations may store active contracts under
            # another label. Do not silently assign them to MOD or non-MOD.
            continue
        try:
            fields = json.loads(r["fields"])
            if not isinstance(fields,dict):
                continue
        except (TypeError,ValueError):
            continue
        if not str(fields.get("Customer / site") or "").strip():
            continue
        action = str(fields.get("Next action") or "").strip()
        action_date = _date(fields.get("Next action date"))
        if action or str(fields.get("Next action date") or "").strip():
            description = action if action else "Follow-up date recorded; action description missing"
            tasks.append(_kind_record(
                r["id"],"follow_up",description,action_date,fields,r["source_sheet"],today
            ))
        expiry = _date(fields.get("Expiry date"))
        if expiry is None:
            tasks.append(_kind_record(
                r["id"],"missing_expiry","Review missing or invalid expiry date",
                None,fields,r["source_sheet"],today
            ))
        elif (expiry - today).days <= 90:
            tasks.append(_kind_record(
                r["id"],"renewal_review","Review agreement expiry / renewal status",
                expiry,fields,r["source_sheet"],today
            ))
    return tasks


def _enrich(db, tasks, today):
    stored = {
        (r["contract_id"], r["kind"], r["fingerprint"]): r
        for r in db.execute("SELECT * FROM action_tracking")
    }
    for t in tasks:
        found = stored.get((t["contract_id"],t["kind"],t["fingerprint"]))
        t["status"] = found["status"] if found else "Open"
        t["last_updated_by"] = found["updated_by"] if found else None
        t["last_updated_at"] = found["updated_at"] if found else None
        t["completed_by"] = found["completed_by"] if found else None
        t["note"] = found["note"] if found else ""
        t["snooze_until"] = found["snooze_until"] or None if found else None
        snooze = _date(t["snooze_until"])
        source = _date(t["recorded_due_date"])
        target = snooze or source
        if t["status"] in ("Completed","Not Applicable"):
            urgency = "Completed / closed"
        elif snooze and snooze > today:
            urgency = "Snoozed"
        elif target is None:
            urgency = "Date missing / check"
        elif target < today:
            urgency = "Overdue review"
        elif target == today:
            urgency = "Due today"
        elif (target - today).days <= 7:
            urgency = "Due within 7 days"
        elif (target - today).days <= 30:
            urgency = "Due within 30 days"
        else:
            urgency = "Upcoming within 90 days / scheduled"
        t["urgency"] = urgency
        t["effective_due_date"] = target.isoformat() if target else None
    return tasks


def get_actions(*,kind=None,sheet=None,status=None,search="",limit=100,offset=0,today=None):
    today = today or dt.date.today()
    with closing(connect()) as db:
        _tables(db)
        tasks = _enrich(db, _derive(db,today),today)
    summary = Counter(t["urgency"] for t in tasks)
    kinds = Counter(t["kind"] for t in tasks)
    if kind:
        tasks = [t for t in tasks if t["kind"] == kind]
    if sheet:
        tasks = [t for t in tasks if t["sheet"] == sheet]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    phrase = search.strip().casefold()
    if phrase:
        tasks = [t for t in tasks if phrase in (
            t["customer_site"] + " " + t["contract_reference"] + " " +
            t["description"] + " " + t["sales_manager"]
        ).casefold()]
    priorities={
        "Overdue review":0,"Due today":1,"Due within 7 days":2,
        "Date missing / check":3,"Due within 30 days":4,
        "Upcoming within 90 days / scheduled":5,
        "Snoozed":6,"Completed / closed":7,
    }
    tasks.sort(key=lambda t:(priorities.get(t["urgency"],9),
        t["effective_due_date"] or "9999-12-31",
        t["customer_site"].casefold(), t["task_id"]))
    total = len(tasks)
    return {
        "summary":dict(summary),
        "kinds":dict(kinds),
        "total":total, "limit":limit, "offset":offset,
        "items":tasks[offset:offset+limit],
        "source_is_current_contract_database_not_necessarily_latest_excel_upload":True,
        "past_due_does_not_prove_action_is_incomplete":True,
        "contract_coordinator_column_added":False,
        "excluded_calculated_excel_action_centre":True,
    }


@router.get("")
def list_actions(kind: str = Query("",max_length=40),
                 sheet: str = Query("",max_length=60),
                 status: str = Query("",max_length=40),
                 search: str = Query("",max_length=150),
                 limit: int = Query(100,ge=1,le=250),
                 offset: int = Query(0,ge=0)):
    if kind and kind not in KINDS:raise HTTPException(422,"Unknown action category")
    if sheet and sheet not in SOURCE_SHEETS:raise HTTPException(422,"Unknown source worksheet")
    if status and status not in ALLOWED:raise HTTPException(422,"Unknown action status")
    return get_actions(kind=kind or None,sheet=sheet or None,
                       status=status or None,search=search,limit=limit,offset=offset)


@router.post("/{task_id}/status")
def change_action(task_id: str, body: ActionUpdate):
    if not PILOT_MODE or current_role() not in ("Admin","Coordinator"):
        raise HTTPException(403,"Only signed-in pilot staff can record action outcomes.")
    if body.status not in ALLOWED:
        raise HTTPException(422,"Invalid action status.")
    if body.snooze_until:
        snooze=_date(body.snooze_until)
        if not snooze or snooze.isoformat() != body.snooze_until:
            raise HTTPException(422,"Snooze date must be a valid YYYY-MM-DD date.")
        if snooze < dt.date.today():
            raise HTTPException(422,"Snooze date cannot be in the past.")
    else:
        snooze=None
    match=TASK_PATTERN.fullmatch(task_id)
    if not match:raise HTTPException(422,"Invalid action reference.")
    cid=int(match.group(1))
    kind=match.group(2)
    fingerprint=match.group(3)
    person=actor()
    with closing(connect()) as db:
        _tables(db)
        db.execute("BEGIN IMMEDIATE")
        row=db.execute(
            "SELECT source_sheet,status,fields FROM contracts WHERE id=?",(cid,)
        ).fetchone()
        if row is None or row["status"] != "Active" or row["source_sheet"] not in SOURCE_SHEETS:
            raise HTTPException(404,"The contract is no longer in a current register.")
        # Derive just the current live task identity from current stored fields.
        tasks=[t for t in _derive(db,dt.date.today()) if t["contract_id"]==cid and
               t["kind"]==kind and t["fingerprint"]==fingerprint]
        if not tasks:
            raise HTTPException(409,"The source action changed; refresh the Action Centre.")
        existing=db.execute(
            "SELECT status FROM action_tracking WHERE contract_id=? AND kind=? AND fingerprint=?",
            (cid,kind,fingerprint)
        ).fetchone()
        if existing and existing["status"]==body.status and not body.note and not snooze:
            return {"ok":True,"unchanged":True,"task_id":task_id}
        db.execute("""INSERT INTO action_tracking(
            contract_id,kind,fingerprint,status,note,snooze_until,
            completed_by,updated_by,updated_at
          ) VALUES(?,?,?,?,?,?,?,?,?)
          ON CONFLICT(contract_id,kind,fingerprint) DO UPDATE SET
            status=excluded.status,note=excluded.note,
            snooze_until=excluded.snooze_until,
            completed_by=excluded.completed_by,
            updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
            (cid,kind,fingerprint,body.status,body.note,
             snooze.isoformat() if snooze else "",
             person if body.status=="Completed" else "",person,now())
        )
        db.execute("""INSERT INTO action_tracking_history(
            contract_id,kind,fingerprint,old_status,new_status,
            note,snooze_until,actor,at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (cid,kind,fingerprint,existing["status"] if existing else "Open",
             body.status,body.note,snooze.isoformat() if snooze else "",person,now())
        )
        db.commit()
    return {"ok":True,"task_id":task_id,"status":body.status,
            "recorded_by":person,"workbook_data_unchanged":True}


@router.get("/history/{contract_id}")
def action_history(contract_id: int):
    with closing(connect()) as db:
        _tables(db)
        entries=db.execute(
            "SELECT kind,fingerprint,old_status,new_status,note,snooze_until,actor,at "
            "FROM action_tracking_history WHERE contract_id=? ORDER BY id DESC LIMIT 100",
            (contract_id,)
        ).fetchall()
    return {"contract_id":contract_id,"events":[dict(row) for row in entries]}
