"""One-time setup for a separately hosted, single-instance pilot.

Run with PULSE_DATA_DIR pointing to the host-mounted pilot volume. This does not
contact MongoDB, Emergent, Microsoft or PulseFitness.ai.
"""
import getpass, os, shutil, sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
DEST=Path(os.environ.get('PULSE_DATA_DIR',str(BASE/'pilot_data')))
if not DEST.is_absolute():raise SystemExit('PULSE_DATA_DIR must be an absolute path')
DEST.mkdir(parents=True,exist_ok=True)
for name in ['contracts.sqlite3','approved_master.xlsx','equipment_catalogue.json']:
    if not (DEST/name).exists():
        shutil.copy2(BASE/'data'/name,DEST/name)
        print('Initialised:',name)
    else:
        print('Preserved existing:',name)
sys.path.insert(0,str(BASE))
from app.pilot_access import provision_user
username=input('Administrator login name: ').strip()
password=getpass.getpass('Strong password (12+ characters): ')
if password != getpass.getpass('Confirm password: '): raise SystemExit('Passwords do not match')
print('Pilot administrator:', provision_user(username,password,'Admin'))
print('Pilot data:',DEST,'\nKeep this directory and the session signing secret securely backed up.')
