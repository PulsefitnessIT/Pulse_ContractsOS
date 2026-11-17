"""No customer data: regression checks for offline unified price source audit."""
import csv

from scripts.audit_unified_prices import audit


def sample(tmp_path, rows):
    dest = tmp_path / "price.csv"
    with dest.open("w", newline="", encoding="utf-8") as stream:
        w = csv.writer(stream)
        w.writerow(("SKU", "Price GBP", "Price Source", "Price Status",
                    "Master Reference GBP", "Sage Reference GBP"))
        w.writerows(rows)
    return dest


def test_expected_source_precedence_and_unpriced_conflicts(tmp_path):
    path = sample(tmp_path, [
        ("MACHINE-A", "3500.00", "Master 24-08-2026", "PRICE REFERENCE - cover not approved", "3500.00", "2400.00"),
        ("LEGACY-B", "1299.50", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "", "1299.50"),
        ("PART-C", "0", "Sage imported reference", "UNPRICED - do not quote", "", "0"),
        ("CONFLICT-D", "", "Master - conflict", "HOLD - Master conflicting prices", "", "1900"),
    ])
    r = audit(path)
    assert r["passed"] is True
    assert r["counts"]["unique_codes"] == 4
    assert r["counts"]["master_conflicted"] == 1
    assert r["counts"]["sage_unpriced"] == 1
    assert audit(path, snapshot_2026=True)["passed"] is False


def test_selected_master_price_must_match_master_reference(tmp_path):
    r = audit(sample(tmp_path, [
        ("MACHINE-A", "100", "Master 24-08-2026", "PRICE REFERENCE - cover not approved", "110", "100")
    ]))
    assert r["passed"] is False


def test_sage_fallback_must_have_no_master_reference(tmp_path):
    r = audit(sample(tmp_path, [
        ("MACHINE-A", "100", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "150", "100")
    ]))
    assert r["passed"] is False


def test_unpriced_and_conflict_cannot_get_released_as_valid_amounts(tmp_path):
    r = audit(sample(tmp_path, [
        ("ZERO", "0", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "", "0"),
        ("CONFLICT", "200", "Master - conflict", "HOLD - Master conflicting prices", "", "180"),
    ]))
    assert r["passed"] is False
    assert r["counts"]["errors"] >= 2


def test_duplicate_and_bad_money_are_rejected(tmp_path):
    r = audit(sample(tmp_path, [
        ("A", "100", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "", "100"),
        ("A", "101", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "", "101"),
        ("B", "NaN", "Sage imported reference", "PRICE REFERENCE - equipment eligibility unverified", "", "NaN"),
    ]))
    assert r["passed"] is False
    assert r["counts"]["errors"] == 2
