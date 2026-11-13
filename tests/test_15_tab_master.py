"""Fictional 15-sheet Pulse maintenance workbook regression test.

NEVER check real customer workbooks into public GitHub. This tiny OOXML
fixture proves positional MAIN- IDs, immutable extra source registers, MOD
segregation and hidden annual tabs without storing private contract data.
"""
import json
import sqlite3
from pathlib import Path
import zipfile
import pytest

from app.data_readiness import (
    PULSE_15_WORKSHEETS, PULSE_15_SOURCE_SHEETS, workbook_check,
)
from app.excel_io import ExcelSource, export_template
from app import store


def make_workbook(path, *, visible_ppm=False):
    n="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels="http://schemas.openxmlformats.org/package/2006/relationships"

    def letter(number):
        text=""
        while number:
            number,low=divmod(number-1,26)
            text=chr(65+low)+text
        return text

    def cell(col,row,value):
        v=str(value).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f'<c r="{letter(col)}{row}" t="inlineStr"><is><t>{v}</t></is></c>'

    register_head={
        1:"Customer / site", 9:"Contract number", 10:"Start date",
        11:"Expiry date",13:"Contract / warranty type", 14:"Invoice Code",
        21:"Contract amount (£)"
    }
    sources={}
    for index,sheet in enumerate(PULSE_15_WORKSHEETS,1):
        heading={}
        content={}
        if sheet in ("Maintenance Database","MOD","Expired"):
            heading=register_head.copy()
            content={1:"Fictional Training Gym",9:"DEMO-"+str(index),
                     10:"2026-01-01",11:"2027-01-01",13:"Gold",
                     14:"DEMO",21:"300"}
            if sheet=="Maintenance Database":
                heading[30]=""  # AD1 remains blank in genuine 15-tab Master
                content[30]="MAIN-TEST1"
            elif sheet=="MOD":
                heading[30]="Record ID"
                content[30]="PF-TEST1"
            else:
                heading[30]="Historical Comments (Old Master)"
                content[30]="Historical proof only"
        elif sheet in PULSE_15_SOURCE_SHEETS:
            heading={1:"Customer / site",4:"Contract number"}
            content={1:"Fictional Training Gym",4:"DEMO-999"}
            if sheet=="Sicon Contracts":
                heading.update({32:"Sicon contract ID",33:"Sicon line ID",
                                41:"",42:"",43:""})
                content.update({32:"SICON-FIC",33:"LINE-1",41:"Unknown raw 1"})
            else:
                heading[25]="Service year key (internal)"
                content[25]="2026-DATES-REVIEW"
        elif sheet in ("Weekly Values","Invoices","Quotes"):
            heading={1:"Customer / site"}
            content={1:"Fictional Training Gym"}
        else:
            heading={1:"Report title"}
        top="".join(cell(k,1,v) for k,v in sorted(heading.items()))
        value="".join(cell(k,2,v) for k,v in sorted(content.items()))
        xml=(f'<worksheet xmlns="{n}"><sheetData><row r="1">{top}</row>'
             + (f'<row r="2">{value}</row>' if value else '')
             + '</sheetData></worksheet>')
        sources[f"xl/worksheets/sheet{index}.xml"]=xml
    metadata=''.join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"'
        + (' state="hidden"' if not visible_ppm and
           name in ("PPM Annual Detail - Commercial","PPM Annual Detail - MOD")
           else '')
        + '/>' for i,name in enumerate(PULSE_15_WORKSHEETS,1)
    )
    workbook=(f'<workbook xmlns="{n}" xmlns:r="{r}"><sheets>{metadata}'
              '</sheets></workbook>')
    relationships=(f'<Relationships xmlns="{rels}">'
      + ''.join(f'<Relationship Id="rId{i}" Type="{r}/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>' for i in range(1,16))
      + '</Relationships>')
    styles=(f'<styleSheet xmlns="{n}"><fills count="1"><fill>'
            '<patternFill patternType="none"/></fill></fills>'
            '<cellXfs count="1"><xf fillId="0"/></cellXfs></styleSheet>')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml",workbook)
        archive.writestr("xl/_rels/workbook.xml.rels",relationships)
        archive.writestr("xl/styles.xml",styles)
        for name,content in sources.items():
            archive.writestr(name,content)
    return path


