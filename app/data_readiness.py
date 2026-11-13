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

WORKSHEETS = [
    "Home", "Maintenance Database", "Weekly Values", "Invoices",
    "Monthly Report", "Sales Report", "Quotes", "Expired",
]
CURRENT_WORKSHEETS = [
    "Home", "Action Centre", "Maintenance Database", "MOD",
    "Weekly Values", "Invoices", "Monthly Report", "Sales Report",
    "Quotes", "Expired",
]
# Approved 13 November 2026 source includes service planning and Sicon
# registers. Do not mistake a 15-tab source for the older 10-tab layout.
PULSE_15_WORKSHEETS = [
    "Home", "Action Centre", "Maintenance Database", "MOD",
    "Service Planner", "MOD Service Planner", "Weekly Values", "Invoices",
    "Monthly Report", "Sales Report", "Quotes", "Expired",
    "Sicon Contracts", "PPM Annual Detail - Commercial",
    "PPM Annual Detail - MOD",
]
PULSE_15_SOURCE_SHEETS = (
    "Service Planner", "MOD Service Planner", "Sicon Contracts",
    "PPM Annual Detail - Commercial", "PPM Annual Detail - MOD",
)

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def workbook_check(path):
    path = Path(path)
    result = {"present": path.is_file(), "valid": False, "sheet_names": [], "issues": []}
    if not path.is_file():
        result["issues"].append("Approved Excel Master is missing from private pilot storage")
        return result
    try:
        with zipfile.ZipFile(path) as archive:
            from .excel_io import check_excel_archive_limits
            check_excel_archive_limits(archive)
            if archive.testzip() is not None:
                raise ValueError("Workbook ZIP integrity check failed")
            required_parts = ["xl/workbook.xml", "xl/styles.xml",
                              "xl/_rels/workbook.xml.rels"]
            if any(name not in archive.namelist() for name in required_parts):
                raise ValueError("Required workbook metadata parts are missing")
            root = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = root.find(SHEET_NS + "sheets")
            if sheets is None:
                raise ValueError("Workbook sheet definitions are missing")
            result["sheet_names"] = [item.attrib["name"] for item in sheets]
            if result["sheet_names"] not in (
                    WORKSHEETS, CURRENT_WORKSHEETS, PULSE_15_WORKSHEETS):
                result["issues"].append(
                    "Workbook sheet order does not match an approved 8-, 10- or 15-tab Master"
                )
            else:
                # Verify sheet relationship targets rather than assuming sheet
                # positions. Old file IDs need not change when tabs are inserted.
                from .excel_io import ExcelSource
                src = ExcelSource(path)
                try:
                    for name in result["sheet_names"]:
                        if name not in src.sheet_parts:
                            raise ValueError("Missing worksheet part")
                    if result["sheet_names"] == PULSE_15_WORKSHEETS:
                        # These two annual-cycle registers are source evidence,
                        # not new active customer contracts. Require both to
                        # remain hidden in the approved 15-tab export.
                        states={sheet.attrib["name"]:sheet.attrib.get("state")
                                for sheet in sheets}
                        for name in ("PPM Annual Detail - Commercial",
                                     "PPM Annual Detail - MOD"):
                            if states.get(name) != "hidden":
                                result["issues"].append(
                                    "Approved annual PPM source tab is not hidden: " + name
                                )
                        key_fields={
                            "Service Planner":("Contract number","Service year key (internal)"),
                            "MOD Service Planner":("Contract number","Service year key (internal)"),
                            "PPM Annual Detail - Commercial":("Contract number","Service year key (internal)"),
                            "PPM Annual Detail - MOD":("Contract number","Service year key (internal)"),
                            "Sicon Contracts":("Sicon contract ID","Sicon line ID"),
                        }
                        for name,required in key_fields.items():
                            headers,_=src.records(name)
                            missing=set(required)-set(headers)
                            if missing:
                                result["issues"].append(
                                    "Missing source fields on " + name + ": "
                                    + ", ".join(sorted(missing))
                                )
                        # The real commercial workbook stores 600 durable
                        # MAIN- IDs in blank-heading column AD. Read but
                        # preserve that physical source cell on export.
                        headings,_=src.records("Maintenance Database")
                        if "Record ID" not in headings:
                            result["issues"].append(
                                "Maintenance Database internal ID column AD could not be mapped"
                            )
                    if not result["issues"]:
                        result["valid"] = True
                        result["profile"] = (
                            "pulse_15_tab_operational_master"
                            if result["sheet_names"] == PULSE_15_WORKSHEETS else
                            "ten_tab_mod_action_centre"
                            if result["sheet_names"] == CURRENT_WORKSHEETS else
                            "legacy_eight_tab"
                        )
                finally:
                    src.z.close()
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
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=15) as con:
            check = con.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                raise ValueError("Database integrity check failed")
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contracts'").fetchone():
                raise ValueError("Contracts table is missing")
            result["database_valid"] = True
            refs = Counter()
            cover = {}
            source_labels = {}
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
                literal_label = str(fields.get("Contract / warranty type") or "").strip()
                literal_label = literal_label or "(blank in record)"
                if literal_label not in source_labels:
                    source_labels[literal_label] = Counter()
                group = _contract_group(fields.get("Contract / warranty type"))
                if group not in cover:
                    cover[group] = Counter()
                kind = _amount_kind(fields.get("Contract amount (£)"))
                cover[group][kind] += 1
                source_labels[literal_label][kind] += 1
                money[kind] += 1
            summary["repeated_reference_records"] = sum(count for count in refs.values() if count > 1)
            money["recorded"] = money["positive"] + money["zero"] + money["negative"]
            if summary["active"]:
                money["recorded_percent"] = round(100 * money["recorded"] / summary["active"], 1)
            money["by_cover_type"] = {
                key: {"total": sum(counts.values()), **dict(sorted(counts.items()))}
                for key, counts in sorted(cover.items())
            }
            money["cover_type_grouping_is_heuristic"] = True
            money["by_recorded_source_label"] = {
                key: {"total": sum(counts.values()), **dict(sorted(counts.items()))}
                for key, counts in sorted(source_labels.items())
            }
            money["recorded_source_labels_are_not_legal_cover_verification"] = True
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


def missing_amount_review_rows(db_path):
    """Coordinator review queue for missing/invalid active contract amounts.

    Never invent amounts or silently fill missing values with zero.
    Call only from an authenticated route when private customer data is present.
    """
    rows = []
    if not Path(db_path).is_file():
        return rows
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=15) as con:
        for contract_id, raw in con.execute(
            "SELECT id,fields FROM contracts WHERE status='Active'"
        ):
            try:
                item = json.loads(raw)
                if not isinstance(item, dict):
                    continue
            except (TypeError, ValueError):
                continue
            raw_amount = item.get("Contract amount (£)")
            state = _amount_kind(raw_amount)
            if state not in ("missing", "invalid"):
                continue
            rows.append({
                "Contract ID": contract_id,
                "Customer / site": str(item.get("Customer / site") or ""),
                "Contract number": str(item.get("Contract number") or ""),
                "Contract / warranty type": str(item.get("Contract / warranty type") or ""),
                "Sales manager": str(item.get("Sales manager") or "Unassigned"),
                "Recorded amount": str(raw_amount or ""),
                "Review reason": "Missing amount" if state == "missing" else "Unclear amount",
            })
    return sorted(rows, key=lambda item: (
        item["Sales manager"].casefold(), item["Customer / site"].casefold(), item["Contract ID"]
    ))


def safe_excel_csv_cell(value):
    """Protect exported CSV against formula execution in spreadsheet software."""
    text = str(value if value is not None else "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
