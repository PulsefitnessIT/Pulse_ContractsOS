# Pulse Contracts OS — Version 9 (17 October 2026)

## Focus: practical batch document intake and a coordinator-friendly review queue

This update extends V8 rather than replacing the approved Contracts Master, the equipment catalogue or the existing import/approval controls.

### Implemented and tested

1. **Multiple-file intake** in the existing Import Documents page. Staff can select or drop up to 12 documents at a time, with a maximum of 20 MB per file and 60 MB total. Each upload is passed through V8's original duplicate prevention and safe PDF/CSV/XLSX extraction; a bad file is reported separately rather than blocking the rest.
2. **Invoice review work queue**: one row per identified invoice group, plus unassigned/unreadable pages where applicable. It shows the uploaded file, detected invoice reference, relevant page(s), next action, and whether a coordinator has checked the original source.
3. **Triage, not invented confidence scores**: detected conflicts, absent invoice dates, and OCR-based text are explicitly flagged. Equipment-register pages are marked **Reference only** rather than automatically classified as invoices.
4. **Verified-source status** updates when a coordinator saves evidence, but does **not** mean that the agreement, financial entry or asset list has been approved or modified.
5. **Downloadable CSV review queue** for an operational handover; imported strings are escaped to prevent spreadsheet formula execution.
6. **No changes to the eight-sheet approved Excel export**, the bundled source workbook, or any existing contract and financial records.

### Where staff find it

Open **Import Documents**. Choose multiple PDFs, CSVs or XLSXs, then review the batch result. The new **Invoice review work queue** sits beneath the Excel round-trip section. Filter by Needs review / Source verified / Reference only; select Review to open the existing document/evidence screen.

### Tested

- New `tests/v9_batch_queue.py` checks triage, reference-only asset schedules, duplicate detection, invalid files in a batch, review-to-queue status updates, per-batch limits, CSV delivery and neutral effect on contract/ledger totals.
- Existing V2–V8 tests passed (see `V9_TEST_REPORT.md`).
- JavaScript source passes Node syntax checking.

### Limitations, not production-ready

- Handwritten contract references still require human confirmation. Local Tesseract recognises printed text, not dependable handwritten contractual terms.
- The batch endpoint works sequentially and may be slow on long scanned PDFs; there is no background job system yet.
- The queue covers the latest 200 imported documents and does not assign individual staff or due dates.
- The prototype is still local-only with no trusted shared office access. Do not expose it publicly or treat the handwritten invoice pilot as validated recognition accuracy.
- Source verification and posting into the Maintenance Master are separate approval operations.
- Microsoft sign-in remains parked at the user's request.
