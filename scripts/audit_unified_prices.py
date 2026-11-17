"""Offline, read-only audit of the private SmartQuote unified equipment price CSV.

No prices, customer information or source files are uploaded or committed.
Run before an administrator activates the first consolidated price book:
    python scripts/audit_unified_prices.py "C:\\Private\\unified.csv" --snapshot-2026
Later incremental imports can be checked without --snapshot-2026.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

SKU_PATTERN = re.compile(r"^[A-Z0-9?][A-Z0-9 ?._/#*()&+\\-]{0,99}$")
EXPECTED_2026 = {
    "unique_codes": 21187,
    "master_selected": 5064,
    "sage_positive": 11741,
    "sage_unpriced": 4375,
    "master_conflicted": 7,
}
REQUIRED = ("SKU", "Price GBP", "Price Source", "Price Status",
            "Master Reference GBP", "Sage Reference GBP")


def pennies(raw):
    value = str(raw if raw is not None else "").strip().replace("£", "").replace(",", "")
    if not value:
        return None
    try:
        number = Decimal(value)
        if (not number.is_finite() or number < 0 or number > 1_000_000
                or number != number.quantize(Decimal("0.01"))):
            raise ValueError("invalid amount")
        return int(number * 100)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid currency amount")


def audit(path: Path, snapshot_2026: bool = False) -> dict:
    counts = Counter()
    problems = []
    seen = set()

    def flag(line, message):
        counts["errors"] += 1
        if len(problems) < 40:
            problems.append(f"CSV row {line}: {message}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or any(h not in reader.fieldnames for h in REQUIRED):
                raise ValueError("Required columns missing: " + ", ".join(REQUIRED))
            for n, row in enumerate(reader, 2):
                counts["rows"] += 1
                code = str(row.get("SKU") or "").strip().upper()
                if not code or not SKU_PATTERN.fullmatch(code):
                    flag(n, "missing or unsafe SKU")
                    continue
                if code in seen:
                    flag(n, "duplicate exact SKU")
                    continue
                seen.add(code)
                source = str(row.get("Price Source") or "").strip().casefold()
                status = str(row.get("Price Status") or "").strip().casefold()
                try:
                    selected = pennies(row.get("Price GBP"))
                    master = pennies(row.get("Master Reference GBP"))
                    sage = pennies(row.get("Sage Reference GBP"))
                except ValueError:
                    flag(n, "non-finite, negative, over-precision or invalid price")
                    continue

                if status.startswith("hold") or ("master" in source and "conflict" in source):
                    counts["master_conflicted"] += 1
                    if not status.startswith("hold") or selected is not None:
                        flag(n, "Master conflict must be HOLD with no selected price")
                    # A Sage value may exist as evidence but cannot settle a Master conflict.
                elif source == "master 24-08-2026":
                    counts["master_selected"] += 1
                    if (selected is None or selected == 0 or master is None
                            or selected != master):
                        flag(n, "selected Master price does not equal positive Master reference")
                    if not status.startswith("price reference"):
                        flag(n, "Master row has unexpected price status")
                elif source == "sage imported reference":
                    if master is not None:
                        flag(n, "Sage fallback selected despite a present Master reference")
                    if selected is None or sage is None or selected != sage:
                        flag(n, "selected Sage price does not equal Sage reference")
                    if selected == 0:
                        counts["sage_unpriced"] += 1
                        if not status.startswith("unpriced"):
                            flag(n, "zero-price Sage row is not marked UNPRICED")
                    elif selected is not None and selected > 0:
                        counts["sage_positive"] += 1
                        if not status.startswith("price reference"):
                            flag(n, "positive Sage price has unexpected price status")
                else:
                    flag(n, "unrecognised price source or source precedence")
            counts["unique_codes"] = len(seen)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        return {"passed": False, "errors": [str(exc)], "counts": dict(counts)}

    if snapshot_2026:
        for label, expected in EXPECTED_2026.items():
            if counts[label] != expected:
                flag("totals", f"{label} count does not match locked November 2026 source audit (expected {expected}, observed {counts[label]})")
    return {
        "passed": not problems,
        "counts": {key: counts[key] for key in
                   ("rows", "unique_codes", "master_selected", "sage_positive",
                    "sage_unpriced", "master_conflicted", "errors")},
        "errors": problems,
        "note": "Validates source data arithmetic and precedence only. Not commercial approval, tariff or equipment-cover certification.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--snapshot-2026", action="store_true",
                        help="Also enforce the exact historical 21,187-code baseline totals")
    args = parser.parse_args(argv)
    result = audit(args.csv_path, args.snapshot_2026)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
