"""Synthetic safety checks for draft-only unified quotations."""
import pytest
from fastapi import HTTPException
from app import quote_drafts

def test_draft_never_generates_a_price():
    result = quote_drafts.validate_draft({
        "customer":"Example Ltd","site":"Demo Site","tier":"Silver",
        "equipment":[{"description":"Treadmill", "quantity":2,"item_code":"TEST001"}]})
    assert result["price"] is None
    assert result["approved"] is False
    assert result["commercial_status"] == "Unpriced draft"
    assert result["equipment"][0]["quantity"] == 2

@pytest.mark.parametrize("qty",[0,-1,1.5,True,"2"])
def test_invalid_quantity_rejected(qty):
    with pytest.raises(HTTPException) as error:
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym",
           "equipment":[{"description":"Treadmill","quantity":qty}]})
    assert error.value.status_code == 422

def test_unknown_maintenance_package_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym","tier":"Unsupported"})

def test_empty_customer_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"","site":"Gym"})

def test_too_many_lines_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym",
           "equipment":[{"description":"Test"} for _ in range(501)]})

def test_create_edit_and_reopen_draft_with_revision_control(tmp_path, monkeypatch):
    import sqlite3
    from app import store
    db_path = tmp_path / "contracts.sqlite3"

    def test_connect():
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        return con

    monkeypatch.setattr(quote_drafts, "connect", test_connect)
    monkeypatch.setattr(quote_drafts, "actor", lambda: "demo-coordinator")
    monkeypatch.setattr(quote_drafts, "PILOT_MODE", False)

    payload = {"customer": "Example Leisure", "site": "Demo Pool", "tier": "Gold",
        "equipment": [{"description": "Bike", "item_code": "DEMO-001", "quantity": 2}]}
    created = quote_drafts.create_draft(payload)
    assert created["approved"] is False and created["price"] is None

    opened = quote_drafts.get_draft(created["id"])
    assert opened["equipment"][0]["quantity"] == 2
    assert opened["revision"] == 1

    review = quote_drafts.draft_readiness(created["id"])
    assert review["pricing_ready"] is False
    assert review["contract_setup_ready"] is False
    assert any("serial" in item.lower() for item in review["review_issues"])

    updated = quote_drafts.update_draft(created["id"], {**payload, "revision": 1,
        "equipment": [{"description": "Bike", "item_code": "DEMO-001",
                        "quantity": 1, "serial": "SERIAL-1"}]})
    assert updated["revision"] == 2
    assert quote_drafts.get_draft(created["id"])["equipment"][0]["serial"] == "SERIAL-1"

    with pytest.raises(HTTPException) as error:
        quote_drafts.update_draft(created["id"], {**payload, "revision": 1})
    assert error.value.status_code == 409

    with sqlite3.connect(db_path) as con:
        count = con.execute("SELECT COUNT(*) FROM unified_quote_drafts").fetchone()[0]
    assert count == 1


def test_client_cannot_assert_pricing_or_approval():
    result = quote_drafts.validate_draft({
        "customer": "Demo", "site": "Demo Site",
        "approved": True, "price": 12345,
        "commercial_status": "Approved", "equipment": []})
    assert result["approved"] is False
    assert result["price"] is None
    assert result["commercial_status"] == "Unpriced draft"

def test_viewer_cannot_write_drafts_even_with_non_viewer_username(monkeypatch):
    monkeypatch.setattr(quote_drafts, "actor", lambda: "lee")
    monkeypatch.setattr(quote_drafts, "PILOT_MODE", True)
    monkeypatch.setattr(quote_drafts, "current_role", lambda: "Viewer")
    with pytest.raises(HTTPException) as error:
        quote_drafts._check_access(write=True)
    assert error.value.status_code == 403


