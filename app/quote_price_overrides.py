"""Controlled per-SKU price revisions for the unified SmartQuote pilot.

Original August price master, original V10 JSON, Sage snapshots and issued
quotes remain immutable. A named pilot Admin can set/revert a *local*
effective equipment RRP for an exact source SKU. Each revision is audited and
bound to the source snapshot that was inspected; a refreshed source blocks
stale overrides until reconfirmed. This never approves contract tariffs.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import pilot_access
from .store import connect

router = APIRouter(prefix="/api/quoting/prices", tags=["Controlled equipment price revisions"])
SKU = re.compile(r"^[A-Z0-9][A-Z0-9 ._/#*()&+\-]{0,99}$")
ACTIVE_SOURCES = {"august_2026_master_list_price", "sage_exact_sku_price"}


class PriceChange(BaseModel):
    price_gbp: Decimal
    expected_revision: int
    reason: str


class PriceRevert(BaseModel):
    expected_revision: int
    reason: str


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "A signed-in pricing administrator is required.")
    person = pilot_access.actor("")
    if not person or person == "Coordinator":
        raise HTTPException(403, "A named pricing administrator is required.")
    return person


def _code(code):
    code = str(code or "").strip().upper()
    if not SKU.fullmatch(code):
        raise HTTPException(422, "Enter an exact equipment item code.")
    return code


def _pence(value):
    if isinstance(value, bool):
        raise HTTPException(422, "Enter a valid equipment price.")
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise HTTPException(422, "Enter a valid equipment price.") from exc
    if not amount.is_finite() or not 0 < amount <= 1000000 or amount != amount.quantize(Decimal(".01")):
        raise HTTPException(422, "Price must be positive GBP with at most 2 decimal places.")
    return int(amount * 100)


def _reason(value):
    reason = str(value or "").strip()
    if not 12 <= len(reason) <= 500:
        raise HTTPException(422, "Explain the price change in 12–500 characters.")
    return reason


def _table(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS smartquote_price_overrides (
            sku TEXT PRIMARY KEY,
            price_pence INTEGER NOT NULL CHECK(price_pence>0),
            source_kind TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS smartquote_price_override_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL, action TEXT NOT NULL,
            before_pence INTEGER, after_pence INTEGER,
            revision INTEGER NOT NULL, source_kind TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, actor TEXT NOT NULL,
            reason TEXT NOT NULL, at TEXT NOT NULL
        );
    """)


def active_overrides(codes=None):
    """Return local overrides without database/schema mutations."""
    try:
        con = connect()
        try:
            if codes is None:
                rows = con.execute(
                    "SELECT * FROM smartquote_price_overrides WHERE active=1"
                ).fetchall()
            else:
                codes = sorted({_code(sku) for sku in codes if sku})
                if not codes:
                    return {}
                if len(codes) > 500:
                    raise HTTPException(422, "Too many equipment codes.")
                marks = ",".join("?" for _ in codes)
                rows = con.execute(
                    "SELECT * FROM smartquote_price_overrides WHERE active=1 "
                    f"AND sku IN ({marks})", codes
                ).fetchall()
            return {row["sku"]: dict(row) for row in rows}
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return {}
        raise


def _digest(decision, august, sage):
    if decision["basis"] == "august_2026_master_list_price":
        return august["snapshot_sha256"]
    if decision["basis"] == "sage_exact_sku_price" and sage is not None:
        return sage["source_file_sha256"]
    return None


def effective(decision, override, august, sage):
    """Apply only revisions matching the exact underlying evidence."""
    if override is None or not override.get("active"):
        return decision
    expected = _digest(decision, august, sage)
    if (decision["basis"] != override["source_kind"]
            or expected != override["source_sha256"]):
        return {
            **decision, "basis": "stale_price_override",
            "rrp": None, "review_required": True,
            "override_revision": override["revision"],
            "override_status": "source_changed_review_required",
        }
    return {
        **decision,
        "basis": "managed_price_override",
        "underlying_basis": decision["basis"],
        "rrp": override["price_pence"] / 100,
        "override_revision": override["revision"],
        "override_status": "active",
        "review_required": False,
        "original_source_price_gbp": decision["rrp"],
        "source_price_updated_by": override["updated_by"],
        "source_price_updated_at": override["updated_at"],
    }


def source_for_code(code):
    """Only an already-staged current master or Sage item may be edited."""
    from .quote_rrp_priority import source_snapshot as august_snapshot, index, resolve
    from .quote_sage_reference import snapshot as sage_snapshot
    august = august_snapshot()
    try:
        sage = sage_snapshot()
    except HTTPException:
        sage = None
    decision = resolve(code, index(august), sage)
    if decision["basis"] not in ACTIVE_SOURCES:
        raise HTTPException(
            409, "No single valid August List Price or exact Sage price is available for this code."
        )
    digest = _digest(decision, august, sage)
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest.lower()):
        raise HTTPException(503, "Price source has no valid evidence fingerprint.")
    return decision, digest


