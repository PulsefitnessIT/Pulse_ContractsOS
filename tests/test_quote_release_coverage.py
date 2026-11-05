"""Synthetic-only candidate coverage tests; no live customer or tariff data."""
import pytest
from fastapi import HTTPException
from app import quote_release_coverage as released


def _fixture():
    catalogue = [
        {"sku":"FIC-TREAD","name":"Example 10.1 Cardio Treadmill",
         "model":"FIC","service_key":"FIC | Console 5 (Series 2)",
         "console":"Console 5 (Series 2)","rrp":1,
         "match":"Exact SKU"},
        {"sku":"FIC-UNCERTAIN","name":"Unverified 10.1 Strength Console",
         "model":"FIC","service_key":"FIC | Strength Console",
         "console":"Strength Console","rrp":1,
         "match":"Exact SKU"},
        {"sku":"FIC-SAGE","name":"Legacy example machine",
         "model":"OLD","service_key":"OLD | No Console / N/A",
         "console":"No Console / N/A","rrp":1,
         "match":"Exact SKU"},
        {"sku":"FIC-DUP","name":"Duplicate variant A",
         "model":"FIC","service_key":"FIC | Console 5 (Series 2)",
         "console":"Console 5 (Series 2)","rrp":1},
        {"sku":"FIC-DUP","name":"Duplicate variant B",
         "model":"FIC","service_key":"FIC | Console 5 (Series 2)",
         "console":"Console 5 (Series 2)","rrp":1},
    ]
    configs=[
        {"key":"FIC | Console 5 (Series 2)","rate_group":"Standard Equipment","eligible":"Yes"},
        {"key":"FIC | Strength Console","rate_group":"Standard Equipment","eligible":"Yes"},
        {"key":"OLD | No Console / N/A","rate_group":"Standard Equipment","eligible":"Yes"},
    ]
    pricing={"currency":"GBP",
        "tiers":{"Gold":1.0},
        "rates":[{"group":"Standard Equipment","standard":0.03,
                  "minimum":0.025,"uplift":0.0,"status":"Active"}],
        "console_rules":[
            {"name":"Console 5 (Series 2)","multiplier":1,"uplift":0},
            {"name":"Strength Console","multiplier":1,"uplift":0},
            {"name":"No Console / N/A","multiplier":1,"uplift":0},
        ],
    }
    def row(sku,name,console,amount):
        return {"sku":sku,"name":name,"console":console,"rrp":str(amount),
                "row":12,"sheet":"Synthetic","rrp_column":"BA"}
    master={
        "source_file_sha256":"b"*64,
        "rows":[
            row("FIC-TREAD",catalogue[0]["name"],"10.1-inch cardio tactile-key",4000),
            row("FIC-UNCERTAIN",catalogue[1]["name"],"10.1-inch strength touchscreen (verify)",3000),
        ]
    }
    sage={
        "prices":{"FIC-SAGE":{"sku":"FIC-SAGE","name":"Legacy example machine",
                              "sales_price":2100,"group":"Cardiovascular Equipment"}},
        "source_file_sha256":"a"*64,
        "source_date":"2026-11-01","review_due":"2027-11-01",
        "review_overdue":False,
        "source":"Synthetic Sage source",
    }
    return catalogue,configs,pricing,master,sage


def test_source_coverage_counts_realistic_cardio_matches_and_sage_without_prices():
    result=released.coverage(*_fixture())
    assert result["v10_catalogue_rows"]==5
    assert result["distinct_v10_skus"]==4
    assert result["candidate_current_master_skus"]==1
    assert result["candidate_sage_fallback_skus"]==1
    assert result["candidate_total"]==2
    assert result["review_categories"]["master_description_or_console_requires_review"]==1
    assert result["review_categories"]["duplicate_v10_sku"]==1
    assert result["no_source_pricing_returned"] is True
    assert "4000" not in str(result)
    assert "FIC-TREAD" not in str(result)


def test_coverage_does_not_promote_sage_without_source_or_when_review_overdue():
    args=list(_fixture())
    args[4]["review_overdue"]=True
    overdue=released.coverage(*args)
    assert overdue["candidate_sage_fallback_skus"]==0
    assert overdue["review_categories"]["sage_price_review_overdue"]==1
    absent=released.coverage(*args[:4])
    assert absent["candidate_sage_fallback_skus"]==0
    assert absent["review_categories"]["unresolved_master_or_sage_price"]==1


