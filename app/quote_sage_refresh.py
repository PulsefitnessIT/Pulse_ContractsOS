"""Controlled Sage price-list refresh: preview, compare, commit, history.

No writes to Sage 200 or original SmartQuote database. Uploaded Sage exports
stay in the protected Contracts OS SQLite store, not the source repository.
Only authenticated pilot Administrators can preview and activate an import.
"""
from __future__ import annotations

import csv
import gzip
import datetime as dt
import hashlib
import io
import json
import re
import secrets
import sqlite3
import zipfile
import zlib
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from . import pilot_access
from .store import connect
from .quote_price_overrides import _admin

router = APIRouter(prefix="/api/quoting/sage-refresh", tags=["Protected Sage price-list refresh"])
SIZE_LIMIT = 16 * 1024 * 1024
MAX_SHEET_XML = 40 * 1024 * 1024
MAX_STRINGS_XML = 10 * 1024 * 1024
MAX_ROWS = 60000
MAX_PREVIEW_AGE = dt.timedelta(hours=2)
MIN_VALID = 5
COLUMNS = ("code", "name", "product group description", "sales price")
N = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SOURCE_LABEL = "Sage Sales Price export — exact item-code equipment price basis"
ALLOWED_GROUPS = frozenset((
    "Strength Equipment", "Cardiovascular Equipment", "Functional Equipment",
    "Free Weight Benches & Racks", "Studio/Circuit Equipment",
    "Non Pulse Equipment", "Equipment with Serial Numbers",
    "Equipment without serial numbers",
))
SKU = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,99}$")


def _date(value):
    try:
        date = dt.date.fromisoformat(value)
        if date.isoformat() != value or date > dt.date.today():
            raise ValueError()
        return date
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Use the actual Sage price-export date, YYYY-MM-DD, not a future date.") from exc


def _review_due(date):
    try:
        return date.replace(year=date.year + 1).isoformat()
    except ValueError:
        return date.replace(year=date.year + 1, day=28).isoformat()


