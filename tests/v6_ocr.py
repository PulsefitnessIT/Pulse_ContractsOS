"""V6 real scan check, source preview, and strict no-auto-approval safeguards."""
import os,sys,tempfile,shutil,io,sqlite3
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/mnt/data/20261016135837854.pdf')
if not SOURCE.is_file():
    print('SKIPPED: pilot scan was not available at the reference test path')
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as temp:
    clone=Path(temp)
    shutil.copy2(ROOT/'data'/'contracts.sqlite3',clone/'contracts.sqlite3')
    shutil.copy2(ROOT/'data'/'approved_master.xlsx',clone/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=str(clone)
    os.environ['PULSE_AUTO_BACKUP']='0'
    os.environ['PULSE_OCR_MODE']='local'
    os.environ.pop('PULSE_AZURE_DOC_ENDPOINT',None)
    os.environ.pop('PULSE_AZURE_DOC_KEY',None)
    sys.path.insert(0,str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    from app.local_ocr import available
    assert available(),'Tesseract must be available for this local-pilot test'
    client=TestClient(app)
    baseline=client.get('/api/meta').json()['stats']['active']
    source=fitz.open(str(SOURCE))
    selected=fitz.open()
    selected.insert_pdf(source,from_page=0,to_page=0)
    selected.insert_pdf(source,from_page=15,to_page=15)
    pdf=selected.tobytes();selected.close();source.close()
    response=client.post('/api/imports',files={'file':('Example University_2_page_sample.pdf',pdf,'application/pdf')})
    assert response.status_code==200,response.text[:600]
    data=response.json(); ev=data['evidence']
    print('OCR pages',ev.get('page_sources'), 'invoice refs',ev.get('invoice_references'))
    assert len(ev['unread_pages'])==0,ev
    assert any(x['value']=='0000023456' for x in ev['invoice_references']),ev
    assert ev['reading_method'].endswith('Tesseract OCR')
    assert 'No data was automatically saved' in data['notes']
    page=client.get(f'/api/imports/{data["id"]}/pages/2/preview')
    assert page.status_code==200 and page.content.startswith(b'\x89PNG'),page.status_code
    rotated=client.get(f'/api/imports/{data["id"]}/pages/1/preview?rotate=180')
    assert rotated.status_code==200 and rotated.content.startswith(b'\x89PNG')
    assert page.headers['cache-control']=='no-store'
    assert client.get(f'/api/imports/{data["id"]}/pages/3/preview').status_code==404
    assert client.post('/api/imports',files={'file':('not_pdf.pdf',b'this is not a PDF','application/pdf')}).status_code==400
    assert client.get('/api/meta').json()['stats']['active']==baseline,'OCR must never write contract data'
    assert client.post('/api/imports',files={'file':('again.pdf',pdf,'application/pdf')}).json()['duplicate'] is True
    print('V6 LOCAL OCR PASS: real scanned printed invoice reference found; original source page served; no changes written to Master')

from app.invoice_intelligence import invoice_groups
near=invoice_groups([{'page':1,'text':'Invoice 0000003456'},{'page':2,'text':'Invoice 9000003456'}])
assert near['possible_ocr_conflicts'],near
print('V6 INVOICE SAFETY PASS: similarly read invoice numbers are flagged, not silently merged')
