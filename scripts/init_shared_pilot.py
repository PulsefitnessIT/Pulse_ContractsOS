"""Create a pilot administrator only after approved private data is present."""
import getpass
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEST = Path(os.environ.get("PULSE_DATA_DIR", str(BASE / "pilot_data")))
if not DEST.is_absolute():
    raise SystemExit("PULSE_DATA_DIR must be an absolute directory")
required = ("contracts.sqlite3", "approved_master.xlsx")
missing = [name for name in required if not (DEST / name).is_file()]
if missing:
    raise SystemExit(
        "Private pilot data is missing: " + ", ".join(missing)
        + ". Follow docs/PRIVATE_DATA_PILOT_SETUP.md before creating accounts."
    )
sys.path.insert(0, str(BASE))
from app.data_readiness import assess_database

report = assess_database(DEST / "contracts.sqlite3", DEST / "approved_master.xlsx")
if not report["ready_for_data_review"]:
    raise SystemExit("Pilot data validation failed: " + "; ".join(report["issues"]))
print("Private records:", report["contracts"]["active"], "active and",
      report["contracts"]["expired"], "expired.")
print("Recorded amount coverage:", report["financial_completeness"]["recorded_percent"],
      "%; incomplete values must not be reported as total contract revenue.")
from app.pilot_access import provision_user

username = input("Administrator username: ").strip()
password = getpass.getpass("Password (12+ characters): ")
if password != getpass.getpass("Confirm password: "):
    raise SystemExit("Passwords do not match")
print("Independent pilot administrator:", provision_user(username, password, "Admin"))
print("Keep private storage and the separate session secret securely backed up.")
