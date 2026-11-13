"""Deterministic, price-free coverage selection for original SmartQuote V10 parity.

A numerical match on a few machines must not be described as full pricing
parity when source rate/console families were not sampled. No source SKU,
price or customer details are returned in the aggregate public report.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict


def _code(value):
    return str(value or "").strip().upper()


def select_source_coverage(catalog, configs, pricing, maximum):
    """Choose distinct (rate-group, console) families before repeated items.

    `samples` is private in-memory evidence for the pricing comparison. The
    returned `summary` deliberately contains aggregate counts only.
    """
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 3000:
        raise ValueError("Select 1–3,000 original source SKU groups.")
    if not isinstance(catalog, list) or not isinstance(configs, list) or not isinstance(pricing, dict):
        raise ValueError("Unexpected original V10 catalogue, configuration or pricing source.")
    rates = pricing.get("rates")
    consoles = pricing.get("console_rules")
    if not isinstance(rates, list) or not isinstance(consoles, list):
        raise ValueError("Original V10 tariff and console tables are required.")

    config_by_key = defaultdict(list)
    for row in configs:
        if isinstance(row, dict) and _code(row.get("key")):
            config_by_key[_code(row["key"])].append(row)
    sku_by_code = defaultdict(list)
    unidentified_rows = 0
    for row in catalog:
        if not isinstance(row, dict) or not _code(row.get("sku")):
            unidentified_rows += 1
        else:
            sku_by_code[_code(row["sku"])].append(row)

    rate_by_group = defaultdict(list)
    for rate in rates:
        if isinstance(rate, dict) and str(rate.get("group") or "").strip():
            rate_by_group[str(rate["group"])].append(rate)
    console_by_name = defaultdict(list)
    for console in consoles:
        if isinstance(console, dict) and str(console.get("name") or "").strip():
            console_by_name[str(console["name"])].append(console)

    rule_errors = {
        "duplicate_rate_group_source_rows": sum(
            len(rows) for rows in rate_by_group.values() if len(rows) > 1
        ),
        "duplicate_console_rule_source_rows": sum(
            len(rows) for rows in console_by_name.values() if len(rows) > 1
        ),
        "missing_or_invalid_rate_source_rows": sum(
            not isinstance(row, dict) or not str(row.get("group") or "").strip()
            for row in rates
        ),
        "missing_or_invalid_console_source_rows": sum(
            not isinstance(row, dict) or not str(row.get("name") or "").strip()
            for row in consoles
        ),
    }

    family_candidates = defaultdict(list)
    excluded = Counter()
    for code, rows in sorted(sku_by_code.items()):
        if len(rows) != 1:
            excluded["duplicate_source_sku"] += 1
            continue
        product = rows[0]
        matches = config_by_key.get(_code(product.get("service_key")), [])
        if len(matches) != 1:
            excluded["missing_or_ambiguous_config"] += 1
            continue
        config = matches[0]
        if (
            config.get("eligible") == "No"
            or product.get("coverage_override") == "Not eligible"
        ):
            excluded["explicitly_excluded_from_cover"] += 1
            continue
        if (
            config.get("eligible") != "Yes"
            or product.get("match") == "Price list only - review"
        ):
            excluded["coverage_needs_approval"] += 1
            continue
        group = str(product.get("rate_group_override") or config.get("rate_group") or "")
        rate_matches = rate_by_group.get(group, [])
        if group == "Manual Review" or not rate_matches:
            excluded["rate_needs_approval"] += 1
            continue
        if len(rate_matches) != 1:
            excluded["ambiguous_rate_group"] += 1
            continue
        if rate_matches[0].get("status") != "Active":
            excluded["rate_needs_approval"] += 1
            continue
        console_name = str(product.get("console") or "")
        console_matches = console_by_name.get(console_name, [])
        if not console_name or not console_matches:
            excluded["console_unverified"] += 1
            continue
        if len(console_matches) != 1:
            excluded["ambiguous_console_rule"] += 1
            continue
        rrp = product.get("rrp")
        if (
            type(rrp) not in (int, float)
            or not math.isfinite(float(rrp))
            or not 0 < float(rrp) <= 1e8
        ):
            excluded["rrp_missing_or_invalid"] += 1
            continue
        family_candidates[(group, console_name)].append(
            (code, product, config, group, console_name)
        )

    # Cover each source family first; only then add more rows for depth.
    # `sorted` makes the selection independent of source-file row ordering.
    for entries in family_candidates.values():
        entries.sort(key=lambda item: item[0])
    families = sorted(family_candidates)
    samples = []
    while len(samples) < maximum:
        added = False
        for family in families:
            if family_candidates[family]:
                samples.append(family_candidates[family].pop(0))
                added = True
                if len(samples) >= maximum:
                    break
        if not added:
            break

    sampled_families = {(item[3], item[4]) for item in samples}
    all_families = set(families)
    eligible_skus = sum(len(rows) for rows in family_candidates.values()) + len(samples)
    summary = {
        "source_sku_groups": len(sku_by_code),
        "source_catalogue_rows_missing_sku": unidentified_rows,
        "source_skus_eligible_for_parity_sampling": eligible_skus,
        "skipped_source_sku_groups_by_reason": dict(sorted(excluded.items())),
        "pricing_source_rule_identity_issues": rule_errors,
        "eligible_rate_console_families": len(all_families),
        "sampled_rate_console_families": len(sampled_families),
        "unsampled_rate_console_families": len(all_families - sampled_families),
        "all_eligible_rate_console_families_sampled": bool(all_families) and sampled_families == all_families,
        "source_exclusions_require_separate_reconciliation": bool(excluded or unidentified_rows),
        # Explicitly excluded equipment has no valid maintenance price to compare.
        # Every other skipped group requires review before calling parity clean.
        "unresolved_numeric_source_exclusions": sum(
            number for reason, number in excluded.items()
            if reason != "explicitly_excluded_from_cover"
        ),
        "source_rule_identity_conflicts": any(rule_errors.values()),
    }
    return samples, summary
