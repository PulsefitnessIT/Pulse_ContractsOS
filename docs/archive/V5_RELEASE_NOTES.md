# Pulse Contracts OS — Version 5

**17 October 2026 | Tested local pilot, not a live production release.**

Version 5 continues the existing PulseFitness.ai-inspired design. Microsoft staff sign-in remains out of scope by explicit request. It does not enable unauthenticated multi-user hosting.

## Changes delivered

### 1. Excel exports and safe re-imports

- The approved eight-tab Excel workbook remains the exact export template. The tab order, filters, column headings, formulas, named tables and director report worksheets are retained.
- Re-import preview now recognises **new customer contract rows** added to exported Excel, as well as edits to existing records. New records are created **only after a coordinator selects and approves** the proposed row. Duplicate customer/contract combinations are not silently duplicated.
- Re-import preview now recognises a complete contract row **moved between Maintenance Database and Expired**. This is a reviewed archive/reactivation action, not a deletion.
- Incomplete transfers are not proposed if previously populated fields have been lost, reducing the risk of partial cut-and-paste errors.
- Moving an existing contract into the other tab retains its **source-row cell styles**, including original site colour fills, in the next Excel export. A genuine new contract inherits the normal data-row styles.
- Record revision checks and previous-export snapshots continue to protect against overwriting a colleague's later changes.
- Both the live editable database and familiar Excel backup can be used; they must not be treated as independently authoritative versions without reconciliation.

### 2. Document review improvements

- Digitally readable PDFs and optionally extracted OCR text can be grouped into **candidate invoice groups**, identified by *printed* invoice number, with page lists, invoice dates and account references when readable.
- The Import Documents review screen now displays these page groupings and missing/unread page warnings.
- Extracted Pulse Fitness equipment stock codes are matched by **exact code** to the imported 2026 equipment catalogue and displayed with the product name. These are suggestions only, not proof of customer ownership or service entitlement.
- The importer no longer produces auto-proposals from a hard-coded handwritten Example University sample when a scanned PDF has not been read. The 21-page source document correctly reports zero extracted suggestions when OCR is not configured.
- No sales-invoice value is automatically mapped to maintenance contract revenue, and no equipment warranty date is presumed to be the agreement's expiry date.

### 3. Testing

Tested with disposable data copies (the bundled source database and Master template were not changed):

| Test | Result |
|---|---|
| `tests/smoke.py` | Passed |
| `tests/v2.py` | Passed |
| `tests/v3.py` | Passed |
| `tests/v4.py` | Passed |
| `tests/v5_fast.py` | Passed |
| `tests/v5_integration.py` | Passed |
| `tests/v5_documents.py` | Passed |
| JavaScript syntax check | Passed |

The integration test explicitly verifies creation of a new row from Excel, a complete active-to-expired transfer, source-row style preservation, an eight-tab file with valid OOXML and normal formatting on genuinely new rows.

## Important limitations

1. **Scanned handwriting OCR is not yet a working live feature.** Azure Document Intelligence credentials, endpoint approval, security review and benchmarking against real handwritten invoices are required. Even configured OCR requires field-by-field validation.
2. **PulseFitness.ai integration has not been deployed.** The application remains a local prototype bound to localhost. Shared hosting requires secured user/session attribution, storage migration, access controls and backup/recovery procedures. Microsoft sign-in is *not* a prerequisite.
3. **Sage/Sicon is not connected.** There is no automatic Sage customer/contract lookup or safe write-back yet.
4. The approved Excel template has finite preformatted table capacity; attempts to exceed this capacity are rejected rather than emitting incorrectly styled worksheets.
5. Tests validate file contents and styles at the OOXML level. **Desktop Microsoft Excel inspection is still needed** with the coordinators' version of Excel to sign off formulas, filters, charts and editing behaviour.
6. The local actor name shown in audit entries is not cryptographically authenticated. Keep the app local until existing PulseFitness.ai authentication can be reused.
7. The grouping rules are deliberately conservative: scanned documents, badly labelled invoices, duplicate page numbering and equipment schedules may require correction. No automatic approval is granted.
8. The application is a single-company internal tool, not a ready-to-market multi-tenant SaaS service.

## Run locally

Unzip the package, enter the `Pulse_Contracts_Platform` folder and run `START_PULSE_CONTRACTS.bat` on Windows (requires Python and ability to install dependencies). Visit <http://127.0.0.1:8000>.

## Safe upgrade from V4

**If you have entered real data in the existing V4 application, do not overwrite your V4 database.** Stop the old service, back up the entire existing `data/` directory, unzip V5 into a separate directory, and migrate the V4 data folder into that directory only after preserving a copy. The schema remains compatible and migrations are additive. Run smoke tests and export the Excel Master before switching staff.
