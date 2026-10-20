"""V3 importer acceptance checks on a disposable copy of the database."""
from __future__ import annotations
import os,sys,tempfile,shutil,json,io,zipfile
from pathlib import Path
import fitz
BASE=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    shutil.copy2(BASE/'data'/'approved_master.xlsx',Path(tmp)/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=tmp
    os.environ['PULSE_OCR_MODE']='off'
    os.environ.pop('PULSE_AZURE_DOC_ENDPOINT',None)
    os.environ.pop('PULSE_AZURE_DOC_KEY',None)
    sys.path.insert(0,str(BASE))
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/api/meta').json()['document_ai_configured'] is False
    # Extract PDF text conservatively: contract reference C912346 is not the invoice number.
    doc=fitz.open();page=doc.new_page()
    page.insert_text((72,72), 'Pulse Fitness Invoice\nInvoice number: 000023456\nContract: C912346\nStock: 260G-AAP\nAccount Ref: 00001234')
    pdf=doc.tobytes();doc.close()
    uploaded=client.post('/api/imports',files={'file':('sample_invoice.pdf',pdf,'application/pdf')});assert uploaded.status_code==200,uploaded.text
    obj=uploaded.json();iid=obj['id']; assert obj['count']==1,obj
    evidence=obj['evidence'];assert evidence['contract_references'][0]['value']=='912346',evidence
    assert evidence['invoice_references'][0]['value']=='000023456',evidence
    assert any(x['value']=='260G-AAP' for x in evidence['equipment_codes']),evidence
    assert client.post('/api/imports',files={'file':('another_name.pdf',pdf,'application/pdf')}).json()['duplicate']
    assert client.get(f'/api/imports/{iid}/source').content==pdf
    prop_id=obj['proposals'][0]['id']
    preview=client.get(f'/api/imports/{iid}/proposals/{prop_id}/preview').json()
    assert preview['create_new'] is True
    attempt=client.post(f'/api/imports/{iid}/approve/{prop_id}',json={});assert attempt.status_code==409,attempt.text
    amended=client.patch(f'/api/imports/{iid}/proposals/{prop_id}',json={'fields':{
        'Contract number':'912346','Customer / site':'Test Education Site','Contract / warranty type':'Gold warranty',
        'Start date':'2025-10-27','Expiry date':'2027-10-26'},'target_contract_id':None})
    assert amended.status_code==200,amended.text
    preview=client.get(f'/api/imports/{iid}/proposals/{prop_id}/preview').json();assert preview['create_new']
    approved=client.post(f'/api/imports/{iid}/approve/{prop_id}',json={'replace_fields':[]});assert approved.status_code==200,approved.text
    cid=approved.json()['contract_id']
    assert client.post(f'/api/imports/{iid}/approve/{prop_id}',json={}).status_code==409
    existing=client.get('/api/contracts/'+str(cid)).json()
    assert existing['fields']['Expiry date']=='2027-10-26'
    # A product code from a source can be explicitly linked only to a chosen contract.
    linked=client.post(f'/api/imports/{iid}/equipment-link',json={'contract_id':cid,'sku':'260G-AAP','serial_number':'V3-EXAMPLE-0001','quantity':1,'invoice_reference':'000023456'})
    assert linked.status_code==200,linked.text
    assert client.post(f'/api/imports/{iid}/equipment-link',json={'contract_id':cid,'sku':'260G-AAP','serial_number':'V3-EXAMPLE-0001','quantity':1,'invoice_reference':'000023456'}).status_code==409
    assert client.post(f'/api/imports/{iid}/equipment-link',json={'contract_id':cid,'sku':'OTHER-NO-SOURCE','quantity':1}).status_code==409
    assert client.get(f'/api/contracts/{cid}/equipment').json()['count']==1
    assert client.get(f'/api/imports/{iid}').json()['evidence']['equipment_codes'][0]['value']=='260G-AAP'
    # Another file proposes a different expiry date. It must be explicitly reviewed.
    candidate=client.post('/api/imports',files={'file':('different.csv',b'Customer / site,Contract number,Expiry date\nTest Education Site,912346,2028-10-26\n','text/csv')})
    assert candidate.status_code==200,candidate.text
    second=candidate.json()['id']; prev=client.get(f'/api/imports/{second}/proposals/1/preview').json()
    assert prev['target_id']==cid,prev
    assert any(x['field']=='Expiry date' and x['conflict'] for x in prev['fields'])
    assert client.post(f'/api/imports/{second}/approve/1',json={'replace_fields':[],'expected_revision':prev['target_revision']}).status_code==409
    assert client.post(f'/api/imports/{second}/approve/1',json={'replace_fields':['Expiry date'],'expected_revision':prev['target_revision']}).status_code==200
    assert client.get('/api/contracts/'+str(cid)).json()['fields']['Expiry date']=='2028-10-26'
    # Staff can add a proposal manually after a scanned PDF with no recognised text.
    blank=fitz.open();blank.new_page();scan=blank.tobytes();blank.close()
    uploaded=client.post('/api/imports',files={'file':('no_ocr.pdf',scan,'application/pdf')}).json()
    assert uploaded['count']==0 and 'scanned' in uploaded['notes'].lower(),uploaded
    manual=client.post(f'/api/imports/{uploaded["id"]}/proposals',json={'fields':{'Customer / site':'Manual Site','Contract number':'912345'}})
    assert manual.status_code==200,manual.text
    assert client.get(f'/api/imports/{uploaded["id"]}').json()['proposals'][0]['source']=='Coordinator review'
    # The exact Excel template survives with a new row in normal font/date format.
    file=client.get('/api/export/excel');assert file.status_code==200
    z=zipfile.ZipFile(io.BytesIO(file.content))
    assert z.testzip() is None
    assert len([x for x in z.namelist() if x.startswith('xl/worksheets/sheet') and x.endswith('.xml')])==8
    from lxml import etree as ET
    from app.excel_io import Q
    root=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
    rec=root.xpath('.//m:sheetData/m:row[@r="644"]',namespaces={'m':Q('row')[1:].split('}')[0]})[0]
    styles={c.get('r'):c.get('s') for c in rec.findall(Q('c'))}
    assert styles['A644']=='2' and styles['J644']=='13' and styles['T644']=='7',styles
    assert 'Test Education Site' in str(z.read('xl/worksheets/sheet2.xml'))
    print('PASS: PDF evidence extraction, invoice separation, duplicates, manual review, conflict approval and Excel export')
