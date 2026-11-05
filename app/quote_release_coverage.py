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
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from . import pilot_access
from .data_readiness import safe_excel_csv_cell
from .quote_pricing import (
    _line_price, _master_console_identity, source_snapshot,
)
from .quote_rrp_priority import (
    _amount as source_amount, index as master_index, resolve,
    source_snapshot as august_snapshot,
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



def _reconciliation_rows(catalog, configs, pricing, master, sage=None):
    """Full cross-source evidence ledger, including non-maintenance Sage codes.

    Never equate Sage Sales Price with August Master List Price or silently
    convert an inventory/parts line into an eligible maintenance product.
    Source priority is determined solely by quote_rrp_priority.resolve().
    """
    assessment = {
        row["sku"]: row for row in
        candidate_assessments(catalog, configs, pricing, master, sage)
    }
    catalogue_counts = Counter(
        str(row.get("sku") or "").strip().upper()
        for row in catalog if isinstance(row, dict)
        and str(row.get("sku") or "").strip()
    )
    by_master = master_index(master)
    sage_by_code = defaultdict(list)
    if sage and isinstance(sage.get("prices"), dict):
        for code, record in sage["prices"].items():
            canonical = str(code or "").strip().upper()
            if canonical and isinstance(record, dict):
                sage_by_code[canonical].append(record)
    for sku in sorted(set(assessment) | set(by_master) | set(sage_by_code)):
        current = assessment.get(sku)
        master_rows = by_master.get(sku, [])
        raw_sage = sage_by_code.get(sku, [])
        sage_row = raw_sage[0] if len(raw_sage) == 1 else None
        sage_matches_code = bool(
            sage_row and str(sage_row.get("sku") or "").strip().upper() == sku
        )
        master_prices = {
            source_amount(row.get("rrp")) for row in master_rows
        }
        master_price = (
            next(iter(master_prices))
            if master_rows and len(master_prices) == 1
            else None
        )
        sage_amount = (
            source_amount(sage_row.get("sales_price"))
            if sage_matches_code else None
        )
        selected = resolve(sku, by_master, sage)
        basis = str(selected.get("basis") or "")
        selected_amount = source_amount(selected.get("rrp"))
        difference = (
            sage_amount - master_price
            if sage_amount is not None and master_price is not None else None
        )
        if current is not None:
            category = current["category"]
            action = (
                "No automatic change; source-only candidate still requires "
                "real equipment, package tariff and commercial quote approval."
                if current["potentially_quotable"] else
                NEXT_ACTION.get(category, "Review equipment source identity.")
            )
        elif master_rows:
            category = "master_only_not_in_v10_catalogue"
            action = (
                "Verify whether this current Master item is maintainable; "
                "do not add its source price to V10 until equipment and "
                "service configuration are approved."
            )
        else:
            category = "sage_only_inventory_not_v10_maintenance_equipment"
            action = (
                "Identify equipment versus spare parts or other inventory. "
                "Sage price alone does not authorise maintenance cover."
            )
        if len(raw_sage) > 1:
            category = "duplicate_sage_item_code"
            action = "Resolve duplicate Sage codes against the original export."
        elif sage_row and not sage_matches_code:
            category = "sage_item_code_identity_conflict"
            action = "Verify mismatched Sage item code before using its price."
        elif (master_rows and
                basis in ("master_price_conflict", "master_variant_conflict")
                and current is None):
            category = "master_price_or_variant_conflict"
            action = (
                "Resolve Master source price or equipment-console variant "
                "conflicts before this SKU can be used for any quotation."
            )
        elif sage_row and sage_matches_code and sage_amount is None:
            # Distinguish zero/missing from positive Sage prices; never use
            # these to create artificial zero-priced maintenance contracts.
            raw_value = sage_row.get("sales_price")
            try:
                zero = Decimal(str(raw_value)) == 0
            except (ValueError, ArithmeticError, TypeError):
                zero = False
            if current is None and not master_rows:
                category = "sage_zero_or_invalid_price"
                action = (
                    "Sage has a zero or invalid equipment price; verify and "
                    "classify, never use £0 as approved maintenance RRP."
                )
        yield {
            "SKU": sku,
            "V10 catalogue rows": catalogue_counts.get(sku, 0),
            "V10 description": current["description"] if current else "",
            "V10 console": current["console"] if current else "",
            "V10 service configuration": current["service_key"] if current else "",
            "Master source rows": len(master_rows),
            "Master source locations": "; ".join(
                str(row.get("sheet") or "")[:80] + " row " +
                str(row.get("row") or "")[:15] for row in master_rows[:15]
            ),
            "Master equipment name": str(master_rows[0].get("name") or "")[:350]
            if master_rows else "",
            "Master console": str(master_rows[0].get("console") or "")[:120]
            if master_rows else "",
            "Master list price GBP": (
                "; ".join(
                    str(value) if value is not None else "(not positive)"
                    for value in sorted(master_prices, key=lambda x: (x is None, str(x)))
                ) if master_rows else ""
            ),
            "Sage source rows": len(raw_sage),
            "Sage product name": str(sage_row.get("name") or "")[:350]
            if sage_row else "",
            "Sage product group": str(sage_row.get("group") or "")[:120]
            if sage_row else "",
            "Sage Sales Price GBP": (
                str(sage_row.get("sales_price")) if sage_matches_code else ""
            ),
            "Selected equipment price basis": basis,
            "Selected equipment price GBP": (
                str(selected_amount) if selected_amount is not None else ""
            ),
            "Sage less Master GBP": str(difference) if difference is not None else "",
            "Quote status": category,
            "Manager next action": action,
        }


def _reconciliation_data():
    products, configs, policy, hashes = source_snapshot()
    master = august_snapshot()
    sage = sage_snapshot()
    return products, configs, policy, hashes, master, sage


def _reconciliation_admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Protected SmartQuote Administrator required.")
    identity = pilot_access.actor("")
    if not isinstance(identity, str) or len(identity.strip()) < 2 or identity.strip() in (
        "Admin", "Coordinator", "Viewer"
    ):
        raise HTTPException(403, "A named SmartQuote Administrator is required.")


@router.get("/source-reconciliation/summary")
def source_reconciliation_summary():
    """Count every SKU from the three sources without declaring prices approved."""
    _reconciliation_admin()
    products, configs, policy, hashes, master, sage = _reconciliation_data()
    categories = Counter(
        row["Quote status"] for row in
        _reconciliation_rows(products, configs, policy, master, sage)
    )
    candidates = (
        categories["source_price_candidate_august_master"] +
        categories["source_price_candidate_sage"]
    )
    return {
        "sources": {
            "v10_catalogue_rows": len(products),
            "august_master_rows": len(master["rows"]),
            "sage_loaded": sage is not None,
            "sage_item_codes": len(sage["prices"]) if sage else None,
            "sage_export_date": sage["source_date"] if sage else None,
            "sage_review_overdue": sage["review_overdue"] if sage else None,
            "august_master_original_sha256": master["source_file_sha256"],
            "sage_export_sha256": sage["source_file_sha256"] if sage else None,
            "v10_source_sha256": hashes,
        },
        "distinct_source_skus": sum(categories.values()),
        "potentially_quotable_gold_skus": candidates,
        "review_categories": dict(sorted(categories.items())),
        "full_three_source_comparison_available": sage is not None,
        "commercial_tariffs_approved_by_this_report": False,
        "customer_quotes_approved_by_this_report": False,
        "warning": (
            "Exact source evidence only. Sage and August prices are different "
            "price bases; differences are informational, not automatic errors. "
            "Gold-candidate counts do not verify Silver/Platinum or customer terms."
        ),
    }


@router.get("/source-reconciliation.csv")
def source_reconciliation_csv():
    """Admin-only full SKU ledger with prices and review decisions, no customers."""
    _reconciliation_admin()
    products, configs, policy, _, master, sage = _reconciliation_data()
    if sage is None:
        raise HTTPException(
            409,
            "Import and activate the full Sage export before downloading "
            "the three-source reconciliation report."
        )
    fields = (
        "SKU", "V10 catalogue rows", "V10 description", "V10 console",
        "V10 service configuration", "Master source rows",
        "Master source locations", "Master equipment name", "Master console",
        "Master list price GBP", "Sage source rows", "Sage product name",
        "Sage product group", "Sage Sales Price GBP",
        "Selected equipment price basis", "Selected equipment price GBP",
        "Sage less Master GBP", "Quote status", "Manager next action",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in _reconciliation_rows(
        products, configs, policy, master, sage
    ):
        writer.writerow({
            key: safe_excel_csv_cell(row[key]) for key in fields
        })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                'attachment; filename="Pulse_SmartQuote_Sage_Master_Full_Reconciliation.csv"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
