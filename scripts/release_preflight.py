"""Local pilot preflight. This is not a production deployment approval."""
from pathlib import Path
import os,sys,zipfile,sqlite3,shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.store import DB,TEMPLATE
from app.local_ocr import available

def check(name,ok,note=''):
    print(('PASS' if ok else 'ACTION REQUIRED')+'  '+name+((': '+note) if note else ''))

check('Approved Excel template exists',Path(TEMPLATE).is_file())
if Path(TEMPLATE).is_file():
    with zipfile.ZipFile(TEMPLATE) as archive:
        check('Workbook package integrity',archive.testzip() is None)
        check('Eight-sheet workbook present',sum(f.startswith('xl/worksheets/sheet') and f.endswith('.xml') for f in archive.namelist())==8)
check('Local pilot database present',Path(DB).is_file())
if Path(DB).is_file():
    database=sqlite3.connect(DB)
    try:check('Database integrity check',database.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
    finally:database.close()
check('Offline OCR available (optional)',available(),'Install Tesseract or use an approved document-reading service')
check('Local-only runner',"host='127.0.0.1'" in (ROOT/'run.py').read_text(),'No direct LAN/internet exposure')
print('\nPRODUCTION RELEASE IS BLOCKED: shared identity/permissions, central transactional storage, file security, off-site backups, live OCR evaluation and Excel desktop testing remain open.')
