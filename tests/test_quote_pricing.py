"""Deterministic V10 tariff preview parity, using fictional SKUs only."""
import json

import pytest
from fastapi import HTTPException

from app import quote_drafts, quote_pricing


def example():
    catalog = [
        {"sku": "TEST-100", "service_key": "TEST | No Console / N/A", "name": "Example Bike",
         "model":"TEST", "console":"No Console / N/A", "rrp":2000, "match":"Mapped"},
        {"sku": "TEST-DUP", "service_key": "TEST | No Console / N/A",
         "name":"Variant A", "rrp":1000},
        {"sku": "TEST-DUP", "service_key": "TEST | No Console / N/A",
         "name":"Variant B", "rrp":1500}
    ]
    configs = [
        {"key":"TEST | No Console / N/A","rate_group":"Standard Equipment","eligible":"Yes"}
    ]
    pricing = {
        "currency":"GBP", "source_snapshot":"2026-10-15",
        "pricing_status":"Provisional; requires authorised commercial approval before issue",
        "tiers":{"Silver":0.8,"Gold":1.0,"Platinum":1.3},
        "rates":[{"group":"Standard Equipment", "standard":0.03, "minimum":0.025,
                  "uplift":0, "status":"Active"}],
        "console_rules":[{"name":"No Console / N/A", "multiplier":1,"uplift":0}]
    }
    return catalog,configs,pricing,{"catalog":"fictional", "configs":"fictional", "pricing":"fictional"}


def draft(tier="Gold", discount=0, term=1):
    return {"id":"e"*32,"revision":1, "tier":tier, "term_years":term,
            "discount_percent":discount, "equipment":[
               {"item_code":"TEST-100","description":"Example Bike","quantity":2,"serial":""}]}


@pytest.mark.parametrize("tier,expected_unit,expected_annual", [
    ("Silver",48.0,96.0), ("Gold",60.0,120.0), ("Platinum",78.0,156.0)
])
def test_original_v10_standard_tariff_math(tier,expected_unit,expected_annual):
    # Original engine.price_line: base = RRP * standard_rate; apply package
    # and discount BEFORE rounding unit; line total = rounded_unit * qty.
    result=quote_pricing.preview(draft(tier),*example())
    assert result["lines"][0]["unit_annual"] == expected_unit
    assert result["lines"][0]["annual"] == expected_annual
    assert result["annual_partial"] == expected_annual
    assert result["issue_quote_enabled"] is False
    assert result["commercially_approved"] is False


def test_discount_and_term_pricing_does_not_approve_quotation():
    result=quote_pricing.preview(draft("Silver",10,3),*example())
    assert result["lines"][0]["unit_annual"] == 43.2
    assert result["annual_partial"] == 86.4
    assert result["term_partial"] == 259.2
    assert result["complete_price"] is True
    assert result["contract_setup_enabled"] is False


def test_discount_below_source_minimum_requires_review():
    result=quote_pricing.preview(draft("Gold",25),*example())
    assert result["lines"][0]["annual"] == 90.0
    assert result["lines"][0]["minimum_annual"] == 100.0
    assert result["lines"][0]["review_required"] is True
    assert any("below" in issue for issue in result["issues"])


def test_missing_and_duplicate_skus_are_never_automatically_priced():
    catalog,configs,pricing,hashes=example()
    q=draft()
    q["equipment"].extend([
        {"item_code":"TEST-DUP","description":"Conflicting variant","quantity":1},
        {"item_code":"MISSING","description":"Unknown machine","quantity":1},
        {"item_code":"","description":"Unknown machine","quantity":1}
    ])
    result=quote_pricing.preview(q,catalog,configs,pricing,hashes)
    assert result["priced_count"] == 1
    assert result["complete_price"] is False
    assert result["annual_partial"] == 120
    assert all(not x["priced"] for x in result["lines"][1:])


def test_unmapped_configuration_is_not_priced():
    catalog,configs,pricing,hashes=example()
    result=quote_pricing.preview(draft(),catalog,[],pricing,hashes)
    assert result["priced_count"] == 0
    assert result["annual_partial"] == 0
    assert "configuration" in result["lines"][0]["exception"]


def test_ineligible_equipment_is_not_priced():
    catalog,configs,pricing,hashes=example()
    configs[0]["eligible"] = "No"
    result=quote_pricing.preview(draft(),catalog,configs,pricing,hashes)
    assert not result["lines"][0]["priced"]
    assert result["annual_partial"] == 0


