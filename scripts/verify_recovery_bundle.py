"""Non-destructive restore drill for the entire pilot recovery bundle."""
from __future__ import annotations
import argparse,hashlib,json,sqlite3,tempfile,zipfile
from pathlib import Path


def verify(bundle):
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(bundle) as z:
        if z.testzip():raise RuntimeError('ZIP failed validation')
        manifest=json.loads(z.read('manifest.json'))
        for name,expected in manifest['files'].items():
            content=z.read(name)
            if len(content)!=expected['bytes'] or hashlib.sha256(content).hexdigest()!=expected['sha256']:
                raise RuntimeError('Checksum mismatch: '+name)
            output=Path(tmp)/name;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(content)
        con=sqlite3.connect(str(Path(tmp)/'contracts.sqlite3'))
        try:
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            names={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {'contracts','ledger','imports','changes','equipment'}<=names
            print('Recovery verified:',', '.join(f'{tbl}={con.execute("SELECT COUNT(*) FROM "+tbl).fetchone()[0]}' for tbl in ('contracts','ledger','imports','equipment')))
        finally:con.close()
    print('FULL BUNDLE RESTORE DRILL PASSED – all extracted into a disposable directory')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle');verify(p.parse_args().bundle)
