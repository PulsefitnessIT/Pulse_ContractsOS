"""V4 feature acceptance on disposable database and template; no live customer edits."""
import os,sys,tempfile,shutil,io,zipfile,json
from pathlib import Path
from lxml import etree as ET
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    shutil.copy2(ROOT/'data'/'approved_master.xlsx',Path(tmp)/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=tmp
    sys.path.insert(0,str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    from app.master_roundtrip import read_export_id
    from app.excel_io import Q,cell_set
    cl=TestClient(app)
    initial=cl.get('/api/meta').json()
    assert initial['stats']['active']==642,initial
    record=cl.get('/api/contracts?limit=1').json()['items'][0]
    id=record['id'];detail=cl.get('/api/contracts/'+str(id)).json();r=detail['revision']
    edited=cl.patch(f'/api/contracts/{id}',json={'fields':{'Next action':'V4 collaboration test'},'expected_revision':r})
    assert edited.status_code==200,edited.text
    stale=cl.patch(f'/api/contracts/{id}',json={'fields':{'Next action':'STALE OVERWRITE'},'expected_revision':r})
    assert stale.status_code==409,stale.text
    missing=cl.patch(f'/api/contracts/{id}',json={'fields':{'Next action':'Unsafe'}})
    assert missing.status_code==428,missing.text
    assert cl.get('/api/contracts/'+str(id)).json()['fields']['Next action']=='V4 collaboration test'
    # Renewal history and revision token updated.
    now=cl.get(f'/api/contracts/{id}').json()
    renew=cl.post(f'/api/contracts/{id}/renew',json={'start_date':'2027-01-01','expiry_date':'2028-01-01','expected_revision':now['revision']})
    assert renew.status_code==200,renew.text
    history=cl.get(f'/api/contracts/{id}/renewals').json()
    assert len(history)==1 and history[0]['new_expiry']=='2028-01-01',history
    # Download remains an eight-tab template, with workbook snapshot metadata.
    exported=cl.get('/api/export/excel')
    assert exported.status_code==200,exported.text[:200]
    export_id=read_export_id(exported.content);assert export_id
    z=zipfile.ZipFile(io.BytesIO(exported.content));assert z.testzip() is None
    assert len([f for f in z.namelist() if f.startswith('xl/worksheets/sheet') and f.endswith('.xml')])==8
    root=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
    # Locate record by its stable identifier; no row-position assumptions.
    base=cl.get(f'/api/contracts/{id}').json();key=base['row_key']
    import sqlite3
    db=sqlite3.connect(str(Path(tmp)/'contracts.sqlite3'))
    source_row=db.execute('SELECT source_row FROM contracts WHERE id=?',(id,)).fetchone()[0];db.close()
    rows=root.find(Q('sheetData'))
    row=next(r for r in rows.findall(Q('row')) if int(r.get('r'))==source_row)
    cell_set(row,'B'+str(source_row),'Excel edited site note – version-safe')
    altered=ET.tostring(root,xml_declaration=True,encoding='UTF-8')
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as out:
        for part in z.infolist():out.writestr(part,altered if part.filename=='xl/worksheets/sheet2.xml' else z.read(part.filename))
    z.close()
    changed=payload.getvalue()
    preview=cl.post('/api/master/reimport/preview',files={'file':('edited.xlsx',changed,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert preview.status_code==200,preview.text[:400]
    results=preview.json();assert results['count']>=1,results
    idx=next((i for i,x in enumerate(results['items']) if x['key']==key),None)
    assert idx is not None,results
    entry=results['items'][idx]
    assert any(c['field']=='Site notes' for c in entry['changes']),entry
    apply=cl.post('/api/master/reimport/'+results['review_id']+'/apply',json={'approved_items':[idx],'actor':'V4 QA'})
    assert apply.status_code==200,apply.text
    assert cl.get('/api/contracts/'+str(id)).json()['fields']['Site notes']=='Excel edited site note – version-safe'
    assert cl.post('/api/master/reimport/'+results['review_id']+'/apply',json={'approved_items':[idx]}).status_code==409
    # Excel round-trip also handles financial registers using immutable source references.
    archive=zipfile.ZipFile(io.BytesIO(exported.content))
    ledger_sheet=ET.fromstring(archive.read('xl/worksheets/sheet3.xml'))
    ledger_row=next(x for x in ledger_sheet.find(Q('sheetData')).findall(Q('row')) if x.get('r')=='2')
    cell_set(ledger_row,'E2',1555.75)
    new_xml=ET.tostring(ledger_sheet,xml_declaration=True,encoding='UTF-8')
    ledger_payload=io.BytesIO()
    with zipfile.ZipFile(ledger_payload,'w') as output:
        for part in archive.infolist():
            output.writestr(part,new_xml if part.filename=='xl/worksheets/sheet3.xml' else archive.read(part.filename))
    archive.close()
    financial=cl.post('/api/master/reimport/preview',files={'file':('weekly-edit.xlsx',ledger_payload.getvalue())})
    assert financial.status_code==200,financial.text[:300]
    review=financial.json()
    ledger_idx=next(i for i,x in enumerate(review['items']) if x['key']=='Weekly Values::G2')
    assert review['items'][ledger_idx]['action']=='update_ledger'
    assert cl.post('/api/master/reimport/'+review['review_id']+'/apply',json={'approved_items':[ledger_idx]}).status_code==200
    ledger_latest=cl.get('/api/ledger/weekly?limit=150').json()
    assert ledger_latest['total']>=1564
    # Workbook changed after export -> explicit conflict resolution is mandatory.
    prior=cl.get(f'/api/contracts/{id}').json()
    changed_on_server=cl.patch(f'/api/contracts/{id}',json={'fields':{'Site notes':'Newer colleague entry'},'expected_revision':prior['revision']})
    assert changed_on_server.status_code==200
    conflict=cl.post('/api/master/reimport/preview',files={'file':('edited_again.xlsx',changed,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert conflict.status_code==200,conflict.text
    check=conflict.json();ci=next(i for i,x in enumerate(check['items']) if x['key']==key)
    assert any(c['conflict'] for c in check['items'][ci]['changes'])
    rejected=cl.post('/api/master/reimport/'+check['review_id']+'/apply',json={'approved_items':[ci]})
    assert rejected.status_code==409
    approved=cl.post('/api/master/reimport/'+check['review_id']+'/apply',json={'approved_items':[ci],'accepted_conflicts':[f'{ci}:Site notes']})
    assert approved.status_code==200,approved.text
    assert cl.get(f'/api/contracts/{id}').json()['fields']['Site notes']=='Excel edited site note – version-safe'
    unknown=cl.post('/api/master/reimport/preview',files={'file':('untracked.xlsx',(ROOT/'data'/'approved_master.xlsx').read_bytes())})
    assert unknown.status_code==409,unknown.text
    backup=cl.post('/api/admin/backup');assert backup.status_code==200,backup.text
    assert (Path(tmp)/'backups'/backup.json()['filename']).exists()
    print('V4 PASS: version conflict prevention, renewal audit, 8-tab export, Excel round-trip, conflict approval, backup')
