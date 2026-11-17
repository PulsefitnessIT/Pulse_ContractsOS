"""Synthetic, non-customer regressions for repeated working-Master uploads."""
import hashlib
import json
import sqlite3
import datetime as dt

import pytest
from fastapi import HTTPException

from app import master_sync


def row(num, code, amount, site="Fictional Gym", cover="Contract", sheet="Maintenance Database"):
    return {"row": num, "fill":"", "fields":{
        "Customer / site":site, "Record ID":code,
        "Contract number":"FICT-001", "Contract / warranty type":cover,
        "Contract amount (£)":amount, "Invoice Code":"",
        "Start date":"2026-01-01", "Expiry date":"2026-12-31"
    }}


class FakeSource:
    def __init__(self, active, expired=None):
        self.rows={"Maintenance Database":active, "Expired":expired or []}
    def records(self,sheet):
        return ["Customer / site","Record ID","Contract number","Contract / warranty type"], self.rows[sheet]


def database(tmp_path):
    path=tmp_path/"contracts.sqlite3"
    def connect():
        conn=sqlite3.connect(path)
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    with connect() as db:
        db.execute("""CREATE TABLE contracts(
            id INTEGER PRIMARY KEY, row_key TEXT UNIQUE,
            status TEXT, source_sheet TEXT, source_row INTEGER,
            fields TEXT, revision INTEGER DEFAULT 1, dirty INTEGER DEFAULT 0,
            updated_at TEXT
        )""")
        db.execute("""CREATE TABLE changes(
            id INTEGER PRIMARY KEY,contract_id INTEGER,actor TEXT,action TEXT,
            before_data TEXT,after_data TEXT,at TEXT
        )""")
        db.execute("""CREATE TABLE equipment(
            id INTEGER PRIMARY KEY,contract_id INTEGER,sku TEXT,serial_number TEXT
        )""")
        db.execute("INSERT INTO equipment VALUES(1,1,'TEST-BIKE','SN-KEEP')")
        db.execute("INSERT INTO contracts VALUES(?,?,?,?,?,?,?,?,?)",(
            1,"ID-001","Active","Maintenance Database",4,
            json.dumps(row(4,"ID-001",120)["fields"]),1,0,"2026-01-01"
        ))
        db.execute("INSERT INTO contracts VALUES(?,?,?,?,?,?,?,?,?)",(
            2,"ID-002","Active","Maintenance Database",5,
            json.dumps(row(5,"ID-002",300,site="Another Fictional Gym")["fields"]),1,0,"2026-01-01"
        ))
        master_sync._tables(db)
    return path,connect


def test_modified_master_creates_safe_review_without_mutating_platform(tmp_path):
    path,connect=database(tmp_path)
    old=FakeSource([row(4,"ID-001",120),row(5,"ID-002",300,site="Another Fictional Gym")])
    new=FakeSource([row(4,"ID-001",140),row(5,"ID-002",300,site="Another Fictional Gym")])
    with connect() as db:
        report=master_sync.plan(db,old,new,"a"*64)
        amount=json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])["Contract amount (£)"]
    assert amount == 120
    assert report["summary"]["safe_updates"]==1
    assert report["summary"]["unchanged_or_already_current"]==1
    assert report["items"][0]["changes"][0]["field"]=="Contract amount (£)"
    assert report["items"][0]["changes"][0]["in_workbook"]==140
    assert report["deleted_or_archived_by_upload"]==0


def test_divergent_local_edits_require_manual_conflict_resolution(tmp_path):
    _,connect=database(tmp_path)
    old=FakeSource([row(4,"ID-001",120)])
    new=FakeSource([row(4,"ID-001",140)])
    with connect() as db:
        current=json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])
        current["Contract amount (£)"]=135
        db.execute("UPDATE contracts SET fields=?,revision=2 WHERE id=1",
                   (json.dumps(current),))
        db.commit()
        report=master_sync.plan(db,old,new,"b"*64)
    assert report["summary"]["conflicts"]==1
    assert report["summary"]["safe_updates"]==0
    assert "Contract amount (£)" in report["review_required"][0]["conflicting_fields"]


