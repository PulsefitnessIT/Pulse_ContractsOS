"""Pulse Contracts OS | local working prototype.

NOT production SaaS: authentication, cloud hosting, independent security assessment
and live Sage/Sicon interfaces must be completed before real deployment.
"""
from __future__ import annotations
import os,io,json,csv,hashlib,datetime as dt,re,uuid,zipfile,copy,sqlite3,tempfile,shutil,base64,zlib,asyncio
from pathlib import Path
from collections import Counter,defaultdict
from difflib import SequenceMatcher
import fitz
from fastapi import FastAPI,HTTPException,Request,UploadFile,File,Query,Body
from fastapi.responses import FileResponse,Response,StreamingResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .store import DATA,DB,TEMPLATE,connect,init_db,parse_row,stats,now,status_for,type_bucket
from .backups import create_local_backup
from .excel_io import ExcelSource,export_template,REGISTER_SHEETS
from .master_roundtrip import attach_export_id, read_export_id, parse_workbook_records, diff_workbook
from .document_ai import configured as document_ai_configured, read_scanned_pdf, extract_evidence, reference_proposals, DocumentAIError
from .invoice_intelligence import invoice_groups
from .invoice_review import analyse_invoice_document, validate_review
from .import_queue import build_review_queue, queue_csv
from .excel_quality import inspect_excel,remaining_capacity
from .invoice_quality import invoice_quality,invoice_quality_csv
from .pilot_access import PILOT_MODE, SESSION_COOKIE, CSRF_COOKIE, COOKIE_SECURE, configure_users, secret, sign_session, login, revoke_session, actor, pilot_middleware
from .deployment_guards import check_deployment_environment
from .matching import candidate_matches
from .local_ocr import available as local_ocr_available, read_local_scanned_pdf, LocalOCRError
from .v12_features import router as v12_router
from .v13_history import router as v13_router
from .quote_intake import router as smartquote_router
from .quote_workspace import router as quoting_workspace_router
from .quote_drafts import router as quoting_drafts_router
from .quote_catalogue import router as quoting_catalogue_router
from .quote_reconciliation import router as quote_reconciliation_router
from .native_quote_handover import router as native_quote_handover_router
from .quote_pricing import router as quote_pricing_router
from .quote_sage_reference import router as sage_reference_router
from .quote_price_overrides import router as price_overrides_router
from .quote_sage_refresh import router as sage_refresh_router
from .quote_customer_issuance import router as customer_quote_issuance_router
from .quote_commercial_setup import router as quote_commercial_setup_router
from .quote_source_setup import router as quote_source_setup_router
from .source_integrity import router as source_integrity_router
from .action_centre import router as action_centre_router
from .master_sync import router as working_master_sync_router
from .expiry_transfer import router as expiry_transfer_router
from .register_layout import current_layout as checked_register_layout
from .quote_site_lookup import router as source_site_lookup_router
from .contract_setup import router as contract_setup_router
from .sicon_bridge import router as sicon_bridge_router
from .data_readiness import assess_database, missing_amount_review_rows, safe_excel_csv_cell

APP_ROOT=Path(__file__).parent
DEPLOYMENT_PROFILE=check_deployment_environment()
# Fail before creating an empty database if the protected shared pilot has not
# been supplied with its approved private snapshot and Master workbook.
if PILOT_MODE and (not os.path.isfile(DB) or not os.path.isfile(TEMPLATE)):
    raise RuntimeError('Private pilot data missing: stage contracts.sqlite3 and approved_master.xlsx before starting the server')
os.makedirs(DATA,exist_ok=True)
init_db()
if PILOT_MODE:
    secret()  # Refuse to start a pilot without an adequate signing secret.
    configure_users()
if os.environ.get('PULSE_AUTO_BACKUP','1')!='0':
    create_local_backup()
app=FastAPI(title='Pulse Contracts OS',version='1.0.0-pilot')
app.middleware('http')(pilot_middleware)
app.mount('/static',StaticFiles(directory=str(APP_ROOT/'static')),name='static')
HEADERS=ExcelSource(TEMPLATE).records('Maintenance Database')[0]

@app.get('/manifest.webmanifest')
def pwa_manifest():
    return FileResponse(APP_ROOT/'static'/'manifest.webmanifest',media_type='application/manifest+json',headers={'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'})

@app.get('/sw.js')
def pwa_worker():
    return FileResponse(APP_ROOT/'static'/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'})

@app.get('/')
def landing():return FileResponse(APP_ROOT/'static'/'index.html',headers={'Cache-Control':'no-store'})

class PilotLogin(BaseModel):
    username:str
    password:str

@app.get('/pilot/login')
def pilot_login_page():
    if not PILOT_MODE:raise HTTPException(404,'Pilot login is disabled')
    return FileResponse(APP_ROOT/'static'/'pilot-login.html')

@app.post('/api/pilot/login')
def pilot_login(payload:PilotLogin,request:Request):
    if not PILOT_MODE:raise HTTPException(404,'Pilot login is disabled')
    result=login(payload.username,payload.password,request)
    ticket,body=sign_session(result)
    resp=JSONResponse({'ok':True,'user':result['username'],'role':result['role']})
    resp.set_cookie(SESSION_COOKIE,ticket,max_age=8*3600,httponly=True,secure=COOKIE_SECURE,samesite='strict',path='/')
    resp.set_cookie(CSRF_COOKIE,body['csrf'],max_age=8*3600,httponly=False,secure=COOKIE_SECURE,samesite='strict',path='/')
    return resp

@app.get('/api/pilot/me')
def pilot_me(request:Request):
    if not PILOT_MODE:return {'pilot':False}
    from .pilot_access import read_session
    session=read_session(request.cookies.get(SESSION_COOKIE))
    return {'pilot':True,'user':session.get('sub'),'role':session.get('role')}

@app.post('/api/pilot/logout')
def pilot_logout(request:Request):
    if PILOT_MODE:
        # A copied cookie must not remain valid after explicit sign-out.
        revoke_session(request.cookies.get(SESSION_COOKIE))
    resp=JSONResponse({'ok':True})
    resp.delete_cookie(SESSION_COOKIE,path='/')
    resp.delete_cookie(CSRF_COOKIE,path='/')
    resp.headers['Cache-Control']='no-store'
    return resp


app.include_router(v12_router)
app.include_router(v13_router)
app.include_router(smartquote_router)
app.include_router(quoting_workspace_router)
app.include_router(quoting_drafts_router)
app.include_router(quoting_catalogue_router)
app.include_router(quote_reconciliation_router)
app.include_router(native_quote_handover_router)
app.include_router(quote_pricing_router)
app.include_router(sage_reference_router)
app.include_router(price_overrides_router)
app.include_router(sage_refresh_router)
app.include_router(customer_quote_issuance_router)
app.include_router(quote_commercial_setup_router)
app.include_router(quote_source_setup_router)
app.include_router(source_integrity_router)
app.include_router(action_centre_router)
app.include_router(working_master_sync_router)
app.include_router(expiry_transfer_router)
app.include_router(source_site_lookup_router)
app.include_router(contract_setup_router)
app.include_router(sicon_bridge_router)

@app.get('/api/meta')
def meta():return {'stats':stats(),'headers':HEADERS,'version':'1.0.0-pilot','release':'V13 Development','environment':'Independent protected pilot' if PILOT_MODE else 'Local demonstration','document_ai_configured':document_ai_configured(),'local_ocr_available':local_ocr_available(),'ocr_mode':os.environ.get('PULSE_OCR_MODE','auto').lower(),'data_readiness':assess_database(DB,TEMPLATE)}

@app.get('/api/pilot/data-readiness')
def pilot_data_readiness():
    # Aggregated status only; no contract names, prices or source documents returned.
    return assess_database(DB,TEMPLATE)

@app.get('/api/pilot/data-quality/missing-amounts.csv')
def missing_amounts_csv():
    # Source-linked review queue; never infer amounts from invoices or warranties.
    fieldnames = ('Contract ID','Customer / site','Contract number',
                  'Contract / warranty type','Sales manager','Recorded amount','Review reason')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fieldnames)
    for row in missing_amount_review_rows(DB):
        writer.writerow([safe_excel_csv_cell(row.get(name,'')) for name in fieldnames])
    return Response(content=chr(0xfeff)+output.getvalue(),media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':'attachment; filename="Pulse_Contracts_Missing_Amounts_Review.csv"',
                 'Cache-Control':'no-store'})


@app.get('/api/contracts')
def contracts(q:str='',status:str='Active',region:str='',manager:str='',bucket:str='',sheet:str='',sort:str='Customer / site',direction:str='asc',page:int=1,limit:int=40):
    if sheet and sheet not in ('Maintenance Database','MOD','Expired'):
        raise HTTPException(422,'Unknown contract register')
    if limit>150:limit=150
    con=connect()
    if status=='All':rows=con.execute('SELECT * FROM contracts').fetchall()
    else:rows=con.execute('SELECT * FROM contracts WHERE status=?',(status,)).fetchall()
    con.close()
    values=[]
    for row in rows:
        if sheet and row['source_sheet']!=sheet:continue
        f=json.loads(row['fields'])
        if q and q.lower() not in (' '.join(str(f.get(k,'')) for k in ['Customer / site','Contract number','Invoice Code','Invoice account','Site account','Site notes','Contract coordinator','Record ID'])).lower():continue
        if region and f.get('Sales region')!=region:continue
        if manager and f.get('Sales manager')!=manager:continue
        if bucket and type_bucket(f.get('Contract / warranty type'))!=bucket:continue
        values.append((row,f))
    def val(x):
        t=str(x[1].get(sort,'') or '')
        return t.lower()
    values.sort(key=val,reverse=direction=='desc')
    total=len(values);start=(page-1)*limit
    return {'total':total,'page':page,'limit':limit,'items':[parse_row(x[0],True) for x in values[start:start+limit]]}

@app.get('/api/contracts/{cid}')
def get_contract(cid:int):
    con=connect();r=con.execute('SELECT * FROM contracts WHERE id=?',(cid,)).fetchone();con.close()
    if not r:raise HTTPException(404,'Contract not found')
    result=parse_row(r)
    result['fields']['Renewal status']=status_for(str(result['fields'].get('Expiry date') or '')) if r['status']=='Active' else 'Historical / archived'
    return result

