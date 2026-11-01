"""Optional Sicon WebAPI integration boundary for Pulse Contracts.

The production transport is deliberately NOT implemented. No credentials, API
keys or Sicon server are needed for any coordinator operation. Public, read-only
planning endpoints expose the intended API write *sequence*, not executable
payloads. The approved/manual agreement and Excel import process stays primary.

Schema references:
- Contracts Release 26: /api/Contract/CreateUpdateContract,
  /api/ContractLine/PostContractLine
- Common Components Release 26: /api/SiconEquipment/PostNewEquipment

Do not add an HTTP client to this module until independent sandbox verification
covers Sicon-generated identifiers, pricing, duplicate detection and retry rules.
"""
from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from .store import connect

router = APIRouter(prefix="/api/smartquote/sicon", tags=["Sicon integration preview"])

DOCS = {
    "contract": "https://webapidocs.blob.core.windows.net/published/Contracts.R260200c.json",
    "equipment": "https://webapidocs.blob.core.windows.net/published/CC.R260200c.json",
}
WRITE_ENABLED = False  # Does not read credentials, keys or an enable flag.


def integration_status() -> dict[str, Any]:
    """No network; no secrets; manual remains available even with stray env vars."""
    return {
        "mode": "manual_excel",
        "api_connected": False,
        "api_write_enabled": WRITE_ENABLED,
        "requires_api_credentials": False,
        "documents_available_without_api": True,
        "manual_contract_import": True,
        "manual_equipment_import": True,
        "manual_import_confirmation": True,
        "notes": (
            "Contracts OS works without Sicon API access. The coordinator can "
            "prepare the maintenance agreement and separate review-only Excel "
            "templates, import after Sicon mapping approval, and record the "
            "external contract and equipment batch references."
        ),
        "api_stage": "Documentation-backed mapping preview only; no requests to Sicon.",
    }


def _decimal_sum(rows: list[dict], key: str) -> str:
    return str(sum((Decimal(str(r[key])) for r in rows), Decimal("0")).quantize(Decimal("0.01")))


