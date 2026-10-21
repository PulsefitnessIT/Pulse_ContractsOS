"""Read-only pilot data readiness checks. Never exports customer details or financial totals.

The check is not an accounting certification: contract amounts, invoice previews,
warranties and sales revenue must not be treated as interchangeable.
"""
from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

WORKSHEETS = [
    "Home", "Maintenance Database", "Weekly Values", "Invoices",
    "Monthly Report", "Sales Report", "Quotes", "Expired",
]
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def workbook_check(path):
    path = Path(path)
    result = {"present": path.is_file(), "valid": False, "sheet_names": [], "issues": []}
    if not path.is_file():
        result["issues"].append("Approved Excel Master is missing from private pilot storage")
        return result
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Workbook ZIP integrity check failed")
            root = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = root.find(SHEET_NS + "sheets")
            if sheets is None:
                raise ValueError("Workbook sheet definitions are missing")
            result["sheet_names"] = [item.attrib["name"] for item in sheets]
            if result["sheet_names"] != WORKSHEETS:
                result["issues"].append("The workbook does not have the approved eight worksheets in order")
            else:
                result["valid"] = True
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError) as error:
        result["issues"].append("The approved Excel Master could not be validated: " + type(error).__name__)
    return result


def _amount_kind(value):
    if value is None or str(value).strip() == "":
        return "missing"
    text = str(value).strip().replace("£", "").replace(",", "").replace(" ", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        number = Decimal(text)
        if not number.is_finite():
            return "invalid"
        if number == 0:
            return "zero"
        return "negative" if number < 0 else "positive"
    except (InvalidOperation, ValueError):
        return "invalid"


def _contract_group(text):
    label = str(text or "").lower()
    if "charge" in label or "reactive" in label:
        return "Chargeable"
    if any(x in label for x in ("warr", "gold", "platinum", "silver")):
        return "Warranty"
    if any(x in label for x in ("contract", "maintenance", "type a", "type b", "type c")):
        return "Contract"
    return "Other / unclear"


def assess_database(db_path, workbook_path):
    """Aggregates only; never returns names, contract IDs, paths or amounts."""
    workbook = workbook_check(workbook_path)
    result = {
        "database_present": Path(db_path).is_file(),
        "database_valid": False,
        "workbook": workbook,
        "contracts": {
            "active": 0, "expired": 0, "malformed_records": 0,
            "missing_reference": 0, "missing_expiry": 0, "missing_sales_manager": 0,
            "repeated_reference_records": 0,
        },
        "financial_completeness": {
            "positive": 0, "zero": 0, "negative": 0, "missing": 0,
            "invalid": 0, "recorded": 0, "recorded_percent": 0.0,
            "by_cover_type": {},
            "is_verified_revenue": False,
        },
        "ready_for_data_review": False,
        "issues": list(workbook["issues"]),
    }
    if not Path(db_path).is_file():
        result["issues"].append("Private contract database is missing; restore a reviewed snapshot")
        return result
    try:
        # Explicit read-only mode avoids accidentally creating an empty database.
        uri = "file:" + quote(str(Path(db_path).resolve()), safe="/") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=15) as con:
            check = con.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                raise ValueError("Database integrity check failed")
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contracts'").fetchone():
                raise ValueError("Contracts table is missing")
            result["database_valid"] = True
            refs = Counter()
            cover = {}
            money = result["financial_completeness"]
            summary = result["contracts"]
            for status, raw in con.execute("SELECT status,fields FROM contracts"):
                if status == "Expired":
                    summary["expired"] += 1
                    continue
                if status != "Active":
                    continue
                summary["active"] += 1
                try:
                    fields = json.loads(raw)
                    if not isinstance(fields, dict):
                        raise ValueError("Fields are not an object")
                except (TypeError, ValueError, json.JSONDecodeError):
                    summary["malformed_records"] += 1
                    continue
                ref = str(fields.get("Contract number") or "").strip().casefold()
                if ref:
                    refs[ref] += 1
                else:
                    summary["missing_reference"] += 1
                if not str(fields.get("Expiry date") or "").strip():
                    summary["missing_expiry"] += 1
                if not str(fields.get("Sales manager") or "").strip():
                    summary["missing_sales_manager"] += 1
                group = _contract_group(fields.get("Contract / warranty type"))
                if group not in cover:
                    cover[group] = Counter()
                kind = _amount_kind(fields.get("Contract amount (£)"))
                cover[group][kind] += 1
                money[kind] += 1
            summary["repeated_reference_records"] = sum(count for count in refs.values() if count > 1)
            money["recorded"] = money["positive"] + money["zero"] + money["negative"]
            if summary["active"]:
                money["recorded_percent"] = round(100 * money["recorded"] / summary["active"], 1)
            money["by_cover_type"] = {
                key: {"total": sum(counts.values()), **dict(sorted(counts.items()))}
                for key, counts in sorted(cover.items())
            }
    except (sqlite3.Error, OSError, ValueError) as error:
        result["issues"].append("Private contract database failed validation: " + type(error).__name__)
    if result["database_valid"] and result["contracts"]["active"] == 0:
        result["issues"].append("No active contracts were found in the private snapshot")
    if result["contracts"]["malformed_records"]:
        result["issues"].append("Some active contract records contain unreadable fields")
    missing = result["financial_completeness"]["missing"]
    invalid = result["financial_completeness"]["invalid"]
    if missing or invalid:
        result["issues"].append("Contract amounts are incomplete: do not report their sum as total contract revenue")
    if result["contracts"]["repeated_reference_records"]:
        result["issues"].append("Repeated contract numbers need coordinator review; they are not automatically duplicates")
    result["ready_for_data_review"] = bool(
        result["database_valid"] and workbook["valid"]
        and result["contracts"]["active"] > 0
        and result["contracts"]["malformed_records"] == 0
    )
    return result
