"""One-click accepted SmartQuote snapshot intake into Contracts OS.

Read from a configured local SmartQuote database, verify the immutable archived
PDF bytes and locked issued values, then apply the existing Contracts OS intake
validation/deduplication. Does not issue prices, infer commercial approval,
change contracts, upload equipment or write to Sage/Sicon.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import closing
from decimal import InvalidOperation

from fastapi import APIRouter, HTTPException

from .pilot_access import actor
from .store import connect
from .quote_workspace import _connect
from ._smartquote_transfer_v10 import from_accepted_pdf_snapshot
from .quote_intake import IntakeError, preview_data, register

router = APIRouter(prefix="/api/quoting", tags=["Native SmartQuote handover"])
MAX_ARCHIVE = 15 * 1024 * 1024


def accepted_snapshot(source_id: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", source_id):
        raise HTTPException(422, "Invalid original SmartQuote source reference.")
    with closing(_connect()) as source:
        try:
            latest = source.execute(
                "SELECT payload FROM quotes WHERE id=?", (source_id,)
            ).fetchone()
            if latest is None:
                raise HTTPException(404, "Original SmartQuote quotation not found.")
            live = json.loads(latest["payload"])
            if not isinstance(live, dict) or live.get("pipeline_status") != "Accepted":
                raise HTTPException(409, "Original SmartQuote quotation is not marked Accepted.")
            archive = source.execute(
                "SELECT version, status, payload, pdf, pdf_sha256 "
                "FROM quote_versions WHERE quote_id=? ORDER BY version DESC LIMIT 1",
                (source_id,),
            ).fetchone()
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, "SmartQuote quotation data is invalid.") from exc
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(503, "SmartQuote archive schema is unavailable.") from exc

    if archive is None:
        raise HTTPException(409, "No archived quotation PDF. Issue a quotation first.")
    original_pdf = archive["pdf"]
    if not isinstance(original_pdf, bytes) or not original_pdf.startswith(b"%PDF-") or len(original_pdf) > MAX_ARCHIVE:
        raise HTTPException(409, "Archived PDF bytes are unavailable or exceed the pilot limit.")
    fingerprint = str(archive["pdf_sha256"] or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint) or hashlib.sha256(original_pdf).hexdigest() != fingerprint:
        raise HTTPException(409, "The original archived PDF integrity check failed.")
    try:
        saved = json.loads(archive["payload"])
        if not isinstance(saved, dict) or saved.get("id") != source_id:
            raise ValueError("Archived quotation identity differs from source.")
        if saved.get("quote_no") != live.get("quote_no"):
            raise ValueError("Archived quotation number differs from current record.")
        summary = saved.get("issued_quote_values")
        if not isinstance(summary, dict):
            raise ValueError("Archived quotation lacks locked issued equipment values.")
        # Conservatively force review: a locally recorded 'Accepted' status
        # does NOT prove legal customer acceptance or approved commercial tariffs.
        return from_accepted_pdf_snapshot(
            saved, summary, archive["version"], fingerprint, pilot_snapshot=True
        )
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        raise HTTPException(422, f"Archived accepted quotation cannot be transferred: {exc}") from exc


@router.get("/quotes/{source_id}/intake-preview")
def preview_native_handover(source_id: str):
    actor()
    payload = accepted_snapshot(source_id)
    with closing(connect()) as db:
        try:
            result = preview_data(db, payload)
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc
    return {
        "source_quote_id": source_id,
        "quote_number": payload["quote_number"],
        "readiness": result["readiness"],
        "already_imported_id": result["already_imported_id"],
        "prior_revision_id": result["prior_revision_id"],
        "equipment_lines": len(payload["equipment"]),
        "commercially_approved": False,
        "read_only_preview": True,
    }


@router.post("/quotes/{source_id}/intake")
def submit_native_handover(source_id: str):
    """Explicit coordinator action; repeated snapshots return original intake."""
    username = actor()
    payload = accepted_snapshot(source_id)
    with closing(connect()) as db:
        try:
            result = register(db, payload, username)
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc
    return {
        "intake_id": result["id"], "already_imported": result["already_imported"],
        "readiness": result["readiness"], "commercially_approved": False,
        "sicon_write_performed": False,
    }
