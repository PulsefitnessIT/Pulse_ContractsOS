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
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def _pennies(value):
    return Decimal(str(value)).quantize(Decimal(".01"))


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
    # import the complete original source runtime, without copying its data
    # into GitHub and without changing its local database.
    if str(source_root) not in sys.path:
        sys.path.insert(0,str(source_root))
    from app.quote_pricing import _line_price
    from app._smartquote_price_line_v10 import original_v10_price_line
    original=importlib.import_module("engine")
    if Path(original.__file__).resolve() != (source_root/"engine.py").resolve():
        raise RuntimeError("Refusing to compare a cached or wrong V10 engine.")
    verify_original_function(original)
    catalog=json.loads(sources[0].read_text(encoding="utf-8"))
    configs=json.loads(sources[1].read_text(encoding="utf-8"))
    pricing=json.loads(sources[2].read_text(encoding="utf-8"))
    if not all((isinstance(catalog,list),isinstance(configs,list),isinstance(pricing,dict))):
        raise RuntimeError("Original pricing source shape does not match V10.")
    config_by_key=defaultdict(list)
    for row in configs:
        if isinstance(row,dict):
            config_by_key[str(row.get("key") or "").strip().upper()].append(row)
    sku_by_code=defaultdict(list)
    for row in catalog:
        if isinstance(row,dict) and row.get("sku"):
            sku_by_code[str(row["sku"]).strip().upper()].append(row)
    active_rates={
        str(r.get("group")) for r in pricing.get("rates",[])
        if isinstance(r,dict) and r.get("status")=="Active"
    }
    source_consoles={
        str(r.get("name")) for r in pricing.get("console_rules",[])
        if isinstance(r,dict)
    }

    eligible=[]
    excluded=Counter()
    for code,rows in sorted(sku_by_code.items()):
        if len(rows)!=1:
            excluded["duplicate_source_sku"]+=1
            continue
        p=rows[0]
        config_key=str(p.get("service_key") or "").strip().upper()
        matches=config_by_key.get(config_key,[])
        if len(matches)!=1:
            excluded["missing_or_ambiguous_config"]+=1
            continue
        c=matches[0]
        if c.get("eligible")!="Yes" or p.get("coverage_override")=="Not eligible" or p.get("match")=="Price list only - review":
            excluded["coverage_needs_approval"]+=1
            continue
        group=str(p.get("rate_group_override") or c.get("rate_group") or "")
        if group not in active_rates:
            excluded["rate_needs_approval"]+=1
            continue
        if p.get("console") not in source_consoles:
            excluded["console_unverified"]+=1
            continue
        if type(p.get("rrp")) not in (int,float) or not 0 < float(p["rrp"]) <= 1e8:
            excluded["rrp_missing_or_invalid"]+=1
            continue
        eligible.append((code,p,c,group,str(p.get("console") or "")))
    # Round-robin across (rate group, console variant) to avoid sampling only
    # the alphabetically first family of machines.
    groups=defaultdict(list)
    for item in eligible:
        groups[(item[3],item[4])].append(item)
    samples=[]
    while len(samples)<maximum:
        added=False
        for group in sorted(groups):
            if groups[group]:
                samples.append(groups[group].pop(0))
                added=True
                if len(samples)>=maximum:
                    break
        if not added:
            break

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
    return {
        "original_engine_source_verified":True,
        "authentic_source_sha256":{
            name:hashlib.sha256(path.read_bytes()).hexdigest()
            for name,path in zip(("catalog","configs","pricing"),sources)
        },
        "source_sku_groups":len(sku_by_code),
        "source_skus_eligible_for_parity_sampling":len(eligible),
        "skipped_source_sku_groups_by_reason":dict(excluded),
        "sourced_skus_sampled":len(samples),
        "rate_groups_covered":sorted(covered_groups),
        "console_variants_covered":len(covered_consoles),
        "calculations_compared":compared,
        "calculations_expected":len(samples)*27,
        "blockers":dict(failures),
        "sample_blockers_without_customer_or_sku_data":exceptional,
        "pass":bool(samples) and compared==len(samples)*27 and not failures,
        "tariff_commercially_approved":False,
        "note":"Strict source numeric parity only. Tariff/RRP approval and full quoting release are separate.",
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
