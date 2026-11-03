"""OOXML reader and loss-minimising template patcher.

Designed to preserve the approved Excel template's untouched ZIP parts exactly.
Only changed cells and affected table ranges are patched. This is not a spreadsheet
formula calculation engine; Microsoft Excel recalculates on opening.
"""
from __future__ import annotations
import copy
import datetime as dt
import io
import os
import re
import zipfile
import posixpath
from lxml import etree as ET

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
Q=lambda n:'{%s}%s'%(NS,n)
NSMAP={'m':NS, 'r':R}
SHEET_INDEX={'Home':1,'Maintenance Database':2,'Weekly Values':3,'Invoices':4,'Monthly Report':5,'Sales Report':6,'Quotes':7,'Expired':8}
REGISTER_SHEETS=('Maintenance Database','Expired')  # Legacy eight-tab fallback
CURRENT_REGISTER_SHEETS=('Maintenance Database','MOD','Expired')

def register_sheets(source):
    """Only factual contract registers, never calculated Action Centre rows."""
    return CURRENT_REGISTER_SHEETS if 'MOD' in getattr(source,'sheet_parts',{}) else REGISTER_SHEETS
DATE_FIELDS={'Start date','Expiry date','Action due','Last service recorded','Invoice month','Period from','Period to','Date sent','Week ending (Friday)','Prepared date','Sent date','Next action date','Follow Up Date','Revised Date'}


def colno(col):
    result=0
    for ch in col:result=result*26+ord(ch)-64
    return result

def colname(n):
    out=''
    while n:
        n,rem=divmod(n-1,26);out=chr(65+rem)+out
    return out

def splitcell(ref):
    m=re.fullmatch(r'([A-Z]+)(\d+)',ref)
    return colno(m[1]),int(m[2])

def iso_excel(value):
    try:
        n=float(value)
        if 15000<n<100000:
            return (dt.datetime(1899,12,30)+dt.timedelta(days=n)).date().isoformat()
    except (ValueError,TypeError,OverflowError):pass
    return str(value or '')

def excel_day(value):
    if not value:return None
    if isinstance(value,(int,float)):return value
    try:
        return (dt.date.fromisoformat(str(value)[:10])-dt.date(1899,12,30)).days
    except ValueError:return None

class ExcelSource:
    def __init__(self,filepath):
        self.path=filepath;self.z=zipfile.ZipFile(filepath,'r')
        # Match worksheet *names* to OOXML relationships, not historical positions.
        # The ten-tab working Master inserts Action Centre and MOD but retains
        # the original sheet XML part IDs; sheet position is not sheet identity.
        workbook=ET.fromstring(self.z.read('xl/workbook.xml'))
        relroot=ET.fromstring(self.z.read('xl/_rels/workbook.xml.rels'))
        rels={el.get('Id'):el.get('Target') for el in relroot}
        self.sheet_parts={}
        self.sheet_names=[]
        for el in workbook.find(Q('sheets')):
            name=el.get('name')
            relationship=el.get('{'+R+'}id')
            target=rels.get(relationship,'')
            if not target:raise ValueError('Missing OOXML worksheet relationship')
            part=posixpath.normpath(target.lstrip('/') if target.startswith('/')
                else posixpath.join('xl',target))
            if not part.startswith('xl/worksheets/') or part not in self.z.namelist():
                raise ValueError('Unexpected or missing worksheet relationship')
            if name in self.sheet_parts:raise ValueError('Duplicated worksheet name')
            self.sheet_names.append(name)
            self.sheet_parts[name]=part

        self.shared=[];self.styles=[];self.fills=[]
        if 'xl/sharedStrings.xml' in self.z.namelist():
            root=ET.fromstring(self.z.read('xl/sharedStrings.xml'))
            for si in root.findall(Q('si')):
                self.shared.append(''.join(t.text or '' for t in si.iter(Q('t'))))
        st=ET.fromstring(self.z.read('xl/styles.xml'))
        self.fills=list(st.find(Q('fills')))
        self.styles=list(st.find(Q('cellXfs')))
    def cell_value(self,cell):
        if cell is None:return None
        v=cell.find(Q('v'))
        if cell.get('t')=='inlineStr':return ''.join(t.text or '' for t in cell.iter(Q('t')))
        if v is None:return None
        val=v.text
        if cell.get('t')=='s':return self.shared[int(val)]
        if cell.get('t') in ('str','e'):return val
        try:
            n=float(val)
            return int(n) if n.is_integer() else n
        except (ValueError,TypeError):return val
    def color(self,cell):
        try:
            style=self.styles[int(cell.get('s','0'))]
            fill=self.fills[int(style.get('fillId','0'))]
            rgb=fill.find('.//'+Q('fgColor'))
            if rgb is None:return ''
            col=rgb.get('rgb','')
            if len(col)==8 and col[0:2] in ('FF','00'):
                code='#'+col[-6:].upper()
                if code not in ('#FFFFFF','#000000'):return code
        except Exception:pass
        return ''
    def sheet(self,name):
        return ET.fromstring(self.z.read(self.sheet_parts[name]))
    def records(self,name):
        root=self.sheet(name)
        rows=root.find(Q('sheetData')).findall(Q('row'))
        if not rows:return [],[]
        header_cells={splitcell(c.get('r'))[0]:self.cell_value(c) for c in rows[0].findall(Q('c'))}
        headers=[str(header_cells.get(i,'') or '') for i in range(1,max(header_cells)+1)]
        data=[]
        for row in rows[1:]:
            cells={splitcell(c.get('r'))[0]:c for c in row.findall(Q('c'))}
            fields={}
            for idx,h in enumerate(headers,1):
                if not h:continue
                v=self.cell_value(cells.get(idx))
                if h in DATE_FIELDS and isinstance(v,(int,float)):
                    v=iso_excel(v)
                fields[h]=v if v is not None else ''
            if not any(str(fields.get(h,'')).strip() for h in headers[:3]):continue
            first=cells.get(1)
            data.append({'row':int(row.get('r')),'fields':fields,'fill':self.color(first) if first is not None else ''})
        return headers,data


