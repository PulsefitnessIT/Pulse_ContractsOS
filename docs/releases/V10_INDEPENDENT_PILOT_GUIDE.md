# Pulse Contracts OS V10 — Independent pilot guide

## What V10 does (and does not do)

- **Completely separate** from PulseFitness.ai and its MongoDB, users, routes and CRM contracts.
- Adds a protected pilot login with local staff accounts (no Microsoft sign-in).
- Has three roles: Coordinator and Admin may edit; Viewer may read and export only.
- Uses a session cookie and anti-CSRF protection. Every tested contract change is attributed to the signed-in user, not a browser-supplied name.
- Preserves the eight-sheet Maintenance Master template; export quality gate checks sheet order, key headings, identical active/expired layouts and filter definitions before distributing files.
- Warns when the existing preformatted Excel template is running out of rows (`/api/export/preflight`). It **does not automatically extend Excel tables**.
- Has a complete local recovery ZIP script (database, equipment catalogue, Excel template and uploaded PDFs) and a separate restore-verification script.
- Includes an invoice-recognition quality endpoint based on human-verified data only (`/api/quality/invoice-recognition`). It does not claim handwritten accuracy.

## Local pilot on one Windows computer

1. Extract this ZIP into a **new folder**; do not overwrite an existing V9 `data` directory.
2. Run `SETUP_V10_PILOT.bat` once. It installs dependencies, copies the supplied sample records into **pilot_data/**, generates a local session signing secret and prompts you to create an Admin login. It does not overwrite existing pilot_data if already present.
3. Run `START_V10_PILOT_LOCAL.bat`. Access `http://127.0.0.1:8000` and log in.
4. Run `ADD_PILOT_USER.bat` to add other coordinators or read-only viewers.
5. Do not email or share the generated `pilot_settings.cmd`: it contains a security secret. Do not put `pilot_data/` or `pilot_settings.cmd` in GitHub.

## Sharing with several coordinators (requires IT deployment)

V10 is **not hosted yet**. Do not simply open port 8000 to the office or internet. For a small supervised pilot, IT should run **one** application instance on an internal Windows/Linux server, bound to loopback, with HTTPS termination via a managed reverse proxy, a suitable firewall, and access limited to authorised staff / VPN. Configure `PULSE_COOKIE_SECURE=1` once HTTPS is available. Arrange appropriate proxy-side upload limits and rate controls. Keep the SQLite database on local server storage, never on a network share. Do not run multiple independent server copies sharing the same database file. A production-grade multi-node deployment would require a migration to a managed transactional data store.

Add account lockout, logs, server patch management and independent vulnerability testing to the formal release checklist. Rate limiting in this version is in-memory, not shared across multiple processes. None of this constitutes a production security sign-off.

## Backups and disaster recovery

From the application root with the correct `PULSE_DATA_DIR` loaded, run:

```
python scripts/pilot_backup_bundle.py
python scripts/verify_recovery_bundle.py "path/to/pulse_pilot_recovery_....zip"
```

The bundle includes database + approved workbook + product catalogue + stored uploaded documents, and checks SHA-256 hashes. Schedule the backup tool daily, copy completed ZIPs to encrypted off-host storage, restrict access, apply a retention policy and test restores routinely. The app's on-start local SQLite snapshot does **not** replace this process. `pilot_settings.cmd` is intentionally **not included** in the recovery ZIP; maintain it in a separate protected secrets store.

## Testing the 8-tab export

`python tests/v10_critical.py` uses a disposable database and validates the pilot sign-in, CSRF, read-only access, simultaneous editors, audit identity and exported Excel structure. Exported files still require practical checks in **desktop Excel** for formulas, filter behaviour, row colour and print appearance before the team signs off.

## How we decide to release to staff

- At least two coordinators can edit different records simultaneously; stale edits produce a clear conflict, not lost changes.
- 20+ representative documents are correctly grouped and reviewed; there is no unapproved change to contract terms or invoice totals.
- Staff verify an exported Excel workbook in desktop Excel, including a new record, renewal and archived contract.
- An IT-supervised backup + full restore succeeds, including uploaded PDFs.
- Security review and authorised staff access are complete.

**PulseFitness.ai remains untouched throughout V10.** The contracts app is an independent pilot and should not be used as a replacement for the live Maintenance Master until these acceptance tests are complete.
