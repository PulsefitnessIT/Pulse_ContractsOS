"""Source-preserving preview generators for the approved Pulse agreement and Sicon templates.

The original legal terms pages and Excel column identities are retained.
Outputs are internal REVIEW-ONLY artefacts. The generated Excel files must not
be used in live Sicon without an independently approved mapping and sandbox test.
No customer source files, private templates or PDFs belong in the Git repo.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
X = "{"+MAIN_NS+"}"
ET.register_namespace("x", MAIN_NS)

AGREEMENT = "maintenance_agreement_approved.pdf"
CONTRACT_XLSX = "sicon_contract_import.xlsx"
EQUIPMENT_XLSX = "sicon_equipment_import.xlsx"

REVIEW_NOTICE = "REVIEW ONLY - NOT APPROVED FOR CUSTOMER ISSUE OR LIVE SICON IMPORT"

def today():
    return dt.date.today()


class TemplateError(ValueError):
    pass


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)


def _s(value):
    text=str(value if value is not None else "").replace("\r"," ").replace("\n"," ").strip()
    # Reject Excel formula injection and invalid XML characters; never transform
    # a risky value into a legitimate-looking Sicon import field.
    if text.startswith(("=","+","-","@")):
        raise TemplateError("An imported text field contains a spreadsheet formula prefix")
    if any(ord(c)<32 for c in text):
        raise TemplateError("An imported text field contains an unsupported character")
    if len(text)>1000:
        raise TemplateError("An imported field is too long")
    return text


def _iso_to_uk(iso):
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError,TypeError) as exc:
        raise TemplateError("Invalid contract or equipment cover date") from exc


# SHA-256 of the exact ordered first-row headers supplied by Pulse, including
# 15 blank formatted columns following the equipment template's 29 field names.
APPROVED_HEADER_SHA256 = {
    "contract": "89e9ab9f829ecd5db96870e813483fedead25633bd5ff4f16e042adf8ba367ba",
    "equipment": "0ef5121179775645a082806363fffcc3a1de8bbd98b5e89615c16e174d1b6105",
}

def _headers(row, strings=None):
    columns=[]
    strings=strings or []
    for c in row.findall(X+"c"):
        inline=c.find(X+"is")
        value=c.find(X+"v")
        if c.get("t")=="s" and value is not None:
            try:
                columns.append(strings[int(value.text)].strip())
            except (IndexError,ValueError,TypeError) as exc:
                raise TemplateError("Shared-string Sicon header could not be resolved") from exc
        elif inline is not None:
            columns.append("".join(inline.itertext()).strip())
        else:
            columns.append(value.text.strip() if value is not None and value.text else "")
    return columns


def _column(n):
    out=""
    while n:
        n,m=divmod(n-1,26)
        out=chr(65+m)+out
    return out


def workbook_from_template(template: bytes, kind: str, rows: list[dict]):
    """Keep complete XLSX package and header row; delete example data rows."""
    if kind not in ("contract","equipment"):
        raise TemplateError("Unknown Sicon template type")
    try:
        source=zipfile.ZipFile(io.BytesIO(template))
        root=ET.fromstring(source.read("xl/worksheets/sheet1.xml"))
    except (OSError,KeyError,ET.ParseError,zipfile.BadZipFile) as exc:
        raise TemplateError("A recognised Sicon Excel template is required") from exc
    data=root.find(X+"sheetData")
    if data is None or not list(data):
        raise TemplateError("Sicon template does not contain its required header row")
    first=list(data)[0]
    shared=[]
    if "xl/sharedStrings.xml" in source.namelist():
        shared_root=ET.fromstring(source.read("xl/sharedStrings.xml"))
        shared=["".join(node.itertext()) for node in shared_root.findall(X+"si")]
    headers=_headers(first,shared)
    count=len(headers)
    named=sum(bool(x) for x in headers)
    expected=(239,239) if kind=="contract" else (44,29)
    digest=hashlib.sha256("\0".join(headers).encode("utf-8")).hexdigest()
    if (count,named)!=expected or digest!=APPROVED_HEADER_SHA256[kind]:
        raise TemplateError("Sicon template headers differ from the approved import map; IT review required")
    if len(set(headers))!=len(headers):
        # Supplied contract template repeats 'CL AnalysisCode 40'; index-based
        # fallback would silently fill the wrong column, so only use unique keys.
        dupe={h for h in headers if headers.count(h)>1}
        if any(k in dupe for row in rows for k in row):
            raise TemplateError("Requested Sicon field is duplicated in this template")
    header_lookup=set(headers)
    for row in rows:
        if not isinstance(row,dict) or set(row)-header_lookup:
            raise TemplateError("Unrecognised Sicon import column; mapping is not approved")
    for old in list(data)[1:]:
        data.remove(old)
    first.set("r","1")
    for i,c in enumerate(first.findall(X+"c"),1):
        c.set("r",_column(i)+"1")
    for number,record in enumerate(rows,2):
        out=ET.SubElement(data,X+"row",{"r":str(number)})
        for idx,title in enumerate(headers,1):
            value=record.get(title)
            if value is None or value=="":
                continue
            pos=_column(idx)+str(number)
            cell=ET.SubElement(out,X+"c",{"r":pos})
            if isinstance(value,(int,float,Decimal)) and not isinstance(value,bool):
                cell.set("t","n")
                ET.SubElement(cell,X+"v").text=str(value)
            else:
                cell.set("t","inlineStr")
                ET.SubElement(ET.SubElement(cell,X+"is"),X+"t").text=_s(value)
    sheet_xml=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as dest:
        for item in source.infolist():
            body=sheet_xml if item.filename=="xl/worksheets/sheet1.xml" else source.read(item.filename)
            dest.writestr(item,body)
    source.close()
    raw=out.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as verify:
        if verify.testzip():
            raise TemplateError("Generated Sicon workbook did not pass ZIP integrity check")
        new=ET.fromstring(verify.read("xl/worksheets/sheet1.xml"))
        if _headers(new.find(X+"sheetData")[0],shared)!=headers:
            raise TemplateError("Generated workbook headers differ from the original Sicon template")
    return raw


def _value(quote,verified,name,default=""):
    return str(verified.get(name) or default or "").strip()


def contract_rows(quote, verified):
    """Proposed Sicon billing rows; all materially system-specific fields verified."""
    c=quote["customer"]
    contract=quote["contract"]
    ledger=_value(quote,verified,"sage_account_ref",c["sage_account_ref"])
    contract_ref=_value(quote,verified,"contract_reference",contract["reference"])
    stock=_value(quote,verified,"billing_stock_code")
    warehouse=_value(quote,verified,"warehouse_name")
    address=_value(quote,verified,"sicon_delivery_address")
    if not all((ledger,contract_ref,stock,warehouse,address)):
        raise TemplateError("Confirm Sage account, contract, billing stock code, warehouse and Sicon delivery address")
    cadence=_value(quote,verified,"billing_frequency",contract["payment_terms"]).casefold()
    intervals={"monthly":(1,"months"),"quarterly":(3,"months"),
               "annually":(12,"months"),"annual":(12,"months"),
               "yearly":(12,"months")}
    if cadence not in intervals:
        raise TemplateError("Payment plan needs an approved monthly/quarterly/annual Sicon frequency")
    n,unit=intervals[cadence]
    stages=sorted({a["cover_start"] for a in quote["equipment"]})
    rows=[]
    for idx,start in enumerate(stages,1):
        group=[a for a in quote["equipment"] if a["cover_start"]==start]
        yearly=sum((_money(a["annual_total"]) for a in group),Decimal("0"))
        rows.append({
            "Contract Number":contract_ref,
            "Contract Description":f'{c["site_name"]} - {contract["package"]} maintenance',
            "Customer Order Number":_value(quote,verified,"purchase_order"),
            "Contract Line Number":idx,
            "Sales Ledger Account Number":ledger,
            "Delivery Address Description":address,
            "Product Stock Code":stock,
            "Warehouse Name":warehouse,
            "Internal Description":f'Maintenance cover from {_iso_to_uk(start)} to {_iso_to_uk(contract["end_date"])}',
            "Quantity":1,
            "Unit Price":yearly,
            "Price Interval":"years",
            "Contract Start Date":_iso_to_uk(start),
            "Contract End Date":_iso_to_uk(contract["end_date"]),
            "Is Rolling Contract":"No",
            "Current Invoice Already Generated":"No",
            "Invoice Frequency":n,
            "Invoice Frequency Interval":unit,
            "Bill Cover From Date":_iso_to_uk(start),
            "Suspended":"No",
        })
    return rows


def equipment_rows(quote,verified,sicon_contract_ref,stage_start,serials_override=None):
    """One row per actual machine; only one due-start-date batch at a time."""
    c=quote["customer"]
    customer=_value(quote,verified,"sicon_customer_ref")
    location=_value(quote,verified,"sicon_location_description")
    sla=_value(quote,verified,"sla_name")
    if not all((customer,location,sla,sicon_contract_ref)):
        raise TemplateError("Confirm Sicon customer ref, location, approved SLA and imported contract number")
    stages=sorted({a["cover_start"] for a in quote["equipment"]})
    if stage_start not in stages:
        raise TemplateError("Equipment start date is not on this accepted quotation")
    if dt.date.fromisoformat(stage_start)>today():
        raise TemplateError("Cannot prepare future-dated equipment for an early Sicon import")
    index=stages.index(stage_start)+1
    rows=[]
    for a in quote["equipment"]:
        if a["cover_start"]!=stage_start:
            continue
        serials=(serials_override or {}).get(a["source_line_id"],a["serial_numbers"])
        if len(serials)!=a["quantity"] or not all(serials):
            raise TemplateError("Resolve all serial numbers for this equipment group before export")
        make=str(a.get("make") or _value(quote,verified,"equipment_make")).strip()
        if not make:
            raise TemplateError("Verify the actual manufacturer for all equipment before Sicon export")
        for serial in serials:
            rows.append({
                "Sicon Customer Ref":customer,
                "Location Description":location,
                "Sublocation Description":_value(quote,verified,"sicon_sublocation_description"),
                "Supplier Reference":_value(quote,verified,"sicon_supplier_reference"),
                "Supplier Name":_value(quote,verified,"sicon_supplier_name"),
                "Contract Number":sicon_contract_ref,
                "Contract Line No":index,
                "SLA Name":sla,
                "Stock Item Code":a["item_code"],
                "Description":a["description"],
                "Make":make,
                "Model":a["model"],
                "Serial Number":serial,
            })
    if not rows:
        raise TemplateError("No equipment for the selected start date")
    return rows


def agreement_preview(template: bytes, quote: dict, verified: dict, equipment_serials=None):
    """Fill supplier-approved base PDF; replace blank Schedule 3, keep legal pages."""
    try:
        import fitz
    except ImportError as exc:
        raise TemplateError("PyMuPDF is required for the maintenance agreement") from exc
    doc=fitz.open(stream=template,filetype="pdf")
    if len(doc)!=8 or "Maintenance Agreement" not in doc[0].get_text() or "Schedule 6" not in doc[6].get_text():
        raise TemplateError("Unknown maintenance agreement template version; never replace its legal terms")
    if "MAINTENANCE AGREEMENT" not in doc[7].get_text():
        raise TemplateError("The maintenance terms page was not found")
    c,contract=quote["customer"],quote["contract"]
    ref=_value(quote,verified,"contract_reference",contract["reference"])
    if not ref:
        raise TemplateError("Agreement number has not been confirmed")
    vals={
        "Agreement number":ref,
        "Date prepared":dt.date.today().strftime("%d/%m/%Y"),
        "The customer":c["legal_name"],
        "In respect of":c["site_name"],
    }
    site_lines=[x.strip() for x in c["site_address"].replace("\r","\n").split("\n") if x.strip()]
    if len(site_lines)>4:
        raise TemplateError("Confirm the shortened site address for the four available agreement address lines")
    for name,value in zip(("undefined","undefined_2","undefined_3","undefined_4"),site_lines[:4]):
        vals[name]=value
    cover=contract["package"]
    if cover in ("Silver","Gold","Platinum"):
        vals["Dropdown1"]=cover
    # Start/end ComboBox fields accept typed values even though the template
    # only offers 'To be agreed' in its dropdown choices.
    vals["Start Date"]=_iso_to_uk(contract["start_date"])
    vals["End date"]=_iso_to_uk(contract["end_date"])
    duration=(dt.date.fromisoformat(contract["end_date"])-dt.date.fromisoformat(contract["start_date"])).days+1
    year_options={365:"1 year",366:"1 year",730:"2 years",731:"2 years",1095:"3 years",1096:"3 years"}
    if duration in year_options:
        vals["Dropdown2"]=year_options[duration]
    visits=contract.get("visits")
    if visits==1: vals["Dropdown3"]="One per year"
    if visits==0: vals["Dropdown3"]="None"
    # No payment widget is filled automatically for multi-stage agreements,
    # because equal instalments cannot be inferred from total contract value.
    if len({a["cover_start"] for a in quote["equipment"]})==1:
        if contract.get("payment_terms","").strip().lower() in ("annual","annually","yearly"):
            vals["annual payments of"]=f'£{_money(quote["pricing"]["annual_total"]):,.2f}'
            vals["from_2"]=_iso_to_uk(contract["start_date"])
            vals["totalling_2"]=f'£{_money(quote["pricing"]["term_total"]):,.2f}'
    for page in (doc[0],doc[1]):
        for widget in list(page.widgets() or []):
            if widget.field_name in vals:
                widget.field_value=vals[widget.field_name]
                widget.update()
    # Remove the two blank legacy equipment pages only. Do not touch the
    # obligations, exceptions, supplier terms or existing signature widgets.
    doc.delete_pages(2,3)
    sheet=fitz.open()
    ordered=sorted(quote["equipment"],key=lambda x:(x["item_code"],x["source_line_id"]))
    lines=[]
    for a in ordered:
        serials=(equipment_serials or {}).get(a["source_line_id"],a["serial_numbers"])
        lines.append({
            "sku":a["item_code"],"name":a["description"],"qty":a["quantity"],
            "serials":", ".join(serials) or "TO VERIFY",
            "date":_iso_to_uk(a["cover_start"]),
            "end":_iso_to_uk(a["cover_end"]),
        })
    for offset in range(0,len(lines),14):
        page=sheet.new_page(width=960,height=540)
        page.draw_rect(fitz.Rect(0,0,960,62),color=None,fill=(0.08,0.21,0.28))
        page.insert_text((32,29),"PULSE FITNESS  |  MAINTENANCE AGREEMENT",fontsize=17,color=(1,1,1))
        page.insert_text((32,49),f'Schedule 3 - Equipment | {c["site_name"][:80]}',fontsize=11,color=(0.8,0.9,1))
        header=[(32,"ITEM CODE"),(168,"DESCRIPTION"),(446,"QTY"),(485,"SERIAL NUMBERS"),(724,"COVER START"),(826,"COVER ENDS")]
        for x,label in header: page.insert_text((x,83),label,fontsize=9,color=(0.08,0.23,0.32))
        for n,a in enumerate(lines[offset:offset+14]):
            y=104+n*28
            if n%2==0:page.draw_rect(fitz.Rect(28,y-14,932,y+12),color=None,fill=(0.95,0.97,0.98))
            widths=[125,270,37,230,95,108]
            for (x,_),val,w in zip(header,(a["sku"],a["name"],str(a["qty"]),a["serials"],a["date"],a["end"]),widths):
                page.insert_textbox(fitz.Rect(x,y-12,x+w,y+11),val,fontsize=8.5,
                                    fontname="helv",color=(0.12,0.24,0.30))
        page.insert_text((32,525),f'Contracting customer: {c["legal_name"][:100]}',fontsize=8,color=(0.25,0.34,0.40))
        page.insert_text((32,512),f'All stages co-terminate: {_iso_to_uk(contract["end_date"])}  |  Page {offset//14+1}',fontsize=9,color=(0.25,0.34,0.40))
        # The original Schedule 3 had a single total; maintain that convention.
        page.insert_text((612,512),f'Contract value (ex VAT): £{_money(quote["pricing"]["term_total"]):,.2f}',fontsize=9,color=(0.10,0.22,0.30))
    doc.insert_pdf(sheet,start_at=2)
    sheet.close()
    for p in doc:
        p.insert_text((32,25),"DRAFT FOR CONTRACT REVIEW - NOT FOR SIGNATURE",fontsize=9,
                      color=(0.78,0.12,0.12),overlay=True)
    result=doc.tobytes(garbage=4,deflate=True)
    doc.close()
    return result


def approved_template_path(data_folder, filename):
    root=Path(data_folder).resolve()
    path=root/"approved_sicon_templates"/filename
    if path.is_symlink() or not path.is_file():
        raise TemplateError(f"IT must stage the approved {filename} in the protected runtime")
    if path.stat().st_size>12*1024*1024:
        raise TemplateError("Template exceeds allowed size")
    return path