def _parse_price(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        p = Decimal(str(value).replace("£", "").replace(",", "").strip())
        if not p.is_finite() or not 0 < p <= 1000000:
            return None
        return float(p.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation, TypeError):
        return None


def _csv_rows(raw):
    try:
        text = raw.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
        reader = csv.reader(io.StringIO(text, newline=""), dialect)
        for position, parts in enumerate(reader, start=1):
            if any(str(p).strip() for p in parts):
                yield position, [str(p).strip() for p in parts]
    except (UnicodeError, csv.Error) as exc:
        raise HTTPException(422, "Sage CSV is not a valid UTF-8 equipment export.") from exc


def _xlsx_rows(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
            names = workbook.namelist()
            if (len(names) > 200 or any(name.startswith(("../", "/")) or ".." in name.split("/") for name in names)
                    or "[Content_Types].xml" not in names):
                raise ValueError("Invalid spreadsheet archive")
            sheets = sorted(
                name for name in names
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            if not sheets:
                raise ValueError("No equipment worksheet")
            strings = []
            if "xl/sharedStrings.xml" in names:
                if workbook.getinfo("xl/sharedStrings.xml").file_size > MAX_STRINGS_XML:
                    raise ValueError("Oversized shared strings")
                root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
                strings = [
                    "".join(n.text or "" for n in el.iter(N + "t"))
                    for el in root.iter(N + "si")
                ]
                if len(strings) > 100000:
                    raise ValueError("Too many shared strings")
            sheet = sheets[0]  # The controlled Sage export uses its first worksheet.
            if workbook.getinfo(sheet).file_size > MAX_SHEET_XML:
                raise ValueError("Oversized worksheet")
            sheet_xml = workbook.read(sheet)
            stream = io.BytesIO(sheet_xml)
            for _, element in ET.iterparse(stream, events=("end",)):
                if element.tag != N + "row":
                    continue
                number = int(element.attrib.get("r") or 0)
                fields = {}
                for cell in element.findall(N + "c"):
                    column = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
                    if not column or column.group(0) not in ("A", "B", "C", "D"):
                        continue
                    if cell.find(N + "f") is not None:
                        raise ValueError("Formula-driven prices cannot be treated as Sage export evidence")
                    val = cell.find(N + "v")
                    kind = cell.attrib.get("t", "")
                    value = val.text if val is not None else ""
                    if kind == "s" and value:
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.iter(N + "t"))
                    fields[column.group(0)] = str(value or "").strip()
                element.clear()
                if fields:
                    yield number, [fields.get(k, "") for k in ("A", "B", "C", "D")]
    except (ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError,
            OSError, OverflowError) as exc:
        raise HTTPException(422, "Invalid or unsafe Sage XLSX export. Export a new Sage item price list.") from exc


def parse_export(filename, raw):
    """Match original SmartQuote's four-column Sage equipment export layout."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= SIZE_LIMIT:
        raise HTTPException(413, "Sage export is empty or exceeds 16 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise HTTPException(422, "Upload Sage price list as CSV or XLSX.")
    rows = _csv_rows(raw) if suffix == ".csv" else _xlsx_rows(raw)
    items, conflicts, excluded, invalid, total, equipment, seen_header = {}, set(), 0, 0, 0, 0, False
    for position, parts in rows:
        if not seen_header:
            if tuple(p.lower().strip() for p in parts[:4]) != COLUMNS:
                raise HTTPException(
                    422, "Expected Sage export columns: Code, Name, Product Group Description, Sales Price."
                )
            seen_header = True
            continue
        total += 1
        if total > MAX_ROWS:
            raise HTTPException(422, "Sage export exceeds 60,000 item rows.")
        code, name, group, price = (parts + ["", "", "", ""])[:4]
        if group not in ALLOWED_GROUPS:
            excluded += 1
            continue
        equipment += 1
        sku = code.strip().upper()
        amount = _parse_price(price)
        if not SKU.fullmatch(sku) or amount is None:
            invalid += 1
            continue
        item = {
            "sku": sku, "name": name[:250], "group": group[:120],
            "sales_price": amount, "row": position,
        }
        old = items.get(sku)
        if old and any(old[k] != item[k] for k in ("name", "group", "sales_price")):
            conflicts.add(sku)
        else:
            items.setdefault(sku, item)
    for key in conflicts:
        items.pop(key, None)
    if not seen_header or len(items) < MIN_VALID:
        raise HTTPException(
            422, "Sage equipment export is incomplete (fewer than five usable item codes)."
        )
    return {
        "prices": items,
        "total_rows": total,
        "equipment_rows": equipment,
        "usable_rows": len(items),
        "excluded_group_rows": excluded,
        "invalid_equipment_rows": invalid,
        "conflicting_item_codes": len(conflicts),
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _ensure_tables(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS smartquote_sage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            active INTEGER NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL, imported_by TEXT NOT NULL,
            filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
            source_date TEXT NOT NULL, review_due TEXT NOT NULL,
            total_rows INTEGER NOT NULL, usable_rows INTEGER NOT NULL,
            excluded_rows INTEGER NOT NULL, payload BLOB NOT NULL,
            change_counts TEXT NOT NULL, previous_sha256 TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_sage_source_hash
          ON smartquote_sage_snapshots(file_sha256);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_sage_active
          ON smartquote_sage_snapshots(active) WHERE active=1;
        CREATE TABLE IF NOT EXISTS smartquote_sage_import_previews (
            token TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            created_by TEXT NOT NULL, filename TEXT NOT NULL,
            file_sha256 TEXT NOT NULL, source_date TEXT NOT NULL,
            expected_active_sha256 TEXT, payload BLOB NOT NULL,
            summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS smartquote_sage_price_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL, sku TEXT NOT NULL,
            change_kind TEXT NOT NULL, previous_price REAL,
            current_price REAL, previous_name TEXT, current_name TEXT,
            previous_group TEXT, current_group TEXT,
            FOREIGN KEY(snapshot_id) REFERENCES smartquote_sage_snapshots(id)
        );
        CREATE INDEX IF NOT EXISTS idx_unified_sage_changes
          ON smartquote_sage_price_changes(snapshot_id,change_kind,sku);
    """)
    # Support existing local pilots created before the source-group columns.
    fields = {row[1] for row in con.execute(
        "PRAGMA table_info(smartquote_sage_price_changes)"
    )}
    for column in ("previous_group", "current_group"):
        if column not in fields:
            con.execute(
                "ALTER TABLE smartquote_sage_price_changes "
                f"ADD COLUMN {column} TEXT"
            )


def _packed(prices):
    return gzip.compress(json.dumps(prices, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), compresslevel=9)


def _unpacked(blob):
    from .quote_sage_reference import _unpack
    return _unpack(blob)


def _current():
    """Resolve actual effective source: Contracts OS override or original V10."""
    from .quote_sage_reference import snapshot
    return snapshot()


def difference(previous, current):
    """Compare exact SKUs; never silently discard removed equipment."""
    before = previous.get("prices", {}) if previous else {}
    keys = sorted(set(before) | set(current))
    changes = []
    counts = Counter()
    for sku in keys:
        older, newer = before.get(sku), current.get(sku)
        if older is None:
            kind = "added"
        elif newer is None:
            kind = "removed"
        elif older.get("sales_price") != newer.get("sales_price"):
            kind = "price_changed"
        elif older.get("name") != newer.get("name") or older.get("group") != newer.get("group"):
            kind = "details_changed"
        else:
            kind = "unchanged"
        counts[kind] += 1
        if kind != "unchanged":
            changes.append({
                "sku": sku, "kind": kind,
                "previous_price": older.get("sales_price") if older else None,
                "current_price": newer.get("sales_price") if newer else None,
                "previous_name": older.get("name") if older else None,
                "current_name": newer.get("name") if newer else None,
                "previous_group": older.get("group") if older else None,
                "current_group": newer.get("group") if newer else None,
            })
    for kind in ("added", "removed", "price_changed", "details_changed", "unchanged"):
        counts.setdefault(kind, 0)
    return dict(counts), changes


def preview_import(filename, raw, source_date):
    who = _admin()
    date = _date(source_date)
    parsed = parse_export(filename, raw)
    if parsed["conflicting_item_codes"]:
        raise HTTPException(422, "Sage export contains conflicting equipment item codes. Correct the export before replacing prices.")
    previous = _current()
    if previous and date.isoformat() < previous["source_date"]:
        raise HTTPException(409, "Sage export date is older than the active source. Verify the list revision.")
    before_sha = previous["source_file_sha256"] if previous else None
    if before_sha == parsed["source_file_sha256"]:
        raise HTTPException(409, "This exact Sage export is already active.")
    counts, changes = difference(previous, parsed["prices"])
    old_count = len(previous["prices"]) if previous else 0
    high_removal = old_count >= 20 and counts["removed"] > max(10, int(old_count * .10))
    summary = {
        "source_date": date.isoformat(), "filename": Path(filename).name[:140],
        "file_sha256": parsed["source_file_sha256"],
        "total_rows": parsed["total_rows"],
        "equipment_rows": parsed["equipment_rows"],
        "usable_rows": parsed["usable_rows"],
        "excluded_group_rows": parsed["excluded_group_rows"],
        "invalid_equipment_rows": parsed["invalid_equipment_rows"],
        "conflicting_item_codes": parsed["conflicting_item_codes"],
        "previous_usable_rows": old_count,
        "change_counts": counts,
        "large_removal_warning": high_removal,
        "source_precedence": "August 2026 List Price first, Sage for other exact item codes",
        "changes_preview": changes[:30],
        "changes_total": len(changes),
        "automatic_quote_issuance": False,
    }
    token = secrets.token_urlsafe(24)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    con = connect()
    try:
        _ensure_tables(con)
        con.execute(
            "INSERT INTO smartquote_sage_import_previews "
            "(token,created_at,created_by,filename,file_sha256,source_date,"
            "expected_active_sha256,payload,summary) VALUES(?,?,?,?,?,?,?,?,?)",
            (token, now, who, Path(filename).name[:140], parsed["source_file_sha256"],
             date.isoformat(), before_sha, _packed(parsed["prices"]),
             json.dumps(summary, separators=(",", ":"))),
        )
        con.commit()
    finally:
        con.close()
    return {"preview_token": token, **summary}


class SageApply(BaseModel):
    preview_token: str
    reason: str
    confirm_large_removal: bool = False


def activate_preview(payload):
    who = _admin()
    reason = payload.reason.strip()
    if not 12 <= len(reason) <= 500:
        raise HTTPException(422, "Record the purpose of this price-list refresh (12–500 characters).")
    token = payload.preview_token
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise HTTPException(422, "Invalid or expired Sage preview.")
    # Read the original source before beginning a transaction in Contracts OS;
    # the historic source database is always opened read-only.
    observed = _current()
    now = dt.datetime.now(dt.timezone.utc)
    con = connect()
    try:
        _ensure_tables(con)
        con.execute("BEGIN IMMEDIATE")
        record = con.execute(
            "SELECT * FROM smartquote_sage_import_previews WHERE token=?", (token,)
        ).fetchone()
        if not record or record["created_by"] != who:
            raise HTTPException(404, "Sage preview not found for this administrator.")
        created = dt.datetime.fromisoformat(record["created_at"])
        if now - created > MAX_PREVIEW_AGE:
            raise HTTPException(409, "Sage preview expired; upload the current list again.")
        expected = record["expected_active_sha256"]
        # The local active snapshot cannot change while the SQLite write
        # transaction holds the lock. Original SmartQuote remains read-only.
        latest = con.execute(
            "SELECT file_sha256 FROM smartquote_sage_snapshots "
            "WHERE active=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest_sha = latest["file_sha256"] if latest else (
            observed["source_file_sha256"] if observed else None
        )
        if latest_sha != expected:
            raise HTTPException(409, "Sage prices changed since preview. Upload and compare again.")
        summary = json.loads(record["summary"])
        if summary["large_removal_warning"] and not payload.confirm_large_removal:
            raise HTTPException(
                409, "A large number of Sage item codes would disappear. "
                "Confirm the full-list removal risk explicitly."
            )
        if con.execute(
            "SELECT 1 FROM smartquote_sage_snapshots WHERE file_sha256=?",
            (record["file_sha256"],)
        ).fetchone():
            raise HTTPException(409, "This Sage file was previously installed; stage a new dated export.")
        new_prices = _unpacked(record["payload"])
        actual_counts, change_rows = difference(observed, new_prices)
        if actual_counts != summary["change_counts"]:
            raise HTTPException(409, "Source contents changed since Sage preview.")
        con.execute("UPDATE smartquote_sage_snapshots SET active=0 WHERE active=1")
        stamp = now.isoformat(timespec="seconds")
        cur = con.execute(
            "INSERT INTO smartquote_sage_snapshots "
            "(active,imported_at,imported_by,filename,file_sha256,"
            "source_date,review_due,total_rows,usable_rows,excluded_rows,"
            "payload,change_counts,previous_sha256) "
            "VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?)",
            (stamp, who, record["filename"], record["file_sha256"],
             record["source_date"], _review_due(dt.date.fromisoformat(record["source_date"])),
             summary["total_rows"], summary["usable_rows"],
             summary["excluded_group_rows"] + summary["invalid_equipment_rows"]
             + summary["conflicting_item_codes"], record["payload"],
             json.dumps(actual_counts), expected),
        )
        if change_rows:
            con.executemany(
                "INSERT INTO smartquote_sage_price_changes "
                "(snapshot_id,sku,change_kind,previous_price,current_price,"
                "previous_name,current_name,previous_group,current_group) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                ((cur.lastrowid, item["sku"], item["kind"],
                  item["previous_price"], item["current_price"],
                  item["previous_name"], item["current_name"],
                  item["previous_group"], item["current_group"])
                 for item in change_rows),
            )
        con.execute("DELETE FROM smartquote_sage_import_previews WHERE token=?", (token,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "activated": True, "snapshot_id": cur.lastrowid,
        "source_date": record["source_date"], "file_sha256": record["file_sha256"],
        "change_counts": actual_counts,
        "source_data_written_to_sage": False,
        "original_quotes_updated": False,
        "price_override_review_required_after_refresh": True,
        "customer_quote_issue_enabled": False,
    }


@router.post("/preview")
async def preview_sage_upload(
    file: UploadFile = File(...),
    source_date: str = Form(...)
):
    _admin()
    raw = await file.read(SIZE_LIMIT + 1)
    return preview_import(file.filename or "", raw, source_date)


@router.post("/activate")
def activate_sage_upload(payload: SageApply):
    return activate_preview(payload)


@router.get("/status")
def sage_refresh_status():
    _admin()
    con = connect()
    try:
        try:
            active = con.execute(
                "SELECT id,filename,file_sha256,source_date,review_due,"
                "imported_at,imported_by,total_rows,usable_rows,change_counts "
                "FROM smartquote_sage_snapshots WHERE active=1"
            ).fetchone()
            recent = con.execute(
                "SELECT id,filename,source_date,imported_at,imported_by,"
                "usable_rows,change_counts,active "
                "FROM smartquote_sage_snapshots ORDER BY id DESC LIMIT 20"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            active, recent = None, []
    finally:
        con.close()
    return {
        "local_active": dict(active) if active else None,
        "history": [
            {**dict(row), "change_counts": json.loads(row["change_counts"])}
            for row in recent
        ],
        "original_sage_database_unmodified": True,
    }


@router.get("/changes")
def sage_refresh_changes(
    snapshot_id: int = Query(..., ge=1),
    kind: str = Query("", max_length=30),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    _admin()
    if kind and kind not in ("added", "removed", "price_changed", "details_changed"):
        raise HTTPException(422, "Choose a valid Sage change category.")
    con = connect()
    try:
        where = "snapshot_id=?" + (" AND change_kind=?" if kind else "")
        params = (snapshot_id, kind) if kind else (snapshot_id,)
        exists = con.execute(
            "SELECT id FROM smartquote_sage_snapshots WHERE id=?",
            (snapshot_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(404, "No recorded Sage import for this snapshot.")
        total = con.execute(
            f"SELECT COUNT(*) FROM smartquote_sage_price_changes WHERE {where}", params
        ).fetchone()[0]
        rows = con.execute(
            "SELECT sku,change_kind,previous_price,current_price,"
            "previous_name,current_name,previous_group,current_group "
            f"FROM smartquote_sage_price_changes WHERE {where} "
            "ORDER BY sku LIMIT ? OFFSET ?", (*params, limit, offset)
        ).fetchall()
    finally:
        con.close()
    return {
        "snapshot_id": snapshot_id, "total": total,
        "limit": limit, "offset": offset, "items": [dict(r) for r in rows],
        "read_only": True,
    }
