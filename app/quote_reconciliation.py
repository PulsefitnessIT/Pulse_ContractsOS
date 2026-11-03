"""Evidence-only canonical SmartQuote equipment reconciliation.

One consolidated SKU/service/legacy review surface from PRIVATE V10 snapshots.
This cannot promote historical prices, source RRP, Sage Sales Price, a rate
marked Active or a matching model into commercial approval.

The original customer catalogue/masters are never shipped to GitHub.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .pilot_access import actor, current_role
from .quote_pricing import source_snapshot, _positive_number, source_manifest_status

router = APIRouter(prefix="/api/quoting/catalogue", tags=["V10 equipment reconciliation"])

# All optional data sources are private on the staff server. An absent source
# means 'not checked', never "all historical items reconciled".
OPTIONAL_FILES = {
    "legacy_crosswalk": ("PULSE_SMARTQUOTE_LEGACY_JSON", 8 * 1024 * 1024),
    "historical_identity": ("PULSE_SMARTQUOTE_HISTORICAL_INDEX", 35 * 1024 * 1024),
}
LEGACY_IGNORE = {"", "0", "6", "25", "N/A"}
SKU_REGEX = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,99}$")


def _code(value):
    return str(value or "").strip().upper()


def _private_optional_source(kind):
    variable, maximum = OPTIONAL_FILES[kind]
    file = os.environ.get(variable, "").strip()
    if not file:
        return None, None
    path = Path(file).expanduser().resolve()
    if path.suffix.lower() not in (".json", ".gz"):
        raise HTTPException(503, f"{kind} source is not a JSON evidence file.")
    try:
        if not path.is_file() or not 2 <= path.stat().st_size <= maximum:
            raise OSError("missing or oversized")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if path.suffix.lower() == ".gz":
            # Bound inflated content regardless of compressed source size.
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            decoded = decoder.decompress(raw, 80 * 1024 * 1024 + 1)
            if (len(decoded) > 80 * 1024 * 1024 or not decoder.eof
                or decoder.unused_data or decoder.unconsumed_tail):
                raise ValueError("Incomplete or oversized compressed identity evidence.")
            raw = decoded
        payload = json.loads(raw.decode("utf-8"))
        if kind == "legacy_crosswalk" and (not isinstance(payload, list) or len(payload) > 80000):
            raise ValueError("Unexpected original legacy crosswalk.")
        if kind == "historical_identity" and (
            not isinstance(payload, dict) or not isinstance(payload.get("records"), dict)
            or len(payload["records"]) > 150000
            or not isinstance(payload.get("aliases", {}), dict)
        ):
            raise ValueError("Unexpected original historical identity index.")
        return payload, digest
    except (OSError, ValueError, UnicodeError, zlib.error, json.JSONDecodeError) as exc:
        raise HTTPException(503, f"{kind} staged source failed integrity checks.") from exc


def _review_reasons(item, configs, pricing):
    """Exact evidence checks; never manufacture a contract price."""
    reasons = []
    code = _code(item.get("sku"))
    if not SKU_REGEX.fullmatch(code):
        reasons.append("invalid_sku")
    # Numeric strings and booleans are not authoritative signed-off RRPs.
    original_rrp = item.get("rrp")
    if type(original_rrp) not in (int, float) or _positive_number(original_rrp) is None:
        reasons.append("missing_or_invalid_current_rrp")
    service_key = _code(item.get("service_key"))
    matches = configs.get(service_key, ())
    config = matches[0] if len(matches) == 1 else None
    if not service_key or config is None:
        reasons.append("missing_or_ambiguous_service_configuration")
    if config is not None:
        if (item.get("coverage_override") == "Not eligible" or
                config.get("eligible") == "No"):
            reasons.append("excluded_from_cover")
        elif config.get("eligible") != "Yes":
            reasons.append("service_eligibility_not_confirmed")
    if item.get("match") == "Price list only - review":
        reasons.append("price_list_only_coverage_review")
    # Never collapse multiple competing policy rows into a last-wins dict.
    group = str(item.get("rate_group_override") or
                ((config or {}).get("rate_group")) or "")
    rate_matches = [
        r for r in pricing.get("rates", []) if isinstance(r, dict)
        and str(r.get("group") or "") == group
    ]
    if group == "Manual Review" or not group or not rate_matches:
        reasons.append("rate_group_unmapped")
    elif len(rate_matches) > 1:
        reasons.append("ambiguous_maintenance_rate_group")
    elif rate_matches[0].get("status") != "Active":
        reasons.append("source_rate_requires_review")
    console = str(item.get("console") or "")
    console_matches = [
        r for r in pricing.get("console_rules", []) if isinstance(r, dict)
        and str(r.get("name") or "") == console
    ]
    if not console or not console_matches:
        reasons.append("console_rule_unverified")
    elif len(console_matches) > 1:
        reasons.append("ambiguous_console_rule")
    return reasons


def policy_reconciliation(pricing):
    """Read-only tariff identity audit: rule names and positions, never rates."""
    worklist = []
    flags = Counter()
    for section, identity_key, duplicate_reason, missing_reason in (
        ("rates", "group", "duplicate_rate_group", "missing_rate_group_name"),
        ("console_rules", "name", "duplicate_console_rule", "missing_console_rule_name"),
    ):
        rows = pricing.get(section, [])
        counts = Counter(
            str(row.get(identity_key) or "").strip()
            for row in rows if isinstance(row, dict)
            and str(row.get(identity_key) or "").strip()
        )
        for position, row in enumerate(rows, start=1):
            key = str(row.get(identity_key) or "").strip() if isinstance(row, dict) else ""
            issues = []
            if not isinstance(row, dict):
                issues.append("invalid_policy_source_row")
            elif not key:
                issues.append(missing_reason)
            elif counts[key] > 1:
                issues.append(duplicate_reason)
            if issues:
                for issue in issues:
                    flags[issue] += 1
                worklist.append({
                    "source_section": section,
                    "source_row": position,
                    "rule_name": key[:120],
                    "issues": issues,
                    "review_only": True,
                    "price_approved": False,
                })
    return {
        "worklist": worklist,
        "flag_counts": dict(sorted(flags.items())),
        "source_rows": {
            "rates": len(pricing.get("rates", [])),
            "console_rules": len(pricing.get("console_rules", [])),
        },
    }


def reconcile(catalog, configs, pricing, fingerprint, legacy=None,
              legacy_sha=None, history=None, history_sha=None):
    """Deterministic source-only audit; no database writes and no implicit approvals."""
    sku_rows = defaultdict(list)
    sku_source_positions = defaultdict(list)
    config_rows = defaultdict(list)
    for config in configs:
        if isinstance(config, dict):
            key = _code(config.get("key"))
            if key:
                config_rows[key].append(config)
    for position, product in enumerate(catalog, start=1):
        if isinstance(product, dict):
            code = _code(product.get("sku"))
            if code:
                sku_rows[code].append(product)
                sku_source_positions[code].append(position)
    policy_audit = policy_reconciliation(pricing)
    buckets = Counter()
    worklist = []
    # Rows without an SKU must be visible to reviewers. Previously these
    # silently fell out of sku_rows and could make reconciliation look clean.
    # Report their original one-based catalogue position, without a price.
    missing_sku_rows = [
        position for position, product in enumerate(catalog, start=1)
        if not isinstance(product, dict) or not _code(product.get("sku"))
    ]
    for position in missing_sku_rows:
        buckets["missing_sku"] += 1
        worklist.append({
            "sku": "",
            "catalogue_source_row": position,
            "model": "",
            "description": "",
            "console": "",
            "source_rows": 1,
            "issues": ["missing_sku"],
            "price_approved": False,
            "verified_master_rrp": False,
            "source": "Exact staged V10 product catalogue",
        })
    for code, rows in sorted(sku_rows.items()):
        reasons = []
        if len(rows) > 1:
            reasons.append("duplicate_sku")
            # Never merge two rows (including apparent exact duplicates) by
            # choosing the first; preserve original row count.
        if len(rows) == 1:
            reasons.extend(_review_reasons(rows[0], config_rows, pricing))
        else:
            # Duplicates may each also have separate problems, but no source
            # price or eligibility decision is possible for the SKU group.
            for item in rows:
                reasons.extend(_review_reasons(item, config_rows, pricing))
        reasons = sorted(set(reasons))
        for reason in reasons:
            buckets[reason] += 1
        if reasons:
            representative = rows[0]
            worklist.append({
                "sku": code[:100],
                "model": str(representative.get("model") or "")[:120],
                "description": str(representative.get("name") or "")[:250],
                "console": str(representative.get("console") or "")[:150],
                "source_rows": len(rows),
                "catalogue_source_rows": sku_source_positions[code],
                "issues": reasons,
                "price_approved": False,
                "verified_master_rrp": False,
                "source": "Exact staged V10 product catalogue",
            })
    known_skus = set(sku_rows)
    legacy_keys = defaultdict(set)
    legacy_review = []
    legacy_row_data = []
    legacy_unresolved_codes = set()
    legacy_missing, legacy_invalid = 0, 0
    if legacy is not None:
        for position, entry in enumerate(legacy, start=1):
            reasons = []
            if not isinstance(entry, dict):
                legacy_invalid += 1
                reasons.append("invalid_legacy_source_row")
                entry = {}
            target = _code(entry.get("new_sku"))
            old_values = [_code(entry.get(field)) for field in ("old_code", "old_sku")]
            old_codes = set()
            for old in old_values:
                if old in LEGACY_IGNORE:
                    continue
                if SKU_REGEX.fullmatch(old):
                    old_codes.add(old)
                else:
                    reasons.append("invalid_legacy_identifier")
            if not old_codes:
                reasons.append("missing_legacy_identifier")
            if not target:
                reasons.append("missing_current_target_sku")
            elif not SKU_REGEX.fullmatch(target):
                reasons.append("invalid_current_target_sku")
            elif target not in known_skus:
                reasons.append("target_missing_from_current_catalogue")
                legacy_missing += 1  # Source ROW count, not old-code field count.
            else:
                if len(sku_rows[target]) != 1:
                    reasons.append("duplicate_current_target_sku")
                for old in old_codes:
                    legacy_keys[old].add(target)
            if any(reason in reasons for reason in (
                "missing_current_target_sku", "invalid_current_target_sku",
                "target_missing_from_current_catalogue", "duplicate_current_target_sku",
            )):
                legacy_unresolved_codes.update(old_codes)
            legacy_row_data.append({
                "row": position, "old_codes": old_codes,
                "old_code": old_values[0][:100], "old_sku": old_values[1][:100],
                "new_sku": target[:100], "issues": reasons,
            })
    multi_target_codes = {
        code for code, targets in legacy_keys.items()
        if len(targets) != 1 or any(len(sku_rows[target]) != 1 for target in targets)
    }
    # A historical code pointing to one valid target AND one missing target
    # is still unsafe to resolve as an unambiguous equipment identity.
    legacy_ambiguous = multi_target_codes | legacy_unresolved_codes
    legacy_flags = Counter()
    for item in legacy_row_data:
        reasons = set(item["issues"])
        if any(code in multi_target_codes for code in item["old_codes"]):
            reasons.add("ambiguous_legacy_mapping")
        if any(code in legacy_unresolved_codes for code in item["old_codes"]):
            # Flag BOTH sides of a code that has a valid AND a dangling target.
            reasons.add("incomplete_legacy_mapping")
        if reasons:
            for reason in reasons:
                legacy_flags[reason] += 1
            legacy_review.append({
                "source_row": item["row"],
                "old_code": item["old_code"],
                "old_sku": item["old_sku"],
                "new_sku": item["new_sku"],
                "issues": sorted(reasons),
                "source_identity_only": True,
                "approved_price": None,
            })
    summary = {
        "catalogue_source_rows": len(catalog),
        "catalogue_rows_with_sku": sum(map(len,sku_rows.values())),
        "catalogue_rows_missing_sku": len(missing_sku_rows),
        "distinct_skus": len(sku_rows),
        "unique_skus": sum(len(rows)==1 for rows in sku_rows.values()),
        "duplicate_sku_groups": sum(len(rows)>1 for rows in sku_rows.values()),
        "excess_duplicate_rows": sum(max(0,len(rows)-1) for rows in sku_rows.values()),
        "source_skus_requiring_review": len(worklist)-len(missing_sku_rows),
        "source_skus_without_flagged_identity_issues": len(sku_rows)-(len(worklist)-len(missing_sku_rows)),
        "catalogue_rows_requiring_review": len(worklist),
        "flag_counts": dict(sorted(buckets.items())),
        "pricing_policy_source_rows": policy_audit["source_rows"],
        "policy_rule_rows_requiring_review": len(policy_audit["worklist"]),
        "policy_flag_counts": policy_audit["flag_counts"],
        "legacy_source_rows": len(legacy) if legacy is not None else None,
        "legacy_codes_mapped": len(legacy_keys) if legacy is not None else None,
        "ambiguous_legacy_codes": len(multi_target_codes) if legacy is not None else None,
        "legacy_missing_target_mappings": legacy_missing if legacy is not None else None,
        "legacy_invalid_source_rows": legacy_invalid if legacy is not None else None,
        "legacy_codes_with_unresolved_targets": (
            len(legacy_unresolved_codes) if legacy is not None else None
        ),
        "legacy_source_rows_requiring_review": (
            len(legacy_review) if legacy is not None else None
        ),
        "legacy_flag_counts": dict(sorted(legacy_flags.items())) if legacy is not None else None,
        "historical_source_variants": (
            len(history["records"]) if history is not None else None
        ),
        "historical_source_staged": history is not None,
        "not_a_master_price_list_approval": True,
    }
    return {
        "summary": summary,
        "worklist": worklist,
        "policy_worklist": policy_audit["worklist"],
        "legacy_worklist": legacy_review,
        "legacy_targets": legacy_keys,
        "legacy_ambiguous": legacy_ambiguous,
        "sku_rows": sku_rows,
        "source_sha256": {
            **fingerprint,
            "legacy_crosswalk": legacy_sha,
            "historical_identity": history_sha,
        },
        "commercial_policy_as_recorded": str(
            pricing.get("pricing_status") or "Not commercially approved"
        )[:200],
        "source_snapshot": pricing.get("source_snapshot"),
        "commercially_approved": False,
        "customer_quote_issue_enabled": False,
    }


def source_report():
    catalog, configs, pricing, fingerprints = source_snapshot()
    legacy, legacy_sha = _private_optional_source("legacy_crosswalk")
    history, history_sha = _private_optional_source("historical_identity")
    # All four reconciliation endpoints must be protected against staging
    # changes after IT signs off an exact source snapshot.
    source_manifest_status({
        **fingerprints, "legacy_crosswalk": legacy_sha,
        "historical_identity": history_sha,
    })
    return reconcile(catalog, configs, pricing, fingerprints, legacy, legacy_sha,
                     history, history_sha)


@router.get("/reconciliation")
def reconciliation_status():
    actor()
    r = source_report()
    return {
        "summary": r["summary"],
        "source_sha256": r["source_sha256"],
        "manifest_status": source_manifest_status(r["source_sha256"]),
        "source_snapshot": r["source_snapshot"],
        "commercial_policy_as_recorded": r["commercial_policy_as_recorded"],
        "all_counts_source_derived": True,
        "historical_absence_is_not_completeness": True,
        "commercially_approved": False,
        "customer_quote_issue_enabled": False,
        "source_approval_does_not_follow_from_rate_status_active": True,
    }


@router.get("/reconciliation/worklist")
def reconciliation_worklist(q: str = Query("", max_length=100),
                            issue: str = Query("", max_length=100),
                            limit: int = Query(50, ge=1, le=100),
                            offset: int = Query(0, ge=0)):
    actor()
    r = source_report()
    items = r["worklist"]
    phrase = q.casefold().strip()
    if phrase:
        items = [
            x for x in items if any(phrase in str(x[key]).casefold()
                for key in ("sku", "model", "description", "console"))
        ]
    if issue:
        items = [item for item in items if issue in item["issues"]]
    return {
        "total": len(items), "offset": offset, "limit": limit,
        "items": items[offset:offset+limit],
        "review_only": True, "price_approved": False,
    }



@router.get("/reconciliation/policy-worklist")
def reconciliation_policy_worklist(
        issue: str = Query("", max_length=100),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0)):
    """Read-only conflicting tariff/console rule identities and source rows."""
    actor()
    report = source_report()
    items = report["policy_worklist"]
    if issue:
        items = [item for item in items if issue in item["issues"]]
    return {
        "total": len(items), "offset": offset, "limit": limit,
        "items": items[offset:offset + limit],
        "review_only": True, "price_approved": False,
    }


@router.get("/reconciliation/legacy-worklist")
def legacy_reconciliation_worklist(
        q: str = Query("", max_length=100),
        issue: str = Query("", max_length=100),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0)):
    """Original legacy crosswalk exceptions, never a proposed approved price."""
    actor()
    r = source_report()
    if r["summary"]["legacy_source_rows"] is None:
        raise HTTPException(503, "The authentic V10 legacy crosswalk is not staged.")
    items = r["legacy_worklist"]
    phrase = q.casefold().strip()
    if phrase:
        items = [item for item in items if any(
            phrase in str(item[key]).casefold()
            for key in ("old_code", "old_sku", "new_sku")
        )]
    if issue:
        items = [item for item in items if issue in item["issues"]]
    return {
        "total": len(items), "offset": offset, "limit": limit,
        "items": items[offset:offset + limit],
        "review_only": True, "price_approved": False,
    }


@router.get("/legacy/resolve")
def resolve_legacy(code: str = Query(..., min_length=2, max_length=100)):
    actor()
    key = _code(code)
    if not SKU_REGEX.fullmatch(key):
        raise HTTPException(422, "Enter an exact historical SKU, not a partial model.")
    r = source_report()
    if r["source_sha256"]["legacy_crosswalk"] is None:
        raise HTTPException(503, "The authentic V10 legacy crosswalk is not staged.")
    targets = r["legacy_targets"].get(key, set())
    candidates = []
    for target in sorted(targets):
        rows = r["sku_rows"][target]
        item = rows[0]
        candidates.append({
            "sku": target,
            "model": str(item.get("model") or "")[:120],
            "console": str(item.get("console") or "")[:150],
            "duplicate_current_sku": len(rows) != 1,
            "source_identity_only": True,
        })
    return {
        "searched_exact_legacy_code": key,
        "candidates": candidates,
        "match_count": len(candidates),
        "ambiguous": len(candidates)!=1 or key in r["legacy_ambiguous"],
        "requires_explicit_staff_match_confirmation": True,
        "rrp_not_inferred_from_historical_code": True,
        "approved_price": None,
    }


@router.get("/historical/search")
def historical_search(q: str = Query(..., min_length=2, max_length=100),
                      limit: int = Query(15, ge=1, le=50)):
    """Search authentic 2020–2026 historical identity without supplying prices."""
    actor()
    key = _code(q)
    if len(key) < 2:
        raise HTTPException(422, "Enter at least two characters.")
    history, sha = _private_optional_source("historical_identity")
    if os.environ.get("PULSE_SMARTQUOTE_SOURCE_MANIFEST", "").strip():
        # Historical search must not bypass a pinned source-manifest check.
        _, _, _, fingerprints = source_snapshot()
        _, legacy_sha = _private_optional_source("legacy_crosswalk")
        source_manifest_status({
            **fingerprints, "legacy_crosswalk": legacy_sha,
            "historical_identity": sha,
        })
    if history is None:
        raise HTTPException(
            503, "The protected original V10 historical identity index has not been staged."
        )
    records = history.get("records", {})
    aliases = history.get("aliases", {})
    matched = []
    alias_targets = aliases.get(key, [])
    if not isinstance(alias_targets, list):
        alias_targets = []
    selected_aliases = set(str(x).strip().upper() for x in alias_targets)
    for code, item in records.items():
        if not isinstance(item, dict):
            continue
        sku = _code(code)
        model = _code(item.get("model"))
        name = str(item.get("name") or "")
        if sku == key:
            score = 1000
        elif sku in selected_aliases:
            score = 900
        elif model == key:
            score = 800
        elif sku.startswith(key):
            score = 700
        elif key in sku or key in model:
            score = 500
        elif key.casefold() in name.casefold():
            score = 200
        else:
            continue
        matched.append((score,sku,{
            "historical_sku":sku[:100],
            "model":str(item.get("model") or "")[:120],
            "name":name[:250],
            "console":str(item.get("console") or "")[:150],
            "year_as_recorded":str(item.get("year") or "")[:30],
            "source_as_recorded":str(item.get("source") or "")[:150],
            "status_as_recorded":str(item.get("status") or "")[:80],
            "historical_identity_only":True,
            "current_rrp":None,
            "approved_replacement_sku":None,
        }))
    matched.sort(key=lambda x:(-x[0],x[1]))
    return {
        "query":key, "total":len(matched),
        "results":[x[2] for x in matched[:limit]],
        "source_sha256":sha,
        "contains_price_information":False,
        "ambiguous_or_multiple_variants":len(matched)>1,
        "cannot_auto_select_for_current_pricing":True,
    }
