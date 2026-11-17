# Pulse Fitness Contracts OS — controlled server rollout and production gates

**Status:** Release engineering work in the development PR, 3 November 2026.
**Decision:** Provision **private server staging first**. No production launch,
live Sage/Sicon write integration or irreversible workbook replacement has
been authorised by these changes.

## Recommended server architecture (Linux VM or host)

| Layer | Staging design | Final production acceptance |
|---|---|---|
| Staff access | Private HTTPS URL over VPN / allowlisted network | Tested access restrictions, TLS renewal and monitoring |
| Reverse proxy | IT-managed Caddy, Nginx or existing HTTPS gateway | Forwarded-proxy trust set to explicitly approved IPs |
| Web app | One non-root Uvicorn process via Docker Compose | Load test, deployment health and downtime/rollback controls |
| Storage | Separate, permissions-restricted local disk mounted at `/app/pilot_data` | Database capacity/concurrency review, selected storage architecture |
| Source records | Current approved 10-tab Excel Master and pilot SQLite | 100% critical reconciliation of MOD, historical and staff edits |
| Authentication | Separate protected pilot accounts | Central staff identity/MFA, secure session revocation, audited RBAC |
| Backups | Verified local SQLite online copies | Encrypted off-host copies, tested full restore and recovery objective |
| Commercial flows | Unpriced/preview SmartQuote + manual approval | Full V10 price parity, tariff approvals, signed PDF issuance controls |
| External writes | Sicon/Sage production writes disabled | Explicit integration acceptance, rollback and audit |

**Why one process for the pilot?** The existing code is designed around a
single SQLite database with WAL and direct connection management. That should
not be scaled horizontally until concurrent-write and migration behaviour are
tested. PostgreSQL may be the better longer-term shared database, but it
cannot be swapped in without a reviewed application/data migration.

## Deployment safeguards implemented in this branch

- `PULSE_DEPLOYMENT_ENV=staging` requires pilot authentication, secure cookies,
  a long independently stored session signing secret, absolute private data
  path, enabled local backup and one HTTPS public origin.
- Setting `PULSE_DEPLOYMENT_ENV=production` **fails closed**: this release is
  explicitly not certified for unrestricted production.
- `compose.server-staging.yml` binds the backend to `127.0.0.1:18080`
  **only**. IT must provide the HTTPS reverse proxy and network restrictions.
- Container runs as non-root, drops capabilities, has a read-only root
  filesystem, a private writable mounted data directory and a /tmp tmpfs.
- `GET /api/health` exposes no customer data and returns an error if the
  database or approved workbook is missing/unreadable.
- `scripts/server_staging_preflight.py` checks configuration, private
  database integrity, Master layout, admin provisioning and recent local
  recovery checkpoints. It deliberately always reports production **not**
  approved. Passing staging checks does not prove full readiness.

## IT preparation on a Linux server

1. Prepare an OS-maintained Linux VM/host with disk encryption, security
   updates and restricted management access.
2. Choose an internal DNS name, for example
   `https://contracts.company.internal`. Configure an IT-managed HTTPS
   gateway/VPN; **do not** forward port 18080 publicly.
3. Create a private data directory **outside** the GitHub checkout, with
   UID 10001 access only; ensure encrypted/offsite backup policy is agreed.
4. Preserve an independently approved latest ten-tab Excel Master as
   `approved_master.xlsx` and provision a separate SQLite pilot database.
   Use the source-only, non-overwriting staging script if starting fresh,
   **not** against an existing staff-edited database.
5. Configure the following through server-managed, access-controlled
   environment configuration **outside GitHub**:
   - `PULSE_PRIVATE_DATA_DIR=/absolute/host/private/path`
   - `PULSE_PUBLIC_ORIGIN=https://your-IT-approved-HTTPS-hostname`
   - `PULSE_SESSION_SECRET` = new, non-reused cryptographically generated
     secret (at least 48 characters), never sent in chats or committed.
6. Build and start **protected staging**:
   ```bash
   docker compose --env-file /secure/contracts-staging.env \
     -f compose.server-staging.yml config
   docker compose --env-file /secure/contracts-staging.env \
     -f compose.server-staging.yml build
   docker compose --env-file /secure/contracts-staging.env \
     -f compose.server-staging.yml up -d
   ```
   The `/secure/contracts-staging.env` path is an **illustrative IT-owned
   path**, not a file supplied in this repository.
7. Provision a named administrator interactively using the existing protected
   `scripts/init_shared_pilot.py` procedure; don't use shared passwords.
8. Run staging preflight inside the container after provisioning:
   ```bash
   docker compose --env-file /secure/contracts-staging.env \
     -f compose.server-staging.yml exec contracts-os \
     python scripts/server_staging_preflight.py
   ```
9. From a permitted staff computer, test HTTPS, staff role controls, secure
   sign-in/out, PWA installation, and denial of direct backend access.
10. Back up, restore into an **isolated disposable environment**, and prove
    every contract, invoice, equipment and action-audit table survives.

**Important:** The application is still an internal pilot, even when hosted
on a company-owned server. Hosting alone does not authorise customer use as
the legal system of record.

## Build priorities and measurable acceptance

### P0 — Repeatable server deployment and rollback

**Owner:** IT/infrastructure with lead developer.

- One staging URL, reproducible image, no data in source/image.
- Private external volume survives container upgrade and clean restart.
- TLS and firewall settings tested from both allowed and blocked networks.
- Recovery bundle taken, restored and reconciled independently.
- Release image ID/commit, configuration version and rollback steps logged.

