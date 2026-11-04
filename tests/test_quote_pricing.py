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


def test_duplicate_rate_group_blocks_pricing_not_last_rule_wins():
    catalogue, configs, pricing, fingerprints = example()
    pricing["rates"].append({
        "group": "Standard Equipment", "standard": .20,
        "minimum": .05, "status": "Active",
    })
    result = quote_pricing.preview(draft(), catalogue, configs, pricing, fingerprints)
    assert result["priced_count"] == 0
    assert result["complete_price"] is False
    assert result["lines"][0]["priced"] is False
    assert "Conflicting" in result["lines"][0]["exception"]
    assert result["issue_quote_enabled"] is False
    assert result["commercially_approved"] is False


def test_duplicate_console_rules_block_pricing_not_last_rule_wins():
    catalogue, configs, pricing, fingerprints = example()
    pricing["console_rules"].append({
        "name": "No Console / N/A", "multiplier": 50, "uplift": 0,
    })
    result = quote_pricing.preview(draft(), catalogue, configs, pricing, fingerprints)
    assert result["priced_count"] == 0
    assert result["lines"][0]["priced"] is False
    assert "Conflicting" in result["lines"][0]["exception"]
    assert result["issue_quote_enabled"] is False


def test_unrelated_duplicate_tariff_does_not_block_unique_source_group():
    catalogue, configs, pricing, fingerprints = example()
    pricing["rates"].extend([
        {"group": "Unrelated", "standard": .01, "status": "Active"},
        {"group": "Unrelated", "standard": .05, "status": "Active"},
    ])
    result = quote_pricing.preview(draft(), catalogue, configs, pricing, fingerprints)
    assert result["priced_count"] == 1
    assert result["annual_partial"] == 120.0
    assert result["issue_quote_enabled"] is False


def _set_comparison_sources(monkeypatch, source_draft=None, catalogue=None, configs=None, pricing=None):
    from app import quote_rrp_priority, quote_price_overrides
    cat, cfg, policy, hashes = example()
    if catalogue is not None: cat = catalogue
    if configs is not None: cfg = configs
    if pricing is not None: policy = pricing
    saved = source_draft or draft()
    source = {
        "rows": [
            {
                "sku": "TEST-100", "rrp": 2000,
                "name": "Example Bike", "console": "No Console / N/A",
                "sheet": "Test", "row": 2, "rrp_column": "List Price",
            }
        ],
        "source_date": quote_rrp_priority.MASTER_DATE,
        "source_file_sha256": quote_rrp_priority.MASTER_ORIGINAL_SHA256,
        "snapshot_sha256": "b" * 64,
    }
    monkeypatch.setattr(quote_pricing, "get_draft", lambda _: saved)
    monkeypatch.setattr(quote_pricing, "source_snapshot", lambda: (cat, cfg, policy, hashes))
    monkeypatch.setattr(quote_pricing, "sage_snapshot", lambda: None)
    monkeypatch.setattr(quote_rrp_priority, "source_snapshot", lambda: source)
    monkeypatch.setattr(quote_price_overrides, "active_overrides", lambda _: {})
    return saved


def test_tier_comparison_uses_one_verified_equipment_price_basis(monkeypatch):
    saved = _set_comparison_sources(monkeypatch)
    before = json.dumps(saved, sort_keys=True)
    result = quote_pricing.draft_tier_comparison(saved["id"])
    assert result["selected_tier"] == "Gold"
    assert result["revision"] == 1
    assert result["indicative_only"] is True
    assert result["commercially_approved"] is False
    assert result["customer_quote_issued"] is False
    assert [x["annual_gbp"] for x in result["options"]] == [96, 120, 156]
    assert [x["monthly_gbp"] for x in result["options"]] == [8, 10, 13]
    assert [x["term_gbp"] for x in result["options"]] == [96, 120, 156]
    assert all(x["complete_price"] for x in result["options"])
    assert json.dumps(saved, sort_keys=True) == before


