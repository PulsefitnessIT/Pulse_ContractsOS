"""Fictional regression tests for the 31+12-column expired contract workflow.

No real customer identifiers are stored in this repository.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

import pytest
from fastapi import HTTPException

from app import expiry_transfer as move
from app import register_layout as layout


HEADERS = [
    "Customer / site", "Site notes", "Sage Checked and Updated",
    "Sales region", "Sales manager", "County", "Site account",
    "Invoice account", "Contract number", "Start date", "Expiry date",
    "Contract term", "Contract / warranty type", "Invoice Code",
    "Beds and belts covered", "Upholstery covered",
    "Services per year", "Last service recorded", "Payment frequency",
    "Original amount (£)", "Contract amount (£)", "Payment notes",
    "Invoice numbers", "Comments", "Follow Up Date",
    "Next action date", "Next action", "Upholstery colour",
    "Renewal status", "Record ID", "Original source",
]
HISTORY = [
    "Contract coordinator", "Action due", "Response target",
    "Original amount notes", "Invoice reference", "Upholstery range",
    "Consoles / software", "Pulse Move CV", "Pulse Move strength",
    "IFI site", "Frame / upholstery finish", "Price reviews / contract history",
]


def date(offset):
    return (dt.date.today()+dt.timedelta(days=offset)).isoformat()


def fields(key, name, expiry):
    return {
        "Customer / site": name, "Record ID": key, "Expiry date": expiry,
        "Contract number": "SYNTH-2026-"+key,
        "Contract / warranty type": "Contract", "Sales manager": "Demo Sales",
        "Site notes": "Old equipment warranty terms in source",
        "Start date": date(-365),
        "Contract amount (£)": "777.35",
        "Next action": "Confirm renewal with customer",
        "Original source": "Synthetic master!3",
        "Renewal status": "Expiry passed – check",
    }


def fixture(tmp_path, monkeypatch):
    database=tmp_path/"fictional-contracts.db"
    def con():
        db=sqlite3.connect(database,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    with con() as db:
        db.execute("""CREATE TABLE contracts(
            id INTEGER PRIMARY KEY,row_key TEXT UNIQUE NOT NULL,
            revision INTEGER NOT NULL,status TEXT NOT NULL,
            source_sheet TEXT NOT NULL,source_row INTEGER NOT NULL,
            old_sheet TEXT DEFAULT '',old_row INTEGER,
            fields TEXT NOT NULL,fill TEXT,dirty INTEGER DEFAULT 0,
            updated_at TEXT
        )""")
        db.execute("""CREATE TABLE changes(
            id INTEGER PRIMARY KEY,contract_id INTEGER,actor TEXT,
            action TEXT,before_data TEXT,after_data TEXT,at TEXT
        )""")
        db.execute("""CREATE TABLE equipment(
            id INTEGER PRIMARY KEY,contract_id INTEGER,
            sku TEXT,serial_number TEXT
        )""")
        base=[
            (1,"FIC-01","Active","Maintenance Database",5,fields("FIC-01","Demo Leisure One",date(-14))),
            (2,"FIC-02","Active","Maintenance Database",6,fields("FIC-02","Demo Leisure Two",date(-40))),
            (3,"FIC-03","Active","Maintenance Database",7,fields("FIC-03","Demo Future",date(60))),
            (4,"FIC-04","Active","MOD",3,fields("FIC-04","Demo Defence",date(-4))),
            (5,"HIST-05","Expired","Expired",12,{
                **fields("HIST-05","Historical Fitness",date(-800)),
                "Contract coordinator":"Historical Coordinator",
                "Price reviews / contract history":"Keep this text",
            }),
            (6,"FIC-06","Active","Maintenance Database",8,fields("FIC-06","Missing date","")),
        ]
        for cid,key,status,sheet,row,record in base:
            db.execute(
                "INSERT INTO contracts "
                "(id,row_key,revision,status,source_sheet,source_row,fields,fill,dirty) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (cid,key,1,status,sheet,row,json.dumps(record),"#AABBCC",0),
            )
        db.execute(
            "INSERT INTO equipment VALUES(1,1,'FIC-TREAD','FIC-SERIAL-001')"
        )
    marker={"called":0}
    def backup(force=False):
        marker["called"]+=1
        return {"created":True,"integrity":"ok"}
    monkeypatch.setattr(move,"connect",con)
    monkeypatch.setattr(move,"create_local_backup",backup)
    monkeypatch.setattr(move.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(move.pilot_access,"current_role",lambda:"Coordinator")
    monkeypatch.setattr(move.pilot_access,"actor",lambda fallback="":"fictional-coordinator")
    layout_state={
        **layout.verify_headers(HEADERS,HEADERS+HISTORY,HEADERS),
        "template_last_expired_row":100,
        "source_registers":["Maintenance Database","MOD"],
    }
    monkeypatch.setattr(move,"current_layout",lambda path:layout_state)
    return con,marker


def approve(items, reason="All selected agreements confirmed expired and not renewed"):
    return move.TransferBatch(
        items=[
            move.TransferItem(**{
                key:entry[key] for key in (
                    "contract_id","expected_revision","row_key",
                    "source_sheet","source_row","expiry_date"
                )
            }) for entry in items
        ],
        reason=reason,
        confirm_verified_expiry_and_no_renewal=True,
    )


def test_expired_master_preserves_exact_31_shared_columns_plus_12_at_end():
    result=layout.verify_headers(HEADERS,HEADERS+HISTORY,HEADERS)
    assert result["aligned"] is True
    assert result["shared_column_count"]==31
    assert result["expired_only_column_count"]==12
    assert result["safe_copy_paste_range"]=="A:AE"
    assert result["expired_only_columns"]==HISTORY


@pytest.mark.parametrize("expired,mod",[
    (HEADERS[:-1]+[HEADERS[-2],HEADERS[-1]]+HISTORY,HEADERS),
    (HEADERS[:-1]+HISTORY,HEADERS),
    (HEADERS[:4]+["Contract coordinator"]+HEADERS[4:]+HISTORY,HEADERS),
    (HEADERS+HISTORY,HEADERS[:-1]+["Different source"]),
    (HEADERS+HISTORY+["Contract amount (£)"],HEADERS),
])
def test_misaligned_expired_or_mod_columns_fail_closed(expired,mod):
    with pytest.raises(ValueError):
        layout.verify_headers(HEADERS,expired,mod)


def test_coordinator_sees_candidates_without_any_transfer(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    rows=move.expiry_transfer_preview(source_sheet="Maintenance Database",
                                      limit=100,offset=0)
    assert rows["total_candidates"]==2
    assert rows["not_yet_expired"]==1
    assert rows["missing_or_invalid_expiry"]==1
    assert rows["columns"]["shared"]==31
    assert rows["columns"]["historical_only"]==12
    assert rows["no_automatic_transfers"] is True
    assert rows["items"][0]["contract_id"]==1  # Most recently expired first.
    assert marker["called"]==0
    with conn() as db:
        assert db.execute("SELECT COUNT(*) FROM contracts WHERE status='Expired'").fetchone()[0]==1


def test_expiry_transfer_preserves_every_field_and_linked_equipment(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    preview=move.expiry_transfer_preview(source_sheet="Maintenance Database")
    selected=preview["items"][:1]
    result=move.transfer_expired_contracts(approve(selected))
    assert result["transferred"]==1
    assert result["verified_backup_created"] is True
    assert result["items"][0]["from_sheet"]=="Maintenance Database"
    assert result["items"][0]["to_sheet"]=="Expired"
    assert result["items"][0]["to_row"]==101
    assert result["shared_expired_columns"]==31
    assert result["expired_extra_columns_preserved"]==12
    assert marker["called"]==1
    with conn() as db:
        row=db.execute("SELECT * FROM contracts WHERE id=1").fetchone()
        value=json.loads(row["fields"])
        assert row["status"]=="Expired"
        assert row["source_sheet"]=="Expired"
        assert row["old_sheet"]=="Maintenance Database"
        assert row["old_row"]==5
        assert row["revision"]==2
        assert row["dirty"]==1
        assert row["fill"]=="#AABBCC"
        assert value["Site notes"]=="Old equipment warranty terms in source"
        assert value["Contract amount (£)"]=="777.35"
        assert value["Original source"]=="Synthetic master!3"
        assert value["Renewal status"]=="Historical / archived"
        assert db.execute(
            "SELECT serial_number FROM equipment WHERE contract_id=1"
        ).fetchone()[0]=="FIC-SERIAL-001"
        archived=db.execute("SELECT fields FROM contracts WHERE id=5").fetchone()[0]
        assert json.loads(archived)["Price reviews / contract history"]=="Keep this text"
        log=db.execute(
            "SELECT actor,action,before_data,after_data FROM changes WHERE contract_id=1"
        ).fetchone()
        assert log["actor"]=="fictional-coordinator"
        assert log["action"]=="Transferred verified expired contract"
        assert json.loads(log["after_data"])["to_row"]==101


def test_batch_moves_mod_and_maintenance_without_overlapping_history(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    a=move.expiry_transfer_preview(source_sheet="Maintenance Database")["items"][0]
    m=move.expiry_transfer_preview(source_sheet="MOD")["items"][0]
    output=move.transfer_expired_contracts(approve([a,m]))
    assert output["transferred"]==2
    assert [item["to_row"] for item in output["items"]]==[101,102]
    with conn() as db:
        assert tuple(db.execute(
            "SELECT source_sheet,old_sheet FROM contracts WHERE id=4"
        ).fetchone())==("Expired","MOD")
        assert db.execute(
            "SELECT COUNT(DISTINCT source_row) FROM contracts WHERE source_sheet='Expired'"
        ).fetchone()[0]==3


def test_stale_revision_blocks_entire_batch_before_backup(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    entries=move.expiry_transfer_preview(source_sheet="Maintenance Database")["items"]
    with conn() as db:
        db.execute("UPDATE contracts SET revision=revision+1 WHERE id=2")
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(approve(entries))
    assert error.value.status_code==409
    assert marker["called"]==0
    with conn() as db:
        assert db.execute("SELECT status FROM contracts WHERE id=1").fetchone()[0]=="Active"


def test_expiring_future_contract_is_rejected_even_if_client_forges_selection(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    future={
        "contract_id":3,"expected_revision":1,
        "row_key":"FIC-03","source_sheet":"Maintenance Database",
        "source_row":7,"expiry_date":date(60),
    }
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(approve([future]))
    assert error.value.status_code==409
    assert marker["called"]==0


def test_missing_confirmation_or_unverified_role_does_not_archive(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    entry=move.expiry_transfer_preview(source_sheet="Maintenance Database")["items"][0]
    payload=approve([entry])
    payload.confirm_verified_expiry_and_no_renewal=False
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(payload)
    assert error.value.status_code==422
    monkeypatch.setattr(move.pilot_access,"current_role",lambda:"Viewer")
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(approve([entry]))
    assert error.value.status_code==403
    assert marker["called"]==0


def test_backup_failure_blocks_transfer_without_modification(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    entry=move.expiry_transfer_preview(source_sheet="MOD")["items"][0]
    monkeypatch.setattr(move,"create_local_backup",
                        lambda force=False:{"created":False,"integrity":"failed"})
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(approve([entry]))
    assert error.value.status_code==503
    with conn() as db:
        assert db.execute("SELECT status FROM contracts WHERE id=4").fetchone()[0]=="Active"


def test_duplicate_selected_contracts_rejected_before_writing(tmp_path,monkeypatch):
    conn,marker=fixture(tmp_path,monkeypatch)
    entry=move.expiry_transfer_preview(source_sheet="Maintenance Database")["items"][0]
    with pytest.raises(HTTPException) as error:
        move.transfer_expired_contracts(approve([entry,entry]))
    assert error.value.status_code==422
    assert marker["called"]==0
