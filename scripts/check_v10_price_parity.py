"""Strict original-vs-unified SmartQuote V10 tariff parity on approved private data.

Run ONLY on an IT-approved, disposable original V10 source/runtime checkout.
No file is modified; results contain aggregate counts only, never SKU prices,
customers or personal data.

Example: python scripts/check_v10_price_parity.py /secure/SmartQuoteV10 --max-skus 300
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import sys
from collections import Counter

if __package__:
    from .parity_source_coverage import select_source_coverage
else:
    from parity_source_coverage import select_source_coverage
from decimal import Decimal
from pathlib import Path


def _pennies(value):
    return Decimal(str(value)).quantize(Decimal(".01"))


def source_fingerprints(sources):
    """Hash exact source bytes without exposing any source rows or prices."""
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in zip(("catalog", "configs", "pricing"), sources)
    }


def require_source_unchanged(sources, pinned_hashes):
    """Fail if the original runtime files were altered during a parity run."""
    if source_fingerprints(sources) != pinned_hashes:
        raise RuntimeError(
            "Original V10 pricing source files changed during parity testing; "
            "discard results and verify a new private source snapshot."
        )


def verify_original_function(original):
    """Source text must remain exactly the original V10 price_line function."""
    from app._smartquote_price_line_v10 import price_line as vendored
    if inspect.getsource(original.price_line).strip() != inspect.getsource(vendored).strip():
        raise RuntimeError(
            "Original SmartQuote price_line source differs from the vendored "
            "Contracts OS kernel; stop and review the changes before parity testing."
        )


def run(source_root: Path, maximum: int = 300) -> dict:
    root = Path(__file__).resolve().parents[1]
    if not (root/"app"/"quote_pricing.py").is_file():
        raise RuntimeError("Run from a Contracts OS application checkout.")
    if not 1 <= maximum <= 3000:
        raise ValueError("Select 1–3,000 source SKU groups.")

    source_root=source_root.expanduser().resolve()
    sources=[source_root/"data"/name for name in
             ("catalog.json","configs.json","pricing.json")]
    if not (source_root/"engine.py").is_file() or any(
        not p.is_file() or p.stat().st_size==0 for p in sources
    ):
        raise RuntimeError(
            "Complete original V10 engine and genuine catalog/config/pricing JSON "
            "must be staged privately; empty or fictional source is not accepted."
        )
    # Original source files are untrusted until matched to a private manifest.
    # Load once and hash the SAME bytes used by the numerical comparison.
    from app.quote_pricing import _line_price, source_manifest_status
    from app._smartquote_price_line_v10 import original_v10_price_line
    source_bytes=[path.read_bytes() for path in sources]
    fingerprints={
        name: hashlib.sha256(raw).hexdigest()
        for name,raw in zip(("catalog","configs","pricing"),source_bytes)
    }
    manifest=source_manifest_status(fingerprints)
    if not manifest.get("pinned") or not manifest.get("matches"):
        raise RuntimeError(
            "Pin and verify the exact private original V10 source files before parity testing."
        )
    # The original runtime is only imported after its input-file hashes match.
    # It must run on an isolated machine, not the staff-facing service host.
    if str(source_root) not in sys.path:
        sys.path.insert(0,str(source_root))
    original=importlib.import_module("engine")
    if Path(original.__file__).resolve() != (source_root/"engine.py").resolve():
        raise RuntimeError("Refusing to compare a cached or wrong V10 engine.")
    verify_original_function(original)
    require_source_unchanged(sources, fingerprints)
    catalog=json.loads(source_bytes[0].decode("utf-8"))
    configs=json.loads(source_bytes[1].decode("utf-8"))
    pricing=json.loads(source_bytes[2].decode("utf-8"))
    if not all((isinstance(catalog,list),isinstance(configs,list),isinstance(pricing,dict))):
        raise RuntimeError("Original pricing source shape does not match V10.")
    samples, coverage=select_source_coverage(catalog,configs,pricing,maximum)

    compared=0
    failures=Counter()
    exceptional=[]
    covered_groups=set()
    covered_consoles=set()
    for code,product,config,group,console in samples:
        selected=original.live_catalogue_option(product)
        covered_groups.add(group)
        covered_consoles.add(console)
        for tier in ("Silver","Gold","Platinum"):
            for discount in (0,10,20):
                for qty in (1,3,17):
                    asset={"qty":qty,"selected":selected}
                    baseline=original.price_line(asset,"Standard",tier,discount)
                    unified,reason=_line_price(product,config,pricing,tier,discount,qty)
                    isolated=original_v10_price_line(asset,"Standard",tier,discount,pricing)
                    if baseline is None or isolated is None or unified is None:
                        failures["unpriced_or_blocked"]+=1
                        if len(exceptional)<8:
                            exceptional.append({
                                "tier":tier,"discount_percent":discount,
                                "quantity":qty,"reason":"Source eligibility or pricing parity blocked",
                            })
                        continue
                    metrics=(("unit","unit_annual"),("annual","annual"),
                             ("minimum","minimum_annual"))
                    for old,new in metrics:
                        if _pennies(baseline[old])!=_pennies(unified[new]):
                            failures["numeric_penny_mismatch"]+=1
                        if _pennies(baseline[old])!=_pennies(isolated[old]):
                            failures["source_kernel_divergence"]+=1
                    compared+=1
    # A source file swapped mid-check invalidates every comparison result.
    require_source_unchanged(sources, fingerprints)
    return {
        "original_engine_source_verified":True,
        "authentic_source_sha256":fingerprints,
        "private_source_manifest_verified":True,
        **coverage,
        "sourced_skus_sampled":len(samples),
        "rate_groups_covered_count":len(covered_groups),
        "console_variants_covered":len(covered_consoles),
        "calculations_compared":compared,
        "calculations_expected":len(samples)*27,
        "blockers":dict(failures),
        "sample_blockers_without_customer_or_sku_data":exceptional,
        "numeric_comparisons_match":bool(samples) and compared==len(samples)*27 and not failures,
        "pass":(
            bool(samples) and compared==len(samples)*27 and not failures
            and coverage["all_eligible_rate_console_families_sampled"]
            and not coverage["source_rule_identity_conflicts"]
            and coverage["unresolved_numeric_source_exclusions"]==0
            and coverage["source_catalogue_rows_missing_sku"]==0
        ),
        "tariff_commercially_approved":False,
        "customer_quote_issue_enabled":False,
        "note":(
            "Numeric parity checks only verified eligible sampled source SKUs. "
            "Unresolved or ambiguous source identities prevent a clean parity pass. "
            "Explicitly excluded equipment remains outside the numeric scope. "
            "Commercial approval, full source completeness, and customer quote "
            "issuance are separate gates."
        ),
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smartquote_root",type=Path)
    parser.add_argument("--max-skus",type=int,default=300)
    args=parser.parse_args()
    outcome=run(args.smartquote_root,args.max_skus)
    print(json.dumps(outcome,indent=2))
    raise SystemExit(0 if outcome["pass"] else 1)


if __name__=="__main__":
    main()
