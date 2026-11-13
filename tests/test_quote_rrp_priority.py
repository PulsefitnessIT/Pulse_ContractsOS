"""Fictional evidence for the user-approved Master -> Sage source priority."""
import gzip
import hashlib
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app import quote_rrp_priority as rrp


def staged(rows):
    return {
        "rows": rows,
        "source_date": rrp.MASTER_DATE,
        "source_file_sha256": rrp.MASTER_ORIGINAL_SHA256,
        "snapshot_sha256": "d" * 64,
    }


def line(code, amount, *, name="Fictional bike", console="No Console / N/A"):
    return {
        "sku": code, "rrp": amount, "name": name, "console": console,
        "sheet": "Fictional", "row": 17, "rrp_column": "List Price",
    }


def sage_source():
    return {
        "prices": {
            "MASTER-EXACT": {"sku": "MASTER-EXACT", "sales_price": 9999},
            "MASTER-CONFLICT": {"sku": "MASTER-CONFLICT", "sales_price": 9999},
            "NOT-ON-MASTER": {
                "sku": "NOT-ON-MASTER", "name": "Fictional fallback",
                "sales_price": 1550,
            },
        },
        "source_date": "2026-10-23", "review_due": "2027-10-23",
        "review_overdue": False, "source_file_sha256": "a" * 64,
        "source": "Sage Sales Price export — not an approved RRP",
    }


def test_exact_master_list_price_always_wins_over_sage():
    index = rrp.index(staged([line("MASTER-EXACT", 3000)]))
    result = rrp.resolve("master-exact", index, sage_source())
    assert result["basis"] == "august_2026_master_list_price"
    assert result["rrp"] == 3000
    assert "sage_reference" not in result
    assert result["review_required"] is False


def test_unchanged_duplicates_of_exact_master_row_are_safe_to_identify():
    row = line("MASTER-EXACT", "3000.00")
    result = rrp.resolve("MASTER-EXACT", rrp.index(staged([row, dict(row)])), sage_source())
    assert result["rrp"] == 3000.0
    assert len(result["master_rows"]) == 2


@pytest.mark.parametrize("rows,expected", [
    ([line("MASTER-CONFLICT", 200), line("MASTER-CONFLICT", 300)],
     "master_price_conflict"),
    ([line("MASTER-CONFLICT", None), line("MASTER-CONFLICT", 300)],
     "master_price_conflict"),
    ([line("MASTER-CONFLICT", 200, name="Bike"),
      line("MASTER-CONFLICT", 200, name="Treadmill")],
     "master_variant_conflict"),
    ([line("MASTER-CONFLICT", 200, console="Console X"),
      line("MASTER-CONFLICT", 200, console="Console Y")],
     "master_variant_conflict"),
])
def test_master_conflict_never_falls_through_to_sage(rows, expected):
    result = rrp.resolve("MASTER-CONFLICT", rrp.index(staged(rows)), sage_source())
    assert result["basis"] == expected
    assert result["rrp"] is None
    assert "sage_reference" not in result


def test_only_absent_master_sku_refers_to_exact_sage_sales_price():
    result = rrp.resolve("NOT-ON-MASTER", rrp.index(staged([
        line("MASTER-EXACT", 3200),
    ])), sage_source())
    assert result["basis"] == "sage_exact_sku_price"
    assert result["rrp"] == 1550.0
    assert result["sage_reference"]["sage_sales_price"] == 1550
    assert result["sage_reference"]["approved_rrp"] is False
    assert result["sage_reference"]["quoted_annual_amount"] is None


def test_sage_not_loaded_is_missing_not_automatic_old_v10_rrp():
    result = rrp.resolve("MISSING", rrp.index(staged([])))
    assert result["basis"] == "not_on_august_master_or_usable_sage_export"
    assert result["rrp"] is None


def test_manipulated_source_metadata_rejected(tmp_path, monkeypatch):
    payload = {
        "source_file": rrp.MASTER_FILE, "source_date": rrp.MASTER_DATE,
        "source_sha256": "f" * 64,
        "rows": [line("MASTER-EXACT", 3000)],
    }
    path = tmp_path / "rrp_2026_source.json.gz"
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    monkeypatch.setenv(rrp.SOURCE_ENV, str(path))
    with pytest.raises(HTTPException) as err:
        rrp.source_snapshot()
    assert err.value.status_code == 503


