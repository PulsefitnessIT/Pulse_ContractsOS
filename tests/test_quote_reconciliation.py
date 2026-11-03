"""Canonical SmartQuote identity and provenance checks with fictional machines."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import quote_reconciliation


def synthetic_sources():
    products=[
        {"sku":"EXAMPLE-001","name":"Fictional Bike","model":"EX-1",
         "console":"No Console / N/A","rrp":2000,
         "match":"Mapped","service_key":"EX-1 | No Console"},
        {"sku":"EXAMPLE-002","name":"Fictional no RRP","model":"EX-2",
         "console":"No Console / N/A","rrp":None,
         "match":"Mapped","service_key":"EX-1 | No Console"},
        {"sku":"EXAMPLE-TEXT","name":"Text RRP","model":"EX-3",
         "console":"Unknown","rrp":"5000","service_key":"EX-1 | No Console"},
        {"sku":"EXAMPLE-DUP","name":"First variant","rrp":1000,
         "service_key":"EX-1 | No Console"},
        {"sku":"EXAMPLE-DUP","name":"Second variant","rrp":1200,
         "service_key":"EX-1 | No Console"},
        {"sku":"EXAMPLE-STAIR","name":"Step mill","model":"ST",
         "rrp":5000,"console":"No Console / N/A",
         "service_key":"ST | No Console"},
    ]
    configs=[
        {"key":"EX-1 | No Console", "rate_group":"Standard Equipment",
         "eligible":"Yes"},
        {"key":"ST | No Console", "rate_group":"Stepmill",
         "eligible":"Review"},
    ]
    pricing={
        "source_snapshot":"2026-10-15",
        "pricing_status":"Provisional; not approved",
        "rates":[
            {"group":"Standard Equipment","standard":.03,
             "minimum":.025,"status":"Active"},
            {"group":"Stepmill","standard":.038,"minimum":.038,
             "status":"Review"},
        ],
        "console_rules":[{"name":"No Console / N/A","multiplier":1,"uplift":0}],
        "tiers":{"Silver":.8,"Gold":1,"Platinum":1.3},
    }
    legacy=[
        {"old_code":"LEGACY-EX","old_sku":"LEGACY-EX",
         "new_sku":"EXAMPLE-001"},
        {"old_code":"LEGACY-MULTI","old_sku":"",
         "new_sku":"EXAMPLE-001"},
        {"old_code":"LEGACY-MULTI","old_sku":"",
         "new_sku":"EXAMPLE-002"},
        {"old_code":"LEGACY-MISSING","old_sku":"",
         "new_sku":"NOT-IN-SOURCE"},
        {"old_code":"","old_sku":"6","new_sku":"EXAMPLE-001"},
    ]
    history={"records":{"OLD-EXAMPLE":{"model":"EX-1"}},"aliases":{}}
    return products,configs,pricing,legacy,history


def build():
    p,c,r,l,h=synthetic_sources()
    return quote_reconciliation.reconcile(
        p,c,r,{"catalog":"a"*64,"configs":"b"*64,"pricing":"c"*64},
        legacy=l,legacy_sha="d"*64,history=h,history_sha="e"*64
    )


def test_counts_are_source_factual_and_do_not_claim_approval():
    result=build()
    summary=result["summary"]
    assert summary["catalogue_source_rows"]==6
    assert summary["distinct_skus"]==5
    assert summary["unique_skus"]==4
    assert summary["duplicate_sku_groups"]==1
    assert summary["excess_duplicate_rows"]==1
    assert summary["flag_counts"]["missing_or_invalid_current_rrp"]==2
    assert summary["flag_counts"]["source_rate_requires_review"]==1
    assert summary["historical_source_variants"]==1
    assert summary["legacy_source_rows"]==5
    assert summary["legacy_codes_mapped"]==2
    assert summary["ambiguous_legacy_codes"]==1
    assert summary["legacy_missing_target_mappings"]==1
    assert result["commercially_approved"] is False
    assert result["customer_quote_issue_enabled"] is False


def test_matching_does_not_auto_promote_duplicate_or_legacy_records():
    result=build()
    assert len(result["sku_rows"]["EXAMPLE-DUP"])==2
    found=next(x for x in result["worklist"] if x["sku"]=="EXAMPLE-DUP")
    assert found["issues"].count("duplicate_sku")==1
    assert found["verified_master_rrp"] is False
    assert "LEGACY-MULTI" in result["legacy_ambiguous"]
    assert "LEGACY-EX" not in result["legacy_ambiguous"]


def test_missing_unstaged_history_is_not_misrepresented_as_empty_complete():
    p,c,r,_,_=synthetic_sources()
    result=quote_reconciliation.reconcile(
        p,c,r,{"catalog":"fictional"},legacy=None,history=None
    )
    assert result["summary"]["legacy_source_rows"] is None
    assert result["summary"]["historical_source_variants"] is None
    assert result["summary"]["historical_source_staged"] is False


def test_private_sources_are_hash_verified_not_written_to_repository(tmp_path,monkeypatch):
    _,_,_,legacy,history=synthetic_sources()
    p=tmp_path/"private_legacy.json"
    p.write_text(json.dumps(legacy),encoding="utf-8")
    h=tmp_path/"private_historical.json.gz"
    h.write_bytes(gzip.compress(json.dumps(history).encode("utf-8")))
    monkeypatch.setenv("PULSE_SMARTQUOTE_LEGACY_JSON",str(p))
    monkeypatch.setenv("PULSE_SMARTQUOTE_HISTORICAL_INDEX",str(h))
    raw,checksum=quote_reconciliation._private_optional_source("legacy_crosswalk")
    previous,older=quote_reconciliation._private_optional_source("historical_identity")
    assert raw==legacy and previous==history
    assert checksum==hashlib.sha256(p.read_bytes()).hexdigest()
    assert older==hashlib.sha256(h.read_bytes()).hexdigest()


def test_corrupt_optional_history_fails_closed(tmp_path,monkeypatch):
    p=tmp_path/"invalid.gz"
    p.write_bytes(b"not compressed")
    monkeypatch.setenv("PULSE_SMARTQUOTE_HISTORICAL_INDEX",str(p))
    with pytest.raises(HTTPException) as err:
        quote_reconciliation._private_optional_source("historical_identity")
    assert err.value.status_code==503


def test_legacy_lookup_never_returns_replacement_rrp(monkeypatch):
    monkeypatch.setattr(quote_reconciliation,"actor",lambda: "fictional-staff")
    monkeypatch.setattr(quote_reconciliation,"source_report",build)
    result=quote_reconciliation.resolve_legacy("legacy-multi")
    assert result["match_count"]==2
    assert result["ambiguous"] is True
    assert result["approved_price"] is None
    assert all("rrp" not in x for x in result["candidates"])
    clear=quote_reconciliation.resolve_legacy("legacy-ex")
    assert clear["match_count"]==1
    assert clear["ambiguous"] is False
    assert clear["requires_explicit_staff_match_confirmation"] is True


def test_reconciliation_worklist_is_read_only(monkeypatch):
    monkeypatch.setattr(quote_reconciliation,"actor",lambda: "fictional-staff")
    monkeypatch.setattr(quote_reconciliation,"source_report",build)
    results=quote_reconciliation.reconciliation_worklist(
        q="example",issue="duplicate_sku",limit=30,offset=0
    )
    assert results["total"]==1
    assert results["items"][0]["sku"]=="EXAMPLE-DUP"
    assert results["price_approved"] is False
    assert not any("rrp" in p for p in results["items"][0] if p != "verified_master_rrp")


def test_historical_identity_search_does_not_promote_old_rrp(monkeypatch):
    historical={
        "records":{
            "OLD-BIKE-A":{"sku":"OLD-BIKE-A","model":"200K",
                          "name":"Fictional older bike","console":"Console 5",
                          "year":2021,"rrp":9999},
            "OLD-BIKE-B":{"sku":"OLD-BIKE-B","model":"200K",
                          "name":"Fictional another variant","console":"Console 6",
                          "year":2023,"rrp":8888}
        },
        "aliases":{"R200K":["OLD-BIKE-A","OLD-BIKE-B"]}
    }
    monkeypatch.setattr(quote_reconciliation,"actor",lambda: "fictional-coordinator")
    monkeypatch.setattr(quote_reconciliation,"_private_optional_source",
        lambda kind:(historical,"c"*64))
    found=quote_reconciliation.historical_search("R200K",20)
    assert found["total"]==2
    assert found["ambiguous_or_multiple_variants"] is True
    assert found["cannot_auto_select_for_current_pricing"] is True
    assert {r["console"] for r in found["results"]}=={"Console 5","Console 6"}
    assert all(r["current_rrp"] is None for r in found["results"])
    assert all("rrp" not in r or r["current_rrp"] is None for r in found["results"])
    exact=quote_reconciliation.historical_search("OLD-BIKE-A",20)
    assert exact["total"]==1
    assert exact["results"][0]["historical_sku"]=="OLD-BIKE-A"
    assert exact["results"][0]["approved_replacement_sku"] is None


def test_catalogue_rows_without_skus_are_not_silently_ignored():
    products, configs, pricing, legacy, history = synthetic_sources()
    products.extend([
        {"sku": "", "name": "Unidentified fictional product", "rrp": 999},
        {"model": "NO-SKU", "rrp": 250},
        None,
    ])
    report = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"}
    )
    summary = report["summary"]
    assert summary["catalogue_source_rows"] == 9
    assert summary["catalogue_rows_with_sku"] == 6
    assert summary["catalogue_rows_missing_sku"] == 3
    assert summary["flag_counts"]["missing_sku"] == 3
    # SKU-group counts remain separate from missing-source-row counts.
    assert summary["source_skus_requiring_review"] == 4
    assert summary["source_skus_without_flagged_identity_issues"] == 1
    assert summary["catalogue_rows_requiring_review"] == 7
    missing = [x for x in report["worklist"] if "missing_sku" in x["issues"]]
    assert [x["catalogue_source_row"] for x in missing] == [7, 8, 9]
    assert all(x["price_approved"] is False for x in missing)
    assert all(x["verified_master_rrp"] is False for x in missing)
    assert all("rrp" not in x for x in missing if x != "verified_master_rrp")


def test_missing_sku_rows_appear_in_filtered_read_only_worklist(monkeypatch):
    products, configs, pricing, _, _ = synthetic_sources()
    products.append({"sku": None, "name": "Unnamed source row", "rrp": 10})
    report = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"}
    )
    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-reviewer")
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: report)
    response = quote_reconciliation.reconciliation_worklist(
        q="", issue="missing_sku", limit=20, offset=0
    )
    assert response["total"] == 1
    assert response["items"][0]["catalogue_source_row"] == 7
    assert response["price_approved"] is False


def test_legacy_review_records_source_rows_without_pricing(monkeypatch):
    products, configs, pricing, legacy, history = synthetic_sources()
    legacy.extend([
        {"old_code": "LEGACY-MIXED", "new_sku": "EXAMPLE-001"},
        {"old_code": "LEGACY-MIXED", "new_sku": "NO-SUCH-SKU"},
        {"old_code": "LEGACY-DUP", "new_sku": "EXAMPLE-DUP"},
        {"old_code": "LEGACY-INVALID", "new_sku": ""},
        "not a dictionary",
    ])
    result = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"},
        legacy=legacy, legacy_sha="f" * 64,
    )
    summary = result["summary"]
    assert summary["legacy_source_rows"] == 10
    assert summary["legacy_missing_target_mappings"] == 2
    assert summary["legacy_invalid_source_rows"] == 1
    assert summary["legacy_codes_with_unresolved_targets"] >= 2
    assert summary["legacy_source_rows_requiring_review"] >= 8
    assert "LEGACY-MIXED" in result["legacy_ambiguous"]
    assert "LEGACY-DUP" in result["legacy_ambiguous"]
    assert all(row["approved_price"] is None for row in result["legacy_worklist"])
    assert all("rrp" not in row for row in result["legacy_worklist"])

    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-reviewer")
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: result)
    response = quote_reconciliation.legacy_reconciliation_worklist(
        q="LEGACY-MIXED", issue="", limit=20, offset=0
    )
    assert response["total"] == 2
    assert response["price_approved"] is False
    resolved = quote_reconciliation.resolve_legacy("LEGACY-MIXED")
    assert resolved["match_count"] == 1
    assert resolved["ambiguous"] is True  # Other source row had missing target.


def test_unstaged_legacy_worklist_is_unavailable_not_an_empty_success(monkeypatch):
    products, configs, pricing, _, _ = synthetic_sources()
    result = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"}
    )
    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-staff")
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: result)
    with pytest.raises(HTTPException) as err:
        quote_reconciliation.legacy_reconciliation_worklist(q="", issue="", limit=20, offset=0)
    assert err.value.status_code == 503


def test_legacy_two_old_fields_do_not_double_count_missing_target():
    products, configs, pricing, _, _ = synthetic_sources()
    result = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"},
        legacy=[{
            "old_code": "OLD-ONE", "old_sku": "OLD-TWO",
            "new_sku": "MISSING-NEW",
        }],
    )
    assert result["summary"]["legacy_missing_target_mappings"] == 1
    assert result["summary"]["legacy_source_rows_requiring_review"] == 1


def test_policy_duplicate_rate_and_console_rows_create_unpriced_review_items(monkeypatch):
    products, configs, pricing, _, _ = synthetic_sources()
    pricing["rates"].append(dict(pricing["rates"][0]))
    pricing["console_rules"].append(dict(pricing["console_rules"][0]))
    result = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"}
    )
    summary = result["summary"]
    assert summary["policy_rule_rows_requiring_review"] == 4
    assert summary["policy_flag_counts"] == {
        "duplicate_console_rule": 2,
        "duplicate_rate_group": 2,
    }
    assert summary["pricing_policy_source_rows"] == {
        "rates": 3, "console_rules": 2
    }
    listed = result["policy_worklist"]
    assert [(row["source_section"], row["source_row"]) for row in listed] == [
        ("rates", 1), ("rates", 3),
        ("console_rules", 1), ("console_rules", 2),
    ]
    assert all("rrp" not in row and "rate" not in row for row in listed
               if not isinstance(row, str))
    assert all(row["price_approved"] is False for row in listed)
    flagged = next(row for row in result["worklist"] if row["sku"] == "EXAMPLE-001")
    assert "ambiguous_maintenance_rate_group" in flagged["issues"]
    assert "ambiguous_console_rule" in flagged["issues"]

    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-staff")
    monkeypatch.setattr(quote_reconciliation, "source_report", lambda: result)
    page = quote_reconciliation.reconciliation_policy_worklist(
        issue="duplicate_rate_group", limit=1, offset=1
    )
    assert page["total"] == 2
    assert page["items"][0]["source_row"] == 3
    assert page["price_approved"] is False


def test_policy_audit_reports_source_rows_without_identifiers():
    _, _, pricing, _, _ = synthetic_sources()
    pricing["rates"].append({"group": "", "standard": 0.99})
    pricing["console_rules"].append(None)
    report = quote_reconciliation.policy_reconciliation(pricing)
    assert report["flag_counts"]["missing_rate_group_name"] == 1
    assert report["flag_counts"]["invalid_policy_source_row"] == 1
    assert report["source_rows"]["rates"] == 3
    assert report["source_rows"]["console_rules"] == 2
    assert all(item["price_approved"] is False for item in report["worklist"])


def test_catalogue_exception_keeps_all_original_row_positions():
    products, configs, pricing, _, _ = synthetic_sources()
    report = quote_reconciliation.reconcile(
        products, configs, pricing, {"catalog": "fictional"}
    )
    dup = next(row for row in report["worklist"] if row["sku"] == "EXAMPLE-DUP")
    assert dup["catalogue_source_rows"] == [4, 5]
    assert dup["source_rows"] == 2
    # These source-row identities allow correction without choosing an RRP.
    assert dup["price_approved"] is False
