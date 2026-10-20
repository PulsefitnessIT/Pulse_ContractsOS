"""V5 page grouping and reviewed Excel operations without importing a live workbook."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.invoice_intelligence import invoice_groups
from app.master_roundtrip import diff_workbook
pages=[{'page':1,'text':'Equipment schedule Warranty Expiry Serial Number 1001'},
       {'page':2,'text':'Asset List Serial Number 1002'},
       {'page':3,'text':'Invoice 000003456\nInvoice Date 15/09/2022\nAccount Ref 00001234\nContract C912345'},
       {'page':4,'text':'Invoice 000003456\n260G-AAP Treadmill'},
       {'page':5,'text':'Further details on continuation page'},
       {'page':6,'text':'Invoice number: 000023456\nInvoice Date: 27/10/2025\nContract C912346'}]
result=invoice_groups(pages)
assert [x['invoice_number'] for x in result['groups']]==['000003456','000023456'],result
assert result['unassigned_pages']==[1,2],result
assert result['groups'][0]['pages']==[3,4,5],result
assert result['groups'][0]['account_references']==['00001234'],result
assert result['groups'][0]['continuation_pages']==[5],result
assert result['groups'][1]['invoice_dates']==['27/10/2025'],result
from app.document_ai import reference_proposals,extract_evidence
props,evidence=reference_proposals(pages)
assert len(props)==2 and {'912345','912346'}=={p['fields']['Contract number'] for p in props}
assert '000023456' in [x['value'] for x in evidence['invoice_references']]
# Never confuse an unlabeled number with an invoice or service entitlement.
assert invoice_groups([{'page':1,'text':'Account Ref 0000012345\nContract C912346'}])['groups']==[]
base={'contracts':{'ABC':{'fields':{'Customer / site':'Original Site','Contract number':'123456','Site notes':'Old notes'},'sheet':'Maintenance Database','revision':1}}}
current=[{'id':1,'row_key':'ABC','source_sheet':'Maintenance Database','fields':base['contracts']['ABC']['fields'],'revision':1}]
uploaded={'Maintenance Database':[{'row':3,'fields':{'Customer / site':'New Site','Contract number':'654321','Record ID':''}}],
          'Expired':[{'row':14,'fields':{'Customer / site':'Original Site','Contract number':'123456','Site notes':'Old notes','Record ID':'ABC'}}]}
result=diff_workbook(base,current,uploaded)
assert {x['action'] for x in result['items']}=={'move','new'},result
assert result['conflicts']==0,result
print('V5 FAST PASS: grouped invoices, page provenance, no invented invoice numbers, explicit new and moved Excel records')
