"""Read-only operational status for an isolated private Contracts OS pilot."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.data_readiness import assess_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("PULSE_DATA_DIR"),
                        help="Private runtime directory; defaults to PULSE_DATA_DIR")
    parser.add_argument("--json", action="store_true", help="Machine-readable aggregate report")
    args = parser.parse_args()
    if not args.data_dir:
        parser.error("Pass --data-dir or set PULSE_DATA_DIR; no source data defaults are assumed")
    folder = Path(args.data_dir)
    report = assess_database(folder / "contracts.sqlite3", folder / "approved_master.xlsx")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Active contracts:", report["contracts"]["active"])
        print("Expired contracts:", report["contracts"]["expired"])
        print("Recorded amount coverage:", report["financial_completeness"]["recorded_percent"], "%")
        for issue in report["issues"]:
            print("REVIEW:", issue)
        print("Complete recurring revenue cannot be inferred from the recorded amounts.")
    if not report["ready_for_data_review"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
