"""Optional external document reading + conservative contract evidence parsing.

This is a document-reading adapter, not a contract decision engine. Invoices,
pricing and asset warranties are *never* interpreted as agreed recurring terms.
All candidate fields require explicit staff approval in main.py.
"""
from __future__ import annotations
import json, os, re, time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REFERENCE_RE = re.compile(r'\bC[ -]?(9\d{5,6})\b', re.IGNORECASE)
INVOICE_RE = re.compile(r'\b(?:Invoice(?: number| no\.?| ref\.?| reference)?)[\s:#-]*(\d{6,10})\b', re.IGNORECASE)
PRODUCT_RE = re.compile(r'(?<![\w-])\d{2,4}[A-Z]-[A-Z0-9]{2,7}(?![\w-])', re.IGNORECASE)
ACCOUNT_RE = re.compile(r'\b(?:Account Ref|Account Reference)[\s:#-]*(\d{4,12})\b', re.IGNORECASE)

class DocumentAIError(Exception):pass

def configured():
    return bool(os.environ.get('PULSE_AZURE_DOC_ENDPOINT') and os.environ.get('PULSE_AZURE_DOC_KEY'))

def _request(req,timeout=40):
    try:
        with urlopen(req,timeout=timeout) as response:
            return response.headers, response.read()
    except (URLError, HTTPError, TimeoutError) as error:
        raise DocumentAIError('Document reading service could not complete the request. Check its configuration and connectivity.') from error

def read_scanned_pdf(pdf:bytes):
    """Azure Document Intelligence prebuilt-layout 2024-11-30; return page line text.

    Must be intentionally configured by IT; no hardcoded credentials and no
    connections to external services on the standard local prototype.
    """
    endpoint=os.environ.get('PULSE_AZURE_DOC_ENDPOINT','').rstrip('/')
    key=os.environ.get('PULSE_AZURE_DOC_KEY','')
    if not endpoint or not key:raise DocumentAIError('Document AI is not configured')
    parsed=urlparse(endpoint)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:
        raise DocumentAIError('Document AI endpoint must use a valid HTTPS URL')
    url=endpoint+'/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30'
    headers,raw=_request(Request(url,data=pdf,headers={'Ocp-Apim-Subscription-Key':key,'Content-Type':'application/pdf'},method='POST'))
    location=headers.get('Operation-Location')
    if not location or urlparse(location).netloc!=parsed.netloc:
        raise DocumentAIError('Document AI returned an invalid operation location')
    for _ in range(25):
        time.sleep(1.5)
        _,raw=_request(Request(location,headers={'Ocp-Apim-Subscription-Key':key}))
        result=json.loads(raw)
        if result.get('status')=='succeeded':
            pages=[]
            for page in result.get('analyzeResult',{}).get('pages',[]):
                text='\n'.join(line.get('content','') for line in page.get('lines',[]))
                pages.append({'page':page.get('pageNumber',len(pages)+1),'text':text,'source':'Azure Document Intelligence layout'})
            return pages
        if result.get('status')=='failed':raise DocumentAIError('The document-reading service could not analyse this PDF')
    raise DocumentAIError('Document reading timed out. The PDF can still be reviewed manually.')

def extract_evidence(pages):
    """Return traceable *candidates*. Never assign invoice numbers to contracts."""
    ref_pages={}
    invoice_pages={}
    items={}
    accounts={}
    for page in pages:
        p=page['page'];text=page['text']
        for match in REFERENCE_RE.finditer(text):
            ref_pages.setdefault(match.group(1),set()).add(p)
        for match in INVOICE_RE.finditer(text):
            invoice_pages.setdefault(match.group(1),set()).add(p)
        for match in PRODUCT_RE.finditer(text):
            items.setdefault(match.group(0).upper(),set()).add(p)
        for match in ACCOUNT_RE.finditer(text):
            accounts.setdefault(match.group(1),set()).add(p)
    def collection(source):return [{'value':v,'pages':sorted(p)} for v,p in source.items()]
    return {'contract_references':collection(ref_pages),'invoice_references':collection(invoice_pages),
            'equipment_codes':collection(items),'account_references':collection(accounts),
            'page_count':len(pages), 'warning':'Possible references only. Check each item against the original source before approval.'}

def reference_proposals(pages):
    evidence=extract_evidence(pages)
    proposals=[]
    for i,entry in enumerate(evidence['contract_references'][:30],1):
        proposals.append({'id':i,'page':', '.join(map(str,entry['pages'])),
            'confidence':'Document candidate – verify','fields':{'Contract number':entry['value']},
            'evidence':'C-prefixed possible contract reference seen in document. Customer and terms must be confirmed.',
            'source':'Document line extraction', 'approved':False, 'target_contract_id':None})
    return proposals,evidence
