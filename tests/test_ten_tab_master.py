"""Verify the named, ten-worksheet Excel structure without private customer data."""
import datetime as dt
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from app.data_readiness import CURRENT_WORKSHEETS, workbook_check
from app.excel_io import ExcelSource, register_sheets
from app.source_integrity import source_audit
from app.master_roundtrip import parse_workbook_records


N="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P="http://schemas.openxmlformats.org/package/2006/relationships"
FILES={"Home":1,"Action Centre":10,"Maintenance Database":2,
       "MOD":9,"Weekly Values":3,"Invoices":4,"Monthly Report":5,
       "Sales Report":6,"Quotes":7,"Expired":8}
HEADERS=["Customer / site","Record ID","Contract number",
         "Contract / warranty type","Start date","Expiry date",
         "Contract amount (£)","Invoice Code","Next action date","Next action"]


def row_xml(number, values):
    cells=[]
    for index,value in enumerate(values):
        col=chr(65+index)
        if value is None:
            continue
        if isinstance(value,(int,float)):
            cells.append(f'<c r="{col}{number}"><v>{value}</v></c>')
        else:
            cells.append(f'<c r="{col}{number}" t="inlineStr"><is><t>'
                         f'{escape(str(value))}</t></is></c>')
    return f'<row r="{number}">{"".join(cells)}</row>'


def create_ten_tab_file(path):
    date_serial=(dt.date(2026,11,5)-dt.date(1899,12,30)).days
    xml_wb="".join(
        f'<sheet name="{escape(name)}" sheetId="{FILES[name]}" r:id="rId{i}"/>'
        for i,name in enumerate(CURRENT_WORKSHEETS,1)
    )
    xml_rels="".join(
        f'<Relationship Id="rId{i}" Type="{R}/worksheet" '
        f'Target="worksheets/sheet{FILES[name]}.xml"/>'
        for i,name in enumerate(CURRENT_WORKSHEETS,1)
    )
    data={}
    for sheet in CURRENT_WORKSHEETS:
        if sheet in ("Maintenance Database","MOD","Expired"):
            values=[
                "Fictional Site "+sheet, "TEST-"+sheet[:3], "FICT-01",
                "P&L Ext Warr", date_serial,date_serial+365,"","WAR-TEST",
                date_serial, "Request verified agreement"
            ]
            data[sheet]=[HEADERS,values]
        elif sheet=="Action Centre":
            data[sheet]=[["Customer / site","Action"],
                         ["Fictional derived task","Do not import as a contract"]]
        elif sheet in ("Weekly Values","Invoices","Quotes"):
            data[sheet]=[["Original source","Customer / site"]]
        else:
            data[sheet]=[["Overview"],["Derived report"]]
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml",
            f'<workbook xmlns="{N}" xmlns:r="{R}"><sheets>{xml_wb}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{P}">{xml_rels}</Relationships>')
        z.writestr("xl/styles.xml",
            f'<styleSheet xmlns="{N}"><fills><fill/></fills>'
            '<cellXfs><xf/></cellXfs></styleSheet>')
        for sheet,rows in data.items():
            elements="".join(row_xml(i,record) for i,record in enumerate(rows,1))
            z.writestr(f'xl/worksheets/sheet{FILES[sheet]}.xml',
                f'<worksheet xmlns="{N}"><sheetData>{elements}</sheetData></worksheet>')


def test_ten_tab_layout_and_non_positional_sheet_relationships(tmp_path):
    file=tmp_path/"fictional-ten-tab.xlsx"
    create_ten_tab_file(file)
    check=workbook_check(file)
    assert check["valid"] is True
    assert check["profile"]=="ten_tab_mod_action_centre"
    source=ExcelSource(file)
    try:
        assert source.sheet_parts["Action Centre"].endswith("sheet10.xml")
        assert source.sheet_parts["Maintenance Database"].endswith("sheet2.xml")
        assert source.sheet_parts["MOD"].endswith("sheet9.xml")
        assert list(register_sheets(source))==["Maintenance Database","MOD","Expired"]
        headers,rows=source.records("MOD")
        assert rows[0]["fields"]["Next action date"]=="2026-11-05"
        assert headers[-1]=="Next action"
    finally:
        source.z.close()


def test_source_audit_includes_mod_but_excludes_calculated_action_centre(tmp_path):
    file=tmp_path/"fictional-ten-tab.xlsx"
    create_ten_tab_file(file)
    report=source_audit(file)
    assert report["registers"]["Maintenance Database"]["populated_site_rows"]==1
    assert report["registers"]["MOD"]["populated_site_rows"]==1
    assert report["registers"]["Expired"]["populated_site_rows"]==1
    assert report["total_register_rows"]==3
    assert report["computed_action_centre_is_not_a_contract_register"] is True
    assert report["verified_financial_revenue"] is False


def test_tracked_master_roundtrip_ignores_action_centre_rows(tmp_path):
    file=tmp_path/"fictional-ten-tab.xlsx"
    create_ten_tab_file(file)
    data=parse_workbook_records(file.read_bytes())
    assert "MOD" in data and len(data["MOD"])==1
    assert "Maintenance Database" in data and "Expired" in data
    assert "Action Centre" not in data
