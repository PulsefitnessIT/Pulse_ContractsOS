"""Render actual branded internal SmartQuote PDF without customer approval."""
from decimal import Decimal
import fitz
import pytest
from fastapi import HTTPException

from app import quote_quick_draft as quick
from app.quote_quick_pdf import render_quick_internal_pdf


@pytest.fixture
def quote():
    book={"revision":21,"sha256":"c"*64,"rows":{
        "ROWER-A":{
            "description":"Fictional Rower with Console",
            "group":"Cardiovascular Equipment",
            "price_pence":230000,"status":"REFERENCE","origin":"Master"
        }
    }}
    draft=quick.QuickDraft(
        customer="Fictional Council",site="Test Leisure Centre",
        package="Gold",term_years=3,
        notes="PPM scope for internal manager review only.",
        expected_price_book_sha256="c"*64,
        lines=[quick.QuickDraftLine(
            sku="ROWER-A",quantity=2,
            serials="DEMO-100",
            annual_rate_percent=Decimal("5")
        )],
    )
    return book,draft


def test_branded_internal_quote_pdf_renders_exact_backend_values(quote):
    book,draft=quote
    data=quick.calculate(draft,book)
    pdf=render_quick_internal_pdf(draft,data)
    assert pdf.startswith(b"%PDF")
    with fitz.open(stream=pdf,filetype="pdf") as document:
        all_text=" ".join(page.get_text() for page in document)
        assert document.page_count>=1
        assert "Fictional Council" in all_text
        assert "Test Leisure Centre" in all_text
        assert "ROWER-A" in all_text
        assert "ANNUAL MAINTENANCE" in all_text
        assert "GBP 230.00" in all_text
        assert "GBP 690.00" in all_text
        assert "INTERNAL DRAFT ONLY" in all_text
        assert "NOT AUTHORISED FOR CUSTOMER ISSUE" in all_text
        assert document[0].get_xobjects()  # supplied Pulse signature vector


def test_pdf_export_route_denies_old_price_or_missing_staff(quote,monkeypatch):
    book,draft=quote
    monkeypatch.setattr(quick, "_book", lambda: book)
    monkeypatch.setattr(quick.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(quick.pilot_access,"current_role",lambda:"Coordinator")
    monkeypatch.setattr(quick.pilot_access,"actor",lambda default="":"fictional-coordinator")
    response=quick.quick_internal_pdf(draft)
    assert response.media_type=="application/pdf"
    assert response.headers["Cache-Control"]=="private, no-store"
    assert response.body.startswith(b"%PDF")
    book["sha256"]="d"*64
    with pytest.raises(HTTPException) as exc:
        quick.quick_internal_pdf(draft)
    assert exc.value.status_code==409
    monkeypatch.setattr(quick.pilot_access,"current_role",lambda:"Viewer")
    with pytest.raises(HTTPException) as exc:
        quick.quick_internal_pdf(draft)
    assert exc.value.status_code==403


def test_internal_pdf_refuses_incomplete_or_unpriced_equipment(quote,monkeypatch):
    book,draft=quote
    monkeypatch.setattr(quick,"_book",lambda:book)
    monkeypatch.setattr(quick.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(quick.pilot_access,"current_role",lambda:"Coordinator")
    monkeypatch.setattr(quick.pilot_access,"actor",lambda default="":"fictional-coordinator")
    draft.lines[0].sku="PART-UNMATCHED"
    with pytest.raises(HTTPException) as exc:
        quick.quick_internal_pdf(draft)
    assert exc.value.status_code==409


def test_multi_page_pdf_keeps_draft_watermark_on_all_pages(quote):
    book,draft=quote
    draft.lines=[quick.QuickDraftLine(
        sku="ROWER-A",quantity=1,
        annual_rate_percent=Decimal("5"),serials=""
    ) for _ in range(42)]
    result=quick.calculate(draft,book)
    pdf=render_quick_internal_pdf(draft,result)
    with fitz.open(stream=pdf,filetype="pdf") as document:
        assert document.page_count>2
        for page in document:
            text=page.get_text()
            assert "INTERNAL DRAFT ONLY" in text
            assert "NOT AN APPROVED CUSTOMER OFFER" in text


def test_internal_pdf_preserves_every_serial_on_multi_unit_equipment(quote):
    book,draft=quote
    serials=[f"EXAMPLE-{i:05d}" for i in range(1,13)]
    draft.lines[0].quantity=12
    draft.lines[0].serials=", ".join(serials)
    priced=quick.calculate(draft,book)
    pdf=render_quick_internal_pdf(draft,priced)
    with fitz.open(stream=pdf,filetype="pdf") as document:
        full=" ".join(page.get_text() for page in document)
        for serial in serials:
            assert serial in full
        assert "INTERNAL DRAFT ONLY" in full