# ---- Stock-code catalogue and equipment linked to customer agreements ----
# Product catalogue attributes are reference data, not proof of agreed coverage.
@app.get('/api/catalogue')
def list_catalogue(q:str='', limit:int=60, page:int=1):
    limit=max(1,min(limit,100)); page=max(1,page)
    con=connect()
    if q.strip():
        term='%'+q.strip().lower()+'%'
        where='WHERE lower(sku) LIKE ? OR lower(model) LIKE ? OR lower(name) LIKE ? OR lower(description) LIKE ? OR lower(category) LIKE ?'
        args=(term,)*5
    else:where='';args=()
    total=con.execute(f'SELECT COUNT(*) FROM catalogue {where}',args).fetchone()[0]
    rows=[dict(r) for r in con.execute(f'SELECT * FROM catalogue {where} ORDER BY sku LIMIT ? OFFSET ?',args+(limit,(page-1)*limit))]
    con.close()
    return {'total':total,'items':rows,'page':page,'limit':limit}

@app.get('/api/contracts/{cid}/equipment')
def contract_equipment(cid:int):
    con=connect()
    if not con.execute('SELECT 1 FROM contracts WHERE id=?',(cid,)).fetchone():
        con.close();raise HTTPException(404,'Contract not found')
    rows=[dict(r) for r in con.execute('''SELECT e.*,c.model,c.name,c.description,c.category,c.frame,
      c.upholstery,c.console,c.software,c.status AS catalogue_status FROM equipment e
      LEFT JOIN catalogue c ON c.sku=e.sku WHERE e.contract_id=? ORDER BY e.id''',(cid,))]
    con.close()
    return {'items':rows,'count':len(rows)}

class EquipmentCreate(BaseModel):
    sku:str
    serial_number:str=''
    quantity:int=1
    installation_date:str=''
    warranty_expiry:str=''
    invoice_reference:str=''
    notes:str=''

@app.post('/api/contracts/{cid}/equipment')
def attach_equipment(cid:int,payload:EquipmentCreate):
    con=connect()
    if not con.execute('SELECT 1 FROM contracts WHERE id=?',(cid,)).fetchone():
        con.close();raise HTTPException(404,'Contract not found')
    sku=payload.sku.strip().upper()
    if not con.execute('SELECT 1 FROM catalogue WHERE sku=?',(sku,)).fetchone():
        con.close();raise HTTPException(400,'Choose a valid stock item code from the catalogue')
    if payload.quantity<1 or payload.quantity>10000:
        con.close();raise HTTPException(400,'Quantity must be between 1 and 10,000')
    for label,value in [('Installation date',payload.installation_date),('Warranty expiry',payload.warranty_expiry)]:
        if value:
            try:dt.date.fromisoformat(value)
            except ValueError:
                con.close();raise HTTPException(400,label+' must be a valid YYYY-MM-DD date')
    # Duplicate serials against this agreement need review, not accidental re-import.
    if payload.serial_number.strip() and con.execute('SELECT 1 FROM equipment WHERE contract_id=? AND upper(serial_number)=?',(cid,payload.serial_number.strip().upper())).fetchone():
        con.close();raise HTTPException(409,'This serial number is already linked to this contract')
    cur=con.execute('''INSERT INTO equipment
      (contract_id,sku,serial_number,quantity,installation_date,warranty_expiry,invoice_reference,notes,created_at)
      VALUES (?,?,?,?,?,?,?,?,?)''',(cid,sku,payload.serial_number.strip(),payload.quantity,payload.installation_date,payload.warranty_expiry,payload.invoice_reference.strip(),payload.notes.strip(),now()))
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
       (cid,actor('Demo coordinator'),'Linked equipment',None,json.dumps(payload.model_dump(),ensure_ascii=False),now()))
    con.commit();con.close();return {'ok':True,'id':cur.lastrowid}

@app.delete('/api/contracts/{cid}/equipment/{eid}')
def unlink_equipment(cid:int,eid:int):
    con=connect();item=con.execute('SELECT * FROM equipment WHERE contract_id=? AND id=?',(cid,eid)).fetchone()
    if not item:con.close();raise HTTPException(404,'Equipment link not found')
    con.execute('DELETE FROM equipment WHERE id=?',(eid,))
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
        (cid,actor('Demo coordinator'),'Unlinked equipment',json.dumps(dict(item),ensure_ascii=False),None,now()))
    con.commit();con.close();return {'ok':True}

@app.get('/api/contracts/{cid}/equipment/field-suggestions')
def equipment_field_suggestions(cid:int):
    con=connect();existing=con.execute('SELECT fields FROM contracts WHERE id=?',(cid,)).fetchone()
    if not existing:con.close();raise HTTPException(404,'Contract not found')
    fields=json.loads(existing[0]);rows=con.execute('''SELECT c.console,c.software,c.frame,c.upholstery
        FROM equipment e JOIN catalogue c ON e.sku=c.sku WHERE e.contract_id=?''',(cid,)).fetchall();con.close()
    def combined(key):
        items=sorted({str(r[key]).strip() for r in rows if r[key] and str(r[key]).strip()})
        return ' / '.join(items)[:250]
    proposals={}
    if not fields.get('Consoles / software'):
        v=' / '.join(t for t in [combined('console'),combined('software')] if t)
        if v:proposals['Consoles / software']=v[:250]
    if not fields.get('Frame / upholstery finish'):
        v=' / '.join(t for t in [combined('frame'),combined('upholstery')] if t)
        if v:proposals['Frame / upholstery finish']=v[:250]
    return {'suggestions':proposals,'equipment_count':len(rows),
      'note':'Reference product specifications only. No contract terms, amounts or cover are inferred; suggestions require staff approval.'}

@app.get('/api/export/equipment')
def equipment_export():
    import csv
    con=connect();rows=con.execute('''SELECT e.id,e.sku,e.serial_number,e.quantity,e.installation_date,e.warranty_expiry,e.invoice_reference,e.notes,
      c.model,c.name,c.console,c.software,c.frame,c.upholstery,t.fields
      FROM equipment e JOIN catalogue c ON c.sku=e.sku JOIN contracts t ON t.id=e.contract_id ORDER BY e.id''').fetchall();con.close()
    output=io.StringIO();w=csv.writer(output)
    w.writerow(['Customer / site','Contract number','Stock item code','Model','Equipment description','Serial number','Quantity','Installation date','Equipment warranty expiry','Invoice reference','Console','Software','Frame','Upholstery','Notes'])
    for r in rows:
        contract=json.loads(r['fields'])
        w.writerow([contract.get('Customer / site',''),contract.get('Contract number',''),r['sku'],r['model'],r['name'],r['serial_number'],r['quantity'],r['installation_date'],r['warranty_expiry'],r['invoice_reference'],r['console'],r['software'],r['frame'],r['upholstery'],r['notes']])
    return Response(output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=Pulse_Contract_Equipment_Register.csv'})

@app.get('/api/contracts/{cid}/changes')
def changes(cid:int):
    con=connect();res=[dict(x) for x in con.execute('SELECT actor, action, at, before_data, after_data FROM changes WHERE contract_id=? ORDER BY id DESC LIMIT 30',(cid,))];con.close()
    return res

class ContractUpdate(BaseModel):
    fields:dict
    source_register:str='Maintenance Database'
    actor:str='Demo coordinator'
    expected_revision:int|None=None

class ArchiveRequest(BaseModel):
    expected_revision:int
    reason:str=''
    actor:str='Coordinator'

class RenewalRequest(BaseModel):
    expected_revision:int
    start_date:str
    expiry_date:str
    amount:str|None=None
    actor:str='Coordinator'


def concurrency_check(row,expected,con=None):
    if expected is None:
        if con: con.rollback();con.close()
        raise HTTPException(428,'Refresh this record before saving. A record version is required.')
    if expected!=row['revision']:
        if con: con.rollback();con.close()
        raise HTTPException(409,'This contract was changed by someone else. Close it, reopen it and review the latest values before saving.')


@app.patch('/api/contracts/{cid}')
def update_contract(cid:int,payload:ContractUpdate):
    con=connect()
    con.execute('BEGIN IMMEDIATE')
    r=con.execute('SELECT * FROM contracts WHERE id=?',(cid,)).fetchone()
    if not r:con.close();raise HTTPException(404,'Contract not found')
    concurrency_check(r,payload.expected_revision,con)
    disallowed=set(payload.fields)-set(HEADERS)
    if disallowed:con.close();raise HTTPException(400,'Unknown columns: '+','.join(disallowed))
    old=json.loads(r['fields']);new=old.copy();new.update(payload.fields)
    if not str(new.get('Customer / site','')).strip():con.close();raise HTTPException(400,'Customer/site is required')
    if new.get('Expiry date') and new.get('Start date') and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(new['Expiry date'])) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(new['Start date'])) and new['Start date']>new['Expiry date']:
        con.close();raise HTTPException(400,'Expiry date cannot be before the start date')
    new['Renewal status']=status_for(str(new.get('Expiry date') or '')) if r['status']=='Active' else 'Historical / archived'
    if new!=old:
        con.execute('UPDATE contracts SET fields=?, dirty=1, revision=revision+1, updated_at=? WHERE id=?',(json.dumps(new,ensure_ascii=False),now(),cid))
        con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',(cid,actor(payload.actor),'Updated contract',json.dumps(old,ensure_ascii=False),json.dumps(payload.fields,ensure_ascii=False),now()))
        con.commit()
    con.close();return {'ok':True,'updated':new!=old}

@app.post('/api/contracts')
def create_contract(payload:ContractUpdate):
    if payload.source_register not in ('Maintenance Database','MOD'):
        raise HTTPException(422,'Choose a valid source register')
    if payload.source_register=='MOD':
        from .data_readiness import CURRENT_WORKSHEETS,workbook_check
        if workbook_check(TEMPLATE).get('sheet_names')!=CURRENT_WORKSHEETS:
            raise HTTPException(409,'The approved private Master has no MOD worksheet')
    f={k:payload.fields.get(k,'') for k in HEADERS}
    if not str(f.get('Customer / site','')).strip():raise HTTPException(400,'Customer / site is required')
    con=connect();con.execute('BEGIN IMMEDIATE')
    row=int(con.execute("SELECT coalesce(max(source_row),1) FROM contracts WHERE source_sheet=?",
        (payload.source_register,)).fetchone()[0])+1
    if row>=1_048_576:
        con.close();raise HTTPException(409,'The worksheet has reached Excel row capacity')
    key='NEW-'+uuid.uuid4().hex[:8].upper();f['Record ID']=key;f['Renewal status']=status_for(str(f.get('Expiry date') or ''))
    cur=con.execute('INSERT INTO contracts(row_key,status,source_sheet,source_row,fields,fill,dirty,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
        (key,'Active',payload.source_register,row,json.dumps(f,ensure_ascii=False),'',1,now(),now()))
    cid=cur.lastrowid
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',(cid,actor(payload.actor),'Created contract',None,json.dumps(f,ensure_ascii=False),now()))
    con.commit();con.close();return {'id':cid,'row_key':key}

