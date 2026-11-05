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
    fixture[0][-1]["name"] = "=HYPERLINK(\\\"https://bad.invalid\\\",\\\"OPEN\\\")"
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
