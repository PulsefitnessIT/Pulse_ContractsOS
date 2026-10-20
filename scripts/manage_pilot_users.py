"""From project root: python scripts/manage_pilot_users.py add <username> --role Coordinator"""
import sys,argparse,getpass
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.pilot_access import provision_user
parser=argparse.ArgumentParser(description='Create a separate Contracts OS pilot user')
parser.add_argument('action',choices=['add']);parser.add_argument('username');parser.add_argument('--role',choices=['Admin','Coordinator','Viewer'],default='Coordinator')
args=parser.parse_args()
pw=getpass.getpass('New password (at least 12 characters): ')
confirm=getpass.getpass('Confirm password: ')
if pw!=confirm:raise SystemExit('Passwords do not match')
print('Created / updated:',provision_user(args.username,pw,args.role),'('+args.role+')')
