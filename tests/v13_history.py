"""V13 acceptance test: safe visit reviews, status-aware last service, duplication and due dates."""
import os, tempfile, shutil, sys, datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory(prefix='pulse_v13_test_') as td:
        for name in ('contracts.sqlite3','approved_master.xlsx'):
            shutil.copy2(ROOT/'data'/name,Path(td)/name)
        os.environ['PULSE_DATA_DIR']=td
        os.environ['PULSE_PILOT_MODE']='0'
        os.environ['PULSE_AUTO_BACKUP']='0'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.store import connect
        client=TestClient(app)
        c=connect(); cid=c.execute('SELECT id FROM contracts LIMIT 1').fetchone()['id']; c.close()
        path=f'/api/contracts/{cid}/ppm-visits'
        payload={'visit_date':'2026-06-30','status':'Completed','source_type':'engineer_job_sheet','source_reference':'TEST-SYNTHETIC-100','confirmed':True}
        assert client.post(path,json={**payload,'confirmed':False}).status_code==400
        assert client.post(path,json={**payload,'status':'Scheduled','visit_date':'2027-06-30'}).status_code==200
        assert client.post(path,json=payload).status_code==409
        assert client.get(path).json()['last_confirmed_service'] is None
        p2={**payload,'source_reference':'TEST-SYNTHETIC-101'}
        assert client.post(path,json=p2).status_code==200
        assert client.post(path,json=p2).status_code==409
        assert client.post(path,json={**payload,'source_reference':'TEST-SYNTHETIC-102','visit_date':'2035-01-01'}).status_code==400
        result=client.get(path+'?interval_months=6').json()
        assert result['last_confirmed_service']=='2026-06-30'
        assert result['next_due']=='2026-12-30'
        assert len(result['visits'])==2
        assert client.get(path+'?interval_months=5').status_code==400
        print('PASS V13: visit review, provenance, duplicate controls, no future completed visits, last service and next due')

if __name__=='__main__':run()
