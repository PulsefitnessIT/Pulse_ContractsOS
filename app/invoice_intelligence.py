"""Conservative page-level invoice grouping from document-reading text.

This module does NOT interpret handwritten contractual terms or infer prices,
cover, invoice-to-contract relationships, quantities or serial numbers.
Evidence is a navigation aid for human approval, not source of truth.
"""
from __future__ import annotations
import re

# Require the printed label and number together; never treat a payment account,
# sales order number, or contract identifier as an invoice number.
INVOICE = re.compile(r"\bInvoice(?:\s*(?:No\.?|Number|Reference|Ref\.?|#))?\s*[:#-]?\s*(0*\d{6,10})\b",re.I)
ACCOUNT = re.compile(r"\bAccount\s*(?:Ref\.?|Reference)\s*[:#-]?\s*(0*\d{4,12})\b",re.I)
SALES_ORDER = re.compile(r"\bSales\s*Order\s*(?:Ref\.?|Reference|No\.?)?\s*[:#-]?\s*(0*\d{4,12})\b",re.I)
DATE = re.compile(r"\bInvoice\s*Date\s*[:#-]?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",re.I)
ASSET_HINT = re.compile(r"\b(?:equipment\s*schedule|asset\s*list)\b",re.I)

def _find(regex, text):
    match=regex.search(text)
    return match.group(1) if match else None

def invoice_groups(pages):
    """Group adjacent printed invoice pages with the same invoice number.

    Mixed PDFs might contain unnamed continuation pages. These are allocated
    to the last identified invoice *only when directly adjacent*, and marked
    inferred; pages preceding the first invoice remain unassigned.
    """
    ordered=sorted((p for p in pages if isinstance(p.get('page'),int)),key=lambda x:x['page'])
    groups=[];last=None;unassigned=[];assigned=set()
    for item in ordered:
        page=int(item['page']);text=str(item.get('text') or '')
        # Invoice number must be printed close to its label, not a stray number.
        number=_find(INVOICE,text)
        if number:
            group=last if last is not None and last['invoice_number']==number and last['pages'][-1]==page-1 else None
            if group is None:
                group={'invoice_number':number,'pages':[],'continuation_pages':[],
                       'invoice_dates':[],'account_references':[],'sales_order_references':[],
                       'source':'Printed invoice headings (OCR may contain errors)',
                       'requires_review':True}
                groups.append(group)
            last=group
        elif last is not None and last['pages'] and page==last['pages'][-1]+1 and not ASSET_HINT.search(text) and not re.search(r'\binvoice\b',text,re.I):
            group=last;group['continuation_pages'].append(page)
        else:
            unassigned.append(page);last=None;continue
        if page not in group['pages']:
            group['pages'].append(page);assigned.add(page)
        for rx,key in ((DATE,'invoice_dates'),(ACCOUNT,'account_references'),(SALES_ORDER,'sales_order_references')):
            value=_find(rx,text)
            if value and value not in group[key]:group[key].append(value)
    # OCR may read the same long invoice number differently on different pages.
    # Flag near-identical numbers but never silently merge them.
    import difflib
    ocr_conflicts=[]
    for a in range(len(groups)):
        for b in range(a+1,len(groups)):
            left=groups[a]['invoice_number'];right=groups[b]['invoice_number']
            if left!=right and len(left)==len(right) and difflib.SequenceMatcher(None,left,right).ratio()>=0.86:
                ocr_conflicts.append({'invoice_numbers':[left,right],
                  'pages':[groups[a]['pages'],groups[b]['pages']],
                  'warning':'Similar printed invoice numbers detected; verify against the source pages.'})
    for i,a in enumerate(groups):
        for b in groups[i+1:]:
            if a['invoice_number']==b['invoice_number']:
                ocr_conflicts.append({'invoice_numbers':[a['invoice_number'],b['invoice_number']],
                    'pages':[a['pages'],b['pages']],
                    'warning':'Same invoice number appears in separated page groups; check whether these are duplicate or continuation pages.'})
    allpages={int(p['page']) for p in ordered}
    return {'groups':groups,'possible_ocr_conflicts':ocr_conflicts,'unassigned_pages':sorted(allpages-assigned),
            'warning':'Possible invoice groupings only. Confirm invoice numbers and original pages. No financial or contractual terms were inferred.'}
