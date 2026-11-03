"""Safe self-service V10 source intake for the protected Quotes pilot.

A named Admin stages the four original source files as one small ZIP:
  catalog.json, configs.json, pricing.json, rrp_2026_source.json.gz
No customer databases, accounts, invoices, workbooks or additional repo files
are accepted. Genuine source bytes live only in protected Contracts OS SQLite,
not GitHub. The independent commercial tariff sign-off stays mandatory.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import re
import secrets
import sqlite3
import zipfile
from contextlib import closing

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import pilot_access
from .store import connect
from .quote_rrp_priority import MASTER_FILE, MASTER_DATE, MASTER_ORIGINAL_SHA256

router=APIRouter(prefix="/api/quoting/source-setup",
                 tags=["Protected V10 quotation-source intake"])
MAX_ZIP=35*1024*1024
FILES={
    "catalog":("catalog.json",20*1024*1024),
    "configs":("configs.json",12*1024*1024),
    "pricing":("pricing.json",1024*1024),
    "august_2026_rrp":("rrp_2026_source.json.gz",8*1024*1024),
}
MAX_SOURCE_BYTES=45*1024*1024
MAX_AGE=dt.timedelta(hours=2)


def _admin():
    if not pilot_access.PILOT_MODE or pilot_access.current_role()!="Admin":
        raise HTTPException(403,"Protected pilot Administrator login required.")
    person=pilot_access.actor("")
    if not person or person in ("Coordinator","Viewer"):
        raise HTTPException(403,"A named Administrator must review source files.")
    return person[:120]


def inspect_bundle(data):
    if not isinstance(data,bytes) or not 2<=len(data)<=MAX_ZIP:
        raise HTTPException(413,"Source ZIP is empty or exceeds 35 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if not 4<=len(entries)<=8:
                raise ValueError("Expected four specific source files, no other data.")
            files={}
            total=0
            for item in entries:
                if item.is_dir():
                    continue
                path=item.filename.replace("\\","/")
                if (path.startswith("/") or path.startswith("./")
                        or ".." in path.split("/")
                        or not re.fullmatch(r"[A-Za-z0-9_./-]{1,150}",path)):
                    raise ValueError("Source ZIP contains an unsafe path.")
                basename=path.rsplit("/",1)[-1]
                kind=next((key for key,(file,_) in FILES.items()
                           if file==basename),None)
                if kind is None or kind in files or item.flag_bits&0x1:
                    raise ValueError("Unexpected, duplicate or encrypted source file.")
                if (item.file_size<2 or item.file_size>FILES[kind][1]):
                    raise ValueError("Source file exceeds its safe byte limit.")
                total+=item.file_size
                if total>MAX_SOURCE_BYTES:
                    raise ValueError("Source files exceed the maximum expanded size.")
                raw=archive.read(item)
                files[kind]=raw
        if set(files)!=set(FILES):
            raise ValueError("Source bundle is missing required V10/August files.")
        catalog=json.loads(files["catalog"].decode("utf-8"))
        configs=json.loads(files["configs"].decode("utf-8"))
        pricing=json.loads(files["pricing"].decode("utf-8"))
        if (not isinstance(catalog,list) or not 1<=len(catalog)<=30000 or
                not isinstance(configs,list) or not 1<=len(configs)<=10000 or
                not isinstance(pricing,dict) or
                pricing.get("currency")!="GBP" or
                not isinstance(pricing.get("rates"),list) or
                not isinstance(pricing.get("tiers"),dict) or
                not isinstance(pricing.get("console_rules"),list)):
            raise ValueError("Original V10 catalogue, configuration or tariff has the wrong shape.")
        source=files["august_2026_rrp"]
        if len(source)>8*1024*1024:
            raise ValueError("August price evidence is oversized.")
        with gzip.GzipFile(fileobj=io.BytesIO(source)) as stream:
            content=stream.read(32*1024*1024+1)
        if len(content)>32*1024*1024:
            raise ValueError("August price source exceeds safe expanded size.")
        august=json.loads(content.decode("utf-8"))
        if (not isinstance(august,dict) or
                august.get("source_file")!=MASTER_FILE or
                august.get("source_date")!=MASTER_DATE or
                str(august.get("source_sha256","")).lower()!=MASTER_ORIGINAL_SHA256 or
                not isinstance(august.get("rows"),list) or
                not 1<=len(august["rows"])<=20000):
            raise ValueError("Wrong August master source evidence.")
        hashes={key:hashlib.sha256(raw).hexdigest()
                for key,raw in files.items()}
        return {
            "files":files,"hashes":hashes,"counts":{
                "catalogue_rows":len(catalog),"service_configs":len(configs),
                "august_list_price_rows":len(august["rows"]),
                "tariff_groups":len(pricing["rates"]),
                "console_rules":len(pricing["console_rules"]),
            },
            "pricing_status":str(pricing.get("pricing_status") or "No source status")[:100],
            "source_date":MASTER_DATE,
            "bundle_sha256":hashlib.sha256(data).hexdigest(),
        }
    except (OSError,ValueError,UnicodeError,KeyError,IndexError,
            zipfile.BadZipFile,gzip.BadGzipFile,json.JSONDecodeError) as exc:
        raise HTTPException(
            422,"V10 ZIP source is incomplete or unsafe. Select only the four exact source files."
        ) from exc


def _schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS quote_source_bundles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        active INTEGER NOT NULL DEFAULT 0,
        payload BLOB NOT NULL,
        zip_sha256 TEXT NOT NULL UNIQUE,
        hashes_json TEXT NOT NULL,
        counts_json TEXT NOT NULL,
        staged_by TEXT NOT NULL,staged_at TEXT NOT NULL,
        approval_reference TEXT NOT NULL,reason TEXT NOT NULL
    )""")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_quote_active_source "
                "ON quote_source_bundles(active) WHERE active=1")
    con.execute("""CREATE TABLE IF NOT EXISTS quote_source_previews(
        token TEXT PRIMARY KEY,payload BLOB NOT NULL,
        zip_sha256 TEXT NOT NULL,
        expected_active_sha256 TEXT,
        staged_by TEXT NOT NULL,created_at TEXT NOT NULL,
        summary_json TEXT NOT NULL
    )""")


