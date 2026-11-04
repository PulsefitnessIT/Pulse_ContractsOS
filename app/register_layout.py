"""Verify safe, copy-compatible Master and Expired register columns.

The Expired worksheet must begin with the exact same ordered columns as the
Maintenance Database (and MOD). Historical-only columns may follow at the
end; they are never discarded or silently mapped into active contract fields.
The approved private workbook remains authoritative and unmodified.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from .excel_io import ExcelSource, NS, splitcell

MAIN = "Maintenance Database"
MOD = "MOD"
EXPIRED = "Expired"
ACTIVE = (MAIN, MOD)
APPEND_SHEET = EXPIRED
MAX_COLS = 250
MAX_ROWS = 1_048_575
NS_ROW = "{%s}row" % NS
NS_CELL = "{%s}c" % NS
NS_DATA = "{%s}sheetData" % NS


def verify_headers(active, expired, mod=None):
    """Pure validator, suitable for fictional regression fixtures."""
    active = tuple(str(h or "").strip() for h in active)
    expired = tuple(str(h or "").strip() for h in expired)
    mod = tuple(str(h or "").strip() for h in mod) if mod is not None else None

    if not 2 <= len(active) <= MAX_COLS:
        raise ValueError("Maintenance Database has no valid column headings.")
    if not all(active) or len(set(active)) != len(active):
        raise ValueError("Maintenance Database has duplicate or blank column headings.")
    if not {"Customer / site", "Record ID", "Expiry date"}.issubset(active):
        raise ValueError("Maintenance Database is missing identity or expiry columns.")
    if len(expired) < len(active):
        raise ValueError("Expired worksheet has fewer columns than Maintenance Database.")
    if expired[:len(active)] != active:
        mismatch = next((i for i,(left,right) in
                         enumerate(zip(active,expired),start=1)
                         if left != right),1)
        raise ValueError(
            "Expired columns do not mirror Maintenance Database at column "
            + str(mismatch) + ". Align the worksheet before transferring records."
        )
    if not all(expired) or len(set(expired)) != len(expired):
        raise ValueError("Expired has duplicate or blank extra columns.")
    if mod is not None and mod != active:
        raise ValueError("MOD columns must exactly mirror Maintenance Database.")
    return {
        "aligned": True,
        "shared_columns": list(active),
        "shared_column_count": len(active),
        "expired_only_columns": list(expired[len(active):]),
        "expired_only_column_count": len(expired) - len(active),
        "expired_only_columns_at_end": True,
        "mod_mirrors_maintenance": mod is not None,
        "safe_copy_paste_range": f"A:{_column(len(active))}",
    }


def _column(number):
    result = ""
    while number:
        number, digit = divmod(number-1, 26)
        result = chr(65+digit) + result
    return result


def _sheet_headers(source, sheet):
    if sheet not in source.sheet_parts:
        raise ValueError(f"{sheet} worksheet is not present in the approved Master.")
    root = source.sheet(sheet)
    data = root.find(NS_DATA)
    if data is None:
        raise ValueError(f"{sheet} worksheet contains no records.")
    rows = data.findall(NS_ROW)
    if not rows or int(rows[0].get("r") or "0") != 1:
        raise ValueError(f"{sheet} has no first-row header.")
    first = rows[0]
    positions = {}
    for cell in first.findall(NS_CELL):
        ref = cell.get("r")
        if not ref:
            continue
        col, row = splitcell(ref)
        if row != 1 or col > MAX_COLS:
            raise ValueError(f"{sheet} has an invalid header location.")
        positions[col] = str(source.cell_value(cell) or "").strip()
    if not positions or max(positions) > MAX_COLS:
        raise ValueError(f"{sheet} has no recognised headings.")
    cols = [positions.get(i, "") for i in range(1,max(positions)+1)]
    final = max(int(row.get("r") or "0") for row in rows)
    if final < 1 or final > MAX_ROWS:
        raise ValueError("Workbook data row is outside the supported Excel range.")
    return cols, final


@lru_cache(maxsize=4)
def _checked(file_path, mtime_ns, length):
    source = ExcelSource(file_path)
    try:
        active, active_last = _sheet_headers(source, MAIN)
        expired, expired_last = _sheet_headers(source, EXPIRED)
        mod, mod_last = (_sheet_headers(source, MOD)
                         if MOD in source.sheet_parts else (None, 0))
        checked = verify_headers(active, expired, mod)
        return {
            **checked, "source_registers": [MAIN] + ([MOD] if mod is not None else []),
            "template_last_expired_row": expired_last,
            "template_last_maintenance_row": active_last,
            "template_last_mod_row": mod_last,
        }
    finally:
        source.z.close()


def current_layout(path):
    """Inspect layout only; no contract data is returned to the browser."""
    name = Path(path).expanduser().resolve()
    try:
        stat = name.stat()
        return dict(_checked(str(name), stat.st_mtime_ns, stat.st_size))
    except (OSError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(409,
            "The approved Master layout is incompatible with safe expiry "
            "transfer. Update the private workbook first: "+str(exc)[:220]) from exc
