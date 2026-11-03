"""Source-only audit of authentic historical SmartQuote equipment identities.

No RRPs, maintenance rates, customer names, or approval flags are inferred.
This module only examines the structure of a privately staged identity index.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

CODE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,99}$")


def _key(value):
    return str(value or "").strip().upper()


def analyze_historical_identity(history):
    """Return deterministic, read-only record/alias exceptions, never prices.

    Exact JSON object keys are shown for locating the original staged rows.
    Normalised collisions and dangling aliases cannot silently pass as
    historically verified identities. Multiple real variants are for review.
    """
    if history is None:
        return {
            "staged": False,
            "summary": {
                "historical_source_records": None,
                "historical_alias_source_entries": None,
                "historical_identity_rows_requiring_review": None,
                "historical_identity_flag_counts": None,
            },
            "worklist": [],
        }
    records = history["records"]
    aliases = history.get("aliases", {})
    counts = Counter()
    worklist = []
    record_keys = defaultdict(list)
    alias_keys = defaultdict(list)

    for raw in records:
        record_keys[_key(raw)].append(raw)
    for raw in aliases:
        alias_keys[_key(raw)].append(raw)

    def flag(source_type, source_key, reasons):
        if not reasons:
            return
        reasons = sorted(set(reasons))
        counts.update(reasons)
        worklist.append({
            "source_type": source_type,
            "source_key": str(source_key)[:100],
            "issues": reasons,
            "identity_only": True,
            "approved_price": None,
        })

    for raw, item in records.items():
        code = _key(raw)
        problems = []
        if not CODE.fullmatch(code):
            problems.append("invalid_historical_record_key")
        if len(record_keys[code]) > 1:
            problems.append("duplicate_normalized_historical_code")
        if not isinstance(item, dict):
            problems.append("invalid_historical_record")
        else:
            recorded_sku = _key(item.get("sku"))
            if recorded_sku and recorded_sku != code:
                problems.append("historical_sku_disagrees_with_record_key")
            if not str(item.get("console") or "").strip():
                problems.append("missing_historical_console_identity")
        flag("record", raw, problems)

    valid_codes = set(record_keys)
    for raw, targets in aliases.items():
        alias = _key(raw)
        problems = []
        if not CODE.fullmatch(alias):
            problems.append("invalid_historical_alias")
        if len(alias_keys[alias]) > 1:
            problems.append("duplicate_normalized_historical_alias")
        if not isinstance(targets, list) or not targets:
            problems.append("invalid_or_empty_historical_alias_targets")
        else:
            valid_targets = []
            for target in targets:
                code = _key(target)
                if not isinstance(target, str) or not CODE.fullmatch(code):
                    problems.append("invalid_historical_alias_target")
                elif code not in valid_codes:
                    problems.append("dangling_historical_alias_target")
                else:
                    valid_targets.append(code)
                    if len(record_keys[code]) != 1:
                        problems.append("ambiguous_historical_alias_target")
            if len(valid_targets) != len(set(valid_targets)):
                problems.append("duplicate_historical_alias_target")
            if len(set(valid_targets)) > 1:
                problems.append("multi_variant_historical_alias")
        flag("alias", raw, problems)

    worklist.sort(key=lambda item: (item["source_type"], item["source_key"]))
    return {
        "staged": True,
        "summary": {
            "historical_source_records": len(records),
            "historical_alias_source_entries": len(aliases),
            "historical_identity_rows_requiring_review": len(worklist),
            "historical_identity_flag_counts": dict(sorted(counts.items())),
        },
        "worklist": worklist,
    }
