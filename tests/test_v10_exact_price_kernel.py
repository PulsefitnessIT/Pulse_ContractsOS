"""Original V10 price_line source arithmetic tested with fictional price evidence."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app._smartquote_price_line_v10 import original_v10_price_line
from app.quote_pricing import preview


def policy(rate=.03, status="Active"):
    return {
        "currency": "GBP",
        "source_snapshot": "fictional test only",
        "pricing_status": "Provisional; NOT approved",
        "tiers": {"Silver":.8,"Gold":1.0,"Platinum":1.3},
        "rates": [{"group":"Standard Equipment","standard":rate,
                   "preferred":rate,"minimum":.025,"uplift":1.0,"status":status}],
        "console_rules":[{"name":"No Console / N/A","multiplier":1,"uplift":2.0}],
    }


def asset(qty=3, rrp=333.33, multiplier=1.2):
    return {"qty":qty, "selected":{
        "sku":"FICTIONAL-1","rrp":rrp,
        "rate_group":"Standard Equipment", "console":"No Console / N/A",
        "console_pricing":multiplier, "eligible":"Yes",
        "price_origin":"mapped","pricing_rule":"Fictional source"
    }}


@pytest.mark.parametrize("tier,discount,qty",[
    ("Silver",0,1),("Gold",0,3),("Platinum",20,3),
    ("Silver",10,10),("Gold",25,11),("Platinum",33.33,2)
])
def test_unit_first_rounding_and_minimum_as_original_engine(tier,discount,qty):
    source=policy()
    result=original_v10_price_line(asset(qty), "Standard",tier,discount,source)
    assert result["annual"]==pytest.approx(result["unit"]*qty,abs=.01)
    assert result["qty"]==qty
    assert result["rate"]==source["rates"][0]["standard"]
    assert result["minimum"]>0


def test_manual_annual_unit_branch_remains_original_and_not_source_rrp():
    original={"qty":2,"manual_annual_unit":100}
    result=original_v10_price_line(original,"Standard","Gold",10,policy())
    assert result["unit"]==90
    assert result["annual"]==180
    assert result["minimum"]==0
    assert result["manual"] is True
    assert result["rrp"] is None


def test_historical_price_is_explicitly_reference_only():
    original={"qty":1,"historic_rrp":1000,
              "historic_rate_percent":3,"historic_annual_unit":35}
    result=original_v10_price_line(original,"Standard","Silver",10,policy())
    assert result["unit"]==25.2
    assert result["basis"]=="historic-reference"
    assert "Historic" in result["rule"]


def test_source_prices_are_isolated_across_parallel_users():
    first=policy(rate=.03)
    second=policy(rate=.04)
    one=asset(qty=1,rrp=2000,multiplier=1)
    def calculate(source):
        return original_v10_price_line(one,"Standard","Gold",0,source)["unit"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        amounts=list(pool.map(calculate,[first,second]*40))
    assert amounts[0]==pytest.approx(63.0)
    assert amounts[1]==pytest.approx(83.0)
    assert all(amounts[i]==amounts[i%2] for i in range(len(amounts)))


def test_exact_native_preview_uses_original_source_function():
    source=policy()
    product={"sku":"FICTIONAL-1","service_key":"FICTIONAL | No Console",
             "model":"FICTIONAL","console":"No Console / N/A",
             "name":"Example Bike","rrp":333.33,"match":"Mapped",
             "console_multiplier_override":1.2}
    config={"key":"FICTIONAL | No Console",
            "rate_group":"Standard Equipment","eligible":"Yes"}
    quote={"id":"a"*32,"revision":1,"tier":"Platinum",
           "term_years":1,"discount_percent":10,
           "equipment":[{"item_code":"FICTIONAL-1",
                         "description":"Example Bike","quantity":3}]}
    result=preview(quote,[product],[config],source,{"catalog":"fictional"})
    original=original_v10_price_line(asset(), "Standard","Platinum",10,source)
    line=result["lines"][0]
    assert line["unit_annual"]==original["unit"]
    assert line["annual"]==original["annual"]
    assert line["minimum_annual"]==original["minimum"]
    assert line["source_engine"]=="original SmartQuote V10 price_line arithmetic"
    assert result["issue_quote_enabled"] is False
    assert result["commercially_approved"] is False


def test_deleted_or_unknown_tariff_does_not_auto_price():
    selected=asset()
    selected["selected"]["rate_group"]="Unknown Source Rate"
    assert original_v10_price_line(selected,"Standard","Gold",0,policy()) is None


def test_original_price_function_identity_guard_detects_drift():
    from types import SimpleNamespace
    from app._smartquote_price_line_v10 import price_line
    from scripts.check_v10_price_parity import verify_original_function
    verify_original_function(SimpleNamespace(price_line=price_line))
    def altered_price_line(asset,level,tier,discount):
        return {"unit":1000000}
    with pytest.raises(RuntimeError,match="differs"):
        verify_original_function(SimpleNamespace(price_line=altered_price_line))
