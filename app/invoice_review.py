"""Evidence-first invoice extraction, for staff review only.

Uses printed/embedded text and OCR; no amounts, dates or contract associations
are ever written into the Maintenance Master by this module.
"""
from __future__ import annotations
import datetime as dt
import re
from collections import defaultdict
from .invoice_intelligence import invoice_groups, INVOICE, ACCOUNT, SALES_ORDER, DATE, ASSET_HINT
from .document_ai import PRODUCT_RE

MONEY_RE = re.compile(r'(?:£|\bGBP\s*)(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})', re.I)
MONEY_LABELS = {
    'net': re.compile(r'^\s*(?:net(?:\s+total)?|subtotal|sub\s*total)\s*[:£ ]+', re.I),
    'vat': re.compile(r'^\s*(?:vat(?:\s+at\s*\d+%)?)\s*[:£ ]+', re.I),
    'gross': re.compile(r'^\s*(?:gross|total\s+including\s+vat|invoice\s+total)\s*[:£ ]+', re.I),
}
DATE_ANY = re.compile(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2})\b')
WARRANTY_WORDING = re.compile(r'\b(?:warranty|parts\s+and\s+labour|service\s+per\s+annum)\b',re.I)


def _iso_date(text):
    """Convert fully labelled UK invoice dates; never guess 2-digit years."""
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%Y-%m-%d'):
        try:
            val=dt.datetime.strptime(text.strip(),fmt).date()
            if dt.date(2000,1,1)<=val<=dt.date(2100,12,31):return val.isoformat()
        except ValueError:pass
    return None


def _confidence(page):
    return 'OCR – visually confirm' if 'ocr' in str(page.get('source','')).lower() or 'Azure' in str(page.get('source','')) else 'Embedded text – verify'


def _candidates(page):
    lines=[s.strip() for s in str(page.get('text') or '').splitlines() if s.strip()]
    result=[]
    for index,line in enumerate(lines):
        line=' '.join(line.split())
        # A printed invoice label and reference are necessary. Sales order refs and
        # payment reference numbers must never be treated as invoice references.
        match=INVOICE.search(line)
        if match and re.fullmatch(r'\d{6,10}',match.group(1)):
            result.append({'field':'Invoice number','value':match.group(1),'page':page['page'],
                           'snippet':line[:200],'confidence':_confidence(page)})
        match=DATE.search(line)
        if match:
            value=_iso_date(match.group(1))
            if value:result.append({'field':'Invoice date','value':value,'page':page['page'],
                                    'snippet':line[:200],'confidence':_confidence(page)})
        for regex,name in ((ACCOUNT,'Account reference'),(SALES_ORDER,'Sales order reference')):
            match=regex.search(line)
            if match:
                result.append({'field':name,'value':match.group(1),'page':page['page'],
                               'snippet':line[:200],'confidence':_confidence(page)})
        # Only accept a monetary amount if label and value are on the SAME line.
        # Do not infer from item line costs or misread unlabelled totals.
        for key,label in [('net','Net total'),('vat','VAT total'),('gross','Gross total')]:
            if MONEY_LABELS[key].search(line):
                v=MONEY_RE.findall(line)
                if len(v)==1:
                    result.append({'field':label,'value':v[0].replace(',',''),'page':page['page'],
                                   'snippet':line[:200],'confidence':_confidence(page)})
                    break
        if WARRANTY_WORDING.search(line) and len(line)<185:
            result.append({'field':'Warranty wording (not contractual proof)','value':line[:185],
                           'page':page['page'],'snippet':line[:185],'confidence':_confidence(page)})
    return result


