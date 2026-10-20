from pathlib import Path
import subprocess,sys,time
root=Path(__file__).resolve().parents[1]
names=['v4.py','v5_fast.py','v5_documents.py','v5_integration.py','v6_ocr.py',
    'v7_matching.py','v8_invoice_review.py','v9_batch_queue.py',
    'v10_critical.py','v11_growth.py','v11_quality_csv.py']
results=[]
for name in names:
 start=time.monotonic()
 try:
  p=subprocess.run([sys.executable,str(root/'tests'/name)],cwd=root,capture_output=True,text=True,timeout=90)
  status='PASS' if p.returncode==0 else 'FAIL'
  note=(p.stdout or '')[-450:]+(p.stderr or '')[-500:]
 except subprocess.TimeoutExpired:
  status='TIMEOUT';note='Stopped after 90 seconds (not counted as passed)'
 results.append((name,status,round(time.monotonic()-start,1),note))
 print(name,status,results[-1][2],flush=True)
 (root/'V11_ALL_TESTS_RESULT.txt').write_text('\n\n'.join(f'{n}: {s} ({d} seconds)\n{out}' for n,s,d,out in results),encoding='utf-8')
print('COMPLETE',sum(s=='PASS' for _,s,_,_ in results),'/',len(results),flush=True)
