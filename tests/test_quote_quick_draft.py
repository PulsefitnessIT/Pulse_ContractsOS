"""Today-ready internal quote calculation against one unified Master price book.

All data are fictional. Never run customer payloads in CI.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app import quote_quick_draft as quick


@pytest.fixture
def book():
    return {
        "revision": 7, "sha256": "a" * 64,
        "rows": {
            "TREAD-1": {
                "price_pence": 1022096, "description": "Fictional Treadmill",
                "group": "Cardiovascular Equipment", "origin": "Current approved master",
                "status": "REFERENCE",
            },
            "BIKE-1": {
                "price_pence": 200000, "description": "Fictional Bike",
                "group": "Cardiovascular Equipment", "origin": "Legacy Sage",
                "status": "REFERENCE",
            },
            "PART-1": {
                "price_pence": 500000, "description": "Treadmill drive motor",
                "group": "CV Parts", "origin": "Legacy Sage",
                "status": "REFERENCE",
            },
            "HOLD-1": {
                "price_pence": None, "description": "Conflicting machine",
                "group": "Strength Equipment", "origin": "Master held",
                "status": "HOLD",
            },
            "ZERO-1": {
                "price_pence": 0, "description": "Unpriced machine",
                "group": "Strength Equipment", "origin": "Sage",
                "status": "UNPRICED",
            },
        }
    }


def payload(*lines):
    return quick.QuickDraft(
        customer="Fictional Local Authority",
        site="Example Sport Centre",
        package="Gold",
        discount_percent=Decimal("10"),
        term_years=3,
        notes="PPM only",
        lines=[quick.QuickDraftLine(**entry) for entry in lines],
        expected_price_book_sha256="a" * 64,
    )


def test_quotable_current_equipment_calculates_without_v10_mapping(book):
    draft = payload({"sku": "tread-1", "quantity": 3,
                     "serials": "DEMO-1,DEMO-2,DEMO-3",
                     "annual_rate_percent": Decimal("3.75")})
    result = quick.calculate(draft, book)
    assert result["price_book_revision"] == 7
    assert result["annual_partial_gbp"] == "1034.88"
    assert result["monthly_partial_gbp"] == "86.24"
    assert result["term_partial_gbp"] == "3104.64"
    assert result["equipment"][0]["annual_unit_gbp"] == "344.96"
    assert result["equipment"][0]["reference_price_gbp"] == "10220.96"
    assert result["complete_calculation"] is True
    assert result["customer_issue_enabled"] is False
    assert "INTERNAL DRAFT" in result["watermark"]
    assert result["scope_review_needed"] is True


def test_latest_price_book_is_sole_source_and_stale_snapshot_fails(book):
    draft = payload({"sku": "BIKE-1", "quantity": 2,
                     "annual_rate_percent": Decimal("3")})
    first = quick.calculate(draft, book)
    assert first["annual_partial_gbp"] == "108.00"
    book["rows"]["BIKE-1"]["price_pence"] = 300000
    updated = quick.calculate(draft, book)
    assert updated["annual_partial_gbp"] == "162.00"
    book["sha256"] = "b" * 64
    with pytest.raises(HTTPException) as exc:
        quick.calculate(draft, book)
    assert exc.value.status_code == 409


def test_parts_cannot_become_quote_machines_just_because_sage_has_price(book):
    draft = payload({"sku": "PART-1", "quantity": 1,
                     "annual_rate_percent": Decimal("3")})
    result = quick.calculate(draft, book)
    assert result["priced_line_count"] == 0
    assert result["complete_calculation"] is False
    assert result["equipment"][0]["annual_line_gbp"] is None
    assert any("spare-part classification" in issue for issue in result["issues"])


@pytest.mark.parametrize("sku", ["HOLD-1", "ZERO-1", "UNKNOWN-1"])
def test_held_zero_or_unknown_source_price_never_quoted(book, sku):
    result = quick.calculate(
        payload({"sku": sku, "quantity": 1,
                 "annual_rate_percent": Decimal("3")}), book)
    assert result["complete_calculation"] is False
    assert result["annual_partial_gbp"] == "0.00"
    assert result["customer_issue_enabled"] is False


def test_fixed_unit_annual_price_overrides_historic_rate_for_internal_review(book):
    result = quick.calculate(
        payload({"sku": "BIKE-1", "quantity": 2,
                 "annual_rate_percent": Decimal("5"),
                 "fixed_annual_unit_gbp": Decimal("129.99")}), book)
    assert result["equipment"][0]["annual_unit_gbp"] == "116.99"
    assert result["annual_partial_gbp"] == "233.98"
    assert result["term_partial_gbp"] == "701.94"


def test_invalid_discount_rate_quantity_and_fixed_money_fail_closed(book):
    with pytest.raises(HTTPException):
        quick.calculate(payload({"sku": "BIKE-1", "quantity": 0,
                                 "annual_rate_percent": Decimal("3")}), book)
    with pytest.raises(HTTPException):
        quick.calculate(payload({"sku": "BIKE-1", "quantity": 1,
                                 "annual_rate_percent": Decimal("201")}), book)
    with pytest.raises(HTTPException):
        quick.calculate(payload({"sku": "BIKE-1", "quantity": 1,
                                 "fixed_annual_unit_gbp": Decimal("10.005")}), book)
    q = payload({"sku": "BIKE-1", "quantity": 1,
                 "annual_rate_percent": Decimal("3")})
    q.discount_percent = Decimal("105")
    with pytest.raises(HTTPException):
        quick.calculate(q, book)


def test_search_requires_named_staff_filters_parts_and_missing_prices(monkeypatch, book):
    monkeypatch.setattr(quick, "active_book", lambda: book)
    monkeypatch.setattr(quick.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(quick.pilot_access, "current_role", lambda: "Coordinator")
    monkeypatch.setattr(quick.pilot_access, "actor", lambda default="": "fictional-coordinator")
    lookup = quick.search_equipment(q="TREAD", limit=20)
    assert len(lookup["results"]) == 1
    assert lookup["results"][0]["sku"] == "TREAD-1"
    assert lookup["results"][0]["maintenance_eligible"] is False
    assert lookup["price_book_revision"] == 7
    assert lookup["inventory_parts_excluded"] is True

    result = quick.quick_quote_preview(
        payload({"sku": "TREAD-1", "quantity": 1,
                 "annual_rate_percent": Decimal("3")}))
    assert result["complete_calculation"] is True
    monkeypatch.setattr(quick.pilot_access, "current_role", lambda: "Viewer")
    with pytest.raises(HTTPException) as exc:
        quick.quick_quote_preview(payload({
            "sku": "TREAD-1", "quantity": 1,
            "annual_rate_percent": Decimal("3")}))
    assert exc.value.status_code == 403


def test_quick_draft_requires_active_unified_price_book(monkeypatch):
    monkeypatch.setattr(quick, "active_book", lambda: None)
    monkeypatch.setattr(quick.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(quick.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(quick.pilot_access, "actor", lambda default="": "fictional-admin")
    with pytest.raises(HTTPException) as exc:
        quick.search_equipment(q="test", limit=10)
    assert exc.value.status_code == 503
