# Pulse Contracts: full Maintenance Agreement and two Sicon template exports

Protected development only. Original customer master records and signed document versions stay unchanged.

## Source documents — IT-owned, never committed to GitHub

In the protected `PULSE_DATA_DIR`, create folder `approved_sicon_templates` and stage exactly:

- `maintenance_agreement_approved.pdf`: Pulse's eight-page legal agreement, Schedule 3 replaced dynamically (terms pages preserved).
- `sicon_contract_import.xlsx`: approved **Contract Import.xlsx**, all 239 original columns in the same order.
- `sicon_equipment_import.xlsx`: approved **Equipment Import - Template.xlsx**, all 29 named columns in the same order.

Document storage must have restricted read access and be included in private recovery backups; these files must not be committed to GitHub or sent in the user's downloadable build.

## Coordinator flow

Open the Accepted Quotes worklist and choose Review. Its existing Setup Workbench now offers:

1. Confirm missing customer/site identifiers, billing stock code, warehouse, invoice frequency, delivery-address reference and equipment SLA in one form.
2. **Preview populated agreement:** fills customer, site, contract reference, package, dates, services where supported and creates a multi-page Schedule 3 ordered by machine code, showing each machine's start/end date and serials. Original terms, signature fields and conditions are retained. The PDF is **WATERMARKED INTERNAL DRAFT** until Pulse's legal review and approved production workflow.
3. Obtain the signed agreement and archive it with a checksum. The protected recovery bundle includes signed PDFs.
4. **Prepare contract Excel (review only):** copies the supplied 239-column Sicon import template, removes its sample records, and writes one billing line for each contractual commencement group. Source-derived amounts are preserved; Sicon billing stock code, warehouse and delivery address must be explicitly verified. This is not a live import.
5. Record the real Sicon contract number/evidence once uploaded and checked in the approved test environment.
6. **Prepare due equipment Excel (review only):** copies the supplied 29-column equipment template, removes blank/example records, creates one row per serial number, links to the confirmed contract and commencement-date line number, and blocks premature export of future coverage groups. Verify SLA, Sicon customer reference, actual manufacturer and location.
7. Record each date-specific Sicon equipment batch separately; future groups stay on the next-90-day worklist.

## Data mapping restrictions

- Source invoice sales prices are NOT used as RRPs.
- Accepted SmartQuote price snapshots are authoritative; changes to live tariffs do not silently revise an accepted quote.
- The Sicon contract's `Product Stock Code` is a verified billing item, **not** an exercise machine item code.
- Equipment template's `Stock Item Code` is the machine item code; `Serial Number` is the verified physical asset.
- Sicon equipment template has **no dedicated individual coverage start date column**. Each machine must reference the correct separately dated contract line, and its import is deferred until cover begins.
- Never replace existing machine serials, service dates, manufacturer warranty dates or site IDs with guesses.
- Contract pricing columns are an **unapproved mapping proposal**: confirmation of Sicon's invoice generation and pro-rata behaviour is required before any live spreadsheet import.
- Workbooks are named `REVIEW_ONLY.xlsx`, never `READY_FOR_SICON`. Template header changes block export, rather than moving field values into incorrect columns.
- Mixed Silver/Gold/Platinum agreements still require legal/service package sign-off; never infer package entitlement.
- Current Sicon accounting, deferred revenue, analysis codes, original service dates and equipment installation dates remain blank until verified.

## Automation limitations

This is *document generation*, not direct Sage/Sicon integration, digital signature collection or automatic future-dated cover activation. The generated draft legal agreement is not an authorised customer-signature version. Once Commercial, Legal and the Sicon import trial are approved, remove the preview watermark in a separately authorised release.

## Automated tests

`python -m unittest discover -s tests -p 'test_pilot_data_*.py' -v` plus `node --check app/static/accepted-quotes.js`; tests use fictional customer/equipment names and synthetic source templates. No actual private Sicon workbook or agreement PDF is checked into GitHub.
