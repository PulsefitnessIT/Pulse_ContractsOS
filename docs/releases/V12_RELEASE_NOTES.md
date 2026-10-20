# Pulse Contracts OS V12 – Reporting and PPM reconciliation

## Scope and independence

This release remains a standalone, local independent pilot, with no connection to or changes in live PulseFitness.ai or MongoDB. Microsoft sign-in is not required. The eight-tab approved Excel Master remains the original export template. Coordinator approval is necessary before service-planner dates are written to contract records.

## 1. Quarterly sales-manager reports

- Select a quarter and choose **Reports for every manager** once.
- The system produces a ZIP containing one UTF-8 Excel-compatible CSV per assigned manager, with customer/site, contract number, expiry date, cover, region, invoice code and next action.
- A README explains the quarter and totals. Manager assignment is taken from the current active contract record.
- Unassigned and regional placeholder owners receive separate lists for assignment, **not automatic distribution**.
- No emails are sent automatically. Staff can open the individual files in Excel and email them after reviewing the recipient list.

## 2. Weekly value reporting

- Filters for reporting year, calendar month and ISO week have been added.
- Weeks follow the ISO Monday–Sunday convention; the individual weekly values are still recorded against the original weekly ending dates.
- Selection totals are recalculated from all matching entries, including those not shown on the first page.

## 3. Compact contract register

- The desktop view now shows customer/site, contract number, type, expiry, sales manager and renewal state in a compact fixed-width table.
- All the existing detail fields remain in the contract editor and in the Excel Master export.
- On narrow mobile screens, controlled sideways scrolling may still be necessary.

## 4. Preventative maintenance planner assessment

Source: **DJ Service Planner March 2020.xlsx**. Although the title says March 2020, it contains many service dates in 2025–2026 and monthly planning columns spanning years.

- 386 populated rows and 2,130 populated month/notes cells imported as **source evidence**.
- Proposed matches against 642 active contracts: 260 strong, 90 potential, 16 ambiguous and 20 unmatched.
- 220 strong proposed matches include an available last-service date.
- Original monthly notes and planning markings are not automatically interpreted as completed maintenance.
- A reviewer must explicitly confirm a strong contract match and completed visit date before updating `Last service recorded`.
- The platform blocks duplicate approvals, stale record revisions, future completion dates and replacement of a more recent last-service date with an older one.
- Approval creates a permanent source-linked audit entry in the pilot database.
- The separate `Pulse_Service_Planner_Contract_Match_Review.xlsx` report retains all 386 planner rows and all 2,130 monthly-note entries for the coordinators.

**No service dates were bulk-written into the released pilot contracts.**

## 5. Public business contact research

- Added a contact research queue download containing each active contract/site, county, sales manager and an official-contact search link.
- Added a public contact panel in each contract record for business telephone, email, website, departmental contact and a public source URL.
- No contact details are fabricated. The source URL is mandatory before saving contact details.
- **Fully automated AI-led enrichment of all sites is not active**: it requires a verified web/business data provider, source verification and a separate acceptance test. Avoid mass collection of nonpublic personal details.

## V12 test status

- `tests/v12_operational.py`: passed with an isolated temporary test database.
- `tests/v11_growth.py`: passed for five expanding tables and associated Excel styles/formulas.
- JavaScript syntax: passed Node syntax check.
- The broad V10 regression did not complete in the available timeout window; it must not be represented as passed.
- Desktop Microsoft Excel user-acceptance tests, centrally hosted access, production security and data backups remain required before live rollout.

## First pilot use

1. Extract the V12 ZIP to a **new directory** rather than overwriting an active V11 deployment.
2. Follow the existing V11 setup instructions, and back up any live pilot data before migrating.
3. Select Reports → quarterly sales report bundle; verify manager assignments.
4. Select Reports → service planner matching review; approve only dates confirmed to represent completed services.
5. Open a customer contract to record evidenced public contact information.
6. Export the Excel Master and verify its appearance and filtering in desktop Excel.
