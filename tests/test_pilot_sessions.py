"""Synthetic account-security regressions; no actual staff credentials or records."""
from __future__ import annotations

import asyncio
import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app import pilot_access


@pytest.fixture
def pilot(tmp_path,monkeypatch):
    db=tmp_path/"fake-staging.sqlite3"
    monkeypatch.setattr(pilot_access,"DB",str(db))
    monkeypatch.setattr(pilot_access,"DATA",str(tmp_path))
    monkeypatch.setattr(pilot_access,"PILOT_MODE",True)
    monkeypatch.setenv("PULSE_SESSION_SECRET","synthetic-test-only-signature-secret-"+("A" * 55))
    monkeypatch.delenv("PULSE_DEPLOYMENT_ENV",raising=False)
    monkeypatch.delenv("PULSE_PUBLIC_ORIGIN",raising=False)
    pilot_access.configure_users()
    pilot_access.provision_user("fictionaladmin","test-only-password-long","Admin")
    pilot_access.provision_user("fictionalstaff","test-only-password-long","Coordinator")
    pilot_access.provision_user("fictionalviewer","test-only-password-long","Viewer")
    return db


def issue(user="fictionaladmin",role="Admin"):
    return pilot_access.sign_session({"username":user,"role":role})


def test_logout_revokes_session_server_side(pilot):
    cookie,_=issue()
    assert pilot_access.read_session(cookie)
    assert pilot_access.revoke_session(cookie) is True
    assert pilot_access.read_session(cookie) is None
    assert pilot_access.revoke_session(cookie) is False


def test_individual_sessions_can_be_revoked_without_disabling_account(pilot):
    c1,_=issue()
    c2,_=issue()
    assert pilot_access.revoke_session(c1)
    assert pilot_access.read_session(c1) is None
    assert pilot_access.read_session(c2)


def test_idle_expiry_is_enforced_even_before_signed_cookie_expiry(pilot):
    cookie,body=issue()
    with sqlite3.connect(pilot) as db:
        db.execute("UPDATE pilot_sessions SET last_seen_at=? WHERE id_hash=?",
                   (int(time.time())-pilot_access.IDLE_TTL-1,
                    pilot_access._session_digest(body["sid"])))
    assert pilot_access.read_session(cookie) is None


def test_password_reset_invalidates_all_old_sessions(pilot):
    old,_=issue()
    pilot_access.provision_user("fictionaladmin","longer-reset-password-here","Admin")
    assert pilot_access.read_session(old) is None
    assert pilot_access.check_password("fictionaladmin","longer-reset-password-here")


def test_disable_user_revokes_all_login_sessions(pilot):
    cookie,_=issue("fictionalstaff","Coordinator")
    assert pilot_access.disable_user("fictionalstaff")=="fictionalstaff"
    assert pilot_access.read_session(cookie) is None
    assert pilot_access.check_password("fictionalstaff","test-only-password-long") is None


def test_last_administrator_cannot_be_disabled(pilot):
    with pytest.raises(ValueError,match="last active administrator"):
        pilot_access.disable_user("fictionaladmin")


def test_unsigned_and_forged_sessions_fail(pilot):
    cookie,_=issue()
    assert pilot_access.read_session("tampered."+cookie.split(".")[-1]) is None
    assert pilot_access.read_session(cookie[:-1]+"0") is None
    assert pilot_access.read_session("x"*6000) is None


@pytest.mark.parametrize("origin",[
    "http://contracts.example.org",
    "https://evil.example.org",
    "https://contracts.example.org.evil.test",
    "null",
    "",
])
def test_server_staging_rejects_cross_origin_requests(pilot,monkeypatch,origin):
    monkeypatch.setenv("PULSE_DEPLOYMENT_ENV","staging")
    monkeypatch.setenv("PULSE_PUBLIC_ORIGIN","https://contracts.example.org")
    assert not pilot_access._public_origin_is_allowed({"origin":origin})


