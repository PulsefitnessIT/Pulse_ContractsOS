# Pulse Contracts OS V7 — Evidence-first Contract Matching

**Release:** development / local testing build, 17 October 2026  
**Baseline:** V6 (offline scanned-PDF recognition and eight-tab Excel export)

## What's new

1. **Cautious matching against the existing Maintenance Database.** The matching engine compares normalized contract references, physical site names, site accounts, invoice accounts and agreement dates. It explains the reasons for each suggested match.
2. **Coordinator-facing suggested records.** The Import Documents review drawer now shows up to six candidate agreements with customer, contract reference, site account, expiry date and warnings. Staff can select the correct record for further review.
3. **Improved conflict protection.** Shared invoice accounts alone never identify a unique contract. A repeated contract number, a materially different site or a contradictory site account prevents automatic target selection. A conflicting existing contract reference cannot be used to silently create a duplicate new agreement.
4. **Audit provenance.** An approved document update records the originating import ID, filename, document SHA-256, source page reference and original extraction note in the contract change history, alongside fields changed and any overwritten fields.
5. **Existing Excel functionality retained.** The approved eight-tab spreadsheet remains the exact-layout source template, with filters, source site colours and historical sheets protected by the established export regression checks.

## What 'automatic' means in this version

V7 **suggests** a target only when one exact contract reference has supporting independent identity evidence and no serious site/account contradiction. **It never saves a document-derived field without a deliberate confirmation action.** If evidence is insufficient, staff must explicitly choose the destination record. An equipment sales price remains separate from maintenance contract revenue.

## Starting it

Extract the ZIP, go to `Pulse_Contracts_Platform`, and run `START_PULSE_CONTRACTS.bat` on Windows with Python installed. Configure `PULSE_OCR_MODE=local` and install Tesseract if offline printed-text OCR is needed. Azure document reading remains optional and unconfigured. Do not replace the `data` directory of an existing installation with bundled demonstration records.

## Known gaps / production blockers

- Printed text extraction works on supported scanned pages when OCR is installed, but **unattended handwriting recognition is not validated**. Handwritten contractual references and dates must be checked visually.
- Multi-user web hosting, user/permission enforcement, reliable staff attribution and a production database are still required. Microsoft SSO is intentionally parked; an alternative approved access method will be needed for production.
- Sage 200 / Sicon are not yet connected for live data reconciliation or write-back.
- No deployment to PulseFitness.ai or formal desktop Excel compatibility sign-off has occurred.
- Existing local sample data are for testing. Deployments require an agreed migration procedure, scheduled backups and restore drills.

## Upgrade warning

Create a backup of any V6 database and uploads first. Package contains a pilot `contracts.sqlite3` and approved workbook; **never overwrite an active site's `data` folder** with the bundled test database. New code uses additive changes only, but a tested migration and rollback process is required before a shared rollout.
