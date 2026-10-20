# V12 GitHub migration checklist

## Rules
- Keep Contracts OS independent from PulseFitness.ai and its live MongoDB database.
- Never commit production/pilot databases, scanned invoices, customer spreadsheets, credentials, or real customer data.
- Do not declare source migration complete until the application files, dependencies and tests are actually present.

## A. Inspect V12 archive
- [ ] Unpack the existing V12 ZIP in a secure environment.
- [ ] Inventory the app entrypoints, dependencies, tests, assets, Excel templates and data.
- [ ] Exclude any live/pilot database, invoice PDFs, OCR extracts and files containing confidential customer data.
- [ ] Scan source for hardcoded secrets and credentials.
- [ ] Prepare sanitised sample data; keep the approved Excel Master separately in controlled storage if it contains real customer information.

## B. Transfer source
- [ ] Commit approved source files, manifest and automated tests.
- [ ] Include a placeholder environment example with no credentials.
- [ ] Explain local start, test commands and migration processes.
- [ ] Inspect repository changes for accidental secrets and document uploads.
- [ ] Create a V12 baseline only after verification.

## C. Validate V12
- [ ] Install from pinned dependencies and start application.
- [ ] Run all existing automated tests, documenting actual results.
- [ ] Test contract edits, archive, Excel roundtrip, OCR, batch invoices, concurrency, audit, backups and reporting.
- [ ] Verify the 8-sheet Excel export, live filters, matching active/expired headings, formulas, row styles, and expansion beyond preformatted ranges.
- [ ] Record manual desktop Microsoft Excel checks separately.
- [ ] Tag only a verified V12 baseline.

## D. Begin V13
- [ ] Open feature work on develop.
- [ ] Build verified contact research with sources and explicit approvals.
- [ ] Add completed/planned/cancelled PPM history from the existing review process.
- [ ] Retest all previous functionality.

Current status: repository preparation complete; source archive extraction and source import remain outstanding.
