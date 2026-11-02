"""Read-only Sage Sales Price *reference* from original SmartQuote V10.

Sales Price is NOT an authorised maintenance RRP or tariff. Even an exact code
never increases quoted totals here. No database migration, no writes.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import sqlite3
import zlib
from contextlib import closing
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, HTTPException
from .pilot_access import actor
from .quote_workspace import _connect

router = APIRouter(prefix="/api/quoting", tags=["Unapproved Sage price references"])
MAX_COMPRESSED = 10 * 1024 * 1024
MAX_UNCOMPRESSED = 32 * 1024 * 1024
SKU = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,99}$")


def _unpack(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_COMPRESSED:
        raise HTTPException(503, "Sage snapshot is unavailable or exceeds the source limit.")
    try:
        decompress = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = decompress.decompress(raw, MAX_UNCOMPRESSED + 1)
        if len(decoded) > MAX_UNCOMPRESSED or not decompress.eof or decompress.unused_data:
            raise ValueError("Oversized or incomplete Sage snapshot.")
        data = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, zlib.error) as exc:
        raise HTTPException(503, "Active Sage source snapshot is invalid.") from exc
    if not isinstance(data, dict) or len(data) > 60000:
        raise HTTPException(503, "Unexpected Sage source snapshot content.")
    return data


def snapshot():
    """Read the same active snapshot table as original SmartQuote, without writes."""
    with closing(_connect()) as db:
        try:
            row = db.execute(
                "SELECT source_date,review_due,file_sha256,payload,usable_rows "
                "FROM sage_price_snapshots WHERE active=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        except sqlite3.Error:
            return None  # Older installations have no manager-imported snapshot.
    if row is None:
        return None
    try:
        source_date = dt.date.fromisoformat(row["source_date"])
        review_due = dt.date.fromisoformat(row["review_due"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Sage price-source date cannot be verified.") from exc
    digest = str(row["file_sha256"] or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HTTPException(503, "Sage export fingerprint is missing.")
    prices = _unpack(row["payload"])
    return {
        "prices": prices,
        "source_date": source_date.isoformat(),
        "review_due": review_due.isoformat(),
        "review_overdue": review_due <= dt.date.today(),
        "source_file_sha256": digest,
        "source": "Sage Sales Price export — NOT an approved RRP",
    }


def reference(sku: str, source: dict):
    code = str(sku or "").strip().upper()
    if not SKU.fullmatch(code):
        return None
    item = source["prices"].get(code)
    if not isinstance(item, dict) or str(item.get("sku") or "").strip().upper() != code:
        return None
    try:
        amount = Decimal(str(item.get("sales_price")))
        if not amount.is_finite() or not 0 < amount <= 1000000:
            return None
        amount = amount.quantize(Decimal(".01"))
    except (InvalidOperation, ValueError):
        return None
    return {
        "sku": code, "name": str(item.get("name") or "")[:250],
        "product_group": str(item.get("group") or "")[:120],
        "sage_sales_price": float(amount),
        "source_date": source["source_date"],
        "review_due": source["review_due"],
        "review_overdue": source["review_overdue"],
        "source_file_sha256": source["source_file_sha256"],
        "basis": source["source"],
        "approved_rrp": False,
        "quoted_annual_amount": None,
        "action": "Verify this exact product and current Master Price List before converting a Sage sales price into any maintenance quote.",
    }


@router.get("/sage/status")
def sage_reference_status():
    actor()
    source = snapshot()
    if source is None:
        return {"loaded": False, "read_only": True, "approved_rrp": False}
    return {
        "loaded": True, "read_only": True, "approved_rrp": False,
        "source_date": source["source_date"], "review_due": source["review_due"],
        "review_overdue": source["review_overdue"],
        "source_file_sha256": source["source_file_sha256"],
    }
