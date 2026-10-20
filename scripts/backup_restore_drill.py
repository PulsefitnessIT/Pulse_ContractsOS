"""Perform a non-destructive local SQLite restore drill in a temporary directory.

This proves database backup readability only. It does not restore source PDFs,
Excel templates, external files or an off-site disaster recovery environment.
"""
from pathlib import Path
import tempfile, sqlite3, sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.store import DB

if not Path(DB).is_file():raise SystemExit('Database not found: start the application once.')
with tempfile.TemporaryDirectory() as folder:
    source=sqlite3.connect(DB)
    target_path=Path(folder)/'restored.sqlite3'
    target=sqlite3.connect(target_path)
    try:
        source.backup(target)
        target.commit()
        assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Restore integrity check failed'
        for table in ('contracts','ledger','imports','equipment','catalogue','changes'):
            original=source.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            restored=target.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            assert original==restored,(table,original,restored)
            print(f'{table}: {restored:,} records verified')
        print('RESTORE DRILL PASS: disposable restored database verified; production data not modified.')
        print('NOTE: PDF uploads and Excel template require separate secure backups and restore testing.')
    finally:
        source.close();target.close()
