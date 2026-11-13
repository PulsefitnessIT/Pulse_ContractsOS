"""Generate a complete local pilot recovery bundle (not an off-site backup).

Run from an appropriate scheduler and copy the resulting ZIP to encrypted off-host storage.
No live database writes; SQLite online-backup API is used for consistency in WAL mode.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, shutil, sqlite3, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.store import DB,DATA,TEMPLATE


def create_bundle():
    base=Path(DATA)
    if not Path(DB).exists():raise RuntimeError('No database available yet')
    dest=Path(os.environ.get('PULSE_BACKUP_OUTPUT', str(base/'recovery_bundles')))
    dest.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    output=dest/('pulse_pilot_recovery_'+stamp+'.zip')
    manifest={'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'files':{},
       'warning':'Sensitive customer data. Store on encrypted, access-controlled off-host storage.'}
    with tempfile.TemporaryDirectory() as tmp:
        snapshot=Path(tmp)/'contracts.sqlite3'
        source=sqlite3.connect(DB,timeout=30);target=sqlite3.connect(snapshot)
        try:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite snapshot is corrupt')
        finally:source.close();target.close()
        inputs=[(snapshot,'contracts.sqlite3'),(Path(TEMPLATE),'approved_master.xlsx')]
        catalogue=base/'equipment_catalogue.json'
        if catalogue.exists():inputs.append((catalogue,'equipment_catalogue.json'))
        upload_dir=base/'uploads'
        if upload_dir.is_dir():
            for file in sorted(upload_dir.iterdir()):
                if file.is_file() and not file.is_symlink():inputs.append((file,'uploads/'+file.name))
        # Signed agreements are external evidence, not just database metadata.
        # Include them in the complete recovery bundle with SHA-256 manifest.
        signed_dir=base/'private_signed_agreements'
        if signed_dir.is_dir():
            for signed in sorted(signed_dir.iterdir()):
                if signed.is_file() and not signed.is_symlink() and signed.suffix.lower()=='.pdf':
                    inputs.append((signed,'private_signed_agreements/'+signed.name))
        # Templates used to prepare agreements and Sicon exports must survive a
        # restore alongside the contract/setup history, never travel via GitHub.
        templates=base/'approved_sicon_templates'
        if templates.is_dir() and not templates.is_symlink():
            permitted={'maintenance_agreement_approved.pdf','sicon_contract_import.xlsx','sicon_equipment_import.xlsx'}
            for name in sorted(permitted):
                original=templates/name
                if original.is_file() and not original.is_symlink():
                    inputs.append((original,'approved_sicon_templates/'+name))
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for file,name in inputs:
                if not file.exists():raise RuntimeError('Required recovery file missing: '+str(file))
                raw=file.read_bytes();manifest['files'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                z.writestr(name,raw)
            z.writestr('manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as z:
        if z.testzip():raise RuntimeError('Recovery bundle archive is corrupted')
        for name,details in manifest['files'].items():
            raw=z.read(name)
            if len(raw)!=details['bytes'] or hashlib.sha256(raw).hexdigest()!=details['sha256']:
                raise RuntimeError('Recovery bundle checksum mismatch: '+name)
    print('Recovery bundle created and checksums verified:',output)
    print('Files:',len(manifest['files']),', bytes:',output.stat().st_size)
    print('REMINDER: Copy to encrypted off-host storage and test a full restore.')
    return output


if __name__=='__main__':create_bundle()