def test_new_duplicate_moved_or_removed_rows_never_auto_created_or_archived(tmp_path):
    _,connect=database(tmp_path)
    old=FakeSource([row(4,"ID-001",120),row(5,"ID-002",300,site="Another Fictional Gym")])
    new=FakeSource([
        row(6,"NEW-001",900,site="New Fictional Gym"),
        row(7,"REPEAT",100,site="Duplicate A"),
        row(8,"REPEAT",110,site="Duplicate B"),
    ],expired=[row(10,"ID-001",120)])
    with connect() as db:
        report=master_sync.plan(db,old,new,"c"*64)
        assert db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]==2
    assert report["summary"]["new_or_unmatched"]==1
    assert report["summary"]["ambiguous_rows"]==2
    assert report["summary"]["moves_requiring_review"]==1
    assert report["summary"]["missing_or_removed_from_workbook"]==1
    assert report["items"]==[]
    assert report["deleted_or_archived_by_upload"]==0


def _seed_review(tmp_path,monkeypatch):
    dbpath, connect=database(tmp_path)
    original=FakeSource([row(4,"ID-001",120)])
    incoming=FakeSource([row(4,"ID-001",140)])
    staged=tmp_path/"source.xlsx"
    staged.write_bytes(b"synthetic workbook bytes for testing only")
    sha=hashlib.sha256(staged.read_bytes()).hexdigest()
    monkeypatch.setattr(master_sync,"connect",connect)
    monkeypatch.setattr(master_sync,"_pending_path",lambda value: staged)
    monkeypatch.setattr(master_sync,"_baseline_verified",lambda db: "baseline-trusted")
    monkeypatch.setattr(master_sync,"create_local_backup",lambda force: {"created":True,"integrity":"ok"})
    monkeypatch.setattr(master_sync,"PILOT_MODE",True)
    monkeypatch.setattr(master_sync,"current_role",lambda: "Admin")
    monkeypatch.setattr(master_sync,"actor",lambda: "fictional-admin")
    review_id="a"*32
    with connect() as db:
        report=master_sync.plan(db,original,incoming,sha)
        db.execute(
            "INSERT INTO working_master_reviews VALUES(?,?,?,?,?,?,?,?)",
            (review_id,sha,"synthetic.xlsx","fictional-admin",
             "2026-11-02T12:00:00+00:00",
             "2099-01-01T00:00:00+00:00","Pending",json.dumps(report))
        )
    return connect,review_id


def test_reviewed_fields_apply_once_preserving_equipment_and_audit(tmp_path,monkeypatch):
    connect,review_id=_seed_review(tmp_path,monkeypatch)
    result=master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[0]))
    assert result["approved_records_updated"]==1
    assert result["automatically_archived"]==0
    with connect() as db:
        item=db.execute("SELECT fields,revision,status FROM contracts WHERE id=1").fetchone()
        assert json.loads(item["fields"])["Contract amount (£)"]==140
        assert item["revision"]==2
        assert item["status"]=="Active"
        assert db.execute("SELECT serial_number FROM equipment WHERE contract_id=1").fetchone()[0]=="SN-KEEP"
        assert db.execute("SELECT COUNT(*) FROM changes WHERE contract_id=1").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM working_master_actions").fetchone()[0]==1
        assert json.loads(db.execute("SELECT fields_json FROM working_master_baselines").fetchone()[0])["Contract amount (£)"]==140
    with pytest.raises(HTTPException) as exc:
        master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[0]))
    assert exc.value.status_code==409


def test_revision_change_after_preview_rejects_entire_batch(tmp_path,monkeypatch):
    connect,review_id=_seed_review(tmp_path,monkeypatch)
    with connect() as db:
        db.execute("UPDATE contracts SET revision=revision+1 WHERE id=1")
    with pytest.raises(HTTPException) as error:
        master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[0]))
    assert error.value.status_code==409
    with connect() as db:
        assert json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])["Contract amount (£)"]==120
        assert db.execute("SELECT COUNT(*) FROM working_master_actions").fetchone()[0]==0


def test_only_real_pilot_admin_may_apply(monkeypatch):
    monkeypatch.setattr(master_sync,"PILOT_MODE",True)
    monkeypatch.setattr(master_sync,"current_role",lambda: "Coordinator")
    with pytest.raises(HTTPException) as error:
        master_sync._admin()
    assert error.value.status_code==403
    monkeypatch.setattr(master_sync,"PILOT_MODE",False)
    monkeypatch.setattr(master_sync,"current_role",lambda: "Admin")
    with pytest.raises(HTTPException) as error:
        master_sync._admin()
    assert error.value.status_code==403


