"""V11 validation of the full approved, eight-tab export beyond every prior table end."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import os, tempfile, zipfile
from pathlib import Path
from lxml import etree as ET
from app.excel_io import ExcelSource, export_template, Q, SHEET_INDEX
from app.excel_quality import inspect_excel
from app.table_growth import TABLE_TO_SHEET

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'data'/'approved_master.xlsx'


def execute():
    test_data={
        'Maintenance Database':[{'row':804,'changes':{'Customer / site':'V11 Site',
            'Contract number':'TEST-804','Invoice Code':'CON-AAA-001',
            'Expiry date':'2027-11-30','Contract amount (£)':1250.75}}],
        'Expired':[{'row':8496,'changes':{'Customer / site':'V11 Historical',
            'Contract number':'TEST-8496','Expiry date':'2025-01-31'}}],
        'Weekly Values':[{'row':1686,'changes':{'Customer / site':'V11 Weekly',
            'Week ending (Friday)':'2026-10-23','Value recorded (£)':123.45}}],
        'Invoices':[{'row':733,'changes':{'Customer / site':'V11 Invoice',
            'Invoice month':'2026-10-01','Amount ex VAT (£)':600}}],
        'Quotes':[{'row':1507,'changes':{'Customer / site':'V11 Quote','Quote type':'Maintenance'}}],
    }
    limits={'ContractsRegister':804,'ExpiredHistoryRegister':8496,
        'WeeklyValuesRegister':1686,'InvoiceRunRegister':733,'QuotationRegister':1507}
    with tempfile.TemporaryDirectory(prefix='pulse_v11_growth_') as tmp:
        output=Path(tmp)/'beyond_template_capacity.xlsx'
        assert set(export_template(str(TEMPLATE),test_data,str(output)))==set(test_data)
        outcome=inspect_excel(str(output))
        assert outcome['ok'],outcome
        assert outcome['stats']['active_rows']==643,outcome['stats']
        assert outcome['stats']['expired_rows']==8382,outcome['stats']
        assert len(outcome['tables'])==5
        for name,last in limits.items():
            assert outcome['tables'][name]['ref'].endswith(str(last)),outcome['tables'][name]
            assert outcome['tables'][name]['has_filter']
        source=ExcelSource(str(output))
        for sheet,match in [('Maintenance Database','V11 Site'),('Expired','V11 Historical'),
                ('Weekly Values','V11 Weekly'),('Invoices','V11 Invoice'),('Quotes','V11 Quote')]:
            hdr,rows=source.records(sheet)
            rec=next(x for x in rows if x['fields'].get('Customer / site')==match)
            assert rec['row']==test_data[sheet][0]['row'],rec
        main=source.sheet('Maintenance Database')
        newrow=next(r for r in main.find(Q('sheetData')) if r.tag==Q('row') and r.get('r')=='804')
        newcells={c.get('r'):c for c in newrow.findall(Q('c'))}
        assert len(newcells)==37, len(newcells)
        assert newcells['L804'].find(Q('f')) is not None,'Renewal formula missing'
        assert '$K804' in newcells['L804'].find(Q('f')).text
        assert newcells['L804'].get('s') is not None
        dim=main.find(Q('dimension')).get('ref');assert dim.endswith('804'),dim
        assert any('L2:L804' in x.get('sqref','') for x in main.findall(Q('conditionalFormatting')))
        source.z.close()
        # The approved Home and reporting worksheet XML should be copied unchanged.
        with zipfile.ZipFile(TEMPLATE) as before,zipfile.ZipFile(output) as after:
            assert set(before.namelist())==set(after.namelist())
            for name in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet5.xml',
                         'xl/worksheets/sheet6.xml','xl/styles.xml','xl/sharedStrings.xml']:
                if name in before.namelist():assert before.read(name)==after.read(name),name
        # Larger-than-original validation ranges extend automatically.
        far=Path(tmp)/'past_validation_buffer.xlsx'
        export_template(str(TEMPLATE),{'Maintenance Database':[{'row':2500,'changes':
             {'Customer / site':'V11 Far Site','Contract number':'2500'}}]},str(far))
        with zipfile.ZipFile(far) as f:
            ws=ET.fromstring(f.read('xl/worksheets/sheet2.xml'))
            validators=' '.join(v.get('sqref','') for v in ws.findall('.//'+Q('dataValidation')))
            assert 'D804:D2500' in validators,validators
            assert 'N804:N2500' in validators,validators
            assert inspect_excel(str(far))['ok']
        print('PASS V11: five filters grow; row styling; renewal formulas; worksheet dimensions; validations; template preservation')

if __name__=='__main__':execute()
