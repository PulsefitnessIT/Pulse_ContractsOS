"""Synthetic source-only tests for the single Pulse item-price master."""
import csv
import hashlib
import io
import sqlite3

import pytest
from fastapi import HTTPException

from app import quote_price_book as book


@pytest.fixture
def administrator(tmp_path, monkeypatch):
    path = tmp_path / "unified_demo.sqlite3"
    def connect():
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        return con
    monkeypatch.setattr(book, "connect", connect)
    monkeypatch.setattr(book.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(book.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(book.pilot_access, "actor", lambda default="": "fictional-pricing-manager")
    return path


def _data(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("SKU", "Price GBP", "Description", "Product Group",
                     "Price Source", "Price Status"))
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def test_first_merge_uses_one_price_per_code_and_imports_parts(administrator):
    initial = _data([
        ("MACHINE-A", "2100.00", "Example current treadmill", "Cardiovascular Equipment",
         "Master 24-08-2026", "PRICE REFERENCE"),
        ("PART-B", "145.50", "Example replacement drive belt", "CV Parts",
         "Sage imported reference", "PRICE REFERENCE"),
        ("ZERO-C", "0.00", "Unpriced console part", "Console Parts",
         "Sage imported reference", "UNPRICED"),
        ("CONFLICT-D", "", "Master-conflicted model", "Strength Equipment",
         "Master - conflict", "HOLD - Master conflicting prices"),
    ])
    preview = book.preview_import("Pulse_Fitness_Unified_Master.csv", initial)
    assert preview["current_revision"] == 0
    assert preview["changes"]["new_codes"] == 4
    assert preview["changes"]["held_codes"] == 1
    assert preview["changes"]["zero_price_codes"] == 1
    with pytest.raises(HTTPException) as rejected:
        book.activate_import(book.ActivatePriceImport(
            preview_token=preview["preview_token"],
            reason="First signed-off source-book import",
        ))
    assert rejected.value.status_code == 409
    activated = book.activate_import(book.ActivatePriceImport(
        preview_token=preview["preview_token"],
        reason="First signed-off source-book import",
        confirm_zero_and_held_prices=True,
    ))
    assert activated["revision"] == 1
    snapshot = book.active_book()
    assert snapshot["rows"]["MACHINE-A"]["price_pence"] == 210000
    assert snapshot["rows"]["PART-B"]["price_pence"] == 14550
    assert snapshot["rows"]["ZERO-C"]["price_pence"] == 0
    assert snapshot["rows"]["CONFLICT-D"]["price_pence"] is None
    assert len(snapshot["rows"]) == 4
    assert activated["maintenance_tariffs_not_approved"] is True


def test_next_price_import_overwrites_matching_codes_without_deleting_others(administrator):
    first = book.preview_import("initial.csv", _data([
        ("MACHINE-A", "3200.00", "Example machine", "Strength Equipment",
         "Master", "REFERENCE"),
        ("PART-B", "20.00", "Example spare", "Spare Parts",
         "Sage", "REFERENCE"),
    ]))
    book.activate_import(book.ActivatePriceImport(
        preview_token=first["preview_token"],
        reason="Establish first merged exact SKU catalogue",
    ))
    prior = book.active_book()
    imported = book.preview_import("2027_new_prices.csv", _data([
        ("MACHINE-A", "3555.55", "Example machine", "Strength Equipment",
         "New supplier 2027", "REFERENCE"),
        ("NEW-C", "999.00", "Example newly priced machine", "Cardiovascular Equipment",
         "New supplier 2027", "REFERENCE"),
    ]))
    assert imported["changes"]["updated_codes"] == 1
    assert imported["changes"]["new_codes"] == 1
    assert imported["changes"]["retained_existing_codes"] == 1
    updated = book.activate_import(book.ActivatePriceImport(
        preview_token=imported["preview_token"],
        reason="Confirm revised 2027 equipment price schedule",
    ))
    current = book.active_book()
    assert current["revision"] == 2
    assert current["sha256"] != prior["sha256"]
    assert current["rows"]["MACHINE-A"]["price_pence"] == 355555
    assert current["rows"]["MACHINE-A"]["origin"] == "New supplier 2027"
    assert current["rows"]["PART-B"]["price_pence"] == 2000
    assert current["rows"]["NEW-C"]["price_pence"] == 99900
    assert updated["changes"]["deletes_unmentioned_codes"] is False
    # Snapshot v1 is retained for forensic audit/old issued quote evidence.
    with sqlite3.connect(administrator) as con:
        assert con.execute("SELECT COUNT(*) FROM unified_price_book_versions").fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM unified_price_book_versions WHERE active=1"
        ).fetchone()[0] == 1


def test_import_with_duplicate_skus_is_rejected_before_any_activation(administrator):
    data = _data([
        ("MODEL-A", "1250", "Equipment", "Strength Equipment", "Master", "REFERENCE"),
        ("model-a", "1500", "Equipment", "Strength Equipment", "Sage", "REFERENCE"),
    ])
    with pytest.raises(HTTPException) as error:
        book.preview_import("duplicates.csv", data)
    assert error.value.status_code == 422
    assert book.active_book() is None


def test_price_book_rejects_malformed_amount_and_csv_formula(administrator):
    for value in ("-10", "NaN", "Infinity", "=1+3", "12.345"):
        with pytest.raises(HTTPException):
            book.preview_import("bad.csv", _data([
                ("BAD-A", value, "Example", "Strength Equipment", "Master", "REFERENCE")
            ]))


def test_stale_preview_cannot_clobber_newer_import(administrator):
    original = book.preview_import("initial.csv", _data([
        ("SKU-A", "500", "Example machine", "Strength Equipment", "Master", "REFERENCE")
    ]))
    staged = book.preview_import("also_original.csv", _data([
        ("SKU-A", "700", "Example machine", "Strength Equipment", "Master", "REFERENCE")
    ]))
    book.activate_import(book.ActivatePriceImport(
        preview_token=original["preview_token"],
        reason="Activate reviewed initial source schedule",
    ))
    with pytest.raises(HTTPException) as error:
        book.activate_import(book.ActivatePriceImport(
            preview_token=staged["preview_token"],
            reason="This stale preview must not overwrite the first activation",
        ))
    assert error.value.status_code == 409
    assert book.active_book()["rows"]["SKU-A"]["price_pence"] == 50000


def test_admin_only_export_preserves_source_records_without_quoting_permissions(administrator, monkeypatch):
    stage = book.preview_import("initial.csv", _data([
        ("MACHINE-A", "500", "Example machine", "Strength Equipment", "Master", "REFERENCE"),
        ("PART-B", "45", "=HYPERLINK(1,1)", "Parts", "Sage", "REFERENCE"),
    ]))
    book.activate_import(book.ActivatePriceImport(
        preview_token=stage["preview_token"], reason="Approved internal source reference"
    ))
    response = book.price_book_export()
    items = list(csv.DictReader(io.StringIO(response.body.decode("utf-8-sig"))))
    assert len(items) == 2
    assert items[1]["Description"].startswith("'=HYPERLINK")
    assert response.headers["cache-control"] == "private, no-store"
    monkeypatch.setattr(book.pilot_access, "current_role", lambda: "Coordinator")
    with pytest.raises(HTTPException) as error:
        book.price_book_export()
    assert error.value.status_code == 403


def test_import_pins_source_sha_and_rejects_corrupted_active_snapshot(administrator):
    contents = _data([
        ("SKU-A", "500", "Example", "Strength Equipment", "Master", "REFERENCE")
    ])
    staged = book.preview_import("baseline.csv", contents)
    book.activate_import(book.ActivatePriceImport(
        preview_token=staged["preview_token"], reason="Activate verified baseline snapshot"
    ))
    assert book.active_book()["source_file_sha256"] == hashlib.sha256(contents).hexdigest()
    with sqlite3.connect(administrator) as con:
        con.execute(
            "UPDATE unified_price_book_versions SET snapshot_sha256=? WHERE active=1",
            ("9" * 64,),
        )
    with pytest.raises(HTTPException) as error:
        book.active_book()
    assert error.value.status_code == 503


def test_price_only_import_keeps_existing_equipment_identity(administrator):
    base = book.preview_import("first.csv", _data([
        ("MACHINE-A", "1450", "Model with known console", "Strength Equipment",
         "August master", "REFERENCE")
    ]))
    book.activate_import(book.ActivatePriceImport(
        preview_token=base["preview_token"],
        reason="Approved first reference list",
    ))
    change = ("SKU,Price GBP\nMACHINE-A,1900.00\n").encode("utf-8")
    staged = book.preview_import("newprices.csv", change)
    assert staged["changes"]["updated_codes"] == 1
    book.activate_import(book.ActivatePriceImport(
        preview_token=staged["preview_token"],
        reason="Approved replacement equipment price",
    ))
    updated = book.active_book()["rows"]["MACHINE-A"]
    assert updated["price_pence"] == 190000
    assert updated["description"] == "Model with known console"
    assert updated["group"] == "Strength Equipment"
    assert updated["origin"] == "Price import"
