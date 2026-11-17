"""Synthetic tests: protected Sage import and original quotation preservation."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi import HTTPException

from app import quote_sage_refresh as refresh
from app import quote_sage_reference as reference


def activate_local_db(tmp_path, monkeypatch):
    dbpath = tmp_path / "contracts-local.sqlite3"

    def db_connection():
        db = sqlite3.connect(str(dbpath), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    monkeypatch.setattr(refresh, "connect", db_connection)
    monkeypatch.setattr(reference, "DB", str(dbpath))
    monkeypatch.setattr(refresh.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(refresh.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(refresh.pilot_access, "actor", lambda name="": "fictional-admin")
    return dbpath


def csv_bytes(items):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Code", "Name", "Product Group Description", "Sales Price"])
    for code, price, *rest in items:
        writer.writerow([
            code, rest[0] if rest else "Fictional gym equipment",
            "Cardiovascular Equipment",
            str(price),
        ])
    return out.getvalue().encode("utf-8")


def dataset(count=6, base=100):
    return [(f"FIC-{i:04d}", base+i) for i in range(count)]


def date():
    return dt.date.today().isoformat()


def test_sage_first_refresh_and_local_price_read_precedence(tmp_path, monkeypatch):
    db = activate_local_db(tmp_path, monkeypatch)
    raw = csv_bytes(dataset())
    staged = refresh.preview_import("sage.csv", raw, date())
    assert staged["usable_rows"] == 6
    assert staged["change_counts"]["added"] == 6
    assert staged["change_counts"]["price_changed"] == 0
    assert staged["changes_total"] == 6
    assert reference.snapshot() is None
    result = refresh.activate_preview(refresh.SageApply(
        preview_token=staged["preview_token"],
        reason="Full authorised Sage price list refresh",
    ))
    assert result["activated"] is True
    assert result["source_data_written_to_sage"] is False
    assert result["original_quotes_updated"] is False
    live = reference.snapshot()
    assert live["source_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert live["prices"]["FIC-0002"]["sales_price"] == 102
    assert live["source_date"] == date()
    assert live["review_overdue"] is False
    item = reference.reference("fic-0002", live)
    assert item["sage_sales_price"] == 102
    assert item["legacy_equipment_pricing_basis_accepted"] is True
    history = refresh.sage_refresh_status()
    assert history["local_active"]["usable_rows"] == 6
    assert len(history["history"]) == 1
    items = refresh.sage_refresh_changes(
        snapshot_id=result["snapshot_id"], kind="added", limit=5, offset=1,
    )
    assert items["total"] == 6
    assert len(items["items"]) == 5
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT count(*) FROM smartquote_sage_snapshots"
        ).fetchone()[0] == 1


def test_second_refresh_records_price_added_removed_and_description_changes(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("list-1.csv", csv_bytes(dataset()), date())
    previous = refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"], reason="Initial sample Sage full export"
    ))
    next_rows = dataset()
    next_rows[0] = ("FIC-0000", "200.00")
    next_rows[1] = ("FIC-0001", 101, "Updated fictional label")
    next_rows.pop()
    next_rows.append(("FIC-NEW", 777))
    updated = refresh.preview_import("list-2.csv", csv_bytes(next_rows), date())
    counts = updated["change_counts"]
    assert counts["price_changed"] == 1
    assert counts["details_changed"] == 1
    assert counts["added"] == 1
    assert counts["removed"] == 1
    assert counts["unchanged"] == 3
    activated = refresh.activate_preview(refresh.SageApply(
        preview_token=updated["preview_token"], reason="Full revision after scheduled Sage export"
    ))
    assert activated["snapshot_id"] != previous["snapshot_id"]
    original = reference.snapshot()
    assert original["prices"]["FIC-0000"]["sales_price"] == 200
    assert "FIC-0005" not in original["prices"]
    assert "FIC-NEW" in original["prices"]
    history = refresh.sage_refresh_status()["history"]
    assert sum(record["active"] for record in history) == 1
    assert len(history) == 2
    differences = refresh.sage_refresh_changes(
        snapshot_id=activated["snapshot_id"], kind="price_changed",
        limit=50, offset=0,
    )
    assert differences["total"] == 1
    assert differences["items"][0]["previous_price"] == 100
    assert differences["items"][0]["current_price"] == 200
    details = refresh.sage_refresh_changes(
        snapshot_id=activated["snapshot_id"], kind="details_changed",
        limit=50, offset=0,
    )
    assert details["total"] == 1
    assert details["items"][0]["previous_name"] == "Fictional gym equipment"
    assert details["items"][0]["current_name"] == "Updated fictional label"
    assert details["items"][0]["previous_group"] == "Cardiovascular Equipment"
    with pytest.raises(HTTPException) as exc:
        refresh.activate_preview(refresh.SageApply(
            preview_token=updated["preview_token"],
            reason="Do not repeat this already applied preview"
        ))
    assert exc.value.status_code == 404


def test_concurrent_sage_import_previews_cannot_overwrite_newer_active_snapshot(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("first.csv", csv_bytes(dataset()), date())
    second = refresh.preview_import("second.csv", csv_bytes(dataset(base=300)), date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"], reason="First approved snapshot import"
    ))
    with pytest.raises(HTTPException) as exc:
        refresh.activate_preview(refresh.SageApply(
            preview_token=second["preview_token"], reason="Attempt stale snapshot activation"
        ))
    assert exc.value.status_code == 409
    assert reference.snapshot()["prices"]["FIC-0000"]["sales_price"] == 100


def test_large_sage_removal_requires_explicit_checkbox(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("full.csv", csv_bytes(dataset(30)), date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"], reason="Full first staging snapshot"
    ))
    reduced = refresh.preview_import("short.csv", csv_bytes(dataset(6)), date())
    assert reduced["large_removal_warning"] is True
    assert reduced["change_counts"]["removed"] == 24
    with pytest.raises(HTTPException) as exc:
        refresh.activate_preview(refresh.SageApply(
            preview_token=reduced["preview_token"],
            reason="Removal without critical list check"
        ))
    assert exc.value.status_code == 409
    assert len(reference.snapshot()["prices"]) == 30
    result = refresh.activate_preview(refresh.SageApply(
        preview_token=reduced["preview_token"],
        reason="Verified full source explicitly removing retired codes",
        confirm_large_removal=True,
    ))
    assert result["activated"] is True
    assert len(reference.snapshot()["prices"]) == 6


def test_sage_conflicts_and_non_equipment_rows_cannot_be_silently_installed(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    records = dataset()
    records += [("FIC-0001", 12345)]
    parsed = refresh.parse_export("sage.csv", csv_bytes(records))
    assert parsed["conflicting_item_codes"] == 1
    assert "FIC-0001" not in parsed["prices"]
    with pytest.raises(HTTPException) as error:
        refresh.preview_import("sage.csv", csv_bytes(records), date())
    assert error.value.status_code == 422

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Code", "Name", "Product Group Description", "Sales Price"])
    for row in dataset():
        writer.writerow([row[0], "Fictional equipment", "Cardiovascular Equipment", row[1]])
    writer.writerow(["PART-1", "Fictional repair kit", "Spare Parts", "20000"])
    parsed = refresh.parse_export("sage.csv", output.getvalue().encode())
    assert parsed["excluded_group_rows"] == 0
    assert parsed["non_equipment_reference_rows"] == 1
    assert parsed["usable_rows"] == 7
    assert parsed["prices"]["PART-1"]["sales_price"] == 20000
    # An inventory code in Sage is not automatically a maintainable machine.


def test_invalid_sage_formats_prices_and_dates_fail_closed(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        refresh.parse_export("sage.pdf", csv_bytes(dataset()))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        refresh.parse_export("sage.csv", csv_bytes([("FIC-0001", "NaN")]*6))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        refresh.preview_import("sage.csv", csv_bytes(dataset()), "2099-01-01")
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        refresh.parse_export("sage.csv", b"SKU,Price\nFICTIONAL,100\n")
    assert exc.value.status_code == 422


def test_admin_authorisation_guards_reads_writes_and_file_upload(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    monkeypatch.setattr(refresh.pilot_access, "current_role", lambda: "Coordinator")
    with pytest.raises(HTTPException) as exc:
        refresh.preview_import("sage.csv", csv_bytes(dataset()), date())
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        refresh.sage_refresh_status()
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        refresh.activate_preview(refresh.SageApply(
            preview_token="a"*32, reason="Unauthorised Sage list import"
        ))
    assert exc.value.status_code == 403


def test_xlsx_first_worksheet_can_import_exact_original_four_columns():
    rows = [
        ["Code", "Name", "Product Group Description", "Sales Price"],
    ] + [[code, "Fictional bike", "Cardiovascular Equipment", str(price)]
         for code, price in dataset()]
    root = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
    )
    for rownum, values in enumerate(rows, 1):
        root += f'<row r="{rownum}">'
        for col, value in zip("ABCD", values):
            root += (f'<c r="{col}{rownum}" t="inlineStr">'
                     f'<is><t>{value}</t></is></c>')
        root += '</row>'
    root += '</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types/>')
        archive.writestr("xl/worksheets/sheet1.xml", root)
    result = refresh.parse_export("full_sage.xlsx", buffer.getvalue())
    assert result["usable_rows"] == 6
    assert result["prices"]["FIC-0003"]["sales_price"] == 103.0


def test_local_active_corrupt_snapshot_fails_closed_not_original_fallback(tmp_path, monkeypatch):
    dbpath = activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("sage.csv", csv_bytes(dataset()), date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"], reason="Full source with fictional prices"
    ))
    with sqlite3.connect(dbpath) as con:
        con.execute(
            "UPDATE smartquote_sage_snapshots SET payload=? WHERE active=1",
            (b"bad gzip body",)
        )
    with pytest.raises(HTTPException) as error:
        reference.snapshot()
    assert error.value.status_code == 503


def test_sage_refresh_invalidates_previously_audited_local_price_revision(tmp_path, monkeypatch):
    from app import quote_price_overrides as edits
    activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("sage-first.csv", csv_bytes(dataset()), date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"],
        reason="Full initial Sage pricing evidence export"
    ))
    old_source = reference.snapshot()
    monkeypatch.setattr(edits, "connect", refresh.connect)
    monkeypatch.setattr(edits.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(edits.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(edits.pilot_access, "actor", lambda name="": "fictional-admin")
    monkeypatch.setattr(edits, "source_for_code", lambda sku: (
        {"basis": "sage_exact_sku_price", "rrp": 100.0},
        old_source["source_file_sha256"],
    ))
    changed = edits.update_price("FIC-0000", edits.PriceChange(
        price_gbp="149.99", expected_revision=0,
        reason="Authorised price correction following review",
    ))
    assert changed["revision"] == 1
    assert edits.active_overrides(["FIC-0000"])["FIC-0000"]["price_pence"] == 14999
    next_export = csv_bytes(dataset(base=180))
    latest = refresh.preview_import("sage-updated.csv", next_export, date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=latest["preview_token"],
        reason="New comprehensive Sage Sales Price export"
    ))
    new_source = reference.snapshot()
    assert new_source["source_file_sha256"] != old_source["source_file_sha256"]
    active = edits.active_overrides(["FIC-0000"])["FIC-0000"]
    result = edits.effective(
        {"basis": "sage_exact_sku_price", "rrp": 180.0},
        active, {}, new_source,
    )
    assert result["rrp"] is None
    assert result["basis"] == "stale_price_override"
    assert result["override_status"] == "source_changed_review_required"


def test_older_sage_price_list_cannot_replace_more_recent_source(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    first = refresh.preview_import("sage-current.csv", csv_bytes(dataset()), date())
    refresh.activate_preview(refresh.SageApply(
        preview_token=first["preview_token"],
        reason="Latest working source under verification"
    ))
    with pytest.raises(HTTPException) as exc:
        refresh.preview_import(
            "sage-old.csv", csv_bytes(dataset(base=200)),
            (dt.date.today() - dt.timedelta(days=3)).isoformat(),
        )
    assert exc.value.status_code == 409


def test_sage_refresh_requires_full_valid_export_and_hash_integrity(tmp_path, monkeypatch):
    activate_local_db(tmp_path, monkeypatch)
    rows = csv_bytes(dataset())
    preview = refresh.preview_import("valid.csv", rows, date())
    assert preview["file_sha256"] == hashlib.sha256(rows).hexdigest()
    assert len(preview["preview_token"]) >= 20
    with pytest.raises(HTTPException) as err:
        refresh.activate_preview(refresh.SageApply(
            preview_token=preview["preview_token"],
            reason="too short",
        ))
    assert err.value.status_code == 422
    assert reference.snapshot() is None


def test_full_sage_export_preserves_original_special_codes_manufacturer_and_zero_prices():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "Code", "Name", "Product Group Description",
        "Sales Price", "Manufacturer",
    ])
    writer.writerow([
        "JTDR-05-20 BLK", "Fictional weight rack",
        "Free Weight Benches & Racks", "320.643", "Example Manufacturer",
    ])
    writer.writerow([
        "P16-A5000-B#1", "Fictional spare code",
        "CV Parts", "0", "Parts Supplier",
    ])
    writer.writerow([
        "SCKIOSK&COMPUTER2", "Fictional console",
        "PulseMove Parts", "445.50", "Example",
    ])
    writer.writerow([
        "FS800-100(209)", "Fictional exercise equipment",
        "Functional Equipment", "1499", "Example",
    ])
    writer.writerow([
        "JTDR-08-10N GRY", "Fictional weight rack",
        "Free Weights", "199.99", "Example",
    ])
    parsed = refresh.parse_export("sage-full.csv", out.getvalue().encode())
    assert parsed["usable_rows"] == 5
    assert parsed["positive_price_rows"] == 4
    assert parsed["zero_price_rows"] == 1
    assert parsed["invalid_equipment_rows"] == 0
    assert parsed["non_equipment_reference_rows"] == 2
    assert parsed["prices"]["JTDR-05-20 BLK"]["sales_price"] == 320.64
    assert parsed["prices"]["JTDR-05-20 BLK"]["manufacturer"] == "Example Manufacturer"
    assert parsed["prices"]["P16-A5000-B#1"]["sales_price"] == 0
    assert "SCKIOSK&COMPUTER2" in parsed["prices"]


def test_real_export_style_xlsx_fifth_manufacturer_column_is_retained():
    rows = [
        ["Code", "Name", "Product Group Description", "Sales Price", "Manufacturer"],
    ] + [[code, "Fictional product", "Free Weights", str(price), "Test Supplier"]
         for code, price in dataset()]
    root = ('<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>')
    for position, values in enumerate(rows, 1):
        root += f'<row r="{position}">'
        for col, value in zip("ABCDE", values):
            root += (f'<c r="{col}{position}" t="inlineStr"><is>'
                     f'<t>{value}</t></is></c>')
        root += '</row>'
    root += '</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/worksheets/sheet1.xml", root)
    result = refresh.parse_export("full-sage.xlsx", buffer.getvalue())
    assert result["usable_rows"] == 6
    assert result["equipment_rows"] == 6
    assert result["prices"]["FIC-0002"]["manufacturer"] == "Test Supplier"
