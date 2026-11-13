"""Private reconciliation readiness requires real staged evidence and no prices."""
from copy import deepcopy
import json

import pytest

from scripts.smartquote_source_readiness import build_readiness, write_private_report


def prepared_report():
    return {
        "summary": {
            "catalogue_source_rows": 4,
            "catalogue_rows_missing_sku": 0,
            "distinct_skus": 4,
            "duplicate_sku_groups": 0,
            "catalogue_rows_requiring_review": 0,
            "pricing_policy_source_rows": {"rates": 1, "console_rules": 1},
            "policy_rule_rows_requiring_review": 0,
            "legacy_source_rows": 2,
            "legacy_source_rows_requiring_review": 0,
            "legacy_missing_target_mappings": 0,
            "historical_source_variants": 2,
            "historical_alias_source_entries": 2,
            "historical_identity_rows_requiring_review": 0,
            "historical_source_staged": True,
        },
        "source_sha256": {
            "catalog": "a"*64, "configs": "b"*64, "pricing": "c"*64,
            "legacy_crosswalk": "d"*64, "historical_identity": "e"*64,
        },
        "worklist": [{"sku": "SECRET-SKU", "rrp": 9876543}],
        "customer": "PRIVATE CUSTOMER",
        "pricing_policy": {"rrp": 50000},
    }


def verified_manifest():
    return {"pinned": True, "matches": True, "owner": "Private person"}


def test_report_allowlists_aggregate_evidence_and_never_claims_quote_approval(tmp_path):
    report = prepared_report()
    copy = deepcopy(report)
    result = build_readiness(report, verified_manifest())
    assert report == copy
    assert result["ready_to_run_private_numeric_parity"] is True
    assert result["actual_v10_numeric_parity_completed"] is False
    assert result["customer_quote_issue_enabled"] is False
    assert result["commercial_tariff_approved"] is False
    output = tmp_path / "readiness.json"
    write_private_report(output, result)
    content = output.read_text(encoding="utf-8")
    assert "SECRET-SKU" not in content
    assert "PRIVATE CUSTOMER" not in content
    assert "Private person" not in content
    assert "9876543" not in content
    assert "rrp" not in content.lower()
    assert json.loads(content) == result
    with pytest.raises(ValueError):
        write_private_report(output, result)


@pytest.mark.parametrize("edit", [
    {"legacy_source_rows": None},
    {"historical_source_staged": False},
    {"historical_source_variants": 0},
    {"catalogue_source_rows": 0},
    {"legacy_source_rows": 0},
    {"catalogue_rows_requiring_review": 1},
    {"policy_rule_rows_requiring_review": 1},
    {"legacy_source_rows_requiring_review": 1},
    {"historical_identity_rows_requiring_review": 1},
])
def test_missing_or_unresolved_source_blocks_parity_readiness(edit):
    report = prepared_report()
    report["summary"].update(edit)
    result = build_readiness(report, verified_manifest())
    assert result["ready_to_run_private_numeric_parity"] is False
    assert result["customer_quote_issue_enabled"] is False


def test_unpinned_source_blocks_parity_even_if_no_exception():
    report = prepared_report()
    result = build_readiness(report, {"pinned": False, "matches": False})
    assert result["ready_to_run_private_numeric_parity"] is False
    assert result["source_manifest_hash_verified"] is False


def test_empty_rate_or_console_rule_table_blocks_parity():
    for field in ("rates", "console_rules"):
        report = prepared_report()
        report["summary"]["pricing_policy_source_rows"][field] = 0
        result = build_readiness(report, verified_manifest())
        assert result["ready_to_run_private_numeric_parity"] is False
