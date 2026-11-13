"""Single Pulse Fitness equipment/item price book with additive, versioned imports.

Initial import: the reconciled Master-over-Sage list. Subsequent imports
replace prices for matching exact SKUs and retain all other SKUs. This module
does NOT approve equipment eligibility, maintenance cover rates or contract
terms. It never writes to Sage, historic V10 or issued quotation archives.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import secrets
import sqlite3
import zlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import pilot_access
from .store import connect
from .data_readiness import safe_excel_csv_cell

router = APIRouter(prefix="/api/quoting/price-book",
                   tags=["Unified item-price master"])
MAX_UPLOAD = 9 * 1024 * 1024
MAX_ITEMS = 60000
MAX_PAYLOAD = 14 * 1024 * 1024
PREVIEW_AGE = dt.timedelta(hours=2)
SKU = re.compile(r"^[A-Z0-9?][A-Z0-9 ?._/#*()&+\-]{0,99}$")
HEADERS = ("SKU", "Price GBP", "Description", "Product Group",
           "Price Source", "Price Status", "Master Reference GBP",
           "Sage Reference GBP", "Review Action", "Effective Date",
           "Original Master Rows")


class ActivatePriceImport(BaseModel):
    preview_token: str
    reason: str
    confirm_zero_and_held_prices: bool = False


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Named pricing administrator required.")
    who = pilot_access.actor("")
    if not isinstance(who, str) or len(who.strip()) < 2 or who.strip() in (
            "Admin", "Coordinator", "Viewer"):
        raise HTTPException(403, "Named pricing administrator required.")
    return who[:120]


def _tables(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS unified_price_book_versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        revision INTEGER NOT NULL UNIQUE,
        active INTEGER NOT NULL CHECK(active IN (0,1)),
        snapshot_sha256 TEXT NOT NULL,
        source_file_sha256 TEXT NOT NULL,
        filename TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        imported_by TEXT NOT NULL,
        reason TEXT NOT NULL,
        changed_count INTEGER NOT NULL,
        new_count INTEGER NOT NULL,
        kept_count INTEGER NOT NULL,
        rows_zlib BLOB NOT NULL
      );
      CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_price_book_active
      ON unified_price_book_versions(active) WHERE active=1;
      CREATE TABLE IF NOT EXISTS unified_price_book_previews(
        token TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        expected_revision INTEGER NOT NULL,
        expected_sha256 TEXT,
        filename TEXT NOT NULL,
        source_file_sha256 TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        new_rows_zlib BLOB NOT NULL
      );
    """)


def _unpack(blob, expected_sha):
    if not isinstance(blob, bytes) or len(blob) > MAX_PAYLOAD:
        raise HTTPException(503, "Unified price master is missing or too large.")
    try:
        d = zlib.decompressobj()
        raw = d.decompress(blob, MAX_PAYLOAD + 1)
        if (len(raw) > MAX_PAYLOAD or not d.eof or d.unused_data
                or d.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != expected_sha):
            raise ValueError("Price-book fingerprint mismatch")
        rows = json.loads(raw.decode("utf-8"))
        if not isinstance(rows, dict) or len(rows) > MAX_ITEMS:
            raise ValueError("Invalid price-book structure")
        return rows
    except (zlib.error, ValueError, UnicodeError, TypeError) as exc:
        raise HTTPException(503, "Unified price master integrity check failed.") from exc


def _pack(rows):
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_PAYLOAD:
        raise HTTPException(413, "Unified price data exceeds protected storage limit.")
    return zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest()


def active_book():
    """Read current immutable snapshot; no implicit source fallback after activation."""
    try:
        con = connect()
    except sqlite3.OperationalError as exc:
        from .store import DB
        if ("unable to open database file" in str(exc).lower()
                and not Path(DB).parent.is_dir()):
            # Synthetic/unit tests and source-only checkouts have no pilot DB.
            # An existing protected DB that fails to open must still fail closed.
            return None
        raise HTTPException(503, "Unified price master database unavailable.") from exc
    try:
        try:
            record = con.execute(
                "SELECT revision,snapshot_sha256,source_file_sha256,filename,"
                "imported_at,rows_zlib FROM unified_price_book_versions "
                "WHERE active=1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
        if not record:
            return None
        return {
            "revision": record["revision"],
            "sha256": record["snapshot_sha256"],
            "source_file_sha256": record["source_file_sha256"],
            "source_file": record["filename"],
            "imported_at": record["imported_at"],
            "rows": _unpack(record["rows_zlib"], record["snapshot_sha256"]),
        }
    finally:
        con.close()


def _money(raw):
    text = str(raw or "").strip().replace("£", "").replace(",", "")
    if not text:
        return None
    try:
        price = Decimal(text)
        if (not price.is_finite() or price < 0 or price > 1000000
                or price != price.quantize(Decimal("0.01"))):
            raise InvalidOperation()
        return int(price * 100)
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, "Price GBP must be 0–1,000,000 with at most two decimals.")


