"""Native quotation preparation within Contracts OS.

Draft-only records; intentionally does not invent commercial rates, issue PDFs,
or claim these drafts have been approved by SmartQuote's pricing engine.
"""
from __future__ import annotations
import json
import uuid
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, HTTPException, Body, Query
from .store import connect, now
from .pilot_access import actor, PILOT_MODE, current_role
from ._smartquote_staged_v10 import parse_date, valid_contract

router = APIRouter(prefix="/api/quoting", tags=["Unified quotation drafts"])
TIERS = {"Silver", "Gold", "Platinum"}
MAX_LINES = 500

# Shared physical-unit check for both coordinator draft readiness and final
# commercial approval. Keep serial exception counts consistent across screens.
SERIAL_PLACEHOLDERS = frozenset({"N/A", "NA", "NONE", "UNKNOWN", "TBC", "TBD", "-", "?"})


def unconfirmed_serials(equipment):
    """Return physical equipment units without unique verified serial numbers.

    A quantity-two row with one serial verifies only one physical unit.
    Historical drafts may contain duplicates; those cannot verify two units.
    """
    missing = []
    seen = set()
    for i, item in enumerate(equipment, 1):
        quantity = item.get("quantity")
        if type(quantity) is not int or quantity < 1:
            continue
        serial = " ".join(str(item.get("serial") or "").strip().upper().split())
        valid = bool(serial) and serial not in SERIAL_PLACEHOLDERS and serial not in seen
        if valid:
            seen.add(serial)
        remaining = quantity - int(valid)
        if remaining:
            missing.append({"line": i, "unconfirmed_units": remaining})
    return {"total": sum(row["unconfirmed_units"] for row in missing), "lines": missing}

def _check_access(write=False):
    identity = actor()
    if PILOT_MODE:
        role = current_role()
        if role is None:
            raise HTTPException(401, "A verified pilot session is required.")
        if write and role == "Viewer":
            raise HTTPException(403, "Viewer cannot modify quotation drafts.")
    return identity

def _init(con):
    con.execute("""CREATE TABLE IF NOT EXISTS unified_quote_drafts(
      id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      created_by TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
      payload_json TEXT NOT NULL)""")

def _clean(value, field, size=250, required=False):
    if not isinstance(value, str):
        raise HTTPException(422, f"{field} must be text.")
    value = value.strip()
    if len(value)>size or any(ord(c)<32 and c not in "\t\n" for c in value):
        raise HTTPException(422, f"Invalid {field}.")
    if required and not value:
        raise HTTPException(422, f"{field} is required.")
    return value

