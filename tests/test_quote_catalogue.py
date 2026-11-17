"""Private SmartQuote product catalogue is identity-only, never a price source."""
import json
import pytest
from fastapi import HTTPException
from app import quote_catalogue


def test_catalogue_search_is_identity_only(tmp_path, monkeypatch):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps([
        {"sku":"BIKE-1","name":"Studio Bike","model":"SB-1","rrp":1299},
        {"sku":"BIKE-1","name":"Studio Bike — alternate","model":"SB-1","rrp":1399},
        {"sku":"TREAD-2","name":"Treadmill","model":"TR-2","rrp":3400},
    ]))
    monkeypatch.setenv("PULSE_SMARTQUOTE_CATALOG_JSON", str(p))
    monkeypatch.setattr(quote_catalogue, "actor", lambda: "coordinator")
    result = quote_catalogue.search_catalogue("BIKE", 10)
    assert result["total"] == 2
    assert result["identity_only"] is True
    assert result["price_supplied"] is False
    assert all("rrp" not in x and "price" not in x for x in result["results"])
    assert all(x["duplicate_sku"] is True for x in result["results"])
    assert all(x["pricing_approved"] is False for x in result["results"])


def test_missing_catalogue_refuses_invented_identity(monkeypatch):
    monkeypatch.delenv("PULSE_SMARTQUOTE_CATALOG_JSON", raising=False)
    monkeypatch.setattr(quote_catalogue, "actor", lambda: "coordinator")
    with pytest.raises(HTTPException) as err:
        quote_catalogue.search_catalogue("BIKE", 5)
    assert err.value.status_code == 503


def test_short_catalogue_search_rejected(tmp_path, monkeypatch):
    p = tmp_path / "catalog.json"
    p.write_text("[]")
    monkeypatch.setenv("PULSE_SMARTQUOTE_CATALOG_JSON", str(p))
    monkeypatch.setattr(quote_catalogue, "actor", lambda: "coordinator")
    with pytest.raises(HTTPException) as err:
        quote_catalogue.search_catalogue(" ", 5)
    assert err.value.status_code == 422



def test_admin_staged_original_v10_catalogue_is_searchable_without_it_file(monkeypatch):
    """In-app source ZIP must work for search as well as price calculations."""
    import hashlib
    from app import quote_source_setup
    monkeypatch.delenv("PULSE_SMARTQUOTE_CATALOG_JSON", raising=False)
    monkeypatch.setattr(quote_catalogue, "actor", lambda: "fictional-coordinator")
    rows=[
        {"sku":"FIC-TREAD-1","name":"Synthetic treadmill","model":"FIC-260",
         "console":"Console 8 (Series 3 Mini)",
         "service_key":"FIC-260 | Console 8 (Series 3 Mini)",
         "rrp":99999},
        {"sku":"FIC-BIKE-2","name":"Synthetic cycle","model":"FIC-330",
         "console":"No Console / N/A",
         "service_key":"FIC-330 | No Console / N/A",
         "rrp":12345},
    ]
    binary=json.dumps(rows).encode("utf-8")
    digest=hashlib.sha256(binary).hexdigest()
    monkeypatch.setattr(quote_source_setup,"active_source",lambda:{
        "files":{"catalog":binary},"hashes":{"catalog":digest}
    })
    quote_catalogue._bundle_catalogue.cache_clear()
    result=quote_catalogue.search_catalogue("FIC-TREAD",10)
    assert result["total"]==1
    assert result["results"][0]["sku"]=="FIC-TREAD-1"
    assert result["results"][0]["console"]=="Console 8 (Series 3 Mini)"
    assert result["results"][0]["service_key"]=="FIC-260 | Console 8 (Series 3 Mini)"
    assert result["results"][0]["duplicate_sku"] is False
    assert result["results"][0]["pricing_approved"] is False
    assert "rrp" not in result["results"][0]


def test_explicit_broken_it_catalogue_does_not_fallback_to_admin_bundle(monkeypatch, tmp_path):
    from app import quote_source_setup
    monkeypatch.setenv("PULSE_SMARTQUOTE_CATALOG_JSON",str(tmp_path/"missing.json"))
    monkeypatch.setattr(quote_catalogue,"actor",lambda:"fictional-coordinator")
    called=[]
    monkeypatch.setattr(quote_source_setup,"active_source",lambda:called.append(True))
    with pytest.raises(HTTPException) as error:
        quote_catalogue.search_catalogue("FIC",10)
    assert error.value.status_code==503
    assert called==[]


def test_verified_bundle_catalogue_rejects_digest_mismatch():
    quote_catalogue._bundle_catalogue.cache_clear()
    with pytest.raises(HTTPException) as error:
        quote_catalogue._bundle_catalogue("0"*64, b'[{"sku":"FIC-1"}]')
    assert error.value.status_code==503
