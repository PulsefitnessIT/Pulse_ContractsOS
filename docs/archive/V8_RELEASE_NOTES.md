# Pulse Contracts OS — Version 8

**17 October 2026 | Local development prototype, NOT a hosted business deployment**

## Invoice recognition improvements

- Invoices are identified from **printed invoice labels**, grouped into separate source-page sets, with nearby continuation pages treated cautiously. OCR that reads the same invoice number in separate page groups is flagged for review instead of silently merged.
- Structured, source-page-linked candidates are prepared for invoice number, UK invoice date, account reference, sales order reference, separately labelled totals and equipment catalogue codes. Observed warranty wording is kept distinct from verified contract cover.
- Ambiguous OCR readings and conflicting dates are highlighted; pages with no dependable invoice number remain unassigned instead of being attached to a nearby invoice.
- The import UI has a **Check invoice evidence** card for each invoice. A coordinator can correct the printed invoice number, confirm account details, enter the handwritten contract reference and customer/site, inspect the PDF page and tick an explicit verification checkbox.
- **Manual invoice recovery** is available for pages whose printed invoice reference is unreadable. The coordinator selects the original page and records only information visible in the document.
- Verified invoice evidence is saved in dedicated `invoice_document_reviews` and `invoice_review_history` database tables. This is separate from the monthly invoice reporting ledger and the Maintenance Master.
- A verified invoice with customer/site and contract reference can be used to **prepare a contract proposal**. It goes into the existing proposal comparison/approval flow. Preparing this proposal does not edit any contract or financial record.
- Existing contract matching and Excel export capabilities are retained.

## Example University testing (real 21-page scan)

A targeted sample of PDF pages 1, 2, 3, 14–21 produced readable OCR text for all 11 selected pages. The reader proposed the printed numbers `0000003456`, `000004987`, and `0000023456` (the last occurs in separate groups at pages 16 and 19), with important limitations:

- Page 3 OCR yielded `00001224` for an account field, whereas later pages read `00001234` or `0001234`. These are **not accepted as the same verified account**. A reviewer must check the paper scan.
- Several pages had no safe invoice-number extraction and remain unassigned for manual checking.
- The handwritten contract references were **not** reliably recovered; they still require coordinator transcription and approval.
- OCR produced possible warranty phrases and stock codes; it did **not** assert contract expiry dates or recurring maintenance values.
- The manual review API and staged-contract-proposal process were exercised on a disposable database, with no Master changes.

## Run locally

Extract the ZIP to a separate folder and use `START_PULSE_CONTRACTS.bat` on Windows with Python 3.11+ installed. Install Tesseract OCR separately for scanned PDF reading; `PULSE_OCR_MODE=local` requests local recognition. A configured Azure Document Intelligence service is an optional alternative. There is no live OCR/AI subscription or access key bundled with the software.

**Upgrade safely:** The ZIP includes a copy of the pilot SQLite database. Back up and retain the existing installation's entire `data` directory (including `uploads`), then move updated code into the approved location. Do not overwrite live office records with the sample database. The new tables are created additively on startup.

## What remains unproven / blocked

- Unattended handwriting recognition is **not** reliable. Manual confirmation remains required.
- This has not been deployed into PulseFitness.ai, hosted for concurrent staff, or given trusted access controls. Microsoft sign-in remains parked.
- Sage/Sicon live read/write is not connected.
- Real-world accuracy rates on a large labelled test set and desktop Excel acceptance testing still need to be completed.
- Invoice evidence is intentionally **not automatically posted to the financial ledger**. Posting requires an explicitly designed accounting workflow that prevents equipment invoices being counted as maintenance income.

## Regression tests

`tests/v8_invoice_review.py` exercises sample evidence grouping, conflict detection, source verification, rejected invalid reviews, audited corrections, manual OCR fallback, staging a contract proposal, and preserving the Maintenance Master. `tests/v6_ocr.py` runs a small real scanned PDF fixture if available. Existing V2–V7 tests are retained.
