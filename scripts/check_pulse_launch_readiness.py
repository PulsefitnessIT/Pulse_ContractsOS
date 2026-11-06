"""Read-only readiness gate for a *supervised* Pulse Fitness Contracts OS pilot.

Runs against a private server data directory. Does not stage, migrate, approve,
create accounts, publish data, or enable customer quotation issuance.

Usage (from the running staging container, with its configured environment):
  python scripts/check_pulse_launch_readiness.py --data-dir /app/pilot_data

To certify operational sign-offs (only AFTER independent evidence is retained):
  python scripts/check_pulse_launch_readiness.py --data-dir /app/pilot_data \
      --data-reconciled --restore-tested --https-and-roles-tested --coordinator-uat-passed

Machine status and counts are safe for internal IT; no names, serials,
customer prices, document contents or credentials are printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_readiness import assess_database
from app.deployment_guards import check_deployment_environment

MAX_PRICE_BYTES = 14 * 1024 * 1024


def _check_row(con, query, parameters=()):
    return con.execute(query, parameters).fetchone()


def _exists(con, name):
    return bool(_check_row(
        con, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ))


def _book_check(con):
    """Check the active Master snapshot without loading prices into output."""
    if not _exists(con, "unified_price_book_versions"):
        return {"passed": False, "detail": "Unified Master has not been activated"}
    row = _check_row(
        con,
        "SELECT revision,snapshot_sha256,rows_zlib FROM "
        "unified_price_book_versions WHERE active=1",
    )
    if row is None:
        return {"passed": False, "detail": "No active unified Master revision"}
    revision, expected, blob = row
    if not isinstance(blob, bytes):
        return {"passed": False, "detail": "Active price snapshot unavailable"}
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(blob, MAX_PRICE_BYTES + 1)
        if (len(raw) > MAX_PRICE_BYTES or not decoder.eof
                or decoder.unused_data or decoder.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != expected):
            raise ValueError("Snapshot hash/size mismatch")
        items = json.loads(raw)
        if not isinstance(items, dict) or len(items) > 60000:
            raise ValueError("Invalid snapshot rows")
    except (ValueError, TypeError, UnicodeError, zlib.error):
        return {"passed": False, "detail": "Active Master failed integrity verification"}
    usable = sum(
        type(row) is dict
        and row.get("status") == "REFERENCE"
        and type(row.get("price_pence")) is int
        and row["price_pence"] > 0
        for row in items.values()
    )
    return {
        "passed": bool(usable),
        "detail": (
            f"Active Master revision {revision}: {len(items)} source codes, "
            f"{usable} with positive reference prices; maintenance eligibility "
            "and tariffs are NOT implied"
        ),
        "revision": revision,
        "item_codes": len(items),
        "priced_reference_codes": usable,
    }


def _roles_check(con):
    if not _exists(con, "pilot_users"):
        return {"passed": False, "detail": "Named pilot users have not been provisioned"}
    rows = con.execute(
        "SELECT role,COUNT(*) FROM pilot_users WHERE disabled=0 GROUP BY role"
    ).fetchall()
    by_role = dict(rows)
    return {
        "passed": by_role.get("Admin", 0) >= 1 and by_role.get("Coordinator", 0) >= 1,
        "detail": (
            f"{by_role.get('Admin', 0)} active Admin and "
            f"{by_role.get('Coordinator', 0)} active Coordinator accounts; "
            "HTTPS login/permissions must still be exercised manually"
        ),
    }


def _backup_check(data_dir, now=None):
    folder = Path(data_dir) / "backups"
    existing = list(folder.glob("pulse_contracts_*.sqlite3"))
    latest = max((p.stat().st_mtime for p in existing if p.is_file()),
                 default=None)
    if latest is None:
        return {"passed": False, "detail": "No local SQLite backup found"}
    age_hours = max(0, ((now or dt.datetime.now(dt.timezone.utc)).timestamp()
                        - latest) / 3600)
    return {
        "passed": age_hours <= 24,
        "detail": (
            f"Most recent local backup {age_hours:.1f} hours old; "
            "an off-host restore test is still required"
        ),
    }


def assess_launch(data_dir, env=None, *,
                  data_reconciled=False, restore_tested=False,
                  https_and_roles_tested=False, coordinator_uat_passed=False):
    """No mutations; every gate has a specific human/technical meaning."""
    folder = Path(data_dir).expanduser().resolve()
    variables = dict(os.environ if env is None else env)
    variables["PULSE_DATA_DIR"] = str(folder)
    checks = {}

    try:
        profile = check_deployment_environment(variables)
        if profile["deployment_profile"] != "staging":
            raise ValueError("Supervised launch requires the staging profile")
        checks["server_security_profile"] = {
            "passed": True, "detail": "Protected staging profile verified"
        }
    except (RuntimeError, ValueError) as exc:
        checks["server_security_profile"] = {
            "passed": False, "detail": str(exc)
        }

    try:
        data = assess_database(
            folder / "contracts.sqlite3",
            folder / "approved_master.xlsx",
        )
        checks["private_contracts_data"] = {
            "passed": bool(data["ready_for_data_review"]
                           and data["contracts"]["active"] > 0),
            "detail": (
                f"{data['contracts']['active']} active, "
                f"{data['contracts']['expired']} expired contract records; "
                f"workbook/database review issues: {len(data['issues'])}. "
                "Counts are not independently certified contract totals."
            ),
            "readiness_issues": len(data["issues"]),
        }
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        checks["private_contracts_data"] = {
            "passed": False,
            "detail": "Approved private contract snapshot could not be inspected"
        }

    db_file = folder / "contracts.sqlite3"
    if db_file.is_file():
        try:
            uri = db_file.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=10) as con:
                con.execute("PRAGMA query_only=ON")
                if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Database check failed")
                checks["unified_master"] = _book_check(con)
                checks["named_staff_accounts"] = _roles_check(con)
        except (sqlite3.Error, OSError):
            checks["unified_master"] = {
                "passed": False, "detail": "Could not validate active unified Master"
            }
            checks["named_staff_accounts"] = {
                "passed": False, "detail": "Could not verify named staff accounts"
            }
    else:
        checks["unified_master"] = {
            "passed": False, "detail": "Private database missing"
        }
        checks["named_staff_accounts"] = {
            "passed": False, "detail": "Private database missing"
        }

    checks["local_backup"] = _backup_check(folder)
    approvals = (
        ("source_data_reconciled", data_reconciled,
         "Sign off workbook/database parity and recent coordinator updates"),
        ("off_host_restore_exercised", restore_tested,
         "Complete a protected off-host backup and successful test restore"),
        ("https_and_roles_tested", https_and_roles_tested,
         "Verify real HTTPS login, Coordinator/Viewer/Admin rights and logout"),
        ("coordinator_uat", coordinator_uat_passed,
         "Two coordinators complete invoice-to-internal-PDF acceptance and contract edits"),
    )
    for label, yes, description in approvals:
        checks[label] = {
            "passed": yes, "detail": (
                "Operator marked complete; evidence must be retained by IT"
                if yes else "PENDING: " + description
            ),
            "manual_attestation": True,
        }
    ready = all(item["passed"] for item in checks.values())
    return {
        "internal_pilot_ready": ready,
        "customer_quote_issuance_authorised": False,
        "production_certified": False,
        "checks": checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.getenv("PULSE_DATA_DIR"),
                        help="Private staging directory (required)")
    parser.add_argument("--json", action="store_true",
                        help="Aggregate/identity-free machine-readable status")
    parser.add_argument("--data-reconciled", action="store_true")
    parser.add_argument("--restore-tested", action="store_true")
    parser.add_argument("--https-and-roles-tested", action="store_true")
    parser.add_argument("--coordinator-uat-passed", action="store_true")
    args = parser.parse_args(argv)
    if not args.data_dir:
        parser.error("--data-dir or PULSE_DATA_DIR is required")
    result = assess_launch(
        args.data_dir,
        data_reconciled=args.data_reconciled,
        restore_tested=args.restore_tested,
        https_and_roles_tested=args.https_and_roles_tested,
        coordinator_uat_passed=args.coordinator_uat_passed,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for name, value in result["checks"].items():
            print(f"{'PASS' if value['passed'] else 'BLOCK'} "
                  f"{name}: {value['detail']}")
        print("INTERNAL PILOT:", "GO (supervised)" if result["internal_pilot_ready"]
              else "NO-GO")
        print("CUSTOMER ISSUE: separate commercial release, not granted here")
    return 0 if result["internal_pilot_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
