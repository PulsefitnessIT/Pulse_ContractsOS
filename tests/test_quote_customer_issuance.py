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
        serial_exception_reason="The second fictional machine serial is unreadable; site to verify on installation.",
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
    monkeypatch.setattr(quote_drafts,"connect",db)
    from app import quote_commercial_setup
    monkeypatch.setattr(quote_commercial_setup, "connect", db)
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


def test_coordinator_can_check_release_readiness_but_cannot_authorise_pdf(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Coordinator")
    # Price functions are stubbed here; only the access boundary is under test.
    result=issues.customer_quote_readiness(fake_draft()["id"])
    assert result["draft_id"]==fake_draft()["id"]
    assert result["pricing_complete"] is True
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert err.value.status_code==403


def test_coordinator_can_download_approved_pdf_without_reissuing(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    issued=issues.issue_customer_quotation(fake_draft()["id"],approval())
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Coordinator")
    archive=issues.issued_quotation_history(fake_draft()["id"])
    assert archive["items"][0]["quote_no"]==issued["quote_no"]
    received=issues.download_issued_customer_quote(issued["quote_no"])
    assert received.body.startswith(b"%PDF-")
    assert hashlib.sha256(received.body).hexdigest()==issued["pdf_sha256"]


def test_viewer_cannot_access_commercial_quote_readiness_or_pdf(tmp_path,monkeypatch):
    setup_database(tmp_path,monkeypatch)
    issued=issues.issue_customer_quotation(fake_draft()["id"],approval())
    monkeypatch.setattr(issues.pilot_access,"current_role",lambda:"Viewer")
    for action in [
        lambda:issues.customer_quote_readiness(fake_draft()["id"]),
        lambda:issues.issued_quotation_history(fake_draft()["id"]),
        lambda:issues.download_issued_customer_quote(issued["quote_no"]),
    ]:
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code==403



def test_business_confirmed_sage_master_price_difference_is_informational_and_archived(tmp_path,monkeypatch):
    db=setup_database(tmp_path,monkeypatch)
    changed=fake_price()
    changed["lines"][0]["source_price_comparison"]={
        "selected_equipment_price_gbp":9000.0,
        "sage_sales_price_gbp":7000.0,
        "percentage_difference":-22.22,
        "requires_explicit_ack":False,
        "comparison_for_information_only":True,
        "not_a_new_or_approved_tariff":True,
    }
    monkeypatch.setattr(
        issues,"_price",
        lambda draft:(changed,{"pricing":"a"*64,"catalog":"b"*64,"configs":"c"*64})
    )
    ready=issues.customer_quote_readiness(fake_draft()["id"])
    assert ready["price_source_variances_requiring_ack"]==0
    assert ready["price_source_comparisons_available"]==1
    assert "separate approval requirement" in ready["source_price_policy"]
    # The normal Admin quote sign-off remains mandatory; the made-up 5%
    # threshold must never become an extra manager checkbox.
    issued=issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert issued["issued"] is True
    with sqlite3.connect(db) as conn:
        raw=conn.execute(
            "SELECT snapshot_json FROM unified_customer_quotes WHERE quote_no=?",
            (issued["quote_no"],)
        ).fetchone()[0]
    frozen=json.loads(raw)
    assert frozen["source_price_comparisons_informational"] is True
    assert frozen["source_price_comparison_lines"]==[1]
    assert frozen["priced"]["lines"][0]["source_price_comparison"]["sage_sales_price_gbp"]==7000.0


def test_stale_sage_reference_does_not_block_selected_current_master_price():
    record=fake_draft()
    price=fake_price()
    price["lines"][0]["rrp_source"]="august_2026_master_list_price"
    price["lines"][0]["sage_reference"]={"review_overdue":True}
    assert not any("Sage" in error for error in issues._errors(record,price))
    price["lines"][0]["rrp_source"]="sage_exact_sku_price"
    assert any("Sage" in error for error in issues._errors(record,price))



def test_missing_machine_serials_require_a_specific_manager_reason_and_archive_it(tmp_path, monkeypatch):
    path=setup_database(tmp_path,monkeypatch)
    readiness=issues.customer_quote_readiness(fake_draft()["id"])
    assert readiness["serials_unconfirmed"]==1
    assert readiness["serials_unconfirmed_lines"]==[{"line":1,"unconfirmed_units":1}]
    assert readiness["serial_exception_reason_needed"] is True
    blank=approval().model_copy(update={"serial_exception_reason":""})
    with pytest.raises(HTTPException) as error:
        issues.issue_customer_quotation(fake_draft()["id"],blank)
    assert error.value.status_code==422
    assert "serial" in str(error.value.detail).lower()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM unified_customer_quotes").fetchone()[0]==0
    issued=issues.issue_customer_quotation(fake_draft()["id"],approval())
    assert issued["issued"] is True
    with sqlite3.connect(path) as db:
        frozen=json.loads(db.execute(
            "SELECT snapshot_json FROM unified_customer_quotes WHERE quote_no=?",
            (issued["quote_no"],)
        ).fetchone()[0])
    assert frozen["unconfirmed_serial_count"]==1
    assert frozen["serial_exception_reason"].startswith("The second fictional machine serial")


def test_all_individual_serials_confirmed_needs_no_manager_exception(tmp_path,monkeypatch):
    fully= fake_draft()
    fully["equipment"]=[
        {**fully["equipment"][0],"quantity":1,"serial":"SERIAL-ONE"},
        {**fully["equipment"][0],"quantity":1,"serial":"SERIAL-TWO"},
    ]
    setup_database(tmp_path,monkeypatch,draft=fully)
    fully_priced=fake_price()
    first={**fully_priced["lines"][0], "quantity":1,"annual":112.50,
        "minimum_annual":93.75}
    second={**first,"line":2,"item_code":"DEMO-TREAD"}
    fully_priced["lines"]=[first,second]
    fully_priced["line_count"]=2
    fully_priced["priced_count"]=2
    monkeypatch.setattr(issues,"_price",lambda data:(
        fully_priced,{"pricing":"a"*64,"catalog":"b"*64,"configs":"c"*64}
    ))
    ready=issues.customer_quote_readiness(fully["id"])
    assert ready["serials_unconfirmed"]==0
    assert ready["serial_exception_reason_needed"] is False
    approval_without_reason=approval().model_copy(update={"serial_exception_reason":""})
    issued=issues.issue_customer_quotation(fully["id"],approval_without_reason)
    assert issued["issued"] is True



def test_customer_issue_rejects_price_engine_omitting_saved_machine(tmp_path,monkeypatch):
    extra=fake_draft()
    extra["equipment"].append({
        "item_code":"DEMO-SECOND","description":"Fictional second machine",
        "quantity":1,"serial":"OTHER-SERIAL","cover_start":"",
    })
    path=setup_database(tmp_path,monkeypatch,draft=extra)
    # The synthetic pricing source reports complete for only its first line.
    # It must never be allowed to issue a customer PDF for two saved lines.
    preview=fake_price()
    assert preview["complete_price"] is True
    assert any("every saved equipment line" in text for text in issues._errors(extra,preview))
    with pytest.raises(HTTPException) as err:
        issues.issue_customer_quotation(extra["id"],approval())
    assert err.value.status_code==409
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM unified_customer_quotes").fetchone()[0]==0


def test_customer_issue_rejects_swapped_quantity_sku_or_draft_revision():
    original=fake_draft()
    price=fake_price()
    for damaged in (
        {**price,"lines":[{**price["lines"][0],"quantity":1}]},
        {**price,"lines":[{**price["lines"][0],"item_code":"OTHER-SKU"}]},
        {**price,"revision":5},
        {**price,"tier":"Silver"},
        {**price,"draft_id":"e"*32},
    ):
        assert any(
            "snapshot" in text.lower() or "equipment line" in text.lower()
            for text in issues._errors(original,damaged)
        )


def test_repeated_or_placeholder_serials_cannot_verify_multiple_machines():
    """Serials are unique per physical unit, not merely non-empty text."""
    draft = {"equipment": [
        {"quantity": 1, "serial": "ABC-123"},
        {"quantity": 1, "serial": " abc-123 "},
        {"quantity": 1, "serial": "N/A"},
        {"quantity": 1, "serial": "TBC"},
        {"quantity": 2, "serial": "UNIQUE-456"},
        {"quantity": 1, "serial": "OTHER-789"},
    ]}
    result = issues._unconfirmed_serials(draft)
    assert result["total"] == 4
    assert result["lines"] == [
        {"line": 2, "unconfirmed_units": 1},
        {"line": 3, "unconfirmed_units": 1},
        {"line": 4, "unconfirmed_units": 1},
        {"line": 5, "unconfirmed_units": 1},
    ]


def test_individual_unique_serials_remain_verified():
    draft = {"equipment": [
        {"quantity": 1, "serial": "S-001"},
        {"quantity": 1, "serial": "S-002"},
        {"quantity": 1, "serial": "S-003"},
    ]}
    assert issues._unconfirmed_serials(draft) == {"total": 0, "lines": []}