@app.post('/api/contracts/{cid}/archive')
def archive(cid:int,payload:ArchiveRequest):
    # The maintenance, MOD and Expired column positions must match before
    # an archived row can be represented safely in a later Excel export.
    layout=checked_register_layout(TEMPLATE)
    con=connect();con.execute('BEGIN IMMEDIATE')
    r=con.execute('SELECT * FROM contracts WHERE id=?',(cid,)).fetchone()
    if not r or r['status']!='Active':
        con.close();raise HTTPException(404,'Active contract not found')
    concurrency_check(r,payload.expected_revision,con)
    row=max(
        int(con.execute("SELECT coalesce(max(source_row),1) FROM contracts WHERE source_sheet='Expired'").fetchone()[0]),
        int(layout['template_last_expired_row'])
    )+1
    if row>=1_048_576:
        con.close();raise HTTPException(409,'The Expired worksheet has reached Excel row capacity')
    old=json.loads(r['fields']);f=old.copy();f['Renewal status']='Historical / archived'
    con.execute('UPDATE contracts SET status="Expired",old_sheet=?,old_row=?,source_sheet="Expired",source_row=?,fields=?,revision=revision+1,dirty=1,updated_at=? WHERE id=?',
        (r['source_sheet'],r['source_row'],row,json.dumps(f,ensure_ascii=False),now(),cid))
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
        (cid,actor(payload.actor),'Archived contract',json.dumps(old,ensure_ascii=False),json.dumps({'reason':payload.reason,'record':f},ensure_ascii=False),now()))
    con.commit();con.close();return {'ok':True,'status':'Expired'}

@app.post('/api/contracts/{cid}/renew')
def renew_contract(cid:int,payload:RenewalRequest):
    try:
        start=dt.date.fromisoformat(payload.start_date);end=dt.date.fromisoformat(payload.expiry_date)
    except ValueError:raise HTTPException(400,'Enter valid renewal dates')
    if end<start:raise HTTPException(400,'Renewal end date is before start date')
    con=connect();con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT * FROM contracts WHERE id=?',(cid,)).fetchone()
    if not row or row['status']!='Active':
        con.close();raise HTTPException(404,'Active contract not found')
    concurrency_check(row,payload.expected_revision,con)
    old=json.loads(row['fields']);new=old.copy();new['Start date']=payload.start_date;new['Expiry date']=payload.expiry_date
    if payload.amount is not None:
        try:float(payload.amount.replace(',','').replace('£',''))
        except ValueError:con.close();raise HTTPException(400,'Contract amount must be a number')
        new['Contract amount (£)']=payload.amount
    new['Renewal status']=status_for(payload.expiry_date)
    con.execute('INSERT INTO renewal_history(contract_id,old_start,old_expiry,old_amount,new_start,new_expiry,new_amount,effective_at,actor) VALUES (?,?,?,?,?,?,?,?,?)',
        (cid,old.get('Start date'),old.get('Expiry date'),str(old.get('Contract amount (£)','')),payload.start_date,payload.expiry_date,str(new.get('Contract amount (£)','')),now(),actor(payload.actor)))
    con.execute('UPDATE contracts SET fields=?,dirty=1,revision=revision+1,updated_at=? WHERE id=?',(json.dumps(new,ensure_ascii=False),now(),cid))
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
        (cid,actor(payload.actor),'Renewed contract',json.dumps(old,ensure_ascii=False),json.dumps(new,ensure_ascii=False),now()))
    con.commit();con.close();return {'ok':True,'contract_id':cid,'revision':row['revision']+1}

@app.get('/api/contracts/{cid}/renewals')
def renewal_history(cid:int):
    con=connect();result=[dict(r) for r in con.execute('SELECT * FROM renewal_history WHERE contract_id=? ORDER BY id DESC',(cid,))];con.close();return result

@app.get('/api/ledger/{kind}')
def ledger(kind:str,q:str='',year:int=0,month:str='',week:str='',page:int=1,limit:int=60):
    lookup={'weekly':'Weekly Values','invoices':'Invoices','quotes':'Quotes'}
    if kind not in lookup:raise HTTPException(404,'Unknown ledger')
    con=connect();rows=con.execute('SELECT * FROM ledger WHERE kind=?',(lookup[kind],)).fetchall();con.close()
    items=[]
    for row in rows:
        f=json.loads(row['fields'])
        if q and q.lower() not in ' '.join(str(x) for x in f.values()).lower():continue
        d=str(f.get({'weekly':'Week ending (Friday)','invoices':'Invoice month','quotes':'Prepared date'}[kind]) or '')
        if year and not d.startswith(str(year)):continue
        if month and not d.startswith(month):continue
        if week:
            try:
                y,w = [int(x) for x in week.split('-W')]
                monday=dt.date.fromisocalendar(y,w,1);sunday=monday+dt.timedelta(days=6)
                date=dt.date.fromisoformat(d[:10])
            except (ValueError,TypeError):raise HTTPException(400,'Week must use YYYY-Www')
            if not monday <= date <= sunday:continue
        items.append({'id':row['id'],'fields':f})
    total=len(items); start=(page-1)*limit
    total_value = round(sum(float(x['fields'].get('Value recorded (£)') or 0) for x in items),2) if kind=='weekly' else None
    return {'total':total,'items':items[start:start+limit], 'total_value':total_value}


LEDGER_NAMES={'weekly':'Weekly Values','invoices':'Invoices','quotes':'Quotes'}
LEDGER_FIELDS={name:ExcelSource(TEMPLATE).records(name)[0] for name in LEDGER_NAMES.values()}
LEDGER_LIMITS={'Weekly Values':1685,'Invoices':732,'Quotes':1506}

@app.get('/api/ledger/{kind}/{lid}')
def get_ledger_item(kind:str,lid:int):
    if kind not in LEDGER_NAMES:raise HTTPException(404,'Unknown register')
    con=connect();row=con.execute('SELECT * FROM ledger WHERE id=? AND kind=?',(lid,LEDGER_NAMES[kind])).fetchone();con.close()
    if not row:raise HTTPException(404,'Entry not found')
    return {'id':row['id'],'fields':json.loads(row['fields']),'revision':row['revision']}

@app.post('/api/ledger/{kind}')
def create_ledger(kind:str,payload:ContractUpdate):
    if kind not in ('weekly','invoices'):raise HTTPException(400,'New entries are supported for weekly values and invoices')
    register=LEDGER_NAMES[kind]
    headers=LEDGER_FIELDS[register]
    fields={key:payload.fields.get(key,'') for key in headers}
    required='Week ending (Friday)' if kind=='weekly' else 'Invoice month'
    if not fields.get(required):raise HTTPException(400,f'{required} is required')
    try:
        number=float(fields.get('Value recorded (£)' if kind=='weekly' else 'Amount ex VAT (£)') or '')
        if number<0 and kind=='weekly':raise ValueError()
    except (ValueError,TypeError):raise HTTPException(400,'Enter a valid numerical amount')
    con=connect();con.execute('BEGIN IMMEDIATE')
    row=int(con.execute('SELECT COALESCE(MAX(source_row),1) FROM ledger WHERE kind=?',(register,)).fetchone()[0])+1
    if row>LEDGER_LIMITS[register]:
        con.close();raise HTTPException(409,'Excel template is full for this register; expand the approved template first.')
    cur=con.execute('INSERT INTO ledger(kind,source_row,fields,dirty) VALUES (?,?,?,1)',(register,row,json.dumps(fields,ensure_ascii=False)))
    con.commit();con.close();return {'id':cur.lastrowid}

@app.patch('/api/ledger/{kind}/{lid}')
def edit_ledger(kind:str,lid:int,payload:ContractUpdate):
    if kind not in ('weekly','invoices'):raise HTTPException(400,'Register cannot be edited here')
    register=LEDGER_NAMES[kind]
    if set(payload.fields)-set(LEDGER_FIELDS[register]):raise HTTPException(400,'Unknown register column')
    con=connect();con.execute('BEGIN IMMEDIATE');old=con.execute('SELECT * FROM ledger WHERE id=? AND kind=?',(lid,register)).fetchone()
    if not old:
        con.close();raise HTTPException(404,'Entry not found')
    concurrency_check(old,payload.expected_revision,con)
    fields=json.loads(old['fields']);fields.update(payload.fields)
    amount_field='Value recorded (£)' if kind=='weekly' else 'Amount ex VAT (£)'
    if fields.get(amount_field):
        try:float(fields[amount_field])
        except (ValueError,TypeError):raise HTTPException(400,'Amount must be numerical')
    con.execute('UPDATE ledger SET fields=?,dirty=1,revision=revision+1 WHERE id=?',(json.dumps(fields,ensure_ascii=False),lid))
    con.commit();con.close();return {'ok':True}

@app.get('/api/reports/sales')
def sales_report(start:str,manager:str='All'):
    try:
        s=dt.date.fromisoformat(start);end=dt.date(s.year+1,1,1) if s.month>=10 else dt.date(s.year,s.month+3,1)
    except Exception:raise HTTPException(400,'Start date must be YYYY-MM-DD; use the first day of a quarter')
    con=connect();rows=con.execute("SELECT * FROM contracts WHERE status='Active'").fetchall();con.close()
    out=[]
    for r in rows:
        f=json.loads(r['fields']);expiry=str(f.get('Expiry date') or '')[:10]
        if not expiry:continue
        try:d=dt.date.fromisoformat(expiry)
        except ValueError:continue
        if s<=d<end and (manager=='All' or manager==f.get('Sales manager')):
            out.append({'id':r['id'],'customer':f.get('Customer / site'),'contract':f.get('Contract number'),'expiry':expiry,'manager':f.get('Sales manager'),'region':f.get('Sales region'),'cover':f.get('Contract / warranty type')})
    out.sort(key=lambda x:x['expiry']);return {'items':out,'count':len(out),'quarter_start':start,'manager':manager}

@app.get('/api/reports/monthly')
def monthly_report(month:str):
    con=connect();rows=con.execute("SELECT fields FROM ledger WHERE kind='Invoices'").fetchall();con.close()
    preview=[];sent=[]
    for r in rows:
        f=json.loads(r['fields'])
        if str(f.get('Invoice month') or '')[:7]!=month:continue
        is_sent=str(f.get('Invoice status','')).strip().lower() in ('sent','confirmed sent','issued')
        try:a=float(f.get('Amount ex VAT (£)') or 0)
        except ValueError:a=0
        (sent if is_sent else preview).append((f,a))
    return {'month':month,'preview_count':len(preview),'preview_total':round(sum(a for _,a in preview),2),'sent_count':len(sent),'sent_total':round(sum(a for _,a in sent),2)}

