"""Fictional admin price editing is source-bound and fully audited."""
import sqlite3
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import quote_price_overrides as edits, quote_pricing, quote_rrp_priority as rrp


def setup_admin(tmp_path, monkeypatch):
    db = tmp_path / "quote-prices.sqlite3"
    def connect():
        con = sqlite3.connect(str(db), timeout=10)
        con.row_factory = sqlite3.Row
        return con
    monkeypatch.setattr(edits, "connect", connect)
    monkeypatch.setattr(edits.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(edits.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(edits.pilot_access, "actor", lambda fallback="": "fictional-admin")
    monkeypatch.setattr(edits, "source_for_code", lambda sku: (
        {"basis": "sage_exact_sku_price", "rrp": 1200.0, "review_required": False},
        "a"*64,
    ))
    return db


def test_admin_updates_are_versioned_and_revert_retains_audit(tmp_path, monkeypatch):
    db = setup_admin(tmp_path, monkeypatch)
    first = edits.update_price("old-bike", edits.PriceChange(
        price_gbp="1300.25", expected_revision=0,
        reason="Corrected against company price review"
    ))
    assert first["sku"] == "OLD-BIKE"
    assert first["effective_rrp_gbp"] == 1300.25
    assert first["revision"] == 1
    assert first["customer_quote_issue_enabled"] is False
    with pytest.raises(HTTPException) as err:
        edits.update_price("OLD-BIKE", edits.PriceChange(
            price_gbp="4000", expected_revision=0,
            reason="Stale coordinator revision attempt"
        ))
    assert err.value.status_code == 409
    latest = edits.update_price("OLD-BIKE", edits.PriceChange(
        price_gbp="1400", expected_revision=1,
        reason="Annual price review and correction"
    ))
    assert latest["revision"] == 2
    assert edits.active_overrides(["old-bike"])["OLD-BIKE"]["price_pence"] == 140000
    detail = edits.price_detail("OLD-BIKE")
    assert detail["effective_price_gbp"] == 1400
    assert detail["revision"] == 2
    assert len(detail["history"]) == 2
    reverted = edits.revert_price("OLD-BIKE", edits.PriceRevert(
        expected_revision=2, reason="Restore exact Sage source price"
    ))
    assert reverted["active"] is False
    assert reverted["revision"] == 3
    assert edits.active_overrides(["OLD-BIKE"]) == {}
    assert edits.price_detail("OLD-BIKE")["effective_price_gbp"] == 1200
    with sqlite3.connect(db) as con:
        changes = con.execute(
            "SELECT action,revision,actor FROM smartquote_price_override_audit "
            "ORDER BY id"
        ).fetchall()
    assert changes == [
        ("set", 1, "fictional-admin"),
        ("set", 2, "fictional-admin"),
        ("revert", 3, "fictional-admin"),
    ]


def test_stale_source_snapshot_blocks_old_edited_price():
    original = {"basis": "sage_exact_sku_price", "rrp": 2500.0}
    changed = edits.effective(original, {
        "price_pence": 180000, "source_kind": "sage_exact_sku_price",
        "source_sha256": "a"*64, "revision": 3,
        "updated_at": "2026-11-03", "updated_by": "fictional-admin",
        "active": 1,
    }, {}, {"source_file_sha256": "b"*64})
    assert changed["basis"] == "stale_price_override"
    assert changed["rrp"] is None
    assert changed["override_status"] == "source_changed_review_required"
    assert changed["review_required"] is True


def test_price_override_works_without_changing_underlying_sage():
    underlying = {"basis": "sage_exact_sku_price", "rrp": 999.99}
    overlay = edits.effective(underlying, {
        "price_pence": 112255, "source_kind": "sage_exact_sku_price",
        "source_sha256": "b"*64, "revision": 2,
        "updated_at": "2026-11-03", "updated_by": "fictional-admin",
        "active": 1,
    }, {}, {"source_file_sha256": "b"*64})
    assert overlay["rrp"] == 1122.55
    assert overlay["basis"] == "managed_price_override"
    assert overlay["underlying_basis"] == "sage_exact_sku_price"
    assert overlay["original_source_price_gbp"] == 999.99
    assert underlying["rrp"] == 999.99


def test_non_admin_and_non_pilot_cannot_change_price(tmp_path, monkeypatch):
    setup_admin(tmp_path, monkeypatch)
    monkeypatch.setattr(edits.pilot_access, "current_role", lambda: "Coordinator")
    with pytest.raises(HTTPException) as err:
        edits.update_price("OLD-BIKE", edits.PriceChange(
            price_gbp="300", expected_revision=0,
            reason="Should not be permitted"
        ))
    assert err.value.status_code == 403
    monkeypatch.setattr(edits.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(edits.pilot_access, "PILOT_MODE", False)
    with pytest.raises(HTTPException) as err:
        edits.price_detail("OLD-BIKE")
    assert err.value.status_code == 403


@pytest.mark.parametrize("price", ["-1", "0", "NaN", "1000001", "1.001"])
def test_bad_prices_rejected(tmp_path, monkeypatch, price):
    setup_admin(tmp_path, monkeypatch)
    with pytest.raises((HTTPException, ValidationError)) as err:
        edits.update_price("OLD-BIKE", edits.PriceChange(
            price_gbp=price, expected_revision=0,
            reason="Reject malformed price entry"
        ))
    if isinstance(err.value, HTTPException):
        assert err.value.status_code == 422


def _preview_inputs():
    catalogue = [{"sku": "OLD-BIKE", "rrp": 1000,
                  "service_key": "MODEL | No Console / N/A",
                  "console": "No Console / N/A", "model": "MODEL",
                  "name": "Fictional Bike", "match": "Exact SKU"}]
    configs = [{"key": "MODEL | No Console / N/A",
                "eligible": "Yes", "rate_group": "Standard Equipment"}]
    rules = {"currency": "GBP", "tiers": {"Gold": 1},
             "pricing_status": "Provisional",
             "rates": [{"group": "Standard Equipment", "status": "Active",
                        "standard": .03, "minimum": .025, "uplift": 0}],
             "console_rules": [{"name": "No Console / N/A",
                                "multiplier": 1, "uplift": 0}]}
    draft = {"id": "a"*32, "revision": 1, "tier": "Gold",
             "term_years": 1, "discount_percent": 0,
             "equipment": [{"item_code": "OLD-BIKE", "quantity": 2}]}
    return catalogue, configs, rules, draft


def test_quote_preview_uses_admin_price_not_stale_source_values():
    catalogue, configs, rules, draft = _preview_inputs()
    sage = {"prices": {"OLD-BIKE": {
        "sku": "OLD-BIKE", "sales_price": 1200
    }}, "source_date": "2026-11-03", "review_due": "2027-11-03",
        "review_overdue": False, "source_file_sha256": "d"*64,
        "source": "Sage exact SKU source"}
    override = {"OLD-BIKE": {
        "price_pence": 160000,
        "source_kind": "sage_exact_sku_price",
        "source_sha256": "d"*64,
        "revision": 2,
        "active": 1,
        "updated_by": "fictional-admin", "updated_at": "2026-11-03",
    }}
    result = quote_pricing.preview(
        draft, catalogue, configs, rules,
        {"catalog": "x", "configs": "y", "pricing": "z"},
        master_by_sku=rrp.index({"rows": []}),
        sage_source=sage, overrides=override, august_source={}
    )
    line = result["lines"][0]
    assert line["priced"] is True
    assert line["rrp"] == 1600
    assert line["annual"] == 96
    assert line["price_override"]["revision"] == 2
    assert line["rrp_source"] == "managed_price_override"
    assert catalogue[0]["rrp"] == 1000
    assert result["issue_quote_enabled"] is False


def test_stale_override_stops_quote_instead_of_using_new_sage_price():
    catalogue, configs, rules, draft = _preview_inputs()
    sage = {"prices": {"OLD-BIKE": {"sku": "OLD-BIKE", "sales_price": 1300}},
            "source_date": "2026-11-03", "review_due": "2027-11-03",
            "review_overdue": False, "source_file_sha256": "e"*64,
            "source": "Sage exact SKU source"}
    override = {"OLD-BIKE": {
        "price_pence": 160000,
        "source_kind": "sage_exact_sku_price",
        "source_sha256": "d"*64,
        "revision": 2, "active": 1,
    }}
    result = quote_pricing.preview(
        draft, catalogue, configs, rules, {"catalog": "x", "configs": "y", "pricing": "z"},
        master_by_sku=rrp.index({"rows": []}), sage_source=sage,
        overrides=override, august_source={}
    )
    assert result["priced_count"] == 0
    assert result["lines"][0]["rrp_source"] == "stale_price_override"
    assert result["lines"][0]["price_override"]["status"] == "source_changed_review_required"
    assert result["issue_quote_enabled"] is False
