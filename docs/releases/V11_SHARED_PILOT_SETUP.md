# V11: independent shared pilot setup (for Pulse Fitness IT)

**Not production-approved.** V11 remains separate from PulseFitness.ai, Emergent and all existing CRM/Sicon systems. No Microsoft sign-in is required.

## Deployment prerequisites
- An IT-managed Linux host with Docker Compose, available disk space, encrypted storage and monitored backups.
- Internal-only access via VPN or approved HTTPS reverse proxy; do **not** expose HTTP port 18080 directly to users.
- Create a protected `PULSE_SESSION_SECRET` (48+ random characters) in the server's secret store/environment. Do not put it in GitHub.
- Make `pilot_data` a persistent directory accessible to UID 10001. Use `chmod 700` with appropriate ownership and include it in encrypted off-host backups.

## Initial setup (run by IT)
1. Build: `docker compose -f compose.pilot.yml build`.
2. Create persistent directory: `mkdir -p pilot_data && sudo chown 10001:10001 pilot_data`.
3. Initialise with the same environment variable `PULSE_SESSION_SECRET` that will be used for the server:
   `docker compose -f compose.pilot.yml run --rm contracts python scripts/init_shared_pilot.py`
   This copies the bundled **test** records once and prompts for an administrator account. Existing pilot data is not overwritten.
4. Start: `docker compose -f compose.pilot.yml up -d`.
5. Verify locally: `curl -i http://127.0.0.1:18080/api/health`.
6. Configure approved HTTPS termination from the organisation's internal/VPN access path to `127.0.0.1:18080`.
7. Open through HTTPS and verify that the secure authentication cookie is sent and a Viewer cannot edit contracts.

## Safety boundaries
- Do not add MongoDB connections, live Sicon credentials or production PulseFitness.ai assets to this test environment.
- Single Uvicorn worker; the SQLite database stays on **local** server storage (never a mapped network share). Scaling to several instances requires an additional database redesign.
- The in-memory login failure throttling is per process. Enforce additional proxy-level rate limiting and monitoring.
- Daily off-host backups must include `pilot_data/contracts.sqlite3` (SQLite's consistent backup mechanism), uploaded documents, the equipment catalogue and approved Excel template. Use the existing `scripts/pilot_backup_bundle.py` utility and test restores.
- Image builds contain the bundled pilot seed data: do not publish the image to a public registry.
- The Excel template is an authoritative **format**, not proof that all imported customer information has been validated.
- Do not turn off `PULSE_PILOT_MODE`, `PULSE_COOKIE_SECURE`, HTTPS or CSRF protections for multi-user testing.

## Release gates
- At least two coordinators perform concurrent edits on independent machines over HTTPS.
- Verify a workbook with new rows beyond the prior table end (including filters, conditional formatting, date/currency columns) in desktop Microsoft Excel.
- A staff member opens and checks 20+ representative invoices, including scanned handwriting; no uncertain fields update contracts automatically.
- Test restoring an off-host backup onto an **isolated** host without touching production.
- Independent security review, permission checks and a documented incident response plan are required before broader rollout.
