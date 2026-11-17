"""Loss-minimising reviewed Excel round-trip for approved 8/10-tab templates.

The export identifier sits in standard OOXML core keywords, not an extra tab,
so the approved visible layout stays unchanged. If metadata is removed by an
editor, the import is refused instead of inventing a comparison baseline.
"""
from __future__ import annotations
import datetime as dt,io,json,os,tempfile,zipfile,re
from pathlib import Path
from lxml import etree as ET
from .excel_io import ExcelSource,REGISTER_SHEETS,register_sheets
from .data_readiness import WORKSHEETS,CURRENT_WORKSHEETS

CP='http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
DC='http://purl.org/dc/elements/1.1/'
Q=lambda ns,tag:f'{{{ns}}}{tag}'
PREFIX='PulseContractsExport:'
DERIVED={'Renewal status','Record ID','Original source'}


def attach_export_id(path, export_id):
    """Set standard OOXML document keywords; avoid changing workbook layout."""
    with zipfile.ZipFile(path,'r') as zin:
        parts=[(info,zin.read(info.filename)) for info in zin.infolist()]
    changed=[]
    for info,data in parts:
        if info.filename=='docProps/core.xml':
            root=ET.fromstring(data)
            kw=root.find(Q(CP,'keywords'))
            if kw is None:kw=ET.SubElement(root,Q(CP,'keywords'))
            old=str(kw.text or '').strip()
            old=re.sub(r'(?:^|\s)PulseContractsExport:[A-Fa-f0-9-]+','',old).strip()
            kw.text=(old+' '+PREFIX+export_id).strip()
            data=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
        changed.append((info,data))
    with tempfile.NamedTemporaryFile(dir=str(Path(path).parent),suffix='.xlsx',delete=False) as handle:
        tmp=handle.name
    try:
        with zipfile.ZipFile(tmp,'w') as zout:
            for info,data in changed:zout.writestr(info,data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.remove(tmp)


def read_export_id(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        root=ET.fromstring(z.read('docProps/core.xml'))
        kw=root.find(Q(CP,'keywords'))
        m=re.search(r'PulseContractsExport:([A-Fa-f0-9-]{36})',str(kw.text if kw is not None else ''))
        return m.group(1) if m else None


def parse_workbook_records(content):
    with tempfile.NamedTemporaryFile(suffix='.xlsx',delete=False) as temp:
        temp.write(content);path=temp.name
    try:
        src=ExcelSource(path)
        try:
            sheets=list(register_sheets(src))+['Weekly Values','Invoices','Quotes']
            if src.sheet_names not in (WORKSHEETS,CURRENT_WORKSHEETS):
                raise ValueError('The workbook does not match the supported eight/ten-tab Master layout.')
            data={}
            for sheet in sheets:
                headers,rows=src.records(sheet)
                if sheet in register_sheets(src) and not {'Customer / site','Contract number','Record ID'}.issubset(set(headers)):
                    raise ValueError(f'{sheet} is missing essential column headings.')
                if sheet in ('Weekly Values','Invoices','Quotes') and 'Original source' not in headers:
                    raise ValueError(f'{sheet} does not have the expected source identifier.')
                data[sheet]=rows
            return data
        finally:src.z.close()
    finally:os.unlink(path)


def normal(value):
    if value is None:return ''
    if isinstance(value,str):
        value=value.strip()
        if not value:return ''
        # numeric value types must not create spurious changes if Excel round-trips 15.0
        return value
    if isinstance(value,(int,float)):
        if isinstance(value,float) and value.is_integer():return str(int(value))
        return format(value,'.12g')
    return str(value).strip()


def diff_workbook(baseline, current_records, uploaded):
    """Three-way comparison of two contract register sheets.

    Excludes computed and identity cells. Never mutates records. New rows without
    stable keys become explicit 'new' candidates, not implicit customer matches.
    """
    matches=[];warnings=[];seen=set()
    base=baseline.get('contracts',{})
    current={str(x['row_key']):x for x in current_records}
    current_signatures={(normal(x['fields'].get('Customer / site')).casefold(),normal(x['fields'].get('Contract number')).casefold()) for x in current_records if normal(x['fields'].get('Contract number')) not in ('','?')}
    for sheet,items in uploaded.items():
        if sheet in ('Weekly Values','Invoices','Quotes'):
            from_ledger=baseline.get('ledger',{})
            live=baseline.get('live_ledger',{})  # overridden by caller, not trusted from export snapshot
            for item in items:
                fields=item['fields'];identifier=normal(fields.get('Quote ID' if sheet=='Quotes' else 'Original source'))
                code=sheet+'::'+identifier
                if not identifier:
                    warnings.append(f'{sheet} row {item["row"]} lacks its stable original source. Add new entries in the application.')
                    continue
                if code in seen:
                    warnings.append(f'{sheet} source identifier {identifier} appears more than once and cannot be imported.')
                    continue
                seen.add(code)
                if code not in from_ledger:
                    warnings.append(f'{sheet} source {identifier} was not part of the original Excel export.')
                    continue
                old=from_ledger[code];current_item=live.get(code)
                if not current_item:
                    warnings.append(f'{sheet} source {identifier} is not present in the current platform.')
                    continue
                edits=[]
                for field,original in old['fields'].items():
                    if field in ('Original source','Quote ID'):continue
                    val=fields.get(field,'')
                    if normal(val)==normal(original):continue
                    existing=current_item['fields'].get(field,'')
                    if normal(val)==normal(existing):continue
                    edits.append({'field':field,'original':original,'current':existing,'incoming':val,
                                  'conflict':normal(existing)!=normal(original)})
                if edits:
                    matches.append({'key':code,'ledger_id':current_item['id'],'contract_id':None,
                                    'sheet':sheet,'row':item['row'],'action':'update_ledger',
                                    'changes':edits,'revision':current_item['revision']})
            continue
        for item in items:
            f=item['fields'];key=normal(f.get('Record ID'))
            if not normal(f.get('Customer / site')):continue
            if key in seen and key:
                warnings.append(f'Duplicate record identifier {key} in the uploaded workbook; no changes for that identifier can be approved.')
                continue
            if key:seen.add(key)
            if key and key in base:
                before=base[key];live=current.get(key)
                if not live:
                    warnings.append(f'{key} no longer exists in the platform. Review outside this import.')
                    continue
                if live.get('source_sheet')!=before['sheet']:
                    warnings.append(f'{key} has changed status in the platform since export. Compare against a fresh download.')
                    continue
                moved=sheet!=before['sheet']
                if moved and sheet not in ('Maintenance Database','MOD','Expired'):
                    warnings.append(f'{key} was moved to an unsupported tab.')
                    continue
                edits=[];base_fields=before['fields'];live_fields=live['fields']
                if moved:
                    # Cutting and pasting an entire row is safe only when no
                    # previously populated values disappear accidentally.
                    missing=[field for field,val in base_fields.items() if field not in DERIVED
                             and normal(val) and not normal(f.get(field))]
                    if missing:
                        warnings.append(f'{key} moved to {sheet}, but {len(missing)} previously populated fields were lost ({", ".join(missing[:4])}). Copy the entire row, including all columns. Transfer not proposed.')
                        continue
                for field,old in base_fields.items():
                    if field in DERIVED:continue
                    val=f.get(field,'')
                    if normal(val)==normal(old):continue
                    current_val=live_fields.get(field,'')
                    if normal(val)==normal(current_val):continue
                    edits.append({'field':field,'original':old,'current':current_val,'incoming':val,
                        'conflict':normal(current_val)!=normal(old)})
                if edits or moved:
                    matches.append({'key':key,'contract_id':live['id'],'sheet':sheet,'row':item['row'],
                                    'action':'move' if moved else 'update', 'from_sheet':before['sheet'],
                                    'changes':edits,'revision':live['revision']})
            elif key:
                warnings.append(f'{key} was not present in this export snapshot. No updates were proposed for it.')
            else:
                # New user-entered row: requires explicit approval as a new contract.
                candidate={k:v for k,v in f.items() if k not in DERIVED and normal(v)}
                signature=(normal(candidate.get('Customer / site')).casefold(),normal(candidate.get('Contract number')).casefold())
                duplicate=bool(signature[1] and signature[1]!='?' and signature in current_signatures)
                matches.append({'key':'','contract_id':None,'sheet':sheet,'row':item['row'],
                                'action':'new','possible_duplicate':duplicate,
                                'changes':[{'field':k,'incoming':v,'conflict':False} for k,v in candidate.items()],
                                'revision':None})
    return {'items':matches,'warnings':warnings,'count':len(matches),
            'conflicts':sum(1 for x in matches for c in x['changes'] if c['conflict'])}