def validate_draft(data):
    if not isinstance(data, dict):
        raise HTTPException(422,"Quotation must be an object.")
    customer=_clean(data.get("customer",""),"customer",required=True)
    site=_clean(data.get("site",""),"site",required=True)
    tier=data.get("tier","Gold")
    if tier not in TIERS:
        raise HTTPException(422,"Choose Silver, Gold or Platinum.")
    contact=_clean(data.get("contact",""),"contact")
    source_contract_id = data.get("source_contract_id")
    if source_contract_id in ("", None):
        source_contract_id = None
    elif type(source_contract_id) is not int or source_contract_id < 1:
        raise HTTPException(422, "Source site reference must be an existing record ID.")
    term = data.get("term_years", 1)
    if type(term) is not int or not 1 <= term <= 5:
        raise HTTPException(422, "Contract term must be 1–5 whole years.")
    raw_discount = data.get("discount_percent", 0)
    if type(raw_discount) not in (int, float, str) or str(raw_discount).strip() == "":
        raise HTTPException(422, "Discount must be a number between 0% and 100%.")
    try:
        discount = Decimal(str(raw_discount))
        if not discount.is_finite() or not 0 <= discount <= 100 or discount.as_tuple().exponent < -2:
            raise InvalidOperation()
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "Discount must be between 0% and 100%, with at most two decimals.")
    contract_start = _clean(data.get("contract_start", ""), "contract_start", 10)
    contract_end = _clean(data.get("contract_end", ""), "contract_end", 10)
    # Original SmartQuote permits a partially prepared contract draft.
    for entered in (contract_start, contract_end):
        if entered:
            try:
                parse_date(entered)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
    if contract_start and contract_end:
        try:
            valid_contract(contract_start, contract_end)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    equipment=data.get("equipment",[])
    if not isinstance(equipment,list) or len(equipment)>MAX_LINES:
        raise HTTPException(422,"Maximum 500 equipment lines.")
    result=[]
    seen_serials={}
    for i,line in enumerate(equipment):
        if not isinstance(line,dict):
            raise HTTPException(422,f"Equipment line {i+1} must be an object.")
        qty=line.get("quantity",1)
        if type(qty) is not int or qty<1 or qty>10000:
            raise HTTPException(422,"Equipment quantity must be a positive whole number.")
        cover_start = _clean(line.get("cover_start", ""), "cover_start", 10)
        if cover_start:
            try:
                first = parse_date(cover_start)
                if contract_start and contract_end:
                    begin, finish = valid_contract(contract_start, contract_end)
                    if not begin <= first <= finish:
                        raise ValueError("Equipment cover start must be within the contract period.")
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        # PDF source provenance is attached to the DRAFT only. A printed
        # item code does not become approved maintenance equipment.
        source_id = line.get("source_import_id")
        if source_id in ("", None):
            source_id = None
        elif type(source_id) is not int or source_id < 1:
            raise HTTPException(422, f"Equipment line {i+1}: invalid invoice source ID.")
        # Invoice machine identity must be explicitly accepted by the
        # coordinator. A detected PDF code is never automatically a confirmed
        # match, even if its SKU exists in the unified Master price list.
        confirmed = line.get("invoice_match_confirmed", False)
        if type(confirmed) is not bool:
            raise HTTPException(422, f"Equipment line {i+1}: invalid invoice confirmation.")
        if source_id is not None and not confirmed:
            raise HTTPException(
                422,
                f"Equipment line {i+1}: coordinator must explicitly confirm "
                "the invoice code matches the exact equipment before attaching invoice evidence."
            )
        if source_id is None and confirmed:
            raise HTTPException(
                422,
                f"Equipment line {i+1}: an invoice confirmation must reference "
                "the actual source PDF."
            )
        match_method = line.get(
            "invoice_match_method",
            "manual_confirmed" if confirmed else "",
        )
        if not isinstance(match_method, str) or match_method not in (
                "", "manual_confirmed", "auto_exact_master"):
            raise HTTPException(
                422, f"Equipment line {i+1}: invalid invoice match method."
            )
        if (confirmed and not match_method
                or not confirmed and match_method):
            raise HTTPException(
                422, f"Equipment line {i+1}: invoice match state is inconsistent."
            )
        pages = line.get("source_pages", [])
        if not isinstance(pages, list) or len(pages)>30 or any(
            type(page) is not int or not 1 <= page <= 9999 for page in pages
        ):
            raise HTTPException(422, f"Equipment line {i+1}: invalid invoice page references.")
        pages = sorted(set(pages))
        if pages and source_id is None:
            raise HTTPException(422, f"Equipment line {i+1}: pages require a source invoice.")
        serial=_clean(line.get("serial",""),"serial",120)
        serial_key=serial.casefold()
        if serial_key and serial_key in seen_serials:
            raise HTTPException(
                422, f"Equipment serial on line {i+1} is already entered on "
                f"line {seen_serials[serial_key]}. Check for duplicate machines."
            )
        if serial_key:
            seen_serials[serial_key]=i+1
        # Rates are user-selected INTERNAL draft assumptions, never approved tariffs.
        rate_raw = line.get("annual_rate_percent")
        fixed_raw = line.get("fixed_annual_unit_gbp")
        def optional_rate(raw, title, maximum, fraction):
            if raw is None or raw == "":
                return None
            try:
                value = Decimal(str(raw))
                if (not value.is_finite() or not 0 <= value <= maximum
                        or value != value.quantize(fraction)):
                    raise InvalidOperation()
                return str(value)
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise HTTPException(422, f"Equipment line {i+1}: invalid {title}.") from exc
        rate = optional_rate(rate_raw, "service percentage", 100, Decimal("0.0001"))
        fixed = optional_rate(fixed_raw, "fixed annual charge", 1000000, Decimal("0.01"))
        result.append({"item_code":_clean(line.get("item_code",""),"item_code",100),
                       "description":_clean(line.get("description",""),"description",400,required=True),
                       "serial":serial,
                       "cover_start":cover_start, "quantity":qty,
                       "source_import_id":source_id, "source_pages":pages,
                       "invoice_match_confirmed":confirmed,
                       "invoice_match_method":match_method,
                       "annual_rate_percent":rate,
                       "fixed_annual_unit_gbp":fixed,
                       "quantity_verified":line.get("quantity_verified", match_method != "auto_exact_master")})
    return {"customer":customer,"site":site,"tier":tier,"contact":contact,
            "term_years":term,"discount_percent":float(discount),
            "contract_start":contract_start,"contract_end":contract_end,
            "source_contract_id":source_contract_id,
            "equipment":result,"commercial_status":"Unpriced draft",
            "price":None,"approved":False}

