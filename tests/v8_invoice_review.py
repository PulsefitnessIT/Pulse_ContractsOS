"""V8: scanned-invoice review, source lineage, safe persistence and no financial posting."""
from __future__ import annotations
import sys,os,tempfile,shutil,sqlite3,json
from pathlib import Path
import fitz
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from app.invoice_review import analyse_invoice_document

page_data=[
 {'page':1,'source':'Tesseract offline OCR (unverified)','text':'Equipment schedule\nSerial Number 123456789\nWarranty Expiry 27/10/2027'},
 {'page':2,'source':'Embedded PDF text','text':'Invoice 0000023456\nAccount Ref 00001234\nInvoice Date 27/10/2025\nSales Order Ref 0000023235\nWarranty - 5 years, service per annum\nLine Item 260G-AAP 1 £150.00'},
 {'page':3,'source':'Embedded PDF text','text':'Continued table, line item 250G-AAH 1 £10.00'},
 {'page':4,'source':'Tesseract offline OCR (unverified)','text':'Invoice 000004987\nInvoice Date 03/10/2022\nAccount Ref 9001791\nGROSS £2676.37'},
 {'page':5,'source':'Tesseract offline OCR (unverified)','text':'Invoice 000004987\nInvoice Date 03/10/2023\nSales Order Ref 0000008751'},
 {'page':6,'source':'Tesseract offline OCR (unverified)','text':'Invoice Reference unreadable\nInvoice Date blur123'},
]
result=analyse_invoice_document(page_data)
assert len(result['invoices'])==2,result
assert result['invoices'][0]['pages']==[2,3],result
assert result['invoices'][0]['equipment_codes']==['250G-AAH','260G-AAP'],result
assert any(x['field']=='Invoice date' and x['value']=='2025-10-27' for x in result['invoices'][0]['field_candidates']),result
assert any(x['field']=='Account reference' and x['value']=='00001234' for x in result['invoices'][0]['field_candidates']),result
assert not any(x['field']=='Contract amount (£)' for x in result['invoices'][0]['field_candidates']),result
assert any(x['field']=='Invoice date' for x in result['invoices'][1]['conflicts']),result
assert {1,6}.issubset({r['page'] for r in result['unassigned']}),result
print('PASS structured field extraction, asset schedule isolation, conflict detection, no amount inferred')