def test_server_staging_accepts_exact_origin_and_valid_referer(pilot,monkeypatch):
    monkeypatch.setenv("PULSE_DEPLOYMENT_ENV","staging")
    monkeypatch.setenv("PULSE_PUBLIC_ORIGIN","https://contracts.example.org")
    assert pilot_access._public_origin_is_allowed({"origin":"https://contracts.example.org"})
    assert pilot_access._public_origin_is_allowed({
        "referer":"https://contracts.example.org/contracts/action-centre"})
    assert not pilot_access._public_origin_is_allowed({
        "referer":"https://contracts.example.org.evil.invalid/stuff"})


def _request(path,method,cookie,csrf,origin="https://contracts.example.org"):
    headers=[
        (b"host",b"contracts.example.org"),
        (b"origin",origin.encode()),
        (b"cookie",("pulse_contracts_session="+cookie).encode()),
        (b"x-pulse-csrf",csrf.encode()),
    ]
    scope={"type":"http","method":method,"path":path,"headers":headers,
           "query_string":b"","scheme":"https",
           "client":("203.0.113.5",1234),"server":("contracts.example.org",443)}
    return Request(scope)


async def _accepted(request):
    return JSONResponse({"accepted":True},status_code=202)


def test_non_admin_cannot_approve_old_master_reimports(pilot,monkeypatch):
    monkeypatch.setenv("PULSE_DEPLOYMENT_ENV","staging")
    monkeypatch.setenv("PULSE_PUBLIC_ORIGIN","https://contracts.example.org")
    cookie,body=issue("fictionalstaff","Coordinator")
    request=_request("/api/master/reimport/abc/apply","POST",cookie,body["csrf"])
    result=asyncio.run(pilot_access.pilot_middleware(request,_accepted))
    assert result.status_code==403
    # Normal coordinator writes should remain available with valid CSRF.
    request=_request("/api/contracts/10","PATCH",cookie,body["csrf"])
    result=asyncio.run(pilot_access.pilot_middleware(request,_accepted))
    assert result.status_code==202


def test_viewer_can_log_out_but_cannot_change_contracts(pilot,monkeypatch):
    monkeypatch.setenv("PULSE_DEPLOYMENT_ENV","staging")
    monkeypatch.setenv("PULSE_PUBLIC_ORIGIN","https://contracts.example.org")
    cookie,body=issue("fictionalviewer","Viewer")
    request=_request("/api/contracts/10","PATCH",cookie,body["csrf"])
    assert asyncio.run(pilot_access.pilot_middleware(request,_accepted)).status_code==403
    request=_request("/api/pilot/logout","POST",cookie,body["csrf"])
    assert asyncio.run(pilot_access.pilot_middleware(request,_accepted)).status_code==202


def test_missing_csrf_blocks_write_even_from_admin(pilot,monkeypatch):
    cookie,_=issue()
    request=_request("/api/master/reimport/abc/apply","POST",cookie,"")
    assert asyncio.run(pilot_access.pilot_middleware(request,_accepted)).status_code==403


@pytest.mark.parametrize("path",[
    "/api/export/excel",
    "/api/export/equipment",
    "/api/pilot/data-quality/missing-amounts.csv",
    "/api/reports/sales/all-managers/download",
    "/api/imports/42/source",
    "/api/smartquote/setups/1/signed-agreement",
])
def test_viewer_cannot_bulk_export_customer_or_document_data(pilot,path):
    cookie,body=issue("fictionalviewer","Viewer")
    request=_request(path,"GET",cookie,body["csrf"])
    result=asyncio.run(pilot_access.pilot_middleware(request,_accepted))
    assert result.status_code==403


def test_coordinator_can_download_after_sign_in(pilot):
    cookie,body=issue("fictionalstaff","Coordinator")
    request=_request("/api/export/excel","GET",cookie,body["csrf"])
    result=asyncio.run(pilot_access.pilot_middleware(request,_accepted))
    assert result.status_code==202