def encode_snapshot(snapshot):
    text=json.dumps(snapshot,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return 'z:'+base64.b64encode(zlib.compress(text,level=7)).decode('ascii')

def decode_snapshot(text):
    if text.startswith('z:'):
        return json.loads(zlib.decompress(base64.b64decode(text[2:])))
    return json.loads(text)  # backward compatibility for earlier export snapshots

@app.get('/api/export/excel')
def export_excel():
    # Keep a consistent read snapshot of the exact data used to render Excel.
    con=connect();con.execute('BEGIN')
    rows=con.execute('SELECT * FROM contracts').fetchall()
    ledger_rows=con.execute('SELECT * FROM ledger').fetchall()
    updates=defaultdict(list)
    baseline={'contracts':{},'ledger':{},'created_at':now(),'template':'approved source Master'}
    for r in rows:
        f=json.loads(r['fields'])
        baseline['contracts'][r['row_key']]={'fields':f,'sheet':r['source_sheet'],'revision':r['revision']}
        if r['dirty']:
            updates[r['source_sheet']].append({'row':r['source_row'],'changes':f,'style_origin':{'sheet':r['old_sheet'],'row':r['old_row']} if r['old_sheet'] and r['old_row'] else None})
            if r['old_sheet'] and r['old_row']:
                updates[r['old_sheet']].append({'row':r['old_row'],'changes':{k:'' for k in HEADERS}})
    for lr in ledger_rows:
        lf=json.loads(lr['fields'])
        stable=str(lf.get('Quote ID' if lr['kind']=='Quotes' else 'Original source') or '').strip()
        if stable:
            baseline['ledger'][lr['kind']+'::'+stable]={'fields':lf,'revision':lr['revision']}
        if lr['dirty']:
            updates[lr['kind']].append({'row':lr['source_row'],'changes':lf})
    con.commit();con.close()
    folder=Path(DATA)/'generated';folder.mkdir(exist_ok=True)
    export_id=str(uuid.uuid4())
    file=folder/('Pulse_Maintenance_Master_'+export_id+'.xlsx')
    if updates:export_template(TEMPLATE,updates,str(file))
    else:shutil.copy2(TEMPLATE,file)
    attach_export_id(str(file),export_id)
    quality=inspect_excel(str(file))
    if not quality['ok']:
        file.unlink(missing_ok=True)
        raise HTTPException(500,'Excel export quality check failed: '+'; '.join(quality['failures'][:3]))
    expected_active=sum(1 for r in rows if r['status']=='Active')
    expected_expired=sum(1 for r in rows if r['status']=='Expired')
    if quality['stats']['active_rows']!=expected_active or quality['stats']['expired_rows']!=expected_expired:
        file.unlink(missing_ok=True)
        raise HTTPException(500,'Excel export row count differs from current contracts. No workbook was issued.')
    sha=hashlib.sha256(file.read_bytes()).hexdigest()
    con=connect()
    con.execute('INSERT INTO export_snapshots(export_id,exported_at,baseline_json,file_sha256) VALUES (?,?,?,?)',
       (export_id,now(),encode_snapshot(baseline),sha))
    con.commit();con.close()
    return FileResponse(file,filename='Pulse_Fitness_Maintenance_Master.xlsx',media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'X-Pulse-Export-ID':export_id})

@app.get('/api/quality/invoice-recognition')
def invoice_recognition_quality():
    con=connect()
    try:return invoice_quality(con)
    finally:con.close()

@app.get('/api/quality/invoice-recognition.csv')
def invoice_quality_spreadsheet():
    # Existing visually verified data only; no new review form is required.
    con=connect()
    try:content,count=invoice_quality_csv(con)
    finally:con.close()
    return Response(content,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':'attachment; filename="Pulse_Invoice_Recognition_Quality.csv"',
        'X-Pulse-Verified-Invoices':str(count)})

@app.get('/api/export/preflight')
def export_preflight():
    con=connect()
    capacity=remaining_capacity(con)
    con.close()
    return {'template':inspect_excel(TEMPLATE),'capacity':capacity,
        'message':'Excel tables, filters and matching formats will expand automatically when new entries exceed the approved template boundaries. The original eight-sheet layout remains unchanged.'}

@app.get('/api/export/history')
def export_history():
    con=connect();out=[dict(x) for x in con.execute('SELECT export_id,exported_at FROM export_snapshots ORDER BY exported_at DESC LIMIT 30')];con.close()
    return out

@app.post('/api/master/reimport/preview')
async def preview_master_reimport(file:UploadFile=File(...)):
    content=await file.read()
    if len(content)>30_000_000:raise HTTPException(413,'Maximum workbook size is 30 MB')
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(400,'Upload the exported .xlsx Maintenance Master')
    try:export_id=read_export_id(content)
    except (zipfile.BadZipFile,KeyError,ValueError):raise HTTPException(400,'The file is not a valid Maintenance Master Excel export.')
    if not export_id:raise HTTPException(409,'Export tracking is missing. Download a fresh Master from the platform, edit it and upload that version. No changes were applied.')
    con=connect();snapshot=con.execute('SELECT baseline_json FROM export_snapshots WHERE export_id=?',(export_id,)).fetchone()
    if not snapshot:con.close();raise HTTPException(409,'This workbook was not exported by this platform database. No changes were applied.')
    try:incoming=parse_workbook_records(content)
    except (ValueError,KeyError,zipfile.BadZipFile) as e:con.close();raise HTTPException(400,str(e))
    records=[dict(r) for r in con.execute('SELECT id,row_key,source_sheet,fields,revision FROM contracts')]
    current=[{'id':r['id'],'row_key':r['row_key'],'fields':json.loads(r['fields']),'revision':r['revision'],'source_sheet':r['source_sheet']} for r in records]
    baseline=decode_snapshot(snapshot['baseline_json'])
    ledger_live={}
    for r in con.execute('SELECT id,kind,fields,revision FROM ledger'):
        lf=json.loads(r['fields']);stable=str(lf.get('Quote ID' if r['kind']=='Quotes' else 'Original source') or '').strip()
        if stable:ledger_live[r['kind']+'::'+stable]={'id':r['id'],'fields':lf,'revision':r['revision']}
    baseline['live_ledger']=ledger_live  # transient; never written into an export snapshot
    diff=diff_workbook(baseline,current,incoming)
    review_id=str(uuid.uuid4())
    # Pending review is held for 24 hours. Importing again refreshes and rechecks the live database.
    expires=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24)).isoformat(timespec='seconds')
    con.execute('INSERT INTO import_reviews(review_id,export_id,created_at,expires_at,rows_json) VALUES (?,?,?,?,?)',
       (review_id,export_id,now(),expires,json.dumps(diff,ensure_ascii=False)))
    con.commit();con.close()
    return {'review_id':review_id,'export_id':export_id,**diff}

class ReimportApproval(BaseModel):
    approved_items:list[int]
    accepted_conflicts:list[str]=[]
    actor:str='Coordinator'

