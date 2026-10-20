"""Independent pilot V12: grouped quarterly reports, read-only service-planner review,
and evidence-backed public business contact capture. No live CRM connections.
"""
import csv,io,zipfile,re,json,datetime as dt
from collections import defaultdict
from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .store import connect,now
from .pilot_access import actor
from .service_planner import proposals,summary

router=APIRouter()

def quarter_range(start):
    try:s=dt.date.fromisoformat(start)
    except ValueError:raise HTTPException(400,'Date must be YYYY-MM-DD')
    if s.day!=1 or s.month not in (1,4,7,10):raise HTTPException(400,'Select the first day of a quarter')
    end=dt.date(s.year+1,1,1) if s.month==10 else dt.date(s.year,s.month+3,1)
    return s,end

def quarter_rows(start):
    s,end=quarter_range(start)
    c=connect();rows=c.execute("SELECT fields FROM contracts WHERE status='Active'").fetchall();c.close()
    result=[]
    for r in rows:
        f=json.loads(r['fields']);expiry=str(f.get('Expiry date') or '')[:10]
        try:d=dt.date.fromisoformat(expiry)
        except ValueError:continue
        if s<=d<end:
            result.append({'customer':f.get('Customer / site') or '',
                           'contract':f.get('Contract number') or '',
                           'expiry':expiry,'manager':f.get('Sales manager') or 'Unassigned',
                           'region':f.get('Sales region') or '',
                           'cover':f.get('Contract / warranty type') or '',
                           'invoice_code':f.get('Invoice Code') or '',
                           'action':f.get('Next action') or ''})
    return sorted(result,key=lambda r:(r['manager'],r['expiry'],r['customer']))

@router.get('/api/reports/sales/all-managers')
def sales_managers_report(start:str):
    rows=quarter_rows(start);grouped=defaultdict(list)
    for r in rows:grouped[r['manager']].append(r)
    return {'quarter_start':start,'total':len(rows),'managers':[{'manager':k,'count':len(v)} for k,v in sorted(grouped.items())]}

