"""Pricing parity coverage tests use fictional equipment; never real RRPs."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.parity_source_coverage import select_source_coverage
from scripts.check_v10_price_parity import (
    run, source_fingerprints, require_source_unchanged,
)


def source():
    catalogue = [
        {"sku": "EXAMPLE-B1", "rrp": 200, "service_key": "BIKE|A", "console": "Console A"},
        {"sku": "EXAMPLE-B2", "rrp": 210, "service_key": "BIKE|A", "console": "Console A"},
        {"sku": "EXAMPLE-B3", "rrp": 300, "service_key": "BIKE|B", "console": "Console B"},
        {"sku": "EXAMPLE-S1", "rrp": 400, "service_key": "STEP|A", "console": "Console A"},
    ]
    configs = [
        {"key": "BIKE|A", "rate_group": "Group A", "eligible": "Yes"},
        {"key": "BIKE|B", "rate_group": "Group A", "eligible": "Yes"},
        {"key": "STEP|A", "rate_group": "Group B", "eligible": "Yes"},
    ]
    pricing = {
        "rates": [
            {"group": "Group A", "status": "Active", "standard": .03},
            {"group": "Group B", "status": "Active", "standard": .04},
        ],
        "console_rules": [
            {"name": "Console A", "multiplier": 1, "uplift": 0},
            {"name": "Console B", "multiplier": 1, "uplift": 0},
        ],
    }
    return catalogue, configs, pricing


def test_eligible_families_all_selected_before_extra_skus():
    c, cfg, policy = source()
    samples, summary = select_source_coverage(c, cfg, policy, maximum=3)
    assert len(samples) == 3
    assert summary["source_skus_eligible_for_parity_sampling"] == 4
    assert summary["eligible_rate_console_families"] == 3
    assert summary["sampled_rate_console_families"] == 3
    assert summary["unsampled_rate_console_families"] == 0
    assert summary["all_eligible_rate_console_families_sampled"] is True
    assert summary["source_rule_identity_conflicts"] is False
    assert len({(sample[3], sample[4]) for sample in samples}) == 3
    assert "EXAMPLE-B2" not in [sample[0] for sample in samples]
    assert "EXAMPLE-B1" not in json.dumps(summary)
    assert "200" not in json.dumps(summary)


def test_limited_sample_cannot_pass_source_family_coverage():
    c, cfg, policy = source()
    samples, summary = select_source_coverage(c, cfg, policy, maximum=2)
    assert len(samples) == 2
    assert summary["eligible_rate_console_families"] == 3
    assert summary["unsampled_rate_console_families"] == 1
    assert summary["all_eligible_rate_console_families_sampled"] is False


def test_selection_independent_of_catalogue_row_order():
    c, cfg, policy = source()
    first, result = select_source_coverage(c, cfg, policy, maximum=3)
    reverse, result_rev = select_source_coverage(list(reversed(c)), cfg, policy, maximum=3)
    assert [x[0] for x in first] == [x[0] for x in reverse]
    assert result == result_rev


def test_duplicate_rate_group_cannot_be_silently_selected():
    c, cfg, policy = source()
    policy["rates"].append({**policy["rates"][0], "standard": .90})
    samples, result = select_source_coverage(c, cfg, policy, maximum=10)
    assert result["pricing_source_rule_identity_issues"]["duplicate_rate_group_source_rows"] == 2
    assert result["source_rule_identity_conflicts"] is True
    assert result["skipped_source_sku_groups_by_reason"]["ambiguous_rate_group"] == 3
    assert [x[0] for x in samples] == ["EXAMPLE-S1"]


def test_duplicate_console_rule_blocks_source_family():
    c, cfg, policy = source()
    policy["console_rules"].append({"name": "Console A", "multiplier": 44})
    samples, result = select_source_coverage(c, cfg, policy, maximum=10)
    assert result["source_rule_identity_conflicts"] is True
    assert result["skipped_source_sku_groups_by_reason"]["ambiguous_console_rule"] == 3
    assert [x[0] for x in samples] == ["EXAMPLE-B3"]


def test_missing_sku_invalid_rrp_and_duplicate_sku_reported_without_prices():
    c, cfg, policy = source()
    c.append({"name": "No SKU", "rrp": 50})
    c.append({"sku": "EXAMPLE-B3", "rrp": 500, "service_key": "BIKE|B"})
    c[0]["rrp"] = "200"
    samples, result = select_source_coverage(c, cfg, policy, maximum=20)
    assert result["source_catalogue_rows_missing_sku"] == 1
    assert result["skipped_source_sku_groups_by_reason"]["duplicate_source_sku"] == 1
    assert result["skipped_source_sku_groups_by_reason"]["rrp_missing_or_invalid"] == 1
    assert result["source_exclusions_require_separate_reconciliation"] is True
    assert all(x[0] not in ("EXAMPLE-B1", "EXAMPLE-B3") for x in samples)
    assert "EXAMPLE-" not in json.dumps(result)


@pytest.mark.parametrize("maximum", [0, -1, 3001, True, 1.5])
def test_invalid_sampling_limit_is_rejected(maximum):
    c, cfg, policy = source()
    with pytest.raises(ValueError, match="1–3,000"):
        select_source_coverage(c, cfg, policy, maximum=maximum)


def test_pinned_source_stability_detects_midrun_price_change(tmp_path):
    paths = []
    for name, data in (
        ("catalog.json", [{"sku": "DEMO", "rrp": 100}]),
        ("configs.json", []),
        ("pricing.json", {"rates": []}),
    ):
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        paths.append(p)
    hashes = source_fingerprints(paths)
    require_source_unchanged(paths, hashes)
    paths[0].write_text('[{"sku":"DEMO","rrp":999999}]', encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed during parity testing"):
        require_source_unchanged(paths, hashes)


def test_strict_parity_refuses_unpinned_source_before_importing_engine(tmp_path, monkeypatch):
    root = tmp_path / "untrusted-v10"
    data = root / "data"
    data.mkdir(parents=True)
    (root / "engine.py").write_text(
        "raise AssertionError('An unpinned engine must never be imported')"
    )
    c, cfg, policy = source()
    for name, rows in (
        ("catalog.json", c), ("configs.json", cfg), ("pricing.json", policy)
    ):
        (data / name).write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.delenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST", raising=False)
    with pytest.raises(RuntimeError, match="Pin and verify"):
        run(root, maximum=3)


def test_intentionally_ineligible_equipment_not_confused_with_broken_source():
    catalogue, configs, pricing = source()
    configs[0]["eligible"] = "No"
    samples, summary = select_source_coverage(catalogue, configs, pricing, 10)
    assert summary["skipped_source_sku_groups_by_reason"]["explicitly_excluded_from_cover"] == 2
    assert summary["unresolved_numeric_source_exclusions"] == 0
    assert summary["source_exclusions_require_separate_reconciliation"] is True
    assert len(samples) == 2


def test_unresolved_missing_rrp_is_a_release_blocker_not_an_intentional_exclusion():
    catalogue, configs, pricing = source()
    catalogue[0]["rrp"] = None
    _, summary = select_source_coverage(catalogue, configs, pricing, 10)
    assert summary["unresolved_numeric_source_exclusions"] == 1
    assert summary["skipped_source_sku_groups_by_reason"]["rrp_missing_or_invalid"] == 1
    assert summary["source_rule_identity_conflicts"] is False


def test_unverified_cover_is_still_an_unresolved_parity_omission():
    catalogue, configs, pricing = source()
    catalogue[0]["match"] = "Price list only - review"
    _, summary = select_source_coverage(catalogue, configs, pricing, 10)
    assert summary["skipped_source_sku_groups_by_reason"]["coverage_needs_approval"] == 1
    assert summary["unresolved_numeric_source_exclusions"] == 1
