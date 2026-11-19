"""Administrator-first onboarding for Contracts OS + SmartQuote.

This is a *setup checklist*, not a second pricing engine. All readiness
indicators come from existing, authoritative source/approval services.
Progress is stored in the private pilot DB (never localStorage), and no
setup action approves tariffs or enables customer issue automatically.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import pilot_access
from .data_readiness import assess_database
from .quote_price_book import active_book
from .quote_commercial_setup import commercial_status
from .store import connect, DB, TEMPLATE, now

router = APIRouter(prefix="/api/admin/setup", tags=["Administrator setup wizard"])

STEP_LABELS = {
    "contracts": "Maintenance Master and contracts",
    "prices": "Unified equipment prices",
    "company": "Pulse company details",
    "terms": "Maintenance agreement terms",
    "rates": "Approved service pricing",
}


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Only signed-in Administrators can manage platform setup.")
    user = pilot_access.actor("")
    if (not isinstance(user, str) or len(user.strip()) < 2
            or user.strip() in ("Admin", "Coordinator", "Viewer")):
        raise HTTPException(403, "A named Administrator account is required.")
    return user.strip()[:120]


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS platform_setup_wizard(
        id INTEGER PRIMARY KEY CHECK(id=1),
        first_opened_at TEXT NOT NULL DEFAULT '',
        deferred_at TEXT NOT NULL DEFAULT '',
        completed_at TEXT NOT NULL DEFAULT '',
        completed_by TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '')""")


def _progress():
    with closing(connect()) as db:
        _schema(db)
        row = db.execute("SELECT * FROM platform_setup_wizard WHERE id=1").fetchone()
        return dict(row) if row else {
            "first_opened_at": "", "deferred_at": "",
            "completed_at": "", "completed_by": "", "updated_at": "",
        }


def _readiness():
    """Do not conflate equipment RRP, maintenance rate approval and issuance."""
    try:
        data = assess_database(DB, TEMPLATE)
        contracts_ready = bool(data.get("ready_for_data_review"))
        contract_count = int((data.get("contracts") or {}).get("active") or 0)
        database_errors = (data.get("issues") or [])[:5]
    except (OSError, ValueError, sqlite3.Error):
        contracts_ready, contract_count = False, 0
        database_errors = ["Maintenance records could not be checked on this device."]

    try:
        price = active_book()
        prices_ready = bool(price and price.get("rows"))
        price_count = len(price["rows"]) if prices_ready else 0
        price_revision = price.get("revision") if price else None
    except (OSError, ValueError, sqlite3.Error, HTTPException):
        prices_ready, price_count, price_revision = False, 0, None

    try:
        commercial = commercial_status()
        issuer = (commercial.get("settings") or {}).get("issuer") or {}
        terms = (commercial.get("settings") or {}).get("terms") or {}
        tariff = commercial.get("tariff_source") or {}
        company_ready = bool(issuer.get("integrity_valid"))
        terms_ready = bool(terms.get("integrity_valid"))
        rates_ready = bool(tariff.get("commercially_approved"))
        rate_policy_loaded = bool(tariff.get("staged"))
        customer_issue = bool(commercial.get("customer_issuance_enabled"))
    except (OSError, ValueError, sqlite3.Error, HTTPException):
        company_ready = terms_ready = rates_ready = rate_policy_loaded = customer_issue = False

    state = {
        "contracts": {
            "ready": contracts_ready,
            "detail": (f"{contract_count:,} active contract records available."
                       if contracts_ready else "Maintenance Master or contract records need review."),
        },
        "prices": {
            "ready": prices_ready,
            "detail": (f"{price_count:,} item codes in approved Master price version {price_revision}."
                       if prices_ready else "No active Unified Master equipment price list."),
        },
        "company": {
            "ready": company_ready,
            "detail": ("Verified Pulse company details are saved."
                       if company_ready else "Legal company details and approval are required."),
        },
        "terms": {
            "ready": terms_ready,
            "detail": ("Approved maintenance terms PDF is saved."
                       if terms_ready else "Approved maintenance agreement terms are required."),
        },
        "rates": {
            "ready": rates_ready,
            "detail": ("Maintenance rate policy has commercial approval."
                       if rates_ready else "Approved maintenance rates and cover rules are outstanding."),
        },
    }
    required_ready = all(x["ready"] for x in state.values())
    return {
        "steps": [{"id": key, "title": name, **state[key]}
                  for key, name in STEP_LABELS.items()],
        "ready_count": sum(int(x["ready"]) for x in state.values()),
        "required_count": len(state),
        "internal_use_ready": contracts_ready and prices_ready,
        "core_setup_ready": required_ready,
        "customer_issuance_enabled": customer_issue,
        "customer_quote_ready": required_ready and customer_issue,
        "rate_policy_available_for_approval": rate_policy_loaded,
        "recorded_active_contracts": contract_count,
        "data_issues": database_errors,
        "commercial_approval_is_separate": True,
        "never_approves_or_issues_quotes_automatically": True,
    }


@router.get("/status")
def get_setup_status():
    _admin()
    progress = _progress()
    checks = _readiness()
    return {
        **checks,
        "first_login_wizard": not bool(progress["first_opened_at"]),
        "wizard_started": bool(progress["first_opened_at"]),
        "wizard_deferred": bool(progress["deferred_at"]),
        "wizard_completed": bool(progress["completed_at"]),
        "completed_by": progress["completed_by"],
        "completed_at": progress["completed_at"],
        # A completed wizard cannot hide a subsequently broken source.
        "needs_attention": not checks["core_setup_ready"],
        "has_unresolved_setup": not checks["core_setup_ready"],
    }


class SetupAction(BaseModel):
    action: Literal["start", "continue_later", "finish"]


@router.post("/progress")
def update_setup_progress(payload: SetupAction):
    who = _admin()
    if payload.action == "finish":
        checked = _readiness()
        if not checked["core_setup_ready"]:
            outstanding = [s["title"] for s in checked["steps"] if not s["ready"]]
            raise HTTPException(
                409, "Complete the required checks before marking setup finished: "
                + ", ".join(outstanding)
            )
    timestamp = now()
    with closing(connect()) as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        db.execute("""INSERT OR IGNORE INTO platform_setup_wizard(id) VALUES (1)""")
        db.execute("""UPDATE platform_setup_wizard
                      SET first_opened_at=CASE
                          WHEN first_opened_at='' THEN ? ELSE first_opened_at END,
                          deferred_at=CASE WHEN ?='continue_later' THEN ? ELSE deferred_at END,
                          completed_at=CASE WHEN ?='finish' THEN ? ELSE completed_at END,
                          completed_by=CASE WHEN ?='finish' THEN ? ELSE completed_by END,
                          updated_at=?
                      WHERE id=1""", (
            timestamp, payload.action, timestamp,
            payload.action, timestamp, payload.action, who, timestamp,
        ))
        db.commit()
    return get_setup_status()
