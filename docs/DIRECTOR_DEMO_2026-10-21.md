# Director meeting: Contracts OS demonstration (21 October 2026)

## What is ready

A **standalone, offline, fictional-data demonstrator** has been packaged as `Pulse_ContractsOS_Director_Demo_Ready_for_Meeting.zip` for local use at a director meeting.

The demonstration deliberately runs without a Python installation, server, GitHub login or company data. It is *not* the hosted PWA or the full production Contracts OS system.

## Walkthrough (5 minutes)

1. Dashboard: active agreements, contract mix, Q4 renewals, confirmed PPM and fictional example portfolio.
2. Contracts: compact searchable register; open a record and update fictional data in session.
3. PPM: distinguish scheduled, confirmed and cancelled visits. A future appointment cannot be confirmed as completed, and duplicate source references are blocked.
4. Contacts: review and approve built-in fictional suggestions. **No actual AI contact research takes place in this offline demonstration.**
5. Invoices: demonstrate a prefilled evidence-review flow. **No PDF extraction occurs in the offline version.**
6. Reports: filter weekly values by month/week/year and download one ZIP containing three separate fictional CSV manager reports.
7. Excel: demonstrate a *fictional* eight-sheet workbook; the real production-approved Excel template is held outside GitHub.

## Evidence of local checks

- Chromium browser interactions: dashboard, contracts search and session update, PPM creation, contacts approval, fictional invoice review and quarterly report download.
- JavaScript syntax via Node.
- ZIP package and generated per-manager ZIP pass archive-integrity checks.
- Eight-sheet fictional Excel workbook generated and checked.
- Local test browser may require test harness content injection due to browser sandbox navigation policy; does not prove compatibility with every company-managed Edge configuration.

## Important limits

- No customer data, real prices, named staff, passwords, uploads or actual documents were used.
- There is no live data persistence; reloading resets the demo.
- This is *not* an installed PWA, production deployment, verified OCR run or multi-user acceptance test.
- Existing independent V13 FastAPI app remains separate from PulseFitness.ai and needs approved runtime assets, protected HTTPS hosting and UAT.
- Do not merge `feature/pwa-desktop` into `develop` until PR #3's acceptance gates are signed off.

## Director approval recommended

Request approval for a limited independent hosting pilot, two coordinator testers, approved data migration, realistic invoice and Excel acceptance testing, and the Windows PWA rollout only after security review.
