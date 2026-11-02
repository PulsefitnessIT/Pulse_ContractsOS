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
