# V4 IT/developer handoff

**Do not expose this ZIP's server on a LAN or the public internet without secure application authentication.** It is intentionally a single-machine local pilot. Microsoft sign-in remains deferred.

## Starting locally

Use `START_PULSE_CONTRACTS.bat` or `py run.py`. Browse to `http://127.0.0.1:8000`.

## Safe upgrade from V3

1. Stop the V3 server; take a copy of its **entire `data/` folder**, especially `contracts.sqlite3`, `approved_master.xlsx`, `uploads/` and equipment catalogue.
2. Unzip V4 into a NEW folder and compare the contained `data/` files against your V3 working database. **Never overwrite a V3 database containing real edits with the V4 demo database.**
3. For migration, replace V4's demo `data/contracts.sqlite3` and relevant upload storage with the backed-up V3 user data. Keep the agreed `approved_master.xlsx` and catalogue.
4. Start V4 on localhost. Additive schema migrations create `revision`, `export_snapshots`, `import_reviews` and `renewal_history`, retaining original contract records.
5. Export Excel and check 8 tabs, filters, notes, statuses, colours, price formats and reports in desktop Excel. Verify that the latest user edits remain.
6. Ask two coordinators to attempt concurrent editing of the same TEST contract; the later save must receive a conflict warning.
7. Test an exported Master: edit a note, re-import, review the change; then edit the same field in the platform and repeat, confirming a conflict is shown.

## Backups and recovery

The local pilot creates a SQLite backup on startup if one has not been generated in the previous 24 hours. `POST /api/admin/backup` can also create a verified snapshot from localhost. Keep a copy of the approved template and uploaded documents separately. Store encrypted backup copies off the workstation with a company retention policy. For recovery, STOP the app, preserve the damaged database, restore a verified snapshot to `data/contracts.sqlite3` and test in an isolated copy before reopening to staff.

## Production integration architecture

- Host as a Contracts module inside PulseFitness.ai, using its existing verified session and staff permissions; no Microsoft sign-in requirement.
- Place an authenticated reverse proxy in front of the app. The server must validate signatures, not trust free-text user names or client-provided roles.
- Move shared contract data to supported managed PostgreSQL or similarly managed transactional database; redesign database access and add migration tooling.
- Encrypt and scan uploaded files; use private object storage and an expiring source-file access policy.
- Maintain an immutable import evidence log per field (page/line/text/confidence/reviewer).
- Use read-only Sage/Sicon lookup before any production write-back; do not assume that invoice item codes are contract numbers or equipment warranty terms.
- Deploy worker processes for OCR, nightly backup, report delivery and data quality checks, with retries and observable failures.

## Excel tracking and re-import

The export contains an invisible `PulseContractsExport:<UUID>` token in standard OOXML core keywords. The source's eight visible worksheet tabs are unchanged. The database stores a snapshot keyed to that token. If Excel or another editor strips the token, the re-import is rejected: use a fresh export; do not bypass this safety check. Contract records match using `Record ID`, and weekly/invoice/quote records match using their existing `Original source` or `Quote ID` values. Do not alter identifier fields.

## Test and acceptance

Run all scripts in `tests/`. These tests cover API and Excel package structure; they are not proof of penetration-test completion, PDF OCR accuracy, Excel UI compatibility or Sage/Sicon functionality.
