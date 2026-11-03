"""End-to-end test: in-app commercial sign-off unlocks customer quotation.

Fictional sources only. These tests prove guarded workflow; they are NOT
approval of the real Pulse Fitness price list or real maintenance terms.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import json
import sqlite3

import fitz
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import quote_commercial_setup as settings
from app import quote_customer_issuance as issue
from app import quote_drafts


def _terms_bytes():
    document=fitz.open()
    page=document.new_page()
    page.insert_text((50,70),"SYNTHETIC PULSE MAINTENANCE TERMS - FOR TESTS ONLY")
    raw=document.tobytes()
    document.close()
    return raw


def _setup(tmp_path,monkeypatch):
    filename=tmp_path/"commercial-approvals.db"
    def connection():
        db=sqlite3.connect(filename,timeout=10)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    monkeypatch.setattr(settings,"connect",connection)
    monkeypatch.setattr(issue,"connect",connection)
    monkeypatch.setattr(settings.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(settings.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(settings.pilot_access,"actor",lambda name="":"fictional-director")
    monkeypatch.setattr(issue.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(issue.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(issue.pilot_access,"actor",lambda name="":"fictional-director")
    monkeypatch.delenv(issue.APPROVAL_SOURCE_ENV,raising=False)
    monkeypatch.delenv(issue.TERMS_FILE_ENV,raising=False)
    monkeypatch.delenv(issue.TERMS_SHA_ENV,raising=False)
    monkeypatch.delenv(issue.ISSUER_FILE_ENV,raising=False)
    monkeypatch.delenv(issue.ISSUER_SHA_ENV,raising=False)
    monkeypatch.delenv(issue.ISSUE_ENV,raising=False)
    policy={
        "pricing_status":"Provisional",
        "rates":[{"group":"Standard Equipment","standard":0.03,
                  "minimum":0.025,"status":"Active"}],
        "tiers":{"Silver":0.8,"Gold":1.0,"Platinum":1.3},
    }
    monkeypatch.setattr(settings.quote_pricing,"source_snapshot",
        lambda:([{"sku":"DEMO-1"}],[{"key":"demo"}],policy,
                {"catalog":"b"*64,"configs":"c"*64,"pricing":"a"*64}))
    monkeypatch.setattr(settings.quote_pricing,"source_manifest_status",
        lambda hashes:{"pinned":True,"matches":True})
    return connection,filename


def _tariff(hash="a"*64):
    return settings.ApproveTariff(
        expected_source_sha256=hash,
        approval_reference="DEMO-DIRECTOR-TARIFF-APPROVAL",
        reason="Commercially reviewed the fictional 2026 tariff",
        confirm_equipment_rate_groups=True,
        confirm_package_multipliers=True,
        confirm_minimums_and_discounts=True,
        confirm_parity_exceptions_reviewed=True,
    )


def _issuer():
    return settings.IssuerDetails(
        legal_name="Test Pulse Fitness Ltd",
        registered_address="123 Fictional Road, Test Town, EX1 1AA",
        company_number="12345678",
        contact_email="service@fictional.invalid",
        telephone="0000 000000",
        approval_reference="COMPANY-IDENTITY-TEST-2026",
        reason="Verified fictional company information for testing",
        confirm_verified_company_details=True,
    )


def _enable(value=True):
    return settings.EnableCustomerQuotes(
        enabled=value,
        approval_reference="RELEASE-APPROVAL-DEMO-2026",
        reason="End-to-end quotation workflow checked in test",
        confirm_customer_quote_acceptance_tests=True,
    )


def _upload_terms():
    file=UploadFile(file=io.BytesIO(_terms_bytes()),filename="approved-terms.pdf")
    return asyncio.run(settings.approve_terms(
        file=file,
        approval_reference="TERMS-SIGNOFF-DEMO-2026",
        reason="Approved current test commercial terms",
        confirm_approved_current_terms=True,
    ))


def test_release_requires_every_approved_commercial_input(tmp_path,monkeypatch):
    db,path=_setup(tmp_path,monkeypatch)
    status=settings.commercial_status()
    assert status["tariff_source"]["staged"] is True
    assert status["tariff_source"]["commercially_approved"] is False
    assert status["customer_issuance_enabled"] is False
    with pytest.raises(HTTPException) as err:
        settings.set_issuance(_enable())
    assert err.value.status_code==409

    confirmed=settings.approve_tariff(_tariff())
    assert confirmed["revision"]==1
    assert settings.tariff_is_approved("a"*64)
    assert issue._approved_tariff("a"*64) is True
    with pytest.raises(HTTPException) as err:
        settings.set_issuance(_enable())
    assert err.value.status_code==409

    identity=settings.save_issuer(_issuer())
    assert identity["revision"]==1
    assert issue._issuer()[0]["company_number"]=="12345678"
    with pytest.raises(HTTPException) as err:
        settings.set_issuance(_enable())
    assert err.value.status_code==409

    legal=_upload_terms()
    assert legal["terms_pages"]==1
    assert issue._terms()[0]==_terms_bytes() or issue._terms()[1]==legal["sha256"]
    activated=settings.set_issuance(_enable())
    assert activated["revision"]==1
    assert settings.enabled() is True
    assert issue._issuance_enabled() is True
    state=settings.commercial_status()
    assert state["customer_issuance_enabled"] is True
    assert state["settings"]["terms"]["integrity_valid"] is True
    assert state["settings"]["issuer"]["integrity_valid"] is True
    assert len(settings.commercial_audit()["items"])==4
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM smartquote_commercial_settings").fetchone()[0]==4


def test_modified_terms_auto_disables_customer_issuance(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    settings.approve_tariff(_tariff())
    settings.save_issuer(_issuer())
    _upload_terms()
    settings.set_issuance(_enable())
    settings.save_issuer(_issuer())
    assert not settings.enabled()
    assert issue._issuance_enabled() is False
    audit=settings.commercial_audit()["items"]
    assert any(item["kind"]=="issuance" and
               "Automatically disabled" in item["reason"] for item in audit)


def test_commercial_setup_tamper_is_not_silently_accepted(tmp_path,monkeypatch):
    db,_=_setup(tmp_path,monkeypatch)
    settings.approve_tariff(_tariff())
    with db() as conn:
        conn.execute("UPDATE smartquote_commercial_settings SET payload=? "
                     "WHERE kind='tariff'",(b'{"approved_tariff_sha256":"a"}',))
    with pytest.raises(HTTPException) as err:
        settings.tariff_is_approved("a"*64)
    assert err.value.status_code==503


@pytest.mark.parametrize("approval",["tariff","issuer","terms","issuance"])
def test_non_admin_cannot_authorise_any_commercial_setup(tmp_path,monkeypatch,approval):
    _setup(tmp_path,monkeypatch)
    monkeypatch.setattr(settings.pilot_access,"current_role",lambda:"Coordinator")
    with pytest.raises(HTTPException) as err:
        if approval=="tariff":
            settings.approve_tariff(_tariff())
        elif approval=="issuer":
            settings.save_issuer(_issuer())
        elif approval=="issuance":
            settings.set_issuance(_enable())
        else:
            _upload_terms()
    assert err.value.status_code==403


def test_admin_cannot_approve_a_tariff_hash_that_changed(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    with pytest.raises(HTTPException) as err:
        settings.approve_tariff(_tariff("9"*64))
    assert err.value.status_code==409
    assert settings.tariff_is_approved("a"*64) is False


def test_explicit_it_disable_overrides_approved_in_app_release(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    settings.approve_tariff(_tariff())
    settings.save_issuer(_issuer())
    _upload_terms()
    settings.set_issuance(_enable())
    assert issue._issuance_enabled()
    monkeypatch.setenv(issue.ISSUE_ENV,"0")
    assert issue._issuance_enabled() is False
    monkeypatch.setenv(issue.APPROVAL_SOURCE_ENV,"f"*64)
    assert issue._approved_tariff("a"*64) is False


def test_zero_price_or_unresolved_equipment_still_blocks_customer_issue(tmp_path,monkeypatch):
    from tests.test_quote_customer_issuance import fake_price, fake_draft
    db,_=_setup(tmp_path,monkeypatch)
    settings.approve_tariff(_tariff())
    settings.save_issuer(_issuer())
    _upload_terms()
    settings.set_issuance(_enable())
    with db() as conn:
        quote_drafts._init(conn)
        draft=fake_draft()
        conn.execute(
            "INSERT INTO unified_quote_drafts(id,created_at,updated_at,"
            "created_by,revision,payload_json) VALUES(?,?,?,?,?,?)",
            (draft["id"],"2026-11-03","2026-11-03","fictional-director",
             1,json.dumps({k:v for k,v in draft.items() if k not in ("id","revision")})),
        )
    incomplete=fake_price()
    incomplete["complete_price"]=False
    incomplete["priced_count"]=0
    incomplete["lines"][0]["priced"]=False
    incomplete["lines"][0]["rrp_source"]="sage_unpriced_exact_sku"
    monkeypatch.setattr(issue,"_price",
        lambda draft:(incomplete,{"pricing":"a"*64,"catalog":"b"*64,"configs":"c"*64}))
    from tests.test_quote_customer_issuance import approval
    with pytest.raises(HTTPException) as err:
        issue.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==409
