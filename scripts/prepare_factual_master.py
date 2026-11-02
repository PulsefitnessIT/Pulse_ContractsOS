"""Create a NEW protected Contracts OS database from a verified Excel Master.

IT-only operation. Never uploads confidential rows to GitHub and NEVER merges or
overwrites an existing database. Existing staff-edited runtimes must instead go
through a separate approved, audited reconciliation and backup process.

Example:
  python scripts/prepare_factual_master.py --source /secure/master.xlsx \
    --destination /secure/new-contracts-snapshot --approved-current-master
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def stage(source, destination, *, explicitly_approved=False):
    if not explicitly_approved:
        raise ValueError("IT must explicitly confirm the Excel file is the approved current Master.")
    source = Path(source).expanduser().resolve(strict=True)
    target = Path(destination).expanduser().absolute()
    if not source.is_file() or source.suffix.lower() != ".xlsx":
        raise ValueError("Provide the original approved .xlsx Maintenance Master.")
    if target.exists() or target.is_symlink():
        raise ValueError("Destination already exists; live or pilot data must never be overwritten.")
    if not target.parent.is_dir():
        raise ValueError("Create a restricted destination parent directory first.")
    if ROOT == target or ROOT in target.parents:
        raise ValueError("Factual customer datasets must be staged outside the source repository.")
    if source == target or target in source.parents:
        raise ValueError("Source and destination must be distinct private locations.")

    # Avoid creating any replacement DB if the supplied file is invalid.
    from app.data_readiness import workbook_check
    checked = workbook_check(source)
    if not checked["valid"]:
        raise ValueError("Master worksheet order/layout mismatch: " + "; ".join(checked["issues"]))

    # A temporary directory in the target filesystem permits a single rename
    # only after a complete validated bootstrap and recorded file fingerprint.
    with tempfile.TemporaryDirectory(prefix=".pulse-source-stage-", dir=target.parent) as temp:
        fresh = Path(temp) / "verified_master"
        fresh.mkdir(mode=0o700)
        shutil.copyfile(source, fresh / "approved_master.xlsx")
        os.chmod(fresh / "approved_master.xlsx", 0o600)

        os.environ["PULSE_DATA_DIR"] = str(fresh)
        from app import store
        from app.source_integrity import source_audit
        if Path(store.DB).resolve() != (fresh / "contracts.sqlite3").resolve():
            raise RuntimeError("Contracts OS persistence already initialised for a different runtime.")
        report = source_audit(fresh / "approved_master.xlsx")
        store.init_db()
        with sqlite3.connect(fresh / "contracts.sqlite3") as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            counts = dict(db.execute("SELECT status,COUNT(*) FROM contracts GROUP BY status"))
            load = db.execute(
                "SELECT sha256,source_rows_active,source_rows_expired "
                "FROM master_source_loads ORDER BY id DESC LIMIT 1"
            ).fetchone()
            missing_current = 0
            for (payload,) in db.execute(
                "SELECT fields FROM contracts WHERE status='Active'"
            ):
                fields = json.loads(payload)
                if not str(fields.get("Contract amount (£)") or "").strip():
                    missing_current += 1
        expected_active = report["registers"]["Maintenance Database"]["populated_site_rows"]
        expected_expired = report["registers"]["Expired"]["populated_site_rows"]
        if (integrity != "ok" or counts.get("Active") != expected_active
            or counts.get("Expired") != expected_expired
            or not load or load[0] != report["workbook_sha256"]
            or load[1] != expected_active or load[2] != expected_expired
            or missing_current !=
                report["registers"]["Maintenance Database"]["amounts_as_recorded"]["missing"]):
            raise ValueError("Factual Master import failed source/database reconciliation.")

        # Only aggregate provenance is written. Customer/contract details stay
        # solely in the restricted workbook and SQLite data file.
        summary = {
            "workbook_sha256": report["workbook_sha256"],
            "register_records_active": expected_active,
            "register_records_expired": expected_expired,
            "missing_current_contract_amounts": missing_current,
            "repeated_source_id_rows": report["source_id_duplicates"]["extra_duplicate_rows"],
            "source": "User-provided approved Maintenance Master",
            "not_erp_reconciled": True,
            "commercial_amounts_not_imputed": True,
            "safe_to_merge_into_existing_db": False,
        }
        (fresh / "master_source_manifest.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        for file in fresh.iterdir():
            if file.is_file():
                os.chmod(file, 0o600)
        os.chmod(fresh, 0o700)
        if target.exists() or target.is_symlink():
            raise ValueError("Destination appeared during staging; refusing to overwrite.")
        fresh.rename(target)
        return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="IT-approved current eight-sheet Excel workbook")
    p.add_argument("--destination", required=True, help="New private folder outside GitHub")
    p.add_argument("--approved-current-master", action="store_true",
                   help="Explicit confirmation from Pulse contract-data owner")
    a = p.parse_args()
    result = stage(a.source, a.destination, explicitly_approved=a.approved_current_master)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
