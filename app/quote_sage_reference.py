"""Read-only Sage item-price source from original SmartQuote V10.

Pulse uses the exact Sage price as the equipment price basis when a SKU is
absent from the current August master. This module never edits the Sage export
or authorises maintenance tariffs, customer PDFs or contract activation.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
from .store import DB
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, HTTPException
from .pilot_access import actor
from .quote_workspace import _connect

router = APIRouter(prefix="/api/quoting", tags=["Unapproved Sage price references"])
MAX_COMPRESSED = 10 * 1024 * 1024
MAX_UNCOMPRESSED = 32 * 1024 * 1024
SKU = re.compile(r"^[A-Z0-9][A-Z0-9 ._/#*()&+\-]{0,99}$")


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


def _local_active():
    """Protected Contracts OS Sage replacement; never changes the original V10 DB."""
    path = Path(DB).expanduser().resolve()
    if not path.is_file():
        return None
    uri = "file:" + quote(str(path), safe="/:") + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            return db.execute(
                "SELECT source_date,review_due,file_sha256,payload,usable_rows "
                "FROM smartquote_sage_snapshots WHERE active=1 "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.Error as exc:
        if "no such table" in str(exc).lower():
            return None
        raise HTTPException(503, "Contracts OS Sage price snapshot is unavailable.") from exc


def snapshot():
    """Prefer approved local Sage refresh; otherwise read original V10 snapshot.

    Source records are read-only on every quote preview and price correction.
    A damaged active local record is never silently replaced by the older V10
    database or an embedded catalogue RRP.
    """
    row = _local_active()
    origin = (
        "Contracts OS administrator-imported Sage Sales Price — exact item-code equipment basis"
        if row is not None else
        "Dated Sage Sales Price export — exact item-code equipment price basis"
    )
    if row is None:
        from .quote_workspace import _source
        try:
            original = _connect()
        except HTTPException:
            if _source() is None:
                return None
            raise
        with closing(original) as db:
            try:
                row = db.execute(
                    "SELECT source_date,review_due,file_sha256,payload,usable_rows "
                    "FROM sage_price_snapshots WHERE active=1 ORDER BY id DESC LIMIT 1"
                ).fetchone()
            except sqlite3.Error as exc:
                if "no such table" in str(exc).lower():
                    return None
                raise HTTPException(503, "Original Sage source snapshot could not be read.") from exc
    if row is None:
        return None
    try:
        source_date = dt.date.fromisoformat(row["source_date"])
        review_due = dt.date.fromisoformat(row["review_due"])
        if review_due <= source_date:
            raise ValueError("Invalid date range")
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
        "source": origin,
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
        "legacy_equipment_pricing_basis_accepted": True,
        "quoted_annual_amount": None,
        "action": "Use this exact item price for legacy-equipment internal previews when absent from the August master. Service eligibility and maintenance tariffs require separate verification.",
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


@router.get("/sage/search")
def search_sage_items(q: str = Query(..., min_length=2, max_length=100),
                      limit: int = Query(20, ge=1, le=50)):
    """Search all exact Sage inventory codes, including legacy equipment.

    Sage is a price/identity source, NOT an equipment service entitlement.
    Equipment not in the V10 catalogue needs an approved mapping before any
    quote may use its source price and maintenance rate.
    """
    actor()
    phrase = str(q).strip().casefold()
    if len(phrase) < 2:
        raise HTTPException(422, "Enter at least two characters.")
    source = snapshot()
    if source is None:
        raise HTTPException(503, "No active Sage price list. Import the current complete export.")
    products = []
    for sku, item in source["prices"].items():
        if not isinstance(item, dict):
            continue
        code = str(sku).casefold()
        description = str(item.get("name") or "").casefold()
        if code == phrase:
            priority = 1000
        elif code.startswith(phrase):
            priority = 800
        elif phrase in code:
            priority = 600
        elif description.startswith(phrase):
            priority = 400
        elif phrase in description:
            priority = 200
        else:
            continue
        price = item.get("sales_price")
        products.append((priority, str(sku), {
            "sku": str(sku),
            "name": str(item.get("name") or "")[:250],
            "model": "",
            "group": str(item.get("group") or "")[:120],
            "manufacturer": str(item.get("manufacturer") or "")[:120],
            "sage_sales_price": price,
            "source_date": source["source_date"],
            "source": "Sage item-price reference",
            "duplicate_sku": False,
            "requires_service_mapping": True,
            "pricing_approved": False,
            "source_price_is_not_maintenance_eligibility": True,
        }))
    products.sort(key=lambda row: (-row[0], row[1]))
    return {
        "results": [item for _,__,item in products[:limit]],
        "total": len(products),
        "read_only": True,
        "requires_independent_maintenance_eligibility": True,
    }
