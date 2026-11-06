"""Pulse invoice/delivery-note line reader for SmartQuote.

Uses table-row evidence, NOT free-floating SKU regex matches. Supports:
* 2018 Pulse legacy invoices (product groups; serials below items)
* 2026 Sage-style Pulse invoices (serials can continue on next page)
* Pulse delivery notes (quantity sent vs received, TO FOLLOW)

Values below are SOURCE HINTS ONLY. Active unified Master decides pricing;
coordinators verify quantities and serials. No customer data is bundled here.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import fitz

_MODERN = re.compile(
    r"^\s*\d{1,3}\s+(?P<sku>[A-Za-z0-9][A-Za-z0-9._/-]{1,40})\s{2,}"
    r"(?P<name>.+?)\s{2,}(?P<qty>\d{1,4})\s+£\s*"
    r"(?P<unit>[\d,]+\.\d{2})\s+£\s*(?P<total>[\d,]+\.\d{2})\s*$"
)
_LEGACY = re.compile(
    r"^\s*(?P<sku>[A-Za-z0-9][A-Za-z0-9./-]{1,40})\s{2,}"
    r"(?P<name>.+?)\s{2,}(?P<qty>\d{1,4})\s+£\s*"
    r"(?P<unit>[\d,]+\.\d{2})\s+£\s*(?P<total>[\d,]+\.\d{2})\s*$"
)
_SERIAL = re.compile(r"^\s*Batch/Serial Number\s*:\s*(\S+)\s*$", re.I)
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./_-]{1,34}(?:\s+[A-Z]{2,4})?$")
_NON_EQUIPMENT = re.compile(
    r"^(?:accessories|customer care|tradein|trade in|del(?:ivery)?(?: & | and )?"
    r"inst(?:allation)?|war-.*|engtrain|software|smart centre)$", re.I
)
_NON_MACHINE_DESCRIPTIONS = re.compile(
    r"^(?:digital freeview|ipod 5 lightning|e-scape virtual training|"
    r"e-scape virtual videos|nfc ready|qr code|software integration|"
    r"delivery\s*(?:&|and)\s*installation|on-site preventative maintenance training|"
    r"business partnership support|pulse move software|small tool box)",
    re.I,
)


def _exclude_hint(code, description):
    return bool(
        _NON_EQUIPMENT.fullmatch(code)
        or _NON_EQUIPMENT.fullmatch(description.strip())
        or _NON_MACHINE_DESCRIPTIONS.search(description.strip())
        or code.upper() in {"STRTRPTRESLINK"}
    )


_MAX_ROWS = 2500
_MAX_SERIALS = 500


def _serials(text):
    return [
        token for token in (part.strip().strip(".,") for part in text.split(","))
        if token and token.upper() not in {"5206/3", "TO FOLLOW"}
    ]


def parse_pages(pages):
    """Parse sorted PDF page text; the same method handles synthetic tests.

    Pages are dictionaries {"page": 1, "text": "..."}; no OCR guesses or
    externally supplied Master data may influence the extraction.
    """
    ordered = sorted(pages, key=lambda p: p["page"])
    first = "\n".join(p["text"][:1800] for p in ordered[:2])
    kind = ("delivery_note" if re.search(r"DELIVERY\s+NOTE", first, re.I)
            else "invoice" if re.search(r"\bINVOICE\b", first, re.I)
            else "unrecognised")
    mode = ("delivery" if kind == "delivery_note" else
            "modern" if "Line Item Code" in first else "legacy")
    if kind == "unrecognised":
        return {"document_type": kind, "format": "", "lines": [],
                "warnings": ["No recognised Pulse invoice or delivery-note layout."]}
    lines = []
    current = None
    serial_mode = False
    serial_seen = False
    truncated = False
    for item in ordered:
        page_no = item["page"]
        within_table = False
        for row in item["text"].splitlines():
            if mode == "delivery":
                if "Products" in row and "QTY SENT" in row:
                    within_table = True
                    continue
                if not within_table:
                    continue
                if "GOODS RECEIVED" in row or re.search(r"Page \d+ of \d+", row):
                    within_table = False
                    continue
                if not row.strip():
                    continue
                columns = re.split(r"\s{2,}", row.strip())
                if (len(columns) >= 4 and _CODE.fullmatch(columns[0])
                        and columns[-1].isdigit() and columns[-2].isdigit()):
                    code = columns[0].upper()
                    qty_sent, qty_received = int(columns[-2]), int(columns[-1])
                    if qty_sent > 10000 or qty_received > 10000:
                        continue
                    name = columns[1][:350]
                    current = {
                        "sku": code, "description": name,
                        "quantity": qty_received, "quantity_sent": qty_sent,
                        "quantity_received": qty_received,
                        "serial_numbers": _serials(",".join(columns[2:-2])),
                        "pages": [page_no],
                        "excluded_hint": _exclude_hint(code, name),
                    }
                    lines.append(current)
                    if len(lines) >= _MAX_ROWS:
                        truncated = True
                        break
                    continue
                # The Pulse delivery note wraps some serial-number lists onto
                # subsequent lines (the product code is not repeated).
                if (current and re.fullmatch(
                        r"\s*[A-Za-z0-9-]{5,30}(?:\s*,\s*[A-Za-z0-9-]{5,30})*\s*",
                        row)):
                    current["serial_numbers"].extend(_serials(row))
                    current["pages"] = sorted(set(current["pages"] + [page_no]))
                continue

            if ((mode == "modern" and "Line Item Code" in row) or
                    (mode == "legacy" and row.strip().startswith("Description")
                     and "Qty" in row)):
                within_table = True
                continue
            if not within_table:
                # Modern Sage invoices place the remaining serials from the
                # previous equipment line ABOVE the next page's table header.
                serial = _SERIAL.match(row)
                if mode == "modern" and serial and current:
                    current["serial_numbers"].append(serial.group(1))
                    current["pages"] = sorted(set(current["pages"] + [page_no]))
                continue
            match = (_MODERN if mode == "modern" else _LEGACY).match(row)
            if match:
                code = match.group("sku").upper()
                name = match.group("name").strip()
                current = {
                    "sku": code, "description": name[:350],
                    "quantity": int(match.group("qty")),
                    "serial_numbers": [], "pages": [page_no],
                    "excluded_hint": _exclude_hint(code, name),
                }
                lines.append(current)
                serial_mode = serial_seen = False
                if len(lines) >= _MAX_ROWS:
                    truncated = True
                    break
                continue
            if mode == "modern":
                serial = _SERIAL.match(row)
                if serial and current:
                    current["serial_numbers"].append(serial.group(1))
                    current["pages"] = sorted(set(current["pages"] + [page_no]))
            else:
                if "Serial Numbers" in row:
                    serial_mode, serial_seen = True, False
                    continue
                if serial_mode and not row.strip() and serial_seen:
                    serial_mode = serial_seen = False
                    continue
                if serial_mode and current and row.strip() and not re.search(
                        r"Product Group|Our Ref", row, re.I):
                    current["serial_numbers"].extend(_serials(row))
                    current["pages"] = sorted(set(current["pages"] + [page_no]))
                    serial_seen = True
                if "Product Group" in row:
                    serial_mode = serial_seen = False
        if truncated:
            break
    for line in lines:
        joined = []
        for candidate in line["serial_numbers"]:
            if (joined and joined[-1].endswith("-") and
                    re.fullmatch(r"[A-Za-z0-9-]{4,24}", candidate)):
                joined[-1] += candidate
            else:
                joined.append(candidate)
        line["serial_numbers"] = list(dict.fromkeys(joined))[:_MAX_SERIALS]
        line["serial_count"] = len(line["serial_numbers"])
        line["quantity_confirmed"] = False
    return {
        "document_type": kind,
        "format": mode,
        "lines": lines,
        "warnings": (
            ["Source table exceeded the safe row limit; manual review required."]
            if truncated else []
        ),
        "source_only": True,
    }


def parse_pdf(content):
    """Bounded local PDF text extraction; no network and no price inference."""
    with fitz.open(stream=content, filetype="pdf") as document:
        pages = [
            {"page": i + 1, "text": page.get_text("text", sort=True)}
            for i, page in enumerate(document)
        ]
    return parse_pages(pages)