@app.post('/api/master/reimport/{review_id}/apply')
def apply_master_reimport(review_id:str,payload:ReimportApproval):
    con=connect();con.execute('BEGIN IMMEDIATE')
    review=con.execute('SELECT * FROM import_reviews WHERE review_id=?',(review_id,)).fetchone()
    if not review:con.close();raise HTTPException(404,'Review not found')
    if review['status']!='Pending':con.close();raise HTTPException(409,'This review has already been processed')
    if dt.datetime.fromisoformat(review['expires_at'])<dt.datetime.now(dt.timezone.utc):
        con.close();raise HTTPException(409,'This review has expired. Upload the workbook again.')
    data=json.loads(review['rows_json']);items=data['items']
    chosen=set(payload.approved_items)
    if any(not isinstance(i,int) or i<0 or i>=len(items) for i in chosen):
        con.close();raise HTTPException(400,'Invalid selection of changes')
    if len(chosen)>250:
        con.close();raise HTTPException(400,'Apply at most 250 reviewed records per batch')
    conflicts=set(payload.accepted_conflicts)
    results=[]
    for i in sorted(chosen):
        entry=items[i]
        if entry['action']=='update_ledger':
            row=con.execute('SELECT * FROM ledger WHERE id=?',(entry['ledger_id'],)).fetchone()
            if not row or row['revision']!=entry['revision']:
                con.close();raise HTTPException(409,f'{entry["key"]} changed since preview; compare again.')
            changed={}
            for field in entry['changes']:
                ck=f'{i}:{field["field"]}'
                if field['conflict'] and ck not in conflicts:
                    con.close();raise HTTPException(409,'Explicitly confirm each conflicting financial or historical field')
                changed[field['field']]=field['incoming']
            old=json.loads(row['fields']);updated={**old,**changed}
            # Financial ledger values must remain valid amounts before applying.
            amount_field='Value recorded (£)' if row['kind']=='Weekly Values' else 'Amount ex VAT (£)' if row['kind']=='Invoices' else None
            if amount_field and updated.get(amount_field) not in (None,''):
                try:float(updated[amount_field])
                except (ValueError,TypeError):con.close();raise HTTPException(400,'Financial amount must be numeric')
            con.execute('UPDATE ledger SET fields=?,dirty=1,revision=revision+1 WHERE id=?',
                (json.dumps(updated,ensure_ascii=False),row['id']))
            results.append({'ledger_id':row['id'],'changed_fields':list(changed)})
            continue
        if entry['action']=='new':
            if entry.get('possible_duplicate'):
                con.close();raise HTTPException(409,'Possible duplicate customer and contract number. Add or update the record through the Contracts screen instead.')
            new={f['field']:f['incoming'] for f in entry['changes'] if f['field'] in HEADERS}
            if not str(new.get('Customer / site','')).strip():
                con.close();raise HTTPException(400,'A new contract must have a customer/site name')
            sheet=entry['sheet']
            if sheet not in ('Maintenance Database','Expired'):
                con.close();raise HTTPException(400,'New records can only be placed in the contract registers')
            number=str(new.get('Contract number') or '').strip()
            if number and number!='?':
                for old in con.execute('SELECT fields FROM contracts'):
                    f=json.loads(old['fields'])
                    if str(f.get('Customer / site','')).strip().casefold()==str(new['Customer / site']).strip().casefold() and str(f.get('Contract number','')).strip().casefold()==number.casefold():
                        con.close();raise HTTPException(409,'Customer and contract number already exist. No duplicate has been created.')
            if new.get('Start date') and new.get('Expiry date') and str(new['Start date'])[:10]>str(new['Expiry date'])[:10]:
                con.close();raise HTTPException(400,'Expiry cannot precede start date')
            new['Renewal status']=status_for(str(new.get('Expiry date') or '')) if sheet=='Maintenance Database' else 'Historical / archived'
            row_number=int(con.execute('SELECT COALESCE(MAX(source_row),1) FROM contracts WHERE source_sheet=?',(sheet,)).fetchone()[0])+1
            if row_number>(803 if sheet=='Maintenance Database' else 8495):
                con.close();raise HTTPException(409,'The approved Excel template has no spare rows. Extend its table before approving new records.')
            key='XLS-'+uuid.uuid4().hex[:10].upper();new['Record ID']=key
            status='Active' if sheet=='Maintenance Database' else 'Expired'
            cid=con.execute('INSERT INTO contracts(row_key,status,source_sheet,source_row,fields,dirty,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)',
                (key,status,sheet,row_number,json.dumps(new,ensure_ascii=False),now(),now())).lastrowid
            con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
                (cid,actor(payload.actor),'Created from reviewed Excel re-import',None,json.dumps({'export_id':review['export_id'],'fields':new},ensure_ascii=False),now()))
            results.append({'contract_id':cid,'action':'new','sheet':sheet})
            continue
        if entry['action'] not in ('update','move'):
            con.close();raise HTTPException(409,'Unsupported Excel change type.')
        row=con.execute('SELECT * FROM contracts WHERE id=?',(entry['contract_id'],)).fetchone()
        if not row or row['revision']!=entry['revision']:
            con.close();raise HTTPException(409,f'{entry["key"]} changed since preview. Upload again to check for conflicts.')
        changed={}
        for field in entry['changes']:
            conflict_key=f'{i}:{field["field"]}'
            if field['conflict'] and conflict_key not in conflicts:
                con.close();raise HTTPException(409,'Explicitly confirm each conflicting field before applying.')
            changed[field['field']]=field['incoming']
        existing=json.loads(row['fields']);new={**existing,**changed}
        if not str(new.get('Customer / site','')).strip():
            con.close();raise HTTPException(400,'Customer/site cannot be blank')
        if new.get('Start date') and new.get('Expiry date') and str(new['Start date'])[:10]>str(new['Expiry date'])[:10]:
            con.close();raise HTTPException(400,'Expiry cannot precede start date')
        destination=entry['sheet'] if entry['action']=='move' else row['source_sheet']
        if entry['action']=='move':
            if row['source_sheet']!=entry['from_sheet']:
                con.close();raise HTTPException(409,'Record location has changed since the Excel export')
            row_number=int(con.execute('SELECT COALESCE(MAX(source_row),1) FROM contracts WHERE source_sheet=?',(destination,)).fetchone()[0])+1
            if row_number>(803 if destination=='Maintenance Database' else 8495):
                con.close();raise HTTPException(409,'The destination Excel table is full. Extend the approved template first.')
            con.execute('UPDATE contracts SET status=?,source_sheet=?,source_row=?,old_sheet=?,old_row=? WHERE id=?',
                ('Active' if destination=='Maintenance Database' else 'Expired',destination,row_number,row['source_sheet'],row['source_row'],row['id']))
        new['Renewal status']=status_for(str(new.get('Expiry date') or '')) if destination=='Maintenance Database' else 'Historical / archived'
        con.execute('UPDATE contracts SET fields=?,revision=revision+1,dirty=1,updated_at=? WHERE id=?',
            (json.dumps(new,ensure_ascii=False),now(),row['id']))
        con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
            (row['id'],actor(payload.actor),'Approved Excel transfer' if entry['action']=='move' else 'Approved Excel re-import',json.dumps(existing,ensure_ascii=False),json.dumps({'export_id':review['export_id'],'changed_fields':changed,'destination_sheet':destination},ensure_ascii=False),now()))
        results.append({'contract_id':row['id'],'changed_fields':list(changed)})
    con.execute('UPDATE import_reviews SET status=? WHERE review_id=?',('Applied' if len(chosen)==len(items) else 'Partially applied',review_id))
    con.commit();con.close()
    return {'ok':True,'updated':len(results),'records':results,'remaining':len(items)-len(chosen)}

@app.post('/api/admin/backup')
def backup_database(request:Request):
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Local backup endpoint is available only on the host computer')
    return {'ok':True,**create_local_backup(force=True)}

# ---- Import inbox: no uncertain values are silently written to the master. ----
def _rank_contract_candidates(fields, con=None):
    owned=con is None
    if owned:con=connect()
    try:
        rows=con.execute("SELECT id,fields,status FROM contracts WHERE status='Active'").fetchall()
        data=[{'id':r['id'],'fields':json.loads(r['fields']),'status':r['status']} for r in rows]
        return candidate_matches(fields,data)
    finally:
        if owned:con.close()

def find_match(fields):
    """V7 matching: suggestions never silently update the Maintenance Master."""
    result=_rank_contract_candidates(fields)
    chosen=result['suggested_target_id']
    if chosen is not None:
        # A corroborated, unique contract number can be proposed for preview.
        con=connect();row=con.execute('SELECT fields FROM contracts WHERE id=?',(chosen,)).fetchone();con.close()
        return {'id':chosen,'match':'Exact contract reference with supporting evidence',
                'existing':json.loads(row['fields']),'candidates':result['candidates']}
    candidates=result['candidates']
    return {'match':('Candidate matches – manual selection required' if candidates else 'New or unmatched – verify'),
            'candidates':candidates}

def extract_text_pdf(content):
    doc=fitz.open(stream=content,filetype='pdf');parts=[]
    for i,page in enumerate(doc):
        txt=page.get_text('text')
        if txt.strip():parts.append({'page':i+1,'text':txt})
    return len(doc),parts

def proposals_from_text(pages):
    combined='\n'.join(p['text'] for p in pages)
    refs=list(dict.fromkeys(re.findall(r'\b(?:C?9\d{5,6}|C?\d{7})\b',combined)))[:30]
    date_strings=re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',combined)
    results=[]
    for i,ref in enumerate(refs[:12]):
        results.append({'id':i+1,'page':'See source PDF','confidence':'Needs review','fields':{'Contract number':ref},
                       'evidence':'Number detected in digital PDF text; context and record type must be checked.', 'source':'Text-based PDF parser'})
    return results

@app.post('/api/imports')
async def upload_document(file:UploadFile=File(...)):
    filename=re.sub(r'[^A-Za-z0-9._ -]','_',(file.filename or 'uploaded-file').replace('/','_').replace('\\','_'))[:135]
    content=await file.read()
    if len(content)>20_000_000:raise HTTPException(413,'Maximum upload size is 20 MB')
    if not content:raise HTTPException(400,'The uploaded file is empty')
    if filename.lower().endswith('.pdf') and not content.lstrip().startswith(b'%PDF-'):
        raise HTTPException(400,'The uploaded file is not a valid PDF')
    sha=hashlib.sha256(content).hexdigest()
    con=connect();dup=con.execute('SELECT id FROM imports WHERE sha256=?',(sha,)).fetchone()
    if dup:con.close();return {'duplicate':True,'id':dup[0],'message':'This exact file has already been uploaded; no duplicate records created.'}
    ext=filename.lower().rsplit('.',1)[-1]
    proposals=[];notes='';doc_type=ext
    evidence={}
    if ext=='pdf':
        try:pages_count,pages=extract_text_pdf(content)
        except Exception as e:raise HTTPException(400,'Cannot open PDF: '+str(e)[:150])
        extraction_method='Embedded PDF text'
        missing=sorted(set(range(1,pages_count+1))-{p['page'] for p in pages})
        ocr_warnings=[]
        mode=os.environ.get('PULSE_OCR_MODE','auto').lower()
        if mode not in ('auto','azure','local','off'):
            mode='off'
        if missing and mode!='off':
            if mode in ('auto','azure') and document_ai_configured():
                try:
                    cloud_pages=await asyncio.to_thread(read_scanned_pdf,content)
                    by_page={p['page']:p for p in pages}
                    for candidate in cloud_pages:
                        if candidate.get('text','').strip():by_page[candidate['page']]=candidate
                    pages=list(by_page.values())
                    extraction_method='Embedded PDF text + Azure Document Intelligence'
                except DocumentAIError as e:
                    ocr_warnings.append('Cloud OCR: '+str(e))
            still_missing=sorted(set(range(1,pages_count+1))-{p['page'] for p in pages})
            if still_missing and mode in ('auto','local') and local_ocr_available():
                try:
                    offline,warnings=await asyncio.to_thread(read_local_scanned_pdf,content,still_missing)
                    pages=sorted(pages+offline,key=lambda p:p['page'])
                    ocr_warnings.extend(warnings)
                    extraction_method='Embedded PDF text + offline Tesseract OCR'
                except LocalOCRError as e:ocr_warnings.append('Local OCR: '+str(e))
            elif still_missing and mode=='local':ocr_warnings.append('Tesseract was not found; handwritten and scanned pages need manual review.')
            elif still_missing and mode=='azure' and not document_ai_configured():ocr_warnings.append('Azure OCR is not configured.')
        if len(missing)>35 and mode in ('auto','local'):
            ocr_warnings.append('Local OCR is limited to the first 35 unread pages per upload.')
        pages=sorted(pages,key=lambda p:p['page'])
        if pages:
            proposals,evidence=reference_proposals(pages)
            evidence['invoice_groups']=invoice_groups(pages)
            evidence['invoice_review']=analyse_invoice_document(pages)
            evidence['invoice_ocr_warnings']=evidence['invoice_groups'].get('possible_ocr_conflicts',[])
            evidence['unread_pages']=sorted(set(range(1,pages_count+1))-{p['page'] for p in pages})
            evidence['reading_warnings']=ocr_warnings
            evidence['page_sources']=[{'page':p['page'],'source':p.get('source', 'Embedded PDF text'),'rotation':p.get('rotation',0)} for p in pages]
            evidence['reading_method']=extraction_method
            notes=f'{pages_count} pages; {len(pages)} pages with extracted text via {extraction_method}. Found {len(evidence["contract_references"])} candidate contract references, {len(evidence["equipment_codes"])} possible product codes and {len(evidence["invoice_groups"]["groups"])} invoice groups. Printed OCR text is NOT verified; handwritten references and dates may be missed. No data was automatically saved.'
        else:
            evidence={'invoice_groups':{'groups':[],'unassigned_pages':list(range(1,pages_count+1))},
                      'unread_pages':list(range(1,pages_count+1)), 'page_count':pages_count}
            evidence['reading_warnings']=ocr_warnings
            if not notes:notes=f'{pages_count} pages. This appears to be a scanned PDF or image-only file; no readable PDF text was found. Configure document extraction or enter verified details manually. Handwritten details have NOT been read.'
    elif ext=='csv':
        try:
            parsed=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        except Exception:raise HTTPException(400,'Could not read CSV')
        for n,f in enumerate(parsed[:150],1):
            obj={k:str(v) for k,v in f.items() if k in HEADERS and v}
            if obj:proposals.append({'id':n,'page':f'Row {n+1}','confidence':'Spreadsheet import – review','fields':obj,'evidence':'Imported from CSV row','source':'CSV'})
        notes=f'{len(parsed)} rows read. Recognised columns have been mapped; approve the records you want to add or update.'
    elif ext=='xlsx':
        # Accept a standard structured Excel workbook without executing macros.
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                sheet_name='xl/worksheets/sheet1.xml';root=__import__('lxml.etree',fromlist=['']).fromstring(z.read(sheet_name))
                from .excel_io import Q,splitcell
                shared=[]
                if 'xl/sharedStrings.xml' in z.namelist():
                    ss=__import__('lxml.etree',fromlist=['']).fromstring(z.read('xl/sharedStrings.xml'))
                    shared=[''.join(t.text or '' for t in si.iter(Q('t'))) for si in ss.findall(Q('si'))]
                def cv(c):
                    v=c.find(Q('v'))
                    if c.get('t')=='inlineStr':return ''.join(x.text or '' for x in c.iter(Q('t')))
                    if v is None:return ''
                    return shared[int(v.text)] if c.get('t')=='s' else v.text
                rows=root.find(Q('sheetData')).findall(Q('row'))
                hdr={splitcell(c.get('r'))[0]:str(cv(c)).strip() for c in rows[0].findall(Q('c'))}
                recognized={i:h for i,h in hdr.items() if h in HEADERS}
                for r in rows[1:151]:
                    obj={recognized[splitcell(c.get('r'))[0]]:str(cv(c)) for c in r.findall(Q('c')) if splitcell(c.get('r'))[0] in recognized and cv(c)}
                    if obj.get('Customer / site') or obj.get('Contract number'):
                        proposals.append({'id':len(proposals)+1,'page':'Excel row '+r.get('r'),'confidence':'Spreadsheet import – review','fields':obj,'evidence':'Exact column heading match','source':'XLSX'})
                notes=f'{len(recognized)} recognised headings; {len(proposals)} rows prepared. No changes have been applied.'
        except Exception as e:raise HTTPException(400,'Could not read Excel file: '+str(e)[:160])
    else:raise HTTPException(400,'Upload PDF, CSV or .xlsx files')
    for p in proposals:
        p['matching']=find_match(p['fields'])
        p['approved']=False
        p.setdefault('target_contract_id',None)
    cur=con.execute('INSERT INTO imports(filename,type,sha256,status,extraction_note,proposals,created_at) VALUES (?,?,?,?,?,?,?)',
       (filename,doc_type,sha,'Awaiting review',notes,json.dumps(proposals,ensure_ascii=False),now()))
    iid=cur.lastrowid
    con.execute('UPDATE imports SET evidence_json=? WHERE id=?',(json.dumps(evidence,ensure_ascii=False),iid))
    con.commit();con.close()
    storage=Path(DATA)/'uploads';storage.mkdir(exist_ok=True);(storage/f'{iid}_{filename}').write_bytes(content)
    return {'id':iid,'duplicate':False,'notes':notes,'count':len(proposals),'proposals':proposals,'evidence':evidence}

