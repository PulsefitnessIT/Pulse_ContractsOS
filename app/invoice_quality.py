"""Measured import quality on visually verified invoice groups only.

Not a general OCR accuracy score; the denominator excludes unreviewed invoices.
"""
from __future__ import annotations
import json

def invoice_quality(con):
    totals={'pdf_documents':0,'scanned_pages_with_evidence':0,'verified_invoices':0,
            'verified_from_detected_group':0,'detected_number_correct':0,
            'detected_number_corrected':0,'manually_identified_invoices':0,
            'source_pages_unassigned':0}
    groups={}
    for row in con.execute("SELECT id,evidence_json FROM imports WHERE type='pdf'"):
        totals['pdf_documents']+=1
        try:evidence=json.loads(row['evidence_json'] or '{}')
        except (ValueError,TypeError):continue
        review=evidence.get('invoice_review') or {}
        totals['scanned_pages_with_evidence']+=int(review.get('processed_pages') or 0)
        totals['source_pages_unassigned']+=len(review.get('unassigned') or [])
        for g in review.get('invoices',[]):groups[(row['id'],g['id'])]=g.get('detected_invoice_number','')
    for row in con.execute('SELECT import_id,group_id,review_data FROM invoice_document_reviews'):
        try:d=json.loads(row['review_data'])
        except (ValueError,TypeError):continue
        if not d.get('invoice_number'):continue
        totals['verified_invoices']+=1
        if row['group_id'].startswith('manual-p'):
            totals['manually_identified_invoices']+=1
            continue
        totals['verified_from_detected_group']+=1
        detected=str(groups.get((row['import_id'],row['group_id']),d.get('original_detected_invoice_number','')))
        if detected==str(d['invoice_number']):totals['detected_number_correct']+=1
        else:totals['detected_number_corrected']+=1
    n=totals['verified_from_detected_group']
    totals['number_accuracy_among_verified_detected_invoices']=round(totals['detected_number_correct']/n*100,1) if n else None
    totals['scope']='Only human-verified invoice groups are measured. Handwriting, totals, equipment, and full-document coverage require separately labelled tests.'
    return totals


def invoice_quality_csv(con):
    """Export an auditable, Excel-safe quality sample from existing staff reviews.

    No values are accepted as OCR truth until a staff member has visually
    confirmed them in the invoice-document review flow.
    """
    import csv,io
    evidence={}
    imports={}
    for r in con.execute("SELECT id,filename,evidence_json FROM imports WHERE type='pdf'"):
        imports[r['id']]=r['filename']
        try:payload=json.loads(r['evidence_json'] or '{}')
        except (ValueError,TypeError):payload={}
        for g in (payload.get('invoice_review') or {}).get('invoices',[]):
            evidence[(r['id'],g['id'])]={'detected':str(g.get('detected_invoice_number') or ''),
                'pages':','.join(str(x) for x in (g.get('pages') or []))}
    buf=io.StringIO(newline='')
    writer=csv.writer(buf)
    writer.writerow(['Document','Invoice group','Page(s)','Originally detected invoice number',
        'Staff-verified invoice number','Result','Review date'])
    count=0
    for r in con.execute('SELECT import_id,group_id,review_data,verified_at FROM invoice_document_reviews ORDER BY verified_at,import_id'):
        if r['import_id'] not in imports:continue
        try:data=json.loads(r['review_data'] or '{}')
        except (ValueError,TypeError):continue
        verified=str(data.get('invoice_number') or '')
        if not verified:continue
        original=evidence.get((r['import_id'],r['group_id']),{})
        detected=original.get('detected','')
        state=('Manually identified' if r['group_id'].startswith('manual-p')
               else 'Correct' if detected==verified else 'Corrected by coordinator')
        raw=[imports[r['import_id']],r['group_id'],original.get('pages',''),detected,verified,state,r['verified_at']]
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in raw])
        count+=1
    return '\ufeff'+buf.getvalue(),count
