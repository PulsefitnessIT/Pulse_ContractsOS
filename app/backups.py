"""Local SQLite online backups for the standalone prototype.

This is not a remote, encrypted, routinely restored disaster recovery solution.
"""
from pathlib import Path
import os,sqlite3,datetime as dt
from .store import DATA,DB


def create_local_backup(force=False):
    folder=Path(DATA)/'backups';folder.mkdir(parents=True,exist_ok=True)
    existing=sorted(folder.glob('pulse_contracts_*.sqlite3'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not force and existing and (dt.datetime.now().timestamp()-existing[0].stat().st_mtime)<24*3600:
        return {'created':False,'filename':existing[0].name,'note':'Latest local backup is less than 24 hours old.'}
    filename='pulse_contracts_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.sqlite3'
    target=folder/filename
    con=sqlite3.connect(DB,timeout=20)
    copy=sqlite3.connect(str(target))
    try:
        con.backup(copy)
        result=copy.execute('PRAGMA integrity_check').fetchone()[0]
        if result!='ok':raise RuntimeError('Backup integrity check failed')
    except Exception:
        copy.close();con.close();target.unlink(missing_ok=True);raise
    copy.close();con.close()
    # Local retention: 14 most recent backups. No backup is deleted by this routine
    # without first having created and verified the newest copy.
    for old in sorted(folder.glob('pulse_contracts_*.sqlite3'),key=lambda p:p.stat().st_mtime,reverse=True)[14:]:
        old.unlink()
    return {'created':True,'filename':filename,'bytes':target.stat().st_size,'integrity':'ok',
      'note':'Local machine only: copy backups to protected, encrypted off-host storage.'}
