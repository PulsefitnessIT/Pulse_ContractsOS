"""Sicon API is optional. All tests use invented records and no network."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import sicon_bridge
from app.quote_intake import register, validate
from test_pilot_data_contract_setup import sample


def approved():
    return {
        "sage_account_ref": "SAGE-DEMO-123",
        "contract_reference": "CON-DEMO-01",
        "billing_stock_code": "DEMO-MAINTENANCE",
        "billing_frequency": "Monthly",
        "verified_serials": {"demo-B": ["DEMO-002", "DEMO-003"]},
    }


class SiconOptionalBridgeTests(unittest.TestCase):
    def test_no_credentials_manual_mode_is_fully_available(self):
        with patch.dict(os.environ, {}, clear=True):
            state = sicon_bridge.integration_status()
        self.assertEqual(state["mode"], "manual_excel")
        self.assertTrue(state["documents_available_without_api"])
        self.assertTrue(state["manual_contract_import"])
        self.assertTrue(state["manual_equipment_import"])
        self.assertTrue(state["manual_import_confirmation"])
        self.assertFalse(state["requires_api_credentials"])
        self.assertFalse(state["api_write_enabled"])

    def test_accidental_env_flags_cannot_enable_live_writes_or_reveal_secrets(self):
        with patch.dict(os.environ, {
            "SICON_API_WRITE_ENABLED": "1",
            "SICON_API_KEY": "FICTIONAL-SHOULD-NOT-BE-RETURNED",
            "SICON_API_MODE": "live",
            "SICON_BEARER_TOKEN": "NEVER-RETURN-THIS",
        }):
            state=sicon_bridge.integration_status()
            self.assertFalse(state["api_write_enabled"])
            self.assertEqual(state["mode"],"manual_excel")
            self.assertNotIn("FICTIONAL-SHOULD-NOT-BE-RETURNED",json.dumps(state))
            self.assertNotIn("NEVER-RETURN-THIS",json.dumps(state))

    def test_contract_and_equipment_preview_is_never_executable(self):
        q=validate(sample())
        before=json.dumps(q,sort_keys=True)
        plan=sicon_bridge.build_api_preview(q,approved(),{},today=dt.date(2026,11,1))
        self.assertTrue(plan["preview_only"])
        self.assertFalse(plan["api_write_enabled"])
        self.assertTrue(plan["manual_workflow_unaffected"])
        self.assertFalse(plan["requires_credentials_to_preview"])
        self.assertEqual(len(plan["lines"]),2)
        self.assertEqual(len(plan["equipment"]),3)
        self.assertEqual(plan["contract"]["proposed_fields"]["CustomerNumber"],"SAGE-DEMO-123")
        self.assertIsNone(plan["lines"][0]["proposed_fields"]["SiconContractID"])
        self.assertIsNone(plan["lines"][0]["proposed_fields"]["UnitPrice"])
        self.assertIsNone(plan["lines"][0]["proposed_fields"]["ProRata"])
        self.assertFalse(plan["lines"][0]["can_send"])
        self.assertFalse(plan["contract"]["can_send"])
        self.assertTrue(all(not x["can_send"] for x in plan["equipment"]))
        self.assertEqual(plan["lines"][1]["start_date"],"2027-07-01")
        self.assertEqual(plan["lines"][1]["accepted_annualised_value"],"300.00")
        self.assertEqual(plan["lines"][1]["accepted_first_period_value"],"150.00")
        self.assertTrue(plan["equipment"][0]["cover_due"])
        self.assertFalse(plan["equipment"][1]["cover_due"])
        self.assertEqual(json.dumps(q,sort_keys=True),before)

    def test_contract_number_is_not_misused_as_numeric_sicon_id(self):
        plan=sicon_bridge.build_api_preview(validate(sample()),approved(),{},
                                            today=dt.date(2026,11,1))
        self.assertEqual(plan["contract"]["proposed_fields"]["ContractNumber"],"CON-DEMO-01")
        self.assertIsNone(plan["lines"][0]["proposed_fields"]["SiconContractID"])
        for line in plan["equipment"]:
            self.assertIsNone(line["proposed_fields"]["SiconContractLineID"])
            self.assertIsNone(line["proposed_fields"]["CustomerID"])
            self.assertIsNone(line["proposed_fields"]["ItemID"])

    def test_readonly_api_preview_preserves_existing_register(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        dbfile=Path(temp.name)/"fictional.sqlite3"
        def connect():
            con=sqlite3.connect(dbfile)
            con.row_factory=sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            return con
        with connect() as con:
            con.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, fields TEXT, status TEXT)")
            result=register(con,sample(),"demo.coordinator")
        with connect() as con:
            pre=con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
            pre_events=con.execute("SELECT COUNT(*) FROM smartquote_setup_events").fetchone()[0]
            pre_revision=con.execute("SELECT revision FROM smartquote_setup_cases").fetchone()[0]
        with patch.object(sicon_bridge,"connect",connect):
            plan=sicon_bridge.api_preview(result["id"])
        self.assertEqual(plan["source_quote"],"SQ-SAMPLE-001")
        with connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],pre)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM smartquote_setup_events").fetchone()[0],pre_events)
            self.assertEqual(con.execute("SELECT revision FROM smartquote_setup_cases").fetchone()[0],pre_revision)


if __name__ == "__main__":
    unittest.main()