@app.get('/api/imports')
def imports_list():
    con=connect();r=[dict(x) for x in con.execute('SELECT id,filename,type,status,extraction_note,created_at FROM imports ORDER BY id DESC LIMIT 40')];con.close();return r

@app.post('/api/imports/batch')
async def upload_document_batch(files:list[UploadFile]=File(...)):
    # Every file passes the established single-document safety and duplicate checks.
    if not files or len(files)>12:
        raise HTTPException(400,'Choose between 1 and 12 documents per batch.')
    sizes=[f.size or 0 for f in files]
    if any(x>20_000_000 for x in sizes) or sum(sizes)>60_000_000:
        raise HTTPException(413,'Maximum 20 MB per file and 60 MB per batch.')
    results=[]
    for file in files:
        label=(file.filename or 'Unnamed file')[:135]
        try:
            result=await upload_document(file)
            results.append({'filename':label,'id':result['id'],'status':'Already uploaded' if result.get('duplicate') else 'Awaiting review',
                            'message':result.get('message') or result.get('notes','')[:200]})
        except HTTPException as error:
            results.append({'filename':label,'id':None,'status':'Upload failed','message':str(error.detail)[:200]})
        except Exception:
            results.append({'filename':label,'id':None,'status':'Upload failed','message':'The file could not be processed. Check its format and retry.'})
    return {'results':results,'processed':sum(x['id'] is not None for x in results),
        'failed':sum(x['status']=='Upload failed' for x in results),
        'message':'Imports are awaiting staff review. No changes have been made to Contracts or the invoice ledger.'}


def _current_import_queue():
    con=connect()
    rows=[dict(r) for r in con.execute('SELECT id,filename,type,status,evidence_json FROM imports ORDER BY id DESC LIMIT 200')]
    ids=[r['id'] for r in rows]
    reviews=[]
    if ids:
        reviews=[dict(r) for r in con.execute('SELECT import_id,group_id FROM invoice_document_reviews WHERE import_id IN ('+','.join('?' for _ in ids)+')',ids)]
    con.close()
    return build_review_queue(rows,reviews)

@app.get('/api/imports/review-queue')
def import_review_queue(status:str='All'):
    queue=_current_import_queue()
    if status!='All':
        if status not in ('Needs review','Source verified','Reference only'):
            raise HTTPException(400,'Unrecognised review status')
        queue['items']=[item for item in queue['items'] if item['status']==status]
    return queue

@app.get('/api/imports/review-queue.csv')
def export_import_review_queue():
    data=queue_csv(_current_import_queue())
    return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="Pulse_Import_Review_Queue.csv"'})

@app.get('/api/imports/{iid}/invoice-review')
def get_invoice_review(iid:int):
    """Expose invoice-level evidence and verified review, without touching Contracts."""
    con=connect()
    row=con.execute('SELECT evidence_json,filename,type FROM imports WHERE id=?',(iid,)).fetchone()
    if not row:
        con.close();raise HTTPException(404,'Import not found')
    if row['type']!='pdf':
        con.close();raise HTTPException(400,'Invoice document review is available for PDF imports')
    evidence=json.loads(row['evidence_json'] or '{}')
    analysis=evidence.get('invoice_review')
    if not analysis:
        # V7 PDFs may not contain detailed evidence, but detected invoice groups
        # remain reviewable. Full extraction requires a fresh non-duplicate scan.
        old=evidence.get('invoice_groups') or {'groups':[],'unassigned_pages':[]}
        analysis={'invoices':[{'id':'inv-'+str(i),'pages':g['pages'],
           'detected_invoice_number':g['invoice_number'],'field_candidates':[],
           'conflicts':[],'equipment_codes':[],'review_status':'Needs visual confirmation'}
           for i,g in enumerate(old.get('groups',[]),1)],
           'unassigned':[{'page':p,'reason':'Page not assigned to a printed invoice'} for p in old.get('unassigned_pages',[])],
           'possible_ocr_conflicts':old.get('possible_ocr_conflicts',[]),
           'note':'Older import: limited invoice evidence. Verify all details against the original PDF.'}
    verified={r['group_id']:json.loads(r['review_data']) for r in con.execute(
         'SELECT group_id,review_data FROM invoice_document_reviews WHERE import_id=?',(iid,))}
    con.close()
    return {'filename':row['filename'],'analysis':analysis,'verified_reviews':verified,
         'warning':'These are invoice source records, NOT confirmed maintenance income. No contract or Master data is changed.'}

class InvoiceReviewApproval(BaseModel):
    invoice_number:str
    invoice_date:str=''
    account_reference:str=''
    contract_reference:str=''
    customer_site:str=''
    reviewer:str
    notes:str=''
    confirmed_from_source:bool=False

class ManualInvoiceReview(InvoiceReviewApproval):
    page_number:int

@app.post('/api/imports/{iid}/invoice-review/manual')
def record_unreadable_invoice(iid:int,payload:ManualInvoiceReview):
    """Staff may verify an invoice on a page whose printed number OCR missed."""
    con=connect();con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT evidence_json,type,sha256 FROM imports WHERE id=?',(iid,)).fetchone()
    if not row:
        con.close();raise HTTPException(404,'Import not found')
    if row['type']!='pdf':
        con.close();raise HTTPException(400,'This is not a PDF upload')
    evidence=json.loads(row['evidence_json'] or '{}')
    pages={p['page'] for p in evidence.get('invoice_review',{}).get('unassigned',[])}
    if not pages:pages=set(evidence.get('unread_pages') or evidence.get('invoice_groups',{}).get('unassigned_pages',[]))
    if payload.page_number not in pages:
        con.close();raise HTTPException(409,'Select a page that has no reliable invoice number. Use the detected invoice review for other pages.')
    group={'id':f'manual-p{payload.page_number}','pages':[payload.page_number],
           'detected_invoice_number':''}
    try:validated=validate_review(payload.model_dump(),group)
    except ValueError as e:
        con.close();raise HTTPException(400,str(e))
    if PILOT_MODE:validated['reviewer']=actor()
    validated.update({'source_sha256':row['sha256'],'source_import_id':iid,'verified_at':now(),
         'status':'Manually confirmed on unreadable source page – not posted to Master'})
    old=con.execute('SELECT review_data FROM invoice_document_reviews WHERE import_id=? AND group_id=?',
                    (iid,group['id'])).fetchone()
    serialised=json.dumps(validated,ensure_ascii=False)
    con.execute("""INSERT INTO invoice_document_reviews(import_id,group_id,review_data,verified_at)
          VALUES (?,?,?,?) ON CONFLICT(import_id,group_id)
          DO UPDATE SET review_data=excluded.review_data,verified_at=excluded.verified_at""",
          (iid,group['id'],serialised,now()))
    con.execute('INSERT INTO invoice_review_history(import_id,group_id,before_data,after_data,reviewed_at) VALUES (?,?,?,?,?)',
         (iid,group['id'],old['review_data'] if old else None,serialised,now()))
    con.commit();con.close()
    return {'ok':True,'group_id':group['id'],'review':validated,
            'message':'Staff-verified invoice recorded with its source page. No Master changes.'}