def cell_set(row,ref,value,style_ref=None):
    idx,_=splitcell(ref)
    found=None
    for c in row.findall(Q('c')):
        if c.get('r')==ref:found=c;break
    if found is None:
        found=ET.Element(Q('c'),r=ref)
        if style_ref is not None:found.set('s',style_ref)
        inserted=False
        for i,existing in enumerate(row.findall(Q('c'))):
            if splitcell(existing.get('r'))[0]>idx:
                row.insert(i,found);inserted=True;break
        if not inserted:row.append(found)
    # For a newly populated preformatted row, override the special blank-row
    # colour and reuse the correct normal data-cell formatting per column.
    if style_ref is not None:
        found.set('s', style_ref)
    # Existing calculated cells are owned by the approved Excel template.
    # Never replace a formula with a cached value from the app.
    if found.find(Q('f')) is not None:return
    for elem in list(found):found.remove(elem)
    found.attrib.pop('t',None)
    if value is None or value=='':return
    if isinstance(value,str):
        found.set('t','inlineStr'); it=ET.SubElement(found,Q('is'));ET.SubElement(it,Q('t')).text=value
    elif isinstance(value,bool):
        found.set('t','b');ET.SubElement(found,Q('v')).text='1' if value else '0'
    else:
        ET.SubElement(found,Q('v')).text=str(value)