def parse_price_upload(filename, raw):
    """Read one canonical CSV; never execute formula fields or ignore duplicates."""
    if (not str(filename or "").lower().endswith(".csv")
            or not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_UPLOAD):
        raise HTTPException(422, "Upload a nonempty unified price-list CSV (maximum 9 MB).")
    try:
        source = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(source, newline=""))
        if reader.fieldnames is None:
            raise ValueError("No CSV header")
        canonical = {
            str(value or "").strip().casefold(): value
            for value in reader.fieldnames
        }
        def field(*aliases):
            return next((canonical[a] for a in aliases if a in canonical), None)
        sku_key = field("sku", "code", "item code", "item_code")
        price_key = field("price gbp", "price_gbp", "price", "current price")
        if not sku_key or not price_key:
            raise ValueError("Required headers: SKU and Price GBP.")
        name_key = field("description", "name")
        group_key = field("product group", "group")
        status_key = field("price status", "status")
        source_key = field("price source", "source")
        book = {}
        for number, row in enumerate(reader, 2):
            if number > MAX_ITEMS + 1:
                raise ValueError("Too many price list rows")
            code = str(row.get(sku_key) or "").strip().upper()
            if not code:
                continue
            if not SKU.fullmatch(code) or code.startswith(("=", "+", "-", "@")):
                raise ValueError(f"Unsafe item code on row {number}")
            if code in book:
                raise ValueError(f"Duplicate item code {code} on row {number}")
            label = str(row.get(status_key) or "")[:110].strip() if status_key else ""
            held = label.casefold().startswith("hold")
            value = _money(row.get(price_key))
            if value is None and not held:
                raise ValueError(f"Price missing for {code} on row {number}")
            if held:
                value = None
            book[code] = {
                "price_pence": value,
                "description": str(row.get(name_key) or "")[:350].strip() if name_key else "",
                "group": str(row.get(group_key) or "")[:140].strip() if group_key else "",
                "origin": str(row.get(source_key) or "Price import")[:120].strip()
                          if source_key else "Price import",
                "status": ("HOLD" if held else "UNPRICED" if value == 0 else "REFERENCE"),
            }
        if not book:
            raise ValueError("No usable price-list records")
        return book
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise HTTPException(422, f"Invalid unified price-list CSV: {exc}") from exc


def merge_records(before, updates):
    """Latest price wins; price-only imports must not erase descriptions/groups."""
    combined = dict(before)
    for code, update in updates.items():
        current = before.get(code, {})
        combined[code] = {
            **current,
            **{key: value for key, value in update.items()
               if key not in ("description", "group") or value},
        }
    return combined


def _difference(before, new):
    added = sum(code not in before for code in new)
    merged = merge_records(before, new)
    changed = sum(code in before and before[code] != merged[code]
                  for code in new)
    unchanged = len(new) - added - changed
    held = sum(item["status"] == "HOLD" for item in new.values())
    zero = sum(item["status"] == "UNPRICED" for item in new.values())
    return {
        "uploaded_codes": len(new), "new_codes": added,
        "updated_codes": changed, "unchanged_codes": unchanged,
        "retained_existing_codes": len(before) - (len(new) - added),
        "held_codes": held, "zero_price_codes": zero,
        "resulting_total_codes": len(before) + added,
        "deletes_unmentioned_codes": False,
        "latest_import_wins_for_matching_codes": True,
    }


def preview_import(filename, raw):
    who = _admin()
    incoming = parse_price_upload(filename, raw)
    previous = active_book()
    before = previous["rows"] if previous else {}
    summary = _difference(before, incoming)
    if len(before) + summary["new_codes"] > MAX_ITEMS:
        raise HTTPException(413, "Unified price book would exceed 60,000 distinct codes.")
    sha = hashlib.sha256(raw).hexdigest()
    packed, _ = _pack(incoming)
    token = secrets.token_urlsafe(28)
    con = connect()
    try:
        _tables(con)
        con.execute(
            "INSERT INTO unified_price_book_previews VALUES(?,?,?,?,?,?,?,?,?)",
            (token, dt.datetime.now(dt.timezone.utc).isoformat(), who,
             previous["revision"] if previous else 0,
             previous["sha256"] if previous else None,
             str(filename)[:250], sha, json.dumps(summary), packed),
        )
        con.commit()
    finally:
        con.close()
    return {
        "preview_token": token, "source_file_sha256": sha,
        "current_revision": previous["revision"] if previous else 0,
        "changes": summary, "source_activated": False,
        "no_changes_to_issued_quotes": True,
        "prices_do_not_approve_maintenance_eligibility": True,
    }