@app.post('/api/imports/{iid}/invoice-review/{group_id}')
def save_invoice_review(iid:int,group_id:str,payload:InvoiceReviewApproval):
    con=connect();con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT evidence_json,type,sha256 FROM imports WHERE id=?',(iid,)).fetchone()
    if not row:
        con.close();raise HTTPException(404,'Import not found')
    if row['type']!='pdf':
        con.close();raise HTTPException(400,'This is not a PDF document')
    evidence=json.loads(row['evidence_json'] or '{}')
    detailed=evidence.get('invoice_review',{}).get('invoices') or []
    if not detailed:
        detailed=[{'id':'inv-'+str(i),'pages':g['pages'],
                   'detected_invoice_number':g['invoice_number']} for i,g in
                  enumerate(evidence.get('invoice_groups',{}).get('groups',[]),1)]
    group=next((g for g in detailed if g['id']==group_id),None)
    if not group:
        con.close();raise HTTPException(404,'That invoice group was not identified. Inspect the source PDF before continuing.')
    try:validated=validate_review(payload.model_dump(),group)
    except ValueError as e:
        con.close();raise HTTPException(400,str(e))
    if PILOT_MODE:validated['reviewer']=actor()
    validated.update({'source_sha256':row['sha256'],'source_import_id':iid,
                      'verified_at':now(),'status':'Source reviewed – not posted to contract or invoice ledger'})
    before=con.execute('SELECT review_data FROM invoice_document_reviews WHERE import_id=? AND group_id=?',(iid,group_id)).fetchone()
    old=before['review_data'] if before else None
    serialised=json.dumps(validated,ensure_ascii=False)
    con.execute("""INSERT INTO invoice_document_reviews(import_id,group_id,review_data,verified_at)
                   VALUES (?,?,?,?) ON CONFLICT(import_id,group_id)
                   DO UPDATE SET review_data=excluded.review_data,verified_at=excluded.verified_at""",
                (iid,group_id,serialised,now()))
    con.execute('INSERT INTO invoice_review_history(import_id,group_id,before_data,after_data,reviewed_at) VALUES (?,?,?,?,?)',
                (iid,group_id,old,serialised,now()))
    con.commit();con.close()
    return {'ok':True,'review':validated,'message':'Invoice evidence saved. Contract and financial records were NOT changed.'}

@app.post('/api/imports/{iid}/invoice-review/{group_id}/prepare-contract')
def prepare_verified_invoice_contract(iid:int,group_id:str):
    """Stage staff-verified invoice identifiers for the existing contract approval UI.

    No amounts, warranty entitlement, service dates or contract writes are inferred.
    """
    con=connect();con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT proposals,filename FROM imports WHERE id=?',(iid,)).fetchone()
    if not row:
        con.close();raise HTTPException(404,'Import not found')
    record=con.execute('SELECT review_data FROM invoice_document_reviews WHERE import_id=? AND group_id=?',
                       (iid,group_id)).fetchone()
    if not record:
        con.close();raise HTTPException(409,'First verify this invoice against the original scanned document.')
    details=json.loads(record['review_data'])
    if not details.get('customer_site') or not details.get('contract_reference'):
        con.close();raise HTTPException(409,'Enter the verified customer/site and handwritten contract reference before preparing a contract change.')
    from .matching import normal_number
    number=normal_number(details['contract_reference'])
    if not re.fullmatch(r'[A-Za-z0-9-]{4,25}',number):
        con.close();raise HTTPException(400,'Contract reference contains unexpected characters; check the original handwriting.')
    proposals=json.loads(row['proposals'])
    for proposal in proposals:
        if proposal.get('invoice_review_group_id')==group_id:
            con.close();return {'ok':True,'already_prepared':True,'proposal_id':proposal['id'],
                'message':'This invoice already has a proposal awaiting normal review.'}
    fields={'Customer / site':details['customer_site'],'Contract number':number}
    if details.get('account_reference'):
        fields['Invoice account']=details['account_reference']
    pid=max((int(p['id']) for p in proposals),default=0)+1
    proposal={'id':pid,'page':', '.join(map(str,details['pages'])),
        'confidence':'Staff-verified invoice identifiers – contract terms unverified',
        'fields':fields,'invoice_review_group_id':group_id,
        'evidence':f"Invoice {details['invoice_number']}. Staff confirmed customer, account and handwritten contract reference against PDF; invoice sale is NOT contract income.",
        'source':'Reviewed invoice evidence','approved':False,'target_contract_id':None,
        'matching':find_match(fields)}
    proposals.append(proposal)
    con.execute('UPDATE imports SET proposals=? WHERE id=?',(json.dumps(proposals,ensure_ascii=False),iid))
    con.commit();con.close()
    return {'ok':True,'already_prepared':False,'proposal_id':pid,
      'message':'A contract proposal has been prepared for review. No Master changes have been applied.'}

@app.get('/api/imports/{iid}')
def import_details(iid:int):
    con=connect();r=con.execute('SELECT * FROM imports WHERE id=?',(iid,)).fetchone();con.close()
    if not r:raise HTTPException(404,'Import not found')
    d=dict(r);d['proposals']=json.loads(d['proposals']);d['evidence']=json.loads(d.get('evidence_json') or '{}');d.pop('sha256')
    codes={str(x.get('value','')).upper() for x in d['evidence'].get('equipment_codes',[]) if x.get('value')}
    # Catalogue is reference-only. No inference of customer ownership or cover.
    if codes:
        con=connect()
        matched=[dict(x) for x in con.execute('SELECT sku,model,name,console,software,frame,upholstery FROM catalogue WHERE sku IN ('+','.join('?' for _ in codes)+')',tuple(codes))]
        con.close();d['catalogue_matches']={x['sku']:x for x in matched}
    else:d['catalogue_matches']={}
    return d

class ProposalEdit(BaseModel):
    fields:dict[str,str]
    target_contract_id:int|None=None

class ApprovalOptions(BaseModel):
    expected_revision:int|None=None
    replace_fields:list[str]=[]
    actor:str='Demo coordinator'

class DocumentEquipmentLink(BaseModel):
    contract_id:int
    sku:str
    serial_number:str=''
    quantity:int=1
    installation_date:str=''
    warranty_expiry:str=''
    invoice_reference:str=''

@app.post('/api/imports/{iid}/equipment-link')
def link_document_equipment(iid:int,payload:DocumentEquipmentLink):
    con=connect();record=con.execute('SELECT evidence_json,filename FROM imports WHERE id=?',(iid,)).fetchone()
    if not record:con.close();raise HTTPException(404,'Import not found')
    evidence=json.loads(record['evidence_json'] or '{}')
    sku=payload.sku.strip().upper()
    detected={x['value'] for x in evidence.get('equipment_codes',[])}
    if sku not in detected:
        con.close();raise HTTPException(409,'This stock code was not detected in the document. Use the normal Equipment screen for manually entered machines.')
    if not con.execute('SELECT 1 FROM catalogue WHERE sku=?',(sku,)).fetchone():
        con.close();raise HTTPException(409,'Stock code has not been identified in the Pulse Fitness catalogue')
    contract=con.execute('SELECT fields FROM contracts WHERE id=? AND status="Active"',(payload.contract_id,)).fetchone()
    if not contract:con.close();raise HTTPException(404,'Active contract not found')
    if payload.quantity<1 or payload.quantity>10000:
        con.close();raise HTTPException(400,'Quantity must be between 1 and 10,000')
    for date_value in (payload.installation_date,payload.warranty_expiry):
        if date_value:
            try:dt.date.fromisoformat(date_value)
            except ValueError:
                con.close();raise HTTPException(400,'Dates must be in YYYY-MM-DD format')
    if con.execute('SELECT 1 FROM equipment WHERE source_import_id=? AND contract_id=? AND sku=? AND serial_number=? AND invoice_reference=?',
        (iid,payload.contract_id,sku,payload.serial_number.strip(),payload.invoice_reference.strip())).fetchone():
        con.close();raise HTTPException(409,'This equipment link has already been imported from the document')
    if payload.serial_number and con.execute('SELECT 1 FROM equipment WHERE contract_id=? AND upper(serial_number)=?',
        (payload.contract_id,payload.serial_number.strip().upper())).fetchone():
        con.close();raise HTTPException(409,'The serial number is already linked to this contract')
    pages=next((x['pages'] for x in evidence['equipment_codes'] if x['value']==sku),[])
    note=f'Source document: {record["filename"]}; page(s): {", ".join(map(str,pages))}. Staff-verified link, not automatic entitlement.'
    eid=con.execute('INSERT INTO equipment (contract_id,sku,serial_number,quantity,installation_date,warranty_expiry,invoice_reference,notes,created_at,source_import_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (payload.contract_id,sku,payload.serial_number.strip(),payload.quantity,payload.installation_date,payload.warranty_expiry,payload.invoice_reference.strip(),note,now(),iid)).lastrowid
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',
        (payload.contract_id,actor('Demo coordinator'),'Linked equipment from reviewed document',None,json.dumps({'import_id':iid,'equipment_id':eid,'sku':sku,'pages':pages},ensure_ascii=False),now()))
    con.commit();con.close();return {'ok':True,'equipment_id':eid,'contract_id':payload.contract_id}

