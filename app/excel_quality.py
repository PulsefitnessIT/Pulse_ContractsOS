"""Non-destructive OOXML quality gate for the approved workbook template.

Does not claim to recalculate formulas or replace hands-on Microsoft Excel testing.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as ET
from .excel_io import ExcelSource,NS,Q,REGISTER_SHEETS,splitcell

EXPECTED=('Home','Maintenance Database','Weekly Values','Invoices','Monthly Report','Sales Report','Quotes','Expired')
TABLE_SHEETS={'ContractsRegister','WeeklyValuesRegister','InvoiceRunRegister','QuotationRegister','ExpiredHistoryRegister'}


def inspect_excel(path):
    failures=[];warnings=[];tables={};sheet_count=0;sheet_names=[];formula_count=0
    with ZipFile(path) as z:
        corrupt=z.testzip()
        if corrupt:failures.append(f'Corrupt archive part: {corrupt}')
        root=ET.fromstring(z.read('xl/workbook.xml'))
        sheet_names=[x.get('name') for x in root.findall('.//'+Q('sheet'))]
        if tuple(sheet_names)!=EXPECTED:failures.append('Worksheet names or ordering differ from the approved eight-sheet Master')
        formula_count=sum(z.read(x).count(b'<f>') for x in z.namelist() if x.startswith('xl/worksheets/sheet') and x.endswith('.xml'))
        for name in z.namelist():
            if not (name.startswith('xl/tables/') and name.endswith('.xml')):continue
            r=ET.fromstring(z.read(name));table=r.get('name');tables[table]={'ref':r.get('ref'),'has_filter':r.find(Q('autoFilter')) is not None}
            if table in TABLE_SHEETS and not tables[table]['has_filter']:
                failures.append(f'Excel filter missing in table {table}')
        missing=TABLE_SHEETS-set(tables)
        if missing:failures.append('Missing Excel tables: '+', '.join(sorted(missing)))
    src=ExcelSource(path)
    try:
        main,active=src.records('Maintenance Database')
        hist,expired=src.records('Expired')
        if main!=hist:failures.append('Active and Expired contract column layouts differ')
        if 'Original Amount Notes' not in main and 'Original amount notes' not in main:
            warnings.append('Original Amount Notes heading not found under the expected spelling')
        if not {'Invoice Code','Sage Checked and Updated','Customer / site','Record ID'}.issubset(set(main)):
            failures.append('Mandatory coordinator columns missing')
        # Every populated source row must fall within its existing Excel table;
        # a worksheet dimension alone does not make new records filterable.
        table_per_sheet={'Maintenance Database':'ContractsRegister','Expired':'ExpiredHistoryRegister',
            'Weekly Values':'WeeklyValuesRegister','Invoices':'InvoiceRunRegister','Quotes':'QuotationRegister'}
        from .table_growth import CELL_RANGE
        for sheet_name,table_name in table_per_sheet.items():
            values=active if sheet_name=='Maintenance Database' else expired if sheet_name=='Expired' else src.records(sheet_name)[1]
            maxrow=max((x['row'] for x in values),default=1)
            tab=tables.get(table_name)
            if tab:
                m=CELL_RANGE.fullmatch(tab['ref'])
                end=int(m.group(4) or m.group(2)) if m else 0
                if maxrow>end:failures.append(f'{table_name} does not cover populated row {maxrow}')
        stats={'active_rows':len(active),'expired_rows':len(expired),'columns':len(main),'sheets':len(sheet_names),'formula_cells_approx':formula_count}
    finally:src.z.close()
    return {'ok':not failures,'failures':failures,'warnings':warnings,'tables':tables,'stats':stats}


def remaining_capacity(con):
    """Report rows in use and original template headroom; export grows tables."""
    from .table_growth import TABLE_TO_SHEET, CELL_RANGE, MAX_EXCEL_ROWS
    current={r['source_sheet']:r['maxrow'] for r in con.execute(
        'SELECT source_sheet,MAX(source_row) AS maxrow FROM contracts GROUP BY source_sheet')}
    ledgers={r['kind']:r['maxrow'] for r in con.execute(
        'SELECT kind,MAX(source_row) AS maxrow FROM ledger GROUP BY kind')}
    from .store import TEMPLATE
    limits={}
    with ZipFile(TEMPLATE) as archive:
        for path in archive.namelist():
            if not path.startswith('xl/tables/') or not path.endswith('.xml'):continue
            root=ET.fromstring(archive.read(path))
            sheet=TABLE_TO_SHEET.get(root.get('name'))
            if sheet:
                m=CELL_RANGE.fullmatch(root.get('ref',''))
                if m:limits[sheet]=int(m.group(4) or m.group(2))
    result={}
    for sheet,last in limits.items():
        used=int(current.get(sheet,ledgers.get(sheet,1)) or 1)
        result[sheet]={'used_through_row':used,
            'last_template_row':last,
            'remaining_rows':max(0,last-used),
            'auto_extend_on_export':True,
            'available_excel_rows':MAX_EXCEL_ROWS-1-used,
            'will_extend_on_next_export':used>last}
    return result
