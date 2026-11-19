"""Pulse-branded printable maintenance agreement REVIEW COPY from a contract.

Only values actually recorded against the selected customer are used.
A live agreement requires Pulse's separately approved original legal template,
verified covered equipment, correct legal contracting customer and signatures.
This route deliberately does not make those contractual assertions.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation

import fitz
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .quote_quick_draft import _staff
from .store import connect

router = APIRouter(prefix="/api/contracts", tags=["Printable contract review"])


def _clean(value, length=160):
    if value is None:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()[:length]


def _uk_date(value):
    text = _clean(value, 30)
    if not text:
        return "To confirm"
    try:
        if re.fullmatch(r"\d{5}", text) and 20000 <= int(text) <= 80000:
            date = dt.date(1899, 12, 30) + dt.timedelta(days=int(text))
            return date.strftime("%d/%m/%Y")
        if re.match(r"^\d{4}-\d\d-\d\d", text):
            return dt.date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
        if re.fullmatch(r"\d\d/\d\d/\d{4}", text):
            day, month, year = map(int, text.split("/"))
            dt.date(year, month, day)
            return text
    except (ValueError, OverflowError):
        pass
    return "To confirm"


def _amount(value):
    text = _clean(value, 60).replace("£", "").replace(",", "")
    if not text:
        return "Not recorded"
    try:
        amount = Decimal(text)
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
        return f"GBP {amount:,.2f} (recorded; verify ex-VAT basis)"
    except (InvalidOperation, ValueError):
        return "Needs checking"


NAVY = (27/255, 28/255, 29/255)
BLUE = (25/255, 205/255, 255/255)
MUTED = (81/255, 99/255, 108/255)
PALE = (241/255, 250/255, 253/255)
PAGE = fitz.paper_rect("a4")
PAGE_W, PAGE_H = PAGE.width, PAGE.height


def _text(page, xy, value, size=10, color=NAVY, font="helv", max_chars=135):
    page.insert_text(xy, _clean(value, max_chars), fontsize=size, color=color, fontname=font)


def _section(page, y, title):
    page.draw_rect(fitz.Rect(40, y-15, PAGE_W-40, y+14), color=None, fill=PALE)
    _text(page, (50, y+3), title, 12, NAVY, "hebo")
    return y+39


def _two_col(page, y, caption, value, *, lines=1):
    _text(page, (47, y), caption, 9, MUTED, "hebo")
    line=str(value)
    for k in range(lines):
        slice_text=line[k*76:(k+1)*76]
        if slice_text:
            _text(page, (205, y+k*17), slice_text, 10, NAVY, max_chars=76)
    page.draw_line((47, y+8+(lines-1)*17), (PAGE_W-47, y+8+(lines-1)*17), color=(.9,.92,.93), width=.5)
    return y+30+(lines-1)*17


def _page(doc, title, contract_ref, number):
    page=doc.new_page(width=PAGE_W, height=PAGE_H)
    page.draw_rect(fitz.Rect(0,0,PAGE_W,82), color=None, fill=NAVY)
    page.draw_rect(fitz.Rect(0,82,PAGE_W,87), color=None, fill=BLUE)
    _text(page,(42,32),"PULSE FITNESS",21,(1,1,1),"hebo")
    _text(page,(44,56),"SERVICE & AFTERSALES  /  MAINTENANCE",10,BLUE,"hebo")
    _text(page,(42,119),title,19,NAVY,"hebo")
    _text(page,(42,141),"DRAFT FOR INTERNAL REVIEW - NOT AN ISSUED OR SIGNED AGREEMENT",9,(.72,.20,.16),"hebo")
    _text(page,(42,PAGE_H-28),f"Review copy  |  {contract_ref[:45]}  |  Page {number}",8,MUTED)
    page.draw_line((42,PAGE_H-42),(PAGE_W-42,PAGE_H-42),color=BLUE,width=1)
    return page


def generate_review_pdf(fields: dict, equipment: list[dict]) -> bytes:
    site=_clean(fields.get("Customer / site"),220)
    if not site:
        raise HTTPException(422, "Customer / site must be recorded before printing.")
    ref=_clean(fields.get("Contract number"),100) or "Reference to confirm"
    document=fitz.open()
    page=_page(document,"Maintenance agreement - record summary",ref,1)
    y=_section(page,182,"Customer and agreement details")
    for title,value,lines in (
        ("Customer / site",site,2),
        ("Agreement reference",ref,1),
        ("Recorded cover",_clean(fields.get("Contract / warranty type")) or "To confirm",2),
        ("Cover starts",_uk_date(fields.get("Start date")),1),
        ("Cover expires",_uk_date(fields.get("Expiry date")),1),
        ("Services per year",_clean(fields.get("Services per year")) or "To confirm",1),
        ("Payment frequency",_clean(fields.get("Payment frequency")) or "To confirm",1),
        ("Recorded contract amount",_amount(fields.get("Contract amount (£)")),2),
    ):
        y=_two_col(page,y,title,value,lines=lines)

    y=_section(page,y+5,"Equipment covered")
    if equipment:
        _text(page,(48,y),f"{len(equipment)} equipment records linked to this customer",10,NAVY)
        _text(page,(48,y+22),"See equipment schedule on the following page(s).",9,MUTED)
    else:
        _text(page,(48,y),"No equipment schedule is currently linked to this agreement.",10,NAVY)
        _text(page,(48,y+22),"Confirm all machines and serial numbers before customer issue.",9,MUTED)

    y2=y+72
    _text(page,(45,y2),"IMPORTANT - COMMERCIAL AND LEGAL REVIEW",10,NAVY,"hebo")
    for index,line in enumerate((
        "This review copy reproduces recorded contract information only.",
        "Confirm the legal customer, exact machines, cover, prices and exclusions.",
        "Use Pulse's approved maintenance agreement template and obtain signatures",
        "before representing any document as a valid customer agreement.",
    )):
        _text(page,(48,y2+20+index*16),line,9,MUTED)

    # Equipment schedule is source-linked to the selected record; no inferred
    # service eligibility, warranty or excluded belt/deck coverage is added.
    if equipment:
        for offset in range(0,len(equipment),15):
            sub=equipment[offset:offset+15]
            pg=_page(document,"Schedule of recorded equipment",ref,document.page_count+1)
            _text(pg,(45,170),"ITEM CODE",9,MUTED,"hebo")
            _text(pg,(150,170),"EQUIPMENT DESCRIPTION",9,MUTED,"hebo")
            _text(pg,(365,170),"QTY",9,MUTED,"hebo")
            _text(pg,(407,170),"SERIAL NUMBER",9,MUTED,"hebo")
            for j,row in enumerate(sub):
                yy=198+j*37
                if j%2==0:
                    pg.draw_rect(fitz.Rect(42,yy-18,PAGE_W-42,yy+18),color=None,fill=PALE)
                _text(pg,(47,yy),row.get("sku") or "To confirm",9,NAVY,max_chars=18)
                _text(pg,(150,yy),row.get("name") or row.get("description") or row.get("model") or "Not recorded",9,NAVY,max_chars=36)
                _text(pg,(366,yy),row.get("quantity") or 1,9,NAVY)
                _text(pg,(407,yy),row.get("serial_number") or "To confirm",9,NAVY,max_chars=31)
            _text(pg,(48,785),"Confirm serials and approved maintenance scope against the signed agreement.",9,MUTED)

    raw=document.tobytes(garbage=4,deflate=True)
    document.close()
    return raw


@router.get("/{cid}/agreement/preview.pdf")
def download_contract_agreement_preview(cid: int):
    _staff()  # named Coordinator/Admin only, never a viewer or unauthenticated browser
    with connect() as db:
        contract=db.execute(
            "SELECT fields FROM contracts WHERE id=?", (cid,)
        ).fetchone()
        if not contract:
            raise HTTPException(404,"Contract not found.")
        fields=json.loads(contract["fields"])
        equipment=[dict(row) for row in db.execute(
            """SELECT e.sku, e.serial_number, e.quantity,
                coalesce(c.name, c.model, c.description, '') AS name
            FROM equipment AS e LEFT JOIN catalogue AS c ON c.sku=e.sku
            WHERE e.contract_id=? ORDER BY e.id""",(cid,)
        )]
    raw=generate_review_pdf(fields,equipment)
    return Response(
        content=raw,media_type="application/pdf",
        headers={
            "Content-Disposition":f'inline; filename="Pulse_Maintenance_Agreement_Review_{cid}.pdf"',
            "Cache-Control":"private, no-store",
            "X-Content-Type-Options":"nosniff",
        },
    )