def test_pinned_source_must_match_master_snapshot_bytes(tmp_path, monkeypatch):
    payload = {
        "source_file": rrp.MASTER_FILE, "source_date": rrp.MASTER_DATE,
        "source_sha256": rrp.MASTER_ORIGINAL_SHA256,
        "rows": [line("MASTER-EXACT", 3000)],
    }
    path = tmp_path / "rrp_2026_source.json.gz"
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    monkeypatch.setenv(rrp.SOURCE_ENV, str(path))
    from app import quote_pricing
    monkeypatch.setattr(quote_pricing, "source_snapshot",
                        lambda: ([], [], {}, {"catalog": "a" * 64,
                            "configs": "b" * 64, "pricing": "c" * 64}))
    captured = []
    def manifest(proofs):
        captured.append(proofs)
        return {"pinned": True, "matches": True}
    monkeypatch.setattr(quote_pricing, "source_manifest_status", manifest)
    result = rrp.source_snapshot()
    assert result["rows"][0]["sku"] == "MASTER-EXACT"
    assert captured[0]["august_2026_rrp"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source_file_sha256"] == rrp.MASTER_ORIGINAL_SHA256


def test_preview_uses_august_price_without_modifying_original_catalogue():
    from app import quote_pricing
    catalog, configs, pricing, hashes = example_sources()
    original_value = catalog[0]["rrp"]
    chosen = rrp.index(staged([line("EXAMPLE-SKU", 3000)]))
    result = quote_pricing.preview(
        example_draft(), catalog, configs, pricing, hashes,
        master_by_sku=chosen, sage_source=sage_source(),
    )
    assert result["priced_count"] == 1
    assert result["lines"][0]["rrp"] == 3000.0
    assert result["lines"][0]["annual"] == 90.0
    assert result["annual_partial"] == 90.0
    assert result["lines"][0]["rrp_source"] == "august_2026_master_list_price"
    assert result["lines"][0]["rrp_source_approved"] is False
    assert result["lines"][0]["review_required"] is True
    assert catalog[0]["rrp"] == original_value
    assert result["customer_quote_issue_enabled"] is False if "customer_quote_issue_enabled" in result else result["issue_quote_enabled"] is False


def test_preview_never_uses_old_catalogue_price_when_master_absent():
    from app import quote_pricing
    catalog, configs, pricing, hashes = example_sources()
    sage = sage_source()
    sage["prices"]["EXAMPLE-SKU"] = {"sku": "EXAMPLE-SKU", "sales_price": 2500}
    result = quote_pricing.preview(
        example_draft(), catalog, configs, pricing, hashes,
        master_by_sku=rrp.index(staged([])), sage_source=sage,
    )
    assert result["priced_count"] == 1
    assert result["lines"][0]["priced"] is True
    assert result["lines"][0]["rrp"] == 2500
    assert result["annual_partial"] == 75.0
    assert result["lines"][0]["sage_reference"]["sage_sales_price"] == 2500
    assert result["lines"][0]["rrp_source"] == "sage_exact_sku_price"
    assert result["complete_price"] is True
    assert result["issue_quote_enabled"] is False


def test_source_priority_summary_counts_are_aggregate_only():
    master = staged([
        line("EXAMPLE-SKU", 3000),
        line("CONFLICT", 1000),
        line("CONFLICT", 1400),
        line("MASTER-NEW", 800),
    ])
    catalog = [
        {"sku": "EXAMPLE-SKU"}, {"sku": "CONFLICT"},
        {"sku": "NOT-ON-MASTER"}, {"sku": "ABSENT"},
    ]
    result = rrp.summarize_priority(master, catalog, sage_source())
    counts = result["counts"]
    assert counts["v10_skus_with_master_reference"] == 1
    assert counts["v10_skus_with_conflicting_master_rows"] == 1
    assert counts["v10_skus_referred_to_sage"] == 1
    assert counts["v10_skus_absent_from_both_lists"] == 1
    assert counts["august_master_skus_not_in_v10"] == 1
    assert result["sage_exact_price_used_as_internal_rrp_basis"] is True
    assert result["customer_quote_issue_enabled"] is False
    assert "EXAMPLE-SKU" not in json.dumps(result)
    assert "3000" not in json.dumps(result)


def example_sources():
    return [
        {
            "sku": "EXAMPLE-SKU", "rrp": 1000,
            "name": "Fictional equipment",
            "model": "X", "service_key": "X | No Console / N/A",
            "console": "No Console / N/A", "match": "Exact SKU",
        },
    ], [
        {"key": "X | No Console / N/A", "eligible": "Yes",
         "rate_group": "Standard Equipment"},
    ], {
        "tiers": {"Gold": 1.0}, "pricing_status": "Provisional",
        "rates": [{"group": "Standard Equipment", "standard": .03,
                   "minimum": .025, "uplift": 0, "status": "Active"}],
        "console_rules": [{"name": "No Console / N/A",
                           "multiplier": 1, "uplift": 0}],
    }, {"catalog": "a"*64, "configs": "b"*64, "pricing": "c"*64}


def example_draft():
    return {
        "id": "e"*32, "revision": 1, "tier": "Gold",
        "term_years": 1, "discount_percent": 0,
        "equipment": [{"item_code": "EXAMPLE-SKU", "quantity": 1}],
    }


def test_sage_zero_price_code_retained_for_price_admin_but_not_automatically_priced():
    source=sage_source()
    source["prices"]["SPECIAL ITEM#2"]={
        "sku":"SPECIAL ITEM#2",
        "sales_price":0.0,
        "name":"Legacy fictional equipment"
    }
    decision=rrp.resolve("SPECIAL ITEM#2",rrp.index(staged([])),source)
    assert decision["basis"]=="sage_unpriced_exact_sku"
    assert decision["rrp"] is None
    assert decision["review_required"] is True


def test_sage_extended_code_characters_match_exactly_with_no_surrogate_id():
    source=sage_source()
    source["prices"]["FS800-100(209)"]={
        "sku":"FS800-100(209)","sales_price":320.64,
        "name":"Fictional complex Sage code"
    }
    decision=rrp.resolve("fs800-100(209)",rrp.index(staged([])),source)
    assert decision["basis"]=="sage_exact_sku_price"
    assert decision["rrp"]==320.64



def test_current_master_console_variant_mismatch_blocks_customer_approval():
    from app import quote_pricing
    from app.quote_customer_issuance import _errors
    catalogue, configs, pricing, hashes = example_sources()
    master = staged([line("EXAMPLE-SKU", 3000, console="Different Console")])
    result = quote_pricing.preview(
        example_draft(), catalogue, configs, pricing, hashes,
        master_by_sku=rrp.index(master), sage_source=None,
    )
    assert result["priced_count"] == 1
    assert any("console variant" in reason for reason in result["lines"][0]["coverage_review"])
    assert any("commercial or equipment coverage" in issue
               for issue in _errors(example_draft(), result))



def test_real_master_tactile_console_terminology_does_not_block_exact_source_identity():
    """The two authentic source systems name the same cardio console differently."""
    from app import quote_pricing
    from app.quote_customer_issuance import _errors
    catalogue, configs, policy, fingerprints = example_sources()
    catalogue[0].update({
        "name":"Fictional Club Line Treadmill with 10.1-inch Tactile Console",
        "console":"Console 5 (Series 2)",
    })
    policy["console_rules"]=[{
        "name":"Console 5 (Series 2)","multiplier":1,"uplift":0,
    }]
    master=staged([line("EXAMPLE-SKU",3000,
        name=catalogue[0]["name"],console="10.1-inch cardio tactile-key")])
    result=quote_pricing.preview(
        example_draft(),catalogue,configs,policy,fingerprints,
        master_by_sku=rrp.index(master),
    )
    item=result["lines"][0]
    assert item["priced"] is True
    assert item["rrp"]==3000.0
    assert item["master_console_evidence"]["identity_reconciled"] is True
    assert item["master_console_evidence"]["exact_full_name_match"] is True
    assert not any("console variant" in note for note in item["coverage_review"])
    assert _errors(example_draft(),result)==[]


@pytest.mark.parametrize("master_name,master_console",[
    ("Fictional Treadmill with Different Equipment", "10.1-inch cardio tactile-key"),
    ("Fictional Club Line Treadmill with 10.1-inch Tactile Console", "10.1-inch strength touchscreen (verify)"),
    ("Fictional Club Line Treadmill with 10.1-inch Tactile Console", "18.5-inch cardio touchscreen"),
    ("Fictional Club Line Treadmill with 10.1-inch Tactile Console", "Console not stated"),
])
def test_console_variant_stays_blocked_with_ambiguous_master_evidence(master_name,master_console):
    from app import quote_pricing
    from app.quote_customer_issuance import _errors
    cat,cfg,policy,hashes=example_sources()
    cat[0]["console"]="Console 5 (Series 2)"
    cat[0]["name"]="Fictional Club Line Treadmill with 10.1-inch Tactile Console"
    policy["console_rules"]=[{"name":"Console 5 (Series 2)","multiplier":1,"uplift":0}]
    master=staged([line("EXAMPLE-SKU",3000,name=master_name,console=master_console)])
    result=quote_pricing.preview(
        example_draft(),cat,cfg,policy,hashes,
        master_by_sku=rrp.index(master),
    )
    assert result["priced_count"]==1
    assert result["lines"][0]["master_console_evidence"]["identity_reconciled"] is False
    assert any("console variant" in note for note in result["lines"][0]["coverage_review"])
    assert any("equipment coverage exception" in note for note in _errors(example_draft(),result))



def test_unadorned_no_console_machine_with_same_full_title_is_quotable():
    from app import quote_pricing
    from app.quote_customer_issuance import _errors
    catalogue, configs, policy, hashes = example_sources()
    catalogue[0]["console"] = "No Console / N/A"
    catalogue[0]["name"] = "Fictional Weight Stack Tower in Black"
    master = staged([line(
        "EXAMPLE-SKU", 3000, name=catalogue[0]["name"],
        console="Console not stated",
    )])
    result = quote_pricing.preview(
        example_draft(), catalogue, configs, policy, hashes,
        master_by_sku=rrp.index(master),
    )
    assert result["complete_price"] is True
    assert result["lines"][0]["master_console_evidence"]["identity_reconciled"] is True
    assert not any("console variant" in s for s in result["lines"][0]["coverage_review"])
    assert _errors(example_draft(),result) == []


@pytest.mark.parametrize("text",[
    "Fictional Machine with LCD Console in Black",
    "Fictional Machine with PM5 Display in Black",
    "Fictional Machine with Touchscreen in Black",
    "Fictional Machine with SmartCard in Black",
    "Fictional Machine with Touch-Key in Black",
    "Fictional Machine with NFC in Black",
])
def test_unstated_master_console_does_not_override_screen_clues(text):
    from app import quote_pricing
    from app.quote_customer_issuance import _errors
    catalogue, configs, policy, hashes = example_sources()
    catalogue[0]["console"] = "No Console / N/A"
    catalogue[0]["name"] = text
    master = staged([line(
        "EXAMPLE-SKU", 3000, name=text, console="Console not stated",
    )])
    result = quote_pricing.preview(
        example_draft(), catalogue, configs, policy, hashes,
        master_by_sku=rrp.index(master),
    )
    assert result["priced_count"] == 1
    assert result["lines"][0]["master_console_evidence"]["identity_reconciled"] is False
    assert any("console variant" in s for s in result["lines"][0]["coverage_review"])
    assert _errors(example_draft(), result)



def test_exact_master_source_price_displays_sage_difference_without_substitution():
    from app import quote_pricing
    cat,cfg,policy,hashes=example_sources()
    sage=sage_source()
    sage["prices"]["EXAMPLE-SKU"]={
        "sku":"EXAMPLE-SKU","sales_price":2500,
        "name":"Fictional equipment","group":"Strength Equipment",
    }
    preview=quote_pricing.preview(
        example_draft(),cat,cfg,policy,hashes,
        master_by_sku=rrp.index(staged([line("EXAMPLE-SKU",3000)])),
        sage_source=sage,
    )
    item=preview["lines"][0]
    assert item["rrp"]==3000.0
    assert item["source_price_comparison"]["sage_sales_price_gbp"]==2500.0
    assert item["source_price_comparison"]["percentage_difference"]==-16.67
    assert item["source_price_comparison"]["requires_explicit_ack"] is False
    assert item["source_price_comparison"]["comparison_for_information_only"] is True
    assert item["source_price_comparison"]["not_a_new_or_approved_tariff"] is True
    assert preview["annual_partial"]==90.0


def test_small_source_price_difference_does_not_trigger_extra_approval():
    from app import quote_pricing
    cat,cfg,policy,hashes=example_sources()
    sage=sage_source()
    sage["prices"]["EXAMPLE-SKU"]={
        "sku":"EXAMPLE-SKU","sales_price":2900,"name":"Fictional equipment",
    }
    preview=quote_pricing.preview(
        example_draft(),cat,cfg,policy,hashes,
        master_by_sku=rrp.index(staged([line("EXAMPLE-SKU",3000)])),
        sage_source=sage,
    )
    assert preview["lines"][0]["source_price_comparison"]["requires_explicit_ack"] is False
    assert preview["annual_partial"]==90.0
