"""Native quotation preparation within Contracts OS.

Draft-only records; intentionally does not invent commercial rates, issue PDFs,
or claim these drafts have been approved by SmartQuote's pricing engine.
"""
from __future__ import annotations
import json
import uuid
from fastapi import APIRouter, HTTPException, Body, Query
from .store import connect, now
from .pilot_access import actor, PILOT_MODE

router = APIRouter(prefix="/api/quoting", tags=["Unified quotation drafts"])
TIERS = {"Silver", "Gold", "Platinum"}
MAX_LINES = 500

def _check_access(write=False):
    identity = actor()
    if write and PILOT_MODE and identity == "Viewer":
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
    equipment=data.get("equipment",[])
    if not isinstance(equipment,list) or len(equipment)>MAX_LINES:
        raise HTTPException(422,"Maximum 500 equipment lines.")
    result=[]
    for i,line in enumerate(equipment):
        if not isinstance(line,dict):
            raise HTTPException(422,f"Equipment line {i+1} must be an object.")
        qty=line.get("quantity",1)
        if type(qty) is not int or qty<1 or qty>10000:
            raise HTTPException(422,"Equipment quantity must be a positive whole number.")
        result.append({"item_code":_clean(line.get("item_code",""),"item_code",100),
                       "description":_clean(line.get("description",""),"description",400,required=True),
                       "serial":_clean(line.get("serial",""),"serial",120),
                       "quantity":qty})
    return {"customer":customer,"site":site,"tier":tier,"contact":contact,
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
    missing_sku = sum(not line["item_code"] for line in record["equipment"])
    if missing_sku:
        issues.append(f"Confirm product codes for {missing_sku} equipment line(s).")
    missing_serials = sum(
        line["quantity"] if not line["serial"] else max(0, line["quantity"] - 1)
        for line in record["equipment"]
    )
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


@router.post("/drafts",status_code=201)
def create_draft(payload:dict=Body(...)):
    user=_check_access(write=True)
    data=validate_draft(payload)
    ref=uuid.uuid4().hex
    with connect() as con:
        _init(con)
        con.execute("INSERT INTO unified_quote_drafts(id,created_at,updated_at,created_by,payload_json) VALUES(?,?,?,?,?)",
                    (ref,now(),now(),str(user),json.dumps(data)))
    return {"id":ref,"revision":1,**data}

@router.put("/drafts/{draft_id}")
def update_draft(draft_id:str,payload:dict=Body(...)):
    _check_access(write=True)
    _validate_id(draft_id)
    revision=payload.get("revision")
    if type(revision) is not int or revision<1:
        raise HTTPException(422,"Revision is required.")
    data=validate_draft(payload)
    with connect() as con:
        _init(con)
        cur=con.execute("UPDATE unified_quote_drafts SET payload_json=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                        (json.dumps(data),now(),draft_id,revision))
        if cur.rowcount!=1:
            exists=con.execute("SELECT 1 FROM unified_quote_drafts WHERE id=?",(draft_id,)).fetchone()
            raise HTTPException(409 if exists else 404,"Draft was modified elsewhere; reload before saving." if exists else "Draft not found.")
    return {"id":draft_id,"revision":revision+1,**data}
