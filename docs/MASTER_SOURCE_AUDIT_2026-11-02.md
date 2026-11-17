# Uploaded Maintenance Master — factual source audit (2 November 2026)

**Source**: user-supplied eight-sheet Excel Maintenance Master, inspected directly
without changing its data. This document includes **aggregate evidence only**;
no customer names, invoice details, contract numbers or workbook data are in GitHub.

- **Workbook SHA-256**: `e6bef923201e3602951c78ff48a015ffeaaced00659deee90f86709855058eed`
- Eight worksheets, in order: Home; Maintenance Database; Weekly Values;
  Invoices; Monthly Report; Sales Report; Quotes; Expired.
- Excel ZIP integrity check returned no corrupted entry.
- Source archive inspection is **not** a Sage/Sicon reconciliation, a legal
  warranty classification, a financial approval or proof that a running
  Contracts OS installation already contains this uploaded snapshot.

## Source register counts

| Worksheet | Populated source rows | Interpretation |
|---|---:|---|
| Maintenance Database | 649 | Rows with a populated Customer / site field |
| Expired | 8,381 | Rows with a populated Customer / site field |
| Quotes | 1,414 | Rows with a populated Customer / site field |
| Invoices | 601 | Rows with a populated Customer / site field |
| Weekly Values | 1,567 | Rows with at least one of the first three source fields populated |

The eight-sheet workbook also contains Home, Monthly Report and Sales Report
worksheets, with formulas and other presentation/report fields. Those are
not to be counted as customer-site agreements.

Total current and expired register rows **9,030**. These are rows, not
deduplicated legal customers, unique gym facilities or revenue-producing
maintenance contracts.

## Missing or ambiguous data

| Source check | Maintenance Database | Expired |
|---|---:|---:|
| Recorded contract amount absent | 502 | 7,521 |
| Recorded contract amount positive | 143 | 858 |
| Recorded contract amount exactly zero | 4 | 1 |
| Recorded contract amount invalid | 0 | 1 |
| Start date absent | 63 | 130 |
| Expiry date absent | 22 | 148 |
| Contract number absent | 6 | 202 |
| Invoice Code absent | 279 | 8,379 |
| Record ID absent | 11 | 0 |

There is **one repeated Record ID** in the current worksheet, occurring in
Excel rows **620 and 621**. Both source rows must be retained. The application
now creates an unambiguous internal row key while keeping the original source
Record ID visible for review.

None of the missing financial values has been filled with £0. No contract
amounts have been inferred from invoices, warranties or equipment RRPs.

## Current source cover descriptions — exact labels

These are not warranty/contract classifications inferred by AI or substring
matching:

| Label in source | Current worksheet rows |
|---|---:|
| P&L Ext Warr | 336 |
| Contract | 146 |
| Contract (Chargeable) | 78 |
| Warranty | 20 |
| Rental & Contract | 12 |
| Blank | 9 |
| Type A: 1 Year Fully Inclusive MOD Maintenance Contract | 6 |

Other exact labels exist and are retained, including carriage, labour-only,
TRAKK and other specialised status descriptions. The app source-audit page
reads all current labels dynamically, without hardcoding this snapshot.

## Operational restrictions

1. The uploaded file has **not** been pushed to GitHub, merged into an
   existing staff-edited database or installed in a running hosted service.
2. An IT/data-owner-approved copy may be staged in a **new** protected runtime
   with `scripts/prepare_factual_master.py`, which verifies fingerprint,
   row counts, amount completeness and duplicate-ID preservation.
3. If the team has already entered changes in Contracts OS, do **not**
   replace its existing SQLite database with the generated snapshot. A
   separate row-level reconciliation, backup and approval is required.
4. Equipment ownership, serials, legally active contracts, signed agreement
   terms, paid invoices and Sage/Sicon balances cannot be inferred from this
   workbook without separate evidence.
5. Source tables must carry their real names, the as-recorded labels, the
   uploaded file hash and a precise review status before any director
   report claims to be authoritative.

The current development branch contains the schema safeguards and audit UI
but does not constitute a completed production rollout.