def test_forged_review_selection_is_rejected_atomically(tmp_path,monkeypatch):
    connect,review_id=_seed_review(tmp_path,monkeypatch)
    with pytest.raises(HTTPException) as error:
        master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[2]))
    assert error.value.status_code==422
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM working_master_actions").fetchone()[0]==0



def test_empty_financial_field_is_not_imputed_to_zero(tmp_path):
    _,connect=database(tmp_path)
    old=FakeSource([row(4,"ID-001",120)])
    incoming=FakeSource([row(4,"ID-001","")])
    with connect() as db:
        result=master_sync.plan(db,old,incoming,"d"*64)
    assert result["summary"]["safe_updates"]==1
    assert result["items"][0]["changes"][0]["in_workbook"]==""
    assert result["items"][0]["changes"][0]["in_workbook"]!=0


def test_bad_financial_amount_is_manual_review_only(tmp_path):
    _,connect=database(tmp_path)
    old=FakeSource([row(4,"ID-001",120)])
    incoming=FakeSource([row(4,"ID-001","not a price")])
    with connect() as db:
        result=master_sync.plan(db,old,incoming,"e"*64)
    assert result["summary"]["safe_updates"]==0
    assert result["summary"]["invalid_financial_or_date_rows"]==1


def test_backup_failure_prevents_any_update(tmp_path,monkeypatch):
    connect,review_id=_seed_review(tmp_path,monkeypatch)
    def backup(force):
        raise OSError("simulated backup failure")
    monkeypatch.setattr(master_sync,"create_local_backup",backup)
    with pytest.raises(HTTPException) as error:
        master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[0]))
    assert error.value.status_code==503
    with connect() as db:
        assert json.loads(db.execute("SELECT fields FROM contracts WHERE id=1").fetchone()[0])["Contract amount (£)"]==120
        assert db.execute("SELECT COUNT(*) FROM working_master_actions").fetchone()[0]==0


def test_master_sync_is_idempotent_after_approved_import(tmp_path,monkeypatch):
    connect,review_id=_seed_review(tmp_path,monkeypatch)
    master_sync.apply_review(review_id,master_sync.ApplyRequest(approved_items=[0]))
    old=FakeSource([row(4,"ID-001",120)])
    new=FakeSource([row(4,"ID-001",140)])
    with connect() as db:
        result=master_sync.plan(db,old,new,"b"*64)
    assert result["summary"]["safe_updates"]==0
    assert result["summary"]["conflicts"]==0
    assert result["items"]==[]


def test_new_source_next_action_date_is_eligible_for_review(tmp_path):
    _,connect=database(tmp_path)
    baseline=FakeSource([row(4,"ID-001",120)])
    updated=row(4,"ID-001",120)
    updated["fields"]["Next action date"]="2026-11-05"
    incoming=FakeSource([updated])
    with connect() as db:
        report=master_sync.plan(db,baseline,incoming,"d"*64)
    assert report["summary"]["safe_updates"]==1
    assert report["items"][0]["changes"]==[{
        "field":"Next action date",
        "before_source":"",
        "in_workbook":"2026-11-05",
        "in_platform":"",
        "conflict":False,
    }]
    assert report["new_source_date_fields_never_inferred_from_action_text"] is True


def test_mod_transfer_is_flagged_not_silently_reclassified(tmp_path):
    _,connect=database(tmp_path)
    previous=FakeSource([row(4,"ID-001",120)])
    new=FakeSource([])
    new.sheet_parts={"MOD":"xl/worksheets/sheet9.xml"}
    new.rows["MOD"]=[row(3,"ID-001",120)]
    with connect() as db:
        report=master_sync.plan(db,previous,new,"e"*64)
        assert db.execute("SELECT source_sheet FROM contracts WHERE id=1").fetchone()[0]=="Maintenance Database"
    assert report["summary"]["moves_requiring_review"]==1
    assert report["summary"]["safe_updates"]==0
    assert report["deleted_or_archived_by_upload"]==0
