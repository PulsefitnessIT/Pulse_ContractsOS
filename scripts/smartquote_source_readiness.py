"""Produce a private, aggregate-only SmartQuote source-reconciliation gate report.

IT/staging only; the report never includes equipment SKUs, customer records,
RRPs, tariffs, source file paths, or any approval to issue a quotation.

Usage:
    python -m scripts.smartquote_source_readiness \\
      --output /private/staging/source-readiness-2026-11-03.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_FIELDS = (
    "catalogue_source_rows",
    "catalogue_rows_missing_sku",
    "distinct_skus",
    "duplicate_sku_groups",
    "catalogue_rows_requiring_review",
    "pricing_policy_source_rows",
    "policy_rule_rows_requiring_review",
    "legacy_source_rows",
    "legacy_source_rows_requiring_review",
    "legacy_missing_target_mappings",
    "historical_source_variants",
    "historical_alias_source_entries",
    "historical_identity_rows_requiring_review",
)


def build_readiness(report, manifest_status):
    """Allowlist aggregate counts only. No source records may enter the result."""
    summary = report["summary"]
    count = {name: summary.get(name) for name in EVIDENCE_FIELDS}
    issue_groups = (
        "catalogue_rows_requiring_review",
        "policy_rule_rows_requiring_review",
        "legacy_source_rows_requiring_review",
        "historical_identity_rows_requiring_review",
    )
    staged = bool(
        summary.get("legacy_source_rows") is not None
        and summary.get("historical_source_staged") is True
    )
    pinned = bool(manifest_status.get("pinned") and manifest_status.get("matches"))
    no_open_issues = all(
        isinstance(count[name], int) and count[name] == 0
        for name in issue_groups
    )
    ready = bool(staged and pinned and no_open_issues)
    return {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Private source evidence readiness for original V10 parity checks",
        "evidence_counts": count,
        "source_sha256": {
            name: report["source_sha256"].get(name)
            for name in (
                "catalog", "configs", "pricing", "legacy_crosswalk",
                "historical_identity",
            )
        },
        "source_manifest_hash_verified": pinned,
        "complete_original_identity_sources_staged": staged,
        "all_recorded_identity_exceptions_resolved": no_open_issues,
        "ready_to_run_private_numeric_parity": ready,
        "actual_v10_numeric_parity_completed": False,
        "commercial_tariff_approved": False,
        "customer_quote_issue_enabled": False,
        "contract_setup_enabled": False,
        "note": (
            "A passed identity gate does not verify any price, parity result, "
            "customer quote, commercial terms or source-master completeness."
        ),
    }


def write_private_report(output: Path, report: dict):
    """Create once outside checkout; no overwrite and no console data leakage."""
    output = output.expanduser().absolute()
    if (output.exists() or output.is_symlink() or output == ROOT
            or ROOT in output.parents or not output.parent.is_dir()):
        raise ValueError("Select a NEW report path outside the Contracts OS repository.")
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
    except Exception:
        output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from app.quote_reconciliation import source_report
    from app.quote_pricing import source_manifest_status

    report = source_report()
    summary = build_readiness(
        report, source_manifest_status(report["source_sha256"])
    )
    write_private_report(args.output, summary)
    print(json.dumps({
        "private_report_created": True,
        "ready_to_run_private_numeric_parity":
            summary["ready_to_run_private_numeric_parity"],
        "commercial_tariff_approved": False,
        "customer_quote_issue_enabled": False,
    }, sort_keys=True))
    return 0 if summary["ready_to_run_private_numeric_parity"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