def export_template(template_path, updates, output_path):
    """updates: {sheet: [{'row':int,'changes':{column-header:value}}, ...]}.
    Preserves template layout, tables, styles, worksheets and all unrelated parts.
    Automatically grows Excel tables when new rows exceed the original template range.
    """
    src=ExcelSource(template_path)
    originals={}
    touched=[]
    final_rows={}
    for sheet,entries in updates.items():
        if not entries:continue
        root=src.sheet(sheet);rows=root.find(Q('sheetData'))
        index={int(r.get('r')):r for r in rows.findall(Q('row'))}
        headers,_=src.records(sheet)
        heading={h:colname(i+1) for i,h in enumerate(headers)}
        template_row=index.get(2)
        standard_styles = {}
        if template_row is not None:
            standard_styles = {splitcell(c.get('r'))[0]:c.get('s') for c in template_row.findall(Q('c'))}
        # Even sparse template rows must have proper styles for each data type.
        # 2: ordinary text; 13: dates; 15: service count; 7: currency;
        # 14: renewal calculation. These are styles already present in the approved template.
        def normal_style(col, header):
            style = standard_styles.get(colno(col))
            if style is not None:return style
            if header in DATE_FIELDS:return '13'
            if header in ('Contract amount (£)','Original amount (£)','Value recorded (£)','Amount ex VAT (£)'):return '7'
            return '2'
        for entry in entries:
            rownum=int(entry['row'])
            if rownum < 2 or rownum >= 1_048_576:raise ValueError(f'Row {rownum} cannot be exported to {sheet}')
            final_rows[sheet]=max(final_rows.get(sheet,1),rownum)
            row=index.get(rownum)
            source_styles={}
            if entry.get('style_origin'):
                origin=entry['style_origin']
                if origin['sheet'] in REGISTER_SHEETS:
                    source_root=src.sheet(origin['sheet'])
                    source_row=next((r for r in source_root.find(Q('sheetData')).findall(Q('row'))
                                     if int(r.get('r'))==int(origin['row'])),None)
                    if source_row is not None:
                        source_styles={splitcell(c.get('r'))[0]:c.get('s') for c in source_row.findall(Q('c')) if c.get('s') is not None}
            if row is None:
                row=ET.Element(Q('row'),r=str(rownum));rows.append(row);index[rownum]=row
            anchor=next((c for c in row.findall(Q('c')) if c.get('r')==f'A{rownum}'),None)
            fresh = (anchor is None or not str(src.cell_value(anchor) or '').strip()) and any(
                str(v or '').strip() for k,v in entry['changes'].items() if k=='Customer / site')
            if fresh:
                # Restyle every column (not only non-empty imported values).
                # Preserve workbook's table definitions, formula cells and headings.
                for i,h in enumerate(headers,1):
                    column=colname(i)
                    cell=next((c for c in row.findall(Q('c')) if c.get('r')==f'{column}{rownum}'),None)
                    sty=source_styles.get(i,normal_style(column,h))
                    if cell is None:cell_set(row,f'{column}{rownum}',None,style_ref=sty)
                    else:cell.set('s',sty)
                if template_row is not None:
                    row.attrib.pop('s',None)
                    row.attrib.pop('customFormat',None)
                    if template_row.get('ht'):
                        row.set('ht',template_row.get('ht'))
                        row.set('customHeight','1')
            for h,val in entry['changes'].items():
                col=heading.get(h)
                if not col:continue
                sty=(source_styles.get(colno(col),normal_style(col,h)) if fresh else None)
                if h in DATE_FIELDS and isinstance(val,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',val):val=excel_day(val)
                if h in ('Contract amount (£)','Original amount (£)') and isinstance(val,str):
                    try:val=float(val.replace('£','').replace(',',''))
                    except ValueError:pass
                cell_set(row,f'{col}{rownum}',val,style_ref=sty)
            # Rows beyond the old preformatted range must retain the original
            # automatically recalculated renewal-status formula (not stale text).
            if fresh and sheet in ('Maintenance Database','MOD') and 'Renewal status' in heading:
                renewal_col=heading['Renewal status']
                expiry_col=heading.get('Expiry date')
                if not expiry_col:raise ValueError('Missing expiry date header')
                formula_cell=next((c for c in row.findall(Q('c')) if c.get('r')==f'{renewal_col}{rownum}'),None)
                if formula_cell is not None and formula_cell.find(Q('f')) is None:
                    for existing in list(formula_cell):formula_cell.remove(existing)
                    formula_cell.attrib.pop('t',None)
                    formula = f'IF($A{rownum}="","",IF(${expiry_col}{rownum}="","No expiry date",IF(${expiry_col}{rownum}<TODAY(),"Expiry passed – check",IF(${expiry_col}{rownum}<=TODAY()+30,"Due within 30 days",IF(${expiry_col}{rownum}<=TODAY()+90,"Due in 31–90 days","Over 90 days")))))'
                    formula_cell.append(ET.Element(Q('f')))
                    formula_cell.find(Q('f')).text=formula
        ordered=sorted(rows.findall(Q('row')),key=lambda x:int(x.get('r')))
        for r in rows.findall(Q('row')):rows.remove(r)
        rows.extend(ordered)
        originals[src.sheet_parts[sheet]]=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
        touched.append(sheet)
    # Grow affected Excel table definitions and the filter/dropdown boundaries.
    # Untouched template ZIP parts remain byte-for-byte identical.
    from .table_growth import extend_ooxml_tables
    extend_ooxml_tables(src, originals, final_rows)
    # Ensure Excel refreshes formulas after updates. Core workbook calculation settings only.
    if touched:
        root=ET.fromstring(src.z.read('xl/workbook.xml'))
        calc=root.find(Q('calcPr'))
        if calc is None:calc=ET.SubElement(root,Q('calcPr'))
        calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1')
        originals['xl/workbook.xml']=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
    with zipfile.ZipFile(output_path,'w') as output:
        for item in src.z.infolist():
            output.writestr(item,originals.get(item.filename,src.z.read(item.filename)))
    src.z.close()
    return touched
