"""Synthetic integrated coordinator setup tests; never use customer data."""
import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from fastapi import HTTPException
from unittest.mock import patch

from app import contract_setup as setup
from app.quote_intake import register, SCHEMA


def sample():
    return {
        "schema_version": SCHEMA, "source_system": "Pulse SmartQuote",
        "source_quote_id": "fictional-quote-01", "quote_number": "SQ-SAMPLE-001",
        "source_revision": "pdf-v1", "acceptance_status": "Accepted",
        "customer": {
            "legal_name": "Fictional Council", "site_name": "Example Community Gym",
            "sage_account_ref": "SAGE-DEMO-1", "sicon_site_ref": "SITE-DEMO-1",
        },
        "contract": {
            "reference": "", "package": "Gold", "start_date": "2026-01-01",
            "end_date": "2027-12-31", "payment_terms": "Monthly", "visits": 1,
        },
        "pricing": {
            "annual_total": 900, "term_total": 750, "currency": "GBP",
            "commercially_approved": True, "source_quote_pdf_sha256": "a"*64,
        },
        "equipment": [
            {"source_line_id": "demo-A", "item_code": "100H-AAA",
             "quantity": 1, "serial_numbers": ["DEMO-001"],
             "cover_start": "2026-01-01", "cover_end": "2027-12-31",
             "annual_total": 600, "first_period_total": 600},
            {"source_line_id": "demo-B", "item_code": "200G-ABC",
             "quantity": 2, "serial_numbers": ["DEMO-002"],
             "cover_start": "2027-07-01", "cover_end": "2027-12-31",
             "annual_total": 300, "first_period_total": 150},
        ],
    }


class ContractSetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / "fictional_runtime.sqlite3"

        def connect():
            con = sqlite3.connect(self.path)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            return con

        self.connect = connect
        patch_data = patch.object(setup, "DATA", str(self.root))
        patch_con = patch.object(setup, "connect", connect)
        patch_data.start()
        patch_con.start()
        self.addCleanup(patch_data.stop)
        self.addCleanup(patch_con.stop)

        with connect() as con:
            con.execute("""CREATE TABLE contracts (
                id INTEGER PRIMARY KEY, status TEXT, fields TEXT)""")
            self.created = register(con, sample(), "synthetic.coordinator")
        self.iid = self.created["id"]

    def get_case(self):
        return setup.get_setup(self.iid)

    def set_details(self, **updates):
        return setup.save_details(self.iid, {"revision": self.get_case()["revision"], **updates})

    def test_one_case_created_automatically(self):
        case = self.get_case()
        self.assertEqual(case["id"], 1)
        self.assertEqual(case["quote_number"], "SQ-SAMPLE-001")
        self.assertIn("Allocate verified contract reference", case["readiness"]["missing"])
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM smartquote_setup_cases").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0], 0)

    def test_simple_verified_details_and_serial_exception(self):
        case = self.set_details(contract_reference="CON-DEMO-001", billing_frequency="Monthly")
        self.assertIn("Verify 1 missing equipment serial number(s)",case["readiness"]["missing"])
        self.assertEqual(case["verified"]["contract_reference"], "CON-DEMO-001")
        self.assertFalse(case["readiness"]["agreement_ready"])
        fixed = setup.verify_serials(self.iid, {
            "revision": case["revision"], "source_line_id": "demo-B",
            "serial_numbers": ["DEMO-002", "DEMO-003"],
            "evidence": "Confirmed against engineer site inventory",
        })
        self.assertTrue(fixed["readiness"]["agreement_ready"])
        self.assertEqual(sample()["equipment"][1]["serial_numbers"], ["DEMO-002"])

    def test_revision_conflict_not_silent_overwrite(self):
        old = self.get_case()["revision"]
        self.set_details(contract_reference="CON-DEMO-001")
        with self.assertRaises(HTTPException) as err:
            setup.save_details(self.iid, {"revision": old, "purchase_order": "PO-123"})
        self.assertEqual(err.exception.status_code,409)

    def test_both_sicon_imports_ordered_and_evidenced(self):
        # Neither template mapping nor signed agreement has yet been approved.
        initial_plan = setup.get_import_plans(self.iid)
        self.assertEqual(initial_plan["warning"], "REVIEW_ONLY_MAPPING_PLAN_NOT_A_SICON_IMPORT")
        self.assertEqual(len(initial_plan["contract_import"]["staged_billing_groups"]),2)
        self.assertEqual(len(initial_plan["equipment_import"]["individual_machine_records"]),3)
        self.assertFalse(initial_plan["contract_import"]["ready_to_prepare"])
        with self.assertRaises(HTTPException):
            setup.confirm_contract_import(self.iid,{"sicon_contract_reference":"CON-1",
                                                   "evidence":"Accepted by test import"})
        case=self.set_details(contract_reference="CON-DEMO-001")
        setup.verify_serials(self.iid, {
            "revision":case["revision"],"source_line_id":"demo-B",
            "serial_numbers":["DEMO-002","DEMO-003"],
            "evidence":"Verified via signed equipment register"
        })
        pdf=base64.b64encode(b"%PDF-1.4\nSynthetic data only\n%%EOF\n").decode("ascii")
        with self.assertRaises(HTTPException) as unsigned:
            setup.record_signed(self.iid,{"filename":"sample.pdf","pdf_base64":pdf})
        self.assertEqual(unsigned.exception.status_code,422)
        signed=setup.record_signed(self.iid,{
            "filename":"sample.pdf","pdf_base64":pdf,"signatures_checked":True
        })
        self.assertTrue(signed["readiness"]["contract_import_ready"])
        with self.assertRaises(HTTPException):
            setup.confirm_equipment_import(self.iid,{
                "sicon_equipment_batch_reference":"BATCH-0001",
                "evidence":"Imported in controlled test environment"
            })
        confirmed=setup.confirm_contract_import(self.iid,{
            "sicon_contract_reference":"SICON-DEMO-001",
            "evidence":"Sicon import report verified by coordinator"
        })
        self.assertTrue(confirmed["readiness"]["equipment_import_ready"])
        after=setup.confirm_equipment_import(self.iid,{
            "sicon_equipment_batch_reference":"BATCH-DEMO-001",
            "evidence":"Individual equipment records checked in Sicon"
        })
        self.assertFalse(after["readiness"]["equipment_import_confirmed"])
        self.assertEqual(after["readiness"]["future_equipment_groups"],["2027-07-01"])
        self.assertEqual(after["readiness"]["imported_equipment_groups"],["2026-01-01"])
        self.assertEqual(len(after["equipment_import_batches"]),1)
        self.assertEqual(len(after["events"]),5)
        self.assertTrue((self.root/"private_signed_agreements").is_dir())
        self.assertEqual(setup.get_import_plans(self.iid)["equipment_import"]["individual_machine_records"][2]["serial_number"],"DEMO-003")

    def test_future_equipment_cannot_be_confirmed_early(self):
        import datetime as dt
        with patch.object(setup,"today",lambda:dt.date(2026,10,26)):
            case=self.set_details(contract_reference="CON-DEMO-001")
            setup.verify_serials(self.iid,{
                "revision":case["revision"],"source_line_id":"demo-B",
                "serial_numbers":["DEMO-002","DEMO-003"],
                "evidence":"Witnessed serials from technician register"
            })
            pdf=base64.b64encode(b"%PDF-1.4\nSigned fiction\n%%EOF\n").decode()
            setup.record_signed(self.iid,{"filename":"sample.pdf",
                          "pdf_base64":pdf,"signatures_checked":True})
            setup.confirm_contract_import(self.iid,{
                "sicon_contract_reference":"SICON-DEMO-001",
                "evidence":"Verified Sicon contract test import"})
            with self.assertRaises(HTTPException) as future:
                setup.confirm_equipment_import(self.iid,{
                    "start_date":"2027-07-01",
                    "sicon_equipment_batch_reference":"FUTURE-IMPORT",
                    "evidence":"Future batch should never be confirmed early"})
            self.assertEqual(future.exception.status_code,409)
            response=setup.upcoming_start_dates(days=365)
            self.assertEqual(len(response["items"]),1)
            self.assertEqual(response["items"][0]["machine_units"],2)
            self.assertEqual(response["items"][0]["start_date"],"2027-07-01")

    def test_invalid_double_serial_rejected_and_no_change(self):
        self.set_details(contract_reference="CON-DEMO-001")
        with self.assertRaises(HTTPException):
            setup.verify_serials(self.iid,{
                "revision": self.get_case()["revision"],"source_line_id":"demo-B",
                "serial_numbers":["DUP","DUP"],"evidence":"Entered from technician's report"
            })
        self.assertEqual(self.get_case()["verified"]["contract_reference"],"CON-DEMO-001")

    def test_signed_pdf_readback_is_hash_verified(self):
        case=self.set_details(contract_reference="CON-DEMO-001")
        setup.verify_serials(self.iid,{
            "revision":case["revision"],"source_line_id":"demo-B",
            "serial_numbers":["DEMO-002","DEMO-003"],
            "evidence":"Signed inventory witnessed by coordinator",
        })
        pdf=b"%PDF-1.4\nFictional file evidence only\n%%EOF\n"
        setup.record_signed(self.iid,{
            "filename":"fictional.pdf","pdf_base64":base64.b64encode(pdf).decode(),
            "signatures_checked":True,
        })
        attachment=setup.view_signed_agreement(self.iid)
        self.assertEqual(Path(attachment.path).read_bytes(),pdf)
        Path(attachment.path).write_bytes(b"%PDF-1.4\nChanged after upload\n%%EOF")
        with self.assertRaises(HTTPException) as changed:
            setup.view_signed_agreement(self.iid)
        self.assertEqual(changed.exception.status_code,409)

    def test_complete_recovery_bundle_contains_signed_evidence(self):
        from scripts import pilot_backup_bundle as backup
        from scripts.verify_recovery_bundle import verify
        from test_pilot_data_readiness import fake_master
        case=self.set_details(contract_reference="CON-DEMO-001")
        setup.verify_serials(self.iid,{
            "revision":case["revision"],"source_line_id":"demo-B",
            "serial_numbers":["DEMO-002","DEMO-003"],
            "evidence":"Verifiable fictional signed inventory",
        })
        pdf=b"%PDF-1.4\nFictional signed agreement\n%%EOF\n"
        setup.record_signed(self.iid,{
            "filename":"fictional.pdf","pdf_base64":base64.b64encode(pdf).decode(),
            "signatures_checked":True,
        })
        with self.connect() as con:
            for table in ("ledger","imports","changes","equipment"):
                con.execute("CREATE TABLE IF NOT EXISTS "+table+" (id INTEGER PRIMARY KEY)")
        fake_master(self.root/"approved_master.xlsx")
        with patch.object(backup,"DATA",str(self.root)), \
             patch.object(backup,"DB",str(self.path)), \
             patch.object(backup,"TEMPLATE",str(self.root/"approved_master.xlsx")):
            output=backup.create_bundle()
        import zipfile
        with zipfile.ZipFile(output) as z:
            evidence=[f for f in z.namelist() if f.startswith("private_signed_agreements/")]
            self.assertEqual(len(evidence),1)
            self.assertEqual(z.read(evidence[0]),pdf)
        verify(output)

    def test_unknown_extra_fields_rejected(self):
        with self.assertRaises(HTTPException):
            setup.save_details(self.iid, {"revision":1, "pricing_approved":True})
        self.assertFalse(self.get_case()["readiness"]["agreement_ready"])


if __name__ == "__main__":
    unittest.main()
