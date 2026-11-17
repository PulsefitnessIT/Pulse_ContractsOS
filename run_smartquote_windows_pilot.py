"""Windows loopback-only, authenticated Contracts OS / SmartQuote pilot runner.

This is a *personal workstation pilot*, not a shared server or commercial
production deployment. Source code/executable contains NO customer data,
maintenance master, quote approvals, passwords or tariff sign-offs.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import secrets
import sqlite3
import sys

PORT = 18080


def _application_folder():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _private_folder():
    return _application_folder() / "private_runtime"


def _configure():
    folder = _private_folder()
    # Deliberately force loopback-only development with verified pilot login.
    # Secure-only cookies are only appropriate when IT supplies TLS: local
    # http://127.0.0.1 cannot receive a Secure cookie in all browsers.
    os.environ["PULSE_DATA_DIR"] = str(folder)
    os.environ["PULSE_PILOT_MODE"] = "1"
    os.environ["PULSE_DEPLOYMENT_ENV"] = "development"
    os.environ["PULSE_COOKIE_SECURE"] = "0"
    os.environ["PULSE_AUTO_BACKUP"] = "1"
    return folder


def _must_have_approved_master():
    folder = _private_folder()
    if not (folder / "approved_master.xlsx").is_file():
        raise RuntimeError(
            "No approved source-backed Master. Run --bootstrap-master first."
        )
    if not (folder / "contracts.sqlite3").is_file():
        raise RuntimeError(
            "Private contract database is missing. Run --bootstrap-master first."
        )
    return folder


def bootstrap(source: str):
    target = _private_folder()
    if target.exists() or target.is_symlink():
        raise RuntimeError(
            "Private runtime already exists. Refusing to erase or rebuild "
            "existing customer/quote data. Ask IT to reconcile a new Master."
        )
    path = Path(source.strip().strip('"')).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise ValueError("Choose the current authorised Maintenance Master .xlsx.")
    print("THIS CREATES A NEW LOCAL PILOT. NO EXISTING DATABASE IS ALTERED.")
    print("Source:", path.name)
    confirm = input(
        "Confirm this is the APPROVED current Maintenance Master "
        "and source snapshot [type APPROVED]: "
    ).strip()
    if confirm != "APPROVED":
        raise RuntimeError("Not approved. No private runtime was created.")
    _configure()
    from scripts.prepare_factual_master import stage
    result = stage(path, target, explicitly_approved=True)
    print(
        "Bootstrapped", result["register_records_active"],
        "active and", result["register_records_expired"],
        "historic source-register rows."
    )
    print(
        "Important: these workbook records and amounts are NOT independently "
        "reconciled to Sage/Sicon, and are not approvals of current contract value."
    )
    return result


def has_admin():
    folder = _must_have_approved_master()
    with sqlite3.connect(folder / "contracts.sqlite3", timeout=10) as db:
        try:
            count = db.execute(
                "SELECT COUNT(*) FROM pilot_users WHERE role='Admin' AND disabled=0"
            ).fetchone()[0]
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            return False
    return count > 0


def create_admin():
    _must_have_approved_master()
    _configure()
    from app.pilot_access import provision_user
    print("Create a named local SmartQuote/Contracts OS pilot Administrator.")
    name = input("User login (minimum 3 characters): ").strip()
    pwd = getpass.getpass("Password (at least 12 characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if pwd != confirmation:
        raise ValueError("Passwords do not match. No Administrator was added.")
    actor = provision_user(name, pwd, "Admin")
    print("Administrator account created:", actor)
    print(
        "Your personal password is not stored in a launcher script. "
        "Use this named login when opening the pilot."
    )


def _session_secret():
    folder = _must_have_approved_master()
    secret_file = folder / ".private_session_secret"
    if secret_file.is_symlink():
        raise RuntimeError("Refusing to use a symlink as pilot signing secret.")
    if secret_file.exists():
        if not secret_file.is_file():
            raise RuntimeError("Signing secret is not a private file.")
        saved = secret_file.read_text(encoding="ascii").strip()
        if len(saved) < 48:
            raise RuntimeError("Existing signing secret is invalid; do not overwrite.")
        return saved
    # Avoid replacing another process's secret if two launchers race.
    key = secrets.token_urlsafe(72)
    try:
        with secret_file.open("x", encoding="ascii") as file:
            file.write(key + "\n")
    except FileExistsError:
        return _session_secret()
    return key


def serve():
    _configure()
    _must_have_approved_master()
    if not has_admin():
        raise RuntimeError("Create a named pilot Admin before starting.")
    os.environ["PULSE_SESSION_SECRET"] = _session_secret()
    # Uvicorn must see PULSE_DATA_DIR and the secret before importing app.main.
    import uvicorn
    print("SmartQuote / Contracts OS local pilot")
    print(f"Open: http://127.0.0.1:{PORT}/")
    print("Available ONLY on this computer; do not publish this port.")
    print("Original V10 and Sage source activation still require Admin review.")
    print("Real customer issuance remains disabled until tariff/terms sign-off.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT,
                workers=1, access_log=False, reload=False)


def self_test():
    _configure()
    from app import quote_pricing, quote_rrp_priority
    import fitz
    source_dir = Path(__file__).resolve().parent / "app" / "static"
    if not (source_dir / "index.html").is_file():
        raise RuntimeError("Web interface not bundled in Windows executable.")
    assert quote_pricing._master_console_identity(
        {"name": "Fictional Strength Unit", "console": "No Console / N/A"},
        {"master_name": "Fictional Strength Unit",
         "master_console": "Console not stated"},
    )
    assert quote_rrp_priority.MASTER_DATE == "2026-08-24"
    assert hasattr(fitz, "open")
    print("Windows SmartQuote pilot components verified. No real data loaded.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bootstrap-master", metavar="SOURCE.xlsx")
    group.add_argument("--create-admin", action="store_true")
    group.add_argument("--has-admin", action="store_true")
    group.add_argument("--serve", action="store_true")
    group.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.bootstrap_master:
            bootstrap(args.bootstrap_master)
        elif args.create_admin:
            create_admin()
        elif args.has_admin:
            return 0 if has_admin() else 1
        elif args.serve:
            serve()
        else:
            self_test()
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        print("SmartQuote pilot setup error:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