@router.get('/api/reports/sales/all-managers/download')
def sales_managers_zip(start:str):
    rows=quarter_rows(start);grouped=defaultdict(list)
    for r in rows:grouped[r['manager']].append(r)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for manager,group in sorted(grouped.items()):
            name=re.sub(r'[^A-Za-z0-9_-]+','_',manager).strip('_')[:65] or 'Unassigned'
            f=io.StringIO();w=csv.writer(f)
            w.writerow(['Customer / site','Contract number','Expiry date','Sales manager','Sales region','Cover type','Invoice code','Next action'])
            for r in group:w.writerow([r['customer'],r['contract'],r['expiry'],r['manager'],r['region'],r['cover'],r['invoice_code'],r['action']])
            z.writestr(f'{start[:7]}_{name}_Expiry_Report.csv','\ufeff'+f.getvalue())
        z.writestr('READ_ME.txt',f'Quarter beginning: {start}\nIncluded managers: {len(grouped)}\nTotal agreements: {len(rows)}\n\nSeparate CSV files are ready to open in Excel and send to their sales managers.\nThese reports are NOT automatically emailed.\nValidate sales-manager allocation and agreement status before distribution.\n')
    buf.seek(0)
    return StreamingResponse(buf,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="Pulse_Quarterly_Sales_Reports_{start}.zip"'})

@router.get('/api/contacts/research-queue/download')
def contact_research_queue():
    # This prepares evidence-based research, not invented or scraped personal details.
    import urllib.parse
    c=connect()
    contracts=c.execute("SELECT id,fields FROM contracts WHERE status='Active'").fetchall()
    saved={r['contract_id'] for r in c.execute('SELECT contract_id FROM site_contact_research')}
    c.close()
    buff=io.StringIO();writer=csv.writer(buff)
    writer.writerow(['Contract ID','Customer / site','County','Sales manager','Public website search','Verified contact saved'])
    for row in contracts:
        f=json.loads(row['fields']);name=f.get('Customer / site') or ''
        query=' '.join([name,str(f.get('County') or ''),'official contact telephone email'])
        url='https://www.google.com/search?q='+urllib.parse.quote_plus(query)
        writer.writerow([row['id'],name,f.get('County') or '',f.get('Sales manager') or '',url,'Yes' if row['id'] in saved else 'No'])
    return StreamingResponse(iter(['\ufeff'+buff.getvalue()]),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=Pulse_Site_Contact_Research_Queue.csv'})

@router.get('/api/service-planner')
def service_planner(status:str='All',q:str='',limit:int=75,offset:int=0):
    c=connect();items=proposals(c)
    approved={r['source_row']:dict(r) for r in c.execute('SELECT * FROM service_planner_approvals')};c.close()
    total_summary=summary(items)
    for r in items:
        if r['source_row'] in approved:r['approval']={'applied_at':approved[r['source_row']]['applied_at'],'contract_id':approved[r['source_row']]['contract_id']}
    matches=[r for r in items if (status=='All' or r['match_status']==status) and (not q or q.casefold() in (r['customer']+' '+r['contract_number']+' '+r.get('matched_customer','')).casefold())]
    return {'summary':total_summary,'total':len(matches),'items':matches[max(0,offset):max(0,offset)+max(1,min(limit,150))]}

class ServiceApproval(BaseModel):
    contract_id:int
    expected_revision:int
    confirm:bool=False
    overwrite_existing:bool=False

@router.post('/api/service-planner/{source_row}/approve')
def approve_planner(source_row:int,payload:ServiceApproval):
    if not payload.confirm:raise HTTPException(400,'Explicit review confirmation is required')
    c=connect();c.execute('BEGIN IMMEDIATE')
    item=next((r for r in proposals(c) if r['source_row']==source_row),None)
    if not item:
        c.close();raise HTTPException(404,'Planner record not found')
    if item['match_status']!='Strong match' or item['contract_id']!=payload.contract_id:
        c.close();raise HTTPException(409,'Only a current strong match to this contract can be approved; other matches require manual reconciliation')
    row=c.execute('SELECT * FROM contracts WHERE id=? AND status="Active"',(payload.contract_id,)).fetchone()
    if not row:
        c.close();raise HTTPException(404,'Active contract not found')
    if row['revision']!=payload.expected_revision:
        c.close();raise HTTPException(409,'The contract changed. Reload it and review again')
    date=item['last_service']
    try: d=dt.date.fromisoformat(date)
    except (ValueError,TypeError):
        c.close();raise HTTPException(400,'No valid last-service date to record')
    if d>dt.date.today():
        c.close();raise HTTPException(409,'A future date cannot be recorded as a completed service')
    old=json.loads(row['fields'])
    previous=str(old.get('Last service recorded') or '')
    if previous and previous!=date and not payload.overwrite_existing:
        c.close();raise HTTPException(409,f'The contract already records {previous}. Confirm replacement separately')
    if previous:
        try:
            if dt.date.fromisoformat(previous)>d:
                c.close();raise HTTPException(409,'Cannot replace a more recent service date with an older planner entry')
        except ValueError:pass
    if c.execute('SELECT 1 FROM service_planner_approvals WHERE source_row=?',(source_row,)).fetchone():
        c.close();raise HTTPException(409,'This planner row was already approved')
    old_copy=old.copy();old['Last service recorded']=date
    c.execute('UPDATE contracts SET fields=?,revision=revision+1,dirty=1,updated_at=? WHERE id=?',(json.dumps(old,ensure_ascii=False),now(),payload.contract_id))
    c.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES(?,?,?,?,?,?)',
              (payload.contract_id,actor('Coordinator'),'Verified service planner last-service date (planner row '+str(source_row)+')',json.dumps(old_copy,ensure_ascii=False),json.dumps(old,ensure_ascii=False),now()))
    c.execute('INSERT INTO service_planner_approvals(source_row,contract_id,date_recorded,source_details,applied_at,actor) VALUES(?,?,?,?,?,?)',
             (source_row,payload.contract_id,date,json.dumps(item,ensure_ascii=False),now(),actor('Coordinator')))
    c.commit();c.close()
    return {'ok':True,'contract_id':payload.contract_id,'last_service':date}

class ContactEntry(BaseModel):
    phone:str=''
    email:str=''
    website:str=''
    source_url:str=''
    contact_name:str=''

@router.get('/api/contracts/{cid}/contact')
def contact_record(cid:int):
    c=connect();contact=c.execute('SELECT * FROM site_contact_research WHERE contract_id=?',(cid,)).fetchone();c.close()
    return dict(contact) if contact else {'contract_id':cid,'phone':'','email':'','website':'','source_url':'','contact_name':'','verified_at':None}

@router.post('/api/contracts/{cid}/contact')
def save_contact(cid:int,item:ContactEntry):
    import urllib.parse
    if item.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',item.email):raise HTTPException(400,'Enter a valid email address')
    if any(getattr(item,k) for k in ('email','phone','contact_name')) and not item.source_url.startswith(('https://','http://')):
        raise HTTPException(400,'Provide the official public source URL for contact details')
    c=connect();c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM contracts WHERE id=?',(cid,)).fetchone():
        c.close();raise HTTPException(404,'Contract not found')
    c.execute('''INSERT INTO site_contact_research(contract_id,phone,email,website,source_url,contact_name,verified_at,actor)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(contract_id) DO UPDATE SET
                phone=excluded.phone,email=excluded.email,website=excluded.website,source_url=excluded.source_url,
                contact_name=excluded.contact_name,verified_at=excluded.verified_at,actor=excluded.actor''',
                (cid,item.phone.strip(),item.email.strip(),item.website.strip(),item.source_url.strip(),item.contact_name.strip(),now(),actor('Coordinator')))
    c.commit();c.close();return {'ok':True}
