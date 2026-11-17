"""Read-only, privacy-safe Contracts OS server staging preflight.

Run on the server inside the configured container. This command inspects
required files and health, but never imports customer details, creates a
database, alters a workbook or generates an account.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.deployment_guards import check_deployment_environment
from app.data_readiness import workbook_check


def check(path=None,env=None):
    env=os.environ if env is None else env
    checks=[]
    def mark(name,ok,description):
        checks.append({"check":name,"passed":bool(ok),"detail":description})
    try:
        profile=check_deployment_environment(env)["deployment_profile"]
        mark("remote_hosting_guard",profile=="staging",
             "Hosted staging must have secure cookies, auth and a private HTTPS origin.")
    except RuntimeError:
        profile="invalid"
        mark("remote_hosting_guard",False,
             "Server staging configuration is missing or insecure; review deployment setup.")
    data=Path(path or env.get("PULSE_DATA_DIR") or "/nonexistent-pulse-data")
    db=data/"contracts.sqlite3"
    master=data/"approved_master.xlsx"
    mark("private_database_present",db.is_file(),
         "A private independently staged SQLite database is required.")
    mark("approved_master_present",master.is_file(),
         "An independently approved working Master snapshot is required.")
    if db.is_file():
        try:
            uri=db.resolve().as_uri()+"?mode=ro"
            with sqlite3.connect(uri,uri=True,timeout=5) as con:
                check_result=con.execute("PRAGMA quick_check").fetchone()[0]
                rows=con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
                admins=con.execute(
                    "SELECT COUNT(*) FROM pilot_users WHERE role='Admin' AND disabled=0"
                ).fetchone()[0]
            mark("database_integrity",check_result=="ok",
                 "Read-only SQLite quick_check on the protected database.")
            mark("record_source_bootstrapped",rows>0,
                 "Database must contain reviewed source-backed records, not an empty demo.")
            mark("pilot_administrator_exists",admins>=1,
                 "At least one active pilot administrator must be provisioned.")
        except (sqlite3.Error,OSError):
            mark("database_integrity",False,
                 "Could not verify a readable, structurally valid pilot database.")
            mark("record_source_bootstrapped",False,"Source records could not be checked.")
            mark("pilot_administrator_exists",False,
                 "Pilot administrator table could not be checked.")
    else:
        for name in ("database_integrity","record_source_bootstrapped","pilot_administrator_exists"):
            mark(name,False,"Private database has not been provisioned.")
    try:
        workbook=workbook_check(master)
        mark("source_workbook_layout",workbook.get("valid",False),
             "Must match the approved eight- or ten-tab workbook profile.")
        workbook_profile=workbook.get("profile")
    except (ValueError,RuntimeError,OSError):
        workbook_profile=None
        mark("source_workbook_layout",False,"Could not verify Excel format.")
    folder=data/"backups"
    snapshots=list(folder.glob("pulse_contracts_*.sqlite3")) if folder.is_dir() else []
    recent=[f for f in snapshots if f.is_file()
            and dt.datetime.now(dt.timezone.utc).timestamp()-f.stat().st_mtime<48*3600]
    mark("recent_local_backup",bool(recent),
         "At least one local SQLite backup within 48 hours; off-site backup not verified.")
    # These checks demand independent real-world evidence; don't turn them
    # green merely because someone set a variable.
    release_blockers=[
        "Independent HTTPS certificate, reverse-proxy and firewall tests",
        "Central identity/MFA, permission review and session revocation",
        "Encrypted off-host backup plus documented full restore drill",
        "Excel/MOD register reconciliation and coordinator UAT sign-off",
        "Security assessment, dependency pinning/scanning and rollback drill",
        "Approved commercial SmartQuote tariffs and issued-PDF parity",
    ]
    return {
        "deployment_profile":profile,
        "staging_checks_passed":sum(1 for x in checks if x["passed"]),
        "staging_checks_total":len(checks),
        "eligible_for_supervised_staging":profile=="staging" and all(x["passed"] for x in checks),
        "workbook_profile":workbook_profile,
        "ready_for_unrestricted_production":False,
        "pending_independent_production_gates":release_blockers,
        "checks":checks,
        "customer_data_in_report":False,
    }


if __name__=="__main__":
    result=check()
    print(json.dumps(result,indent=2))
    sys.exit(0 if result["eligible_for_supervised_staging"] else 2)
