"""Pulse-branded INTERNAL quick quote PDF from the single active Master.

The document is an estimate; not a customer offer. This module has no
commercial issuance, contract approval or data-write capability.
"""
from __future__ import annotations

import datetime as dt

import fitz

from . import quote_customer_pdf as brand

CONTENT_BOTTOM = brand.H - 75


def render_quick_internal_pdf(draft, calculation):
    if (not calculation.get("complete_calculation")
            or not calculation.get("equipment")
            or calculation.get("customer_issue_enabled") is not False):
        raise ValueError("Cannot generate a complete internal quotation.")
    doc = fitz.open()
    reference = calculation["draft_reference"]
    page = brand._page(doc, reference, draft=True)
    y = 154

    def heading(label):
        nonlocal y, page
        if y > CONTENT_BOTTOM - 65:
            page = brand._page(doc, reference, draft=True)
            y = 154
        brand._txt(page, (brand.MARGIN, y), label, 11, brand.ACCENT, "hebo")
        y += 23

    def lines(value, width=486, size=10, *, font="helv"):
        nonlocal y, page
        for line in brand._wrap(value, width, size, font, maxlines=None):
            if y + 16 > CONTENT_BOTTOM:
                page = brand._page(doc, reference, draft=True)
                y = 154
            brand._txt(page, (brand.MARGIN, y), line, size, brand.INK, font)
            y += size + 5

    heading("CUSTOMER AND SITE")
    lines(calculation["customer"], font="hebo")
    lines(calculation["site"])
    y += 8

    heading("MAINTENANCE CONTRACT / INTERNAL ESTIMATE")
    lines(
        f"{calculation['package']} cover | {calculation['term_years']} year(s) | "
        f"Equipment Master version {calculation['price_book_revision']}",
        size=9
    )
    y += 9
    brand._rect(page, brand.MARGIN, y, brand.RIGHT, y + 63, brand.NAVY)
    brand._txt(page, (brand.MARGIN + 13, y + 22), "ANNUAL MAINTENANCE (EX VAT)",
               8.5, brand.WHITE, "hebo")
    brand._txt(page, (brand.MARGIN + 13, y + 48),
               "GBP " + calculation["annual_partial_gbp"], 16, brand.WHITE, "hebo")
    brand._txt(page, (brand.MARGIN + 285, y + 22), "TOTAL TERM (EX VAT)",
               8.5, brand.WHITE, "hebo")
    brand._txt(page, (brand.MARGIN + 285, y + 48),
               "GBP " + calculation["term_partial_gbp"], 13, brand.WHITE, "hebo")
    y += 87
    heading("EQUIPMENT SCHEDULE")
    for line in calculation["equipment"]:
        if y + 76 > CONTENT_BOTTOM:
            page = brand._page(doc, reference, draft=True)
            y = 154
            heading("EQUIPMENT SCHEDULE (CONTINUED)")
        brand._rect(page, brand.MARGIN, y - 10, brand.RIGHT, y + 52,
                    brand.PALE)
        short_name = brand._wrap(line["name"], 292, 9, "hebo", 2)
        for i, title in enumerate(short_name):
            brand._txt(page, (brand.MARGIN + 10, y + 5 + 12 * i),
                       title, 9, brand.INK, "hebo")
        brand._txt(page, (brand.MARGIN + 10, y + 34),
                   f"Item code: {line['sku']}", 8, brand.MUTED)
        brand._txt(page, (brand.MARGIN + 315, y + 5),
                   f"Qty: {line['quantity']}", 9, brand.INK, "hebo")
        brand._txt(page, (brand.MARGIN + 315, y + 20),
                   "Annual GBP " + str(line["annual_line_gbp"]),
                   9, brand.INK, "hebo")
        serial = str(line.get("serials") or "").strip()
        brand._txt(page, (brand.MARGIN + 315, y + 34),
                   "Serials below" if serial else "Serials to be verified",
                   7.4, brand.MUTED)
        y += 69
        # An invoice may contain 12 or more serials on one machine line.
        # The full list belongs in the internal review PDF (with page
        # breaks), not just the first 28 characters.
        if serial:
            lines("Source serials: " + serial, width=480, size=8)
            y += 8

    if draft.notes:
        y += 9
        heading("PROPOSED SCOPE / EXCLUSIONS (FOR REVIEW)")
        lines(draft.notes[:1400], 482, 9)

    y += 10
    heading("RELEASE STATUS")
    lines("INTERNAL DRAFT ONLY - NOT AUTHORISED FOR CUSTOMER ISSUE.", 458, 9,
          font="hebo")
    lines("Machine suitability, serials, service scope, Silver/Gold/Platinum rates, "
          "terms and VAT treatment require approval by Pulse Fitness.", 480, 8)
    lines("Source price revision: " + str(calculation["price_book_revision"])
          + " | Prepared: " + dt.date.today().isoformat(), 480, 8)
    # Do not attach fabricated terms or issue a customer quote number.
    try:
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
