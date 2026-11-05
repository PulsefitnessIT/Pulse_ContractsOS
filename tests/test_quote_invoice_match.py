"""Synthetic invoice-to-one-Master automatic matching tests; no customer data."""
import json
import sqlite3

import pytest
from fastapi import HTTPException

from app import quote_drafts, quote_invoice_match, quote_price_book, quote_quick_draft


@pytest.fixture
def environment(tmp_path, monkeypatch):
    db_path = tmp_path / "invoice_match_synthetic.sqlite3"
    def db():
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        return con
    with db() as con:
        con.execute(
            "CREATE TABLE imports(id INTEGER PRIMARY KEY,type TEXT,evidence_json TEXT)"
        )
        con.execute(
            "INSERT INTO imports(id,type,evidence_json) VALUES(?,?,?)",
            (91, "pdf", json.dumps({"equipment_codes": [
                {"value":"bike-001", "pages":[1,2]},
                {"value":"BIKE-001", "pages":[2]},
                {"value":"BELT-001", "pages":[1]},
                {"value":"HELD-001", "pages":[4]},
                {"value":"UNKNOWN-001", "pages":[4]},
                {"value":"E-REPEAT", "pages":[3]},
            ]})),
        )
        con.execute(
            "INSERT INTO imports(id,type,evidence_json) VALUES(?,?,?)",
            (92, "pdf", json.dumps({"equipment_codes": [
                {"value":"E-REPEAT", "pages":[1]},
            ]})),
        )
    book = {
        "revision": 8, "sha256": "c" * 64, "rows": {
            "BIKE-001": {
                "price_pence": 110000, "status":"REFERENCE",
                "description":"Example Cardio Bike",
                "group":"Cardiovascular Equipment",
            },
            "BELT-001": {
                "price_pence": 3000, "status":"REFERENCE",
                "description":"Spare Bike Belt", "group":"CV Parts"
            },
            "HELD-001": {
                "price_pence": None, "status":"HOLD",
                "description":"Conflicted Strength Machine",
                "group":"Strength Equipment"
            },
            "E-REPEAT": {
                "price_pence": 250000, "status":"REFERENCE",
                "description":"Fictional Strength Machine",
                "group":"Strength Equipment"
            },
        }
    }
    monkeypatch.setattr(quote_invoice_match, "connect", db)
    monkeypatch.setattr(quote_drafts, "connect", db)
    monkeypatch.setattr(quote_price_book, "active_book", lambda: book)
    monkeypatch.setattr(quote_quick_draft, "active_book", lambda: book)
    monkeypatch.setattr(quote_quick_draft.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(quote_quick_draft.pilot_access, "current_role", lambda: "Coordinator")
    monkeypatch.setattr(quote_quick_draft.pilot_access, "actor", lambda default="": "fictional-coordinator")
    return db, book


def test_matching_exact_codes_requires_no_coordinator_checkbox(environment):
    result = quote_invoice_match.invoice_auto_match(
        quote_invoice_match.InvoiceMatchBatch(import_ids=[91])
    )
    by_code = {x["sku"]: x for x in result["results"]}
    assert result["price_book_revision"] == 8
    assert result["price_book_sha256"] == "c" * 64
    assert result["counts"] == {
        "matched_equipment": 2,
        "matched_inventory_not_machine": 1,
        "matched_unpriced_or_held": 1,
        "unmatched": 1,
    }
    assert by_code["BIKE-001"]["auto_add_equipment"] is True
    assert by_code["BIKE-001"]["requires_coordinator_review"] is False
    assert by_code["BIKE-001"]["source_pages"] == [1, 2]
    assert by_code["BELT-001"]["status"] == "matched_inventory_not_machine"
    assert by_code["BELT-001"]["auto_add_equipment"] is False
    assert by_code["HELD-001"]["status"] == "matched_unpriced_or_held"
    assert by_code["HELD-001"]["requires_coordinator_review"] is False
    assert by_code["UNKNOWN-001"]["status"] == "unmatched"
    assert by_code["UNKNOWN-001"]["requires_coordinator_review"] is True
    assert result["automatic_matches_require_no_code_confirmation"] is True
    assert result["not_an_approved_customer_quotation"] is True


def test_exact_code_occurring_in_two_invoices_has_two_source_references(environment):
    results = quote_invoice_match.match_invoices([91,92], environment[1])
    repeated = [x for x in results["results"] if x["sku"] == "E-REPEAT"]
    assert len(repeated) == 2
    assert {x["source_import_id"] for x in repeated} == {91, 92}
    assert {tuple(x["source_pages"]) for x in repeated} == {(3,), (1,)}


def test_auto_matched_invoice_can_be_saved_without_manual_confirmation(environment):
    payload = {
        "customer":"Example Customer", "site":"Training Gym",
        "equipment":[{
            "item_code":"BIKE-001", "description":"Example Cardio Bike",
            "source_import_id":91, "source_pages":[1],
            "invoice_match_confirmed":True,
            "invoice_match_method":"auto_exact_master", "quantity":1,
        }]
    }
    normal = quote_drafts.validate_draft(payload)
    quote_drafts.verify_invoice_evidence_link(normal)
    assert normal["equipment"][0]["invoice_match_master_revision"] == 8
    assert normal["equipment"][0]["invoice_match_master_sha256"] == "c" * 64
    quote_drafts._stamp_invoice_match_decisions(normal, "fictional-coordinator")
    assert normal["equipment"][0]["invoice_match_confirmed_by"] == (
        "Automatic exact Master SKU match"
    )
    assert normal["equipment"][0]["invoice_match_confirmed_at"]


@pytest.mark.parametrize("code", ["BELT-001", "HELD-001", "UNKNOWN-001"])
def test_spares_held_and_unmatched_cannot_forge_automatic_acceptance(environment, code):
    raw = {
        "customer":"Example Customer","site":"Training Gym",
        "equipment":[{
            "item_code":code, "description":"Fictional item",
            "source_import_id":91, "source_pages":[1] if code == "BELT-001" else [4],
            "invoice_match_confirmed":True,
            "invoice_match_method":"auto_exact_master", "quantity":1
        }]
    }
    normal=quote_drafts.validate_draft(raw)
    with pytest.raises(HTTPException) as error:
        quote_drafts.verify_invoice_evidence_link(normal)
    assert error.value.status_code == 409


def test_automatic_claim_rechecked_when_price_book_changes(environment):
    payload={
        "customer":"Example Customer","site":"Training Gym",
        "equipment":[{
            "item_code":"BIKE-001", "description":"Example Cardio Bike",
            "source_import_id":91,"source_pages":[1],
            "invoice_match_confirmed":True,"invoice_match_method":"auto_exact_master",
            "quantity":1
        }]
    }
    normal=quote_drafts.validate_draft(payload)
    environment[1]["rows"]["BIKE-001"]["group"]="CV Parts"
    with pytest.raises(HTTPException) as error:
        quote_drafts.verify_invoice_evidence_link(normal)
    assert error.value.status_code == 409


def test_batch_security_rejects_forged_or_missing_invoice(environment,monkeypatch):
    for ids in ([91,91], [91,92,93], [], [0], [-1]):
        with pytest.raises(HTTPException):
            quote_invoice_match.match_invoices(ids, environment[1])
    monkeypatch.setattr(quote_quick_draft.pilot_access,"current_role",lambda:"Viewer")
    with pytest.raises(HTTPException) as error:
        quote_invoice_match.invoice_auto_match(
            quote_invoice_match.InvoiceMatchBatch(import_ids=[91])
        )
    assert error.value.status_code == 403


def test_no_client_provided_auto_match_audit_fields_can_be_spoofed(environment):
    incoming=quote_drafts.validate_draft({
        "customer":"Example","site":"Gym",
        "equipment":[{
            "item_code":"BIKE-001","description":"Example Cardio Bike",
            "source_import_id":91,"source_pages":[1],
            "invoice_match_confirmed":True,
            "invoice_match_method":"auto_exact_master",
            "invoice_match_confirmed_by":"HACKED",
            "invoice_match_master_sha256":"x"*64,
            "quantity":1
        }],
    })
    assert "invoice_match_confirmed_by" not in incoming["equipment"][0]
    assert "invoice_match_master_sha256" not in incoming["equipment"][0]
    quote_drafts.verify_invoice_evidence_link(incoming)
    assert incoming["equipment"][0]["invoice_match_master_sha256"]=="c"*64