def activate_import(request):
    who = _admin()
    reason = str(request.reason or "").strip()
    if not 12 <= len(reason) <= 500:
        raise HTTPException(422, "Enter an administrator reason (12–500 characters).")
    token = request.preview_token
    if not isinstance(token, str) or not 20 <= len(token) <= 120:
        raise HTTPException(422, "Invalid price-import preview.")
    con = connect()
    try:
        _tables(con)
        con.execute("BEGIN IMMEDIATE")
        stage = con.execute(
            "SELECT * FROM unified_price_book_previews WHERE token=?",
            (token,),
        ).fetchone()
        if not stage or stage["created_by"] != who:
            raise HTTPException(404, "Price-import preview not found for this administrator.")
        created = dt.datetime.fromisoformat(stage["created_at"])
        if dt.datetime.now(dt.timezone.utc) - created > PREVIEW_AGE:
            raise HTTPException(409, "Price-import preview expired; upload the list again.")
        previous = con.execute(
            "SELECT revision,snapshot_sha256,rows_zlib "
            "FROM unified_price_book_versions WHERE active=1"
        ).fetchone()
        revision = previous["revision"] if previous else 0
        fingerprint = previous["snapshot_sha256"] if previous else None
        if (revision != stage["expected_revision"]
                or fingerprint != stage["expected_sha256"]):
            raise HTTPException(409, "Current unified prices changed since preview; reload.")
        before = _unpack(previous["rows_zlib"], fingerprint) if previous else {}
        updates = _unpack(stage["new_rows_zlib"],
                          hashlib.sha256(json.dumps(
                              _unpack_unchecked(stage["new_rows_zlib"]),
                              sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")).hexdigest())
        summary = _difference(before, updates)
        if summary != json.loads(stage["summary_json"]):
            raise HTTPException(409, "Price-import preview no longer matches staged records.")
        if ((summary["held_codes"] or summary["zero_price_codes"])
                and not request.confirm_zero_and_held_prices):
            raise HTTPException(
                409, "Explicitly confirm held/zero-price items; they cannot be quoted."
            )
        merged = merge_records(before, updates)
        packed, final_sha = _pack(merged)
        con.execute("UPDATE unified_price_book_versions SET active=0 WHERE active=1")
        con.execute(
            "INSERT INTO unified_price_book_versions "
            "(revision,active,snapshot_sha256,source_file_sha256,filename,"
            "imported_at,imported_by,reason,changed_count,new_count,kept_count,rows_zlib)"
            " VALUES(?,1,?,?,?,?,?,?,?,?,?,?)",
            (revision + 1, final_sha, stage["source_file_sha256"],
             stage["filename"], dt.datetime.now(dt.timezone.utc).isoformat(),
             who, reason, summary["updated_codes"], summary["new_codes"],
             summary["retained_existing_codes"], packed),
        )
        con.execute("DELETE FROM unified_price_book_previews WHERE token=?", (token,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "activated": True, "revision": revision + 1, "snapshot_sha256": final_sha,
        "changes": summary, "previous_issued_quotes_unchanged": True,
        "maintenance_tariffs_not_approved": True,
    }


def _unpack_unchecked(blob):
    # Preview is already stored inside protected SQLite; verify its structure
    # and recompute its digest before release. Never trust client-supplied rows.
    try:
        d = zlib.decompressobj()
        raw = d.decompress(blob, MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD or not d.eof or d.unused_data or d.unconsumed_tail:
            raise ValueError("Bad staged import")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or len(data) > MAX_ITEMS:
            raise ValueError("Bad staged data")
        return data
    except (zlib.error, ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(503, "Staged price-import evidence is damaged.") from exc


@router.post("/preview")
async def preview_price_book_upload(file: UploadFile = File(...)):
    raw = await file.read(MAX_UPLOAD + 1)
    return preview_import(file.filename or "", raw)


@router.post("/activate")
def activate_price_book_upload(payload: ActivatePriceImport):
    return activate_import(payload)


@router.get("/status")
def price_book_status():
    _admin()
    current = active_book()
    return {
        "active": bool(current),
        "revision": current["revision"] if current else 0,
        "distinct_codes": len(current["rows"]) if current else 0,
        "snapshot_sha256": current["sha256"] if current else None,
        "last_imported_at": current["imported_at"] if current else None,
        "single_price_list": True,
        "new_imports_replace_matching_codes_and_keep_unmentioned": True,
        "maintenance_tariffs_approved": False,
    }


@router.get("/export.csv")
def price_book_export():
    _admin()
    current = active_book()
    if not current:
        raise HTTPException(404, "No active unified price master.")
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(("SKU", "Price GBP", "Description", "Product Group",
                     "Price Source", "Price Status"))
    for code, row in sorted(current["rows"].items()):
        value = row.get("price_pence")
        cells = (
            code, str(Decimal(value) / 100) if value is not None else "",
            row.get("description") or "", row.get("group") or "",
            row.get("origin") or "", row.get("status") or "",
        )
        writer.writerow([safe_excel_csv_cell(c) for c in cells])
    return Response(
        content="\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                'attachment; filename="Pulse_Unified_Master_Current.csv"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        }
    )