def test_missing_source_config_does_not_fabricate_rrp(monkeypatch):
    for key in ("PULSE_SMARTQUOTE_CATALOG_JSON", "PULSE_SMARTQUOTE_CONFIGS_JSON",
                "PULSE_SMARTQUOTE_PRICING_JSON"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(HTTPException) as err:
        quote_pricing.source_snapshot()
    assert err.value.status_code == 503


def test_private_source_snapshot_reads_exact_files_only(tmp_path,monkeypatch):
    catalog,configs,pricing,_=example()
    for key,filename,data in (
        ("PULSE_SMARTQUOTE_CATALOG_JSON","catalog.json",catalog),
        ("PULSE_SMARTQUOTE_CONFIGS_JSON","configs.json",configs),
        ("PULSE_SMARTQUOTE_PRICING_JSON","pricing.json",pricing),
    ):
        path = tmp_path / filename
        path.write_text(json.dumps(data),encoding="utf-8")
        monkeypatch.setenv(key,str(path))
    rows,config_rows,policy,hashes=quote_pricing.source_snapshot()
    assert rows[0]["sku"]=="TEST-100"
    assert len(hashes["catalog"])==64
    assert policy["currency"]=="GBP"
    assert quote_pricing.preview(draft(),rows,config_rows,policy,hashes)["annual_partial"]==120.0


@pytest.mark.parametrize("discount,term",[(101,1),(-1,1),(0,0),(0,6),("nan",1),(0,1.5)])
def test_invalid_commercial_inputs_rejected(discount,term):
    with pytest.raises(HTTPException) as err:
        quote_drafts.validate_draft({"customer":"Fictional","site":"Demo","tier":"Gold",
                                     "discount_percent":discount,"term_years":term})
    assert err.value.status_code == 422


def test_client_cannot_smuggle_an_approved_price_into_saved_draft():
    prepared=quote_drafts.validate_draft({
        "customer":"Fictional","site":"Demo","tier":"Gold","price":12345,
        "approved":True,"equipment":[{"description":"Bike","item_code":"TEST-100"}]
    })
    assert prepared["price"] is None
    assert prepared["approved"] is False



def test_text_rrp_is_not_silently_converted_to_verified_money():
    catalog,configs,pricing,hashes=example()
    catalog[0]["rrp"]="2000"
    result=quote_pricing.preview(draft(),catalog,configs,pricing,hashes)
    assert not result["lines"][0]["priced"]
    assert result["annual_partial"] == 0


def test_invalid_console_multiplier_cannot_crash_or_price():
    catalog,configs,pricing,hashes=example()
    catalog[0]["console_multiplier_override"] = "not-a-number"
    result=quote_pricing.preview(draft(),catalog,configs,pricing,hashes)
    assert result["lines"][0]["priced"] is False
    assert "multiplier" in result["lines"][0]["exception"]


def test_unknown_console_requires_review_even_for_exact_sku():
    catalog,configs,pricing,hashes=example()
    catalog[0]["console"]="Unknown Console"
    result=quote_pricing.preview(draft(),catalog,configs,pricing,hashes)
    assert result["lines"][0]["priced"] is True
    assert result["lines"][0]["review_required"] is True
    assert any("Console" in text for text in result["lines"][0]["coverage_review"])


def test_non_active_rate_is_flagged_as_not_authorised():
    catalog,configs,pricing,hashes=example()
    pricing["rates"][0]["status"] = "Review"
    result=quote_pricing.preview(draft(),catalog,configs,pricing,hashes)
    assert result["lines"][0]["priced"] is True
    assert result["lines"][0]["review_required"] is True
    assert result["commercially_approved"] is False


def test_source_discount_rounds_one_unit_before_quantity():
    catalog,configs,pricing,hashes=example()
    catalog[0]["rrp"] = 333.33
    q=draft("Silver")
    q["equipment"][0]["quantity"]=3
    # 333.33 * .03 * .8 = 7.99992 -> 8.00 per machine -> 24.00.
    result=quote_pricing.preview(q,catalog,configs,pricing,hashes)
    assert result["lines"][0]["unit_annual"] == 8.0
    assert result["lines"][0]["annual"] == 24.0


def test_missing_private_manifest_never_claims_source_approval(monkeypatch):
    monkeypatch.delenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST",raising=False)
    status=quote_pricing.source_manifest_status({
        "catalog":"a"*64,"configs":"b"*64,"pricing":"c"*64
    })
    assert status["pinned"] is False
    assert status["matches"] is False
    assert status["commercially_approved"] is False


def test_private_source_manifest_detects_changed_rrp_file(tmp_path,monkeypatch):
    import hashlib
    catalogue,configs,pricing,_=example()
    fingerprints={}
    for part,variable,filename,data in (
        ("catalog","PULSE_SMARTQUOTE_CATALOG_JSON","catalog.json",catalogue),
        ("configs","PULSE_SMARTQUOTE_CONFIGS_JSON","configs.json",configs),
        ("pricing","PULSE_SMARTQUOTE_PRICING_JSON","pricing.json",pricing),
    ):
        file=tmp_path/filename
        file.write_text(json.dumps(data),encoding="utf-8")
        monkeypatch.setenv(variable,str(file))
        fingerprints[part]=hashlib.sha256(file.read_bytes()).hexdigest()
    manifest=tmp_path/"approved_source_manifest.json"
    manifest.write_text(json.dumps({
        "sha256":fingerprints,"owner":"Fictional IT owner","effective_date":"2026-11-03"
    }))
    monkeypatch.setenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST",str(manifest))
    assert quote_pricing.source_manifest_status(fingerprints)["pinned"] is True
    assert quote_pricing.source_manifest_status(fingerprints)["commercially_approved"] is False
    quote_pricing.source_snapshot()  # Valid pinned test-only source.
    changed=tmp_path/"catalog.json"
    changed.write_text(json.dumps([{**catalogue[0],"rrp":9999999}]))
    with pytest.raises(HTTPException) as error:
        quote_pricing.source_snapshot()
    assert error.value.status_code==503
    assert "source manifest" in error.value.detail.lower()
