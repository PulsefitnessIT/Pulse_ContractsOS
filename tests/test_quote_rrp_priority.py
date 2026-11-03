"""Fictional evidence for the user-approved Master -> Sage source priority."""
import gzip
import hashlib
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app import quote_rrp_priority as rrp


def staged(rows):
    return {
        "rows": rows,
        "source_date": rrp.MASTER_DATE,
        "source_file_sha256": rrp.MASTER_ORIGINAL_SHA256,
        "snapshot_sha256": "d" * 64,
    }


def line(code, amount, *, name="Fictional bike", console="No Console / N/A"):
    return {
        "sku": code, "rrp": amount, "name": name, "console": console,
        "sheet": "Fictional", "row": 17, "rrp_column": "List Price",
    }


def sage_source():
    return {
        "prices": {
            "MASTER-EXACT": {"sku": "MASTER-EXACT", "sales_price": 9999},
            "MASTER-CONFLICT": {"sku": "MASTER-CONFLICT", "sales_price": 9999},
            "NOT-ON-MASTER": {
                "sku": "NOT-ON-MASTER", "name": "Fictional fallback",
                "sales_price": 1550,
            },
        },
        "source_date": "2026-10-23", "review_due": "2027-10-23",
        "review_overdue": False, "source_file_sha256": "a" * 64,
        "source": "Sage Sales Price export — not an approved RRP",
    }


def test_exact_master_list_price_always_wins_over_sage():
    index = rrp.index(staged([line("MASTER-EXACT", 3000)]))
    result = rrp.resolve("master-exact", index, sage_source())
    assert result["basis"] == "august_2026_master_list_price"
    assert result["rrp"] == 3000
    assert "sage_reference" not in result
    assert result["review_required"] is True


def test_unchanged_duplicates_of_exact_master_row_are_safe_to_identify():
    row = line("MASTER-EXACT", "3000.00")
    result = rrp.resolve("MASTER-EXACT", rrp.index(staged([row, dict(row)])), sage_source())
    assert result["rrp"] == 3000.0
    assert len(result["master_rows"]) == 2


@pytest.mark.parametrize("rows,expected", [
    ([line("MASTER-CONFLICT", 200), line("MASTER-CONFLICT", 300)],
     "master_price_conflict"),
    ([line("MASTER-CONFLICT", None), line("MASTER-CONFLICT", 300)],
     "master_price_conflict"),
    ([line("MASTER-CONFLICT", 200, name="Bike"),
      line("MASTER-CONFLICT", 200, name="Treadmill")],
     "master_variant_conflict"),
    ([line("MASTER-CONFLICT", 200, console="Console X"),
      line("MASTER-CONFLICT", 200, console="Console Y")],
     "master_variant_conflict"),
])
def test_master_conflict_never_falls_through_to_sage(rows, expected):
    result = rrp.resolve("MASTER-CONFLICT", rrp.index(staged(rows)), sage_source())
    assert result["basis"] == expected
    assert result["rrp"] is None
    assert "sage_reference" not in result


def test_only_absent_master_sku_refers_to_exact_sage_sales_price():
    result = rrp.resolve("NOT-ON-MASTER", rrp.index(staged([
        line("MASTER-EXACT", 3200),
    ])), sage_source())
    assert result["basis"] == "sage_sales_price_fallback_review"
    assert result["rrp"] is None
    assert result["sage_reference"]["sage_sales_price"] == 1550
    assert result["sage_reference"]["approved_rrp"] is False
    assert result["sage_reference"]["quoted_annual_amount"] is None


def test_sage_not_loaded_is_missing_not_automatic_old_v10_rrp():
    result = rrp.resolve("MISSING", rrp.index(staged([])))
    assert result["basis"] == "not_on_august_master_or_usable_sage_export"
    assert result["rrp"] is None


def test_manipulated_source_metadata_rejected(tmp_path, monkeypatch):
    payload = {
        "source_file": rrp.MASTER_FILE, "source_date": rrp.MASTER_DATE,
        "source_sha256": "f" * 64,
        "rows": [line("MASTER-EXACT", 3000)],
    }
    path = tmp_path / "rrp_2026_source.json.gz"
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    monkeypatch.setenv(rrp.SOURCE_ENV, str(path))
    with pytest.raises(HTTPException) as err:
        rrp.source_snapshot()
    assert err.value.status_code == 503


def test_pinned_source_must_match_master_snapshot_bytes(tmp_path, monkeypatch):
    payload = {
        "source_file": rrp.MASTER_FILE, "source_date": rrp.MASTER_DATE,
        "source_sha256": rrp.MASTER_ORIGINAL_SHA256,
        "rows": [line("MASTER-EXACT", 3000)],
    }
    path = tmp_path / "rrp_2026_source.json.gz"
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    monkeypatch.setenv(rrp.SOURCE_ENV, str(path))
    from app import quote_pricing
    monkeypatch.setattr(quote_pricing, "source_snapshot",
                        lambda: ([], [], {}, {"catalog": "a" * 64,
                            "configs": "b" * 64, "pricing": "c" * 64}))
    captured = []
    def manifest(proofs):
        captured.append(proofs)
        return {"pinned": True, "matches": True}
    monkeypatch.setattr(quote_pricing, "source_manifest_status", manifest)
    result = rrp.source_snapshot()
    assert result["rows"][0]["sku"] == "MASTER-EXACT"
    assert captured[0]["august_2026_rrp"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source_file_sha256"] == rrp.MASTER_ORIGINAL_SHA256
