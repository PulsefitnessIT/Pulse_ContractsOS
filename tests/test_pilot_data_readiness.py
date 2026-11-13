"""Synthetic, customer-free tests for real-data pilot readiness and safe staging."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.data_readiness import (WORKSHEETS, assess_database, workbook_check,
                                missing_amount_review_rows, safe_excel_csv_cell)
from scripts.stage_private_runtime import stage

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def fake_master(path, names=WORKSHEETS):
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    sheet_xml = "".join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}" />'
        for i,name in enumerate(names,1)
    )
    relationships = "".join(
        f'<Relationship Id="rId{i}" Type="{rel_ns}/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>'
        for i in range(1,len(names)+1)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml",
            f'<workbook xmlns="{NS}" xmlns:r="{rel_ns}"><sheets>{sheet_xml}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg_ns}">{relationships}</Relationships>')
        z.writestr("xl/styles.xml",f'<styleSheet xmlns="{NS}">'
            '<fills><fill/></fills><cellXfs><xf/></cellXfs></styleSheet>')
        for i in range(1,len(names)+1):
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                f'<worksheet xmlns="{NS}"><sheetData/></worksheet>')


def fake_db(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE contracts(id INTEGER PRIMARY KEY, status TEXT, fields TEXT)")
        examples = [
            ("Active", {"Customer / site": "Demo Centre A", "Contract number": "A-100", "Contract / warranty type": "Contract",
                        "Contract amount (£)": "£1,250.50", "Expiry date": "2027-04-30", "Sales manager": "Sample"}),
            ("Active", {"Customer / site": "Demo Centre B", "Contract number": "B-100", "Contract / warranty type": "Warranty",
                        "Contract amount (£)": "0", "Expiry date": "2027-04-30", "Sales manager": "Sample"}),
            ("Active", {"Customer / site": "Demo Centre C", "Contract number": "A-100", "Contract / warranty type": "Contract",
                        "Contract amount (£)": "", "Expiry date": "", "Sales manager": ""}),
            ("Active", {"Customer / site": "Demo Centre D", "Contract number": "", "Contract / warranty type": "Chargeable",
                        "Contract amount (£)": "TBC", "Expiry date": "", "Sales manager": ""}),
            ("Expired", {"Customer / site": "Old demo", "Contract number": "E-100", "Contract amount (£)": "5000"}),
        ]
        db.executemany("INSERT INTO contracts(status,fields) VALUES (?,?)",
                       [(status, json.dumps(fields)) for status, fields in examples])


class PrivatePilotDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "secure_source"
        self.source.mkdir()
        fake_master(self.source / "approved_master.xlsx")
        fake_db(self.source / "contracts.sqlite3")

    def test_aggregates_and_no_customer_details(self):
        result = assess_database(self.source / "contracts.sqlite3",
                                 self.source / "approved_master.xlsx")
        self.assertTrue(result["ready_for_data_review"], result["issues"])
        self.assertEqual(result["contracts"]["active"], 4)
        self.assertEqual(result["contracts"]["expired"], 1)
        self.assertEqual(result["contracts"]["missing_reference"], 1)
        self.assertEqual(result["contracts"]["repeated_reference_records"], 2)
        self.assertEqual(result["contracts"]["missing_expiry"], 2)
        self.assertEqual(result["financial_completeness"]["positive"], 1)
        self.assertEqual(result["financial_completeness"]["zero"], 1)
        self.assertEqual(result["financial_completeness"]["missing"], 1)
        self.assertEqual(result["financial_completeness"]["invalid"], 1)
        self.assertEqual(result["financial_completeness"]["recorded_percent"], 50.0)
        self.assertEqual(result["financial_completeness"]["by_cover_type"]["Warranty"]["zero"], 1)
        self.assertNotIn("Demo Centre", json.dumps(result))
        self.assertNotIn("1250.50", json.dumps(result))
        self.assertFalse(result["financial_completeness"]["is_verified_revenue"])

    def test_missing_values_can_be_exported_without_inventing_prices(self):
        rows = missing_amount_review_rows(self.source / "contracts.sqlite3")
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["Review reason"] for r in rows},
                         {"Missing amount", "Unclear amount"})
        self.assertEqual(safe_excel_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(safe_excel_csv_cell("  @SUM(A1)"), "'  @SUM(A1)")
        self.assertEqual(safe_excel_csv_cell("Sample site"), "Sample site")

    def test_missing_and_broken_files(self):
        absent = assess_database(self.root / "not-a-db.sqlite3", self.root / "not-a-master.xlsx")
        self.assertFalse(absent["ready_for_data_review"])
        self.assertFalse((self.root / "not-a-db.sqlite3").exists())
        self.assertTrue(absent["issues"])
        fake_master(self.source / "wrong.xlsx", names=list(reversed(WORKSHEETS)))
        self.assertFalse(workbook_check(self.source / "wrong.xlsx")["valid"])
        with zipfile.ZipFile(self.source / "broken.xlsx", "w") as z:
            z.writestr("xl/workbook.xml", "<workbook />")
        self.assertFalse(workbook_check(self.source / "broken.xlsx")["valid"])

    def test_private_snapshot_staged_and_not_overwritten(self):
        (self.source / "equipment_catalogue.json").write_text('[{"sku":"FAKE-001"}]')
        private_signed = self.source / "private_signed_agreements"
        private_signed.mkdir()
        (private_signed / "1_demo.pdf").write_bytes(b"%PDF-1.4\nSynthetic data\n%%EOF\n")
        templates=self.source/"approved_sicon_templates"
        templates.mkdir()
        (templates/"maintenance_agreement_approved.pdf").write_bytes(b"%PDF-1.4\nFictional approved source\n%%EOF")
        (templates/"sicon_contract_import.xlsx").write_bytes(b"Fake template in synthetic test")
        (templates/"sicon_equipment_import.xlsx").write_bytes(b"Fake equipment template in synthetic test")
        destination = self.root / "pilot_data"
        checked = stage(self.source, destination)
        self.assertEqual(checked["contracts"]["active"], 4)
        self.assertEqual({x.name for x in destination.iterdir()},
                         {"contracts.sqlite3", "approved_master.xlsx", "equipment_catalogue.json", "private_signed_agreements", "approved_sicon_templates"})
        with sqlite3.connect(destination / "contracts.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0], 5)
        self.assertEqual((destination / "private_signed_agreements" / "1_demo.pdf").read_bytes(),
                         b"%PDF-1.4\nSynthetic data\n%%EOF\n")
        self.assertEqual((destination/"approved_sicon_templates"/"sicon_contract_import.xlsx").read_bytes(),
                         b"Fake template in synthetic test")
        # Existing environments are not silently replaced.
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage(self.source, destination)
        with sqlite3.connect(destination / "contracts.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0], 5)

    def test_invalid_source_does_not_create_destination(self):
        fake_master(self.source / "approved_master.xlsx", names=["Bad"] * 8)
        destination = self.root / "pilot_data"
        with self.assertRaisesRegex(ValueError, "failed validation"):
            stage(self.source, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