def analyse_invoice_document(pages):
    """Invoice groups with evidence lines, conflicts and unassigned pages.

    The match status always requires staff verification. A missing or ambiguous
    reference is *not* repaired by guessed characters or proximity alone.
    """
    ordered=sorted([p for p in pages if isinstance(p.get('page'),int)],key=lambda x:x['page'])
    grouped=invoice_groups(ordered)
    by_page={p['page']:p for p in ordered}
    invoices=[]
    for pos,g in enumerate(grouped['groups'],1):
        rows=[]
        for page in g['pages']:
            if page in by_page:rows+=_candidates(by_page[page])
        fields=defaultdict(dict)
        for entry in rows:
            key=entry['value']
            fields[entry['field']].setdefault(key,[]).append(entry)
        conflicts=[]
        for field,entries in fields.items():
            if field!='Warranty wording (not contractual proof)' and len(entries)>1:
                # Repeated headers might actually be OCR mistakes; do not choose one.
                conflicts.append({'field':field,'values':list(entries),
                                  'warning':'Different readings found. Compare the source pages.'})
        # No automatic financial inference even if arithmetic happens to agree.
        values={k:list(v) for k,v in fields.items()}
        for key in ('Net total','VAT total','Gross total'):
            if key in values and len(values[key])!=1:
                conflicts.append({'field':key,'values':values[key],'warning':'Several amounts found; review before use.'})
        observed = [x for x in values.get('Invoice number',[]) if x==g['invoice_number']]
        if not observed:
            conflicts.append({'field':'Invoice number','values':list(values.get('Invoice number',[])),
                              'warning':'Invoice group reference was not reproduced in its page evidence.'})
        invoices.append({'id':'inv-'+str(pos), 'detected_invoice_number':g['invoice_number'],
              'pages':g['pages'],'inferred_continuations':g['continuation_pages'],
              'field_candidates':rows, 'conflicts':conflicts,
              'equipment_codes':sorted(set(m.group(0).upper() for page in g['pages'] if page in by_page for m in PRODUCT_RE.finditer(by_page[page]['text'])))[:100],
              'review_status':'Needs visual confirmation',
              'warning':'Check the printed invoice number, handwritten references, dates, account and value against the PDF. No Master update occurs.'})
    # An invoice can be present even when OCR misses its identifier; keep those
    # pages accessible rather than attaching them to a neighbouring invoice.
    pending=[]
    for pnum in grouped['unassigned_pages']:
        pg=by_page.get(pnum,{})
        content=str(pg.get('text',''))
        if ASSET_HINT.search(content) and not INVOICE.search(content):reason='Possible equipment register / asset schedule'
        elif re.search(r'\binvoice\b',content,re.I):reason='Possible invoice with unreadable reference'
        elif not content.strip():reason='No readable text'
        else:reason='Unassigned document page'
        pending.append({'page':pnum,'reason':reason})
    return {'invoices':invoices,'unassigned':pending,'possible_ocr_conflicts':grouped['possible_ocr_conflicts'],
            'processed_pages':len(ordered),'requires_review':True,
            'note':'Document evidence only. The invoice register, contract amounts, equipment ownership and Master remain unchanged until separately reviewed.'}


def validate_review(payload,known_group):
    number=str(payload.get('invoice_number') or '').strip()
    if not re.fullmatch(r'\d{6,10}',number):raise ValueError('Enter the verified 6–10 digit invoice number, including any leading zeros.')
    inv_date=str(payload.get('invoice_date') or '').strip()
    if inv_date and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',inv_date) or not _iso_date(inv_date)):
        raise ValueError('Enter a valid invoice date in YYYY-MM-DD format.')
    acc=str(payload.get('account_reference') or '').strip()
    if acc and not re.fullmatch(r'\d{4,12}',acc):raise ValueError('Enter an account reference of 4–12 digits.')
    if not payload.get('confirmed_from_source'):
        raise ValueError('Confirm that you checked this invoice against the original scanned page.')
    if len(str(payload.get('reviewer') or '').strip())<2:raise ValueError('Enter the reviewing coordinator.')
    if len(str(payload.get('notes') or ''))>1000:raise ValueError('Review notes must be no longer than 1,000 characters.')
    if len(str(payload.get('contract_reference') or ''))>40:raise ValueError('Contract reference is too long.')
    return {'invoice_number':number,'invoice_date':inv_date,'account_reference':acc,
        'contract_reference':str(payload.get('contract_reference') or '').strip(),
        'customer_site':str(payload.get('customer_site') or '').strip()[:200],
        'notes':str(payload.get('notes') or '').strip(),
        'reviewer':str(payload['reviewer']).strip()[:100], 'group_id':known_group['id'],
        'pages':known_group['pages'], 'original_detected_invoice_number':known_group['detected_invoice_number']}
