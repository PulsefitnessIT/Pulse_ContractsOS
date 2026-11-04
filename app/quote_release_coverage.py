"""Aggregate evidence-based SmartQuote coverage: what CAN be priced today?

This never exposes customer data, equipment prices or approvals. The output is
only a candidate worklist summary; staff must still verify the actual machine,
coverage, commercial tariff and approved customer terms for each quote.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException

from . import pilot_access
from .quote_pricing import (
    _line_price, _master_console_identity, source_snapshot,
)
from .quote_rrp_priority import (
    index as master_index, resolve, source_snapshot as august_snapshot,
)
from .quote_sage_reference import snapshot as sage_snapshot

router = APIRouter(prefix="/api/quoting", tags=["Source-based quotation coverage"])


def coverage(catalog, configs, pricing, master, sage=None):
    sku_rows = defaultdict(list)
    config_rows = defaultdict(list)
    for product in catalog:
        if isinstance(product, dict):
            sku = str(product.get("sku") or "").strip().upper()
            if sku:
                sku_rows[sku].append(product)
    for config in configs:
        if isinstance(config, dict):
            key = str(config.get("key") or "").strip().upper()
            if key:
                config_rows[key].append(config)
    rates = defaultdict(list)
    for rate in pricing.get("rates", []):
        if isinstance(rate, dict):
            rates[str(rate.get("group") or "")].append(rate)
    consoles = Counter(
        str(item.get("name") or "") for item in pricing.get("console_rules", [])
        if isinstance(item, dict)
    )
    indexed_master = master_index(master)
    results = Counter()
    for sku, products in sku_rows.items():
        if len(products) != 1:
            results["duplicate_v10_sku"] += 1
            continue
        product = products[0]
        code = str(product.get("service_key") or "").strip().upper()
        matches = config_rows.get(code, [])
        if len(matches) != 1:
            results["unmapped_or_ambiguous_service_configuration"] += 1
            continue
        config = matches[0]
        if config.get("eligible") != "Yes" or product.get("coverage_override") == "Not eligible":
            results["maintenance_eligibility_review"] += 1
            continue
        if product.get("match") == "Price list only - review":
            results["price_list_only_coverage_review"] += 1
            continue
        group = str(product.get("rate_group_override") or config.get("rate_group") or "")
        if group == "Manual Review" or len(rates.get(group, [])) != 1 or rates[group][0].get("status") != "Active":
            results["maintenance_rate_review"] += 1
            continue
        console = str(product.get("console") or "")
        if not console or consoles[console] != 1:
            results["unverified_v10_console"] += 1
            continue
        decision = resolve(sku, indexed_master, sage)
        if decision.get("rrp") is None:
            results["unresolved_master_or_sage_price"] += 1
            continue
        if decision.get("basis") == "august_2026_master_list_price":
            if not _master_console_identity(product, decision):
                results["master_description_or_console_requires_review"] += 1
                continue
        elif decision.get("basis") == "sage_exact_sku_price":
            if decision.get("sage_reference", {}).get("review_overdue"):
                results["sage_price_review_overdue"] += 1
                continue
        else:
            results["unsupported_price_basis"] += 1
            continue
        priced_product = {**product, "rrp": decision["rrp"]}
        amount, error = _line_price(
            priced_product, config, pricing, "Gold", 0, 1
        )
        if error or amount is None or amount.get("coverage_review"):
            results["unresolved_v10_pricing_or_terms"] += 1
            continue
        if decision["basis"] == "august_2026_master_list_price":
            results["source_price_candidate_august_master"] += 1
        else:
            results["source_price_candidate_sage"] += 1
    return {
        "v10_catalogue_rows": len(catalog),
        "distinct_v10_skus": len(sku_rows),
        "candidate_current_master_skus": results["source_price_candidate_august_master"],
        "candidate_sage_fallback_skus": results["source_price_candidate_sage"],
        "candidate_total": (
            results["source_price_candidate_august_master"]
            + results["source_price_candidate_sage"]
        ),
        "review_categories": {
            key: count for key, count in sorted(results.items())
            if not key.startswith("source_price_candidate_")
        },
        "tier_tested": "Gold; one unit; no discount; before commercial sign-off",
        "note": (
            "Candidate SKU counts are NOT approved contract prices. Each customer, "
            "equipment serial, real maintenance scope, tier and current source "
            "require independent checks and commercial approval."
        ),
        "no_customer_data_returned": True,
        "no_source_pricing_returned": True,
    }


@router.get("/candidate-coverage")
def candidate_coverage():
    if (not pilot_access.PILOT_MODE
            or pilot_access.current_role() not in ("Admin", "Coordinator")):
        raise HTTPException(403, "Signed-in quoting staff required.")
    products, configs, pricing, _ = source_snapshot()
    master = august_snapshot()
    sage = sage_snapshot()
    return coverage(products, configs, pricing, master, sage)
