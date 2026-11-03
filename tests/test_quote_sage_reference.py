"""Sage price-source regression tests: advisory only, never pricing authority."""
import gzip
import hashlib
import json
import sqlite3
import datetime as dt
import pytest
from fastapi import HTTPException
from app import quote_sage_reference as sage


def test_verified_sage_snapshot_is_read_only_reference(tmp_path,monkeypatch):
    dbpath=tmp_path/"smartquote_demo.db"
    price_export=b"Code,Name,Product Group Description,Sales Price\nEXAMPLE-1,Fictional Bike,Strength Equipment,1234\n"
    sha=hashlib.sha256(price_export).hexdigest()
    payload=gzip.compress(json.dumps({"EXAMPLE-1":{
        "sku":"EXAMPLE-1", "name":"Fictional Bike",
        "group":"Strength Equipment","sales_price":1234.56
    }}).encode())
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE sage_price_snapshots(id INTEGER PRIMARY KEY, active INTEGER, source_date TEXT, review_due TEXT, file_sha256 TEXT, usable_rows INTEGER, payload BLOB)")
        db.execute("INSERT INTO sage_price_snapshots VALUES (?,?,?,?,?,?,?)",
                   (7,1,"2026-10-23","2027-10-23",sha,1,payload))
    def read_only():
        uri="file:"+str(dbpath)+"?mode=ro"
        conn=sqlite3.connect(uri,uri=True)
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn
    monkeypatch.setattr(sage,"_connect",read_only)
    snap=sage.snapshot()
    record=sage.reference("EXAMPLE-1",snap)
    assert record["sage_sales_price"]==1234.56
    assert record["approved_rrp"] is False
    assert record["quoted_annual_amount"] is None
    assert record["source_file_sha256"]==sha
    with sqlite3.connect(dbpath) as db:
        assert db.execute("SELECT COUNT(*) FROM sage_price_snapshots").fetchone()[0]==1


def test_missing_sage_source_is_not_invented(tmp_path,monkeypatch):
    dbpath=tmp_path/"no_sage.db"
    with sqlite3.connect(dbpath) as db:
        db.execute("CREATE TABLE quotes (id TEXT)")
    def read_only():
        conn=sqlite3.connect("file:"+str(dbpath)+"?mode=ro",uri=True)
        conn.row_factory=sqlite3.Row
        return conn
    monkeypatch.setattr(sage,"_connect",read_only)
    assert sage.snapshot() is None


@pytest.mark.parametrize("source",[
    {"prices":{"EXAMPLE-1":{"sku":"DIFFERENT","sales_price":100}},"review_due":"2026-01-01",
     "source_date":"2025-01-01","source_file_sha256":"0"*64},
    {"prices":{"EXAMPLE-1":{"sku":"EXAMPLE-1","sales_price":"NaN"}},"review_due":"2026-01-01",
     "source_date":"2025-01-01","source_file_sha256":"0"*64},
    {"prices":{"EXAMPLE-1":{"sku":"EXAMPLE-1","sales_price":-1}},"review_due":"2026-01-01",
     "source_date":"2025-01-01","source_file_sha256":"0"*64},
])
def test_inconsistent_sage_records_never_quoted(source):
    assert sage.reference("EXAMPLE-1",source) is None


def test_oversized_sage_export_is_rejected(monkeypatch):
    monkeypatch.setattr(sage,"MAX_UNCOMPRESSED",1024)
    with pytest.raises(HTTPException) as error:
        sage._unpack(gzip.compress(b"a"*5000))
    assert error.value.status_code==503



