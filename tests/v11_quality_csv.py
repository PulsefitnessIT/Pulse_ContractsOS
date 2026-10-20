"""Safely export coordinator-reviewed invoice recognition ground truth."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,sqlite3,csv,io
from app.invoice_quality import invoice_quality_csv

def execute():
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE imports(id INTEGER,filename TEXT,type TEXT,evidence_json TEXT)')
    con.execute('CREATE TABLE invoice_document_reviews(import_id INTEGER,group_id TEXT,review_data TEXT,verified_at TEXT)')
    evidence={'invoice_review':{'invoices':[{'id':'invoice-1','detected_invoice_number':'INV001','pages':[1,2]},
        {'id':'invoice-2','detected_invoice_number':'INV0O2','pages':[3]}]}}
    con.execute('INSERT INTO imports VALUES(?,?,?,?)',(1,'=MALICIOUS.pdf','pdf',json.dumps(evidence)))
    for id,number in [('invoice-1','INV001'),('invoice-2','INV002'),('manual-p4','INV003')]:
        con.execute('INSERT INTO invoice_document_reviews VALUES(?,?,?,?)',
            (1,id,json.dumps({'invoice_number':number}),'2026-10-17T12:00:00'))
    output,count=invoice_quality_csv(con)
    rows=list(csv.reader(io.StringIO(output.lstrip('\ufeff'))))
    assert count==3,(count,rows)
    assert len(rows)==4
    assert rows[1][5]=='Correct'
    assert rows[2][5]=='Corrected by coordinator'
    assert rows[3][5]=='Manually identified'
    assert rows[1][0]=="'=MALICIOUS.pdf"
    con.close()
    print('PASS V11 invoice scorecard: 3 audited entries, correction rates distinguish detected/manual, Excel formula injection protected')
if __name__=='__main__':execute()
