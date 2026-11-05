"""Synthetic integration: invoice evidence -> exact Master -> coordinator draft ->
rate -> safely watermarked branded PDF. No customer or commercial release.
"""
import json
import sqlite3
from decimal import Decimal

import fitz
import pytest

from app import quote_drafts, quote_invoice_match, quote_quick_draft
from app.quote_quick_pdf import render_quick_internal_pdf


def test_complete_coordinator_internal_journey(tmp_path, monkeypatch):
    path=tmp_path/"coordinator_journey.sqlite"
    def db():
        con=sqlite3.connect(path)
        con.row_factory=sqlite3.Row
        return con
    with db() as con:
        con.execute(
            "CREATE TABLE imports(id INTEGER PRIMARY KEY,type TEXT,evidence_json TEXT)"
        )
        con.execute(
            "INSERT INTO imports(id,type,evidence_json) VALUES(?,?,?)",
            (49,"pdf",json.dumps({"equipment_codes":[
                {"value":"CARDIO-ONE","pages":[1]},
                {"value":"PART-BELT","pages":[1]},
                {"value":"NOT-MAPPED","pages":[2]}
            ]})),
        )
    master={
        "revision":9,"sha256":"9"*64,
        "rows":{
            "CARDIO-ONE":{
                "description":"Fictional Cardio Machine",
                "group":"Cardiovascular Equipment","price_pence":150000,
                "status":"REFERENCE","origin":"Unified Master"
            },
            "PART-BELT":{
                "description":"Fictional Spare Part","group":"CV Parts",
                "price_pence":4900,"status":"REFERENCE","origin":"Unified Master"
            },
        },
    }
    monkeypatch.setattr(quote_invoice_match,"connect",db)
    monkeypatch.setattr(quote_drafts,"connect",db)

    detected=quote_invoice_match.match_invoices([49],master)
    statuses={item["sku"]:item for item in detected["results"]}
    assert statuses["CARDIO-ONE"]["auto_add_equipment"] is True
    assert statuses["PART-BELT"]["auto_add_equipment"] is False
    assert statuses["NOT-MAPPED"]["requires_coordinator_review"] is True

    # The UI adds this exact code automatically, provisional qty=1.
    staged=quote_drafts.validate_draft({
        "customer":"Fictional Community Trust",
        "site":"Demo Fitness Studio",
        "tier":"Gold","term_years":3,
        "equipment":[{
            "item_code":"CARDIO-ONE","description":"Fictional Cardio Machine",
            "quantity":1, "serial":"",
            "source_import_id":49,"source_pages":[1],
            "invoice_match_confirmed":True,
            "invoice_match_method":"auto_exact_master",
            "annual_rate_percent":"3.75",
            "quantity_verified":False
        }]
    })
    assert staged["equipment"][0]["quantity_verified"] is False
    monkeypatch.setattr(
        "app.quote_price_book.active_book", lambda: master
    )
    quote_drafts.verify_invoice_evidence_link(staged)
    assert staged["equipment"][0]["invoice_match_master_revision"]==9

    # One bulk action confirms that the actual invoice contains two units.
    staged["equipment"][0]["quantity"]=2
    staged["equipment"][0]["quantity_verified"]=True
    staged["equipment"][0]["serial"]="FIC-1"
    quote_drafts.verify_invoice_evidence_link(staged)

    internal=quote_quick_draft.QuickDraft(
        customer=staged["customer"],
        site=staged["site"],package=staged["tier"],term_years=3,
        expected_price_book_sha256=master["sha256"],
        lines=[quote_quick_draft.QuickDraftLine(
            sku=staged["equipment"][0]["item_code"],
            quantity=staged["equipment"][0]["quantity"],
            serials=staged["equipment"][0]["serial"],
            annual_rate_percent=Decimal(
                staged["equipment"][0]["annual_rate_percent"]
            ),
        )],
    )
    priced=quote_quick_draft.calculate(internal,master)
    assert priced["complete_calculation"] is True
    assert priced["annual_partial_gbp"]=="112.50"
    assert priced["term_partial_gbp"]=="337.50"
    assert priced["customer_issue_enabled"] is False
    pdf=render_quick_internal_pdf(internal,priced)
    with fitz.open(stream=pdf,filetype="pdf") as document:
        contents=" ".join(page.get_text() for page in document)
        for needed in (
            "Fictional Community Trust","CARDIO-ONE","GBP 112.50",
            "GBP 337.50","INTERNAL DRAFT ONLY","SERVICE & AFTERSALES"
        ):
            assert needed in contents
        assert document[0].get_xobjects()