def write_price(code, data, *, revert=False):
    person = _admin()
    code = _code(code)
    reason = _reason(data.reason)
    if type(data.expected_revision) is not int or not 0 <= data.expected_revision < 1000000:
        raise HTTPException(422, "A valid prior price revision is required.")
    pence = None if revert else _pence(data.price_gbp)
    decision, digest = source_for_code(code)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    con = connect()
    try:
        _table(con)
        con.execute("BEGIN IMMEDIATE")
        old = con.execute(
            "SELECT * FROM smartquote_price_overrides WHERE sku=?", (code,)
        ).fetchone()
        revision = old["revision"] if old else 0
        if revision != data.expected_revision:
            raise HTTPException(409, "Price revision changed; reload the source before editing.")
        if revert and (old is None or not old["active"]):
            raise HTTPException(409, "No active price override exists for this code.")
        if not revert:
            con.execute("""
                INSERT INTO smartquote_price_overrides
                (sku,price_pence,source_kind,source_sha256,revision,
                 updated_at,updated_by,reason,active)
                VALUES (?,?,?,?,?,?,?,?,1)
                ON CONFLICT(sku) DO UPDATE SET
                price_pence=excluded.price_pence,
                source_kind=excluded.source_kind,
                source_sha256=excluded.source_sha256,
                revision=excluded.revision,
                updated_at=excluded.updated_at,
                updated_by=excluded.updated_by,
                reason=excluded.reason,active=1
            """, (code, pence, decision["basis"], digest, revision + 1,
                  now, person, reason))
        else:
            con.execute(
                "UPDATE smartquote_price_overrides SET active=0,revision=?, "
                "updated_at=?,updated_by=?,reason=? WHERE sku=?",
                (revision + 1, now, person, reason, code)
            )
        con.execute("""
            INSERT INTO smartquote_price_override_audit
            (sku,action,before_pence,after_pence,revision,source_kind,
             source_sha256,actor,reason,at) VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (code, "revert" if revert else "set",
              old["price_pence"] if old and old["active"] else None,
              pence, revision + 1, decision["basis"], digest, person, reason, now))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "sku": code, "revision": revision + 1,
        "active": not revert,
        "effective_rrp_gbp": pence / 100 if pence is not None else decision["rrp"],
        "source_kind": decision["basis"],
        "source_sha256": digest,
        "updated_at": now,
        "updated_by": person,
        "commercially_approved": False,
        "customer_quote_issue_enabled": False,
        "original_sage_or_master_data_unchanged": True,
    }


@router.get("/{sku}")
def price_detail(sku: str):
    _admin()
    code = _code(sku)
    decision, digest = source_for_code(code)
    con = connect()
    try:
        try:
            current = con.execute(
                "SELECT * FROM smartquote_price_overrides WHERE sku=?", (code,)
            ).fetchone()
            history = con.execute(
                "SELECT action,before_pence,after_pence,revision,actor,reason,at "
                "FROM smartquote_price_override_audit WHERE sku=? "
                "ORDER BY id DESC LIMIT 30", (code,)
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            current, history = None, []
    finally:
        con.close()
    row = dict(current) if current else None
    applied = effective(decision, row, {
        "snapshot_sha256": digest if decision["basis"] == "august_2026_master_list_price" else "",
    }, {"source_file_sha256": digest} if decision["basis"] == "sage_exact_sku_price" else None)
    return {
        "sku": code,
        "source_kind": decision["basis"],
        "source_price_gbp": decision["rrp"],
        "effective_price_gbp": applied["rrp"],
        "override_active": bool(row and row["active"]),
        "override_status": applied.get("override_status", "none"),
        "revision": row["revision"] if row else 0,
        "updated_by": row["updated_by"] if row else None,
        "updated_at": row["updated_at"] if row else None,
        "history": [{
            "action": event["action"],
            "before_gbp": event["before_pence"] / 100 if event["before_pence"] is not None else None,
            "after_gbp": event["after_pence"] / 100 if event["after_pence"] is not None else None,
            "revision": event["revision"],
            "actor": event["actor"],
            "reason": event["reason"],
            "at": event["at"],
        } for event in history],
        "source_documented": True,
        "quote_tariff_approved": False,
    }


@router.put("/{sku}")
def update_price(sku: str, data: PriceChange):
    return write_price(sku, data)


@router.post("/{sku}/revert")
def revert_price(sku: str, data: PriceRevert):
    return write_price(sku, data, revert=True)
