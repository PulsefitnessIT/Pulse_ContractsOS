"""V12 staged tests against an isolated copy of the bundled database."""
import os,sys,shutil,tempfile,json,io,zipfile,csv,datetime as dt
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory(prefix='pulse_v12_test_') as td:
        for name in ('contracts.sqlite3','approved_master.xlsx'):
            shutil.copy2(ROOT/'data'/name,Path(td)/name)
        os.environ['PULSE_DATA_DIR']=td
        os.environ['PULSE_PILOT_MODE']='0'
        os.environ['PULSE_AUTO_BACKUP']='0'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.store import connect
        client=TestClient(app)
        x=client.get('/api/meta');assert x.status_code==200 and x.json()['release'] in ('V12','V13 Development')
        x=client.get('/api/reports/sales/all-managers?start=2026-10-01');assert x.status_code==200
        meta=x.json(); z=client.get('/api/reports/sales/all-managers/download?start=2026-10-01')
        assert z.status_code==200
        with zipfile.ZipFile(io.BytesIO(z.content)) as a:
            reports=[n for n in a.namelist() if n.endswith('.csv')]
            assert len(reports)==len(meta['managers']) and all('..' not in n and '/' not in n for n in reports)
            count=sum(len(list(csv.reader(io.StringIO(a.read(n).decode('utf-8-sig')))))-1 for n in reports)
            assert count==meta['total'],(count,meta['total'])
        assert client.get('/api/reports/sales/all-managers?start=2026-02-01').status_code==400
        a=client.get('/api/ledger/weekly?year=2026&month=2026-09').json()
        for r in a['items']:assert str(r['fields']['Week ending (Friday)']).startswith('2026-09')
        b=client.get('/api/ledger/weekly?week=2026-W40').json()
        for r in b['items']:
            date=dt.date.fromisoformat(str(r['fields']['Week ending (Friday)'])[:10]);assert date.isocalendar().week==40
        all_planner=client.get('/api/service-planner?limit=150').json()
        assert sum(all_planner['summary'].values())==386
        assert all_planner['summary']['Strong match']>=200
        assert client.get('/api/service-planner?status=Review%20potential%20match').status_code==200
        # Candidate without any existing service date; no writes happen until a reviewer applies.
        from app.service_planner import proposals
        c=connect();items=proposals(c)
        elig=next((r for r in items if r['match_status']=='Strong match' and r['last_service'] and r['last_service']<=dt.date.today().isoformat()
            and not json.loads(c.execute('SELECT fields FROM contracts WHERE id=?',(r['contract_id'],)).fetchone()['fields']).get('Last service recorded')),None)
        assert elig
        target=c.execute('SELECT * FROM contracts WHERE id=?',(elig['contract_id'],)).fetchone();origrev=target['revision'];c.close()
        invalid=client.post('/api/service-planner/'+str(elig['source_row'])+'/approve',json={'contract_id':elig['contract_id'],'expected_revision':origrev,'confirm':False})
        assert invalid.status_code==400
        ok=client.post('/api/service-planner/'+str(elig['source_row'])+'/approve',json={'contract_id':elig['contract_id'],'expected_revision':origrev,'confirm':True})
        assert ok.status_code==200,ok.text
        repeat=client.post('/api/service-planner/'+str(elig['source_row'])+'/approve',json={'contract_id':elig['contract_id'],'expected_revision':origrev,'confirm':True})
        assert repeat.status_code==409
        c=connect();field=json.loads(c.execute('SELECT fields FROM contracts WHERE id=?',(elig['contract_id'],)).fetchone()['fields']);assert field['Last service recorded']==elig['last_service']
        assert c.execute('SELECT COUNT(*) FROM service_planner_approvals').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM changes WHERE contract_id=? AND action like "Verified service planner%"',(elig['contract_id'],)).fetchone()[0]==1
        c.close()
        # Public contact details require supporting URL; do not fabricate or allow unsupported fields.
        bad=client.post('/api/contracts/'+str(elig['contract_id'])+'/contact',json={'phone':'01234 567890'})
        assert bad.status_code==400
        good=client.post('/api/contracts/'+str(elig['contract_id'])+'/contact',json={'phone':'01234 567890','source_url':'https://example.org/contact'})
        assert good.status_code==200
        assert client.get('/api/contracts/'+str(elig['contract_id'])+'/contact').json()['phone']=='01234 567890'
        print('PASS V12: separate quarterly manager reports, week/month filters, planner review and audit, public contact source controls')

if __name__=='__main__':run()
