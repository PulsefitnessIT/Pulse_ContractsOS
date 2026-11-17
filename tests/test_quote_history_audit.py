"""Fictional SmartQuote historical identity evidence: no real machines or prices."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from app.quote_history_audit import analyze_historical_identity
from app import quote_reconciliation


def clean_source():
    return {
        "records": {
            "EXAMPLE-OLD-A": {
                "sku": "EXAMPLE-OLD-A", "model": "Bike-1",
                "console": "Example V1", "rrp": 99999,
            },
            "EXAMPLE-OLD-B": {
                "model": "Bike-2", "console": "Example V2",
                "historic_price": 3.5,
            },
        },
        "aliases": {"PREVIOUS-CODE": ["EXAMPLE-OLD-A"]},
    }


def test_clean_records_are_identity_only_and_not_price_approved():
    source = clean_source()
    before = deepcopy(source)
    result = analyze_historical_identity(source)
    assert source == before
    assert result["staged"] is True
    assert result["summary"]["historical_source_records"] == 2
    assert result["summary"]["historical_alias_source_entries"] == 1
    assert result["summary"]["historical_identity_rows_requiring_review"] == 0
    assert result["worklist"] == []
    assert "rrp" not in str(result).lower()
    assert "99999" not in str(result)


def test_unstaged_history_is_not_a_clean_index():
    result = analyze_historical_identity(None)
    assert result["staged"] is False
    assert result["summary"]["historical_identity_rows_requiring_review"] is None


def test_history_flags_normalized_collision_and_record_sku_disagreement():
    source = clean_source()
    source["records"]["example-old-a"] = {
        "sku": "DIFFERENT-CODE", "console": "Example V3"
    }
    source["records"]["INVALID?CODE"] = None
    audit = analyze_historical_identity(source)
    reasons = audit["summary"]["historical_identity_flag_counts"]
    assert reasons["duplicate_normalized_historical_code"] == 2
    assert reasons["historical_sku_disagrees_with_record_key"] == 1
    assert reasons["invalid_historical_record_key"] == 1
    assert reasons["invalid_historical_record"] == 1
    assert reasons["ambiguous_historical_alias_target"] == 1


def test_aliases_flag_dangling_empty_duplicate_and_multivariant():
    source = clean_source()
    source["aliases"].update({
        "DANGLING": ["GONE"],
        "EMPTY": [],
        "TWICE": ["EXAMPLE-OLD-A", "EXAMPLE-OLD-A"],
        "MANY": ["EXAMPLE-OLD-A", "EXAMPLE-OLD-B"],
        "BAD": "EXAMPLE-OLD-A",
        "ODD": [123],
    })
    audit = analyze_historical_identity(source)
    reasons = audit["summary"]["historical_identity_flag_counts"]
    for expected in (
        "dangling_historical_alias_target",
        "invalid_or_empty_historical_alias_targets",
        "duplicate_historical_alias_target",
        "multi_variant_historical_alias",
        "invalid_historical_alias_target",
    ):
        assert reasons[expected] >= 1
    assert all(row["approved_price"] is None for row in audit["worklist"])


def test_case_colliding_alias_keys_are_flagged_individually():
    source = clean_source()
    source["aliases"]["previous-code"] = ["EXAMPLE-OLD-B"]
    audit = analyze_historical_identity(source)
    assert audit["summary"]["historical_identity_flag_counts"][
        "duplicate_normalized_historical_alias"
    ] == 2


def test_historical_worklist_is_paged_read_only_and_unstaged_fails(monkeypatch):
    source = clean_source()
    source["aliases"]["BAD-LOOKUP"] = ["MISSING"]
    data = quote_reconciliation.reconcile(
        catalog=[], configs=[],
        pricing={"rates": [], "console_rules": []},
        fingerprint={"catalog": "f" * 64}, history=source,
    )
    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-staff")
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: data)
    page = quote_reconciliation.reconciliation_historical_worklist(
        q="BAD", issue="dangling_historical_alias_target", limit=5, offset=0
    )
    assert page["total"] == 1
    assert page["items"][0]["source_key"] == "BAD-LOOKUP"
    assert page["price_approved"] is False
    assert all("rrp" not in item and "historic_price" not in item for item in page["items"])

    absent = quote_reconciliation.reconcile(
        catalog=[], configs=[],
        pricing={"rates": [], "console_rules": []},
        fingerprint={"catalog": "f" * 64},
    )
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: absent)
    with pytest.raises(HTTPException) as err:
        quote_reconciliation.reconciliation_historical_worklist(
            q="", issue="", limit=5, offset=0
        )
    assert err.value.status_code == 503
