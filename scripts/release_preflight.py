"""Read-only preflight for the separate, protected Contracts OS pilot.

A passing result means the private snapshot can be reviewed, NOT that the
system has passed security, desktop Excel, revenue or multiuser acceptance.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.data_readiness import assess_database


def main():
    data = os.getenv("PULSE_DATA_DIR")
    if not data:
        raise SystemExit(
            "ACTION REQUIRED: Specify PULSE_DATA_DIR pointing to your reviewed "
            "private runtime. No customer data is shipped in GitHub."
        )
    folder = Path(data)
    result = assess_database(folder / "contracts.sqlite3", folder / "approved_master.xlsx")
    print("Database:", "OK" if result["database_valid"] else "MISSING / INVALID")
    print("Eight-sheet Master:", "OK" if result["workbook"]["valid"] else "MISSING / INVALID")
    print("Active:", result["contracts"]["active"], "Expired:", result["contracts"]["expired"])
    amount = result["financial_completeness"]
    print("Recorded contract amount coverage:", str(amount["recorded_percent"]) + "%")
    for issue in result["issues"]:
        print("REVIEW:", issue)
    if not result["ready_for_data_review"]:
        raise SystemExit("FAILED: Private data is not ready for an operational review.")
    print("PASS: The snapshot is ready for controlled reconciliation only.")
    print("NOT PRODUCTION APPROVAL: full Excel, security, backups, multiuser and PWA tests remain mandatory.")


if __name__ == "__main__":
    main()