def test_pilot_requires_verified_session_role(monkeypatch):
    monkeypatch.setattr(quote_drafts, "actor", lambda: "Coordinator")
    monkeypatch.setattr(quote_drafts, "PILOT_MODE", True)
    monkeypatch.setattr(quote_drafts, "current_role", lambda: None)
    with pytest.raises(HTTPException) as error:
        quote_drafts._check_access(write=False)
    assert error.value.status_code == 401



@pytest.mark.parametrize("source_id,pages",[
    (True, [2]), ("17", [2]), (0,[2]), (17,["2"]),
    (17,[0]), (17,[-1]), (17,[2]*31), (None,[2]),
])
def test_invoice_provenance_rejects_invalid_client_evidence(source_id, pages):
    with pytest.raises(HTTPException) as err:
        quote_drafts.validate_draft({
            "customer":"Fictional Leisure","site":"Fictional Hall",
            "equipment":[{"description":"Fictional Bike","item_code":"TEST-001",
                "quantity":1,"source_import_id":source_id,"source_pages":pages}],
        })
    assert err.value.status_code==422


def test_pdf_invoice_code_pages_are_checked_before_draft_write(tmp_path,monkeypatch):
    import sqlite3,json
    from pathlib import Path
    db_path=tmp_path/"fictional.sqlite3"
    def db():
        con=sqlite3.connect(db_path)
        con.row_factory=sqlite3.Row
        return con
    with db() as con:
        con.execute("CREATE TABLE imports (id INTEGER PRIMARY KEY, type TEXT, evidence_json TEXT)")
        con.execute("INSERT INTO imports (id,type,evidence_json) VALUES(17,?,?)",(
            "pdf",json.dumps({"equipment_codes":[
                {"value":"TEST-001","pages":[2,3]},
                {"value":"OTHER-PART","pages":[1]},
            ]}),
        ))
        con.execute("INSERT INTO imports (id,type,evidence_json) VALUES(18,?,?)",(
            "xlsx",json.dumps({"equipment_codes":[{"value":"TEST-001","pages":[2]}]}),
        ))
    monkeypatch.setattr(quote_drafts,"connect",db)
    monkeypatch.setattr(quote_drafts,"actor",lambda:"fictional-coordinator")
    monkeypatch.setattr(quote_drafts,"PILOT_MODE",False)
    payload={
        "customer":"Fictional Leisure","site":"Fictional Hall","tier":"Gold",
        "equipment":[{"description":"Fictional Bike","item_code":"TEST-001",
            "serial":"FIC-SER-1","quantity":1,
            "source_import_id":17,"source_pages":[3,2,2]}],
    }
    created=quote_drafts.create_draft(payload)
    assert created["equipment"][0]["source_import_id"]==17
    assert created["equipment"][0]["source_pages"]==[2,3]
    stored=quote_drafts.get_draft(created["id"])
    assert stored["equipment"][0]["serial"]=="FIC-SER-1"

    failures=[
        {**payload,"equipment":[{**payload["equipment"][0],"item_code":"UNSEEN-1"}]},
        {**payload,"equipment":[{**payload["equipment"][0],"source_pages":[4]}]},
        {**payload,"equipment":[{**payload["equipment"][0],"source_import_id":18}]},
        {**payload,"equipment":[{**payload["equipment"][0],"source_import_id":19}]},
    ]
    for bad in failures:
        with pytest.raises(HTTPException) as err:
            quote_drafts.update_draft(created["id"],{**bad,"revision":1})
        assert err.value.status_code==409
    assert quote_drafts.get_draft(created["id"])["revision"]==1
    # Manually confirmed alternatives are permitted, but no forged invoice
    # provenance is retained on that equipment line.
    updated=quote_drafts.update_draft(created["id"],{
        **payload,"revision":1,
        "equipment":[{**payload["equipment"][0],"item_code":"CORRECTED-SKU",
            "source_import_id":None,"source_pages":[]}],
    })
    assert updated["equipment"][0]["source_import_id"] is None
    assert updated["equipment"][0]["source_pages"]==[]