with tempfile.TemporaryDirectory() as temp:
    target=Path(temp)
    shutil.copy2(BASE/'data'/'contracts.sqlite3',target/'contracts.sqlite3')
    shutil.copy2(BASE/'data'/'approved_master.xlsx',target/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=str(target)
    os.environ['PULSE_AUTO_BACKUP']='0';os.environ['PULSE_OCR_MODE']='off'
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/api/meta').json()['version'].startswith('1.0.0')
    before=client.get('/api/meta').json()['stats']
    original=fitz.open()
    pg=original.new_page()
    content='Invoice 0000023456\nInvoice Date 27/10/2025\nAccount Ref 00001234\nSales Order Ref 0000023235\nLine Item 260G-AAP\nWarranty - 5 Years'
    for i,line in enumerate(content.splitlines()):pg.insert_text((50,70+i*20),line,fontsize=12)
    raw=original.tobytes();original.close()
    up=client.post('/api/imports',files={'file':('v8_evidence_invoice.pdf',raw,'application/pdf')})
    assert up.status_code==200,up.text
    iid=up.json()['id']
    detail=client.get(f'/api/imports/{iid}/invoice-review')
    assert detail.status_code==200,detail.text
    data=detail.json();assert len(data['analysis']['invoices'])==1,data
    assert any(x['value']=='00001234' for x in data['analysis']['invoices'][0]['field_candidates']),data
    review={'invoice_number':'0000023456','invoice_date':'2025-10-27','account_reference':'00001234',
            'contract_reference':'C912346','customer_site':'Example University East Campus',
            'reviewer':'QA Coordinator','notes':'Manually verified handwritten contract reference',
            'confirmed_from_source':True}
    assert client.post(f'/api/imports/{iid}/invoice-review/inv-1',json={**review,'confirmed_from_source':False}).status_code==400
    assert client.post(f'/api/imports/{iid}/invoice-review/inv-999',json=review).status_code==404
    invalid=client.post(f'/api/imports/{iid}/invoice-review/inv-1',json={**review,'invoice_date':'2025-99-17'})
    assert invalid.status_code==400,invalid.text
    saved=client.post(f'/api/imports/{iid}/invoice-review/inv-1',json=review)
    assert saved.status_code==200,saved.text
    assert 'NOT changed' in saved.json()['message']
    read=client.get(f'/api/imports/{iid}/invoice-review').json()
    assert read['verified_reviews']['inv-1']['contract_reference']=='C912346'
    updated=client.post(f'/api/imports/{iid}/invoice-review/inv-1',json={**review,'notes':'Correction approved'});
    assert updated.status_code==200,updated.text
    prepared=client.post(f'/api/imports/{iid}/invoice-review/inv-1/prepare-contract')
    assert prepared.status_code==200,prepared.text
    assert prepared.json()['already_prepared'] is False
    again=client.post(f'/api/imports/{iid}/invoice-review/inv-1/prepare-contract')
    assert again.status_code==200 and again.json()['already_prepared'] is True
    proposed=client.get(f'/api/imports/{iid}').json()['proposals']
    assert len(proposed)==1 and proposed[0]['fields']['Contract number']=='912346'
    assert proposed[0]['approved'] is False
    con=sqlite3.connect(target/'contracts.sqlite3')
    assert con.execute('SELECT count(*) FROM invoice_review_history WHERE import_id=?',(iid,)).fetchone()[0]==2
    assert con.execute('SELECT count(*) FROM invoice_document_reviews WHERE import_id=?',(iid,)).fetchone()[0]==1
    assert con.execute('SELECT count(*) FROM changes WHERE action LIKE ?',('%invoice%',)).fetchone()[0]==0
    con.close()
    assert client.get('/api/meta').json()['stats']==before, 'Evidence review must never change contracts or invoices'
    # A second PDF has a scanned/unreadable invoice reference: staff must be able
    # to record the invoice against the original page rather than invent an OCR value.
    doc=fitz.open();page=doc.new_page();page.insert_text((55,75),'Invoice Reference unreadable\nDocument requires visual review',fontsize=12)
    manual_pdf=doc.tobytes();doc.close()
    manual_import=client.post('/api/imports',files={'file':('V8_manual_reference.pdf',manual_pdf,'application/pdf')})
    assert manual_import.status_code==200,manual_import.text
    mid=manual_import.json()['id']
    manual_data=client.get(f'/api/imports/{mid}/invoice-review').json()
    assert not manual_data['analysis']['invoices'] and manual_data['analysis']['unassigned'],manual_data
    manual_payload={**review,'page_number':1,'invoice_number':'000004987','contract_reference':'C912345'}
    no_verify=client.post(f'/api/imports/{mid}/invoice-review/manual',json={**manual_payload,'confirmed_from_source':False})
    assert no_verify.status_code==400,no_verify.text
    verified=client.post(f'/api/imports/{mid}/invoice-review/manual',json=manual_payload)
    assert verified.status_code==200,verified.text
    manual_proposal=client.post(f'/api/imports/{mid}/invoice-review/manual-p1/prepare-contract')
    assert manual_proposal.status_code==200,manual_proposal.text
    assert client.get(f'/api/imports/{mid}').json()['proposals'][0]['fields']['Contract number']=='912345'
    assert client.get('/api/meta').json()['stats']==before
    print('PASS manual verification fallback for unreadable invoice numbers, staged contract proposal only')
    assert client.get('/api/export/excel').status_code==200
    print('PASS invoice evidence review API, invalid input rejected, audit history, zero Master or invoice ledger updates')

# Optional real scanned fixture, with only two pages to keep the acceptance test repeatable.
source=Path('/mnt/data/20261016135837854.pdf')
from app.local_ocr import available,read_local_scanned_pdf
if source.exists() and available():
    pdf=source.read_bytes();pages,warns=read_local_scanned_pdf(pdf,[3,16]);scan=analyse_invoice_document(pages)
    print('REAL SAMPLE',{'pages':len(pages),'invoice_numbers':[r['detected_invoice_number'] for r in scan['invoices']],
                        'warnings':warns})
    assert any(g['detected_invoice_number']=='0000023456' for g in scan['invoices'])
    assert scan['requires_review'] and not any(k in scan for k in ('approved','contract_updates'))
    print('PASS real Example University scanned invoice read: reference proposed, visually verified before saving')
