"""Customer-ready quotation requires a real approved price/terms gate and archive.

Synthetic data ONLY. These tests do not authorise a Pulse commercial tariff.
"""
import datetime as dt
import hashlib
import io
import json
import sqlite3

import fitz
import pytest
from fastapi import HTTPException

from app import quote_customer_issuance as issues
from app import quote_customer_pdf as pdf
from app import quote_drafts


def fake_issuer():
    return {
        "legal_name": "Pulse Fitness Ltd — FICTIONAL TEST DETAILS",
        "registered_address": "123 Fictional Road, Test Town, EX1 1AA",
        "contact_email": "example@fictional.invalid",
        "company_number": "12345678",
        "telephone": "00000 000 000",
        "vat_number": "GB TEST ONLY",
    }


def fake_terms():
    terms = fitz.open()
    page = terms.new_page()
    page.insert_text((55, 70), "FICTIONAL APPROVED MAINTENANCE TERMS (TEST ONLY)")
    data = terms.tobytes()
    terms.close()
    return data


def fake_draft():
    return {
        "id": "c"*32, "revision": 1,
        "customer": "Fictional Leisure Customer Ltd",
        "site": "Fictional Active Centre", "contact": "Example Contact",
        "tier": "Gold", "term_years": 2, "discount_percent": 0,
        "contract_start": "", "contract_end": "",
        "equipment": [{
            "item_code": "DEMO-TREAD", "description": "Example Pulse Treadmill",
            "quantity": 2, "serial": "SERIAL-ONE", "cover_start": "",
        }],
    }


def fake_price():
    return {
        "draft_id": "c"*32, "revision": 1,
        "tier": "Gold", "term_years": 2,
        "complete_price": True, "priced_count": 1, "line_count": 1,
        "annual_partial": 225.00, "term_partial": 450.00,
        "rrp_master": {"original_sha256": "d"*64, "staged_sha256": "e"*64},
        "sage_sha256": "f"*64,
        "staged": {"enabled": False, "issues": []},
        "lines": [{
            "line": 1, "item_code": "DEMO-TREAD", "sku": "DEMO-TREAD",
            "description": "Example Pulse Treadmill", "quantity": 2,
            "rrp": 3000, "annual": 225, "unit_annual": 112.50,
            "minimum_annual": 187.50, "priced": True,
            "source_eligibility": "Yes", "rate_status": "Active",
            "rrp_source": "august_2026_master_list_price",
            "coverage_review": [
                "August 2026 source List Price used; commercial maintenance tariff approval remains separate."
            ],
            "review_required": True,
        }],
    }


def approval(draft=None):
    d = draft or fake_draft()
    return issues.QuoteApproval(
        expected_revision=d["revision"],
        valid_until=(dt.date.today()+dt.timedelta(days=45)).isoformat(),
        commercial_approval_ref="PF-COMMERCIAL-APPROVAL-2026-TEST",
        confirm_customer_and_site=True,
        confirm_equipment_and_serials=True,
        confirm_package_price_and_discount=True,
        confirm_maintenance_scope_and_terms=True,
        confirm_vat_basis=True,
    )


