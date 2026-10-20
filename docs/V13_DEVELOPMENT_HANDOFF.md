# V13 development handover (20 October 2026)

## Status
The **independent V13 application has been built and tested locally** from the recovered V12 source. **The full application source tree is not yet committed to this repository.** Until the source-only bundle is uploaded, this remains a bootstrap repository and must not be deployed as the application.

## Completed locally
- Evidence-backed public business contact proposals and an explicit review/approval step.
- Contact overwrite conflicts and append-only before/after audit history.
- Completed, planned and cancelled preventative-maintenance visits, with planned visits never updating the last-completed date.
- Earlier approved V12 planner visits linked to the new service-history timeline through idempotent migrations.
- Clear source planner notes and an estimated next-service date, explicitly not a contractual promise or booking.
- The existing eight-sheet Excel export preserved.
- All application/pilot data remains separate from PulseFitness.ai.

## Verified tests
- PASS V13 contact proposals and PPM history.
- PASS V12 operational reporting and planner approval.
- PASS V11 Excel-table growth and style checks.
- PASS Python compilation and browser JavaScript syntax.
- **Not certified:** the slower V10 multiuser/export suite exceeded the available test window. Desktop Excel checks, production hosting and live OCR/contact research remain outstanding.

## Source migration
The source-only GitHub package is `Pulse_Contracts_OS_V13_GitHub_Source_Only.zip`. It excludes `data/`, customer databases, the approved Excel workbook, private PDFs, images and secrets. Extract its contents into this repository's `develop` branch and review the diff before committing. Do **not** upload the larger local-pilot package containing internal datasets.

After code is uploaded, run source checks in GitHub Actions and full acceptance tests on a separate protected pilot dataset. Only then open a PR into `main`.

See the local V13 package for `GITHUB_TRANSFER.md`, `V13_RELEASE_NOTES.md` and `V13_TEST_REPORT.md`.
