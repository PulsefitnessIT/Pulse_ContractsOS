# V9 verification — 17 October 2026

## Confirmed checks

- `tests/v9_batch_queue.py`: **PASSED** — queue status, conflict flags, reference-only asset schedule, CSV formula safety, batch with two valid invoices plus one invalid PDF, duplicates, limits, checked-source status, unchanged contract and ledger counts, unmodified Master template.
- `tests/v8_invoice_review.py`: **PASSED** — scanned Example University PDF sample; reviewed invoice evidence and audited staff changes without modifying the Maintenance Master.
- `tests/v7_matching.py`: **PASSED** — contradictory customer information and ambiguous matches require review.
- `tests/v6_ocr.py`: **PASSED** — real scanned sample invoice detection; original source preview; no direct contract changes.
- `tests/v5_integration.py`: **PASSED** — exact-layout eight-tab Excel export and reviewed register transfers.
- `tests/v5_fast.py`, `tests/v5_documents.py`: **PASSED**.
- `tests/v4.py`, `tests/v3.py`, `tests/v2.py`, `tests/smoke.py`: **PASSED**.
- Browser JavaScript syntax (`node --check`): **PASSED**.

## Important qualifications

These are local, isolated tests with sample invoice data and disposable databases. No staff pilot, shared-server load test, independent security assessment, handwriting accuracy benchmark, or desktop Excel acceptance test has yet been completed. The reviewed-source status does not certify that the document's data is correct or posted to Sage/Sicon.
