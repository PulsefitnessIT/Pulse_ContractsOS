"""V10-source, exact-SKU maintenance pricing PREVIEW inside Contracts OS.

Uses privately provisioned SmartQuote catalog/config/pricing JSON files. Copies
the arithmetic of V10 engine.price_line for the selected standard tariff only.
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


@lru_cache(maxsize=2)
def _parse_source(source_fingerprint, contents):
    # The cached source and fingerprint are deployment-controlled, never user input.
    try:
        return tuple(json.loads(x.decode("utf-8")) for x in contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "A staged SmartQuote price-source JSON file is invalid.") from exc


def source_snapshot():
    files = {}
    contents = []
    proofs = []
    for kind, (environment, maximum) in SOURCE_FILES.items():
        name = os.environ.get(environment, "").strip()
        if not name:
            raise HTTPException(503, f"Pricing preview unavailable: IT must stage {environment}.")
        path = Path(name).expanduser().resolve()
        if path.suffix.lower() != ".json":
            raise HTTPException(503, f"Invalid staged SmartQuote {kind} file.")
        data, _ = _load_file(path, maximum)
        files[kind] = path
        contents.append(data)
        proofs.append(hashlib.sha256(data).hexdigest())
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
    rates = {str(item.get("group")): item for item in pricing["rates"] if isinstance(item, dict)}
    rate = rates.get(group)
    if not rate or group == "Manual Review":
        return None, "No verified source maintenance rate group."
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
    rules = {str(c.get("name")): c for c in pricing.get("console_rules", []) if isinstance(c, dict)}
    console = rules.get(console_name, {"multiplier": 1, "uplift": 0})
    override = product.get("console_multiplier_override")
    # V10 live_catalogue_option sets console_pricing = override or 1, which
    # takes precedence over the console rule's configured multiplier.
    try:
        console_factor = float(override or 1)
    except (TypeError, ValueError, OverflowError):
        return None, "Invalid source console multiplier."
    if not math.isfinite(console_factor) or console_factor <= 0:
        return None, "Invalid source console multiplier."
    try:
        uplift = float(console.get("uplift", 0))
        base_uplift = float(rate.get("uplift", 0))
        minimum = float(rate["minimum"])
        base = float(rrp) * float(coefficient)
        annualunit = (base * console_factor + uplift + base_uplift) * multiplier
        unit = _money(annualunit * (1 - discount / 100))
        annual = _money(unit * qty)
        minimum_total = (
            (float(rrp) * minimum * console_factor + uplift + base_uplift)
            * multiplier * qty
        )
        minimum_total = _money(minimum_total)
    except (ValueError, TypeError, ArithmeticError, KeyError):
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
    if not console_name or console_name not in rules:
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
        "price_basis": "exact-v10-sku-standard-tariff-preview",
    }, None


def preview(draft, catalog, configs, pricing, hashes):
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
        if not code:
            line["exception"] = "No exact source SKU entered."
        elif len(by_sku.get(code, [])) != 1:
            line["exception"] = "SKU absent from catalogue or conflicts with duplicate records."
        else:
            product = by_sku[code][0]
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
        "commercially_approved": False,
        "issue_quote_enabled": False,
        "contract_setup_enabled": False,
        "label": "INTERNAL SOURCE-DERIVED PRICING PREVIEW — NOT AN APPROVED QUOTATION",
    }


@router.get("/drafts/{draft_id}/price-preview")
def draft_price_preview(draft_id: str):
    actor()
    draft = get_draft(draft_id)
    catalog, configs, pricing, fingerprints = source_snapshot()
    result = preview(draft, catalog, configs, pricing, fingerprints)
    # Sage Sales Price is advisory ONLY, not a verified Master Price List RRP.
    # Never use this source to replace an existing/conflicting master SKU or
    # increase approved/partial quotation totals.
    missing = [line for line in result["lines"] if not line["priced"]]
    if missing:
        catalogue_codes = {
            str(p.get("sku") or "").strip().upper()
            for p in catalog if isinstance(p, dict)
        }
        try:
            source = sage_snapshot()
        except HTTPException:
            source = None
            result["issues"].append("The original Sage reference source could not be verified.")
        if source is not None:
            for line in missing:
                if line["item_code"] in catalogue_codes:
                    continue
                info = sage_reference(line["item_code"], source)
                if info:
                    line["sage_reference"] = info
                    result["issues"].append(
                        f"Line {line['line']}: dated Sage Sales Price reference exists but "
                        "is excluded from maintenance quote totals until a verified Master RRP is approved."
                    )
            result["sage_reference_status"] = {
                "source_date": source["source_date"],
                "review_overdue": source["review_overdue"],
                "used_for_quotation": False,
            }
    return result
