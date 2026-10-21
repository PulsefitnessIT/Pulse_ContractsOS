"""Stage an approved private Contracts OS snapshot outside GitHub/Docker images.

Usage:
  python scripts/stage_private_runtime.py --source /secure/approved-snapshot --destination /srv/contracts/pilot_data

The source directory must contain contracts.sqlite3 and approved_master.xlsx.
Optional equipment_catalogue.json and service_planner_source.json also stay private.
Never run this on an active destination: no existing files are overwritten.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.data_readiness import assess_database


def stage(source, destination):
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().absolute()
    required = ("contracts.sqlite3", "approved_master.xlsx")
    if not source.is_dir():
        raise ValueError("An approved, extracted private snapshot directory is required")
    if any(not (source / name).is_file() for name in required):
        raise ValueError("Snapshot must contain contracts.sqlite3 and approved_master.xlsx")
    if destination.exists() or destination.is_symlink():
        raise ValueError("The destination already exists. Refusing to overwrite live pilot data")
    if not destination.parent.is_dir():
        raise ValueError("Create the destination's parent folder first with restricted permissions")
    if destination.parent.resolve() == source or source in destination.parents:
        raise ValueError("Destination must be separate from the source snapshot")
    preflight = assess_database(source / required[0], source / required[1])
    if not preflight["ready_for_data_review"]:
        raise ValueError("Snapshot failed validation: " + "; ".join(preflight["issues"]))
    # SQLite backup creates a transactionally consistent copy, including WAL changes.
    # A raw copy of an open *.sqlite3 file can lose the latest writes.
    with tempfile.TemporaryDirectory(prefix=".pulse-contracts-stage-", dir=destination.parent) as tmp:
        stage_dir = Path(tmp) / "private_runtime"
        stage_dir.mkdir(mode=0o700)
        src_uri = (source / "contracts.sqlite3").as_uri() + "?mode=ro"
        with sqlite3.connect(src_uri, uri=True, timeout=20) as src:
            with sqlite3.connect(stage_dir / "contracts.sqlite3") as target:
                src.backup(target)
        shutil.copyfile(source / "approved_master.xlsx", stage_dir / "approved_master.xlsx")
        for optional in ("equipment_catalogue.json", "service_planner_source.json"):
            extra = source / optional
            if extra.is_file():
                # Check JSON syntax before copying optional reference data.
                import json
                json.loads(extra.read_text(encoding="utf-8"))
                shutil.copyfile(extra, stage_dir / optional)
        for path in stage_dir.iterdir():
            os.chmod(path, 0o600)
        result = assess_database(stage_dir / "contracts.sqlite3", stage_dir / "approved_master.xlsx")
        if not result["ready_for_data_review"]:
            raise ValueError("Staged snapshot failed validation: " + "; ".join(result["issues"]))
        # Fail closed if the source changed in ways that affect key record counts.
        if result["contracts"] != preflight["contracts"]:
            raise ValueError("Contract counts changed while preparing the snapshot; try again")
        if destination.exists():
            raise ValueError("Destination was created concurrently; refusing to overwrite")
        stage_dir.rename(destination)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Approved private snapshot directory, not a GitHub folder")
    parser.add_argument("--destination", required=True, help="New, non-existing private runtime folder")
    options = parser.parse_args()
    try:
        report = stage(options.source, options.destination)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, "DATA STAGING FAILED: " + str(error) + "\n")
    print("Private snapshot staged. Active:", report["contracts"]["active"],
          "Expired:", report["contracts"]["expired"])
    print("Recorded contract amount coverage:",
          str(report["financial_completeness"]["recorded_percent"]) + "%")
    print("Customer and financial data remain outside GitHub. Review issues before pilot use.")
    for issue in report["issues"]:
        print("REVIEW:", issue)


if __name__ == "__main__":
    main()
