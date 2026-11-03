"""Protected source ZIP onboarding using synthetic source files only."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import quote_source_setup as src
from app import quote_pricing, quote_rrp_priority


def _setup(tmp_path,monkeypatch):
    path=tmp_path/"private-contracts-quotes.sqlite3"
    def connection():
        con=sqlite3.connect(path,timeout=10)
        con.row_factory=sqlite3.Row
        return con
    monkeypatch.setattr(src,"connect",connection)
    monkeypatch.setattr(src.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(src.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(src.pilot_access,"actor",lambda name="":"fictional-admin")
    for key in ("PULSE_SMARTQUOTE_CATALOG_JSON",
                "PULSE_SMARTQUOTE_CONFIGS_JSON",
                "PULSE_SMARTQUOTE_PRICING_JSON",
                "PULSE_SMARTQUOTE_RRP_2026_SOURCE",
                "PULSE_SMARTQUOTE_SOURCE_MANIFEST"):
        monkeypatch.delenv(key,raising=False)
    return path


def _bundle(changed=False):
    product={
        "sku":"FICTIONAL-EXACT","name":"Fictional Treadmill",
        "model":"FIC-X","service_key":"FIC-X | No Console / N/A",
        "console":"No Console / N/A","rrp":9999 if changed else 1200,
        "match":"Exact SKU",
    }
    config={
        "key":"FIC-X | No Console / N/A",
        "eligible":"Yes","rate_group":"Standard Equipment",
    }
    pricing={
        "currency":"GBP","pricing_status":"Provisional",
        "rates":[{"group":"Standard Equipment","standard":0.03,
                  "minimum":0.025,"uplift":0,"status":"Active"}],
        "tiers":{"Silver":0.8,"Gold":1.0,"Platinum":1.3},
        "console_rules":[{"name":"No Console / N/A","multiplier":1,"uplift":0}],
    }
    august={
        "source_file":quote_rrp_priority.MASTER_FILE,
        "source_date":quote_rrp_priority.MASTER_DATE,
        "source_sha256":quote_rrp_priority.MASTER_ORIGINAL_SHA256,
        "rows":[{
            "sku":"FICTIONAL-EXACT","rrp":3000,
            "name":"Fictional Treadmill","console":"No Console / N/A",
            "sheet":"Fictional Source","row":22,"rrp_column":"List Price",
        }],
    }
    content={
        "catalog.json":json.dumps([product]).encode(),
        "configs.json":json.dumps([config]).encode(),
        "pricing.json":json.dumps(pricing).encode(),
        "rrp_2026_source.json.gz":gzip.compress(json.dumps(august).encode()),
    }
    file=io.BytesIO()
    with zipfile.ZipFile(file,"w") as archive:
        for name,data in content.items():
            archive.writestr("data/"+name,data)
    return file.getvalue()


def _approve(token):
    return src.ActivateSource(
        token=token,
        approval_reference="ORIGINAL-V10-IT-REVIEW",
        reason="Verified source file identities against original repo",
        confirm_original_v10_files=True,
        confirm_august_master_source=True,
    )


def test_admin_zip_intake_activates_private_v10_and_august_sources(tmp_path,monkeypatch):
    path=_setup(tmp_path,monkeypatch)
    binary=_bundle()
    preview=asyncio.run(src.preview_zip(
        UploadFile(file=io.BytesIO(binary),filename="four-original-files.zip")
    ))
    assert preview["counts"]["catalogue_rows"]==1
    assert preview["counts"]["august_list_price_rows"]==1
    assert preview["pricing_status"]=="Provisional"
    assert preview["customer_quote_issue_enabled"] is False
    activated=src.activate_source(_approve(preview["token"]))
    assert activated["active"] is True
    assert activated["version"]==1
    status=src.source_status()
    assert status["active"]["counts"]["service_configs"]==1
    original,statuses,rules,hashes=quote_pricing.source_snapshot()
    assert original[0]["sku"]=="FICTIONAL-EXACT"
    assert rules["tiers"]["Gold"]==1.0
    assert hashes["pricing"]==preview["hashes"]["pricing"]
    assert quote_pricing.source_manifest_status(hashes)["matches"] is True
    master=quote_rrp_priority.source_snapshot()
    assert master["rows"][0]["rrp"]==3000
    assert master["snapshot_sha256"]==preview["hashes"]["august_2026_rrp"]
    assert master["source_file_sha256"]==quote_rrp_priority.MASTER_ORIGINAL_SHA256
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM quote_source_bundles").fetchone()[0]==1


def test_source_zip_rejects_extra_customer_files_and_unsafe_paths():
    good=_bundle()
    assert src.inspect_bundle(good)["counts"]["service_configs"]==1
    with zipfile.ZipFile(io.BytesIO(good)) as archive:
        archive_files={name:archive.read(name) for name in archive.namelist()}
    file=io.BytesIO()
    with zipfile.ZipFile(file,"w") as archive:
        for name,contents in archive_files.items():
            archive.writestr(name,contents)
        archive.writestr("customer-list.csv",b"private data")
    with pytest.raises(HTTPException) as error:
        src.inspect_bundle(file.getvalue())
    assert error.value.status_code==422
    file=io.BytesIO()
    with zipfile.ZipFile(file,"w") as archive:
        for name,contents in archive_files.items():
            if name.endswith("catalog.json"):
                name="../catalog.json"
            archive.writestr(name,contents)
    with pytest.raises(HTTPException) as error:
        src.inspect_bundle(file.getvalue())
    assert error.value.status_code==422


def test_modified_original_file_invalidates_staged_source_hash(tmp_path,monkeypatch):
    path=_setup(tmp_path,monkeypatch)
    review=asyncio.run(src.preview_zip(
        UploadFile(file=io.BytesIO(_bundle()),filename="v10.zip")
    ))
    src.activate_source(_approve(review["token"]))
    with sqlite3.connect(path) as db:
        db.execute("UPDATE quote_source_bundles SET payload=? WHERE active=1",
                   (b"tampered-ZIP-content",))
    with pytest.raises(HTTPException) as err:
        src.active_source()
    assert err.value.status_code==503


def test_concurrent_admin_previews_and_double_activation_are_blocked(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    async def preview(payload):
        return await src.preview_zip(UploadFile(
            file=io.BytesIO(payload),filename="original-sources.zip"
        ))
    first=asyncio.run(preview(_bundle()))
    second=asyncio.run(preview(_bundle(changed=True)))
    src.activate_source(_approve(first["token"]))
    with pytest.raises(HTTPException) as error:
        src.activate_source(_approve(second["token"]))
    assert error.value.status_code==409
    with pytest.raises(HTTPException) as error:
        src.activate_source(_approve(first["token"]))
    assert error.value.status_code==404


def test_original_source_refresh_disables_commercial_issuance(tmp_path,monkeypatch):
    from app import quote_commercial_setup as setup
    db,_=_setup(tmp_path,monkeypatch)
    first=asyncio.run(src.preview_zip(UploadFile(
        file=io.BytesIO(_bundle()),filename="v10.zip"
    )))
    src.activate_source(_approve(first["token"]))
    monkeypatch.setattr(setup,"connect",src.connect)
    with db() as con:
        setup._schema(con)
        enabled=json.dumps({"enabled":True},sort_keys=True).encode()
        con.execute(
            "INSERT INTO smartquote_commercial_settings "
            "(kind,payload,sha256,revision,approval_reference,reason,"
            "approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?)",
            ("issuance",enabled,hashlib.sha256(enabled).hexdigest(),1,
             "TEST-RELEASE","Synthetic source","test-director","2026-11-03"),
        )
        con.commit()
    second=asyncio.run(src.preview_zip(UploadFile(
        file=io.BytesIO(_bundle(changed=True)),filename="v10-new.zip"
    )))
    src.activate_source(_approve(second["token"]))
    assert setup.enabled() is False
    assert src.source_status()["active"]["id"]==2
    audit=setup.commercial_audit()["items"]
    assert any(row["kind"]=="issuance" and
               "source" in row["reason"].lower() for row in audit)


def test_coordinator_must_not_import_potentially_confidential_v10_sources(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    monkeypatch.setattr(src.pilot_access,"current_role",lambda:"Coordinator")
    with pytest.raises(HTTPException) as err:
        asyncio.run(src.preview_zip(UploadFile(
            file=io.BytesIO(_bundle()),filename="v10.zip"
        )))
    assert err.value.status_code==403
    with pytest.raises(HTTPException) as err:
        src.source_status()
    assert err.value.status_code==403
