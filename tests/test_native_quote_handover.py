"""End-to-end synthetic acceptance handover; no Sicon writes or real customers."""
import hashlib
import json
import sqlite3

import pytest
from fastapi import HTTPException

from app import native_quote_handover as bridge
from app import quote_intake


def _db(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _fixture(tmp_path, monkeypatch, *, accepted=True, tamper=False):
    source_path = tmp_path / "fake_smartquote.db"
    target_path = tmp_path / "fake_contracts.db"
    pdf = b"%PDF-1.4\n%synthetic fixture\n"
    sha = hashlib.sha256(pdf).hexdigest()
    saved = {
        "id": "sq-test-01", "quote_no": "SQ-TEST-01",
        "customer": "Fictional Leisure Ltd", "site": "Fictional Gym",
        "tier": "Gold", "pricing_approved": True,
        "account_ref": "EXAMPLE", "sicon_site_ref": "EXAMPLE-1",
        "contract_start": "2027-01-01", "contract_end": "2027-12-31",
        "assets": [{"id":"asset-1", "name":"Bike", "code":"BIKE-001",
                    "qty":1, "serial":"SN-DEMO-01",
                    "cover_start":"2027-01-01"}],
        "issued_quote_values": {
            "lines": [{"id":"asset-1","price":{"annual":120.0,"basis":"approved tariff"}}],
            "annual":120.0, "term_total":120.0,
        }
    }
    live = {**saved, "pipeline_status": "Accepted" if accepted else "Draft"}
    with _db(source_path) as db:
        db.execute("CREATE TABLE quotes(id TEXT PRIMARY KEY,payload TEXT)")
        db.execute("CREATE TABLE quote_versions(quote_id TEXT,version INTEGER,status TEXT,payload TEXT,pdf BLOB,pdf_sha256 TEXT)")
        db.execute("INSERT INTO quotes VALUES(?,?)",("sq-test-01",json.dumps(live)))
        db.execute("INSERT INTO quote_versions VALUES(?,?,?,?,?,?)",
                   ("sq-test-01",1,"Issued",json.dumps(saved),pdf,"a" * 64 if tamper else sha))
    with _db(target_path) as db:
        db.execute("CREATE TABLE contracts(id INTEGER PRIMARY KEY,status TEXT,fields TEXT)")

    monkeypatch.setattr(bridge, "_connect", lambda: _db(source_path))
    monkeypatch.setattr(bridge, "connect", lambda: _db(target_path))
    monkeypatch.setattr(bridge, "actor", lambda: "fictional-coordinator")
    return target_path


def test_direct_handover_creates_one_review_case_only(tmp_path, monkeypatch):
    target = _fixture(tmp_path,monkeypatch)
    handoff = bridge.accepted_snapshot("sq-test-01")
    assert handoff["pricing"]["commercially_approved"] is False
    assert handoff["pricing"]["source_quote_pdf_sha256"]
    assert handoff["equipment"][0]["serial_numbers"] == ["SN-DEMO-01"]

    preview = bridge.preview_native_handover("sq-test-01")
    assert preview["read_only_preview"] is True
    assert preview["already_imported_id"] is None
    assert preview["readiness"]["ready_for_setup"] is False

    first = bridge.submit_native_handover("sq-test-01")
    second = bridge.submit_native_handover("sq-test-01")
    assert first["intake_id"] == second["intake_id"]
    assert first["already_imported"] is False
    assert second["already_imported"] is True
    assert first["sicon_write_performed"] is False
    with _db(target) as db:
        assert db.execute("SELECT COUNT(*) FROM smartquote_intakes").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM smartquote_setup_cases").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 0


def test_handover_refuses_corrupt_pdf(tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch,tamper=True)
    with pytest.raises(HTTPException) as error:
        bridge.accepted_snapshot("sq-test-01")
    assert error.value.status_code == 409


def test_handover_refuses_unaccepted_source(tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch,accepted=False)
    with pytest.raises(HTTPException) as error:
        bridge.accepted_snapshot("sq-test-01")
    assert error.value.status_code == 409
