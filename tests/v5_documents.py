"""V5 PDFs: real scanned sample must not be misrepresented as OCR success."""
import os,tempfile,shutil,sys,io
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/mnt/data/20261016135837854.pdf')
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)
    shutil.copy2(ROOT/'data'/'contracts.sqlite3',p/'contracts.sqlite3')
    shutil.copy2(ROOT/'data'/'approved_master.xlsx',p/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=str(p)
    os.environ['PULSE_AUTO_BACKUP']='0'
    os.environ['PULSE_OCR_MODE']='off'
    os.environ.pop('PULSE_AZURE_DOC_ENDPOINT',None)
    os.environ.pop('PULSE_AZURE_DOC_KEY',None)
    sys.path.insert(0,str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    cl=TestClient(app)
    if SOURCE.exists():
        pdf=SOURCE.read_bytes()
        res=cl.post('/api/imports',files={'file':('Example University_sample.pdf',pdf,'application/pdf')})
        assert res.status_code==200,res.text[:1000]
        data=res.json();assert not data['proposals'] and 'Handwritten details have NOT been read' in data['notes'],data
        assert len(data['evidence']['unread_pages'])==21,data
        assert cl.get(f'/api/imports/{data["id"]}/source').content==pdf
        assert cl.post('/api/imports',files={'file':('same.pdf',pdf,'application/pdf')}).json()['duplicate']
        print('REAL SCAN SAFETY PASS: 21 unread pages, no fabricated recognition or contract changes',flush=True)
    d=fitz.open();page=d.new_page();page.insert_text((44,66),'Pulse Invoice\nInvoice 000023456\nInvoice Date: 27/10/2025\nAccount Ref: 00001234\nContract C912346\nSKU 260G-AAP')
    pdf=d.tobytes();d.close()
    resp=cl.post('/api/imports',files={'file':('readable.pdf',pdf,'application/pdf')})
    assert resp.status_code==200,resp.text
    info=resp.json();assert info['evidence']['invoice_groups']['groups'][0]['invoice_number']=='000023456',info
    assert info['evidence']['contract_references'][0]['value']=='912346',info
    imp=cl.get(f'/api/imports/{info["id"]}').json()
    assert '260G-AAP' in imp['catalogue_matches'],list(imp['catalogue_matches'])
    print('DIGITAL PDF PASS: invoice group, contract evidence, and exact equipment catalogue match (nothing automatically approved)',flush=True)
