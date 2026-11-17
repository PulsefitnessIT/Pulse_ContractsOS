"""IT-only source manifest test using fictional SKUs, never real company tariffs."""
import gzip
import json

import pytest
from fastapi import HTTPException

from app import quote_reconciliation

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


def test_optional_legacy_and_compressed_history_sources_are_hash_pinned(tmp_path, monkeypatch):
    root = fictional_root(tmp_path)
    data = root / "data"
    legacy = [{"old_code": "OLD-001", "new_sku": "TEST-ONE"}]
    history = {"records": {"OLD-001": {"model": "Fictional model"}}, "aliases": {}}
    (data / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    (data / "historical_catalogue_index.json.gz").write_bytes(
        gzip.compress(json.dumps(history).encode("utf-8"))
    )
    manifest_path = tmp_path / "protected.json"
    result = create(root, manifest_path, "Fictional custodian", "2026-11-03",
                    approved_source_snapshot=True)
    assert result["source_counts"]["legacy_crosswalk"] == 1
    assert result["source_counts"]["historical_identity"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert set(("legacy_crosswalk", "historical_identity")) <= set(manifest["sha256"])
    assert "OLD-001" not in manifest_path.read_text(encoding="utf-8")

    monkeypatch.setenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST", str(manifest_path))
    monkeypatch.setenv("PULSE_SMARTQUOTE_LEGACY_JSON", str(data / "legacy.json"))
    monkeypatch.setenv(
        "PULSE_SMARTQUOTE_HISTORICAL_INDEX",
        str(data / "historical_catalogue_index.json.gz")
    )
    catalogue = json.loads((data / "catalog.json").read_text())
    configs = json.loads((data / "configs.json").read_text())
    pricing = json.loads((data / "pricing.json").read_text())
    monkeypatch.setattr(quote_reconciliation, "source_snapshot",
                        lambda: (catalogue, configs, pricing, {
                            key: manifest["sha256"][key]
                            for key in ("catalog", "configs", "pricing")
                        }))
    report = quote_reconciliation.source_report()
    assert report["summary"]["legacy_source_rows"] == 1
    assert report["summary"]["historical_source_variants"] == 1

    # Even valid JSON edits to the private legacy source require re-pinning.
    (data / "legacy.json").write_text(json.dumps(
        [{"old_code": "OLD-001", "new_sku": "TEST-DIFFERENT"}]
    ))
    with pytest.raises(HTTPException) as err:
        quote_reconciliation.source_report()
    assert err.value.status_code == 503
    # Historical lookup must not bypass a pinned reconciliation source check.
    monkeypatch.setattr(quote_reconciliation, "actor", lambda: "fictional-staff")
    with pytest.raises(HTTPException) as err:
        quote_reconciliation.historical_search("OLD-001", 10)
    assert err.value.status_code == 503


def test_pinned_legacy_source_cannot_disappear_without_failure(tmp_path, monkeypatch):
    root = fictional_root(tmp_path)
    data = root / "data"
    (data / "legacy.json").write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "protected.json"
    create(root, manifest_path, "Fictional custodian", "2026-11-03",
           approved_source_snapshot=True)
    hashes = json.loads(manifest_path.read_text())["sha256"]
    monkeypatch.setenv("PULSE_SMARTQUOTE_SOURCE_MANIFEST", str(manifest_path))
    with pytest.raises(HTTPException) as err:
        quote_pricing.source_manifest_status({
            **{key: hashes[key] for key in ("catalog", "configs", "pricing")},
            "legacy_crosswalk": None,
            "historical_identity": None,
        })
    assert err.value.status_code == 503


def test_refuses_dual_original_history_sources(tmp_path):
    root = fictional_root(tmp_path)
    data = root / "data"
    history = json.dumps({"records": {}, "aliases": {}})
    (data / "historical_catalogue_index.json").write_text(history)
    (data / "historical_catalogue_index.json.gz").write_bytes(
        gzip.compress(history.encode("utf-8"))
    )
    with pytest.raises(ValueError, match="Two original history"):
        create(root, tmp_path / "unwritten.json", "Fictional custodian",
               "2026-11-03", approved_source_snapshot=True)


def test_august_2026_sanitized_master_extract_is_privately_pinned(tmp_path):
    from app.quote_rrp_priority import MASTER_DATE, MASTER_FILE, MASTER_ORIGINAL_SHA256
    root = fictional_root(tmp_path)
    payload = {
        "source_file": MASTER_FILE, "source_date": MASTER_DATE,
        "source_sha256": MASTER_ORIGINAL_SHA256,
        "rows": [{"sku": "SYNTHETIC-SKU", "name": "Fictional product",
                  "console": "No Console / N/A", "rrp": "100.00",
                  "sheet": "Example", "row": 5, "rrp_column": "List Price"}],
    }
    source = root / "data" / "rrp_2026_source.json.gz"
    source.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8")))
    manifest = tmp_path / "august-snapshot-manifest.json"
    outcome = create(root, manifest, "Fictional owner", "2026-11-03",
                     approved_source_snapshot=True)
    assert outcome["source_counts"]["august_2026_rrp"] == 1
    saved = json.loads(manifest.read_text())
    assert len(saved["sha256"]["august_2026_rrp"]) == 64
    assert "SYNTHETIC-SKU" not in manifest.read_text()
    assert "100.00" not in manifest.read_text()


def test_manifest_rejects_unverified_august_master_metadata(tmp_path):
    from app.quote_rrp_priority import MASTER_FILE, MASTER_DATE
    root = fictional_root(tmp_path)
    payload = {
        "source_file": MASTER_FILE, "source_date": MASTER_DATE,
        "source_sha256": "0" * 64, "rows": [{"sku": "FICTIONAL", "rrp": 1}],
    }
    source = root / "data" / "rrp_2026_source.json.gz"
    source.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8")))
    with pytest.raises(ValueError, match="August 2026"):
        create(root, tmp_path / "should-not-exist.json", "Fictional owner",
               "2026-11-03", approved_source_snapshot=True)