def test_tier_comparison_hides_partial_amounts_for_unknown_equipment(monkeypatch):
    incomplete = draft()
    incomplete["equipment"].append({
        "item_code": "UNKNOWN-ITEM", "description": "Unknown equipment",
        "quantity": 1, "serial": "",
    })
    _set_comparison_sources(monkeypatch, source_draft=incomplete)
    result = quote_pricing.draft_tier_comparison(incomplete["id"])
    assert all(not x["complete_price"] for x in result["options"])
    assert all(x["annual_gbp"] is None for x in result["options"])
    assert all(x["monthly_gbp"] is None for x in result["options"])
    assert all(x["term_gbp"] is None for x in result["options"])
    assert all(x["priced_lines"] == 1 and x["total_lines"] == 2 for x in result["options"])
    assert any("UNKNOWN-ITEM" in json.dumps(x) for x in result["options"]) is False


def test_tier_comparison_does_not_invent_unsupported_v10_tier(monkeypatch):
    _, _, pricing, _ = example()
    pricing["tiers"].pop("Platinum")
    saved = _set_comparison_sources(monkeypatch, pricing=pricing)
    result = quote_pricing.draft_tier_comparison(saved["id"])
    assert result["options"][2]["tier"] == "Platinum"
    assert result["options"][2]["available"] is False
    assert result["options"][2]["annual_gbp"] is None


def test_tier_comparison_uses_sage_for_valid_legacy_sku_without_master_row(monkeypatch):
    from app import quote_rrp_priority
    saved = _set_comparison_sources(monkeypatch)
    monkeypatch.setattr(quote_rrp_priority, "source_snapshot", lambda: {
        "rows": [], "source_date": quote_rrp_priority.MASTER_DATE,
        "source_file_sha256": quote_rrp_priority.MASTER_ORIGINAL_SHA256,
        "snapshot_sha256": "b" * 64,
    })
    monkeypatch.setattr(quote_pricing, "sage_snapshot", lambda: {
        "prices": {"TEST-100": {
            "sku": "TEST-100", "sales_price": 3000.0, "name": "Example Bike"
        }},
        "source_date": "2026-10-23", "review_due": "2027-10-23",
        "review_overdue": False, "source_file_sha256": "a" * 64,
        "source": "Fictional Sage source",
    })
    result = quote_pricing.draft_tier_comparison(saved["id"])
    assert result["sage_source_sha256"] == "a" * 64
    assert [x["annual_gbp"] for x in result["options"]] == [144, 180, 234]
    assert all(x["complete_price"] for x in result["options"])


def test_tier_comparison_rejects_below_minimum_discount_without_showing_partial_price(monkeypatch):
    saved = _set_comparison_sources(
        monkeypatch, source_draft=draft("Gold", discount=75)
    )
    results = quote_pricing.draft_tier_comparison(saved["id"])["options"]
    assert all(not item["complete_price"] for item in results)
    assert all(item["annual_gbp"] is None for item in results)
    assert all(item["blockers"] for item in results)
    assert any(
        "minimum" in issue.lower()
        for item in results for issue in item["blockers"]
    )


def test_tier_comparison_rejects_overdue_sage_fallback_for_all_packages(monkeypatch):
    from app import quote_rrp_priority
    saved = _set_comparison_sources(monkeypatch)
    monkeypatch.setattr(quote_rrp_priority, "source_snapshot", lambda: {
        "rows": [], "source_date": quote_rrp_priority.MASTER_DATE,
        "source_file_sha256": quote_rrp_priority.MASTER_ORIGINAL_SHA256,
        "snapshot_sha256": "b" * 64,
    })
    monkeypatch.setattr(quote_pricing, "sage_snapshot", lambda: {
        "prices": {
            "TEST-100": {"sku": "TEST-100", "sales_price": 3000, "name": "Example Bike"}
        },
        "source_date": "2024-01-01", "review_due": "2025-01-01",
        "review_overdue": True, "source_file_sha256": "a" * 64,
        "source": "Fictional stale Sage snapshot",
    })
    result = quote_pricing.draft_tier_comparison(saved["id"])
    assert all(item["annual_gbp"] is None for item in result["options"])
    assert all(not item["complete_price"] for item in result["options"])
    assert all(any("overdue" in text for text in item["blockers"]) for item in result["options"])
