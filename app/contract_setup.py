"""Accepted quote -> guided contract setup workbench (protected pilot).

No Sicon writes occur here. The equipment and contract import plans are explicitly
REVIEW_ONLY, not files suitable for direct Sage/Sicon upload. Real import mapping
still requires the approved Sicon templates and a sandbox import.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from .store import DATA, connect, now
from .pilot_access import actor

router = APIRouter(prefix="/api/smartquote/setups", tags=["Contract setup"])
ACCOUNT = re.compile(r"^[a-zA-Z0-9._/ -]{1,80}$")
HASH = re.compile(r"^[0-9a-fA-F]{64}$")
FREQ = {"Monthly", "Quarterly", "Annual", "Annually", "Yearly", "Six-monthly", "One-off", ""}
MAX_PDF = 15 * 1024 * 1024

def today():
    return dt.date.today()



def ensure_tables(con):
    # Use individual statements rather than executescript: the latter implicitly
    # commits SQLite transactions and could leave half-created setup cases.
    con.execute("""
        CREATE TABLE IF NOT EXISTS smartquote_setup_cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intake_id INTEGER NOT NULL UNIQUE,
            revision INTEGER NOT NULL DEFAULT 1,
            verified_json TEXT NOT NULL DEFAULT '{}',
            signed_document_sha256 TEXT NOT NULL DEFAULT '',
            signed_document_filename TEXT NOT NULL DEFAULT '',
            signed_at TEXT NOT NULL DEFAULT '',
            sicon_contract_reference TEXT NOT NULL DEFAULT '',
            sicon_contract_imported_at TEXT NOT NULL DEFAULT '',
            sicon_equipment_imported_at TEXT NOT NULL DEFAULT '',
            sicon_equipment_batch_reference TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(intake_id) REFERENCES smartquote_intakes(id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS smartquote_setup_equipment_batches(
            case_id INTEGER NOT NULL,
            cover_start TEXT NOT NULL,
            batch_reference TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            PRIMARY KEY(case_id,cover_start),
            FOREIGN KEY(case_id) REFERENCES smartquote_setup_cases(id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS smartquote_setup_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            at TEXT NOT NULL, actor TEXT NOT NULL,
            action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(case_id) REFERENCES smartquote_setup_cases(id)
        )
    """)

def _batches(con, case_id):
    return [dict(x) for x in con.execute(
        "SELECT cover_start,batch_reference,confirmed_at,actor FROM smartquote_setup_equipment_batches WHERE case_id=? ORDER BY cover_start",
        (case_id,)).fetchall()]


def _audit(con, case_id, action, detail=""):
    con.execute("INSERT INTO smartquote_setup_events(case_id,at,actor,action,detail) VALUES(?,?,?,?,?)",
                (case_id, now(), actor(), action, str(detail)[:700]))


def ensure_case(con, intake_id):
    """One case per intake revision, without any extra coordinator step."""
    ensure_tables(con)
    quote = con.execute("SELECT id FROM smartquote_intakes WHERE id=?", (intake_id,)).fetchone()
    if not quote:
        raise HTTPException(404, "Accepted quotation not found")
    con.execute("""
        INSERT OR IGNORE INTO smartquote_setup_cases(intake_id,created_at,updated_at)
        VALUES(?,?,?)
    """, (intake_id, now(), now()))
    return con.execute("SELECT * FROM smartquote_setup_cases WHERE intake_id=?", (intake_id,)).fetchone()


def _case(con, intake_id):
    ensure_tables(con)
    item = con.execute("SELECT * FROM smartquote_intakes WHERE id=?", (intake_id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Accepted quote intake not found")
    case = ensure_case(con, intake_id)
    return item, case, json.loads(item["payload_json"]), json.loads(case["verified_json"])


def _field(name, value):
    value = str(value or "").strip()
    if len(value) > 350 or any(ord(c) < 32 and c not in "\t" for c in value):
        raise HTTPException(422, f"{name} contains unsupported text")
    if name in ("sage_account_ref", "sicon_site_ref", "contract_reference") and value and not ACCOUNT.fullmatch(value):
        raise HTTPException(422, f"{name} contains invalid characters")
    if name == "billing_frequency" and value not in FREQ:
        raise HTTPException(422, "Choose a recognised billing frequency")
    if name == "purchase_order" and len(value) > 100:
        raise HTTPException(422, "Purchase order reference is too long")
    if name == "billing_email" and value and (
        "@" not in value or " " in value or not (3 <= len(value) <= 200)):
        raise HTTPException(422, "Enter a valid billing contact email")
    return value


def _unaccounted(q, verified):
    corrected = verified.get('verified_serials', {})
    return sum(max(0, a['quantity'] - len([x for x in corrected.get(a['source_line_id'], a['serial_numbers']) if x]))
               for a in q['equipment'])


def status(quote, verified, case, batches=()):
    """Derived single review queue; accepted quotation itself is never edited."""
    c, contract = quote["customer"], quote["contract"]
    ref = lambda key, source: verified.get(key) or source or ""
    missing = []
    required = (
        (ref("sage_account_ref", c["sage_account_ref"]), "Confirm Sage customer account"),
        (ref("sicon_site_ref", c["sicon_site_ref"]), "Confirm Sicon equipment site/location"),
        (ref("contract_reference", contract["reference"]), "Allocate verified contract reference"),
        (verified.get("billing_frequency") or contract["payment_terms"], "Confirm invoice frequency"),
        (contract["start_date"], "Confirm the contract start date"),
        (contract["end_date"], "Confirm the common contract end date"),
    )
    for value, label in required:
        if not value:
            missing.append(label)
    if quote["contract"]["package"] == "Mixed":
        missing.append("Specify approved package per machine for mixed-cover contracts")
    if not quote["pricing"]["commercially_approved"]:
        missing.append("Approve maintenance tariff / quote pricing")
    if not quote["pricing"]["source_quote_pdf_sha256"]:
        missing.append("Provide archived accepted quote PDF fingerprint")
    if _unaccounted(quote, verified):
        missing.append(f"Verify {_unaccounted(quote, verified)} missing equipment serial number(s)")
    if any(not a["cover_start"] or not a["cover_end"] for a in quote["equipment"]):
        missing.append("Verify machine commencement and end dates")
    signed = bool(case["signed_document_sha256"])
    agreement_ready = not missing
    contract_import_ready = agreement_ready and signed
    contracted = bool(case["sicon_contract_imported_at"] and case["sicon_contract_reference"])
    start_groups = sorted({a["cover_start"] for a in quote["equipment"] if a["cover_start"]})
    already = {x["cover_start"] for x in batches}
    today = today().isoformat()
    due = [d for d in start_groups if d <= today and d not in already]
    future = [d for d in start_groups if d > today]
    equipment_import_ready = contract_import_ready and contracted and bool(due)
    equipment_imported = bool(start_groups) and all(d in already for d in start_groups)
    return {
        "missing": missing,
        "checked": len(required) - sum(not value for value, _ in required),
        "agreement_ready": agreement_ready,
        "agreement_signed": signed,
        "contract_import_ready": contract_import_ready,
        "contract_import_confirmed": contracted,
        "equipment_import_ready": equipment_import_ready,
        "equipment_import_confirmed": equipment_imported,
        "due_equipment_groups": due,
        "future_equipment_groups": future,
        "imported_equipment_groups": sorted(already),
        "workflow_status": ("Imported — awaiting operational reconciliation" if equipment_imported
                            else "Ready for equipment import" if equipment_import_ready
                            else "Future equipment scheduled" if contracted and future
                            else "Ready for contract import" if contract_import_ready
                            else "Agreement signed — needs setup details" if signed
                            else "Ready for customer signature" if agreement_ready
                            else "Needs details"),
        "units": sum(a["quantity"] for a in quote["equipment"]),
        "stage_dates": sorted({a["cover_start"] for a in quote["equipment"] if a["cover_start"]}),
    }


def _display(con, intake_id):
    item, case, quote, verified = _case(con, intake_id)
    batches=_batches(con,case["id"])
    events = con.execute("""SELECT at,actor,action,detail FROM smartquote_setup_events
                             WHERE case_id=? ORDER BY id""", (case["id"],)).fetchall()
    return {
        "id": case["id"], "intake_id": intake_id, "revision": case["revision"],
        "quote_number": quote["quote_number"], "customer": quote["customer"]["legal_name"],
        "site": quote["customer"]["site_name"],
        "source": {
            "sage_account_ref": quote["customer"]["sage_account_ref"],
            "sicon_site_ref": quote["customer"]["sicon_site_ref"],
            "contract_reference": quote["contract"]["reference"],
            "billing_frequency": quote["contract"]["payment_terms"],
        },
        "verified": verified,
        "signed_document": bool(case["signed_document_sha256"]),
        "signed_filename": case["signed_document_filename"],
        "signed_sha256": case["signed_document_sha256"],
        "sicon_contract_reference": case["sicon_contract_reference"],
        "sicon_contract_imported_at": case["sicon_contract_imported_at"],
        "sicon_equipment_imported_at": case["sicon_equipment_imported_at"],
        "sicon_equipment_batch_reference": case["sicon_equipment_batch_reference"],
        "readiness": status(quote, verified, case, batches),
        "equipment_import_batches": batches,
        "events": [dict(x) for x in events],
    }


@router.get("/upcoming")
def upcoming_start_dates(days: int = 90):
    """Future equipment requiring a commencement check; no automatic activation."""
    days=max(1,min(365,days))
    today=today()
    last=today+dt.timedelta(days=days)
    con=connect()
    try:
        ensure_tables(con)
        rows=con.execute("""
            SELECT s.id AS setup_id,s.intake_id,s.sicon_contract_imported_at,
                   s.sicon_equipment_imported_at,i.quote_number,i.source_quote_id,
                   i.payload_json
            FROM smartquote_setup_cases s JOIN smartquote_intakes i ON i.id=s.intake_id
            WHERE i.id=(SELECT MAX(j.id) FROM smartquote_intakes j
                        WHERE j.source_quote_id=i.source_quote_id)
            ORDER BY i.id DESC
        """).fetchall()
        pending=[]
        for r in rows:
            q=json.loads(r["payload_json"])
            for start in sorted({a["cover_start"] for a in q["equipment"] if a["cover_start"]}):
                date=dt.date.fromisoformat(start)
                if date<today or date>last:
                    continue
                scheduled=[a for a in q["equipment"] if a["cover_start"]==start]
                batch=con.execute("""SELECT 1 FROM smartquote_setup_equipment_batches
                       WHERE case_id=? AND cover_start=?""",(r["setup_id"],start)).fetchone()
                pending.append({
                    "intake_id":r["intake_id"],"quote_number":r["quote_number"],
                    "customer":q["customer"]["legal_name"],"site":q["customer"]["site_name"],
                    "start_date":start,"days_until_start":(date-today).days,
                    "machine_units":sum(a["quantity"] for a in scheduled),
                    "import_recorded":bool(batch),
                    "action":"Check scheduled cover and asset eligibility" if batch else
                       "Arrange dated Sicon equipment import when coverage begins",
                })
        pending.sort(key=lambda x:(x["start_date"],x["quote_number"]))
        return {"window_days":days,"items":pending[:200],"total":len(pending),
                "note":"Date worklist only. It does not activate cover, schedule a service, or write to Sicon."}
    finally:
        con.close()


@router.get("/{intake_id}")
def get_setup(intake_id: int):
    con = connect()
    try:
        result = _display(con, intake_id)
        con.commit()
        return result
    finally:
        con.close()


@router.post("/{intake_id}/details")
def save_details(intake_id: int, payload: dict = Body(...)):
    """One grouped coordinator correction; only verified external metadata, not quote pricing."""
    if not isinstance(payload, dict):
        raise HTTPException(422, "Provide the details to verify")
    keys = {"sage_account_ref", "sicon_site_ref", "contract_reference",
            "billing_frequency", "billing_email", "purchase_order"}
    if not set(payload).issubset(keys | {"revision"}) or not (set(payload) & keys):
        raise HTTPException(422, "Unexpected contract setup field")
    con = connect()
    try:
        item, case, quote, verified = _case(con, intake_id)
        if case["sicon_contract_imported_at"]:
            raise HTTPException(409, "Sicon contract already confirmed. Changes require a controlled variation.")
        if case["revision"] != payload.get("revision"):
            raise HTTPException(409, "This setup was updated by another user. Refresh before saving.")
        changed = {key: _field(key, payload[key]) for key in keys & set(payload)}
        updated = {**verified, **changed}
        # Store only corrections supplied by a coordinator; never rewrite original quote.
        con.execute("""UPDATE smartquote_setup_cases
                       SET verified_json=?,revision=revision+1,updated_at=? WHERE id=?""",
                    (json.dumps(updated), now(), case["id"]))
        _audit(con, case["id"], "SETUP_DETAILS_VERIFIED", ", ".join(sorted(changed)))
        con.commit()
        return _display(con, intake_id)
    finally:
        con.close()


@router.post("/{intake_id}/verify-serials")
def verify_serials(intake_id: int, payload: dict = Body(...)):
    """Correct equipment records with source evidence; never mutate an accepted quote."""
    line_id=str(payload.get("source_line_id","")).strip()
    serials=payload.get("serial_numbers")
    evidence=str(payload.get("evidence","")).strip()[:500]
    if not line_id or not isinstance(serials,list) or len(evidence)<8:
        raise HTTPException(422,"Select a machine, supply its serials and record where you verified them")
    if any(not isinstance(x,str) or len(x)>120 or not x.strip() for x in serials):
        raise HTTPException(422,"Serial numbers must be non-empty and no longer than 120 characters")
    serials=[x.strip() for x in serials]
    if len(set(serials))!=len(serials):
        raise HTTPException(422,"Duplicate serial numbers in the equipment line")
    con=connect()
    try:
        item,case,quote,verified=_case(con,intake_id)
        if case["signed_document_sha256"]:
            raise HTTPException(409,"A signed contract already exists; equipment changes require a contract variation")
        if case["revision"]!=payload.get("revision"):
            raise HTTPException(409,"Another coordinator changed this setup. Refresh the record")
        machine=next((x for x in quote["equipment"] if x["source_line_id"]==line_id),None)
        if machine is None:
            raise HTTPException(404,"Equipment line not found")
        if len(serials)!=machine["quantity"]:
            raise HTTPException(422,"Provide one verified serial number for each physical machine")
        updates=dict(verified.get("verified_serials",{}))
        updates[line_id]=serials
        revised={**verified,"verified_serials":updates}
        con.execute("UPDATE smartquote_setup_cases SET verified_json=?,revision=revision+1,updated_at=? WHERE id=?",
                    (json.dumps(revised),now(),case["id"]))
        _audit(con,case["id"],"EQUIPMENT_SERIALS_VERIFIED",f"{line_id} ({len(serials)} serials); source: {evidence}")
        con.commit()
        return _display(con,intake_id)
    finally:
        con.close()


@router.post("/{intake_id}/signed-agreement")
def record_signed(intake_id: int, payload: dict = Body(...)):
    """Store PDF evidence securely in private runtime, never source repo."""
    encoded = payload.get("pdf_base64", "")
    filename = str(payload.get("filename", "signed_agreement.pdf"))[:150]
    if not filename.lower().endswith(".pdf") or "/" in filename or "\\" in filename:
        raise HTTPException(422, "Choose a signed PDF agreement")
    if not isinstance(encoded, str) or len(encoded) > ((MAX_PDF * 4 // 3) + 10):
        raise HTTPException(413, "Signed agreement PDF exceeds the 15 MB limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Unable to read signed PDF") from exc
    if not data.startswith(b"%PDF-") or len(data) > MAX_PDF or not data.rstrip().endswith(b"%%EOF"):
        raise HTTPException(422, "Signed agreement must be a complete PDF under 15 MB")
    # Upload alone is not evidence of a signed agreement; a coordinator must
    # explicitly attest that the required signatures were checked.
    if payload.get("signatures_checked") is not True:
        raise HTTPException(422,"Confirm that the signed agreement has been checked")
    digest = hashlib.sha256(data).hexdigest()
    con = connect()
    try:
        item, case, quote, verified = _case(con, intake_id)
        if case["sicon_contract_imported_at"]:
            raise HTTPException(409, "Signed agreement already handed over to Sicon; use controlled variation workflow.")
        if not status(quote, verified, case)["agreement_ready"]:
            raise HTTPException(409, "Resolve the listed setup exceptions before recording the signed agreement.")
        if case["signed_document_sha256"]:
            if case["signed_document_sha256"] == digest:
                return _display(con, intake_id)
            raise HTTPException(409, "A different signed version already exists. Review a variation before replacing it.")
        folder = Path(DATA) / "private_signed_agreements"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(folder, 0o700)
        except OSError:
            pass
        path = folder / f"{case['id']}_{digest}.pdf"
        # Exclusive creation avoids changing evidence already recorded elsewhere.
        with path.open("xb") as fp:
            fp.write(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        con.execute("""UPDATE smartquote_setup_cases
                   SET signed_document_sha256=?,signed_document_filename=?,signed_at=?,
                       revision=revision+1,updated_at=? WHERE id=?""",
                    (digest,filename,now(),now(),case["id"]))
        _audit(con,case["id"],"SIGNED_AGREEMENT_RECEIVED","Document SHA-256 "+digest)
        con.commit()
        return _display(con, intake_id)
    finally:
        con.close()


def _plan(quote, verified, case, ready):
    c, contract = quote["customer"], quote["contract"]
    ref = lambda key, source: verified.get(key) or source or ""
    # Names deliberately NOT claimed to be mapped Sage/Sicon import column names.
    contract_rows = []
    for start in sorted({a["cover_start"] for a in quote["equipment"]}):
        group = [a for a in quote["equipment"] if a["cover_start"] == start]
        contract_rows.append({
            "contract_reference": ref("contract_reference", contract["reference"]),
            "sage_account_ref": ref("sage_account_ref",c["sage_account_ref"]),
            "sicon_site_ref": ref("sicon_site_ref",c["sicon_site_ref"]),
            "cover_start": start, "cover_end": contract["end_date"],
            "cover_package": contract["package"],
            "machine_units": sum(a["quantity"] for a in group),
            "annual_equipment_value": round(sum(a["annual_total"] for a in group),2),
            "initial_period_value": round(sum(a["first_period_total"] for a in group),2),
            "billing_frequency": ref("billing_frequency",contract["payment_terms"]),
            "purchase_order":verified.get("purchase_order",""),
            "billing_email":verified.get("billing_email",""),
            "status":"Scheduled" if start and start>today().isoformat() else "Commencement due/commenced",
        })
    machine_rows = []
    for a in quote["equipment"]:
        for offset in range(a["quantity"]):
            serials=verified.get('verified_serials',{}).get(a['source_line_id'],a['serial_numbers'])
            serial = serials[offset] if offset < len(serials) else ""
            machine_rows.append({
                "contract_reference":ref("contract_reference",contract["reference"]),
                "sicon_contract_reference":case["sicon_contract_reference"],
                "site_reference":ref("sicon_site_ref",c["sicon_site_ref"]),
                "quote_line_id":a["source_line_id"],"item_code":a["item_code"],
                "model":a["model"],"description":a["description"],
                "serial_number":serial,"coverage_start":a["cover_start"],
                "coverage_end":a["cover_end"],"equipment_status":
                    "Scheduled" if a["cover_start"] and a["cover_start"]>today().isoformat() else "Commencement due/commenced",
                "requires_review":not bool(serial),
                "eligible_for_import_now": bool(a["cover_start"] and a["cover_start"]<=today().isoformat()),
                "import_batch_recorded": a["cover_start"] in ready["imported_equipment_groups"],
            })
    return {
        "warning":"REVIEW_ONLY_MAPPING_PLAN_NOT_A_SICON_IMPORT",
        "note":"Contract and equipment require separate verified Sicon templates. Staged future machines must not be activated early.",
        "source_quote":quote["quote_number"],
        "source_pdf_sha256":quote["pricing"]["source_quote_pdf_sha256"],
        "contract_import":{"ready_to_prepare":ready["contract_import_ready"],
                           "external_import_confirmed":ready["contract_import_confirmed"],
                           "staged_billing_groups":contract_rows,
                           "awaiting_actual_sicon_template_mapping":True},
        "equipment_import":{"ready_to_prepare":ready["equipment_import_ready"],
                            "external_import_confirmed":ready["equipment_import_confirmed"],
                            "individual_machine_records":machine_rows,
                            "awaiting_actual_sicon_template_mapping":True},
    }


@router.get("/{intake_id}/plans")
def get_import_plans(intake_id: int):
    con = connect()
    try:
        item, case, quote, verified = _case(con, intake_id)
        con.commit()
        return _plan(quote,verified,case,status(quote,verified,case,_batches(con,case["id"])))
    finally:
        con.close()


@router.post("/{intake_id}/confirm-sicon-contract")
def confirm_contract_import(intake_id: int,payload: dict = Body(...)):
    """Record an external verified Sicon import, never perform it."""
    ref = str(payload.get("sicon_contract_reference","")).strip()
    note = str(payload.get("evidence","")).strip()[:500]
    if not ACCOUNT.fullmatch(ref) or len(note)<8:
        raise HTTPException(422, "Enter the verified Sicon contract reference and import evidence")
    con = connect()
    try:
        item, case, quote, verified = _case(con, intake_id)
        if case["sicon_contract_imported_at"]:
            if case["sicon_contract_reference"] == ref:
                return _display(con, intake_id)
            raise HTTPException(409,"Sicon contract reference is already recorded")
        if not status(quote,verified,case)["contract_import_ready"]:
            raise HTTPException(409,"Signed agreement and setup details must be complete first")
        con.execute("""UPDATE smartquote_setup_cases SET sicon_contract_reference=?,
                 sicon_contract_imported_at=?,revision=revision+1,updated_at=? WHERE id=?""",
                    (ref,now(),now(),case["id"]))
        _audit(con,case["id"],"SICON_CONTRACT_IMPORT_CONFIRMED",f"{ref}: {note}")
        con.commit()
        return _display(con, intake_id)
    finally:
        con.close()


@router.post("/{intake_id}/confirm-sicon-equipment")
def confirm_equipment_import(intake_id: int,payload: dict = Body(...)):
    """Confirm a single coverage-date batch, never future cover before commencement."""
    reference = str(payload.get("sicon_equipment_batch_reference","")).strip()
    evidence = str(payload.get("evidence","")).strip()[:500]
    if not ACCOUNT.fullmatch(reference) or len(evidence)<8:
        raise HTTPException(422,"Enter equipment import batch reference and evidence")
    con=connect()
    try:
        item,case,quote,verified=_case(con,intake_id)
        batches=_batches(con,case["id"])
        dates=sorted({a["cover_start"] for a in quote["equipment"] if a["cover_start"]})
        requested=str(payload.get("start_date","")).strip()
        if not requested:
            due=[d for d in dates if d<=today().isoformat() and d not in {b["cover_start"] for b in batches}]
            if len(due)!=1:
                raise HTTPException(422,"Select the exact equipment commencement group to confirm")
            requested=due[0]
        if requested not in dates:
            raise HTTPException(422,"Selected equipment date is not in this accepted agreement")
        if requested>today().isoformat():
            raise HTTPException(409,"Future-dated equipment cannot be recorded as imported before its cover starts")
        previous=next((x for x in batches if x["cover_start"]==requested),None)
        if previous:
            if previous["batch_reference"]==reference:
                return _display(con,intake_id)
            raise HTTPException(409,"Equipment commencement group already has a different Sicon batch reference")
        if not status(quote,verified,case,batches)["equipment_import_ready"]:
            raise HTTPException(409,"Confirm contract import and required details before equipment")
        con.execute("""INSERT INTO smartquote_setup_equipment_batches(
                 case_id,cover_start,batch_reference,confirmed_at,actor) VALUES (?,?,?,?,?)""",
                 (case["id"],requested,reference,now(),actor()))
        count=con.execute("SELECT COUNT(*) FROM smartquote_setup_equipment_batches WHERE case_id=?",
                          (case["id"],)).fetchone()[0]
        completed=count==len(dates)
        con.execute("""UPDATE smartquote_setup_cases SET
                       sicon_equipment_batch_reference=?,
                       sicon_equipment_imported_at=?,revision=revision+1,updated_at=? WHERE id=?""",
                    (reference,now() if completed else "",now(),case["id"]))
        _audit(con,case["id"],"SICON_EQUIPMENT_DATE_BATCH_CONFIRMED",
               f"Cover starts {requested}; batch {reference}; evidence: {evidence}")
        con.commit()
        return _display(con,intake_id)
    finally:
        con.close()
