# Contracts OS — ten-tab working Master and Action Centre integration

**Development handover: 3 November 2026.** This is code committed to a draft
pull request; it is **not** evidence of deployment or a completed Sage/Sicon
reconciliation. Customer workbook files stay outside GitHub.

## Source workbook verified by direct file inspection

The latest uploaded Excel is the **ten-tab** source workbook. The exact sheet
order and workbook relationship paths are:

1. Home — `xl/worksheets/sheet1.xml`
2. Action Centre — `xl/worksheets/sheet10.xml` (calculated, not a register)
3. Maintenance Database — `xl/worksheets/sheet2.xml`
4. MOD — `xl/worksheets/sheet9.xml`
5. Weekly Values — `xl/worksheets/sheet3.xml`
6. Invoices — `xl/worksheets/sheet4.xml`
7. Monthly Report — `xl/worksheets/sheet5.xml`
8. Sales Report — `xl/worksheets/sheet6.xml`
9. Quotes — `xl/worksheets/sheet7.xml`
10. Expired — `xl/worksheets/sheet8.xml`

The workbook deliberately retains historical worksheet **part numbers**,
which are different from the visible tab order. The previous fixed eight-tab
reader was therefore incompatible with this source.

Workbook values observed earlier: **592 populated non-MOD current source
records, 57 MOD current source records, and 8,381 Expired records**. These
are row counts, not verified legally active agreements or unique sites.

The new active register header layout includes:

- `Next action date` immediately before `Next action`;
- `Renewal status`, `Record ID`, and `Original source`;
- all 31 current-register columns, in the same order on MOD and Maintenance
  Database;
- the Expired tab's additional historical-only columns remain after the
  matching current-register prefix.

## Implemented on feature/unified-smartquote-intake

- Read original eight-tab and current ten-tab Masters by **actual tab names
  and OOXML relationships**, not fixed worksheet positions.
- Audit, import and stage MOD as a separate current register. Source workbook
  audit sums Maintenance Database and MOD before comparing against the
  database's active total.
- Ignore calculated Action Centre entries as contract rows.
- Parse `Next action date` and `Follow Up Date` as Excel dates, not raw
  serial numbers. When the date column was introduced after the original
  database baseline, only a conflict-free recorded date may be proposed for
  review; **dates are never inferred from free-text actions**.
- In recurring-source upload reviews, transfers into or out of MOD remain
  **human-review exceptions**. No contract is silently reclassified or
  archived. Direct creation of a new MOD record requires the approved ten-tab
  Master and an explicit source-register selection.
- Preserve named worksheet parts, source notes, historical Expired extra
  fields and Excel table definitions during file export.
- Add a live coordinator Action Centre derived from saved current records,
  with filters, due-date urgency, renewal reviews and missing expiry checks.
- Permit signed-in pilot coordinators/admins to record action status,
  free-text outcome notes and reminder dates with an immutable per-event
  history. Completion does not change the source workbook, accepted agreement,
  Sage or Sicon.
- If a recorded follow-up date or description is changed by a later approved
  source upload, a new task identity is created; an old completion isn't
  incorrectly carried onto the new work.

**No Contract Coordinator column** was added back to the active register or
Action Centre UI. Historical-only archived columns are not deleted.

## What this does *not* prove

- Desktop Microsoft Excel has not been exercised end-to-end by GitHub CI.
- A valid workbook structure cannot guarantee the contracts, amounts or
  warranties are independently correct. Historic discrepancies identified
  in the old/new workbook audit remain to be reviewed.
- A reminder date in the past does not prove work was missed or remains open.
- MOD reclassification, new customers and moved/removed rows are held for
  manual, source-linked review pending the next migration workflow.
- SmartQuote pricing and quotation issuance remain separately gated; this
  update doesn't authorise new prices or activation of contracts.
- Neither the uploaded private ten-tab workbook nor its customer records are
  written to the source repository.

## Developer testing

The feature branch source-validation workflow tests Python compilation,
JavaScript syntax, source confidentiality and synthetic-only regressions.
Specific fixtures cover non-positional worksheet IDs, MOD row preservation,
date serial conversion, Action Centre task statuses, actor history, repeated
Excel imports, non-destructive database writes, and flagged MOD movements.

Before a working-user pilot, IT should use a private clone of the **current**
Master and a backed-up application database to test workbook import, register
counts, Excel export preservation and Office desktop formula recalculation.
The development PR must remain unmerged until review and deployment approval.