@app.get('/api/imports/{iid}/pages/{page}/preview')
def source_page_preview(iid:int,page:int,rotate:int=0):
    """Display a specific original PDF page beside its suggested data.

    Source is shown, never modified, and is served with a no-cache header.
    """
    con=connect();record=con.execute('SELECT filename,type FROM imports WHERE id=?',(iid,)).fetchone();con.close()
    if not record:raise HTTPException(404,'Import not found')
    if record['type']!='pdf':raise HTTPException(400,'Page previews are only available for PDF files')
    if rotate not in (0,90,180,270):raise HTTPException(400,'Invalid page rotation')
    source=Path(DATA)/'uploads'/f'{iid}_{record["filename"]}'
    if not source.is_file():raise HTTPException(404,'Original PDF not found')
    with fitz.open(str(source)) as pdf:
        if page<1 or page>len(pdf):raise HTTPException(404,'Page not found')
        pix=pdf[page-1].get_pixmap(matrix=fitz.Matrix(1.15,1.15).prerotate(rotate),colorspace=fitz.csRGB,alpha=False)
        png=pix.tobytes('png')
    return Response(content=png,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/api/imports/{iid}/source')
def import_source(iid:int):
    con=connect();r=con.execute('SELECT filename FROM imports WHERE id=?',(iid,)).fetchone();con.close()
    if not r:raise HTTPException(404,'Import not found')
    path=Path(DATA)/'uploads'/f'{iid}_{r["filename"]}'
    if not path.is_file():raise HTTPException(404,'Original document unavailable')
    media={'pdf':'application/pdf','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','csv':'text/csv'}
    return FileResponse(path,media_type=media.get(path.suffix.lower().lstrip('.'),'application/octet-stream'),filename=r['filename'],content_disposition_type='inline' if path.suffix.lower()=='.pdf' else 'attachment')

@app.post('/api/imports/{iid}/proposals')
def add_manual_proposal(iid:int,payload:ProposalEdit):
    con=connect();r=con.execute('SELECT proposals FROM imports WHERE id=?',(iid,)).fetchone()
    if not r:con.close();raise HTTPException(404,'Import not found')
    fields={k:str(v).strip() for k,v in payload.fields.items() if k in HEADERS and str(v).strip()}
    if not fields:con.close();raise HTTPException(400,'Enter at least one detail from the document')
    proposals=json.loads(r['proposals']);pid=max([x['id'] for x in proposals],default=0)+1
    proposal={'id':pid,'page':'See original document','confidence':'Staff-entered – verify','fields':fields,
       'evidence':'Manually recorded by staff from the original uploaded document.',
       'source':'Coordinator review','approved':False,'target_contract_id':payload.target_contract_id,'matching':find_match(fields)}
    proposals.append(proposal)
    con.execute('UPDATE imports SET proposals=?,status=? WHERE id=?',(json.dumps(proposals,ensure_ascii=False),'Awaiting review',iid))
    con.commit();con.close();return {'ok':True,'proposal':proposal}

@app.patch('/api/imports/{iid}/proposals/{pid}')
def edit_proposal(iid:int,pid:int,payload:ProposalEdit):
    con=connect();r=con.execute('SELECT proposals FROM imports WHERE id=?',(iid,)).fetchone()
    if not r:con.close();raise HTTPException(404,'Import not found')
    proposals=json.loads(r['proposals']);p=next((x for x in proposals if x['id']==pid),None)
    if not p:con.close();raise HTTPException(404,'Proposal not found')
    if p.get('approved'):con.close();raise HTTPException(409,'Approved proposals cannot be edited')
    unknown=set(payload.fields)-set(HEADERS)
    if unknown:con.close();raise HTTPException(400,'Unrecognised contract fields')
    p['fields']={k:str(v).strip() for k,v in payload.fields.items() if str(v).strip()}
    p['target_contract_id']=payload.target_contract_id
    p['matching']=find_match(p['fields'])
    p['reviewed_at']=now()
    con.execute('UPDATE imports SET proposals=? WHERE id=?',(json.dumps(proposals,ensure_ascii=False),iid))
    con.commit();con.close();return {'ok':True,'proposal':p}

@app.get('/api/imports/{iid}/proposals/{pid}/matches')
def proposal_match_candidates(iid:int,pid:int):
    con=connect();row=con.execute('SELECT proposals FROM imports WHERE id=?',(iid,)).fetchone();con.close()
    if not row:raise HTTPException(404,'Import not found')
    p=next((x for x in json.loads(row['proposals']) if x['id']==pid),None)
    if not p:raise HTTPException(404,'Proposal not found')
    return _rank_contract_candidates(p.get('fields') or {})

@app.get('/api/imports/{iid}/proposals/{pid}/preview')
def proposal_preview(iid:int,pid:int):
    con=connect();r=con.execute('SELECT proposals FROM imports WHERE id=?',(iid,)).fetchone()
    if not r:con.close();raise HTTPException(404,'Import not found')
    p=next((x for x in json.loads(r['proposals']) if x['id']==pid),None)
    if not p:con.close();raise HTTPException(404,'Proposal not found')
    match=find_match(p['fields']);target_id=p.get('target_contract_id')
    if target_id is not None:target=con.execute('SELECT id,fields,status,revision FROM contracts WHERE id=?',(target_id,)).fetchone()
    else:
        target=con.execute('SELECT id,fields,status,revision FROM contracts WHERE id=?',(match['id'],)).fetchone() if match.get('match')=='Exact contract reference with supporting evidence' else None
    if target and target['status']!='Active':con.close();raise HTTPException(409,'The selected contract is archived')
    ranked=_rank_contract_candidates(p['fields'])
    old=json.loads(target['fields']) if target else {}
    fields={k:str(v).strip() for k,v in p['fields'].items() if k in HEADERS and str(v).strip()}
    comparisons=[{'field':k,'existing':old.get(k,''),'incoming':v,'conflict':bool(old.get(k) not in (None,'',v))} for k,v in fields.items()]
    con.close()
    return {'id':pid,'target_id':target['id'] if target else None,'target_revision':target['revision'] if target else None,'match':match.get('match'),
            'create_new':not bool(target),'possible_matches':ranked['candidates'],'fields':comparisons,'approved':p.get('approved',False),
            'warning':'Review conflicting values individually. Invoice prices are not contract values.'}

@app.post('/api/imports/{iid}/approve/{pid}')
def approve_proposal(iid:int,pid:int,options:ApprovalOptions=Body(default=ApprovalOptions())):
    con=connect();r=con.execute('SELECT * FROM imports WHERE id=?',(iid,)).fetchone()
    if not r:con.close();raise HTTPException(404,'Import not found')
    items=json.loads(r['proposals'])
    p=next((x for x in items if x['id']==pid),None)
    if not p:con.close();raise HTTPException(404,'Proposal not found')
    if p.get('approved'):con.close();raise HTTPException(409,'Proposal was already approved')
    # Match using a separate read-only connection BEFORE taking a write lock.
    # SQLite's journal-mode setup on that reader otherwise waits on our write lock.
    match=find_match(p['fields'])
    con.execute('BEGIN IMMEDIATE')
    latest=con.execute('SELECT proposals FROM imports WHERE id=?',(iid,)).fetchone()
    current_p=next((x for x in json.loads(latest['proposals']) if x['id']==pid),None)
    if not current_p or current_p.get('approved'):
        con.close();raise HTTPException(409,'This proposal has already been approved or was removed')
    items=json.loads(latest['proposals']);p=next(x for x in items if x['id']==pid)
    existing=p.get('target_contract_id')
    if existing is None and match.get('match')=='Exact contract reference with supporting evidence':existing=match['id']
    if existing is None and any(c['exact_contract_number'] for c in match.get('candidates',[])):
        con.close();raise HTTPException(409,'This contract reference exists in the database. Choose and verify the correct existing record before approval.')
    fields={k:v for k,v in p['fields'].items() if k in HEADERS and v}
    if existing:
        target=con.execute('SELECT * FROM contracts WHERE id=?',(existing,)).fetchone()
        if not target or target['status']!='Active':
            con.close();raise HTTPException(409,'Selected contract is not active')
        concurrency_check(target,options.expected_revision,con)
        old=json.loads(target['fields'])
        conflict={k for k,v in fields.items() if old.get(k) not in (None,'',v)}
        replace=set(options.replace_fields)
        if not replace.issubset(conflict):
            con.close();raise HTTPException(400,'Only actual conflicting fields may be replaced')
        if conflict-replace:
            con.close();raise HTTPException(409,'Review the conflicting fields: '+', '.join(sorted(conflict-replace)))
        new=old.copy();new.update(fields)
        con.execute('UPDATE contracts SET fields=?,dirty=1,revision=revision+1,updated_at=? WHERE id=?',(json.dumps(new,ensure_ascii=False),now(),existing))
        cid=existing;action='Approved document update'
    else:
        if not fields.get('Customer / site'):
            con.close();raise HTTPException(409,'Customer name is required before a new contract can be created')
        if not fields.get('Contract number'):
            con.close();raise HTTPException(409,'Contract number is required for a new document-based contract')
        if any(c['exact_contract_number'] for c in match.get('candidates',[])):
            con.close();raise HTTPException(409,'This contract reference already exists; select and verify the existing record')
        row=int(con.execute("SELECT coalesce(max(source_row),1) FROM contracts WHERE source_sheet='Maintenance Database'").fetchone()[0])+1
        if row>803:con.close();raise HTTPException(409,'No preformatted contract rows remain in Excel template')
        key='DOC-'+uuid.uuid4().hex[:8].upper();new={k:fields.get(k,'') for k in HEADERS};new['Record ID']=key
        new['Renewal status']=status_for(str(new.get('Expiry date') or ''))
        cid=con.execute('INSERT INTO contracts(row_key,status,source_sheet,source_row,fields,dirty,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
            (key,'Active','Maintenance Database',row,json.dumps(new,ensure_ascii=False),1,now(),now())).lastrowid
        action='Created from reviewed document'
    p['approved']=True;p['approved_at']=now();p['approved_by']=actor(options.actor)
    status='Completed' if all(x.get('approved') for x in items) else 'Partially approved'
    con.execute('UPDATE imports SET proposals=?,status=? WHERE id=?',(json.dumps(items,ensure_ascii=False),status,iid))
    con.execute('INSERT INTO changes(contract_id,actor,action,before_data,after_data,at) VALUES (?,?,?,?,?,?)',(cid,actor(options.actor),action,None,json.dumps({'import_id':iid,'proposal_id':pid,'source_filename':r['filename'],'source_sha256':r['sha256'],'source_pages':p.get('page',''),'extraction_source':p.get('source',''),'source_evidence':p.get('evidence',''),'fields':fields,'overwritten_fields':sorted(options.replace_fields)},ensure_ascii=False),now()))
    con.commit();con.close()
    return {'ok':True,'contract_id':cid,'action':action}

@app.get('/api/health')
def health():
    """Minimal unauthenticated liveness for loopback-only reverse-proxy checks.

    Never returns contract counts, filesystem paths, secrets or user information.
    A dead/missing database must not claim a healthy service.
    """
    if not os.path.isfile(TEMPLATE):
        raise HTTPException(503,'Service not ready')
    try:
        # A read-only probe avoids accidental empty SQLite creation and never
        # performs writes during container health monitoring.
        uri=Path(DB).resolve().as_uri()+'?mode=ro'
        with sqlite3.connect(uri,uri=True,timeout=3) as connection:
            connection.execute('SELECT 1 FROM contracts LIMIT 1').fetchone()
    except (sqlite3.Error,OSError):
        raise HTTPException(503,'Service not ready')
    return {'status':'ok'}
