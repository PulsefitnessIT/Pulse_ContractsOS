# Contracts OS — Verified Expired Contract Transfer

**Development date:** 4 November 2026  
**Feature branch:** \`feature/unified-smartquote-intake\` (draft PR #5)  
**Source:** \`MASTER of Maintenance Contract Spreadsheet - NEW MASTER 3.11.xlsx\` and its aligned Expired register

## Why this exists

Pulse Fitness coordinators previously cut/pasted entire maintenance agreement rows
from **Maintenance Database** into **Expired**. This requires identical column
positions and preservation of years of historic contract notes.

The approved working Master contains:
- **31 shared ordered columns, A–AE**, identical on \`Maintenance Database\`,
  \`MOD\` and \`Expired\`.
- **12 additional Expired-only historical columns, AF–AQ**. These remain at
  the right-hand end; existing historical content must not be overwritten.
- **8,381 historical data records in Expired** (the workbook contains 8,382
  rows including the header), plus live current agreements in the separate
  Maintenance and MOD registers.

The app now checks this layout before transferring contracts. Future uploaded
ten-tab Masters whose Expired columns are rearranged are rejected before an
approved recurring Master sync applies data changes.

## Coordinator workflow (protected pilot)

1. Go to **Contracts → Review expired contracts**.
2. Choose **Maintenance Database** (default) or **MOD**.
3. Review the candidate list. It shows active-register records whose
   recorded expiry date is today or in the past. **Expiry date does not
   prove that a contract ended**, so the app never auto-archives.
4. For each candidate, verify the actual agreement, renewal record and
   customer status. Select only agreements which should really move
   to the historical register.
5. Enter a meaningful reason and confirm you checked **every selected
   agreement and its non-renewal**.
6. Transfer up to **40 selected agreements** in one atomic action.
7. The app verifies a recovery backup, checks each record's expected revision,
   original source and expiry date, then moves the selected rows to Expired
   and records the acting coordinator and destination row number.
8. Select **Excel Master** to download the updated workbook with the
   rows reflected in their proper positions.

For an individual contract, the existing **Archive** control remains
available. It now also validates the exact source worksheet headings
and appends beyond the end of the historical Excel template.

## Data preservation guarantees

- The source workbook on disk is not edited immediately by the move. The
  app's next Excel export generates the updated working copy.
- Every source record retains its **stable Record ID** and the source
  **31 fields** including site notes, financial data, actions and invoice
  references. Only status, source register, source row, and computed
  \`Renewal status\` change.
- The app stores the original register and row number and appends the
  moved contract **after the last historical Excel row**, never over a
  previously populated Expired row.
- The existing 12 historical columns in old Expired records are **left
  untouched**. For a newly moved contract those fields stay blank unless
  the record already has matching historic values.
- Attached equipment and serial numbers retain their original contract ID.
- The audit log records the original fields, receiving row, actor, expiry
  evidence and user-supplied reason.
- Changes are all-or-nothing: mismatched revisions, duplicate selections,
  missing expiry dates, future-expiring contracts, absent backups or
  incompatible headers stop the entire batch.
- Excel export retains the approved workbook formatting, tables and
  formulas. The previously overlooked MOD-to-Expired source formatting
  is now copied correctly.
- The feature does not auto-renew, cancel contracts in Sage/Sicon, delete
  agreements or email customers.

## Access and scope

The new preview/apply endpoints require a verified **Coordinator** or **Admin**
account in protected pilot mode. The normal origin and CSRF rules apply.
Viewer accounts cannot move records. An approved database backup must be
created before the batch is written.

A real-source deployment must replace the pilot's existing private
\`approved_master.xlsx\` with the validated latest Master and be reconciled
against its current SQLite snapshot before use. This PR **does not** stage
the user's private customer records or workbook in GitHub.

## Code and testing

- \`app/register_layout.py\` — exact header-order validation and protected
  template last-row lookup.
- \`app/expiry_transfer.py\` — read-only candidate worklist and versioned
  audited batch transfer with backup and atomic SQLite updates.
- \`app/static/expiry-transfer.js\` — coordinator UI, individual selection,
  confirmation and post-transfer refresh.
- \`app/main.py\` — registration, and safe append index for existing
  single-record archives.
- \`app/excel_io.py\` — MOD style transfer support when exporting to Expired.
- \`app/master_sync.py\` — current ten-tab Master layout validation on
  recurring uploads.
- \`tests/test_expiry_transfer.py\` — fictional 31+12-column layout,
  role, expiry, immutable historical data, backup, conflict and source
  export tests. Includes synthetic OOXML round-trip verifying existing
  Expired-only notes are retained and table ranges grow correctly.

**Commercial release:** implemented on a draft feature branch, not merged or
deployed. Synthetic CI tests do not establish real production workbook or
database parity; acceptance tests are required before coordinators use
this workflow with customer records.
