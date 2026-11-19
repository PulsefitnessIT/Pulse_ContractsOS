"""Synthetic-only printable agreement tests; no real Pulse customer details."""
import json
import sqlite3

import fitz
import pytest
from fastapi import HTTPException

from app import contract_agreement_print as agreement


def test_branded_maintenance_agreement_is_review_only():
    fields={
        "Customer / site":"Fictional Leisure Centre",
        "Contract number":"DEMO-CONT-001",
        "Contract / warranty type":"Gold",
        "Start date":"2026-11-01",
        "Expiry date":"2027-10-31",
        "Services per year":"1",
        "Payment frequency":"Annually",
        "Contract amount (£)":"1250.50",
    }
    pdf=agreement.generate_review_pdf(fields,[])
    assert pdf.startswith(b"%PDF")
    doc=fitz.open(stream=pdf,filetype="pdf")
    assert len(doc)==1
    words="\n".join(page.get_text() for page in doc)
    assert "PULSE FITNESS" in words
    assert "Fictional Leisure Centre" in words
    assert "DEMO-CONT-001" in words
    assert "01/11/2026" in words
    assert "31/10/2027" in words
    assert "NOT AN ISSUED OR SIGNED AGREEMENT" in words
    assert "No equipment schedule" in words
    assert "GBP 1,250.50" in words
    doc.close()


def test_equipment_appendix_only_uses_recorded_codes_and_serials():
    rows=[
        {"sku":"FAKE-220","name":"Fictional treadmill","quantity":2,"serial_number":"DEMO-0001"},
        {"sku":"FAKE-311","name":"Fictional strength machine","quantity":1,"serial_number":""},
    ]
    pdf=agreement.generate_review_pdf({"Customer / site":"Test Campus"},rows)
    doc=fitz.open(stream=pdf,filetype="pdf")
    assert len(doc)==2
    appendix=doc[1].get_text()
    assert "FAKE-220" in appendix
    assert "DEMO-0001" in appendix
    assert "To confirm" in appendix
    assert "Confirm serials" in appendix
    doc.close()


def test_missing_site_blocks_document_generation():
    with pytest.raises(HTTPException) as exc:
        agreement.generate_review_pdf({"Customer / site":""},[])
    assert exc.value.status_code==422


def test_pdf_route_reads_only_recorded_contract_and_requires_named_staff(monkeypatch,tmp_path):
    db_path=tmp_path/"fictional_agreement.sqlite3"
    def connect():
        db=sqlite3.connect(db_path)
        db.row_factory=sqlite3.Row
        return db
    with connect() as db:
        db.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, fields TEXT)")
        db.execute("CREATE TABLE catalogue (sku TEXT PRIMARY KEY, name TEXT, model TEXT, description TEXT)")
        db.execute("CREATE TABLE equipment (id INTEGER PRIMARY KEY,contract_id INTEGER,sku TEXT,serial_number TEXT,quantity INTEGER)")
        db.execute("INSERT INTO contracts VALUES(1,?)",
                   (json.dumps({"Customer / site":"Fictional Gym","Contract number":"SIM-023"}),))
        db.execute("INSERT INTO catalogue VALUES('DEMO-CYCLE','Fictional cycle','','')")
        db.execute("INSERT INTO equipment VALUES(1,1,'DEMO-CYCLE','SIM-SERIAL',1)")
    monkeypatch.setattr(agreement,"connect",connect)
    monkeypatch.setattr(agreement,"_staff",lambda:"fictional-coordinator")
    response=agreement.download_contract_agreement_preview(1)
    assert response.media_type=="application/pdf"
    assert response.headers["cache-control"]=="private, no-store"
    with fitz.open(stream=response.body,filetype="pdf") as doc:
        assert "Fictional Gym" in doc[0].get_text()
        assert "SIM-SERIAL" in doc[1].get_text()
    with pytest.raises(HTTPException) as exc:
        agreement.download_contract_agreement_preview(123)
    assert exc.value.status_code==404
    monkeypatch.setattr(agreement,"_staff",
                        lambda:(_ for _ in ()).throw(HTTPException(403,"Denied")))
    with pytest.raises(HTTPException) as denied:
        agreement.download_contract_agreement_preview(1)
    assert denied.value.status_code==403


def test_excel_serial_dates_are_formatted_without_modifying_values():
    original="45799"
    assert agreement._uk_date(original)=="22/05/2025"
    assert original=="45799"
    assert agreement._uk_date("2026-12-31")=="31/12/2026"
