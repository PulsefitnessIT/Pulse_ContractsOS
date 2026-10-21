# Pulse Contracts OS – current V13 development handoff (21 October 2026)

## Repository status
- Full source-only V13 code is now present on `feature/pwa-desktop` (PR #3 to `develop` remains draft).
- This additional work is on `feature/real-data-pilot-readiness`, in draft PR #4 targeting `feature/pwa-desktop`.
- Customer databases, approved Master Excel and private planner/catalogue records are **not in GitHub**.
- The real-data offline director demonstration was a separate read-only snapshot; it is not a live data service or the operational PWA.

## Implemented after the director meeting
- Data-free Docker build: removed `COPY data` and explicit build-context exclusions.
- New protected server boot guard: the signed-in pilot will not silently create an empty records database when its approved private data is missing.
- Runtime storage controls: approved `contracts.sqlite3`, `approved_master.xlsx`, optional catalogue and planner JSON are staged outside GitHub using a consistent SQLite backup. Existing destination data cannot be overwritten.
- Shared-pilot admin/local setup scripts now require approved private records and never use code-repository customer files.
- The equipment catalogue and optional planner both load from `PULSE_DATA_DIR`; missing optional planner data produces no invented visits.
- Aggregated financial completeness analysis distinguishes blank, zero, invalid, negative and populated amounts; never claims that recorded amounts are complete revenue.
- Dashboard shows financial data coverage, with a single-click CSV queue of missing/invalid contract amounts for coordinator review. Prices are never auto-filled; CSV cells are protected against formula injection.
- IT-only staging guide and explicit release preflight checks.

## Verified
GitHub source validation and fictional-data tests passed. These include SQLite snapshot staging, no-overwrite behaviour, approved workbook shape validation, record aggregation, missing amounts and CSV safety.

## Not yet complete
- Use the latest approved real Master/database snapshot and reconcile changes made since V12.
- Test the entire workflow against **disposable** copies of actual pilot records.
- Check the eight-sheet Excel export in desktop Microsoft Excel and reconcile contract/invoice financial totals.
- Complete shared HTTPS hosting, PWA installation, user access, backup recovery and two-coordinator UAT.
- Independently review authentication and external hosting before wider release.

**Do not merge this draft into `main` or treat the current application as a verified production deployment.** PulseFitness.ai remains entirely independent; Microsoft sign-in is parked.
