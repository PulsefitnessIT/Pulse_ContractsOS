"""Opt-in numeric parity check: unified preview vs original SmartQuote V10 engine.

REQUIRES an authorised, disposable full SmartQuote V10 source/data checkout.
Only aggregated results are printed. Never run against production data without
an approved staging copy. No write methods are invoked here.

Usage: python scripts/check_v10_price_parity.py /protected/staging/SmartQuoteV10
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path


def run(source_root: Path, maximum: int = 250) -> dict:
    root = Path(__file__).resolve().parents[1]
    if not (root / "app" / "quote_pricing.py").is_file():
        raise RuntimeError("Start this script from a Contracts OS source checkout.")
    source_root = source_root.expanduser().resolve()
    files = [source_root / "data" / name for name in
             ("catalog.json", "configs.json", "pricing.json")]
    if not (source_root / "engine.py").is_file() or any(not p.is_file() for p in files):
        raise RuntimeError("Original V10 source and runtime catalogue files are required.")
    # Do not copy/migrate the source files or set their paths in a public build.
    for path in files:
        if path.stat().st_size == 0:
            raise RuntimeError("Source catalogue/configuration is empty.")

    sys.path.insert(0, str(source_root))
    from app.quote_pricing import _line_price
    import engine as original

    catalog = json.loads(files[0].read_text(encoding="utf-8"))
    configs = json.loads(files[1].read_text(encoding="utf-8"))
    pricing = json.loads(files[2].read_text(encoding="utf-8"))
    by_key = {}
    for row in configs:
        if isinstance(row, dict):
            by_key.setdefault(str(row.get("key") or "").upper(), []).append(row)
    codes = {}
    for row in catalog:
        if isinstance(row, dict) and row.get("sku"):
            codes.setdefault(str(row["sku"]).upper(), []).append(row)
    choices = []
    for code, variants in sorted(codes.items()):
        if len(variants) != 1:
            continue
        p = variants[0]
        k = str(p.get("service_key") or "").upper()
        if len(by_key.get(k, [])) != 1 or p.get("coverage_override") == "Not eligible":
            continue
        if not isinstance(p.get("rrp"), (int, float)) or isinstance(p.get("rrp"), bool):
            continue
        choices.append((p, by_key[k][0]))
        if len(choices) >= maximum:
            break
    verified, mismatch, skipped = 0, 0, 0
    failures = []
    for row, config in choices:
        chosen = original.live_catalogue_option(row)
        for tier in ("Silver", "Gold", "Platinum"):
            for discount in (0, 10, 20):
                asset = {"qty": 3, "selected": chosen}
                baseline = original.price_line(asset, "Standard", tier, discount)
                new, reason = _line_price(row, config, pricing, tier, discount, 3)
                if not baseline or not new:
                    skipped += 1
                    continue
                # Price_line annual values are already rounded by V10; compare
                # exact pennies and the minimum threshold to catch drift.
                ok = (
                    Decimal(str(baseline["unit"])).quantize(Decimal(".01")) ==
                    Decimal(str(new["unit_annual"])).quantize(Decimal(".01"))
                    and Decimal(str(baseline["annual"])).quantize(Decimal(".01")) ==
                    Decimal(str(new["annual"])).quantize(Decimal(".01"))
                    and Decimal(str(baseline["minimum"])).quantize(Decimal(".01")) ==
                    Decimal(str(new["minimum_annual"])).quantize(Decimal(".01"))
                )
                verified += 1
                if not ok:
                    mismatch += 1
                    if len(failures) < 5:
                        failures.append({
                            "tier": tier, "discount_percent": discount,
                            "reason": "Unit/annual/minimum penny mismatch",
                        })
    return {
        "source_skus_sampled": len(choices),
        "calculations_compared": verified,
        "calculations_skipped": skipped,
        "pricing_mismatch_count": mismatch,
        "pass": bool(verified) and mismatch == 0,
        "sample_failures_no_customer_or_sku_data": failures,
        "policy": "Numeric parity only; does not constitute tariff approval.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smartquote_root", type=Path,
                        help="Disposable verified copy of SmartQuote V10 runtime")
    parser.add_argument("--max-skus", type=int, default=250)
    args = parser.parse_args()
    if not 1 <= args.max_skus <= 2000:
        parser.error("Choose 1–2,000 SKUs.")
    outcome = run(args.smartquote_root, args.max_skus)
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["pass"] else 1)


if __name__ == "__main__":
    main()
