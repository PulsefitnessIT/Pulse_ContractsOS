# Contracts OS – secure real-data pilot setup

This is for **Pulse Fitness IT**, not contract coordinators. The staff experience is the Windows PWA launched from Edge or Chrome. Python and Docker are required **only on the protected server**, never on staff PCs.

## What is in GitHub

Source code, installation assets, tests and documentation only. The private GitHub repository must **not** be used as storage for customers, invoices, credentials or the Maintenance Master. Making a repository private does not make it a suitable customer database.

## Before you begin

- Use a separate, access-controlled Linux/Windows Server host or VM with company-approved HTTPS reverse proxy/VPN. The Compose service only listens on `127.0.0.1:18080` on that server.
- Choose **one** approved current snapshot. The previous V12 example contained 642 active and 8,381 expired contracts, but it may no longer reflect the current Excel Master.
- Store an approved, extracted private snapshot in a restricted directory **outside the GitHub checkout**. It must contain `contracts.sqlite3` and `approved_master.xlsx`; optionally `equipment_catalogue.json` and `service_planner_source.json`.
- Confirm with the contract team whether updates since the snapshot need importing and reconcile active/expired counts and audit history before pilots begin.
- Back up all source records *before* migrating. Do not use the static director-demo HTML as the source database.
- Do **not** push any `pilot_data` directory, workbook, database, PDF, ZIP or authentication secret to GitHub.

## Stage the snapshot (IT-only)

Use the development branch until review has approved a merge:

```bash
git checkout feature/real-data-pilot-readiness
python3 scripts/stage_private_runtime.py \
  --source /secure/approved-contracts-snapshot \
  --destination ./pilot_data
python3 scripts/pilot_data_status.py --data-dir ./pilot_data
```

The destination must not already exist. The script:
- Validates that the source DB is readable and the approved eight worksheet names are present;
- Takes a transactionally consistent SQLite backup, including committed WAL changes;
- Copies the Excel Master and optional private catalogue/planner JSON without modifying the source;
- Creates private file permissions; checks record counts again; does **not** overwrite an existing destination;
- Prints aggregate counts and warnings only, never customer names, individual prices or personal details.

If a different snapshot is needed later, take a verified backup and use a documented cutover process. **Do not re-run staging over live staff changes.**

## Start the private pilot (IT-only)

On Linux, ensure the bind-mounted folder is writable by container UID `10001` and not accessible to ordinary host users:

```bash
sudo chown -R 10001:10001 ./pilot_data
sudo chmod 700 ./pilot_data
sudo find ./pilot_data -type f -exec chmod 600 {} +
```

Set `PULSE_SESSION_SECRET` (a unique random value at least 32 characters long) through the server's approved secret manager or environment, not a tracked file.

Before starting the web service, create one administrator account using a trusted interactive terminal:

```bash
docker compose -f compose.pilot.yml build
docker compose -f compose.pilot.yml run --rm contracts python scripts/init_shared_pilot.py
docker compose -f compose.pilot.yml up -d
```

Keep `PULSE_COOKIE_SECURE=1`. Publish the service **only through approved HTTPS and VPN/access controls**; do not expose port `8000` or `18080` directly to users or the Internet. The pilot must have secure backups, monitored access, staff accounts and independent security review before expanding beyond the supervised office pilot.

## What staff will see

1. Go to the IT-approved HTTPS address.
2. Sign in with an individual Contracts OS pilot account.
3. Use **Install desktop app** in Edge/Chrome.
4. Search and edit actual contract records only with their assigned permissions.

The app will show a **Contract amount completeness** notice on the dashboard. Blank or invalid amounts are not treated as £0 and the recorded-value coverage is **not** a verified revenue figure.

## Acceptance tests before use

- [ ] Check the database and eight-sheet Master are from the correct approved snapshot.
- [ ] Run `python3 scripts/pilot_data_status.py --data-dir ./pilot_data` and review all issues.
- [ ] Make sure the dashboard displays the expected contract counts and missing-value warning.
- [ ] Reconcile a sample of actual contract numbers, notes, colours, expiry dates and service records to source Excel.
- [ ] Run the historic API/Excel tests against a **disposable** copy of this data, not live records.
- [ ] Export the Master and open in Microsoft Excel; verify all eight tabs, filters, formulas and formatting.
- [ ] Test two coordinators editing simultaneously, a read-only Viewer, an Admin and account logout.
- [ ] Validate backup, off-host restore, HTTPS access and PWA installation/update in Windows Edge.
- [ ] Get written pilot sign-off before using the system as the contract source of truth.

## Limits

No live hosting, data reconciliation or real-data Excel acceptance testing has been performed by committing this feature. Python/SQLite remain on the server. This does not integrate with Sage/Sicon or PulseFitness.ai and does not enable Microsoft sign-in.
