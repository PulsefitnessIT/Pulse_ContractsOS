"""Source-provenance safety regression tests with invented workbook records only."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app import source_integrity, store


REQUIRED_ACTIVE = [
    "Customer / site", "Record ID", "Contract number",
    "Contract / warranty type", "Start date", "Expiry date",
    "Contract amount (£)", "Invoice Code",
]
REQUIRED_EXPIRED = [
    "Customer / site", "Record ID", "Contract number",
    "Contract / warranty type", "Expiry date", "Contract amount (£)",
]


def fictional_records():
    def record(row, name, source_id, label, amount):
        return {
            "row": row, "fill": "",
            "fields": {"Customer / site": name, "Record ID": source_id,
                "Contract number": "", "Contract / warranty type": label,
                "Start date": "2026-01-01", "Expiry date": "2026-12-31",
                "Contract amount (£)": amount, "Invoice Code": ""},
        }
    return {
        "Maintenance Database": (
            REQUIRED_ACTIVE,
            [record(620, "Example Alpha", "DUPLICATE", "P&L Ext Warr", ""),
             record(621, "Example Beta", "DUPLICATE", "Contract (Chargeable)", 120.5),
             record(622, "Example Gamma", "ACT-003", "Warranty", 0)]
        ),
        "Expired": (
            REQUIRED_EXPIRED,
            [record(2, "Old Example", "EXP-001", "Second Hand", "")]
        ),
        "Weekly Values": (["Week ending (Friday)"], []),
        "Invoices": (["Invoice month"], []),
        "Quotes": (["Customer / site"], []),
    }


class FakeExcel:
    def __init__(self, path):
        self.z = self

    def records(self, name):
        return fictional_records().get(name, ([], []))

    def close(self):
        return None


def test_source_fingerprint_and_raw_cover_labels_are_factual(tmp_path, monkeypatch):
    p = tmp_path / "approved_master.xlsx"
    p.write_bytes(b"synthetic workbook marker")
    monkeypatch.setattr(source_integrity, "workbook_check",
        lambda _: {"valid": True, "sheet_names": source_integrity.WORKSHEETS})
    monkeypatch.setattr(source_integrity, "ExcelSource", FakeExcel)
    summary = source_integrity.source_audit(p)
    assert summary["workbook_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert summary["registers"]["Maintenance Database"]["populated_site_rows"] == 3
    assert summary["registers"]["Expired"]["populated_site_rows"] == 1
    assert summary["source_id_duplicates"]["extra_duplicate_rows"] == 1
    assert summary["source_id_duplicates"]["affected_source_rows"] == [
        {"sheet":"Maintenance Database", "row":620},
        {"sheet":"Maintenance Database", "row":621}
    ]
    cover = summary["registers"]["Maintenance Database"]["cover_labels_as_recorded"]
    assert cover["P&L Ext Warr"] == 1
    assert cover["Contract (Chargeable)"] == 1
    assert summary["registers"]["Maintenance Database"]["amounts_as_recorded"] == {
        "positive":1, "zero":1, "negative":0, "missing":1, "invalid":0
    }
    assert summary["verified_financial_revenue"] is False


def test_duplicate_source_id_preserved_without_duplicate_db_key(tmp_path, monkeypatch):
    fake_master = tmp_path / "approved_master.xlsx"
    fake_master.write_bytes(b"fictional master fixture")
    monkeypatch.setattr(store, "DATA", str(tmp_path))
    monkeypatch.setattr(store, "DB", str(tmp_path / "contracts.sqlite3"))
    monkeypatch.setattr(store, "TEMPLATE", str(fake_master))
    monkeypatch.setattr(store, "ExcelSource", FakeExcel)
    monkeypatch.setattr(source_integrity, "source_audit",
        lambda _: {"workbook_sha256":"a"*64,
                   "source_id_duplicates":{"extra_duplicate_rows":1}})
    store.init_db()
    with sqlite3.connect(store.DB) as db:
        entries = db.execute(
            "SELECT source_sheet, source_row, row_key,fields "
            "FROM contracts ORDER BY source_sheet, source_row"
        ).fetchall()
        assert len(entries) == 4
        assert len({r[2] for r in entries}) == 4
        doubles = [r for r in entries if json.loads(r[3]).get("Record ID") == "DUPLICATE"]
        assert len(doubles) == 2
        assert all(r[2].startswith("SOURCE_ROW:") for r in doubles)
        assert all(r[2] != "DUPLICATE" for r in doubles)
        meta = db.execute(
            "SELECT sha256,source_rows_active,source_rows_expired,duplicate_source_id_rows "
            "FROM master_source_loads"
        ).fetchone()
        assert meta == ("a"*64,3,1,1)
    current = store.stats()
    assert current["recorded_cover_labels"]["P&L Ext Warr"] == 1
    assert current["recorded_cover_labels"]["Contract (Chargeable)"] == 1
    assert current["types_are_heuristic_not_verified"] is True
    assert current["invoice_amounts_are_revenue_verified"] is False

    # Reopening the application must not re-import or duplicate records.
    store.init_db()
    with sqlite3.connect(store.DB) as db:
        assert db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 4


def test_source_row_key_cannot_be_claimed_as_a_verified_source_id():
    repeated = {"DUPLICATE"}
    assert source_integrity.source_row_key(
        "Maintenance Database", 620, "DUPLICATE", repeated
    ) == "SOURCE_ROW:Maintenance Database:620"
    assert source_integrity.source_row_key(
        "Maintenance Database", 622, "ACT-003", repeated
    ) == "ACT-003"
    assert source_integrity.source_row_key("Expired", 8, "", repeated
    ) == "SOURCE_ROW:Expired:8"
