"""V10 protected-pilot acceptance: isolated copied data, three users, write collision, Excel export."""
from __future__ import annotations
import os,sys,subprocess,json,tempfile,shutil,threading,concurrent.futures
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test():
    with tempfile.TemporaryDirectory(prefix='pulse_v10_test_') as temp:
        tmp=Path(temp)
        for filename in ('contracts.sqlite3','approved_master.xlsx','equipment_catalogue.json'):
            shutil.copy2(ROOT/'data'/filename,tmp/filename)
        env=os.environ.copy()
        env.update(PULSE_DATA_DIR=temp,PULSE_PILOT_MODE='1',PULSE_COOKIE_SECURE='0',
            PULSE_SESSION_SECRET='test-only-secret-value-not-valid-for-live-abc12345',PULSE_AUTO_BACKUP='0')
        code=r'''
import json,threading,concurrent.futures,os
from fastapi.testclient import TestClient
from app.pilot_access import provision_user
provision_user('claire','Testing!456789','Coordinator')
provision_user('mandy','Testing!456789','Coordinator')
provision_user('director','Testing!456789','Viewer')
from app.main import app
from app.excel_quality import inspect_excel
from app.store import connect
c1=TestClient(app);c2=TestClient(app);viewer=TestClient(app)
assert c1.get('/',follow_redirects=False).status_code==303
assert c1.get('/api/contracts').status_code==401
for cli,user in [(c1,'claire'),(c2,'mandy'),(viewer,'director')]:
    resp=cli.post('/api/pilot/login',json={'username':user,'password':'Testing!456789'})
    assert resp.status_code==200,(user,resp.status_code,resp.text)
    assert resp.cookies['pulse_contracts_session']
    assert resp.cookies['pulse_contracts_csrf']
assert c1.get('/api/meta').status_code==200
cid=c1.get('/api/contracts',params={'limit':1}).json()['items'][0]['id']
rec=c1.get(f'/api/contracts/{cid}').json();revision=rec['revision'];field=rec['fields']['Site notes']
patch={'fields':{'Site notes':(str(field or '')+' PILOT TEST').strip()},'expected_revision':revision,'actor':'IMPERSONATION'}
assert c1.patch(f'/api/contracts/{cid}',json=patch).status_code==403 # anti-CSRF
v=viewer.patch(f'/api/contracts/{cid}',json=patch,headers={'X-Pulse-CSRF':viewer.cookies['pulse_contracts_csrf']})
assert v.status_code==403
barrier=threading.Barrier(2)
def write(cli,username):
    barrier.wait()
    body={'fields':{'Site notes':'Concurrent '+username},'expected_revision':revision,'actor':'spoofed'}
    return cli.patch(f'/api/contracts/{cid}',json=body,headers={'X-Pulse-CSRF':cli.cookies['pulse_contracts_csrf']}).status_code
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    f1=pool.submit(write,c1,'claire');f2=pool.submit(write,c2,'mandy')
    outcomes=sorted([f1.result(),f2.result()])
assert outcomes==[200,409],outcomes
con=connect();change=con.execute('SELECT actor FROM changes WHERE contract_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()['actor'];con.close()
assert change in ('claire','mandy'),change
# Concurrent new weekly-value entries must each receive their own Excel source row.
barrier2=threading.Barrier(2)
def add_week(cli,who):
    barrier2.wait()
    return cli.post('/api/ledger/weekly',json={'fields':{'Week ending (Friday)':'2026-10-16',
        'Customer / site':'TEST '+who,'Value recorded (£)':'12.00'}},
        headers={'X-Pulse-CSRF':cli.cookies['pulse_contracts_csrf']})
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    a=pool.submit(add_week,c1,'CLAIRE');b=pool.submit(add_week,c2,'MANDY');add_results=[a.result(),b.result()]
assert all(x.status_code==200 for x in add_results),[(x.status_code,x.text) for x in add_results]
with connect() as con:
    source_rows=[x[0] for x in con.execute("SELECT source_row FROM ledger WHERE kind='Weekly Values' AND fields LIKE '%TEST %'")]
assert len(source_rows)==2 and len(set(source_rows))==2,source_rows
pre=c1.get('/api/export/preflight').json()
assert pre['template']['ok'] and pre['capacity']['Maintenance Database']['remaining_rows']>=0,pre
export=c1.get('/api/export/excel')
assert export.status_code==200,(export.status_code,export.text[:200])
assert export.headers['content-type'].startswith('application/vnd.openxmlformats'),export.headers
from pathlib import Path
f=Path(os.environ['PULSE_DATA_DIR'])/'verified.xlsx';f.write_bytes(export.content)
check=inspect_excel(f)
assert check['ok'],check
assert check['stats']['active_rows']==642 and check['stats']['expired_rows']==8381,check['stats']
assert c1.get('/api/contracts').json()['total']>0
quality=c1.get('/api/quality/invoice-recognition').json()
assert 'verified_invoices' in quality and quality['number_accuracy_among_verified_detected_invoices'] is None,quality
logout=c1.post('/api/pilot/logout',headers={'X-Pulse-CSRF':c1.cookies['pulse_contracts_csrf']})
assert logout.status_code==200
assert c1.get('/api/contracts').status_code==401
print('V10 PILOT PASS; unauthenticated blocked; reviewer read-only; CSRF blocked; concurrent writes:',outcomes,'; audited actor:',change)
print('EXCEL PASS:',check['stats'],'; filters:',list(check['tables']))
print('LEDGER CONCURRENCY PASS: 2 different Excel rows,',source_rows)
'''
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,timeout=160)
        print(result.stdout)
        if result.returncode:
            print(result.stderr)
            raise AssertionError('V10 protected pilot test failed')

if __name__=='__main__':test()
