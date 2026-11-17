"""Safety tests for the read-only operational pilot-launch gate.

The fixtures contain no real staff, customers, equipment prices, or licences.
"""
import hashlib
import json
import sqlite3
import zlib

import pytest

from scripts import check_pulse_launch_readiness as gate


@pytest.fixture
def environment(tmp_path, monkeypatch):
    db_path = tmp_path / "contracts.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE unified_price_book_versions("
            "revision INTEGER, snapshot_sha256 TEXT, rows_zlib BLOB, active INTEGER)"
        )
        data = json.dumps({
            "DEMO-MACHINE": {
                "price_pence": 32100,
                "status": "REFERENCE",
                "group": "Cardiovascular Equipment"
            }
        }, sort_keys=True, separators=(",", ":")).encode()
        db.execute(
            "INSERT INTO unified_price_book_versions VALUES(?,?,?,1)",
            (1, hashlib.sha256(data).hexdigest(), zlib.compress(data)),
        )
        db.execute(
            "CREATE TABLE pilot_users(username TEXT,role TEXT,disabled INTEGER)"
        )
        db.execute("INSERT INTO pilot_users VALUES('fake-admin','Admin',0)")
        db.execute("INSERT INTO pilot_users VALUES('fake-coordinator','Coordinator',0)")
        backups = tmp_path / "backups"
        backups.mkdir()
        # sqlite3.backup must not run against this connection while its
        # own writes are uncommitted: it can otherwise retry forever.
        db.commit()
        dest = sqlite3.connect(backups / "pulse_contracts_20261106.sqlite3")
        try:
            db.backup(dest, pages=100)
        finally:
            dest.close()
    (tmp_path / "approved_master.xlsx").write_bytes(b"synthetic workbook")
    monkeypatch.setattr(gate, "assess_database", lambda db, workbook: {
        "ready_for_data_review": True,
        "contracts": {"active": 17, "expired": 2},
        "issues": [],
    })
    return tmp_path, {
        "PULSE_DEPLOYMENT_ENV": "staging",
        "PULSE_PILOT_MODE": "1",
        "PULSE_COOKIE_SECURE": "1",
        "PULSE_AUTO_BACKUP": "1",
        "PULSE_PUBLIC_ORIGIN": "https://contracts.pulse.invalid",
        "PULSE_SESSION_SECRET": "9" * 60,
    }


def test_no_unverified_manual_approval_can_be_called_ready(environment):
    directory, env = environment
    result = gate.assess_launch(directory, env)
    assert not result["internal_pilot_ready"]
    assert result["checks"]["unified_master"]["passed"]
    assert result["checks"]["named_staff_accounts"]["passed"]
    assert not result["checks"]["coordinator_uat"]["passed"]
    assert result["customer_quote_issuance_authorised"] is False
    assert result["production_certified"] is False
    assert "fake-admin" not in json.dumps(result)
    assert "32100" not in json.dumps(result)


def test_supervised_pilot_needs_all_explicit_operational_signoffs(environment):
    directory, env = environment
    signed = gate.assess_launch(
        directory, env, data_reconciled=True, restore_tested=True,
        https_and_roles_tested=True, coordinator_uat_passed=True,
    )
    assert signed["internal_pilot_ready"] is True
    assert signed["checks"]["unified_master"]["revision"] == 1
    assert signed["checks"]["unified_master"]["item_codes"] == 1
    assert signed["customer_quote_issuance_authorised"] is False


def test_corrupt_master_and_missing_role_fail_closed(environment):
    directory, env = environment
    with sqlite3.connect(directory / "contracts.sqlite3") as db:
        db.execute(
            "UPDATE unified_price_book_versions SET snapshot_sha256='x'"
        )
        db.execute("UPDATE pilot_users SET disabled=1 WHERE role='Coordinator'")
    signed = gate.assess_launch(
        directory, env, data_reconciled=True, restore_tested=True,
        https_and_roles_tested=True, coordinator_uat_passed=True,
    )
    assert not signed["internal_pilot_ready"]
    assert not signed["checks"]["unified_master"]["passed"]
    assert not signed["checks"]["named_staff_accounts"]["passed"]


def test_missing_security_profile_blocks_even_when_data_and_signoffs_exist(environment):
    directory, env = environment
    env["PULSE_COOKIE_SECURE"] = "0"
    result = gate.assess_launch(
        directory, env, data_reconciled=True, restore_tested=True,
        https_and_roles_tested=True, coordinator_uat_passed=True,
    )
    assert not result["internal_pilot_ready"]
    assert not result["checks"]["server_security_profile"]["passed"]
