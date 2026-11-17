# Pulse Fitness — Contracts OS + SmartQuote supervised launch | 9–13 November 2026

**Deployment decision: INTERNAL PILOT ONLY. Customer quote issuance and a
production cutover remain disabled until separately signed off.** This
document describes the shortest supported route using the integrated
`feature/unified-smartquote-intake` branch, not an unimplemented rewrite.
The user-facing service is the Contracts OS HTTPS web/PWA application; no
Python or Docker installation is required on staff PCs.

## What exists and has been source-tested

- Contracts OS customer/contract register, expiry/action workflows, reports,
  equipment-linked contracts and versioned Excel export
- Integrated Pulse-branded SmartQuote with invoice/delivery-note PDF drop,
  exact SKU matching to the single versioned price book, quantity/serial
  batch review, saved drafts and a watermarked INTERNAL quote PDF
- Protected pilot login (Admin/Coordinator/Viewer), audit trails, HTTPS
  reverse-proxy staging configuration and local DB backup capability
- Container image build and synthetic Python/JavaScript CI, without
  customer data in code or builds

Automated tests alone do **not** establish price-list completeness,
commercial terms, licence approval, customer identity or real-file
acceptance.

## Monday 9 November — IT creates the protected instance

1. Assign an IT deployment owner and a Service business owner.
   Use a company-managed host/VM with an **approved HTTPS reverse proxy**
   or VPN. `compose.server-staging.yml` binds only to
   `127.0.0.1:18080` and deliberately contains **no public HTTPS proxy**.
   IT must configure one. Do not expose port 8000 or 18080 publicly.
2. Obtain an **approved private Contracts OS snapshot** with
   `contracts.sqlite3` and `approved_master.xlsx` from the current
   maintenance workbook, reconciling all changes made since the snapshot.
   Take a source backup, then stage into a **new empty** private directory.
   Never commit or copy customer information into the public repository.
3. On the IT-managed Linux host:

```bash
git switch feature/unified-smartquote-intake
python3 scripts/stage_private_runtime.py \
  --source /secure/approved-contracts-snapshot \
  --destination /srv/pulse-contracts/private
sudo chown -R 10001:10001 /srv/pulse-contracts/private
sudo chmod 700 /srv/pulse-contracts/private
sudo find /srv/pulse-contracts/private -type f -exec chmod 600 {} +
```

4. In IT-managed protected environment/secret configuration (not in
   GitHub or shell history), set
   `PULSE_PRIVATE_DATA_DIR=/srv/pulse-contracts/private`,
   `PULSE_PUBLIC_ORIGIN=https://<approved-private-hostname>`, and a
   randomly generated `PULSE_SESSION_SECRET` of at least 48 characters.
   The Compose configuration already sets staging profile, pilot login,
   secure cookies and local backups.
5. Build the server and create a named pilot Admin with the provided
   interactive command; provision separate named Coordinator/Viewer
   accounts through the approved pilot account utility:

```bash
docker compose -f compose.server-staging.yml build
docker compose -f compose.server-staging.yml run --rm contracts-os \
  python scripts/init_shared_pilot.py
docker compose -f compose.server-staging.yml up -d
docker compose -f compose.server-staging.yml ps
```

6. Verify HTTPS in a real browser, account login/logout, Admin versus
   Coordinator versus Viewer permissions, PWA installation and service
   health. Verify backup to **another host** and restore to a separate
   disposable instance before live staff changes begin.

## Tuesday 10 November — validate data and SmartQuote setup

- Confirm the latest maintenance database and Expired sheet totals,
  contract values, renewal dates, sales manager reports, MOD split and
  Action Centre with the owner. Export a fresh Excel file and manually
  compare names, notes, dates, formatting and sample contract records.
  No cutover if there is unexplained data loss.
- Admin uses **Unified Master Price List** to import and activate the
  approved merged Sage/Master price file. Master prices override Sage
  on the initial merge; on later updates, **new verified imports
  override matching codes**, while other SKUs persist.
- Check the one active price-book fingerprint and clear held/duplicate
  item-code conflicts. Verify machine category exclusions: spares,
  consoles/options, installation, trade-ins, warranty and accessories.
