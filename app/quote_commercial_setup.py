"""Protected in-app commercial setup for issuing Pulse customer quotations.

This replaces manual environment-only onboarding in a supervised pilot:
  1. Approve the exact pinned V10 tariff fingerprint (no rate invention).
  2. Upload genuine, signed-off maintenance terms as a PDF.
  3. Record verified Pulse Fitness legal issuer details.
  4. Explicitly enable customer issuance for this protected pilot.

Every change is versioned and audited. No customer data or commercial secrets
are committed to GitHub; source documents live in the protected pilot database.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from contextlib import closing

import fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import pilot_access, quote_pricing
from .store import connect

router = APIRouter(prefix="/api/quoting/commercial-setup",
                   tags=["Protected SmartQuote commercial setup"])
MAX_TERMS_BYTES = 8 * 1024 * 1024
KIND = frozenset(("tariff", "terms", "issuer", "issuance"))
SHA = re.compile(r"^[a-f0-9]{64}$")


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role() != "Admin":
        raise HTTPException(403, "Only signed-in pilot Administrators may approve quote setup.")
    name = pilot_access.actor("")
    if not isinstance(name, str) or len(name.strip()) < 2 or name in ("Coordinator", "Viewer"):
        raise HTTPException(403, "A named Administrator session is required.")
    return name.strip()[:120]


def _field(value, label, minimum=8, maximum=250):
    v = str(value or "").strip()
    if not minimum <= len(v) <= maximum or any(ord(c) < 32 for c in v):
        raise HTTPException(422, f"Enter verified {label} ({minimum}-{maximum} characters).")
    return v


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS smartquote_commercial_settings(
        kind TEXT PRIMARY KEY,
        payload BLOB NOT NULL, sha256 TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        approval_reference TEXT NOT NULL,
        reason TEXT NOT NULL, approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS smartquote_commercial_settings_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, revision INTEGER NOT NULL,
        old_sha256 TEXT, new_sha256 TEXT NOT NULL,
        approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL,
        reason TEXT NOT NULL, approved_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_quote_commercial_audit_kind "
               "ON smartquote_commercial_settings_audit(kind,id)")


def _read(kind):
    if kind not in KIND:
        return None
    with closing(connect()) as db:
        try:
            row = db.execute(
                "SELECT kind,payload,sha256,revision,approval_reference,"
                "reason,approved_by,approved_at FROM smartquote_commercial_settings "
                "WHERE kind=?", (kind,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    return dict(row) if row else None


def _save(kind, raw, digest, *, approval_reference, reason, username):
    if kind not in KIND or not isinstance(raw, bytes) or not SHA.fullmatch(digest):
        raise HTTPException(422, "Invalid commercial settings evidence.")
    approval_reference = _field(approval_reference, "commercial approval reference")
    reason = _field(reason, "change reason", 12, 500)
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with closing(connect()) as db:
        _schema(db)
        try:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT sha256,revision FROM smartquote_commercial_settings WHERE kind=?",
                (kind,),
            ).fetchone()
            rev = old["revision"]+1 if old else 1
            db.execute("""
              INSERT INTO smartquote_commercial_settings
              (kind,payload,sha256,revision,approval_reference,
               reason,approved_by,approved_at)
              VALUES(?,?,?,?,?,?,?,?)
              ON CONFLICT(kind) DO UPDATE SET
              payload=excluded.payload,
              sha256=excluded.sha256,
              revision=excluded.revision,
              approval_reference=excluded.approval_reference,
              reason=excluded.reason,
              approved_by=excluded.approved_by,
              approved_at=excluded.approved_at
            """, (kind,raw,digest,rev,approval_reference,reason,username,at))
            db.execute("""
              INSERT INTO smartquote_commercial_settings_audit
              (kind,revision,old_sha256,new_sha256,approved_by,
               approval_reference,reason,approved_at)
              VALUES(?,?,?,?,?,?,?,?)
            """, (kind,rev,old["sha256"] if old else None,digest,
                  username,approval_reference,reason,at))
            # Changes to a source approval automatically switch customer issuance
            # OFF. Rechecking prerequisites and reenabling is an explicit action.
            if kind != "issuance":
                current = db.execute(
                    "SELECT payload,revision FROM smartquote_commercial_settings "
                    "WHERE kind='issuance'"
                ).fetchone()
                if current:
                    state = json.loads(current["payload"].decode("utf-8"))
                    if state.get("enabled"):
                        off = json.dumps({"enabled":False},
                                         sort_keys=True).encode("utf-8")
                        off_hash = hashlib.sha256(off).hexdigest()
                        new_rev = current["revision"]+1
                        db.execute("""
                          UPDATE smartquote_commercial_settings SET
                          payload=?,sha256=?,revision=?,approval_reference=?,
                          reason=?,approved_by=?,approved_at=?
                          WHERE kind='issuance'
                        """, (off,off_hash,new_rev,approval_reference,
                              "Automatically disabled following updated " + kind,
                              username,at))
                        db.execute("""
                          INSERT INTO smartquote_commercial_settings_audit
                          (kind,revision,old_sha256,new_sha256,approved_by,
                           approval_reference,reason,approved_at)
                          VALUES(?,?,?,?,?,?,?,?)
                        """, ("issuance",new_rev,
                              hashlib.sha256(current["payload"]).hexdigest(),
                              off_hash,username,approval_reference,
                              "Automatically disabled following updated "+kind,at))
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"kind":kind,"revision":rev,"sha256":digest,
            "approved_by":username,"approved_at":at,
            "approval_reference":approval_reference,
            "customer_issuance_recheck_required":kind!="issuance"}


def _json(row,kind):
    if row is None or not SHA.fullmatch(str(row["sha256"])):
        return None
    raw = row["payload"]
    if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=row["sha256"]:
        raise HTTPException(503,f"Approved {kind} source content has changed.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise HTTPException(503,f"Approved {kind} source is invalid.") from exc
    if not isinstance(value,dict):
        raise HTTPException(503,f"Approved {kind} record has an invalid format.")
    return value


def tariff_is_approved(exact_sha):
    if not isinstance(exact_sha,str) or not SHA.fullmatch(exact_sha.lower()):
        return False
    row = _read("tariff")
    if not row:
        return False
    value = _json(row,"tariff")
    return value.get("approved_tariff_sha256")==exact_sha.lower()


def verified_terms():
    row = _read("terms")
    if not row:
        return None
    raw = row["payload"]
    if (not isinstance(raw,bytes) or len(raw)>MAX_TERMS_BYTES
            or hashlib.sha256(raw).hexdigest()!=row["sha256"]):
        raise HTTPException(503,"Approved maintenance terms were changed after sign-off.")
    try:
        with fitz.open(stream=raw,filetype="pdf") as doc:
            if doc.needs_pass or not 1<=doc.page_count<=30:
                raise ValueError("Invalid terms")
    except (ValueError,RuntimeError,fitz.FileDataError) as exc:
        raise HTTPException(503,"Approved maintenance terms PDF cannot be verified.") from exc
    return raw,row["sha256"]


def verified_issuer():
    row = _read("issuer")
    if not row:
        return None
    value = _json(row,"issuer")
    needed = ("legal_name","registered_address","contact_email","company_number")
    if not all(isinstance(value.get(k),str) and
               3<=len(value[k].strip())<=250 for k in needed):
        raise HTTPException(503,"Approved issuer identity is incomplete.")
    if "@" not in value["contact_email"]:
        raise HTTPException(503,"Approved issuer email is invalid.")
    return value,row["sha256"]


def enabled():
    row = _read("issuance")
    if not row:
        return False
    value = _json(row,"issuance")
    return value.get("enabled") is True


class ApproveTariff(BaseModel):
    expected_source_sha256: str
    approval_reference: str
    reason: str
    confirm_equipment_rate_groups: bool
    confirm_package_multipliers: bool
    confirm_minimums_and_discounts: bool
    confirm_parity_exceptions_reviewed: bool


class IssuerDetails(BaseModel):
    legal_name: str = Field(min_length=3,max_length=120)
    registered_address: str = Field(min_length=8,max_length=250)
    contact_email: str = Field(min_length=5,max_length=250)
    company_number: str = Field(min_length=3,max_length=30)
    telephone: str = Field(default="",max_length=40)
    vat_number: str = Field(default="",max_length=40)
    approval_reference: str
    reason: str
    confirm_verified_company_details: bool


class EnableCustomerQuotes(BaseModel):
    enabled: bool
    approval_reference: str
    reason: str
    confirm_customer_quote_acceptance_tests: bool


def _current_tariff():
    catalog,configs,policy,hashes = quote_pricing.source_snapshot()
    status = quote_pricing.source_manifest_status(hashes)
    if not status.get("pinned") or not status.get("matches"):
        raise HTTPException(503,"Price-source manifest has not been pinned.")
    return policy,hashes["pricing"]


@router.get("/status")
def commercial_status():
    _admin()
    settings = {kind:_read(kind) for kind in KIND}
    visible={}
    for kind,row in settings.items():
        visible[kind]=({
            "configured":bool(row),
            "sha256":row["sha256"] if row else None,
            "approved_by":row["approved_by"] if row else None,
            "approved_at":row["approved_at"] if row else None,
            "approval_reference":row["approval_reference"] if row else None,
            "revision":row["revision"] if row else 0,
        })
    try:
        pricing,hash_value=_current_tariff()
        source={
            "staged":True,"sha256":hash_value,
            "pricing_status":str(pricing.get("pricing_status") or ""),
            "rates":[{
                "group":str(item.get("group") or ""),
                "standard":item.get("standard"),
                "minimum":item.get("minimum"),
                "uplift":item.get("uplift"),
                "status":item.get("status"),
            } for item in pricing.get("rates",[]) if isinstance(item,dict)],
            "tiers":pricing.get("tiers",{}),
        }
        source["commercially_approved"]=tariff_is_approved(hash_value)
    except HTTPException as exc:
        source={"staged":False,"error":exc.detail,"commercially_approved":False}
    try:
        verified_terms()
        visible["terms"]["integrity_valid"]=bool(settings["terms"])
    except HTTPException:
        visible["terms"]["integrity_valid"]=False
    try:
        verified_issuer()
        visible["issuer"]["integrity_valid"]=bool(settings["issuer"])
    except HTTPException:
        visible["issuer"]["integrity_valid"]=False
    try:
        active=enabled()
    except HTTPException:
        active=False
    return {
        "tariff_source":source,
        "settings":visible,
        "customer_issuance_enabled":active,
        "requires_commercial_signoff":True,
        "customer_email_sent_by_app":False,
        "original_terms_and_tariff_not_modified":True,
    }


@router.post("/tariff")
def approve_tariff(data: ApproveTariff):
    who=_admin()
    if not (data.confirm_equipment_rate_groups and
            data.confirm_package_multipliers and
            data.confirm_minimums_and_discounts and
            data.confirm_parity_exceptions_reviewed):
        raise HTTPException(422,"Confirm every rate, package, discount and source exception before signing off.")
    policy,digest=_current_tariff()
    if data.expected_source_sha256.lower()!=digest:
        raise HTTPException(409,"Pricing source changed since review. Load its current rates again.")
    # A provisional source is intentionally NOT automatically approved.
    raw=json.dumps({"approved_tariff_sha256":digest,
                    "pricing_status_at_approval":str(policy.get("pricing_status") or "")},
                   sort_keys=True).encode("utf-8")
    return _save("tariff",raw,hashlib.sha256(raw).hexdigest(),
                 approval_reference=data.approval_reference,reason=data.reason,
                 username=who)


@router.post("/terms")
async def approve_terms(file: UploadFile=File(...),
                        approval_reference: str=Form(...),
                        reason: str=Form(...),
                        confirm_approved_current_terms: bool=Form(...)):
    who=_admin()
    if confirm_approved_current_terms is not True:
        raise HTTPException(422,"Confirm this PDF is the legally approved current maintenance agreement terms.")
    raw=await file.read(MAX_TERMS_BYTES+1)
    if (not 2<=len(raw)<=MAX_TERMS_BYTES
            or not (file.filename or "").lower().endswith(".pdf")
            or not raw.startswith(b"%PDF-")):
        raise HTTPException(422,"Upload a complete PDF of approved maintenance terms (max 8 MB).")
    try:
        with fitz.open(stream=raw,filetype="pdf") as doc:
            if doc.needs_pass or not 1<=doc.page_count<=30:
                raise ValueError("Unsupported maintenance agreement")
            pages=doc.page_count
    except (ValueError,RuntimeError,fitz.FileDataError) as exc:
        raise HTTPException(422,"Maintenance terms must be a readable PDF.") from exc
    result=_save("terms",raw,hashlib.sha256(raw).hexdigest(),
                 approval_reference=approval_reference,reason=reason,
                 username=who)
    return {**result,"terms_pages":pages,
            "filename":str(file.filename or "")[:140]}


@router.post("/issuer")
def save_issuer(data: IssuerDetails):
    who=_admin()
    if data.confirm_verified_company_details is not True:
        raise HTTPException(422,"Confirm the legal issuer details match verified company records.")
    from .quote_customer_issuance import _issuer as check_issuer
    details={key:_field(getattr(data,key),key,3 if key not in
                        ("registered_address","contact_email") else 8,250)
             for key in ("legal_name","registered_address",
                         "contact_email","company_number")}
    details.update(telephone=data.telephone.strip(),vat_number=data.vat_number.strip())
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", details["contact_email"]):
        raise HTTPException(422,"Enter a valid verified company email.")
    raw=json.dumps(details,sort_keys=True,ensure_ascii=False,
                   separators=(",",":")).encode("utf-8")
    return _save("issuer",raw,hashlib.sha256(raw).hexdigest(),
                 approval_reference=data.approval_reference,reason=data.reason,
                 username=who)


@router.post("/issuance")
def set_issuance(data: EnableCustomerQuotes):
    who=_admin()
    if data.enabled and not data.confirm_customer_quote_acceptance_tests:
        raise HTTPException(422,"Confirm the end-to-end customer quote acceptance checks before enabling.")
    if data.enabled:
        _,tariff=_current_tariff()
        if not tariff_is_approved(tariff):
            raise HTTPException(409,"The exact pricing tariff has not been commercially approved.")
        if not verified_terms():
            raise HTTPException(409,"Upload and approve the actual maintenance terms.")
        if not verified_issuer():
            raise HTTPException(409,"Verify company issuer details first.")
    raw=json.dumps({"enabled":data.enabled},sort_keys=True).encode("utf-8")
    return _save("issuance",raw,hashlib.sha256(raw).hexdigest(),
                 approval_reference=data.approval_reference,reason=data.reason,
                 username=who)


@router.get("/audit")
def commercial_audit(limit:int=50):
    _admin()
    if not 1<=limit<=100:
        raise HTTPException(422,"Select 1-100 approvals.")
    with closing(connect()) as db:
        try:
            entries=db.execute(
                "SELECT kind,revision,old_sha256,new_sha256,approved_by,"
                "approval_reference,reason,approved_at "
                "FROM smartquote_commercial_settings_audit "
                "ORDER BY id DESC LIMIT ?",(limit,)
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return {"items":[]}
            raise
    return {"items":[dict(row) for row in entries]}