**Gate:** A restored copy of genuine staging data passes integrity checks and
the complete contracts/MOD/Expired/ledger/equipment counts remain consistent.

### P1 — Authentication, permission boundaries and security

**Owner:** software architect, IT security.

- Assess Microsoft Entra ID/other existing organisation identity provider,
  MFA, employee onboarding/offboarding and per-person audit.
- Enforce least-privilege authorization on every API, including data exports,
  maintenance quotes, accounting preview and contract setup.
- Server-side session revocation/inactivity expiry; robust login throttling,
  request/upload size enforcement and audit event retention.
- Pinned/reproducible dependencies with vulnerability and container scans.
- Risk assessment, independent penetration test, incident and recovery plan.

**Gate:** No high/critical unresolved access/security findings.

### P1 — Master workbook parity and historical preservation

**Owner:** contracts data owner + development.

- Verify the **current** 10-tab workbook (Maintenance Database, MOD,
  Expired; Action Centre is derived only).
- Reconcile current and expired records against source fingerprints, IDs,
  values and key comments. Preserve legitimate edited staff values.
- Triage duplicate/missing source IDs and historical quote-note gaps from
  the old/new workbook audit; no row is dropped automatically.
- Improve recurring import to handle new sites, MOD transfers, expired moves
  and source rebaseline **with explicit individual approvals**.
- Validate Excel export in actual desktop Microsoft 365, including Renewal
  Status recalculation and Action Centre formulas.

**Gate:** Data owner signs a source-to-platform reconciliation report; every
exception has an agreed outcome and no critical open discrepancies remain.

### P2 — Coordinator acceptance and commercial safeguards

**Owner:** service/aftersales manager, contracts staff.

- Real coordinators trial the Action Centre, renewals, follow-ups, moving
  agreements into Expired, MOD site amendments and reports.
- Verify completed-task evidence and prevent reopened actions being lost.
- Verify per-manager sales reports and financial completeness against Sage.
- Price SmartQuote through the preserved source engine and approved tariff
  snapshots; penny parity and quote archive verified before any issue action.
- Test permissions, simultaneous edits, load and response-time targets.

**Gate:** Named UAT sign-off across core workflows, and finance/commercial
approval for pricing and issued-document controls.

### P3 — Controlled switch from Excel

**Owner:** board sponsor, service manager, IT and contracts data owner.

- Agree a cutover snapshot/hash and freeze interval.
- Take verified backups and a point-in-time Excel export.
- Complete full source/DB and financial reconciliation.
- Communicate who owns the record, which workflows change and how users
  report incidents; retain read-only historical archives.
- Approve a timed rollback and support rota.
- Only then permit an explicit production deployment after security gates
  are removed by reviewed development work.

**Gate:** Written sign-off for data, IT/security, operations and commercial
pricing; no claims of launch before acceptance evidence.

## Decisions required from the server owner

- Server **OS and version**: Windows Server, Ubuntu/Debian, or other.
- Hosting: on-prem VM/physical or cloud, and VPN-only versus external access.
- Existing TLS/DNS/reverse proxy and organisation SSO/MFA arrangements.
- Number of concurrent coordinators/admins and expected usage.
- Encrypted backup destination and recovery objectives.

These choices affect the actual runbook. The provided Compose file targets
**Linux containers**, not native Windows IIS/Windows services.

## November 3 security-hardening follow-up (development branch)

**Changes implemented and under CI review:**

- A login now creates an individually identified, server-recorded session.
  Session IDs are **hashed** in SQLite, never stored in plaintext or printed.
- Explicit logout immediately revokes the server session instead of just
  asking the browser to erase its cookie. Password resets also invalidate
  all prior sessions.
- Session tickets still expire at eight hours; a session that is inactive
  for one hour also expires, subject to the shared-server time settings.
- IT can disable an individual pilot account, immediately revoking its
  sessions, without disabling the last active administrator.
- Protected staging checks the HTTPS `Origin` or `Referer` of mutating
  requests against the configured `PULSE_PUBLIC_ORIGIN`. It also keeps
  anti-CSRF token checks and denies privileged re-import actions to all
  non-administrators, including in the **legacy** Excel re-import flow.
- Read-only Viewer accounts cannot download full workbook exports, exported
  raw documents, signed agreements or mass-export CSVs. Coordinators retain
  the permitted operational reports and read/write actions.
- The Excel reader now checks ZIP central-directory size, part counts,
  inflated size and anomalous compression ratios **before** parsing.
  This prevents small malformed uploads from exhausting the server.
- The application validation job tests both Python 3.11 and 3.12.
  A separate server-image job validates the Compose configuration and
  builds/imports the Docker image with no customer records.
- A separate dependency vulnerability review runs for pull requests,
  weekly and manually. Its result must be reviewed before any deployment.

For exceptional user-access actions, IT may run this **inside the protected
staging container**, after establishing server administrator access:

```bash
python scripts/manage_pilot_accounts.py list
python scripts/manage_pilot_accounts.py create staff.member --role Coordinator
python scripts/manage_pilot_accounts.py reset-password staff.member
python scripts/manage_pilot_accounts.py revoke-sessions staff.member
python scripts/manage_pilot_accounts.py disable staff.member
```

Account creation and password resets prompt interactively and never accept a
password on the command line. The staff account tool must not be exposed as
an unauthenticated web endpoint. These local pilot controls are transitional,
not substitutes for central company identity, MFA, and independent IT security
review before full production.

**Compatibility consequence:** server-side session checking deliberately
invalidates old signed pilot cookies during rollout. Staff must sign in again;
existing server records are not changed. Keep an approved rollback available.
