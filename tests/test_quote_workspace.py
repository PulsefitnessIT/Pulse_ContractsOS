"""Synthetic regression coverage for the opt-in SmartQuote read-only register."""
import json
import sqlite3

from app import quote_workspace


def test_unconfigured_source_is_not_silently_replaced(monkeypatch):
    monkeypatch.delenv("PULSE_SMARTQUOTE_DB", raising=False)
    assert quote_workspace._source() is None


def test_quotes_are_read_from_source_without_writing(tmp_path, monkeypatch):
    source = tmp_path / "smartquote_local.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE quotes(id TEXT, quote_no TEXT, created TEXT, updated TEXT, status TEXT, payload TEXT)")
        db.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?)",
                   ("fake-id", "SQ-TEST-0001", "2026-01-01", "2026-01-02", "Draft",
                    json.dumps({"customer": "Example Ltd", "site": "Example Site",
                                "tier": "Gold", "pricing_approved": False})))
    monkeypatch.setenv("PULSE_SMARTQUOTE_DB", str(source))
    monkeypatch.setattr(quote_workspace, "actor", lambda: "test")
    result = quote_workspace.list_quotes(limit=10, offset=0)
    assert result["total"] == 1
    assert result["items"][0]["quote_number"] == "SQ-TEST-0001"
    assert result["read_only"] is True
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == 1