def setup_database(tmp_path, monkeypatch, draft=None):
    path = tmp_path / "customer-quotations.sqlite3"
    def db():
        con = sqlite3.connect(path,timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con
    with db() as conn:
        quote_drafts._init(conn)
        d = draft or fake_draft()
        conn.execute(
            "INSERT INTO unified_quote_drafts (id,created_at,updated_at,created_by,"
            "revision,payload_json) VALUES(?,?,?,?,?,?)",
            (d["id"], "2026-11-03", "2026-11-03", "demo",
             d["revision"], json.dumps({
                 k:v for k,v in d.items() if k not in ("id","revision")
             })),
        )
    monkeypatch.setattr(issues,"connect",db)
    monkeypatch.setattr(issues.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(issues.pilot_access,"actor",lambda fallback="":"fictional-admin")
    terms = fake_terms()
    monkeypatch.setattr(issues,"_terms",lambda:(terms,hashlib.sha256(terms).hexdigest()))
    monkeypatch.setattr(issues,"_issuer",lambda:(fake_issuer(),"e"*64))
    monkeypatch.setattr(issues,"_price",lambda data:(fake_price(),{"pricing":"a"*64,"catalog":"b"*64,"configs":"c"*64}))
    monkeypatch.setenv(issues.ISSUE_ENV,"1")
    monkeypatch.setenv(issues.APPROVAL_SOURCE_ENV,"a"*64)
    return path


def test_branded_draft_pdf_contains_correct_customer_money_and_not_for_customer():
    result = pdf.render_quote_pdf(
        draft=fake_draft(), pricing=fake_price(),
        quote_no="INTERNAL-DEMO", prepared_date="2026-11-03",
        valid_until="NOT APPROVED", approval_ref="", approved_by="",
        internal_draft=True,
    )
    with fitz.open(stream=result,filetype="pdf") as report:
        assert report.page_count >= 1
        text=" ".join(page.get_text() for page in report)
    assert "PULSE FITNESS" in text
    assert "Fictional Leisure Customer" in text
    assert "DEMO-TREAD" in text
    assert "GBP 225.00" in text
    assert "GBP 450.00" in text
    assert "DRAFT - NOT FOR CUSTOMER" in text
    assert result.startswith(b"%PDF-")


def test_customer_pdf_includes_actual_approved_terms_unmodified():
    terms=fake_terms()
    out=pdf.render_quote_pdf(
        draft=fake_draft(), pricing=fake_price(),
        quote_no="PFQ-2026-000001", prepared_date="2026-11-03",
        valid_until="2026-12-18",
        approval_ref="PF-COMMERCIAL-APPROVAL-TEST",
        approved_by="fictional-admin", terms_pdf=terms, issuer=fake_issuer(),
    )
    with fitz.open(stream=out,filetype="pdf") as document:
        assert document.page_count >= 2
        customer=" ".join(page.get_text() for page in document)
    assert "FICTIONAL APPROVED MAINTENANCE TERMS" in customer
    assert "PFQ-2026-000001" in customer
    assert "DRAFT - NOT FOR CUSTOMER" not in customer
    assert "GBP 450.00" in customer
    assert "SUPPLIER DETAILS" in customer
    assert "123 Fictional Road" in customer


def test_issue_is_admin_approved_immutable_and_download_integrity_checked(tmp_path,monkeypatch):
    db = setup_database(tmp_path,monkeypatch)
    result=issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert result["quote_no"].startswith("PFQ-")
    assert result["issued"] is True
    assert result["annual_gbp"] == 225
    assert result["term_gbp"] == 450
    assert result["customer_email_sent"] is False
    assert result["contract_activated"] is False
    with sqlite3.connect(db) as conn:
        row=conn.execute(
            "SELECT pdf_sha256,snapshot_sha256,quote_no,issued_by "
            "FROM unified_customer_quotes"
        ).fetchone()
    assert row[0]==result["pdf_sha256"]
    assert row[2]==result["quote_no"]
    assert row[3]=="fictional-admin"
    document=issues.download_issued_customer_quote(result["quote_no"])
    assert document.media_type=="application/pdf"
    assert hashlib.sha256(document.body).hexdigest()==result["pdf_sha256"]
    assert b"%PDF-" in document.body[:20]
    history=issues.issued_quotation_history(fake_draft()["id"])
    assert len(history["items"])==1
    assert history["items"][0]["commercial_approval_ref"]=="PF-COMMERCIAL-APPROVAL-2026-TEST"
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==409
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM unified_customer_quotes").fetchone()[0]==1


def test_archived_pdf_tampering_blocks_distribution(tmp_path,monkeypatch):
    db=setup_database(tmp_path,monkeypatch)
    record=issues.issue_customer_quotation(fake_draft()["id"],approval())
    with sqlite3.connect(db) as con:
        con.execute("UPDATE unified_customer_quotes SET pdf=? WHERE quote_no=?",
                    (b"%PDF-FAKE-EDIT%%EOF",record["quote_no"]))
    with pytest.raises(HTTPException) as err:
        issues.download_issued_customer_quote(record["quote_no"])
    assert err.value.status_code==409


def test_no_issue_without_signed_off_tariff_fingerprint(tmp_path,monkeypatch):
    db=setup_database(tmp_path,monkeypatch)
    monkeypatch.setenv(issues.APPROVAL_SOURCE_ENV,"9"*64)
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==409
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM unified_customer_quotes").fetchone()[0]==0


def test_no_issue_without_it_activation(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    monkeypatch.setenv(issues.ISSUE_ENV,"0")
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==503


@pytest.mark.parametrize("failing",[
    "confirm_customer_and_site", "confirm_equipment_and_serials",
    "confirm_package_price_and_discount", "confirm_maintenance_scope_and_terms",
    "confirm_vat_basis",
])
def test_required_attestation_cannot_be_skipped(tmp_path,monkeypatch,failing):
    setup_database(tmp_path,monkeypatch)
    values=approval().model_dump()
    values[failing]=False
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],issues.QuoteApproval(**values))
    assert err.value.status_code==422


def test_source_ambiguity_and_unverified_console_blocks_quote(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    changed=fake_price()
    changed["lines"][0]["coverage_review"].append(
        "Console configuration is unverified in the source rules."
    )
    monkeypatch.setattr(issues,"_price",lambda d:(changed,{"pricing":"a"*64}))
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==409


def test_provisional_tariff_is_not_approved_by_default_and_age_expiry_checked(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    flags=issues._quote_flags({"pricing":"a"*64},[],True)
    assert flags["approved_tariff_fingerprint_matches"] is True
    monkeypatch.delenv(issues.APPROVAL_SOURCE_ENV)
    flags=issues._quote_flags({"pricing":"a"*64},[],True)
    assert flags["approved_tariff_fingerprint_matches"] is False
    bad=approval().model_dump()
    bad["valid_until"]=(dt.date.today()+dt.timedelta(days=200)).isoformat()
    with pytest.raises(HTTPException) as err:
        issues._approval(issues.QuoteApproval(**bad),1)
    assert err.value.status_code==422


def test_only_admin_in_authenticated_pilot_can_issue(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Coordinator")
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==403
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(issues.pilot_access,"PILOT_MODE",False)
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==403


def test_source_changed_during_pdf_creation_rolls_back_fully(tmp_path,monkeypatch):
    db=setup_database(tmp_path,monkeypatch)
    steps={"n":0}
    def price_state(draft):
        steps["n"]+=1
        quote=fake_price()
        if steps["n"]==2:
            quote["sage_sha256"]="9"*64
        return quote,{"pricing":"a"*64,"catalog":"b"*64,"configs":"c"*64}
    monkeypatch.setattr(issues,"_price",price_state)
    with pytest.raises(HTTPException) as exc:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert exc.value.status_code==409
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM unified_customer_quotes").fetchone()[0]==0


def test_verified_issuer_source_requires_real_file_and_matching_digest(tmp_path,monkeypatch):
    values=fake_issuer()
    path=tmp_path/"verified-issuer.json"
    content=json.dumps(values).encode("utf-8")
    path.write_bytes(content)
    monkeypatch.setenv(issues.ISSUER_FILE_ENV,str(path))
    monkeypatch.setenv(issues.ISSUER_SHA_ENV,hashlib.sha256(content).hexdigest())
    company,digest=issues._issuer()
    assert company["company_number"]=="12345678"
    assert digest==hashlib.sha256(content).hexdigest()
    path.write_bytes(b'{"legal_name":"unverified changed company"}')
    with pytest.raises(HTTPException) as exc:
        issues._issuer()
    assert exc.value.status_code==503


def test_verified_customer_terms_require_exact_pdf_hash(tmp_path,monkeypatch):
    source=fake_terms()
    path=tmp_path/"approved-terms.pdf"
    path.write_bytes(source)
    monkeypatch.setenv(issues.TERMS_FILE_ENV,str(path))
    monkeypatch.setenv(issues.TERMS_SHA_ENV,hashlib.sha256(source).hexdigest())
    actual,digest=issues._terms()
    assert actual==source
    assert digest==hashlib.sha256(source).hexdigest()
    path.write_bytes(source+b"\nINVALID-APPENDIX")
    with pytest.raises(HTTPException) as exc:
        issues._terms()
    assert exc.value.status_code==503