- Test the supplied 2018 Evesham (18 pages), Horizon (26 pages) and
  2021 N100621 delivery note (3 pages) **on this protected instance**.
  Compare detected rows, quantity and all serials with originals.
  Specifically check zero-priced legacy machines are priced only from
  the current Master, Horizon multi-page serials, and delivery goods
  marked **TO FOLLOW** or zero received.

## Wednesday 11 November — two-coordinator acceptance

Have two actual coordinators, one Admin and a Viewer independently test:

1. Sign in and find a known contract/site and its warranty/expiry values.
2. Change a test contract note/action and confirm audit trail and export.
3. Drag invoice/delivery PDF(s) into SmartQuote; exact codes auto-match;
   spare parts/options and zero-received goods must not be auto-quoted.
4. Confirm **all** source quantities and serials in one batch; resolve
   unmatched item codes without falsifying source identity.
5. Set approved-for-INTERNAL-use rate assumptions and compare two
   sample calculations with the existing quotation spreadsheet.
6. Save, reopen, reprice and download the watermarked Pulse PDF.
7. Verify simultaneous user changes, a Viewer denied write access,
   logout, stale price-book protection and a recovered backup.

Record all discrepancies and their resolution. Staff must not send an
**INTERNAL DRAFT** PDF as an externally binding quotation.

## Thursday/Friday 12–13 November — controlled use

Only after the preflight and actual UAT pass, allow a small group of
coordinators to operate the protected pilot for real day-to-day
contract administration and internal quotations, with the existing
maintenance workbook and legacy quote route retained as fallback.
Set a named owner to handle import exceptions, support and daily backups.

Stop or roll back to the previous workflow if contract records fail to
reconcile, incorrect Master prices appear, PDFs misstate quantities,
staff accounts are shared, source exports fail, or backup/restore fails.

## One-command operational preflight

From the running staging container:

```bash
docker compose -f compose.server-staging.yml exec -T contracts-os \
  python scripts/check_pulse_launch_readiness.py --data-dir /app/pilot_data
```

It checks private data and workbook integrity, approved staging security
settings, an active checksum-verified unified Master, named staff
accounts and a recent local backup. By design, **this command initially
returns NO-GO**: no script can honestly perform and approve the actual
data reconciliation, remote restore, HTTPS/browser tests or UAT.

Once the evidence for all four independent tasks has been retained and
approved, re-run adding these explicit acknowledgement switches:

```bash
docker compose -f compose.server-staging.yml exec -T contracts-os \
  python scripts/check_pulse_launch_readiness.py --data-dir /app/pilot_data \
  --data-reconciled --restore-tested --https-and-roles-tested \
  --coordinator-uat-passed
```

Exit 0 means **a supervised internal pilot is technically and manually
cleared**; exit 2 means a gate remains blocked. This gate **never**
enables customer PDF issuance or declares a production certification.
Never use flags unless real tests have been done.

## Customer-facing maintenance quotations — separate permission

Before sending Pulse-branded *customer* documents, the commercial owner
must approve real Silver/Gold/Platinum tariffs, equipment eligibility,
minimums, exclusions, VAT, term/proration rules, supplier details and
genuine T&Cs. IT/Admin then reviews the built-in
`/api/quoting/release-check` evidence, signs the specific quote and
explicitly enables customer issuance, as described in
`docs/SMARTQUOTE_CUSTOMER_QUOTE_RELEASE.md`.

No automatic Sage, Sicon or PulseFitness.ai writes are authorised or
performed by this first launch.

## The actual external dependencies

- **Pulse Fitness Service/Contracts owner:** latest approved private
  workbook/database, real unified Master, rate/terms decisions,
  coordinator UAT sign-off
- **Pulse Fitness IT:** managed VM, HTTPS and private URL, named logins,
  security/access checks, backup/restore, monitoring and user onboarding
- **Engineering:** fix any discrepancies from real data/real invoice
  tests and provide a reviewed, pinned release commit

A CI-green public repository is **not** itself a deployed system, and
its public source contains neither real private pricing nor customer data.