def test_sage_references_cannot_supersede_master_rrp_or_change_totals(monkeypatch):
    from app import quote_pricing
    code = "EXACT-1"
    conflict = "MASTER-NO-RRP"
    unknown = "SAGE-ONLY"
    catalog = [
        {"sku":code,"name":"Test Bike","model":"X",
         "service_key":"X | No Console / N/A","console":"No Console / N/A",
         "rrp":2000.0,"match":"Mapped"},
        {"sku":conflict,"name":"Unpriced machine","model":"X",
         "service_key":"X | No Console / N/A","console":"No Console / N/A",
         "rrp":None,"match":"Mapped"}
    ]
    configs = [{"key":"X | No Console / N/A","eligible":"Yes",
                "rate_group":"Standard Equipment"}]
    pricing = {
        "currency":"GBP", "tiers":{"Gold":1.0},
        "pricing_status":"Provisional", "rates":[{
            "group":"Standard Equipment","standard":0.03,"minimum":0.025,
            "uplift":0,"status":"Active"}],
        "console_rules":[{"name":"No Console / N/A","multiplier":1,"uplift":0}]
    }
    draft = {
        "id":"d"*32, "revision":1, "customer":"Fictional",
        "tier":"Gold","term_years":1,"discount_percent":0,
        "equipment":[
            {"item_code":code,"description":"Test bike","quantity":1},
            {"item_code":conflict,"description":"Master unpriced","quantity":1},
            {"item_code":unknown,"description":"Sage-only","quantity":1}
        ]
    }
    source = {
        "prices":{
            code:{"sku":code,"sales_price":5000},
            conflict:{"sku":conflict,"sales_price":5000},
            unknown:{"sku":unknown,"name":"Sage-only",
                     "group":"Strength Equipment","sales_price":5000}
        },
        "source_date":"2026-10-23","review_due":"2027-10-23",
        "review_overdue":False,"source_file_sha256":"b"*64,
        "source":"Sage Sales Price — NOT approved RRP"
    }
    monkeypatch.setattr(quote_pricing, "actor", lambda: "test")
    monkeypatch.setattr(quote_pricing, "get_draft", lambda _: draft)
    monkeypatch.setattr(quote_pricing, "source_snapshot",
                        lambda: (catalog,configs,pricing,{"catalog":"fictional"}))
    monkeypatch.setattr(quote_pricing, "sage_snapshot", lambda: source)
    from app import quote_price_overrides
    monkeypatch.setattr(quote_price_overrides, "active_overrides", lambda codes: {})
    from app import quote_rrp_priority
    # The genuine route requires the authoritative August list to be pinned.
    # Fictional fixture supplies one valid List Price and one invalid
    # on-master SKU; only genuinely absent SKUs may use Sage reference.
    monkeypatch.setattr(quote_rrp_priority, "source_snapshot", lambda: {
        "rows": [
            {"sku": code, "rrp": 2000, "name": "Test Bike",
             "console": "No Console / N/A", "sheet": "Fictional",
             "row": 4, "rrp_column": "List Price"},
            {"sku": conflict, "rrp": None, "name": "Unpriced machine",
             "console": "No Console / N/A", "sheet": "Fictional",
             "row": 5, "rrp_column": "List Price"},
        ],
        "source_date": "2026-08-24",
        "source_file_sha256": "f" * 64,
        "snapshot_sha256": "a" * 64,
    })
    result = quote_pricing.draft_price_preview(draft["id"])
    assert result["annual_partial"] == 60.0
    assert result["priced_count"] == 1
    assert result["complete_price"] is False
    assert "sage_reference" not in result["lines"][0]
    assert "sage_reference" not in result["lines"][1]  # Master always takes priority
    assert result["lines"][2]["sage_reference"]["sage_sales_price"] == 5000.0
    assert result["lines"][2]["sage_reference"]["quoted_annual_amount"] is None
    assert result["commercially_approved"] is False
    assert result["sage_reference_status"]["used_for_quotation"] is False


def test_full_sage_search_returns_legacy_identity_without_false_maintenance_approval(monkeypatch):
    monkeypatch.setattr(sage,"actor",lambda: "fictional-staff")
    monkeypatch.setattr(sage,"snapshot",lambda:{
        "prices":{
            "LEGACY 101/2":{"sku":"LEGACY 101/2","name":"Fictional old treadmill",
                            "group":"Cardiovascular Equipment","manufacturer":"Demo",
                            "sales_price":2350},
            "REPAIR-101":{"sku":"REPAIR-101","name":"Fictional treadmill motor",
                          "group":"CV Parts","manufacturer":"Demo","sales_price":175},
            "ZERO-102":{"sku":"ZERO-102","name":"Fictional old zero-price bike",
                        "group":"Cardiovascular Equipment","manufacturer":"Demo",
                        "sales_price":0},
        },
        "source_date":"2026-11-03",
    })
    old=sage.search_sage_items(q="legacy",limit=20)
    assert old["total"]==1
    assert old["results"][0]["sku"]=="LEGACY 101/2"
    assert old["results"][0]["sage_sales_price"]==2350
    assert old["results"][0]["pricing_approved"] is False
    assert old["results"][0]["requires_service_mapping"] is True
    parts=sage.search_sage_items(q="motor",limit=20)
    assert parts["total"]==1
    assert parts["results"][0]["group"]=="CV Parts"
    assert parts["results"][0]["source_price_is_not_maintenance_eligibility"] is True
    zeros=sage.search_sage_items(q="zero",limit=20)
    assert zeros["results"][0]["sage_sales_price"]==0