def active_source():
    """Return verified original bytes from the protected source store, or None."""
    with closing(connect()) as db:
        try:
            row=db.execute(
                "SELECT payload,zip_sha256,hashes_json FROM quote_source_bundles "
                "WHERE active=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    if row is None:
        return None
    binary=bytes(row["payload"])
    if hashlib.sha256(binary).hexdigest()!=row["zip_sha256"]:
        raise HTTPException(503,"Protected V10 source bundle integrity check failed.")
    proof=inspect_bundle(binary)
    expected=json.loads(row["hashes_json"])
    if expected!=proof["hashes"]:
        raise HTTPException(503,"V10 source files changed after Administrator approval.")
    return proof


def manifest_status(proofs):
    current=active_source()
    if current is None:
        return None
    expected=current["hashes"]
    # Some callers check only the 3 kernel hashes, others also August RRP.
    if not all(expected.get(k)==v for k,v in proofs.items()) or not all(
        k in expected for k in ("catalog","configs","pricing","august_2026_rrp")
    ):
        raise HTTPException(503,"Source bytes differ from the Admin-pinned V10 manifest.")
    return {
        "pinned":True,"matches":True,
        "manifest_sha256":hashlib.sha256(json.dumps(
            expected,sort_keys=True).encode()).hexdigest(),
        "effective_date_as_recorded":current["source_date"],
        "commercially_approved":False,
        "message":"Exact V10 and August bytes match the Administrator-reviewed source bundle.",
    }


def _active_digest(con):
    try:
        row=con.execute(
            "SELECT zip_sha256 FROM quote_source_bundles WHERE active=1"
        ).fetchone()
        return row["zip_sha256"] if row else None
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise


@router.post("/preview")
async def preview_zip(file:UploadFile=File(...)):
    staff=_admin()
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(422,"Upload a ZIP of the four V10 source files.")
    binary=await file.read(MAX_ZIP+1)
    data=inspect_bundle(binary)
    token=secrets.token_urlsafe(24)
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary={
        "token":token,"source_date":data["source_date"],
        "counts":data["counts"],"hashes":data["hashes"],
        "pricing_status":data["pricing_status"],
        "bundle_sha256":data["bundle_sha256"],
        "customer_quote_issue_enabled":False,
    }
    with closing(connect()) as db:
        _schema(db)
        if _active_digest(db)==data["bundle_sha256"]:
            raise HTTPException(409,"This exact source bundle is already active.")
        db.execute(
            "INSERT INTO quote_source_previews "
            "(token,payload,zip_sha256,expected_active_sha256,"
            "staged_by,created_at,summary_json) VALUES(?,?,?,?,?,?,?)",
            (token,binary,data["bundle_sha256"],_active_digest(db),
             staff,now,json.dumps(summary)),
        )
        db.commit()
    return summary


class ActivateSource(BaseModel):
    token:str
    approval_reference:str
    reason:str
    confirm_original_v10_files:bool
    confirm_august_master_source:bool


@router.post("/activate")
def activate_source(request:ActivateSource):
    staff=_admin()
    if not (request.confirm_original_v10_files and request.confirm_august_master_source):
        raise HTTPException(422,"Verify the original V10 files and the August 2026 Master source.")
    ref=request.approval_reference.strip()
    reason=request.reason.strip()
    if not 8<=len(ref)<=160 or not 12<=len(reason)<=500:
        raise HTTPException(422,"Enter an approval reference and a detailed source verification reason.")
    now=dt.datetime.now(dt.timezone.utc)
    with closing(connect()) as db:
        _schema(db)
        try:
            db.execute("BEGIN IMMEDIATE")
            record=db.execute(
                "SELECT * FROM quote_source_previews WHERE token=?",
                (request.token,),
            ).fetchone()
            if not record or record["staged_by"]!=staff:
                raise HTTPException(404,"Source preview is missing for this Administrator.")
            created=dt.datetime.fromisoformat(record["created_at"])
            if now-created>MAX_AGE:
                raise HTTPException(409,"Source preview expired; inspect files again.")
            if record["expected_active_sha256"]!=_active_digest(db):
                raise HTTPException(409,"Another source bundle became active after your preview.")
            proof=inspect_bundle(bytes(record["payload"]))
            if proof["bundle_sha256"]!=record["zip_sha256"]:
                raise HTTPException(409,"Source ZIP changed after preview.")
            if db.execute("SELECT 1 FROM quote_source_bundles "
                          "WHERE zip_sha256=?",(proof["bundle_sha256"],)).fetchone():
                raise HTTPException(409,"This exact source ZIP was previously activated.")
            db.execute("UPDATE quote_source_bundles SET active=0 WHERE active=1")
            cur=db.execute("""
                INSERT INTO quote_source_bundles(
                active,payload,zip_sha256,hashes_json,counts_json,
                staged_by,staged_at,approval_reference,reason)
                VALUES(1,?,?,?,?,?,?,?,?)
            """,(bytes(record["payload"]),proof["bundle_sha256"],
                 json.dumps(proof["hashes"],sort_keys=True),
                 json.dumps(proof["counts"],sort_keys=True),
                 staff,now.isoformat(timespec="seconds"),ref,reason))
            # Source changes automatically turn OFF the in-app quote release
            # flag, regardless of whether the tariff rules happen to match.
            try:
                current=db.execute(
                    "SELECT payload,revision FROM smartquote_commercial_settings "
                    "WHERE kind='issuance'").fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    current=None
                else:
                    raise
            if current:
                old=json.loads(current["payload"])
                if old.get("enabled"):
                    disabled=json.dumps({"enabled":False},sort_keys=True).encode()
                    newhash=hashlib.sha256(disabled).hexdigest()
                    db.execute(
                        "UPDATE smartquote_commercial_settings SET "
                        "payload=?,sha256=?,revision=revision+1,approval_reference=?,"
                        "reason=?,approved_by=?,approved_at=? WHERE kind='issuance'",
                        (disabled,newhash,ref,"Source ZIP changed; release disabled",
                         staff,now.isoformat(timespec="seconds")),
                    )
                    db.execute(
                        "INSERT INTO smartquote_commercial_settings_audit "
                        "(kind,revision,old_sha256,new_sha256,approved_by,"
                        "approval_reference,reason,approved_at) VALUES(?,?,?,?,?,?,?,?)",
                        ("issuance",current["revision"]+1,
                         hashlib.sha256(current["payload"]).hexdigest(),newhash,
                         staff,ref,"Source ZIP changed; release disabled",
                         now.isoformat(timespec="seconds")),
                    )
            db.execute("DELETE FROM quote_source_previews WHERE token=?",
                       (request.token,))
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "active":True,"version":cur.lastrowid,
        "hashes":proof["hashes"],"counts":proof["counts"],
        "customer_issuance_disabled_until_reapproval":True,
        "source_data_exported_or_written_to_erp":False,
    }


@router.get("/status")
def source_status():
    _admin()
    with closing(connect()) as db:
        try:
            row=db.execute(
                "SELECT id,zip_sha256,counts_json,hashes_json,staged_by,"
                "staged_at,approval_reference FROM quote_source_bundles "
                "WHERE active=1 LIMIT 1"
            ).fetchone()
            older=db.execute(
                "SELECT id,zip_sha256,staged_at,staged_by,active "
                "FROM quote_source_bundles ORDER BY id DESC LIMIT 12"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return {"active":None,"history":[]}
            raise
    return {
        "active":({
            **dict(row),"counts":json.loads(row["counts_json"]),
            "hashes":json.loads(row["hashes_json"]),
        } if row else None),
        "history":[dict(r) for r in older],
        "personal_customer_data_in_source_archive":False,
        "commercial_tariff_approved":False,
    }
