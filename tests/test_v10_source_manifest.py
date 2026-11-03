"""IT-only source manifest test using fictional SKUs, never real company tariffs."""
import json

import pytest

from app import quote_pricing
from scripts.pin_smartquote_v10_sources import create


def fictional_root(tmp_path):
    source=tmp_path/"source"
    data=source/"data"
    data.mkdir(parents=True)
    (source/"engine.py").write_text("# fictional engine fixture")
    (data/"catalog.json").write_text(json.dumps([
        {"sku":"TEST-ONE","rrp":500,"service_key":"TEST | N/A"}
    ]))
    (data/"configs.json").write_text(json.dumps([
        {"key":"TEST | N/A","rate_group":"Standard Equipment","eligible":"Yes"}
    ]))
    (data/"pricing.json").write_text(json.dumps({
        "pricing_status":"Provisional; not approved", "currency":"GBP",
        "rates":[{"group":"Standard Equipment","standard":.03,"minimum":.025}],
        "tiers":{"Silver":.8,"Gold":1,"Platinum":1.3},
        "console_rules":[{"name":"N/A","multiplier":1,"uplift":0}],
    }))
    return source


def test_manifest_is_pinned_to_exact_files_and_never_claims_approval(tmp_path,monkeypatch):
    root=fictional_root(tmp_path)
    output=tmp_path/"private-approved-source-identity.json"
    result=create(root,output,"Fictional source custodian","2026-11-03",
                  approved_source_snapshot=True)
    saved=json.loads(output.read_text())
    assert result["source_counts"]=={"catalog":1,"configs":1,"pricing":5}
    assert result["commercial_rates_approved"] is False
    assert saved["commercial_rate_approval_recorded"] is False
    assert len(saved["sha256"]["catalog"])==64
    assert "rrp" not in output.read_text().lower()
    monkeypatch.setenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST",str(output))
    result=quote_pricing.source_manifest_status(saved["sha256"])
    assert result["pinned"] is True
    assert result["commercially_approved"] is False


def test_missing_or_overwrite_confirmation_refuses_changes(tmp_path):
    root=fictional_root(tmp_path)
    output=tmp_path/"source-manifest.json"
    with pytest.raises(ValueError):
        create(root,output,"Fictional data custodian","2026-11-03")
    assert not output.exists()
    create(root,output,"Fictional data custodian","2026-11-03",
           approved_source_snapshot=True)
    with pytest.raises(ValueError):
        create(root,output,"Fictional data custodian","2026-11-03",
               approved_source_snapshot=True)


def test_missing_catalogue_blocks_private_source_manifest(tmp_path):
    root=fictional_root(tmp_path)
    (root/"data"/"catalog.json").write_text("[]")
    with pytest.raises(ValueError,match="empty"):
        create(root,tmp_path/"new.json","Fictional owner","2026-11-03",
               approved_source_snapshot=True)