def test_15_tab_schema_maps_real_main_id_and_keeps_hidden_ppm(tmp_path):
    path=make_workbook(tmp_path/"demo.xlsx")
    check=workbook_check(path)
    assert check["valid"], check["issues"]
    assert check["profile"]=="pulse_15_tab_operational_master"
    assert len(check["sheet_names"])==15
    src=ExcelSource(path)
    try:
        headers,records=src.records("Maintenance Database")
        assert headers[29]=="Record ID"
        assert records[0]["fields"]["Record ID"]=="MAIN-TEST1"
        _,sicon=src.records("Sicon Contracts")
        assert sicon[0]["fields"]["Unlabelled source AO"]=="Unknown raw 1"
        assert src.records("Expired")[1][0]["fields"].get("Record ID") is None
    finally:
        src.z.close()


def test_unhidden_source_ppm_is_not_approved_master(tmp_path):
    path=make_workbook(tmp_path/"visible.xlsx",visible_ppm=True)
    check=workbook_check(path)
    assert not check["valid"]
    assert any("not hidden" in item for item in check["issues"])


def test_fresh_bootstrap_preserves_source_rows_without_inflating_contracts(
        tmp_path, monkeypatch):
    folder=tmp_path/"private"
    folder.mkdir()
    make_workbook(folder/"approved_master.xlsx")
    monkeypatch.setattr(store,"DATA",str(folder))
    monkeypatch.setattr(store,"DB",str(folder/"contracts.sqlite3"))
    monkeypatch.setattr(store,"TEMPLATE",str(folder/"approved_master.xlsx"))
    store.init_db()
    with sqlite3.connect(folder/"contracts.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]==3
        assert connection.execute(
            "SELECT COUNT(*) FROM contracts WHERE status='Active'"
        ).fetchone()[0]==2
        assert connection.execute(
            "SELECT COUNT(*) FROM auxiliary_source_rows"
        ).fetchone()[0]==5
        assert connection.execute(
            "SELECT COUNT(DISTINCT sheet) FROM auxiliary_source_rows"
        ).fetchone()[0]==5
        assert connection.execute(
            "SELECT COUNT(*) FROM ledger"
        ).fetchone()[0]==3
        row=connection.execute(
            "SELECT fields FROM auxiliary_source_rows "
            "WHERE sheet='Sicon Contracts'"
        ).fetchone()
        assert "Unknown raw 1" in row[0]
        assert connection.execute(
            "SELECT row_key FROM contracts WHERE source_sheet='Maintenance Database'"
        ).fetchone()[0]=="MAIN-TEST1"
        assert connection.execute(
            "SELECT row_key FROM contracts WHERE source_sheet='Expired'"
        ).fetchone()[0].startswith("SOURCE_ROW:")
    # Idempotent after successful first import.
    store.init_db()
    with sqlite3.connect(folder/"contracts.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]==3
        assert connection.execute(
            "SELECT COUNT(*) FROM auxiliary_source_rows"
        ).fetchone()[0]==5


def test_15_tab_roundtrip_preserves_all_operational_evidence(tmp_path):
    original=make_workbook(tmp_path/"source.xlsx")
    output=tmp_path/"export.xlsx"
    with zipfile.ZipFile(original) as z:
        sicon_original=z.read("xl/worksheets/sheet13.xml")
        ppm_original=z.read("xl/worksheets/sheet14.xml")
    export_template(
        original,
        {"Maintenance Database":[{"row":2,"changes":{
            "Customer / site":"Fictional Training Gym — reviewed"
        }}]},
        output,
    )
    report=workbook_check(output)
    assert report["valid"],report["issues"]
    assert report["sheet_names"]==PULSE_15_WORKSHEETS
    with zipfile.ZipFile(output) as z:
        assert z.read("xl/worksheets/sheet13.xml")==sicon_original
        assert z.read("xl/worksheets/sheet14.xml")==ppm_original
    src=ExcelSource(output)
    try:
        details=src.records("Maintenance Database")[1][0]["fields"]
        assert details["Record ID"]=="MAIN-TEST1"
        assert details["Customer / site"].endswith("reviewed")
        archive=src.records("Expired")[1][0]["fields"]
        assert archive["Historical Comments (Old Master)"]=="Historical proof only"
    finally:
        src.z.close()
