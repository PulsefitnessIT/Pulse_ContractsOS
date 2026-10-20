"""Read-only matching of the separately supplied service planner to active contracts.

The planner filename says 2020 but its records contain dates up to the 2030s.
Nothing from the source is treated as service completion until reviewed.
"""
import json,re,unicodedata,datetime as dt
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict,Counter

SOURCE=Path(__file__).parent.parent/'data'/'service_planner_source.json'

def tidy(v):
    t=unicodedata.normalize('NFKD',str(v or '')).casefold()
    t=re.sub(r'\([^)]*\)',' ',t)
    t=re.sub(r'[^a-z0-9]+',' ',t)
    return ' '.join(t.split())

def contract_id(v):
    s=re.sub(r'\s+','',str(v or '').upper())
    if re.fullmatch(r'C?\d{4,12}',s):return s.removeprefix('C').lstrip('0') or '0'
    return ''

def match_planner(rows,contracts):
    by_number=defaultdict(list)
    for c in contracts:
        f=c['fields'];num=contract_id(f.get('Contract number'))
        if num:by_number[num].append(c)
    result=[]
    for row in rows:
        num=contract_id(row.get('contract_number'))
        site=tidy(row['customer'])
        by_contract=by_number.get(num,[]) if num else []
        possibilities=by_contract if by_contract else contracts
        candidates=[]
        for c in possibilities:
            f=c['fields'];target=tidy(f.get('Customer / site'))
            sim=SequenceMatcher(None,site,target).ratio()
            exact=bool(site and site==target)
            date_match=sum(bool(row.get(k) and row[k]==f.get(field)) for k,field in [('start_date','Start date'),('expiry_date','Expiry date')])
            same_contract=bool(num and contract_id(f.get('Contract number'))==num)
            # Contract number can be repeated under umbrella agreements; account/site evidence matters.
            if same_contract or exact or sim >= .83:
                score=(100 if same_contract else 0)+(45 if exact else 35*sim)+date_match*15
                candidates.append((score,sim,exact,date_match,same_contract,c))
        candidates.sort(key=lambda x:x[0],reverse=True)
        top=candidates[0] if candidates else None
        ties=len(candidates)>1 and top and abs(top[0]-candidates[1][0])<10
        if not top:status='Unmatched'
        elif ties:status='Review multiple matches'
        elif top[4] and (top[2] or top[1]>=.72) and top[3]>=1:status='Strong match'
        elif top[2] and top[3]==2 and (not num or top[4]):status='Strong match'
        else:status='Review potential match'
        result.append({**row,'match_status':status,'contract_id':top[5]['id'] if top else None,
                       'matched_customer':top[5]['fields'].get('Customer / site') if top else '',
                       'matched_contract':top[5]['fields'].get('Contract number') if top else '',
                       'similarity':round(top[1],3) if top else 0,
                       'date_matches':top[3] if top else 0,
                       'candidate_count':len(candidates),
                       'alternatives':[{'id':x[5]['id'],'customer':x[5]['fields'].get('Customer / site'),'contract':x[5]['fields'].get('Contract number'),'score':round(x[0])} for x in candidates[:4]]})
    return result

def proposals(con):
    source=json.loads(SOURCE.read_text(encoding='utf-8'))
    contracts=[{'id':r['id'],'fields':json.loads(r['fields'])} for r in con.execute("SELECT id,fields FROM contracts WHERE status='Active'")]
    return match_planner(source,contracts)

def summary(items):return dict(Counter(x['match_status'] for x in items))
