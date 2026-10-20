"""V7 deterministic document-to-contract candidate matching.

A suggestion is not proof. Customer names, invoice accounts and equipment codes
are not globally unique. Only exact contract references with corroborating
context can be preselected; all imported facts still require human approval.
"""
from __future__ import annotations
import re, unicodedata
from difflib import SequenceMatcher

CONTRACT_KEYS=('Contract number',)
SITE_KEYS=('Customer / site',)
INVOICE_ACCOUNT_KEYS=('Invoice account',)
SITE_ACCOUNT_KEYS=('Site account',)
DATE_KEYS=('Start date','Expiry date')


def normal_number(value):
    s=re.sub(r'\s+','',str(value or '').upper())
    return s[1:] if re.fullmatch(r'C\d{5,9}',s) else s

def normal_account(value):
    # A valid matching reference is numerical; ignore long descriptions.
    s=str(value or '').strip()
    m=re.fullmatch(r'(\d{4,12})(?:\s*\(Sage\))?',s,re.I)
    return m.group(1).lstrip('0') or '0' if m else ''

def normal_site(value):
    text=unicodedata.normalize('NFKD',str(value or '')).lower().replace('&',' and ')
    text=re.sub(r'[^a-z0-9]+',' ',text)
    text=re.sub(r'\b(the|limited|ltd|plc)\b',' ',text)
    return ' '.join(text.split())

def similarity(a,b):
    x,y=normal_site(a),normal_site(b)
    if not x or not y:return 0.0
    return SequenceMatcher(None,x,y).ratio()

def candidate_matches(query, records, limit=6):
    """Return human-readable candidates and strict, optional suggested target.

    records are dictionaries with id, fields, status. No database writes.
    """
    qnum=normal_number(query.get('Contract number'))
    qsite=str(query.get('Customer / site') or '').strip()
    qinvoice=normal_account(query.get('Invoice account'))
    qaccount=normal_account(query.get('Site account'))
    ranked=[]
    for row in records:
        if row.get('status','Active')!='Active':continue
        f=row.get('fields') or {}
        num=normal_number(f.get('Contract number'))
        site=str(f.get('Customer / site') or '')
        sim=similarity(qsite,site)
        exactnum=bool(qnum and num and qnum==num)
        othernum=bool(qnum and num and qnum!=num)
        inv_equal=bool(qinvoice and normal_account(f.get('Invoice account'))==qinvoice)
        site_account_equal=bool(qaccount and normal_account(f.get('Site account'))==qaccount)
        date_same=[k for k in DATE_KEYS if query.get(k) and f.get(k) and str(query[k])==str(f[k])]
        date_conflict=[k for k in DATE_KEYS if query.get(k) and f.get(k) and str(query[k])!=str(f[k])]
        site_conflict=bool(qsite and site and sim<0.45)
        site_account_conflict=bool(qaccount and normal_account(f.get('Site account')) and not site_account_equal)
        reasons=[];warnings=[];score=0
        if exactnum:score+=80;reasons.append('Contract reference matches exactly')
        if qsite and site and sim>=0.90:score+=28;reasons.append('Site name is a close match')
        elif qsite and site and sim>=0.75:score+=16;reasons.append('Site name is similar; verify location')
        elif site_conflict:
            score-=32;warnings.append('Customer/site name differs significantly')
        if site_account_equal:score+=25;reasons.append('Site account reference matches')
        elif site_account_conflict:warnings.append('Site account reference differs')
        if inv_equal:score+=8;reasons.append('Invoice account matches (may cover multiple sites)')
        if date_same:score+=10*len(date_same);reasons.append('Matching '+', '.join(date_same).lower())
        if date_conflict:warnings.append('Contract dates differ: '+', '.join(date_conflict))
        if othernum:
            score-=50;warnings.append('Different contract reference: do not overwrite another agreement')
        # Never match using a generic shared invoice account or similar customer alone.
        if not exactnum and not (sim>=0.75 or site_account_equal):continue
        if score<8 and not exactnum:continue
        ranked.append({'id':row['id'],'score':max(0,score),'fields':{
            'Customer / site':site,'Contract number':str(f.get('Contract number') or ''),
            'Site account':str(f.get('Site account') or ''),'Invoice account':str(f.get('Invoice account') or ''),
            'Start date':str(f.get('Start date') or ''),'Expiry date':str(f.get('Expiry date') or '')},
            'exact_contract_number':exactnum,'same_site':sim>=0.75,'reasons':reasons,'warnings':warnings})
    ranked.sort(key=lambda v:(v['exact_contract_number'],v['score'],v['same_site']),reverse=True)
    # Repeated contract references can occur across equipment groups / locations;
    # even the highest-scoring such match must be selected manually.
    numbered=[x for x in ranked if x['exact_contract_number']]
    auto=None
    if len(numbered)==1:
        top=numbered[0]
        corroborated=(top['same_site'] or 'Site account reference matches' in top['reasons'] or any(r.startswith('Matching ') for r in top['reasons']))
        serious=any('differs significantly' in w or 'Site account reference differs' in w for w in top['warnings'])
        # Contract dates may differ because this is a renewal, so flag for review
        # but allow preview if independent identity evidence is present.
        if corroborated and not serious:auto=top['id']
    return {'candidates':ranked[:max(1,min(limit,20))],
            'suggested_target_id':auto,
            'requires_manual_selection':auto is None,
            'warning':('Several records share this contract reference; choose the correct customer/site.' if len(numbered)>1 else
                       'Suggestions are not confirmed matches. Check the original document and existing record before approval.')}