def test_coverage_never_exposes_mismatched_title_as_quotable():
    args=list(_fixture())
    args[3]["rows"][0]["name"]="Different machine name"
    result=released.coverage(*args)
    assert result["candidate_current_master_skus"]==0
    assert result["review_categories"]["master_description_or_console_requires_review"]==2


def test_coverage_endpoint_requires_named_protected_pilot_roles(monkeypatch):
    monkeypatch.setattr(released.pilot_access,"PILOT_MODE",False)
    with pytest.raises(HTTPException) as err:
        released.candidate_coverage()
    assert err.value.status_code==403
    monkeypatch.setattr(released.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(released.pilot_access,"current_role",lambda:"Viewer")
    with pytest.raises(HTTPException) as err:
        released.candidate_coverage()
    assert err.value.status_code==403


def test_candidate_review_rows_reconcile_to_aggregate_counts():
    result = released.coverage(*_fixture())
    rows = list(released.candidate_assessments(*_fixture()))
    assert len(rows) == result["distinct_v10_skus"]
    assert sum(not row["potentially_quotable"] for row in rows) == sum(
        result["review_categories"].values()
    )
    assert [row["sku"] for row in rows] == sorted(row["sku"] for row in rows)
    assert {row["category"] for row in rows if not row["potentially_quotable"]} == {
        "duplicate_v10_sku", "master_description_or_console_requires_review",
    }
    assert all("rrp" not in row and "sales_price" not in row for row in rows)


def test_candidate_review_csv_requires_named_admin(monkeypatch):
    monkeypatch.setattr(released.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Coordinator")
    with pytest.raises(HTTPException) as err:
        released.candidate_review_csv()
    assert err.value.status_code == 403
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(released.pilot_access, "actor", lambda default="": "")
    with pytest.raises(HTTPException) as err:
        released.candidate_review_csv()
    assert err.value.status_code == 403


def test_admin_review_export_contains_review_reasons_not_commercial_amounts(monkeypatch):
    import csv
    import io

    fixture = list(_fixture())
    fixture[0][-2]["name"] = "=HYPERLINK(\\\"https://bad.invalid\\\",\\\"OPEN\\\")"
    monkeypatch.setattr(released.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(released.pilot_access, "actor", lambda default="": "pilot-admin")
    monkeypatch.setattr(released, "source_snapshot", lambda: (*fixture[:3], {}))
    monkeypatch.setattr(released, "august_snapshot", lambda: fixture[3])
    monkeypatch.setattr(released, "sage_snapshot", lambda: fixture[4])

    response = released.candidate_review_csv()
    report = response.body.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(report)))
    assert len(rows) == 2
    assert {row["SKU"] for row in rows} == {"FIC-DUP", "FIC-UNCERTAIN"}
    assert {row["Review category"] for row in rows} == {
        "duplicate_v10_sku", "master_description_or_console_requires_review",
    }
    assert rows[0]["Equipment"].startswith("'=HYPERLINK")
    assert all(row["Recommended next action"] for row in rows)
    assert "4000" not in report and "2100" not in report
    assert "FIC-SAGE" not in report and "FIC-TREAD" not in report
    assert response.headers["cache-control"] == "private, no-store"


def test_full_reconciliation_preserves_master_precedence_and_sage_difference():
    args = list(_fixture())
    args[4]["prices"]["FIC-TREAD"] = {
        "sku": "FIC-TREAD", "name": "Same item in Sage",
        "sales_price": 3550.00, "group": "Cardiovascular Equipment"
    }
    rows = {
        row["SKU"]: row for row in released._reconciliation_rows(*args)
    }
    assert len(rows) == 4
    current = rows["FIC-TREAD"]
    assert current["Master list price GBP"] == "4000.00"
    assert current["Sage Sales Price GBP"] == "3550.0"
    assert current["Sage less Master GBP"] == "-450.00"
    assert current["Selected equipment price GBP"] == "4000.00"
    assert current["Selected equipment price basis"] == "august_2026_master_list_price"
    assert current["Quote status"] == "source_price_candidate_august_master"
    # The Sage amount is informational: different bases do not cancel an
    # otherwise uniquely identified current Master machine price.
    legacy = rows["FIC-SAGE"]
    assert legacy["Selected equipment price basis"] == "sage_exact_sku_price"
    assert legacy["Selected equipment price GBP"] == "2100.00"


def test_full_reconciliation_keeps_noncatalogue_inventory_and_zero_prices_separate():
    args = list(_fixture())
    args[3]["rows"].append({
        "sku": "MASTER-ONLY", "name": "Fictional current-model SKU",
        "console": "Console not stated", "rrp": "7000.00",
        "sheet": "Synthetic", "row": 75,
    })
    args[4]["prices"]["SAGE-ONLY"] = {
        "sku": "SAGE-ONLY", "name": "Sage-only machine",
        "sales_price": 600.0, "group": "Strength Equipment"
    }
    args[4]["prices"]["SAGE-ZERO"] = {
        "sku": "SAGE-ZERO", "name": "Unpriced inventory",
        "sales_price": 0.0, "group": "Spare Parts"
    }
    rows = {
        row["SKU"]: row for row in released._reconciliation_rows(*args)
    }
    assert len(rows) == 7
    assert rows["MASTER-ONLY"]["Quote status"] == "master_only_not_in_v10_catalogue"
    assert rows["SAGE-ONLY"]["Quote status"] == (
        "sage_only_inventory_not_v10_maintenance_equipment"
    )
    assert rows["SAGE-ZERO"]["Quote status"] == "sage_zero_or_invalid_price"
    assert rows["SAGE-ZERO"]["Selected equipment price GBP"] == ""
    assert rows["SAGE-ONLY"]["Selected equipment price basis"] == "sage_exact_sku_price"
    assert "maintenance" in rows["SAGE-ONLY"]["Manager next action"].lower()


def test_full_reconciliation_blocks_conflicting_master_price_even_with_sage():
    args = list(_fixture())
    args[3]["rows"].append({
        "sku": "FIC-TREAD", "name": args[0][0]["name"],
        "console": "10.1-inch cardio tactile-key",
        "rrp": "4001.00", "sheet": "Synthetic", "row": 76
    })
    args[4]["prices"]["FIC-TREAD"] = {
        "sku": "FIC-TREAD", "name": "Treadmill",
        "sales_price": 3900.0, "group": "Cardiovascular Equipment"
    }
    row = {
        result["SKU"]: result
        for result in released._reconciliation_rows(*args)
    }["FIC-TREAD"]
    assert row["Master source rows"] == 2
    assert "4000.00" in row["Master list price GBP"]
    assert "4001.00" in row["Master list price GBP"]
    assert row["Selected equipment price GBP"] == ""
    assert row["Selected equipment price basis"] == "master_price_conflict"


def test_full_reconciliation_csv_does_not_leak_prices_without_named_admin(monkeypatch):
    args = list(_fixture())
    monkeypatch.setattr(released, "_reconciliation_data", lambda: (
        *args[:3], {"pricing": "f" * 64}, args[3], args[4]
    ))
    monkeypatch.setattr(released.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Coordinator")
    with pytest.raises(HTTPException) as error:
        released.source_reconciliation_csv()
    assert error.value.status_code == 403
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(released.pilot_access, "actor", lambda default="": "pilot-admin")
    response = released.source_reconciliation_csv()
    import csv
    import io
    output = response.body.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(output)))
    assert len(rows) == 4
    assert {row["SKU"] for row in rows} == {
        "FIC-TREAD", "FIC-UNCERTAIN", "FIC-DUP", "FIC-SAGE"
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert rows[0]["Manager next action"]
    assert all("customer" not in heading.lower() for heading in rows[0])


def test_full_reconciliation_requires_sage_source_for_download(monkeypatch):
    args = list(_fixture())
    monkeypatch.setattr(released, "_reconciliation_data", lambda: (
        *args[:3], {"pricing": "f" * 64}, args[3], None
    ))
    monkeypatch.setattr(released.pilot_access, "PILOT_MODE", True)
    monkeypatch.setattr(released.pilot_access, "current_role", lambda: "Admin")
    monkeypatch.setattr(released.pilot_access, "actor", lambda default="": "pilot-admin")
    with pytest.raises(HTTPException) as error:
        released.source_reconciliation_csv()
    assert error.value.status_code == 409
    summary = released.source_reconciliation_summary()
    assert summary["full_three_source_comparison_available"] is False
    assert summary["sources"]["sage_item_codes"] is None
    assert summary["commercial_tariffs_approved_by_this_report"] is False
