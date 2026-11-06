"""Build fictional, eight-tab Pulse Contracts demo data for packaged Windows testing.

This utility is exclusively for distribution smoke tests and a supervised DEMO.
It never reads, copies, or modifies a customer's live Maintenance Master.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("", M)
SHEETS = ["Home", "Maintenance Database", "Weekly Values", "Invoices",
          "Monthly Report", "Sales Report", "Quotes", "Expired"]

HEADERS = [
    "Record ID", "Customer / site", "Contract number", "Contract / warranty type",
    "Contract amount (£)", "Start date", "Expiry date", "Sales manager",
    "Site account", "Invoice account", "Sage Checked and Updated",
    "Renewal status", "Notes", "Contact name", "Contact email",
]
DEMO_ACTIVE = [
    ["DEMO-001", "DEMO — Severn Leisure Centre", "SYN-CON-1001", "Gold Contract",
     "4370.63", "2026-10-01", "2027-09-30", "Demo Sales Manager",
     "SITE-DEMO-01", "AC-DEMO-01", "Yes", "Live", "FICTIONAL SAMPLE ONLY",
     "Test Contact", "demo@example.invalid"],
    ["DEMO-002", "DEMO — Market Street Fitness", "SYN-WAR-1002", "Warranty",
     "0", "2026-09-01", "2027-08-31", "Demo Sales Manager",
     "SITE-DEMO-02", "AC-DEMO-02", "Yes", "Warranty", "FICTIONAL SAMPLE ONLY",
     "Test Contact", "demo@example.invalid"],
    ["DEMO-003", "DEMO — Borough Training Hub", "SYN-CON-1003", "Silver Contract",
     "1825", "2026-11-01", "2027-10-31", "Demo Sales Manager",
     "SITE-DEMO-03", "AC-DEMO-03", "No", "Live", "FICTIONAL SAMPLE ONLY",
     "Test Contact", "demo@example.invalid"],
]
DEMO_EXPIRED = [
    ["DEMO-004", "DEMO — Old Leisure Club", "SYN-EXP-1004", "Expired Contract",
     "925", "2024-01-01", "2025-12-31", "Demo Sales Manager",
     "SITE-DEMO-04", "AC-DEMO-04", "Yes", "Expired", "FICTIONAL SAMPLE ONLY",
     "Test Contact", "demo@example.invalid"]
]


def col(n: int) -> str:
    result = ""
    while n:
        n, x = divmod(n - 1, 26)
        result = chr(65 + x) + result
    return result


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def sheet_data(headers, rows):
    root = ET.Element(f"{{{M}}}worksheet")
    sd = ET.SubElement(root, f"{{{M}}}sheetData")
    for row_idx, values in enumerate([headers] + rows, 1):
        r = ET.SubElement(sd, f"{{{M}}}row", r=str(row_idx))
        for c_idx, value in enumerate(values, 1):
            if value is None or str(value) == "":
                continue
            c = ET.SubElement(r, f"{{{M}}}c", r=f"{col(c_idx)}{row_idx}", t="inlineStr")
            inline = ET.SubElement(c, f"{{{M}}}is")
            ET.SubElement(inline, f"{{{M}}}t").text = str(value)
    return xml_bytes(root)


def create_master(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = ET.Element(f"{{{M}}}workbook", {f"{{{REL}}}dummy": "1"})
    wb.attrib.pop(f"{{{REL}}}dummy")
    sheets = ET.SubElement(wb, f"{{{M}}}sheets")
    for i, name in enumerate(SHEETS, 1):
        ET.SubElement(sheets, f"{{{M}}}sheet",
                      {"name": name, "sheetId": str(i), f"{{{REL}}}id": f"rId{i}"})
    styles = (f'<styleSheet xmlns="{M}"><fonts count="1"><font><sz val="11"/>'
              '<name val="Calibri"/></font></fonts><fills count="1"><fill>'
              '<patternFill patternType="none"/></fill></fills><borders count="1">'
              '<border/></borders><cellStyleXfs count="1"><xf numFmtId="0" '
              'fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" '
              'borderId="0" xfId="0"/></cellXfs></styleSheet>').encode()
    ctypes = ET.Element(f"{{{CONTENT}}}Types")
    ET.SubElement(ctypes, f"{{{CONTENT}}}Default",
                  Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(ctypes, f"{{{CONTENT}}}Default",
                  Extension="xml", ContentType="application/xml")
    ET.SubElement(ctypes, f"{{{CONTENT}}}Override",
                  PartName="/xl/workbook.xml",
                  ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    ET.SubElement(ctypes, f"{{{CONTENT}}}Override",
                  PartName="/xl/styles.xml",
                  ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml")
    for i in range(1, 9):
        ET.SubElement(ctypes, f"{{{CONTENT}}}Override",
                      PartName=f"/xl/worksheets/sheet{i}.xml",
                      ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    rels = ET.Element(f"{{{PKG}}}Relationships")
    ET.SubElement(rels, f"{{{PKG}}}Relationship",
                  Id="rId1", Type=REL + "/officeDocument", Target="xl/workbook.xml")
    wrels = ET.Element(f"{{{PKG}}}Relationships")
    for i in range(1, 9):
        ET.SubElement(wrels, f"{{{PKG}}}Relationship", Id=f"rId{i}",
                      Type=REL + "/worksheet", Target=f"worksheets/sheet{i}.xml")
    ET.SubElement(wrels, f"{{{PKG}}}Relationship", Id="rId9",
                  Type=REL + "/styles", Target="styles.xml")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", xml_bytes(ctypes))
        z.writestr("_rels/.rels", xml_bytes(rels))
        z.writestr("xl/workbook.xml", xml_bytes(wb))
        z.writestr("xl/_rels/workbook.xml.rels", xml_bytes(wrels))
        z.writestr("xl/styles.xml", styles)
        for i, name in enumerate(SHEETS, 1):
            if name == "Maintenance Database":
                body = sheet_data(HEADERS, DEMO_ACTIVE)
            elif name == "Expired":
                body = sheet_data(HEADERS, DEMO_EXPIRED)
            else:
                body = sheet_data(["Record ID", "Customer / site", "Notes"], [])
            z.writestr(f"xl/worksheets/sheet{i}.xml", body)
    with zipfile.ZipFile(path) as z:
        if z.testzip():
            raise RuntimeError("Demo master workbook is corrupt")


def sample_quote():
    return {
        "schema_version": "pulse.smartquote.accepted.v1",
        "source_system": "Pulse SmartQuote",
        "source_quote_id": "FICTIONAL-DEMO-ACCEPTED-01",
        "quote_number": "SQ-DEMO-ACCEPTED-01",
        "source_revision": "demo-pdf-v1",
        "acceptance_status": "Accepted",
        "customer": {
            "legal_name": "DEMO — Severn Leisure Council",
            "site_name": "DEMO — Severn Leisure Centre",
            "sage_account_ref": "AC-DEMO-01",
            "sicon_site_ref": "SITE-DEMO-01",
            "billing_address": "Fictional High Street, Demo Town",
            "site_address": "Fictional Sports Road, Demo Town",
            "contact_name": "Example Coordinator",
            "contact_email": "demo@example.invalid",
        },
        "contract": {
            "reference": "SYN-CON-1001",
            "package": "Gold",
            "start_date": "2026-10-01",
            "end_date": "2027-09-30",
            "payment_terms": "Monthly",
            "visits": 1,
        },
        "pricing": {
            "annual_total": 1800,
            "term_total": 1680.25,
            "commercially_approved": True, # Fictional training approval only
            "source_quote_pdf_sha256": "d" * 64, # Synthetic placeholder, not real PDF proof
        },
        "equipment": [
            {
                "source_line_id": "DEMO-LINE-1",
                "item_code": "DEMO-STR-100",
                "description": "Demo strength machine",
                "make": "Pulse Fitness",
                "model": "DEMO 100",
                "quantity": 2,
                "serial_numbers": ["DEMO-SERIAL-001", "DEMO-SERIAL-002"],
                "cover_start": "2026-10-01",
                "cover_end": "2027-09-30",
                "annual_total": 1200,
                "first_period_total": 1200,
            },
            {
                "source_line_id": "DEMO-LINE-2",
                "item_code": "DEMO-CAR-200",
                "description": "Demo exercise bike",
                "make": "Pulse Fitness",
                "model": "DEMO 200",
                "quantity": 1,
                "serial_numbers": ["DEMO-SERIAL-003"],
                "cover_start": "2027-01-01",
                "cover_end": "2027-09-30",
                "annual_total": 600,
                "first_period_total": 480.25,
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("demo_runtime"))
    args = parser.parse_args()
    root = args.output.resolve()
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    master = data / "approved_master.xlsx"
    create_master(master)
    catalog = [
        {"sku": "DEMO-STR-100", "name": "Strength Machine — Fictional",
         "model": "DEMO 100", "manufacturer": "Pulse Fitness",
         "group": "Strength", "status": "Demo Only"},
        {"sku": "DEMO-CAR-200", "name": "Exercise Bike — Fictional",
         "model": "DEMO 200", "manufacturer": "Pulse Fitness",
         "group": "Cardio", "status": "Demo Only"},
    ]
    (data / "equipment_catalogue.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    demo = root / "demo_files"
    demo.mkdir(exist_ok=True)
    (demo / "FICTIONAL_ACCEPTED_SMARTQUOTE.json").write_text(
        json.dumps(sample_quote(), ensure_ascii=False, indent=2), encoding="utf-8")
    (demo / "DEMO_DATA_ONLY.txt").write_text(
        "All records are fictional. Never use this demo database for real customers. "
        "Accepted-quote PDF fingerprint and approval values are sample placeholders. "
        "Agreement and Sicon exports are review-only and not approved for use.\n",
        encoding="utf-8")
    print(f"Created fictional demo runtime at {root}")


if __name__ == "__main__":
    main()
