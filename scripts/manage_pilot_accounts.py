"""IT-only local staff-access operations for protected Contracts OS staging.

Run inside the server container using an authorised operating-system account.
Never pass passwords on the command line, in Docker Compose files or in chat.
This is a transitional pilot tool, not a replacement for central SSO/MFA.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.pilot_access import (
    DB, ROLES, configure_users, disable_user, provision_user,
    revoke_user_sessions,
)


def _existing_role(username):
    with sqlite3.connect(DB,timeout=20) as db:
        found=db.execute(
            "SELECT role FROM pilot_users WHERE username=?",
            (username.strip().casefold(),)
        ).fetchone()
    if not found:
        raise ValueError("Pilot account not found")
    return found[0]


def _status():
    with sqlite3.connect(DB,timeout=20) as db:
        rows=db.execute(
            "SELECT username,role,disabled FROM pilot_users ORDER BY username"
        ).fetchall()
    return [{"username":u,"role":r,"disabled":bool(d)} for u,r,d in rows]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    operations=parser.add_subparsers(dest="operation",required=True)
    operations.add_parser("list",help="List pilot account names and roles only")
    for operation in ("create","reset-password","disable","revoke-sessions"):
        cmd=operations.add_parser(operation)
        cmd.add_argument("username",help="Named individual staff account")
        if operation=="create":
            cmd.add_argument("--role",choices=sorted(ROLES),default="Coordinator")
    args=parser.parse_args(argv)
    if os.getenv("PULSE_PILOT_MODE")!="1":
        parser.error("Only use this tool in an explicitly protected pilot runtime.")
    if not Path(DB).is_file():
        parser.error("Private pilot database is missing. Do not create an empty one.")
    configure_users()
    try:
        if args.operation=="list":
            result={"accounts":_status(),"password_hashes_exposed":False}
        elif args.operation in ("create","reset-password"):
            role=args.role if args.operation=="create" else _existing_role(args.username)
            passwd=getpass.getpass("New password (minimum 12 characters): ")
            confirm=getpass.getpass("Confirm new password: ")
            if passwd!=confirm:
                raise ValueError("Password confirmation did not match")
            if args.operation=="create":
                with sqlite3.connect(DB,timeout=20) as db:
                    existing=db.execute(
                        "SELECT 1 FROM pilot_users WHERE username=?",
                        (args.username.strip().casefold(),)
                    ).fetchone()
                if existing:
                    raise ValueError("Existing account: use reset-password, not create")
            result={"username":provision_user(args.username,passwd,role),
                    "operation":args.operation,
                    "old_sessions_revoked":True,"role":role}
        elif args.operation=="disable":
            result={"username":disable_user(args.username),
                    "operation":"disabled","all_sessions_revoked":True}
        else:
            result={"username":args.username.strip().casefold(),
                    "revoked_session_count":revoke_user_sessions(args.username)}
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
