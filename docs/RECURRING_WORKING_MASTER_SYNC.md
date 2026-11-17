# Recurring Maintenance Master synchronisation — transition workflow

**Status:** Protected development pilot. Excel remains the working register.
**Audience:** Pulse Fitness contracts team, commercial owner and IT.
**App location:** Contracts OS → Source audit → Upload latest working Maintenance Master.

## What changed

This import is **not** the existing Contracts OS "export → edit → re-import"
workflow. It is a second, explicitly controlled process for an Excel Master
that the contracts team continues to maintain independently of the platform.

There is no need to download an Excel template from Contracts OS every week.
Upload the complete current copy of the independently maintained, approved
**eight-worksheet .xlsx Maintenance Master** to the new Source audit area.

The protected server saves the original uploaded bytes, records its SHA-256
fingerprint, compares it with the original private baseline and any previously
accepted field updates, and presents a per-record, per-field preview.

**Nothing is written to existing contracts merely by uploading.**

## Weekly operating procedure

1. Continue making normal changes to the shared Excel Maintenance Master.
2. Agree who owns the current, authoritative file. Avoid uploading another
   person's outdated local copy.
3. Open the protected pilot as an **Admin** and visit **Source audit**.
4. Upload the latest complete workbook and inspect the summary:
   - Already current / unchanged;
   - Safe existing-record field updates;
   - New or unmatched records;
   - Duplicate/blank source Record IDs;
   - Workbook moves/current→expired;
   - Conflicts with edits already made inside Contracts OS;
   - Missing rows (flagged, never deleted or archived);
   - Invalid contract amount or invalid dates.
5. Select only reviewed, conflict-free field updates and approve them.
   Up to **250** records can be applied per review. Upload the latest workbook
   again when additional changes remain.
6. The server must create a verified, recoverable SQLite snapshot **before**
   committing selected changes. Database updates, per-row source baselines
   and source/audit records are committed transactionally.
7. Return to the Source audit dashboard to confirm approved counts, latest
   upload date/hash and exceptions. Resolve exceptions manually before using
   the platform as a definitive contractual or financial source.

## Matching and three-way merge

Only records that have a **unique, unchanged source Record ID** in the old and
new workbooks AND match an existing Contracts OS record are eligible for
automatic matching. Site names alone are not reliable identifiers.

The three sources compared are:

- **Previous accepted source value:** from the audited original Master or an
  approved row-level Excel sync baseline.
- **Latest uploaded workbook value:** exactly what the team entered.
- **Current Contracts OS value:** including staff edits already saved.

If the latest workbook and Contracts OS changed the same field differently,
the update is **blocked** for manual resolution. Missing values are not
converted into £0 and formulas/derived fields are never rewritten.

Blank/duplicate IDs, new customers, newly moved active/expired rows and
records removed from the workbook are reported but **not** automatically
inserted, archived or deleted. This limitation is intentional during the
parallel-running period. The existing Contracts OS staff workflows may be
used for individually reviewed new sites and lifecycle changes.

The current implementation synchronises **existing contract-register fields**
only. It does **not** overwrite the operational workbook copy, replace
ledger/invoice/quotes rows, create equipment, alter signed documents, reconcile
Sage/Sicon, or send invoices.

## Provenance and data protection

- The database retains the original bootstrap Master fingerprint separately
  from the latest working file upload and the list of approved field changes.
- Original uploaded files are held privately under
  `PULSE_DATA_DIR/working_master_uploads`; no customer rows enter GitHub.
- Approval requires authenticated pilot **Admin** role and CSRF protection.
- Reviews expire in 24 hours. Changed DB revisions reject stale approvals.
- Every approved row creates a `changes` audit entry and
  `working_master_actions` source-hash entry.
- The SQLite backup is **local only**; IT must maintain tested, encrypted
  off-host backups and a restoration procedure.
- An imported source entry is still not proof of a legally enforceable
  maintenance agreement, correct cover wording, invoice payment or Sage data.

## Prerequisite and go-live restrictions

The original source baseline must be independently audited and its hash
recorded in `master_source_loads`. The private
`PULSE_DATA_DIR/approved_master.xlsx` must continue to match that fingerprint
so that comparisons are trustworthy. If it does not, the import refuses to
apply anything; IT must first reconcile the historic snapshot without
overwriting staff edits.

**Do not replace the existing Contracts OS SQLite database with a new Master
copy after staff have begun using the platform.** The parallel upload
workflow is a merge, not a restore or destructive rebuild.

When the team is confident in the app, switching Excel to read-only will
require a separately approved cutover: zero unresolved critical conflicts,
backups verified, full row and financial reconciliation, system permissions,
and sign-off from the contract data owner. No automatic switch date is assumed.

## API and tests

- POST `/api/pilot/master-sync/preview` (multipart .xlsx, admin only)
- POST `/api/pilot/master-sync/{review_id}/apply` (selected safe row indices)

The development source-validation workflow runs
`tests/test_master_sync.py` using fictional rows, covering safe matches,
conflicts, duplicates, moves, removals, invalid amounts, repeated uploads,
approval expiry/revisions and failed recovery backups.

**Important:** Passing synthetic CI tests is not the same as authorising a
deployment or proving the correctness of the uploaded real workbook.
