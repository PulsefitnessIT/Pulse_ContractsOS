"""August 2026 current list first; Sage exact-code price is the legacy fallback.

Original workbook/sanitised extracted rows are never bundled in Contracts OS.
This module reads a protected, pinned extract. No quote or catalogue write,
and neither a source List Price nor a Sage Sales Price is tariff approval.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zlib
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from fastapi import HTTPException

SOURCE_ENV = "PULSE_SMARTQUOTE_RRP_2026_SOURCE"
MASTER_FILE = "Full Master Price List 24-08-2026.xlsx"
MASTER_DATE = "2026-08-24"
MASTER_ORIGINAL_SHA256 = "fbc544db9365f6b47cd37fb3e085e5c75acc03042eff5d6f820ffa55f80b3433"
MAX_COMPRESSED = 8 * 1024 * 1024
MAX_DECOMPRESSED = 32 * 1024 * 1024
CODE = re.compile(r"^[A-Z0-9][A-Z0-9 ._/#*()&+\-]{0,99}$")


def _code(value):
    return str(value or "").strip().upper()


def _amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        money = Decimal(str(value))
        if not money.is_finite() or not Decimal("0") < money <= Decimal("100000000"):
            return None
        return money.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def source_snapshot():
    """Read exact original sanitized List Price evidence, fail closed if absent."""
    file = os.environ.get(SOURCE_ENV, "").strip()
    if not file:
        raise HTTPException(503, "IT must stage the 24 August 2026 RRP evidence snapshot.")
    path = Path(file).expanduser().resolve()
    try:
        if path.suffix.lower() != ".gz" or not path.is_file():
            raise ValueError("Incorrect source format")
        if not 2 <= path.stat().st_size <= MAX_COMPRESSED:
            raise ValueError("Invalid source size")
        raw = path.read_bytes()
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = decoder.decompress(raw, MAX_DECOMPRESSED + 1)
        if (len(decoded) > MAX_DECOMPRESSED or not decoder.eof
                or decoder.unused_data or decoder.unconsumed_tail):
            raise ValueError("Incomplete source payload")
        payload = json.loads(decoded.decode("utf-8"))
        if (not isinstance(payload, dict)
                or payload.get("source_file") != MASTER_FILE
                or payload.get("source_date") != MASTER_DATE
                or str(payload.get("source_sha256", "")).lower() != MASTER_ORIGINAL_SHA256
                or not isinstance(payload.get("rows"), list)
                or not 1 <= len(payload["rows"]) <= 20000):
            raise ValueError("Incorrect original August 2026 master evidence")
        if not all(isinstance(row, dict) for row in payload["rows"]):
            raise ValueError("Invalid original source row")
        digest = hashlib.sha256(raw).hexdigest()
        # The private IT manifest must pin this original sanitized snapshot
        # against the three exact V10 engine source files.
        from .quote_pricing import source_manifest_status, source_snapshot as v10_sources
        _, _, _, hashes = v10_sources()
        status = source_manifest_status({**hashes, "august_2026_rrp": digest})
        if not (status["pinned"] and status["matches"]):
            raise ValueError("The August master evidence is not pinned")
        return {
            "rows": payload["rows"],
            "source_date": MASTER_DATE,
            "source_file_sha256": MASTER_ORIGINAL_SHA256,
            "snapshot_sha256": digest,
        }
    except (OSError, ValueError, UnicodeError, zlib.error, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Verified 24 August 2026 master List Price snapshot is unavailable.") from exc


def index(source):
    by_code = defaultdict(list)
    for row in source["rows"]:
        code = _code(row.get("sku"))
        if CODE.fullmatch(code):
            by_code[code].append(row)
    return by_code


def resolve(sku, by_code, sage_source=None):
    """Always prefer August master presence, even when its rows conflict.

    Sage is consulted only when there are ZERO master rows for the exact SKU.
    Pulse has designated Sage Sales Price as the indicative price basis for
    machines absent from the current August master. The maintenance tariff
    and equipment eligibility remain separate from this source price.
    """
    code = _code(sku)
    if not CODE.fullmatch(code):
        return {"basis": "invalid_sku", "rrp": None, "review_required": True}
    rows = by_code.get(code, ())
    if rows:
        prices = {_amount(row.get("rrp")) for row in rows}
        variants = {
            (str(row.get("name") or "").strip().casefold(),
             str(row.get("console") or "").strip().casefold())
            for row in rows
        }
        evidence = [{
            "sheet": str(row.get("sheet") or "")[:100],
            "row": row.get("row"),
            "rrp_column": str(row.get("rrp_column") or "")[:20],
        } for row in rows[:12]]
        if None in prices or len(prices) != 1:
            return {
                "basis": "master_price_conflict",
                "rrp": None, "master_rows": evidence,
                "review_required": True,
            }
        if len(variants) != 1:
            return {
                "basis": "master_variant_conflict",
                "rrp": None, "master_rows": evidence,
                "review_required": True,
            }
        return {
            "basis": "august_2026_master_list_price",
            "rrp": float(next(iter(prices))),
            "master_rows": evidence,
            "master_console": str(rows[0].get("console") or "")[:120],
            "review_required": True,  # Valid source evidence is not tariff approval.
        }

    sage = None
    if sage_source is not None:
        # Import here to avoid circular dependencies with the quote routes.
        from .quote_sage_reference import reference
        sage = reference(code, sage_source)
    if sage:
        return {
            "basis": "sage_exact_sku_price",
            "rrp": sage["sage_sales_price"],
            "sage_reference": sage,
            "sage_source_date": sage["source_date"],
            "sage_source_file_sha256": sage["source_file_sha256"],
            "review_required": bool(sage["review_overdue"]),
            "source_price_policy": "Sage exact SKU is the adopted price basis for legacy equipment",
        }
    # The user's real Sage export includes equipment SKUs priced at £0.
    # Retain these exact codes so an administrator can set a corrected
    # equipment price without creating a fictitious product record.
    if sage_source and isinstance(sage_source.get("prices"), dict):
        recorded = sage_source["prices"].get(code)
        if (isinstance(recorded, dict)
                and str(recorded.get("sku") or "").strip().upper() == code
                and recorded.get("sales_price") == 0):
            return {
                "basis": "sage_unpriced_exact_sku",
                "rrp": None, "review_required": True,
                "sage_source_date": sage_source.get("source_date"),
                "sage_source_file_sha256": sage_source.get("source_file_sha256"),
            }
    return {
        "basis": "not_on_august_master_or_usable_sage_export",
        "rrp": None, "review_required": True,
    }

def summarize_priority(master, catalog, sage_source=None):
    """Aggregate-only mapping status for the coordinator's price-source panel."""
    by_code = index(master)
    catalogue_codes = {
        _code(row.get("sku")) for row in catalog
        if isinstance(row, dict) and CODE.fullmatch(_code(row.get("sku")))
    }
    counts = {
        "original_v10_catalogue_distinct_skus": len(catalogue_codes),
        "august_2026_master_source_rows": len(master["rows"]),
        "august_2026_master_distinct_skus": len(by_code),
        "august_master_skus_not_in_v10": len(set(by_code) - catalogue_codes),
        "v10_skus_with_master_reference": 0,
        "v10_skus_with_conflicting_master_rows": 0,
        "v10_skus_referred_to_sage": 0,
        "v10_skus_absent_from_both_lists": 0,
    }
    for sku in catalogue_codes:
        match = resolve(sku, by_code, sage_source)
        if match["basis"] == "august_2026_master_list_price":
            counts["v10_skus_with_master_reference"] += 1
        elif match["basis"] in ("master_price_conflict", "master_variant_conflict"):
            counts["v10_skus_with_conflicting_master_rows"] += 1
        elif match["basis"] == "sage_exact_sku_price":
            counts["v10_skus_referred_to_sage"] += 1
        else:
            counts["v10_skus_absent_from_both_lists"] += 1
    return {
        "priority": ["August 2026 Master List Price", "Sage exact-SKU Sales Price fallback"],
        "counts": counts,
        "august_source_date": master["source_date"],
        "august_original_file_sha256": master["source_file_sha256"],
        "august_snapshot_sha256": master["snapshot_sha256"],
        "sage_loaded": bool(sage_source),
        "sage_review_overdue": sage_source["review_overdue"] if sage_source else None,
        "master_list_price_is_primary": True,
        "sage_exact_price_used_as_internal_rrp_basis": True,
        "sage_snapshot_remains_subject_to_refresh": True,
        "commercially_approved": False,
        "customer_quote_issue_enabled": False,
    }
