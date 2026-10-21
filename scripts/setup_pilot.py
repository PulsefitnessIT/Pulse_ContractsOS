"""One-time independent pilot configuration. Never modifies PulseFitness.ai."""
from __future__ import annotations
import getpass,os,secrets,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/'pilot_data'
sys.path.insert(0,str(ROOT))
if not PILOT.exists():
    approved=os.environ.get('PULSE_APPROVED_SNAPSHOT_DIR','').strip()
    if not approved:
        raise SystemExit(
            'No approved local contract snapshot is configured. Set '
            'PULSE_APPROVED_SNAPSHOT_DIR to a separately stored, extracted '
            'snapshot and rerun setup; never put customer data in GitHub.'
        )
    from scripts.stage_private_runtime import stage
    stage(approved,PILOT)
from app.data_readiness import assess_database
check=assess_database(PILOT/'contracts.sqlite3',PILOT/'approved_master.xlsx')
if not check['ready_for_data_review']:
    raise SystemExit('Existing pilot files need review: '+'; '.join(check['issues']))
os.environ['PULSE_DATA_DIR']=str(PILOT)
from app.pilot_access import provision_user
settings=ROOT/'pilot_settings.cmd'
if settings.exists():
    print('Existing pilot settings found. Original secret and database remain unchanged.')
else:
    secret=secrets.token_urlsafe(48)
    settings.write_text('@echo off\nset "PULSE_PILOT_MODE=1"\nset "PULSE_AUTO_BACKUP=1"\nset "PULSE_COOKIE_SECURE=0"\nset "PULSE_DATA_DIR=%~dp0pilot_data"\nset "PULSE_SESSION_SECRET='+secret+'"\n',encoding='utf-8')
    print('Created local pilot settings and a separate pilot database.')
print('Create the first pilot administrator (no Microsoft sign-in).')
username=input('Pilot administrator username: ').strip()
password=getpass.getpass('Password (at least 12 characters): ')
if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match')
print('Created user:',provision_user(username,password,'Admin'))
print('Setup complete. Run START_V10_PILOT_LOCAL.bat.')
print('CAUTION: This is LOCAL-only HTTP. For staff on other machines, IT must set up a TLS reverse proxy, set PULSE_COOKIE_SECURE=1 and arrange encrypted off-host backups.')
