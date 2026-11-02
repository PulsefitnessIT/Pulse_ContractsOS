"""Unified workspace: guarded read-only visibility into an existing SmartQuote store.

This is phase one of native consolidation. It deliberately does not copy customer
records, issue quotations, change pricing, or grant Contracts OS users permission
to edit SmartQuote. A shared identity/authorisation design is still required.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from .pilot_access import actor

router = APIRouter(prefix="/api/quoting", tags=["Unified quoting workspace"])
ENV_NAME = "PULSE_SMARTQUOTE_DB"


def _source() -> Path | None:
    configured = os.environ.get(ENV_NAME, "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser().resolve()
    if not path.is_absolute() or not path.is_file() or path.suffix.lower() != ".db":
        return None
    return path


def _connect():
    path = _source()
    if path is None:
        raise HTTPException(503, "SmartQuote data source is not configured. Existing quotations remain unchanged.")
    try:
        # SQLite immutable mode deliberately avoided: it would ignore WAL changes.
        uri = "file:" + quote(str(path), safe="/:") + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as exc:
        raise HTTPException(503, "SmartQuote data source could not be opened read-only.") from exc


@router.get("/status")
def integration_status():
    actor()
    return {
        "workspace": "Pulse Fitness",
        "smartquote_connected": _source() is not None,
        "mode": "read_only",
        "edits_enabled": False,
        "accepted_quote_transfer": "existing validated intake; not yet automatic",
        "source_config": ENV_NAME,
    }


@router.get("/quotes")
def list_quotes(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    actor()
    with _connect() as db:
        try:
            rows = db.execute(
                "SELECT id, quote_no, created, updated, status, payload "
                "FROM quotes ORDER BY updated DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = db.execute("SELECT count(*) FROM quotes").fetchone()[0]
        except sqlite3.Error as exc:
            raise HTTPException(503, "SmartQuote database schema is not compatible.") from exc
    result = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                continue
            result.append({
                "id": row["id"], "quote_number": row["quote_no"],
                "created": row["created"], "updated": row["updated"],
                "status": payload.get("pipeline_status") or row["status"],
                "customer": str(payload.get("customer") or "")[:250],
                "site": str(payload.get("site") or "")[:250],
                "tier": str(payload.get("tier") or "")[:40],
                "pricing_approved": payload.get("pricing_approved") is True,
            })
        except (ValueError, TypeError):
            continue
    return {"items": result, "total": total, "limit": limit, "offset": offset,
            "read_only": True, "source": "Pulse SmartQuote"}