@router.get("/drafts")
def drafts(limit:int=Query(100,ge=1,le=500)):
    _check_access()
    with connect() as con:
        _init(con)
        items=con.execute("SELECT id,created_at,updated_at,revision,payload_json FROM unified_quote_drafts ORDER BY updated_at DESC LIMIT ?",(limit,)).fetchall()
        return {"items":[{"id":r["id"],"created_at":r["created_at"],"updated_at":r["updated_at"],"revision":r["revision"],**json.loads(r["payload_json"])} for r in items]}

def _validate_id(draft_id: str):
    if len(draft_id) != 32 or any(c not in "0123456789abcdef" for c in draft_id):
        raise HTTPException(422, "Invalid draft ID.")
    return draft_id


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    _check_access()
    _validate_id(draft_id)
    with connect() as con:
        _init(con)
        row = con.execute(
            "SELECT id, created_at, updated_at, revision, payload_json FROM unified_quote_drafts WHERE id=?",
            (draft_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Quotation draft not found.")
    return {
        "id": row["id"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], "revision": row["revision"],
        **json.loads(row["payload_json"]),
    }


@router.get("/drafts/{draft_id}/readiness")
def draft_readiness(draft_id: str):
    """Operational review, not pricing authority or a promise of contract readiness."""
    record = get_draft(draft_id)
    issues = []
    if not record["equipment"]:
        issues.append("Add equipment before requesting commercial pricing.")
    if not record.get("contract_start") or not record.get("contract_end"):
        issues.append("Confirm the common contract start/end dates before staged cover can be finalised.")
    missing_sku = sum(not line["item_code"] for line in record["equipment"])
    if missing_sku:
        issues.append(f"Confirm product codes for {missing_sku} equipment line(s).")
    missing_serials = unconfirmed_serials(record["equipment"])["total"]
    if missing_serials:
        issues.append(f"Verify {missing_serials} equipment serial number(s).")
    issues.append("Price all equipment using the approved SmartQuote pricing engine.")
    issues.append("Obtain commercial approval and archive the issued PDF before acceptance.")
    return {
        "id": draft_id, "review_issues": issues,
        "equipment_lines": len(record["equipment"]),
        "equipment_units": sum(item["quantity"] for item in record["equipment"]),
        "pricing_ready": False, "contract_setup_ready": False,
    }


def verify_source_site_link(data):
    """Recheck exact original site label; legal customer name is never inferred."""
    source_id = data.get("source_contract_id")
    if source_id is None:
        return
    with connect() as db:
        row = db.execute(
            "SELECT fields FROM contracts WHERE id=?", (source_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(409, "The selected source site no longer exists.")
    try:
        original = json.loads(row["fields"])
    except (ValueError,TypeError) as exc:
        raise HTTPException(409, "The selected source row cannot be verified.") from exc
    label = str(original.get("Customer / site") or "").strip()
    if not label or label != data["site"]:
        raise HTTPException(
            409, "Site label changed or does not match the source record. Select it again."
        )




def verify_invoice_evidence_link(data):
    """Only allow PDF/source references that actually contain this exact code.

    A separate coordinator confirmation is required before these source
    references can be attached to an equipment line. This still does not
    certify maintenance suitability, ownership, warranties or tariffs. It only
    proves the source PDF was uploaded and its code extraction is preserved
    for later staff audit. A manual correction drops its invoice link unless
    the corrected code also exists on the source evidence.
    """
    sourced=[line for line in data["equipment"] if line.get("source_import_id")]
    if not sourced:
        return
    ids=sorted({line["source_import_id"] for line in sourced})
    with connect() as con:
        rows={}
        for source_id in ids:
            record=con.execute(
                "SELECT type,evidence_json FROM imports WHERE id=?", (source_id,)
            ).fetchone()
            if record is None or record["type"]!="pdf":
                raise HTTPException(409, "A referenced source invoice no longer exists.")
            try:
                evidence=json.loads(record["evidence_json"] or "{}")
            except (ValueError, TypeError) as exc:
                raise HTTPException(409, "The referenced invoice evidence is damaged.") from exc
            found={}
            for item in evidence.get("equipment_codes", []):
                if not isinstance(item,dict):
                    continue
                code=str(item.get("value") or "").strip().upper()
                if not code:
                    continue
                pages={
                    page for page in (item.get("pages") or [])
                    if type(page) is int and 1 <= page <= 9999
                }
                found.setdefault(code,set()).update(pages)
            rows[source_id]=found
    auto_lines = [line for line in sourced
                  if line.get("invoice_match_method") == "auto_exact_master"]
    if auto_lines:
        from .quote_price_book import active_book
        from .quote_invoice_match import classify_sku
        price_book = active_book()
        if price_book is None:
            raise HTTPException(
                409, "Cannot verify automatic invoice matches: the unified "
                "Master Price List is not active."
            )
        for line in auto_lines:
            matched = classify_sku(
                str(line["item_code"]).strip().upper(), price_book
            )
            if not matched["auto_add_equipment"]:
                raise HTTPException(
                    409, "An automatically matched invoice code is no longer "
                    "a uniquely priced equipment code in the active Master. "
                    "Re-import or review this line before saving."
                )
            # The Master evidence is server-owned, not accepted from client.
            line["invoice_match_master_revision"] = price_book["revision"]
            line["invoice_match_master_sha256"] = price_book["sha256"]
    for line in sourced:
        code=str(line["item_code"]).strip().upper()
        pages=rows[line["source_import_id"]].get(code)
        if pages is None:
            raise HTTPException(
                409, "This item code is not evidenced by the selected source invoice. "
                "Verify the code and select it again, or enter it manually without an invoice link."
            )
        if line["source_pages"] and not set(line["source_pages"]).issubset(pages):
            raise HTTPException(409, "This equipment page reference does not match the invoice evidence.")


def _stamp_invoice_match_decisions(data, coordinator, previous=None):
    """Server-owned actor/time evidence for explicitly confirmed PDF matches.

    Confirmation is tied to the exact source PDF, SKU, description and pages.
    Editing any of those details requires a fresh coordinator confirmation.
    Client-provided audit fields are ignored by validate_draft().
    """
    prior = previous.get("equipment", []) if isinstance(previous, dict) else []
    stamped = now()
    for line in data["equipment"]:
        if not line.get("source_import_id") or not line.get("invoice_match_confirmed"):
            continue
        original = next((old for old in prior if (
            old.get("invoice_match_confirmed") is True and
            old.get("source_import_id") == line["source_import_id"] and
            str(old.get("item_code") or "").strip().upper() == line["item_code"].strip().upper() and
            old.get("description") == line["description"] and
            old.get("source_pages") == line["source_pages"] and
            old.get("invoice_match_method", "manual_confirmed") ==
                line.get("invoice_match_method") and
            old.get("invoice_match_master_sha256") ==
                line.get("invoice_match_master_sha256") and
            old.get("invoice_match_confirmed_by") and
            old.get("invoice_match_confirmed_at")
        )), None)
        if original:
            line["invoice_match_confirmed_by"] = original["invoice_match_confirmed_by"]
            line["invoice_match_confirmed_at"] = original["invoice_match_confirmed_at"]
        else:
            line["invoice_match_confirmed_by"] = (
                "Automatic exact Master SKU match"
                if line.get("invoice_match_method") == "auto_exact_master"
                else str(coordinator)[:120]
            )
            line["invoice_match_confirmed_at"] = stamped


@router.post("/drafts",status_code=201)
def create_draft(payload:dict=Body(...)):
    user=_check_access(write=True)
    data=validate_draft(payload)
    verify_source_site_link(data)
    verify_invoice_evidence_link(data)
    _stamp_invoice_match_decisions(data, user)
    ref=uuid.uuid4().hex
    with connect() as con:
        _init(con)
        con.execute("INSERT INTO unified_quote_drafts(id,created_at,updated_at,created_by,payload_json) VALUES(?,?,?,?,?)",
                    (ref,now(),now(),str(user),json.dumps(data)))
    return {"id":ref,"revision":1,**data}

@router.put("/drafts/{draft_id}")
def update_draft(draft_id:str,payload:dict=Body(...)):
    user=_check_access(write=True)
    _validate_id(draft_id)
    revision=payload.get("revision")
    if type(revision) is not int or revision<1:
        raise HTTPException(422,"Revision is required.")
    data=validate_draft(payload)
    verify_source_site_link(data)
    verify_invoice_evidence_link(data)
    with connect() as con:
        _init(con)
        old=con.execute(
            "SELECT revision,payload_json FROM unified_quote_drafts WHERE id=?",
            (draft_id,)
        ).fetchone()
        previous=json.loads(old["payload_json"]) if old and old["revision"] == revision else None
        _stamp_invoice_match_decisions(data, user, previous)
        cur=con.execute("UPDATE unified_quote_drafts SET payload_json=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                        (json.dumps(data),now(),draft_id,revision))
        if cur.rowcount!=1:
            exists=con.execute("SELECT 1 FROM unified_quote_drafts WHERE id=?",(draft_id,)).fetchone()
            raise HTTPException(409 if exists else 404,"Draft was modified elsewhere; reload before saving." if exists else "Draft not found.")
    return {"id":draft_id,"revision":revision+1,**data}
