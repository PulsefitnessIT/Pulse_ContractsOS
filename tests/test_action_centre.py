"""Purely fictional Action Centre scenarios: dates, status and history."""
import datetime as dt
import json
import sqlite3

import pytest
from fastapi import HTTPException

from app import action_centre


def db_fixture(tmp_path, monkeypatch):
    path = tmp_path / "actions_example.sqlite3"
    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    with connect() as db:
        db.execute("""CREATE TABLE contracts (
            id INTEGER PRIMARY KEY, status TEXT, source_sheet TEXT, fields TEXT
        )""")
        fake = [
            (1, "Active", "Maintenance Database", {
                "Customer / site": "Fictional Gym North",
                "Contract number": "TEST-CON-1", "Sales manager": "Fictional Manager",
                "Contract / warranty type": "P&L Ext Warr",
                "Next action": "Contact customer about quote",
                "Next action date": "2026-10-01",
                "Expiry date": "2026-11-15",
            }),
            (2, "Active", "MOD", {
                "Customer / site": "Fictional Defence Facility",
                "Next action": "Request information", "Next action date": "",
                "Expiry date": "2030-01-01",
            }),
            (3, "Expired", "Expired", {
                "Customer / site": "Fictional Archived Site",
                "Next action": "Contact customer",
                "Expiry date": "2020-01-01",
            }),
        ]
        db.executemany("INSERT INTO contracts VALUES(?,?,?,?)",
            [(i,s,sh,json.dumps(fields)) for i,s,sh,fields in fake])
        db.commit()
    monkeypatch.setattr(action_centre, "connect", connect)
    return connect


def test_action_centre_derives_mod_and_current_records_only(tmp_path,monkeypatch):
    db_fixture(tmp_path,monkeypatch)
    result = action_centre.get_actions(today=dt.date(2026,11,3))
    assert result["total"] == 4
    assert result["summary"]["Overdue review"] == 1
    assert result["summary"]["Due within 30 days"] == 1
    assert result["summary"]["Date missing / check"] == 2
    assert all(item["customer_site"] != "Fictional Archived Site" for item in result["items"])
    assert len([t for t in result["items"] if t["sheet"] == "MOD"]) == 2
    assert result["contract_coordinator_column_added"] is False
    assert result["excluded_calculated_excel_action_centre"] is True
    assert result["past_due_does_not_prove_action_is_incomplete"] is True


def test_completion_preserves_original_excel_fields_and_audits_actor(tmp_path,monkeypatch):
    connect = db_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(action_centre, "PILOT_MODE", True)
    monkeypatch.setattr(action_centre, "current_role", lambda: "Coordinator")
    monkeypatch.setattr(action_centre, "actor", lambda: "fictional-staff")
    task = next(t for t in action_centre.get_actions()["items"]
                if t["contract_id"] == 1 and t["kind"] == "follow_up")
    result = action_centre.change_action(task["task_id"],
        action_centre.ActionUpdate(status="Completed",note="Called site; update reviewed"))
    assert result["ok"] is True
    assert result["workbook_data_unchanged"] is True
    current = next(t for t in action_centre.get_actions()["items"]
                   if t["task_id"] == task["task_id"])
    assert current["status"] == "Completed"
    assert current["completed_by"] == "fictional-staff"
    assert current["urgency"] == "Completed / closed"
    with connect() as db:
        original=json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])
        assert original["Next action"] == "Contact customer about quote"
        assert original["Next action date"] == "2026-10-01"
        assert len(action_centre.action_history(1)["events"])==1
    repeat = action_centre.change_action(task["task_id"],
        action_centre.ActionUpdate(status="Completed"))
    assert repeat["unchanged"] is True


def test_changed_workbook_action_requires_new_completion(tmp_path,monkeypatch):
    connect = db_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(action_centre,"PILOT_MODE",True)
    monkeypatch.setattr(action_centre,"current_role",lambda:"Admin")
    monkeypatch.setattr(action_centre,"actor",lambda:"fictional-admin")
    before = next(t for t in action_centre.get_actions()["items"]
                  if t["contract_id"]==1 and t["kind"]=="follow_up")
    action_centre.change_action(before["task_id"],
        action_centre.ActionUpdate(status="Completed",note="Original completed"))
    with connect() as db:
        old=json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])
        old["Next action"]="Chase updated purchase order"
        db.execute("UPDATE contracts SET fields=? WHERE id=1",(json.dumps(old),))
        db.commit()
    newer=next(t for t in action_centre.get_actions()["items"]
               if t["contract_id"]==1 and t["kind"]=="follow_up")
    assert newer["task_id"] != before["task_id"]
    assert newer["status"]=="Open"
    with pytest.raises(HTTPException) as e:
        action_centre.change_action(before["task_id"],
            action_centre.ActionUpdate(status="Completed"))
    assert e.value.status_code==409


def test_viewers_and_local_demo_cannot_change_status(tmp_path,monkeypatch):
    db_fixture(tmp_path,monkeypatch)
    task=next(t for t in action_centre.get_actions()["items"] if t["kind"]=="follow_up")
    monkeypatch.setattr(action_centre,"PILOT_MODE",True)
    monkeypatch.setattr(action_centre,"current_role",lambda:"Viewer")
    with pytest.raises(HTTPException) as exc:
        action_centre.change_action(task["task_id"],
            action_centre.ActionUpdate(status="Completed"))
    assert exc.value.status_code == 403
    monkeypatch.setattr(action_centre,"PILOT_MODE",False)
    monkeypatch.setattr(action_centre,"current_role",lambda:"Admin")
    with pytest.raises(HTTPException):
        action_centre.change_action(task["task_id"],
            action_centre.ActionUpdate(status="Completed"))


def test_invalid_future_snooze_date_fails_closed(tmp_path,monkeypatch):
    db_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(action_centre,"PILOT_MODE",True)
    monkeypatch.setattr(action_centre,"current_role",lambda:"Coordinator")
    task=next(t for t in action_centre.get_actions()["items"] if t["kind"]=="follow_up")
    with pytest.raises(HTTPException) as exc:
        action_centre.change_action(task["task_id"],
            action_centre.ActionUpdate(status="In progress",snooze_until="not-a-date"))
    assert exc.value.status_code==422
