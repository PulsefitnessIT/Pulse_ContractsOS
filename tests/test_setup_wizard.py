"""Private-state-only first-login setup tests. No actual customer or price data."""
import sqlite3

import pytest
from fastapi import HTTPException
from app import setup_wizard as wizard


def fake_environment(tmp_path, monkeypatch):
    path=tmp_path/"synthetic_setup.sqlite3"
    def connect():
        con=sqlite3.connect(path)
        con.row_factory=sqlite3.Row
        return con
    monkeypatch.setattr(wizard,"connect",connect)
    monkeypatch.setattr(wizard.pilot_access,"PILOT_MODE",True)
    monkeypatch.setattr(wizard.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(wizard.pilot_access,"actor",lambda fallback="":"fictional.admin")
    flags={
        "contracts":True,"prices":True,"company":True,
        "terms":True,"rates":True,"issuance":False,
    }
    def data(*_):
        return {
            "ready_for_data_review":flags["contracts"],
            "contracts":{"active":3},
            "issues":([] if flags["contracts"] else ["Synthetic workbook needs review"]),
        }
    def book():
        return {"rows":{"TEST-001":{"price":"12.00"}},"revision":2} if flags["prices"] else None
    def commercial():
        return {
            "settings":{
                "issuer":{"integrity_valid":flags["company"]},
                "terms":{"integrity_valid":flags["terms"]},
            },
            "tariff_source":{"staged":flags["rates"],
                             "commercially_approved":flags["rates"]},
            "customer_issuance_enabled":flags["issuance"],
        }
    monkeypatch.setattr(wizard,"assess_database",data)
    monkeypatch.setattr(wizard,"active_book",book)
    monkeypatch.setattr(wizard,"commercial_status",commercial)
    return flags


def test_first_admin_login_opens_wizard_once_and_progress_survives(tmp_path,monkeypatch):
    fake_environment(tmp_path,monkeypatch)
    initial=wizard.get_setup_status()
    assert initial["first_login_wizard"] is True
    assert initial["ready_count"] == 5
    assert initial["core_setup_ready"] is True
    assert initial["customer_quote_ready"] is False  # never enable issue implicitly

    opened=wizard.update_setup_progress(wizard.SetupAction(action="start"))
    assert opened["first_login_wizard"] is False
    assert opened["wizard_started"] is True
    assert opened["wizard_completed"] is False
    assert wizard.get_setup_status()["wizard_started"] is True

    saved=wizard.update_setup_progress(wizard.SetupAction(action="finish"))
    assert saved["wizard_completed"] is True
    assert saved["completed_by"]=="fictional.admin"
    assert saved["customer_issuance_enabled"] is False
    assert wizard.get_setup_status()["wizard_completed"] is True


def test_missing_price_list_blocks_completion_but_permits_internal_deferral(tmp_path,monkeypatch):
    flags=fake_environment(tmp_path,monkeypatch)
    flags["prices"]=False
    before=wizard.get_setup_status()
    assert before["ready_count"]==4
    assert before["internal_use_ready"] is False
    assert before["core_setup_ready"] is False
    with pytest.raises(HTTPException) as failure:
        wizard.update_setup_progress(wizard.SetupAction(action="finish"))
    assert failure.value.status_code==409
    assert "Unified equipment prices" in failure.value.detail
    paused=wizard.update_setup_progress(wizard.SetupAction(action="continue_later"))
    assert paused["wizard_deferred"] is True
    assert paused["wizard_completed"] is False
    assert paused["needs_attention"] is True


def test_incomplete_maintenance_rates_do_not_approve_customer_quotes(tmp_path,monkeypatch):
    flags=fake_environment(tmp_path,monkeypatch)
    flags["rates"]=False
    flags["issuance"]=True
    result=wizard.get_setup_status()
    assert result["internal_use_ready"] is True
    assert result["customer_quote_ready"] is False
    assert result["rate_policy_available_for_approval"] is False
    assert result["needs_attention"] is True


def test_completed_wizard_does_not_hide_later_invalid_source(tmp_path,monkeypatch):
    flags=fake_environment(tmp_path,monkeypatch)
    wizard.update_setup_progress(wizard.SetupAction(action="finish"))
    flags["terms"]=False
    result=wizard.get_setup_status()
    assert result["wizard_completed"] is True
    assert result["core_setup_ready"] is False
    assert result["needs_attention"] is True
    assert result["customer_quote_ready"] is False


def test_nonadmin_and_demo_mode_cannot_read_or_write_setup(tmp_path,monkeypatch):
    fake_environment(tmp_path,monkeypatch)
    monkeypatch.setattr(wizard.pilot_access,"current_role",lambda:"Coordinator")
    with pytest.raises(HTTPException) as exc:
        wizard.get_setup_status()
    assert exc.value.status_code==403
    with pytest.raises(HTTPException) as exc:
        wizard.update_setup_progress(wizard.SetupAction(action="start"))
    assert exc.value.status_code==403
    monkeypatch.setattr(wizard.pilot_access,"current_role",lambda:"Admin")
    monkeypatch.setattr(wizard.pilot_access,"PILOT_MODE",False)
    with pytest.raises(HTTPException) as exc:
        wizard.get_setup_status()
    assert exc.value.status_code==403


def test_client_cannot_submit_unexpected_wizard_action():
    with pytest.raises(ValueError):
        wizard.SetupAction(action="auto_approve_issuance")
