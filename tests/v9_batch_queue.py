"""V9 regression: multiple document intake, review work queue, safe CSV export."""
import tempfile,shutil,os,sys,json,csv,io,sqlite3
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.import_queue import build_review_queue,queue_csv

# Pure queue logic: conflicting readings are review tasks; verified is source-only.
rows=[{'id':11,'filename':'Invoice QA.pdf','type':'pdf','status':'Awaiting review',
'evidence_json':json.dumps({'invoice_review':{'invoices':[{'id':'inv-1','pages':[2,3],'detected_invoice_number':'0000023456',
 'conflicts':[{'field':'Invoice date'}], 'field_candidates':[]}], 'unassigned':[{'page':1,'reason':'Possible equipment register / asset schedule'},
 {'page':4,'reason':'Possible invoice with unreadable reference'}]},'page_sources':[{'page':2,'source':'Tesseract offline OCR'}]})}]
queue=build_review_queue(rows,[])
assert queue['counts']=={'Needs review':2,'Source verified':0,'Reference only':1},queue
assert len(queue['items'])==3,queue
assert 'conflicting field reading' in queue['items'][0]['reason']
verified=build_review_queue(rows,[{'import_id':11,'group_id':'inv-1'},{'import_id':11,'group_id':'manual-p4'}])
assert verified['counts']=={'Needs review':0,'Source verified':2,'Reference only':1},verified
malicious=build_review_queue([{**rows[0],'filename':'=HYPERLINK("test")'}],[])
assert "'=HYPERLINK" in queue_csv(malicious)
print('PASS queue triage, source-check updates, reference-only schedule, safe Excel CSV')

with tempfile.TemporaryDirectory() as folder:
    dest=Path(folder)
    shutil.copy2(ROOT/'data'/'contracts.sqlite3',dest/'contracts.sqlite3')
    shutil.copy2(ROOT/'data'/'approved_master.xlsx',dest/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=str(dest);os.environ['PULSE_AUTO_BACKUP']='0';os.environ['PULSE_OCR_MODE']='off'
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/api/meta').json()['version'].startswith('1.0.0')
    before=client.get('/api/meta').json()['stats']
    excel_bytes=(dest/'approved_master.xlsx').read_bytes()
    doc=fitz.open();page=doc.new_page();
    for n,line in enumerate(['Invoice 0000023456','Invoice Date 27/10/2025','Account Ref 00001234',
                  'Sales Order Ref 0000023235','260G-AAP 1 £155.00']):page.insert_text((30,75+n*25),line,fontsize=14)
    pdf1=doc.tobytes();doc.close()
    doc=fitz.open();page=doc.new_page();page.insert_text((50,70),'Invoice 0000034444\nInvoice Date 04/11/2025',fontsize=13)
    pdf2=doc.tobytes();doc.close()
    files=[('files',('test-invoice-1.pdf',pdf1,'application/pdf')),
           ('files',('test-invoice-2.pdf',pdf2,'application/pdf')),
           ('files',('not-a-pdf.pdf',b'bad fake content','application/pdf'))]
    r=client.post('/api/imports/batch',files=files)
    assert r.status_code==200,r.text
    d=r.json();assert d['processed']==2 and d['failed']==1,d
    first=d['results'][0]['id']
    task=client.get('/api/imports/review-queue')
    assert task.status_code==200,task.text
    items=[x for x in task.json()['items'] if x['import_id']==first and x['type']=='Invoice']
    assert items and items[0]['status']=='Needs review',task.json()
    # Repeat exact document: no duplicate row.
    dup=client.post('/api/imports/batch',files=[('files',('same-invoice.pdf',pdf1,'application/pdf'))]).json()
    assert dup['results'][0]['status']=='Already uploaded',dup
    # Verify source and ensure queue reflects staff check without altering master.
    review={'invoice_number':'0000023456','invoice_date':'2025-10-27',
            'account_reference':'00001234','contract_reference':'C912346',
            'customer_site':'Example University', 'reviewer':'QA Coordinator',
            'notes':'Checked printed details and handwritten reference','confirmed_from_source':True}
    saved=client.post(f'/api/imports/{first}/invoice-review/inv-1',json=review)
    assert saved.status_code==200,saved.text
    task=client.get('/api/imports/review-queue?status=Source%20verified').json()
    assert any(x['import_id']==first and x['status']=='Source verified' for x in task['items']),task
    bad=client.get('/api/imports/review-queue?status=SuperVerified')
    assert bad.status_code==400,bad.text
    sheet=client.get('/api/imports/review-queue.csv')
    assert sheet.status_code==200 and 'text/csv' in sheet.headers['content-type']
    parsed=list(csv.reader(io.StringIO(sheet.text.lstrip('\ufeff'))));assert len(parsed)>2,parsed
    too_many=client.post('/api/imports/batch',files=[('files',(f'x{i}.pdf',pdf1,'application/pdf')) for i in range(13)])
    assert too_many.status_code==400,too_many.text
    assert client.get('/api/meta').json()['stats']==before,'Invoice batch import must never update contract or ledger totals'
    assert (dest/'approved_master.xlsx').read_bytes()==excel_bytes,'Source Excel template mutated'
    print('PASS batch API, per-file failures, duplicate prevention, verified queue updates, CSV export, limits, unchanged Master')
