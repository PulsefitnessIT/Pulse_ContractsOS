"""Fictional parity tests for original V10 inclusive ACT/ACT staged cover."""
import pytest
from fastapi import HTTPException
from app import quote_drafts, quote_pricing
from app._smartquote_staged_v10 import pro_rata, parse_date, valid_contract

def sources():
    catalog=[{"sku":"FICTIONAL-1","service_key":"X | No Console / N/A",
              "name":"Fictional Bike","model":"X","console":"No Console / N/A",
              "rrp":2000.0,"match":"Mapped"}]
    configs=[{"key":"X | No Console / N/A",
              "eligible":"Yes","rate_group":"Standard Equipment"}]
    pricing={"currency":"GBP","tiers":{"Silver":0.8,"Gold":1.0,"Platinum":1.3},
             "pricing_status":"Provisional; not approved",
             "rates":[{"group":"Standard Equipment","standard":0.03,
                       "minimum":0.025,"uplift":0,"status":"Active"}],
             "console_rules":[{"name":"No Console / N/A","multiplier":1,"uplift":0}]}
    return catalog,configs,pricing,{"catalog":"fictional"}

def equipment(cover_start="", qty=1):
    return {"item_code":"FICTIONAL-1","description":"Fictional Bike",
            "serial":"DEMO","cover_start":cover_start,"quantity":qty}

def quote(start="",end="",rows=None):
    return {"id":"f"*32,"revision":1,"tier":"Gold","term_years":2,"discount_percent":0,
            "contract_start":start,"contract_end":end,"equipment":rows if rows is not None else [equipment()]}

def test_leap_year_prorata_exact_inclusive():
    assert pro_rata(120,parse_date("2028-07-01"),parse_date("2028-12-31"))==60.33
    assert pro_rata(120,parse_date("2028-01-01"),parse_date("2028-12-31"))==120.0

def test_staggered_two_year_totals_and_grouped_dates():
    q=quote("2028-01-01","2029-12-31",[equipment(),equipment("2028-07-01")])
    result=quote_pricing.preview(q,*sources())
    assert result["annual_partial"]==120.0
    assert result["staged"]["enabled"] is True
    assert result["term_partial"]==210.16
    assert [x["start"] for x in result["staged"]["stages"]]==["2028-01-01","2028-07-01"]
    assert [x["amount"] for x in result["staged"]["stages"]]==[120.0,90.16]
    assert result["lines"][1]["period_charge"]==90.16
    assert result["issue_quote_enabled"] is False

def test_partial_contract_dates_do_not_display_a_zero_term_value():
    q=quote(start="2028-01-01",end="")
    preview=quote_pricing.preview(q,*sources())
    assert preview["staged"]["enabled"] is True
    assert preview["term_partial"] is None
    assert any("both" in msg.lower() for msg in preview["issues"])

def test_without_dates_uses_original_simple_years_multiplier():
    result=quote_pricing.preview(quote(),*sources())
    assert result["staged"]["enabled"] is False
    assert result["annual_partial"]==60.0
    assert result["term_partial"]==120.0

@pytest.mark.parametrize("start,end",[
    ("2028-01-01","2028-01-01"), ("2028-12-31","2028-01-01"),
    ("2028-01-01","2034-12-31"), ("2028-02-30","2028-12-31")
])
def test_invalid_contract_period_rejected_by_draft_validator(start,end):
    with pytest.raises(HTTPException) as error:
        quote_drafts.validate_draft({"customer":"Fictional","site":"Demo",
                                     "contract_start":start,"contract_end":end})
    assert error.value.status_code==422

@pytest.mark.parametrize("cover",["2027-12-31","2030-01-01","2028-02-30"])
def test_outside_or_impossible_equipment_cover_start_rejected(cover):
    with pytest.raises(HTTPException) as error:
        quote_drafts.validate_draft({
            "customer":"Fictional","site":"Demo",
            "contract_start":"2028-01-01","contract_end":"2029-12-31",
            "equipment":[equipment(cover)]
        })
    assert error.value.status_code==422

def test_unpriced_staged_equipment_is_flagged_partial():
    q=quote("2028-01-01","2029-12-31",[
        equipment(),{"item_code":"UNKNOWN","description":"Unknown","quantity":1,"cover_start":"2028-07-01"}
    ])
    result=quote_pricing.preview(q,*sources())
    assert result["complete_price"] is False
    assert result["term_partial"]==120.0
    assert result["staged"]["stages"][0]["amount"]==120.0
    assert result["contract_setup_enabled"] is False
    assert any("SKU" in msg for msg in result["issues"])
