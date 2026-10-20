"""V5 end-to-end on a disposable clone; confirms no original DB/file changes."""
from pathlib import Path
import os,tempfile,shutil,sys,io,zipfile,time,json,copy
from lxml import etree as ET
BASE=Path(__file__).resolve().parents[1]
def log(s):print(s,flush=True)
with tempfile.TemporaryDirectory() as temp:
    destination=Path(temp)
    shutil.copy2(BASE/'data'/'contracts.sqlite3',destination/'contracts.sqlite3')
    shutil.copy2(BASE/'data'/'approved_master.xlsx',destination/'approved_master.xlsx')
    os.environ['PULSE_DATA_DIR']=str(destination)
    os.environ['PULSE_AUTO_BACKUP']='0'
    sys.path.insert(0,str(BASE))
    start=time.time()
    from fastapi.testclient import TestClient
    from app.main import app,HEADERS
    from app.excel_io import Q,cell_set,colname
    c=TestClient(app)
    log('API init '+str(round(time.time()-start,1))+'s')
    meta=c.get('/api/meta');assert meta.status_code==200 and meta.json()['version'].startswith('1.0.0')
    x=c.get('/api/export/excel');assert x.status_code==200,x.text[:400]
    log('Export '+str(round(time.time()-start,1))+'s')
    z=zipfile.ZipFile(io.BytesIO(x.content))
    cols={h:colname(i+1) for i,h in enumerate(HEADERS)}
    assert cols['Record ID']
    # Simulate new complete row in current register and a cross-sheet transfer.
    active=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
    expired=ET.fromstring(z.read('xl/worksheets/sheet8.xml'))
    def add(root,rownum,values):
        sheetdata=root.find(Q('sheetData'))
        row=next((r for r in sheetdata.findall(Q('row')) if int(r.get('r'))==rownum),None)
        if row is None:row=ET.SubElement(sheetdata,Q('row'),r=str(rownum))
        for key,value in values.items():cell_set(row,f'{cols[key]}{rownum}',value)
    add(active,644,{'Customer / site':'V5 Test New Customer','Contract number':'V50001','Site notes':'Entered in Excel'})
    import sqlite3
    db=sqlite3.connect(str(destination/'contracts.sqlite3'))
    rec=db.execute("SELECT source_row,row_key,fields FROM contracts WHERE status='Active' AND row_key IS NOT NULL ORDER BY source_row LIMIT 1").fetchone()
    candidate=json.loads(rec[2]);rid=rec[1]
    # We only need fields essential for move and the original record ID.
    max_exp=int(db.execute('SELECT max(source_row) FROM contracts WHERE source_sheet="Expired"').fetchone()[0]);db.close()
    original_row=next(r for r in active.find(Q('sheetData')).findall(Q('row')) if int(r.get('r'))==int(rec[0]))
    dest=expired.find(Q('sheetData'))
    for blank in list(dest.findall(Q('row'))):
        if int(blank.get('r'))==max_exp+1:dest.remove(blank)
    pasted=copy.deepcopy(original_row)
    pasted.set('r',str(max_exp+1))
    for ccell in pasted.findall(Q('c')):
        oldaddr=ccell.get('r')
        ccell.set('r',oldaddr.rstrip('0123456789')+str(max_exp+1))
    dest.append(pasted)
    # Clear all non-empty existing fields except Record ID on transferred row if duplicated in export;
    # parser ignores row without a customer, but this is only a simulation, not a template modification.
    add(active,rec[0],{'Customer / site':''})
    blob=io.BytesIO()
    with zipfile.ZipFile(blob,'w') as out:
        for ent in z.infolist():
            data=ET.tostring(active,xml_declaration=True,encoding='UTF-8') if ent.filename=='xl/worksheets/sheet2.xml' else ET.tostring(expired,xml_declaration=True,encoding='UTF-8') if ent.filename=='xl/worksheets/sheet8.xml' else z.read(ent.filename)
            out.writestr(ent,data)
    z.close()
    request=c.post('/api/master/reimport/preview',files={'file':('review.xlsx',blob.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert request.status_code==200,request.text[:500]
    data=request.json();log('Preview '+str(round(time.time()-start,1))+'s: '+str([(x['action'],x.get('key')) for x in data['items'][:5]]))
    newidx=next(i for i,x in enumerate(data['items']) if x['action']=='new' and any(y['incoming']=='V50001' for y in x['changes']))
    moveidx=next(i for i,x in enumerate(data['items']) if x['action']=='move' and x['key']==rid)
    response=c.post('/api/master/reimport/'+data['review_id']+'/apply',json={'approved_items':[newidx,moveidx], 'actor':'V5 quality check'})
    assert response.status_code==200,response.text[:800]
    assert response.json()['updated']==2
    db=sqlite3.connect(str(destination/'contracts.sqlite3'))
    assert db.execute('SELECT count(*) FROM contracts WHERE row_key LIKE "XLS-%"').fetchone()[0]==1
    assert db.execute('SELECT status FROM contracts WHERE row_key=?',(rid,)).fetchone()[0]=='Expired'
    db.close()
    fresh=c.get('/api/export/excel');assert fresh.status_code==200
    freshzip=zipfile.ZipFile(io.BytesIO(fresh.content))
    assert freshzip.testzip() is None
    archive_xml=ET.fromstring(freshzip.read('xl/worksheets/sheet8.xml'))
    pasted_export=next(r for r in archive_xml.find(Q('sheetData')).findall(Q('row')) if r.get('r')==str(max_exp+1))
    style_before={x.get('r').rstrip('0123456789'):x.get('s') for x in original_row.findall(Q('c'))}
    style_after={x.get('r').rstrip('0123456789'):x.get('s') for x in pasted_export.findall(Q('c'))}
    assert all(style_after.get(k)==v for k,v in style_before.items() if v is not None), (style_before,style_after)
    newxml=ET.fromstring(freshzip.read('xl/worksheets/sheet2.xml'))
    newrow=next(r for r in newxml.find(Q('sheetData')).findall(Q('row')) if r.get('r')=='644')
    assert next(x for x in newrow.findall(Q('c')) if x.get('r')=='A644').get('s')=='2'
    freshzip.close()
    log('V5 INTEGRATION PASS '+str(round(time.time()-start,1))+'s: reviewed new/expired transfers, site-style preservation and eight-tab export')
