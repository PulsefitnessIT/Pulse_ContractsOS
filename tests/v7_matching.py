"""V7 evidence-first matching acceptance; use disposable database and no live edits."""
from __future__ import annotations
import os,sys,tempfile,shutil,sqlite3,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from app.matching import candidate_matches,normal_account

def record(cid,number,site,account='',invoice='',start='',expiry=''):
    return {'id':cid,'status':'Active','fields':{'Contract number':number,'Customer / site':site,
      'Site account':account,'Invoice account':invoice,'Start date':start,'Expiry date':expiry}}

items=[record(1,'912345','Example Sports Centre','00000456','00001234','2025-10-27','2027-10-26'),
       record(2,'912346','Example University East Campus','00000200','00001234'),
       record(3,'912347','Other Site with Shared Billing','00000999','00001234')]
strong=candidate_matches({'Contract number':'C912345','Customer / site':'Example Sports Centre','Site account':'00000456'},items)
assert strong['suggested_target_id']==1,strong
assert 'Contract reference matches exactly' in strong['candidates'][0]['reasons']
ambiguous=candidate_matches({'Contract number':'912345','Customer / site':'Completely Different Site'},items)
assert ambiguous['suggested_target_id'] is None,ambiguous
onlynumber=candidate_matches({'Contract number':'912345'},items)
assert onlynumber['suggested_target_id'] is None
invoiceonly=candidate_matches({'Invoice account':'00001234'},items)
assert invoiceonly['candidates']==[],invoiceonly
wrongnumber=candidate_matches({'Contract number':'999999','Customer / site':'Example Sports Centre'},items)
assert wrongnumber['suggested_target_id'] is None,wrongnumber
assert not wrongnumber['candidates'] or wrongnumber['candidates'][0]['warnings']
duplicated=candidate_matches({'Contract number':'912345','Customer / site':'Example Sports Centre'},items+[record(4,'912345','Example Sports Centre North')])
assert duplicated['suggested_target_id'] is None,duplicated
assert normal_account('00000620 (Sage)')=='620'
print('PASS: evidence-first candidate matching, shared-account safety, wrong-site/number protection, duplicate reference handling',flush=True)

with tempfile.TemporaryDirectory() as t:
    shutil.copy2(BASE/'data'/'contracts.sqlite3',Path(t)/'contracts.sqlite3')
    shutil.copy2(BASE/'data'/'approved_master.xlsx',Path(t)/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=t
    os.environ['PULSE_AUTO_BACKUP']='0'
    os.environ['PULSE_OCR_MODE']='off'
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/api/meta').json()['version'].startswith('1.0.0')
    source=client.get('/api/contracts?status=Active&q=914501&limit=3').json()['items'][0]
    match_fields=source['fields'];site=match_fields['Customer / site'];num=match_fields['Contract number']
    text=f'Customer / site,Contract number,Site account\n{site},{num},{match_fields.get("Site account","")}\n'
    uploaded=client.post('/api/imports',files={'file':('v7-match.csv',text.encode(),'text/csv')})
    assert uploaded.status_code==200,uploaded.text
    iid=uploaded.json()['id']
    suggestions=client.get(f'/api/imports/{iid}/proposals/1/matches')
    assert suggestions.status_code==200,suggestions.text
    data=suggestions.json();assert data['candidates'],data
    assert data['suggested_target_id']==source['id'],data
    preview=client.get(f'/api/imports/{iid}/proposals/1/preview').json()
    assert preview['target_id']==source['id'],preview
    accepted=client.post(f'/api/imports/{iid}/approve/1',json={'actor':'V7 QA reviewer','expected_revision':preview['target_revision'],'replace_fields':[]})
    assert accepted.status_code==200,accepted.text
    audit=client.get(f'/api/contracts/{source["id"]}/changes').json()
    stamped=json.loads(audit[0]['after_data'])
    assert stamped['source_filename']=='v7-match.csv' and stamped['source_sha256'] and stamped['source_pages']=='Row 2',stamped
    # Incorrect site under an existing number must be reviewed manually.
    bogus=client.post('/api/imports',files={'file':('v7-wrong-site.csv',f'Customer / site,Contract number\nUnrelated Demonstration Customer,{num}\n'.encode(),'text/csv')})
    assert bogus.status_code==200,bogus.text
    wrongid=bogus.json()['id']
    cands=client.get(f'/api/imports/{wrongid}/proposals/1/matches').json()
    assert cands['suggested_target_id'] is None,cands
    check=client.get(f'/api/imports/{wrongid}/proposals/1/preview').json()
    assert check['create_new'] is True
    bad=client.post(f'/api/imports/{wrongid}/approve/1',json={'actor':'V7 test'})
    assert bad.status_code==409,bad.text
    # New no-match contracts still require a confirm operation; none auto-saved.
    assert client.get('/api/contracts?status=Active&q=Unrelated%20Demonstration%20Customer').json()['total']==0
    assert client.get('/api/export/excel').status_code==200
    print('PASS: API suggestions displayed; corroborated reference preselected; contradictory sites blocked; Excel export intact',flush=True)
