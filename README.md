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
