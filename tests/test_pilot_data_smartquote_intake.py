"""Contract OS / SmartQuote bridge — fictional test records only; no runtime files."""
import json
import sqlite3
import unittest
from copy import deepcopy

from app.quote_intake import (SCHEMA, IntakeError, assess, exact_matches,
                              fingerprint, preview_data, register, validate)


def example():
    return {
        "schema_version": SCHEMA,
        "source_system": "Pulse SmartQuote",
        "source_quote_id": "a-synthetic-quote-001",
        "quote_number": "SQ-TEST-0001",
        "source_revision": "v3",
        "acceptance_status": "Accepted",
        "customer": {
            "legal_name": "Fictional Leisure Council",
            "site_name": "Sample Leisure Facility",
            "sage_account_ref": "DEMO-A001",
            "sicon_site_ref": "DEMO-S001",
            "billing_address": "Example Avenue",
            "site_address": "Demo Centre Road",
        },
        "contract": {
            "reference": "",
            "package": "Gold",
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "visits": 1,
            "payment_terms": "Annual",
        },
        "pricing": {
            "annual_total": 900,
            "term_total": 751.23,
            "commercially_approved": True,
            "source_quote_pdf_sha256": "a"*64,
        },
        "equipment": [
            {"source_line_id": "asset-001", "item_code": "100H-AAA",
             "description": "Strength machine", "quantity": 1, "serial_numbers": ["DEMO-SERIAL-1"],
             "cover_start": "2027-01-01", "cover_end": "2027-12-31",
             "annual_total": 600, "first_period_total": 600, "price_basis": "Master"},
            {"source_line_id": "asset-002", "item_code": "240G-ABC",
             "description": "Bike", "quantity": 2, "serial_numbers": ["DEMO-SERIAL-2", "DEMO-SERIAL-3"],
             "cover_start": "2027-07-01", "cover_end": "2027-12-31",
             "annual_total": 300, "first_period_total": 151.23, "price_basis": "Sage fallback"},
        ],
    }


def database():
    con=sqlite3.connect(":memory:")
    con.row_factory=sqlite3.Row
    con.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, status TEXT, fields TEXT)")
    con.execute("INSERT INTO contracts VALUES (1, 'Active', ?)", (json.dumps({
        "Customer / site": "Sample Leisure Facility", "Invoice account": "DEMO-A001",
        "Site account": "DEMO-S001", "Contract number": "OTHER-C"}),))
    con.execute("INSERT INTO contracts VALUES (2, 'Expired', ?)", (json.dumps({
        "Customer / site": "Sample Leisure Facility", "Invoice account": "UNRELATED",
        "Site account": "OTHER", "Contract number": "NOT-THE-SAME"}),))
    return con


class SmartQuoteIntakeTests(unittest.TestCase):
    def setUp(self):
        self.db=database()
        self.addCleanup(self.db.close)

    def test_complete_synthetic_quote(self):
        q=validate(example())
        self.assertTrue(assess(q)["ready_for_setup"])
        self.assertEqual(assess(q)["equipment_units"],3)
        self.assertEqual(len(assess(q)["staged_groups"]),2)
        self.assertEqual(len(q["equipment"]),2)

    def test_double_import_is_idempotent(self):
        first=register(self.db,example(),"contract.coordinator")
        again=register(self.db,example(),"contract.coordinator")
        self.assertEqual(first["id"],again["id"])
        self.assertFalse(first["already_imported"])
        self.assertTrue(again["already_imported"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM smartquote_intakes").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM smartquote_intake_history").fetchone()[0],1)

    def test_changed_quote_creates_new_audited_version(self):
        first=register(self.db,example())
        q=example()
        q["source_revision"]="v4"
        second=register(self.db,q)
        self.assertNotEqual(first["id"],second["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM smartquote_intakes").fetchone()[0],2)

    def test_matching_requires_real_references_not_names(self):
        q=validate(example())
        matches=exact_matches(self.db,q)
        self.assertEqual([x["contract_id"] for x in matches],[1])
        q["customer"]["sage_account_ref"]=""
        q["customer"]["sicon_site_ref"]=""
        self.assertEqual(exact_matches(self.db,q),[])
        self.assertFalse(assess(q)["ready_for_setup"])

    def test_unapproved_price_is_review_only(self):
        q=example()
        q["pricing"]["commercially_approved"]=False
        self.assertFalse(assess(validate(q))["ready_for_setup"])

    def test_quote_not_accepted_rejected(self):
        q=example()
        q["acceptance_status"]="Draft"
        with self.assertRaisesRegex(IntakeError,"Accepted"):
            validate(q)

    def test_refuses_wrong_financial_total(self):
        q=example()
        q["pricing"]["annual_total"]=902
        with self.assertRaisesRegex(IntakeError,"reconcile"):
            validate(q)

    def test_no_silent_invalid_equip_price(self):
        q=example()
        q["equipment"][0]["annual_total"]=None
        with self.assertRaisesRegex(IntakeError,"price"):
            validate(q)

    def test_invalid_date_or_duplicate_line_block(self):
        q=example()
        q["equipment"][1]["cover_start"]="2028-01-01"
        with self.assertRaisesRegex(IntakeError,"after its expiry|exceeds"):
            validate(q)
        q=example()
        q["equipment"][1]["source_line_id"]="asset-001"
        with self.assertRaisesRegex(IntakeError,"unique"):
            validate(q)

    def test_no_customer_password_from_unexpected_fields(self):
        q=example()
        q["customer"]["portal_password"]="fictional"
        canonical=validate(q)
        self.assertNotIn("portal_password",canonical["customer"])
        self.assertNotIn("fictional",json.dumps(canonical))

    def test_fingerprint_order_independent(self):
        q=validate(example())
        self.assertEqual(fingerprint(q),fingerprint(json.loads(json.dumps(q,sort_keys=True))))


if __name__=="__main__":
    unittest.main()
