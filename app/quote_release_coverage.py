"""Evidence-based SmartQuote catalogue readiness and administrator review queue.

This diagnoses which exact V10 equipment SKUs are potentially quotable using
approved-source identity rules. It never approves commercial tariffs, quotes
or actual equipment coverage. The CSV is Admin-only, excludes customer records
and financial amounts, and is safe to open in spreadsheet applications.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from . import pilot_access
from .data_readiness import safe_excel_csv_cell
from .quote_pricing import (
    _line_price, _master_console_identity, source_snapshot,
)
from .quote_rrp_priority import (
    index as master_index, resolve, source_snapshot as august_snapshot,
)
from .quote_sage_reference import snapshot as sage_snapshot

router = APIRouter(prefix="/api/quoting", tags=["Source-based quotation coverage"])

NEXT_ACTION = {
    "duplicate_v10_sku": "Resolve duplicate catalogue SKU and confirm the actual model.",
    "unmapped_or_ambiguous_service_configuration": "Map this SKU to exactly one eligible V10 service configuration.",
    "maintenance_eligibility_review": "Review equipment maintenance eligibility and exclusions.",
    "price_list_only_coverage_review": "Verify the machine is eligible for maintenance cover, not solely listed for sale.",
    "maintenance_rate_review": "Confirm its unique, active maintenance rate group.",
    "unverified_v10_console": "Verify the console identity and matching V10 console rule.",
    "unresolved_master_or_sage_price": "Resolve the exact equipment SKU in the current Master or Sage price list.",
    "master_description_or_console_requires_review": "Reconcile the equipment name and console against the August Master.",
    "sage_price_review_overdue": "Obtain and activate a fresh Sage Sales Price export.",
    "unsupported_price_basis": "Review the selected equipment price provenance.",
    "unresolved_v10_pricing_or_terms": "Resolve V10 service tariff, minimum or cover calculation exceptions.",
}


def candidate_assessments(catalog, configs, pricing, master, sage=None):
    """One deterministic, source-only assessment per distinct V10 catalogue SKU."""
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

    for sku in sorted(sku_rows):
        products = sku_rows[sku]
        product = products[0]
        description = str(product.get("name") or "")[:350]
        service_key = str(product.get("service_key") or "")[:160]
        console_name = str(product.get("console") or "")[:120]
        price_basis = ""
        category = ""

        if len(products) != 1:
            category = "duplicate_v10_sku"
        else:
            code = service_key.strip().upper()
            matches = config_rows.get(code, [])
            if len(matches) != 1:
                category = "unmapped_or_ambiguous_service_configuration"
            else:
                config = matches[0]
                if (config.get("eligible") != "Yes"
                        or product.get("coverage_override") == "Not eligible"):
                    category = "maintenance_eligibility_review"
                elif product.get("match") == "Price list only - review":
                    category = "price_list_only_coverage_review"
                else:
                    group = str(product.get("rate_group_override")
                                or config.get("rate_group") or "")
                    if (group == "Manual Review"
                            or len(rates.get(group, [])) != 1
                            or rates[group][0].get("status") != "Active"):
                        category = "maintenance_rate_review"
                    elif not console_name or consoles[console_name] != 1:
                        category = "unverified_v10_console"
                    else:
                        decision = resolve(sku, indexed_master, sage)
                        price_basis = str(decision.get("basis") or "")
                        if decision.get("rrp") is None:
                            category = "unresolved_master_or_sage_price"
                        elif price_basis == "august_2026_master_list_price":
                            if not _master_console_identity(product, decision):
                                category = "master_description_or_console_requires_review"
                        elif price_basis == "sage_exact_sku_price":
                            if decision.get("sage_reference", {}).get("review_overdue"):
                                category = "sage_price_review_overdue"
                        else:
                            category = "unsupported_price_basis"
                        if not category:
                            amount, error = _line_price(
                                {**product, "rrp": decision["rrp"]},
                                config, pricing, "Gold", 0, 1,
                            )
                            if error or amount is None or amount.get("coverage_review"):
                                category = "unresolved_v10_pricing_or_terms"
                            elif price_basis == "august_2026_master_list_price":
                                category = "source_price_candidate_august_master"
                            else:
                                category = "source_price_candidate_sage"

        yield {
            "sku": sku, "description": description,
            "service_key": service_key, "console": console_name,
            "price_basis": price_basis,
            "category": category,
            "potentially_quotable": category.startswith("source_price_candidate_"),
        }


def coverage(catalog, configs, pricing, master, sage=None):
    results = Counter(
        row["category"]
        for row in candidate_assessments(catalog, configs, pricing, master, sage)
    )
    distinct = len({
        str(product.get("sku") or "").strip().upper()
        for product in catalog
        if isinstance(product, dict) and str(product.get("sku") or "").strip()
    })
    return {
        "v10_catalogue_rows": len(catalog),
        "distinct_v10_skus": distinct,
        "candidate_current_master_skus": results["source_price_candidate_august_master"],
        "candidate_sage_fallback_skus": results["source_price_candidate_sage"],
        "candidate_total": (
            results["source_price_candidate_august_master"]
            + results["source_price_candidate_sage"]
        ),
        "review_categories": {
            key: count for key, count in sorted(results.items())
            if not key.startswith("source_price_candidate_") and count
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


@router.get("/candidate-review.csv")
def candidate_review_csv():
    """Admin-only actionable catalogue clean-up, never actual price figures."""
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Only a signed-in SmartQuote Administrator may export the catalogue review.")
    identity = pilot_access.actor("")
    if not isinstance(identity, str) or len(identity.strip()) < 2:
        raise HTTPException(403, "A named SmartQuote Administrator is required.")

    products, configs, pricing, _ = source_snapshot()
    master = august_snapshot()
    sage = sage_snapshot()
    fields = ("SKU", "Equipment", "V10 service configuration", "Console",
              "Price source status", "Review category", "Recommended next action")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(fields)
    for item in candidate_assessments(products, configs, pricing, master, sage):
        if item["potentially_quotable"]:
            continue
        values = (
            item["sku"], item["description"], item["service_key"], item["console"],
            item["price_basis"], item["category"],
            NEXT_ACTION.get(item["category"], "Investigate the verified V10 source records."),
        )
        writer.writerow([safe_excel_csv_cell(value) for value in values])
    return Response(
        content="\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="Pulse_SmartQuote_Catalogue_Review.csv"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
    )
