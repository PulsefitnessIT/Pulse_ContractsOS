"""Non-destructive FastAPI acceptance checks in isolated temporary storage."""
import os,sys,tempfile,shutil,json,zipfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    shutil.copy2(ROOT/'data'/'approved_master.xlsx',Path(temp)/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=temp
    os.environ['PULSE_OCR_MODE']='off'
    sys.path.insert(0,str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    from app.store import connect
    client=TestClient(app)
    x=client.get('/api/meta');assert x.status_code==200,x.text
    s=x.json()['stats'];assert s['active']==642,s;assert s['expired']==8381,s
    print('OK: all original active and expired records imported')
    x=client.get('/api/contracts?status=Active&limit=2');assert x.status_code==200 and x.json()['total']==642
    rid=x.json()['items'][0]['id'];r=client.get('/api/contracts/'+str(rid)).json()
    assert 'Customer / site' in r['fields']
    name=r['fields']['Customer / site']
    res=client.patch('/api/contracts/'+str(rid),json={'fields':{'Next action':'Review pricing with the customer.'},'actor':'Test user','expected_revision':r['revision']})
    assert res.status_code==200,res.text
    changes=client.get(f'/api/contracts/{rid}/changes').json()
    assert changes[0]['action']=='Updated contract'
    print('OK: edit and audit trail')
    res=client.post('/api/contracts',json={'fields':{'Customer / site':'Acceptance test customer','Contract number':'TEST-123','Expiry date':'2027-02-01'}})
    assert res.status_code==200,res.text
    nid=res.json()['id']
    rev=client.get(f'/api/contracts/{nid}').json()['revision']
    x=client.post(f'/api/contracts/{nid}/archive',json={'expected_revision':rev,'reason':'Acceptance test'});assert x.status_code==200,x.text
    assert client.get(f'/api/contracts/{nid}').json()['status']=='Expired'
    print('OK: create and archive, no deletion')
    csv_input='Customer / site,Contract number,Expiry date\nTest CSV Import,NEW-2026,2027-03-01\n'
    res=client.post('/api/imports',files={'file':('contracts.csv',csv_input.encode(),'text/csv')})
    assert res.status_code==200,res.text
    iid=res.json()['id'];assert res.json()['count']==1
    x=client.post(f'/api/imports/{iid}/approve/1');assert x.status_code==200,x.text
    duplicate=client.post('/api/imports',files={'file':('contracts.csv',csv_input.encode(),'text/csv')})
    assert duplicate.json()['duplicate']
    print('OK: file import, review approval and duplicate protection')
    src_pdf=Path('/mnt/data/20261016135837854.pdf')
    if src_pdf.exists():
        uploaded=client.post('/api/imports',files={'file':('Example University.pdf',src_pdf.read_bytes(),'application/pdf')})
        assert uploaded.status_code==200,uploaded.text
        assert uploaded.json()['count']==0,uploaded.text
        assert len(uploaded.json()['evidence']['unread_pages'])==21
        print('OK: real Example University scan correctly requires OCR / human review, no fabricated proposals')
    week=client.post('/api/ledger/weekly',json={'fields':{'Week ending (Friday)':'2026-10-16','Customer / site':'Test Weekly Value','Value recorded (£)':'950.50'}})
    assert week.status_code==200,week.text
    invoice=client.post('/api/ledger/invoices',json={'fields':{'Invoice month':'2026-10-01','Customer / site':'Test Invoice Import','Amount ex VAT (£)':'125.90','Invoice status':'Preview – not confirmed'}})
    assert invoice.status_code==200,invoice.text
    checked=client.patch('/api/ledger/invoices/'+str(invoice.json()['id']),json={'fields':{'Invoice status':'Sent'},'expected_revision':client.get('/api/ledger/invoices/'+str(invoice.json()['id'])).json()['revision']})
    assert checked.status_code==200,checked.text
    assert client.get('/api/reports/monthly?month=2026-10').json()['sent_total']>=125.9
    print('OK: new weekly value, invoice entry and confirmed-sent reporting')
    exp=client.get('/api/export/excel')
    assert exp.status_code==200 and len(exp.content)>1_000_000
    outfile=Path(temp)/'export.xlsx';outfile.write_bytes(exp.content)
    with zipfile.ZipFile(outfile) as f,zipfile.ZipFile(ROOT/'data'/'approved_master.xlsx') as orig:
        assert f.testzip() is None
        assert b'Test Weekly Value' in f.read('xl/worksheets/sheet3.xml')
        assert b'Test Invoice Import' in f.read('xl/worksheets/sheet4.xml')
        assert f.read('xl/worksheets/sheet5.xml')==orig.read('xl/worksheets/sheet5.xml')
        assert f.read('xl/tables/table1.xml')==orig.read('xl/tables/table1.xml')
        sheet=f.read('xl/worksheets/sheet2.xml')
        assert b'IF($A2' in sheet, 'Renewal formulas must survive the export'
        assert b'Review pricing with the customer' in sheet
        assert b'TEST-123' not in sheet # archived row removed from active
        expired=f.read('xl/worksheets/sheet8.xml')
        assert b'TEST-123' in expired
    print('OK: exact template export, unchanged tables and unaffected worksheet XML')
    sales=client.get('/api/reports/sales?start=2026-10-01&manager=All');assert sales.status_code==200
    monthly=client.get('/api/reports/monthly?month=2026-10');assert monthly.status_code==200
    print('OK: sales and monthly reports')
print('\nAll acceptance checks passed.')
