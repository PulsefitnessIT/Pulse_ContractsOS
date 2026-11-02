# Pulse Contracts OS — independent contracts management

**Source-only development checkout.** The existing V12 pilot's operational database, approved eight-tab Excel template, equipment catalogue and confidential documents are intentionally **not** in GitHub. This repository does not provide a pre-populated installation.

## What is here?

- `app/`: FastAPI backend, coordinator-facing web interface and Windows PWA installation assets.
- `scripts/`: local pilot account setup, backup/recovery, import and release verification utilities.
- `tests/`: historic regression tests and V13 PPM/PWA tests. Some require an independent **disposable** copy of pilot data and therefore are not run as ordinary unit tests in GitHub Actions.
- `docs/releases/`: relevant V10–V13 release documentation.
- `docs/archive/`: historical V3–V9 documents, not required to run the platform.
- `Dockerfile.pilot`, `compose.pilot.yml`: IT-managed **staging** configuration, not a production security certification.

## PWA for staff

The recommended staff experience is **Install desktop app** from Microsoft Edge or Chrome after IT deploys the independent app behind HTTPS. No Python is required on staff computers. Python runs only on the central protected server. The offline page caches no customer records. See [`docs/PWA_DESKTOP_RELEASE.md`](docs/PWA_DESKTOP_RELEASE.md).

## Branches

- `main`: release baseline, do not merge partially tested features into it.
- `develop`: reviewed integrated development work.
- `feature/pwa-desktop`: source migration + installable-PWA development in progress.

## Important safeguards

- **No customer data in GitHub.** The source-only bundle was inspected and demonstration customer identifiers were replaced with fictional placeholders for this branch.
- Never add `data/`, `pilot_data/`, databases, PDFs, invoices, business workbooks, secrets, or backups.
- Keep the independent PulseFitness.ai system completely unchanged. Microsoft login remains out of scope.
- No shared office deployment has been performed; HTTPS hosting, server storage, user acceptance and desktop Excel verification are still outstanding.
- Private company runtime assets (approved Excel template and catalogue) must be provisioned securely **outside** GitHub before starting a new instance.

See the migration checklist and current release notes for detailed acceptance gates.

## Real-data protected pilot (development)

`feature/real-data-pilot-readiness` adds secure staging of a private snapshot and read-only financial completeness indicators. **It does not include a customer database and has not been deployed.** Follow [Private data pilot setup](docs/PRIVATE_DATA_PILOT_SETUP.md) for IT instructions. The stage tool preserves WAL-consistent SQLite data and refuses overwrites; GitHub CI tests use fictional synthetic fixtures. Missing amounts are reported separately, not counted as £0 or verified revenue.

## Unified SmartQuote workspace (development branch)

The SmartQuote tab now supports independent unpriced quote drafts, multiple equipment
lines, revision-aware reopening, optional read-only historic quotation browsing,
identity-only V10 catalogue lookup and an integrity-checked direct *accepted
snapshot -> Contract Setup* review handover.

**This does not yet replace the SmartQuote pricing engine.** It must not be used
to issue commercial quotations, calculate approved tariffs or activate Sicon
contracts. The original SmartQuote database is never overwritten by the
unified workspace.

Private runtime settings (provide outside source control):
- `PULSE_SMARTQUOTE_DB` — absolute path to the original SmartQuote V10
  SQLite database, read-only from Contracts OS.
- `PULSE_SMARTQUOTE_CATALOG_JSON` — optional absolute path to the approved
  operational copy of SmartQuote V10 `data/catalog.json`. Product identity
  only; no automatic price.
- The existing protected `PULSE_DATA_DIR` for Contracts OS, including the
  approved maintenance master and its separate runtime database.

See [Founder review and release gates](docs/FOUNDER_REVIEW_UNIFIED_PLATFORM_2026-11-02.md).

A new **V10 source-based pricing preview** uses private operational catalogue,
configuration and tariff JSON files to calculate non-issuable estimates from
exact SKU matches. Configure PULSE_SMARTQUOTE_CONFIGS_JSON and
PULSE_SMARTQUOTE_PRICING_JSON in addition to PULSE_SMARTQUOTE_CATALOG_JSON.
See [Pricing preview and source parity gates](docs/SMARTQUOTE_V10_PRICING_PREVIEW.md).

Staged maintenance agreements now accept optional contract dates and individual
equipment cover starts. The preview uses the original V10 inclusive ACT/ACT
prorating for dated coverage groups. A separate read-only Sage Sales Price
reference can be surfaced for unmatched catalogue SKUs, but never alters an
approved Master Price List entry or quotation totals. Missing sources, incomplete
cover dates, historical estimates and unapproved tariffs remain blocked from
customer-ready issue.



## Factual workbook source and provenance (November 2026)

The latest user-provided Maintenance Master was reviewed as a **source file**,
not silently merged into a running staff database. Its audited source checksum,
row counts and non-personal quality findings are documented in
[2026-11-02 Master evidence](docs/MASTER_SOURCE_AUDIT_2026-11-02.md).

A new **Source audit** screen reads the configured private approved_master.xlsx,
reports its fingerprint, exact cover-type labels, missing information and
source/database record count differences. The dashboard now distinguishes
worksheet records from legally verified live maintenance agreements.

The native SmartQuote interface can search existing site labels stored in the
Contracts OS register. Selecting one records the source record ID, but **never
invents a legal customer name** or assumes the agreement is current. Editing a
site clears the source link until the coordinator reselects it.

To prepare a **new** private database from an IT/data-owner-approved Excel
Master, rather than use fictional demonstration data:

```bash
python scripts/prepare_factual_master.py \\
  --source /secure/latest-approved-master.xlsx \\
  --destination /secure/new-source-backed-snapshot \\
  --approved-current-master
```

The destination must not exist and must be outside the GitHub checkout. The
script refuses to overwrite an existing application database or merge over
staff edits. It retains duplicated source IDs in their original fields while
using labelled internal unique keys. The source file remains private; only
aggregate checks and its checksum may be committed to GitHub.

These features are development-only until full CI, staging, signed commercial
controls and actual Sage/Sicon reconciliation are complete. No production
installation or private workbook transfer is implied by the code commits.

## Recurring upload of the working Maintenance Master

During parallel operation, **Excel remains the authoritative source file**.
Contracts OS now provides a separate administrator-reviewed **Source audit →
Upload latest working Maintenance Master** flow. It accepts a complete
independently edited eight-tab workbook, fingerprints and privately stages it,
then previews exact source-ID matches, safe field updates, conflicting staff
edits, new sites, duplicate IDs, status moves and absent rows before any write.

Only selected safe existing-record field changes may be applied. Approval
requires a verified pilot Admin session, an online SQLite recovery backup,
unchanged record revisions and an auditable original source SHA-256. Uploading
never replaces the entire Contracts OS database, edits the customer's Excel
file or automatically deletes/archives unmatched records. New/moved/ambiguous
records remain a manual review worklist until an approved reconciliation
workflow can handle them.

See [Recurring working-Master upload procedure](docs/RECURRING_WORKING_MASTER_SYNC.md).
