# Pulse Contracts OS

Independent contracts-management application for Pulse Fitness.

> **Repository status: bootstrap only.** The application source has **not yet** been imported into this repository. The most recent locally packaged pilot is V12; V13 development is pending migration and tests. Do not deploy this repository as an application yet.

## Project objectives

- Keep the platform **independent** from PulseFitness.ai during the pilot. Do not connect to its production database or change its existing CRM contracts module.
- Manage active and expired maintenance contracts, renewals, customer and site records, equipment cover, invoices, weekly values, and reports.
- Preserve exact-format exports of the approved eight-worksheet Excel Maintenance Master, including styling, filters, formulas, table growth, and matching active/expired column layouts.
- Extract invoice data with evidence, duplicate checks, and a human review stage for uncertain references or handwritten information.
- Support coordinator workflows with clear audit history and protection against conflicting edits.
- Keep Microsoft sign-in out of scope for now.

## Development conventions

- `main`: verified release baseline only.
- `develop`: development integration branch.
- `feature/*`: individual changes, merged to `develop` through reviewed pull requests.
- Tag verified releases as `v12.0.0`, `v13.0.0`, etc. **Do not tag V12 until its source and regression suite are actually present and validated.**

## Data safety

**Never commit** production or pilot databases, customer spreadsheets, invoices, scanned documents, usernames/passwords, API keys, authentication cookies, or runtime backups. Use anonymised fixtures and environment variables. See `.gitignore` and `docs/SECURITY_AND_DATA.md`.

## Migration checkpoint

- [x] Private GitHub repository access verified.
- [x] Repository bootstrap and project guardrails created.
- [ ] Import the full V12 application source from the existing ZIP.
- [ ] Review the archive for secrets, real customer data, and binaries before committing.
- [ ] Rebuild dependencies and run the existing automated test suite.
- [ ] Verify the original Excel-template compatibility in a safe test environment.
- [ ] Create a validated V12 baseline release.
- [ ] Begin V13 customer contact/PPM work on `develop`.

See [migration checklist](docs/MIGRATION_CHECKLIST.md) and [V13 roadmap](docs/V13_ROADMAP.md).
