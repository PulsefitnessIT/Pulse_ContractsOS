"""Evidence-based coordinator queue for imported documents.

Only reports review progress; never assumes OCR confidence, contractual approval,
or financial posting. Input records are historical imports + explicit staff reviews.
"""
from __future__ import annotations
import csv
import io
import json


def build_review_queue(import_rows, review_rows):
    reviews = {}
    for row in review_rows:
        reviews.setdefault(row['import_id'], set()).add(row['group_id'])
    items = []
    for row in import_rows:
        iid = row['id']
        filename = row['filename']
        if row['type'] != 'pdf':
            # Excel/CSV record proposals have their own existing approval flow.
            if row['status'] not in ('Approved', 'Complete'):
                items.append({'import_id': iid, 'filename': filename, 'type': 'Spreadsheet',
                    'group_id': '', 'pages': [], 'reference': '', 'status': 'Needs review',
                    'reason': 'Review imported spreadsheet contract proposals',
                    'next_action': 'Review suggested contracts'})
            continue
        try:
            evidence = json.loads(row['evidence_json'] or '{}')
        except (ValueError, TypeError):
            evidence = {}
        analysis = evidence.get('invoice_review') or {}
        groups = analysis.get('invoices') or [
            {'id':f'inv-{i}', 'detected_invoice_number':g.get('invoice_number',''),
             'pages':g.get('pages',[]), 'conflicts':[], 'field_candidates':[]}
            for i,g in enumerate((evidence.get('invoice_groups') or {}).get('groups',[]),1)]
        verified = reviews.get(iid, set())
        for group in groups:
            conflicts = group.get('conflicts') or []
            dates = {x['value'] for x in group.get('field_candidates',[]) if x.get('field')=='Invoice date'}
            missing = []
            if not dates: missing.append('invoice date not extracted')
            if conflicts: missing.append(f'{len(conflicts)} conflicting field reading(s)')
            pages = group.get('pages') or []
            flagged_ocr = any('ocr' in str(src.get('source','')).lower() or 'Azure' in str(src.get('source',''))
                for src in evidence.get('page_sources',[]) if src.get('page') in pages)
            if flagged_ocr: missing.append('scanned text requires visual confirmation')
            done = group.get('id') in verified
            items.append({'import_id':iid, 'filename':filename,'type':'Invoice',
                'group_id':group.get('id',''),'pages':pages,
                'reference':group.get('detected_invoice_number',''),
                'status':'Source verified' if done else 'Needs review',
                'reason':'Source checked and recorded; not posted to Master' if done else
                   ('; '.join(missing) if missing else 'Confirm extracted fields against the original invoice'),
                'next_action':'Review recorded evidence' if done else 'Check the original invoice'})
        unassigned = analysis.get('unassigned')
        if unassigned is None:
            unassigned = [{'page':p,'reason':'No reliable printed invoice reference'}
                for p in (evidence.get('invoice_groups') or {}).get('unassigned_pages',[])]
        for pg in unassigned:
            page = pg.get('page')
            if not isinstance(page,int):continue
            reason = pg.get('reason') or 'Page not assigned to an invoice'
            is_reference = 'equipment register' in reason.lower() or 'asset schedule' in reason.lower()
            reviewed = f'manual-p{page}' in verified
            items.append({'import_id':iid, 'filename':filename,'type':'Unassigned page',
                'group_id':f'manual-p{page}', 'pages':[page], 'reference':'',
                'status':'Source verified' if reviewed else ('Reference only' if is_reference else 'Needs review'),
                'reason':'Page manually confirmed' if reviewed else reason,
                'next_action':'View source' if is_reference or reviewed else 'Identify document / invoice'})
        unread = set(evidence.get('unread_pages') or [])
        indexed = {page for t in items if t['import_id']==iid for page in t['pages']}
        for page in sorted(unread-indexed):
            items.append({'import_id':iid,'filename':filename,'type':'Unreadable page',
                'group_id':'','pages':[page],'reference':'','status':'Needs review',
                'reason':'No readable text extracted', 'next_action':'Inspect original page'})
        if not groups and not unassigned and not unread:
            items.append({'import_id':iid,'filename':filename,'type':'Document',
                'group_id':'','pages':[],'reference':'','status':'Needs review',
                'reason':'No invoice references identified', 'next_action':'Inspect original document'})
    counts={s:sum(1 for item in items if item['status']==s) for s in ('Needs review','Source verified','Reference only')}
    return {'counts':counts,'total':len(items),'items':items,
        'disclaimer':'Review status confirms source checking only, not an approved contract, equipment entitlement, or invoice posting.'}


def queue_csv(data):
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(['File','Document type','Reference detected','Source page(s)','Review status','Reason','Next action','Import ID'])
    for item in data['items']:
        values=[item['filename'],item['type'],item['reference'],','.join(map(str,item['pages'])),
                item['status'],item['reason'],item['next_action'],str(item['import_id'])]
        # Excel should display all untrusted extracted text literally, not as formulae.
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in values])
    return '\ufeff'+output.getvalue()
