"""Expand the approved OOXML Excel tables without rebuilding the workbook.

Only the affected worksheet and table XML parts are modified. The approved
workbook's untouched styles, charts, relationships, notes and other ZIP parts
are copied verbatim by the existing exporter.
"""
from __future__ import annotations
import re
from lxml import etree as ET
from .excel_io import NS, Q, splitcell, colname

TABLE_TO_SHEET = {
    'ContractsRegister': 'Maintenance Database',
    'MODContractsRegister': 'MOD',
    'ExpiredHistoryRegister': 'Expired',
    'WeeklyValuesRegister': 'Weekly Values',
    'InvoiceRunRegister': 'Invoices',
    'QuotationRegister': 'Quotes',
}
MAX_EXCEL_ROWS = 1_048_576
CELL_RANGE = re.compile(r'^\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$')


def expand_reference(ref: str, new_last_row: int) -> str:
    """Extend the bottom row of an A1 table/sqref token, never shrink it."""
    m = CELL_RANGE.fullmatch(ref)
    if not m:
        raise ValueError(f'Unsupported Excel cell range: {ref}')
    c1, r1, c2, r2 = m.groups()
    old_end = int(r2 or r1)
    end = max(old_end, new_last_row)
    return f'{c1}{r1}:{c2 or c1}{end}'


def extend_validation_and_colour_rules(root, new_end):
    # Keep validation on new rows even beyond the workbook's original safety buffer.
    container = root.find(Q('dataValidations'))
    if container is not None:
        by_col = {}
        for rule in container.findall(Q('dataValidation')):
            for token in rule.get('sqref', '').split():
                m = CELL_RANGE.fullmatch(token)
                if m:
                    col = m.group(1)
                    last = int(m.group(4) or m.group(2))
                    by_col[col] = max(by_col.get(col, 0), last)
        for rule in container.findall(Q('dataValidation')):
            tokens = []
            for token in rule.get('sqref', '').split():
                m = CELL_RANGE.fullmatch(token)
                if m and int(m.group(4) or m.group(2)) == by_col.get(m.group(1)) and new_end > by_col[m.group(1)]:
                    token = expand_reference(token, new_end)
                tokens.append(token)
            if tokens:
                rule.set('sqref', ' '.join(tokens))
    # The original renewal colour rule starts at L2; extending that existing
    # rule preserves its relative formula references and Excel behaviour.
    for rule in root.findall(Q('conditionalFormatting')):
        tokens = rule.get('sqref', '').split()
        if 'L2:L803' in tokens and new_end > 803:
            rule.set('sqref',' '.join('L2:L'+str(new_end) if t=='L2:L803' else t for t in tokens))


def extend_ooxml_tables(src, changes: dict[str, bytes], final_rows: dict[str, int]):
    """Adjust affected table ranges, AutoFilters, dimensions and validation ranges.

    final_rows maps tab name to maximum populated row during this export.
    Handles sheets whose table extends beyond the current sheet dimension.
    """
    if not final_rows:
        return {}
    table_names = set()
    for part in src.z.namelist():
        if not part.startswith('xl/tables/') or not part.endswith('.xml'):
            continue
        root = ET.fromstring(src.z.read(part))
        name = root.get('name', '')
        sheet = TABLE_TO_SHEET.get(name)
        if sheet not in final_rows:
            continue
        m = CELL_RANGE.fullmatch(root.get('ref',''))
        if not m:
            raise ValueError(f'Cannot safely expand Excel table {name}: unknown range')
        last = int(m.group(4) or m.group(2))
        end = max(last, int(final_rows[sheet]))
        if end >= MAX_EXCEL_ROWS:
            raise ValueError(f'{sheet} has reached the Excel worksheet row limit')
        table_names.add(sheet)
        if end > last:
            root.set('ref', expand_reference(root.get('ref'),end))
            filt = root.find(Q('autoFilter'))
            if filt is None:
                raise ValueError(f'Cannot expand {name} without its original filter')
            filt.set('ref',expand_reference(filt.get('ref'),end))
            changes[part] = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
        name_part=src.sheet_parts[sheet]
        if name_part in changes:
            sheet_root=ET.fromstring(changes[name_part])
            dim=sheet_root.find(Q('dimension'))
            if dim is not None and dim.get('ref'):
                old_dim=dim.get('ref')
                dim_end=int(CELL_RANGE.fullmatch(old_dim).group(4) or CELL_RANGE.fullmatch(old_dim).group(2))
                if end > dim_end: dim.set('ref', expand_reference(old_dim,end))
            if end > last:
                extend_validation_and_colour_rules(sheet_root,end)
            changes[name_part]=ET.tostring(sheet_root,encoding='UTF-8',xml_declaration=True)
    missing=set(final_rows)-table_names
    if missing:
        raise ValueError('Cannot export: expected approved Excel table missing for '+', '.join(sorted(missing)))
    return {s:int(final_rows[s]) for s in table_names}
