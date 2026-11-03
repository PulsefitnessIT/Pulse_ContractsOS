"""Frozen, branded Pulse Fitness customer quote PDF rendering.

Pure function: generates bytes, never saves or issues itself. The caller must
verify tariff approval, sources, commercial sign-off and attached real terms.
No sales/maintenance promises or contractual exclusions are invented here.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from decimal import Decimal
from typing import Mapping

import fitz

NAVY = (0.055, 0.12, 0.21)
INK = (0.11, 0.18, 0.28)
MUTED = (0.36, 0.43, 0.50)
ACCENT = (0.13, 0.41, 0.68)
PALE = (0.94, 0.96, 0.98)
WHITE = (1, 1, 1)
W, H = fitz.paper_size("a4")
MARGIN = 45
RIGHT = W - MARGIN


def _safe(value, length=350):
    s = str(value or "").strip()[:length]
    return "".join(c if 32 <= ord(c) < 127 else
                   ("-" if c in ("\u2013", "\u2014", "\u2212") else
                    " " if c in ("\u00a0", "\t", "\n", "\r") else
                    "?" if ord(c) > 126 else " ")
                   for c in s)


def _money(amount):
    return f"GBP {Decimal(str(amount)):,.2f}"


def _wrap(value, width, size=9, font="helv", maxlines=None):
    text = _safe(value, 800)
    words = text.split()
    lines, current = [], ""
    for word in words:
        proposal = (current + " " + word).strip()
        if fitz.get_text_length(proposal, fontname=font, fontsize=size) <= width:
            current = proposal
            continue
        if current:
            lines.append(current)
            current = ""
        while word and fitz.get_text_length(word, fontname=font, fontsize=size) > width:
            prefix = ""
            for character in word:
                if fitz.get_text_length(prefix + character, fontname=font, fontsize=size) > width:
                    break
                prefix += character
            if not prefix:  # Narrow column safeguard
                prefix = word[0]
            lines.append(prefix)
            word = word[len(prefix):]
        current = word
    if current:
        lines.append(current)
    if not lines:
        lines = [""]
    if maxlines is not None and len(lines) > maxlines:
        lines = lines[:maxlines]
        lines[-1] = (lines[-1][:max(0, len(lines[-1]) - 3)] + "...")
    return lines


def _txt(page, pos, text, size=9, color=INK, font="helv"):
    page.insert_text(pos, _safe(text, 400), fontsize=size, fontname=font,
                     color=color, overlay=True)


def _rect(page, left, top, right, bottom, fill, stroke=None):
    page.draw_rect(fitz.Rect(left, top, right, bottom),
                   color=stroke, fill=fill, overlay=True)


def _page(doc, quote_no, draft=False):
    page = doc.new_page(width=W, height=H)
    _rect(page, 0, 0, W, 92, NAVY)
    _rect(page, 0, 92, W, 96, ACCENT)
    _txt(page, (MARGIN, 37), "PULSE FITNESS", 19, WHITE, "hebo")
    _txt(page, (MARGIN, 59), "MAINTENANCE SERVICES", 9, (0.75, 0.85, 0.95))
    _txt(page, (W-212, 39), "EQUIPMENT MAINTENANCE QUOTATION",
         8.6, WHITE, "hebo")
    _txt(page, (W-212, 60), quote_no, 10, WHITE, "hebo")
    _rect(page, MARGIN, H-44, RIGHT, H-43, (0.83, 0.87, 0.91))
    _txt(page, (MARGIN, H-29), "Pulse Fitness | Service & Aftersales",
         8, MUTED)
    _txt(page, (RIGHT-161, H-29),
         "DRAFT - NOT FOR CUSTOMER" if draft else "Customer quotation",
         8, MUTED)
    if draft:
        _rect(page, MARGIN, 106, RIGHT, 130, (1, 0.90, 0.80))
        _txt(page, (MARGIN+8, 122),
             "INTERNAL DRAFT ONLY - NOT AN APPROVED CUSTOMER OFFER",
             9, (0.55, 0.24, 0.05), "hebo")
    return page


def _row(page, top, label, value, width=190):
    _txt(page, (MARGIN+12, top+14), label, 8.5, MUTED)
    _txt(page, (MARGIN+width, top+14), value, 9.5, INK, "hebo")


def render_quote_pdf(*, draft, pricing, quote_no, prepared_date,
                     valid_until, approval_ref, approved_by,
                     terms_pdf=None, issuer=None, internal_draft=False):
    """Produce immutable PDF bytes for complete, source-priced quote input.

    \`pricing\` is the server-generated V10 snapshot, not client-provided money.
    Actual approved terms are appended unchanged when issuing to a customer.
    """
    if not pricing.get("complete_price") or not pricing.get("lines"):
        raise ValueError("Cannot render an incomplete maintenance price.")
    if (not internal_draft and
            (not terms_pdf or not approval_ref or not approved_by or not issuer)):
        raise ValueError("Customer PDF needs real approved terms and sign-off.")
    doc = fitz.open()
    page = _page(doc, quote_no, internal_draft)
    y = 153 if internal_draft else 137

    _txt(page, (MARGIN, y), "PREPARED FOR", 9, ACCENT, "hebo")
    y += 23
    for line in _wrap(draft["customer"], 490, 16, "hebo", 2):
        _txt(page, (MARGIN, y), line, 16, NAVY, "hebo")
        y += 21
    for line in _wrap(draft["site"], 490, 10, "helv", 2):
        _txt(page, (MARGIN, y+2), line, 10, MUTED)
        y += 16
    y += 13

    _rect(page, MARGIN, y, RIGHT, y+92, PALE)
    _row(page, y+10, "Quote reference", quote_no)
    _row(page, y+33, "Prepared", prepared_date)
    _row(page, y+56, "Valid until", valid_until)
    y += 119

    _txt(page, (MARGIN, y), "MAINTENANCE PACKAGE", 9, ACCENT, "hebo")
    y += 21
    _txt(page, (MARGIN, y), str(draft["tier"]).upper()+" COVER",
         15, NAVY, "hebo")
    _txt(page, (MARGIN+220, y), f"{draft['term_years']} year(s) proposed",
         10, INK)
    y += 19
    if draft.get("contract_start") and draft.get("contract_end"):
        period = f"Proposed period: {draft['contract_start']} to {draft['contract_end']}"
    else:
        period = "Proposed commencement: to be confirmed with the customer"
    _txt(page, (MARGIN, y), period, 9, MUTED)
    y += 36

    _rect(page, MARGIN, y, RIGHT, y+84, NAVY)
    _txt(page, (MARGIN+15, y+19), "ANNUAL MAINTENANCE VALUE", 9, WHITE)
    _txt(page, (MARGIN+15, y+51), _money(pricing["annual_partial"]),
         20, WHITE, "hebo")
    _txt(page, (MARGIN+306, y+19), "PROPOSED TERM VALUE", 9, WHITE)
    _txt(page, (MARGIN+306, y+51),
         _money(pricing["term_partial"]), 15, WHITE, "hebo")
    y += 104
    _txt(page, (MARGIN, y), "Price excludes VAT where applicable.", 9, MUTED)
    y += 24
    _txt(page, (MARGIN, y), "EQUIPMENT SCHEDULE", 11, ACCENT, "hebo")
    y += 18

    def head(current, top):
        _rect(current, MARGIN, top, RIGHT, top+27, NAVY)
        _txt(current, (MARGIN+8, top+17), "Equipment / item code", 8, WHITE, "hebo")
        _txt(current, (MARGIN+303, top+17), "Qty", 8, WHITE, "hebo")
        _txt(current, (MARGIN+362, top+17), "Annual", 8, WHITE, "hebo")
        return top+29

    y = head(page, y)
    for line in pricing["lines"]:
        description = str(line.get("description") or "")
        ident = str(line.get("sku") or line.get("item_code") or "")
        asset_index = int(line["line"]) - 1
        asset = (draft["equipment"][asset_index]
                 if 0 <= asset_index < len(draft["equipment"]) else {})
        desc_lines = _wrap(description, 278, 9, maxlines=3)
        details = ["Item code: " + ident]
        if asset.get("serial"):
            details.append("Serial / reference: " + str(asset["serial"]))
        if asset.get("cover_start"):
            details.append("Cover starts: " + str(asset["cover_start"]))
        detail_lines = []
        for detail in details:
            detail_lines.extend(_wrap(detail, 278, 7.5, maxlines=2))
        h = max(51, 12*len(desc_lines) + 10*len(detail_lines) + 13)
        if y+h > H-115:
            page = _page(doc, quote_no, internal_draft)
            y = head(page, 142 if not internal_draft else 153)
        _rect(page, MARGIN, y, RIGHT, y+h, PALE)
        for j, value in enumerate(desc_lines):
            _txt(page, (MARGIN+8, y+15+j*12), value, 9, INK,
                 "hebo" if j == 0 else "helv")
        start = y+17+len(desc_lines)*12
        for j, value in enumerate(detail_lines):
            _txt(page, (MARGIN+8, start+j*10), value, 7.5, MUTED)
        _txt(page, (MARGIN+307, y+20), str(line["quantity"]), 9, INK)
        _txt(page, (MARGIN+359, y+20),
             _money(line["annual"]), 9, INK, "hebo")
        y += h+3

    if y+100 > H-94:
        page = _page(doc, quote_no, internal_draft)
        y = 149 if not internal_draft else 159
    y += 16
    _txt(page, (MARGIN, y), "IMPORTANT INFORMATION", 9, ACCENT, "hebo")
    y += 19
    notes = [
        "This is a quotation for the indicated maintenance package and equipment only.",
        "Cover, included services, exclusions and conditions are specified in the attached",
        "Pulse Fitness maintenance terms. No maintenance contract is active until agreed.",
        "Changes to equipment or quantities may require a revised quotation.",
    ]
    for note in notes:
        _txt(page, (MARGIN, y), note, 8.6, MUTED)
        y += 13
    y += 11
    _txt(page, (MARGIN, y),
         ("Internal price preview - not authorised for distribution."
          if internal_draft else
          "Commercially reviewed: "+_safe(approval_ref, 100)), 8.5, MUTED)
    if issuer and not internal_draft:
        details = [
            ("Issuer", issuer.get("legal_name", "")),
            ("Registered address", issuer.get("registered_address", "")),
            ("Company number", issuer.get("company_number", "")),
            ("Email", issuer.get("contact_email", "")),
        ]
        if issuer.get("telephone"):
            details.append(("Telephone", issuer["telephone"]))
        if issuer.get("vat_number"):
            details.append(("VAT number", issuer["vat_number"]))
        # Factual company details from an IT-pinned source, never fabricated.
        if y + 22 + len(details) * 13 > H - 66:
            page = _page(doc, quote_no, internal_draft)
            y = 150
        y += 22
        _txt(page, (MARGIN, y), "SUPPLIER DETAILS", 9, ACCENT, "hebo")
        y += 15
        for label, value in details:
            for value_line in _wrap(f"{label}: {value}", 490, 8, maxlines=2):
                _txt(page, (MARGIN, y), value_line, 8, MUTED)
                y += 13

    for number, customer_page in enumerate(doc, start=1):
        _txt(customer_page, (RIGHT-59, H-29), f"Page {number}",
             8, MUTED)

    if terms_pdf and not internal_draft:
        terms = fitz.open(stream=terms_pdf, filetype="pdf")
        try:
            if terms.needs_pass or terms.page_count < 1 or terms.page_count > 30:
                raise ValueError("Approved maintenance terms PDF is invalid.")
            doc.insert_pdf(terms)
        finally:
            terms.close()
    try:
        result = doc.tobytes(garbage=4, deflate=True)
        if len(result) > 15 * 1024 * 1024:
            raise ValueError("Customer quotation PDF exceeds the archive limit.")
        return result
    finally:
        doc.close()
