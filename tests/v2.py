import os,tempfile,shutil,sys,json,zipfile
from pathlib import Path
from lxml import etree as ET
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 shutil.copy2(ROOT/'data'/'approved_master.xlsx',Path(td)/'approved_master.xlsx')
 os.environ['PULSE_DATA_DIR']=td
 sys.path.insert(0,str(ROOT))
 from fastapi.testclient import TestClient
 from app.main import app
 from app.excel_io import Q
 client=TestClient(app)
 catalog=client.get('/api/catalogue?q=260G-AAP').json()
 assert any(x['sku']=='260G-AAP' for x in catalog['items']),catalog
 print('CATALOGUE',catalog['total'],catalog['items'][0]['name'])
 # Create two sample contracts mirroring screenshot but not attempting to invent missing terms.
 for data in [
  {'Customer / site':'Example University – Central Sports Centre','Contract number':'912345','Contract / warranty type':'Gold warranty'},
  {'Customer / site':'Example University – East Campus','Contract number':'912346','Contract / warranty type':'Gold warranty','Start date':'2025-10-27','Expiry date':'2027-10-26'}]:
  resp=client.post('/api/contracts',json={'fields':data});assert resp.status_code==200,resp.text
  if data['Contract number']=='912346':contract_id=resp.json()['id']
 link=client.post(f'/api/contracts/{contract_id}/equipment',json={'sku':'260G-AAP','serial_number':'SAMPLE-TEST','quantity':1,'warranty_expiry':'2027-10-26'})
 assert link.status_code==200,link.text
 suggest=client.get(f'/api/contracts/{contract_id}/equipment/field-suggestions').json()
 assert 'Consoles / software' in suggest['suggestions'] and 'Frame / upholstery finish' in suggest['suggestions'],suggest
 print('SUGGESTIONS',suggest['suggestions'])
 eq=client.get(f'/api/contracts/{contract_id}/equipment').json()
 assert eq['count']==1
 csv=client.get('/api/export/equipment');assert csv.status_code==200 and '260G-AAP' in csv.text
 exported=client.get('/api/export/excel');assert exported.status_code==200,exported.text
 out=Path(td)/'export.xlsx';out.write_bytes(exported.content)
 with zipfile.ZipFile(out) as z,zipfile.ZipFile(ROOT/'data'/'approved_master.xlsx') as original:
  assert z.testzip() is None
  sheet=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
  for r in [644,645]:
   row=sheet.xpath(f'.//m:sheetData/m:row[@r="{r}"]',namespaces={'m':Q('row').split('}')[0].strip('{')})[0]
   cells={c.get('r'):c for c in row.findall(Q('c'))}
   styles={col:cells[f'{col}{r}'].get('s') for col in 'ABCFJKPQTU'}
   print('STYLES',r,styles)
   assert styles['A']=='2',styles
   assert styles['B']=='2',styles
   assert styles['J']=='13',styles
   assert styles['K']=='13',styles
   assert styles['Q']=='15',styles
   assert styles['T']=='7',styles
   assert styles['U']=='7',styles
   assert cells['L'+str(r)].find(Q('f')) is not None
  assert z.read('xl/tables/table1.xml') == original.read('xl/tables/table1.xml')
  assert z.read('xl/worksheets/sheet5.xml') == original.read('xl/worksheets/sheet5.xml')
 print('PASS export follows normal row style for new contracts, normal date/currency formats and original reporting preserved')
