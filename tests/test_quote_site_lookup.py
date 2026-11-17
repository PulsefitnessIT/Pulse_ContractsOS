"""Fictional source-site evidence tests; never infer customer names from site labels."""
import json
import sqlite3

import pytest
from fastapi import HTTPException

from app import quote_site_lookup, quote_drafts


def demo_db(tmp_path,monkeypatch):
    db = tmp_path / "source_site_demo.db"
    with sqlite3.connect(db) as con:
        con.execute("""CREATE TABLE contracts(
            id INTEGER PRIMARY KEY,row_key TEXT,status TEXT,
            source_sheet TEXT,source_row INTEGER,fields TEXT
        )""")
        con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?)",[
            (1,"ACT-001","Active","Maintenance Database",2,
             json.dumps({"Customer / site":"Example Leisure Gym - South",
                         "Contract number":"CON001",
                         "Contract / warranty type":"P&L Ext Warr",
                         "Site account":"SITE-X","Invoice account":"ACC-X",
                         "Record ID":"ACT-001"})),
            (2,"EXP-001","Expired","Expired",15,
             json.dumps({"Customer / site":"Example Leisure Gym - North",
                         "Contract number":"CON-OLD",
                         "Contract / warranty type":"Warranty",
                         "Record ID":"EXP-001"})),
        ])
    def connect():
        c=sqlite3.connect(db)
        c.row_factory=sqlite3.Row
        return c
    monkeypatch.setattr(quote_site_lookup,"connect",connect)
    monkeypatch.setattr(quote_drafts,"connect",connect)
    monkeypatch.setattr(quote_drafts,"actor",lambda: "fictional-coordinator")
    monkeypatch.setattr(quote_drafts,"PILOT_MODE",False)
    return db


def test_site_search_is_exact_record_evidence_not_legal_customer(tmp_path,monkeypatch):
    demo_db(tmp_path,monkeypatch)
    found=quote_site_lookup.find_sites("Example Leisure",20)
    assert found["total"] == 2
    assert found["items"][0]["site_label"] == "Example Leisure Gym - South"
    assert found["items"][0]["recorded_cover_label"] == "P&L Ext Warr"
    assert found["items"][0]["source_row"] == 2
    assert found["items"][1]["status"] == "Expired"
    assert found["legal_customer_name_inferred"] is False
    assert "legal_customer" not in found["items"][0]


def test_source_link_must_match_existing_site_exactly(tmp_path,monkeypatch):
    demo_db(tmp_path,monkeypatch)
    valid = {
        "customer":"Fictional legal company — reviewed separately",
        "site":"Example Leisure Gym - South",
        "source_contract_id":1,"tier":"Gold",
        "equipment":[{"description":"Bike","item_code":"FICTIONAL-1","quantity":1}]
    }
    created=quote_drafts.create_draft(valid)
    assert created["source_contract_id"]==1
    with pytest.raises(HTTPException) as error:
        quote_drafts.create_draft({**valid,"site":"Example Leisure Gym - North"})
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        quote_drafts.create_draft({**valid,"source_contract_id":999})
    assert error.value.status_code == 409


@pytest.mark.parametrize("source",[False,3.5,-1,"1",True])
def test_non_integer_source_row_id_rejected(source):
    with pytest.raises(HTTPException) as error:
        quote_drafts.validate_draft({
            "customer":"Fictional","site":"Recorded Demo",
            "source_contract_id":source
        })
    assert error.value.status_code == 422


def test_manual_site_is_allowed_but_not_claimed_as_verified():
    draft=quote_drafts.validate_draft({
        "customer":"Fictional","site":"Independently verified new site",
        "source_contract_id":None
    })
    assert draft["source_contract_id"] is None
    assert draft["commercial_status"]=="Unpriced draft"
