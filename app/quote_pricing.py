"""V10-source, exact-SKU maintenance pricing PREVIEW inside Contracts OS.

Uses privately provisioned SmartQuote catalog/config/pricing JSON files.
Executes the verbatim original V10 engine.price_line arithmetic with isolated
source-specific globals for the exact selected source SKU and standard tier.
No guesses from historic, Sage or approximate console models; no approvals or
Sicon writes. NEVER use this response as an issued customer quotation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from .quote_drafts import get_draft
from ._smartquote_staged_v10 import stage_summary
from ._smartquote_price_line_v10 import original_v10_price_line
from .quote_sage_reference import snapshot as sage_snapshot, reference as sage_reference
from .pilot_access import actor

router = APIRouter(prefix="/api/quoting", tags=["Unified SmartQuote price preview"])
SOURCE_FILES = {
    "catalog": ("PULSE_SMARTQUOTE_CATALOG_JSON", 20 * 1024 * 1024),
    "configs": ("PULSE_SMARTQUOTE_CONFIGS_JSON", 12 * 1024 * 1024),
    "pricing": ("PULSE_SMARTQUOTE_PRICING_JSON", 1024 * 1024),
}


def _money(value):
    return float(Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))


def _load_file(path: Path, maximum: int):
    try:
        stat = path.stat()
        if not path.is_file() or not (2 <= stat.st_size <= maximum):
            raise OSError("unavailable/invalid size")
        data = path.read_bytes()
        return data, stat
    except OSError as exc:
        raise HTTPException(503, "A required SmartQuote pricing source is missing or invalid.") from exc


def source_manifest_status(proofs):
    """Verify immutable V10 source fingerprints against a private IT manifest.

    This proves file identity only. It never asserts RRP/tariff approval.
    """
    raw_path = os.environ.get("PULSE_SMARTQUOTE_SOURCE_MANIFEST", "").strip()
    if not raw_path:
        from .quote_source_setup import manifest_status as in_app_source_status
        local = in_app_source_status(proofs)
        if local is not None:
            return local
        return {
            "pinned": False, "matches": False,
            "message": "Source fingerprints are not pinned to an IT or Admin-reviewed manifest.",
            "commercially_approved": False,
        }
    path = Path(raw_path).expanduser().resolve()
    try:
        if path.suffix.lower() != ".json" or not path.is_file() or not 2 <= path.stat().st_size <= 16384:
            raise ValueError("Missing or oversized source manifest")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("sha256"), dict):
            raise ValueError("Expected a SHA-256 manifest")
        hashes = manifest["sha256"]
        for name in SOURCE_FILES:
            expected = hashes.get(name)
            if (not isinstance(expected, str) or len(expected) != 64 or
                any(c not in "0123456789abcdef" for c in expected.lower())
                or expected.lower() != proofs[name]):
                raise ValueError("Source fingerprint does not match the pinned manifest")
        # Reconciliation callers supply optional source fingerprints too.
        # A staged legacy/history file must match the *same* private manifest;
        # a previously pinned optional file must not quietly disappear.
        for name in ("legacy_crosswalk", "historical_identity", "august_2026_rrp"):
            if name not in proofs:
                continue  # Pricing-only preview verifies the three core files.
            observed = proofs[name]
            expected = hashes.get(name)
            if observed is None and expected is None:
                continue
            if (not isinstance(observed, str) or not isinstance(expected, str)
                or len(expected) != 64 or len(observed) != 64
                or any(c not in "0123456789abcdef" for c in expected.lower())
                or expected.lower() != observed.lower()):
                raise ValueError("Optional identity source is missing or changed")
        return {
            "pinned": True, "matches": True,
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "effective_date_as_recorded": str(manifest.get("effective_date") or "")[:32],
            "owner_as_recorded": str(manifest.get("owner") or "")[:120],
            "commercially_approved": False,
            "message": "Pricing source files match the privately pinned manifest; tariff approval is separate.",
        }
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Staged SmartQuote pricing data does not match its required source manifest.") from exc


@lru_cache(maxsize=2)
def _parse_source(source_fingerprint, contents):
    # The cached source and fingerprint are deployment-controlled, never user input.
    try:
        return tuple(json.loads(x.decode("utf-8")) for x in contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "A staged SmartQuote price-source JSON file is invalid.") from exc


def source_snapshot():
    contents = []
    proofs = []
    config = [os.environ.get(env, "").strip()
              for env, _ in SOURCE_FILES.values()]
    if not any(config):
        # An authenticated pilot Admin may have staged the four exact V10
        # source files in the private Contracts OS database.
        from .quote_source_setup import active_source
        bundle = active_source()
        if bundle is None:
            raise HTTPException(503,
                "SmartQuote source is missing. Upload the four-file V10 ZIP in Source Setup.")
        contents = [bundle["files"][kind] for kind in SOURCE_FILES]
        proofs = [bundle["hashes"][kind] for kind in SOURCE_FILES]
    else:
        for kind, (environment, maximum) in SOURCE_FILES.items():
            name = os.environ.get(environment, "").strip()
            if not name:
                raise HTTPException(503,
                    f"Incomplete IT source staging: {environment} is missing.")
            path = Path(name).expanduser().resolve()
            if path.suffix.lower() != ".json":
                raise HTTPException(503, f"Invalid staged SmartQuote {kind} file.")
            data, _ = _load_file(path, maximum)
            contents.append(data)
            proofs.append(hashlib.sha256(data).hexdigest())
    source_manifest_status(dict(zip(SOURCE_FILES, proofs)))
    catalog, configs, pricing = _parse_source(tuple(proofs), tuple(contents))
    if not isinstance(catalog, list) or len(catalog) > 30000 or not isinstance(configs, list):
        raise HTTPException(503, "Unexpected SmartQuote V10 catalogue format.")
    if (not isinstance(pricing, dict) or pricing.get("currency") != "GBP"
        or not isinstance(pricing.get("rates"), list)
        or not isinstance(pricing.get("tiers"), dict)
        or not isinstance(pricing.get("console_rules"), list)):
        raise HTTPException(503, "Unexpected SmartQuote V10 pricing policy.")
    return catalog, configs, pricing, dict(zip(SOURCE_FILES, proofs))


def _positive_number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) and 0 < n <= 100000000 else None


def _line_price(product, config, pricing, tier, discount, qty):
    """V10 price_line standard-level arithmetic, including unit-first rounding."""
    sku = str(product.get("sku") or "").strip().upper()
    group = str(product.get("rate_group_override") or config.get("rate_group") or "")
    rate_matches = [
        row for row in pricing["rates"]
        if isinstance(row, dict) and str(row.get("group") or "") == group
    ]
    if group == "Manual Review" or not rate_matches:
        return None, "No verified source maintenance rate group."
    if len(rate_matches) != 1:
        return None, "Conflicting original V10 maintenance rate group; resolve source duplicates."
    rate = rate_matches[0]
    if product.get("coverage_override") == "Not eligible":
        return None, "Product is excluded from maintenance cover."
    if config.get("eligible") == "No":
        return None, "Service configuration is excluded from maintenance."
    source_rrp = product.get("rrp")
    # V10 price_line requires an actual JSON number; numeric-looking text
    # must be reconciled in the master instead of quietly becoming a price.
    rrp = _positive_number(source_rrp) if type(source_rrp) in (int, float) else None
    if rrp is None:
        return None, "No valid current RRP in the exact catalogue SKU."
    coefficient = _positive_number(rate.get("standard"))
    multiplier = _positive_number(pricing.get("tiers", {}).get(tier))
    if coefficient is None or multiplier is None:
        return None, "Unknown tariff or maintenance package rate."
    console_name = str(product.get("console") or "")
    console_matches = [
        row for row in pricing.get("console_rules", [])
        if isinstance(row, dict) and str(row.get("name") or "") == console_name
    ]
    if console_name and len(console_matches) > 1:
        return None, "Conflicting original V10 console rules; resolve source duplicates."
    known_console = bool(console_matches)
    override = product.get("console_multiplier_override")
    # V10 live_catalogue_option sets console_pricing = override or 1, which
    # takes precedence over the console rule's configured multiplier.
    try:
        console_factor = float(override or 1)
    except (TypeError, ValueError, OverflowError):
        return None, "Invalid source console multiplier."
    if not math.isfinite(console_factor) or console_factor <= 0:
        return None, "Invalid source console multiplier."
    # Full numeric arithmetic is executed by the original V10 price_line
    # function, copied verbatim. We control eligibility, SKU, source RRP,
    # console identity and approval independently from the quoted amount.
    # No global tariff state is mutated when two coordinators preview at once.
    original_selected = {
        "rrp": rrp, "rate_group": group, "console": console_name,
        "console_pricing": console_factor, "eligible": config.get("eligible"),
        "price_origin": "exact-v10-catalogue-preview",
        "pricing_rule": "Original V10 exact source SKU tariff",
    }
    try:
        v10_amount = original_v10_price_line(
            {"qty": qty, "selected": original_selected}, "Standard",
            tier, discount, pricing
        )
        if not v10_amount:
            return None, "Original SmartQuote V10 engine did not price this source item."
        unit = float(v10_amount["unit"])
        annual = float(v10_amount["annual"])
        minimum_total = float(v10_amount["minimum"])
    except (ValueError, TypeError, ArithmeticError, KeyError, OverflowError, InvalidOperation):
        return None, "SmartQuote source tariff is not a valid numeric rule."
    if not all(math.isfinite(n) for n in (unit, annual, minimum_total)):
        return None, "Non-finite calculated amount."
    reasons = []
    if config.get("eligible") != "Yes":
        reasons.append("Service configuration eligibility requires review.")
    if product.get("match") == "Price list only - review":
        reasons.append("Source SKU is price-list-only; coverage not verified.")
    if rate.get("status") != "Active":
        reasons.append("Rate group is not marked Active in the source.")
    if not console_name or not known_console:
        reasons.append("Console configuration is unverified in the source rules.")
    if annual < minimum_total - 0.01:
        reasons.append("Discount makes this line fall below its source minimum.")
    # Even a perfect match does not override the source's provisional policy.
    return {
        "sku": sku, "description": str(product.get("name") or "")[:250],
        "model": str(product.get("model") or "")[:120],
        "console": console_name, "quantity": qty,
        "rrp": _money(rrp), "source_rate_group": group,
        "source_standard_rate": coefficient,
        "unit_annual": unit, "annual": annual,
        "minimum_annual": minimum_total,
        "source_eligibility": str(config.get("eligible") or ""),
        "coverage_review": reasons,
        "review_required": bool(reasons),
        "rate_status": str(rate.get("status") or ""),
        "price_basis": "original-v10-price_line-standard-tariff-preview",
        "source_engine": "original SmartQuote V10 price_line arithmetic",
    }, None


def _source_title(value):
    """Compare original equipment descriptions without guessing machine families."""
    return " ".join(str(value or "").casefold().strip().split())


def _master_console_identity(product, master):
    """Evidence-based bridge between two different console naming systems.

    The August master describes physical screens (e.g. '10.1-inch cardio
    tactile-key'); original V10 uses internal console group labels
    ('Console 5 (Series 2)'). Their text is not designed to be equal.

    Only a UNIQUE exact SKU with an IDENTICAL full equipment description and
    an unqualified master console description can overcome this *terminology*
    difference. Unknown/legacy/verify markers, conflicting product names
    and missing master labels still block commercial issuance. We never infer
    a console type from the product family or from a partial string.
    """
    master_console=str(master.get("master_console") or "").strip()
    catalogue_console=str(product.get("console") or "").strip()
    master_name=str(master.get("master_name") or "").strip()
    product_name=str(product.get("name") or "").strip()
    if not master_console or not catalogue_console:
        return False
    if master_console.casefold()==catalogue_console.casefold():
        return True
    if not master_name or not product_name or _source_title(master_name)!=_source_title(product_name):
        return False
    # Both sources show an identical full product description and a UNIQUE
    # exact SKU. For a machine with no console described at all, V10 records
    # "No Console / N/A" while the August extract says "Console not stated".
    # This is a *terminology* difference, NOT proof of an installed option.
    # Reject anything that hints at a screen, electronics or control console;
    # even exact title/price matches cannot approve that physical variant.
    if (master_console.casefold() == "console not stated"
            and catalogue_console.casefold() == "no console / n/a"):
        import re
        if re.search(
            r"\b(?:console|screen|touchscreen|display|lcd|monitor|tablet|"
            r"smartcard|smart-card|pm5|nfc|touch[- ]?key)\b",
            master_name, flags=re.IGNORECASE
        ):
            return False
        return True
    # The only physical-description / V10-group equivalences observed
    # unambiguously in the original 2026 source's exact SKU and full name.
    # Do not generalise from similar-looking equipment or from a console
    # substring. Strength variants labelled "verify" remain under review.
    verified_taxonomy = {
        "7-inch cardio tactile-key": "Console 3.5 (Series 1)",
        "10.1-inch cardio tactile-key": "Console 5 (Series 2)",
        "10.1-inch cardio touchscreen": "Console 8 (Series 3 Mini)",
        "18.5-inch cardio touchscreen": "Console 6 (Series 3)",
    }
    return verified_taxonomy.get(master_console.casefold()) == catalogue_console


def preview(draft, catalog, configs, pricing, hashes, master_by_sku=None, sage_source=None,
            overrides=None, august_source=None):
    tier = draft["tier"]
    term = int(draft.get("term_years", 1))
    discount = float(draft.get("discount_percent", 0))
    if tier not in pricing.get("tiers", {}) or not 1 <= term <= 5 or not 0 <= discount <= 100:
        raise HTTPException(422, "Unsupported SmartQuote cover, term or discount.")
    by_sku = {}
    for row in catalog:
        if isinstance(row, dict):
            code = str(row.get("sku") or "").strip().upper()
            if code:
                by_sku.setdefault(code, []).append(row)
    by_config = {}
    for row in configs:
        if isinstance(row, dict):
            key = str(row.get("key") or "").strip().upper()
            if key:
                by_config.setdefault(key, []).append(row)
    lines, issues, total = [], [], Decimal("0.00")
    for index, asset in enumerate(draft.get("equipment", []), 1):
        code = str(asset.get("item_code") or "").strip().upper()
        line = {"line": index, "item_code": code, "quantity": asset.get("quantity"), "priced": False}
        decision = None
        if master_by_sku is not None:
            from .quote_rrp_priority import resolve
            decision = resolve(code, master_by_sku, sage_source)
            if overrides and code in overrides:
                from .quote_price_overrides import effective
                decision = effective(decision, overrides[code], august_source or {}, sage_source)
                line["price_override"] = {
                    "revision": decision.get("override_revision"),
                    "status": decision.get("override_status", "not_applied"),
                    "source_price_updated_at": decision.get("source_price_updated_at"),
                }
            line["rrp_source"] = decision["basis"]
            line["master_rows"] = decision.get("master_rows", [])
            # Both sources are accepted equipment price bases under the
            # business-confirmed policy: August Master for current SKUs,
            # exact Sage Sales Price for legacy SKUs absent from Master.
            # They can legitimately differ. Preserve both for audit, without
            # inventing an extra price-difference approval threshold.
            # The V10 cover multipliers, minimums and terms are independent.
            if sage_source and decision["basis"] in (
                "august_2026_master_list_price", "managed_price_override"
            ):
                sage_evidence = sage_reference(code, sage_source)
                if sage_evidence:
                    chosen_price = Decimal(str(decision.get("rrp") or 0))
                    sage_price = Decimal(str(sage_evidence["sage_sales_price"]))
                    if chosen_price > 0:
                        difference = sage_price - chosen_price
                        percent = difference * Decimal("100") / chosen_price
                        line["sage_reference"] = sage_evidence
                        line["source_price_comparison"] = {
                            "selected_equipment_price_gbp": _money(chosen_price),
                            "sage_sales_price_gbp": _money(sage_price),
                            "sage_minus_selected_gbp": _money(difference),
                            "percentage_difference": _money(percent),
                            "requires_explicit_ack": False,
                            "comparison_for_information_only": True,
                            "source_values_may_have_different_price_bases": True,
                            "not_a_new_or_approved_tariff": True,
                        }
            if "sage_reference" in decision:
                line["sage_reference"] = decision["sage_reference"]
        if not code:
            line["exception"] = "No exact source SKU entered."
        elif len(by_sku.get(code, [])) != 1:
            line["exception"] = "SKU absent from catalogue or conflicts with duplicate records."
        elif decision is not None and decision["rrp"] is None:
            line["exception"] = {
                "master_price_conflict": "The August 2026 master has conflicting or invalid List Prices; Sage must not override it.",
                "master_variant_conflict": "The August 2026 master has conflicting equipment variants; confirm the exact configuration.",
                "stale_price_override": "Source price list changed since the local price revision. Administrator must review and reapply it.",
                "sage_exact_sku_price": "An exact Sage equipment price is available but cannot be used with this equipment configuration.",
                "sage_unpriced_exact_sku": "Exact Sage product exists but is priced at £0. An administrator must set a valid price before quotation preview.",
            }.get(decision["basis"], "No verified August 2026 master List Price or usable Sage price reference.")
        else:
            product = by_sku[code][0]
            if decision is not None:
                # Never mutate the original historical V10 source catalogue.
                product = {**product, "rrp": decision["rrp"]}
            key = str(product.get("service_key") or "").strip().upper()
            if len(by_config.get(key, [])) != 1:
                line["exception"] = "No unambiguous original V10 service configuration."
            else:
                amount, reason = _line_price(
                    product, by_config[key][0], pricing, tier, discount, asset["quantity"]
                )
                if reason:
                    line["exception"] = reason
                else:
                    line.update(amount)
                    if decision is not None:
                        line["rrp_source"] = decision["basis"]
                        line["rrp_source_approved"] = (
                            decision["basis"] == "managed_price_override"
                        )
                        line["source_list_price_review_required"] = False
                        line["source_equipment_price_basis_accepted"] = (
                            decision["basis"] in (
                                "august_2026_master_list_price",
                                "sage_exact_sku_price", "managed_price_override"
                            )
                        )
                        if decision["basis"] == "august_2026_master_list_price":
                            verified_console = str(decision.get("master_console") or "").strip()
                            catalogue_console = str(product.get("console") or "").strip()
                            line["master_console_evidence"] = {
                                "august_master_label": verified_console,
                                "v10_service_console_group": catalogue_console,
                                "master_name": str(decision.get("master_name") or "")[:250],
                                "exact_full_name_match": (
                                    bool(decision.get("master_name")) and
                                    _source_title(decision.get("master_name")) ==
                                    _source_title(product.get("name"))
                                ),
                                "identity_reconciled": _master_console_identity(product, decision),
                            }
                            if not _master_console_identity(product, decision):
                                line["coverage_review"].append(
                                    "August master console variant does not exactly match the V10 equipment record."
                                )
                        if decision["basis"] == "sage_exact_sku_price":
                            line["coverage_review"].append(
                                "Price taken from exact Sage item code; maintenance tariff approval remains separate."
                            )
                        elif decision["basis"] == "managed_price_override":
                            line["coverage_review"].append(
                                "Administrator-adjusted equipment price; source revision recorded in price audit."
                            )
                        else:
                            line["coverage_review"].append(
                                "August 2026 source List Price used; commercial maintenance tariff approval remains separate."
                            )
                        line["review_required"] = True
                    line["priced"] = True
                    total += Decimal(str(amount["annual"]))
                    if amount["review_required"]:
                        issues.append(f"Line {index}: " + "; ".join(amount["coverage_review"]))
        if not line["priced"]:
            issues.append(f"Line {index}: {line.get('exception')}")
        lines.append(line)
    # Original SmartQuote V10 stage_summary uses inclusive ACT/ACT calendar
    # days and rounds each machine LINE once, including leap years.
    source_assets = [
        {"id": "line-" + str(index), "code": str(a.get("item_code") or ""),
         "name": str(a.get("description") or ""), "qty": a["quantity"],
         "cover_start": str(a.get("cover_start") or "")}
        for index, a in enumerate(draft.get("equipment", []), 1)
    ]
    price_by_id = {
        "line-" + str(line["line"]): {"annual": line["annual"]}
        for line in lines if line["priced"]
    }
    staged = stage_summary({
        "contract_start": draft.get("contract_start") or "",
        "contract_end": draft.get("contract_end") or "",
        "assets": source_assets,
    }, price_by_id)
    stage_by_id = {item["id"]: item for item in staged["lines"]}
    for line in lines:
        period = stage_by_id.get("line-" + str(line["line"]))
        if period:
            line["cover_start"] = period["cover_start"]
            line["cover_end"] = period["cover_end"]
            line["period_charge"] = period["period_charge"]
            line["period_days"] = period["days"]
    issues.extend(staged["issues"])
    # With only one contract date, no term amount may be represented as £0.
    term_partial = (
        staged["total"] if staged["enabled"] else _money(total * term)
    )
    if not any(item["priced"] for item in lines):
        # Never show a £0 contractual value when everything is simply unpriced.
        term_partial = None
    source_status = str(pricing.get("pricing_status") or "Not commercially approved")
    issues.append("Source tariff policy: " + source_status)
    issues.append("Source-derived preview only; verify current RRP, scope, exclusions, and authorised terms.")
    if not lines:
        issues.append("Add equipment lines.")
    return {
        "draft_id": draft["id"], "revision": draft["revision"], "tier": tier,
        "discount_percent": discount, "term_years": term,
        "currency": "GBP", "line_count": len(lines),
        "priced_count": sum(1 for item in lines if item["priced"]),
        "annual_partial": _money(total),
        "monthly_partial": _money(total / 12),
        "term_partial": term_partial,
        "complete_price": bool(lines) and all(item["priced"] for item in lines),
        "lines": lines, "issues": issues,
        "staged": staged,
        "source_pricing_status": source_status,
        "source_snapshot": pricing.get("source_snapshot"),
        "source_sha256": hashes,
        "source_manifest": source_manifest_status(hashes),
        "rrp_source_priority": (
            "24 August 2026 Master List Price > exact Sage price for other equipment; administrator revisions are audited"
            if master_by_sku is not None else "Original V10 synthetic/source-only price preview"
        ),
        "commercially_approved": False,
        "issue_quote_enabled": False,
        "contract_setup_enabled": False,
        "label": "INTERNAL SOURCE-DERIVED PRICING PREVIEW — NOT AN APPROVED QUOTATION",
    }


@router.get("/rrp-source/status")
def rrp_source_status():
    """Read-only source coverage, without exposing per-item prices."""
    actor()
    from .quote_rrp_priority import (
        source_snapshot as august_snapshot, summarize_priority
    )
    catalog, _, _, _ = source_snapshot()
    master = august_snapshot()
    try:
        sage = sage_snapshot()
    except HTTPException:
        sage = None
    return summarize_priority(master, catalog, sage)


@router.get("/drafts/{draft_id}/price-preview")
def draft_price_preview(draft_id: str):
    actor()
    draft = get_draft(draft_id)
    catalog, configs, pricing, fingerprints = source_snapshot()
    from .quote_rrp_priority import source_snapshot as august_snapshot, index
    # The customer-facing route must never silently revert to the older V10
    # catalogue's embedded RRP when the current source has not been staged.
    master = august_snapshot()
    try:
        sage = sage_snapshot()
    except HTTPException:
        sage = None  # Report missing Sage without contaminating any RRP.
    from .quote_price_overrides import active_overrides
    codes = [str(item.get("item_code") or "") for item in draft.get("equipment", [])]
    result = preview(
        draft, catalog, configs, pricing, fingerprints,
        master_by_sku=index(master), sage_source=sage,
        overrides=active_overrides(codes), august_source=master,
    )
    result["rrp_master"] = {
        "source": "Full Master Price List 24-08-2026.xlsx — List Price",
        "source_date": master["source_date"],
        "original_file_sha256": master["source_file_sha256"],
        "staged_snapshot_sha256": master["snapshot_sha256"],
        "commercially_approved": False,
    }
    result["sage_reference_status"] = {
        "loaded": sage is not None,
        "source_date": sage["source_date"] if sage else None,
        "review_overdue": sage["review_overdue"] if sage else None,
        "used_as_automatic_rrp": sage is not None,
        "used_for_quotation": any(
            item.get("priced") and item.get("rrp_source") == "sage_exact_sku_price"
            for item in result["lines"]
        ),
    }
    result["rrp_source_priority"] = (
        "Business-confirmed equipment price basis: August 2026 Master for current "
        "machines; exact Sage Sales Price for legacy machines absent from the Master. "
        "Both are accepted inputs to the V10 maintenance calculation. Audited "
        "administrator corrections remain available; Silver/Gold/Platinum rate "
        "rules, terms and customer quote approval are separate."
    )
    return result


@router.get("/drafts/{draft_id}/tier-comparison")
def draft_tier_comparison(draft_id: str):
    """Side-by-side Silver/Gold/Platinum INTERNAL price comparison.

    Reprice the SAME saved equipment/serials, term, discount, source snapshots
    and reviewed overrides. Do not persist a new draft, approve a maintenance
    tariff, or issue a customer quote. Missing equipment prices are visibly
    incomplete; no partial value is described as a final contract amount.
    """
    actor()
    draft = get_draft(draft_id)
    catalogue, configs, policy, fingerprints = source_snapshot()
    from .quote_rrp_priority import source_snapshot as august_snapshot, index
    from .quote_price_overrides import active_overrides

    august = august_snapshot()
    try:
        sage = sage_snapshot()
    except HTTPException:
        sage = None
    codes = [str(item.get("item_code") or "") for item in draft.get("equipment", [])]
    price_overrides = active_overrides(codes)
    indexed = index(august)
    options = []
    for tier in ("Silver", "Gold", "Platinum"):
        if tier not in policy.get("tiers", {}):
            options.append({
                "tier": tier, "available": False, "complete_price": False,
                "annual_gbp": None, "monthly_gbp": None, "term_gbp": None,
                "priced_lines": 0, "total_lines": len(draft.get("equipment", [])),
                "blockers": ["This tier has no original V10 price rule."],
            })
            continue
        quoted = preview(
            {**draft, "tier": tier}, catalogue, configs, policy, fingerprints,
            master_by_sku=indexed, sage_source=sage,
            overrides=price_overrides, august_source=august,
        )
        # Reuse the EXACT per-equipment commercial release checks for all
        # tiers, rather than inventing weaker comparison-only criteria.
        # This includes overdue Sage fallback, eligibility and minimum price.
        from .quote_customer_issuance import _errors
        blockers = _errors({**draft, "tier": tier}, quoted)
        complete = not blockers
        options.append({
            "tier": tier,
            "available": True,
            "complete_price": complete,
            "annual_gbp": quoted["annual_partial"] if complete else None,
            "monthly_gbp": quoted["monthly_partial"] if complete else None,
            "term_gbp": quoted["term_partial"] if complete else None,
            "priced_lines": quoted["priced_count"],
            "total_lines": quoted["line_count"],
            "blockers": blockers if not complete else [],
        })
    return {
        "draft_id": draft["id"],
        "revision": draft["revision"],
        "selected_tier": draft["tier"],
        "discount_percent": draft["discount_percent"],
        "term_years": draft["term_years"],
        "currency": "GBP",
        "options": options,
        "source_sha256": fingerprints,
        "august_master_sha256": august["snapshot_sha256"],
        "sage_source_sha256": sage["source_file_sha256"] if sage else None,
        "indicative_only": True,
        "commercially_approved": False,
        "customer_quote_issued": False,
        "note": "Internal comparison of identical equipment and contract terms. Save the chosen tier, review equipment scope, and obtain approved tariff, terms and manager sign-off before issuing a customer PDF.",
    }