def build_api_preview(quote: dict, verified: dict, case: Any, today: dt.date | None = None) -> dict:
    """Schema-guided NON-EXECUTABLE operation plan; never mutates input or Sicon.

    Deliberately excludes default values for undocumented/required billing
    properties. Never mistake contract NUMBER for numeric ContractID. The API
    field 'UnitPrice' is not assumed to match our annualised quote amount.
    """
    today = today or dt.date.today()
    customer = quote["customer"]
    contract = quote["contract"]
    account = verified.get("sage_account_ref") or customer.get("sage_account_ref") or ""
    ref = verified.get("contract_reference") or contract.get("reference") or ""
    order = verified.get("purchase_order", "")
    item_code = verified.get("billing_stock_code", "")

    contract_header = {
        "endpoint": "POST /api/Contract/CreateUpdateContract",
        "proposed_fields": {
            "ContractNumber": ref or None,
            "CustomerNumber": account or None,
            "Description": f'{customer["site_name"]} - {contract["package"]} maintenance',
            "CustomerOrderNumber": order or None,
        },
        "missing": ([label for label, value in (
            ("Verified Sage customer account", account),
            ("Approved new/existing Sicon contract number", ref),
        ) if not value]
            + ["Existing ContractID must be verified for updates; do not guess or overwrite"]),
        "api_response_needed": ["ContractID", "ContractNumber"],
        "can_send": False,
    }

    groups = []
    for day in sorted({line["cover_start"] for line in quote["equipment"] if line["cover_start"]}):
        machines = [line for line in quote["equipment"] if line["cover_start"] == day]
        groups.append({
            "endpoint": "POST /api/ContractLine/PostContractLine",
            "start_date": day,
            "end_date": contract.get("end_date", ""),
            "equipment_count": sum(line["quantity"] for line in machines),
            "accepted_annualised_value": _decimal_sum(machines, "annual_total"),
            "accepted_first_period_value": _decimal_sum(machines, "first_period_total"),
            "proposed_fields": {
                "ItemCode": item_code or None,  # Billing product, NOT machine SKU
                "ContractStartDate": f"{day}T00:00:00",
                "ContractEndDate": f'{contract["end_date"]}T00:00:00' if contract.get("end_date") else None,
                "InternalDescription": f'Maintenance cover from {day} to {contract.get("end_date", "")}',
                # Required model fields left explicitly unresolved:
                "SiconContractID": None,
                "SiconContractLineID": None,
                "UnitPrice": None,
                "ProRata": None,
            },
            "missing": [
                "Sicon-generated ContractID from a verified header response",
                "SiconContractLineID create/update semantics and returned line ID",
                "Sicon UnitPrice/PriceInterval/invoice interval and pro-rata reconciliation",
                "Required ContractLine fields and defaults in this installed Sicon version",
                "Approved billing stock item and delivery address/warehouse IDs",
            ],
            "can_send": False,
        })

    equipment = []
    for line in quote["equipment"]:
        serials = verified.get("verified_serials", {}).get(line["source_line_id"], line["serial_numbers"])
        for index in range(line["quantity"]):
            serial = serials[index] if index < len(serials) else ""
            equipment.append({
                "endpoint": "POST /api/SiconEquipment/PostNewEquipment",
                "source_line_id": line["source_line_id"],
                "stock_code": line["item_code"],
                "serial_number": serial or None,
                "cover_start": line["cover_start"],
                "cover_due": bool(line["cover_start"] and line["cover_start"] <= today.isoformat()),
                "proposed_fields": {
                    "ItemCode": line["item_code"],
                    "SerialNumber": serial or None,
                    "Make": line.get("make") or verified.get("equipment_make") or None,
                    "Model": line.get("model") or None,
                    "SiconContractID": None,
                    "SiconContractLineID": None,
                    "CustomerID": None,
                    "ItemID": None,
                    "EquipmentID": None,
                },
                "missing": [
                    "Existing equipment duplicate/asset history check",
                    "Verified Sicon CustomerID, ItemID and EquipmentID create semantics",
                    "Returned numeric SiconContractID and SiconContractLineID",
                    "Approved equipment installation/warranty/service metadata",
                ] + (["Missing verified serial number"] if not serial else [])
                  + (["Future cover date: do not activate early"] if line["cover_start"] > today.isoformat() else []),
                "can_send": False,
            })

    return {
        "preview_only": True,
        "api_write_enabled": WRITE_ENABLED,
        "requires_credentials_to_preview": False,
        "source_quote": quote["quote_number"],
        "source_accepted_pdf_sha256": quote["pricing"]["source_quote_pdf_sha256"],
        "sequence": [
            "Verify customer and IDs (read-only lookup when available)",
            "Create/verify contract header and capture numeric ContractID",
            "Create staged contract lines, reconcile invoices and capture line IDs",
            "Check existing serialised machines before creating or associating equipment",
            "Independently verify Sicon results and retain audit evidence",
        ],
        "contract": contract_header,
        "lines": groups,
        "equipment": equipment,
        "manual_workflow_unaffected": True,
        "blockers": [
            "Integration has no live Sicon connection or write transport",
            "No sandbox-verified Sicon contract-line response identifier",
            "No approved invoice/proration or duplicate equipment mapping",
        ],
        "documentation": DOCS,
    }


@router.get("/status")
def get_status():
    return integration_status()


@router.get("/setups/{intake_id}/preview")
def api_preview(intake_id: int):
    # Import lazily to avoid circular module imports. Existing coordinator
    # records are read only, and no external API request is made.
    from .contract_setup import _case
    con = connect()
    try:
        _, case, quote, verified = _case(con, intake_id)
        return build_api_preview(quote, verified, case)
    finally:
        con.close()
