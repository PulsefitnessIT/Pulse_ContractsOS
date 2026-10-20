# Pulse Contracts OS — V6 document-reading and source-review release

**17 October 2026. Local Windows/Python pilot only. Not yet hosted or integrated with PulseFitness.ai.**

## Delivered

1. Optional, real offline PDF OCR using the Tesseract executable. A local file is rendered page by page; detected text is treated as **unverified evidence**, not as a confirmed maintenance agreement. Rotated pages may be reprocessed at 180° when extraction looks unconvincing. No external OCR account is required for offline mode. Windows requires installation of Tesseract (not included in this ZIP).
2. Scanned and digital PDF text can be combined; the importer keeps a list of unread pages, reading sources and page rotations. Alternative Azure OCR continues to be optional for approved IT use.
3. Original page preview is embedded directly inside the Import Documents review screen, with previous/next page controls and source links from invoice groups/equipment candidates. Rotated pages are displayed upright when OCR identified that orientation.
4. Potentially confusable OCR invoice numbers are **flagged**, not automatically merged or approved. Same-file duplicate blocking, field conflict review, equipment matching and exact-format Excel export remain in place.
5. Added local backup **restore drill** and release preflight scripts. These validate only local database consistency and readiness checks; they are not substitutes for real off-site backups or a security review.

## Evidence from the real 21-page Example University PDF

- Offline OCR returned candidate text from **21/21 pages** in a controlled environment with Tesseract installed (approx. 24 seconds on the test machine).
- Page 1 required 180° rotation to read the equipment schedule more sensibly.
- Printed invoice `0000023456` was found on pages 16 and 19.
- OCR produced other candidate invoice numbers, including values that may represent **misread duplicates**. Four invoice groups were tentatively formed, not a verified invoice inventory. Human verification is required.
- **Neither handwritten contract number was automatically recovered reliably.** The application must not create or change a contract based on OCR alone.
- In the test, importing two scanned pages did not change active/expired contract records. Page images were served for checking and re-uploading the same document was recognised as a duplicate.

## Running OCR locally

Set `PULSE_OCR_MODE=auto` (default) to use an approved Azure connection if configured, or installed Tesseract locally. `PULSE_OCR_MODE=local` uses Tesseract only; `PULSE_OCR_MODE=off` skips all scan OCR. If Tesseract is not in the system PATH, set `PULSE_TESSERACT_PATH` to the executable's full path.

The local pilot limits a single OCR pass to the first **35 unread pages**. Slow or unreadable pages remain visible for manual checking. OCR reads printed text best; it is **not a handwriting-quality guarantee**. The page preview endpoint is meant for a localhost pilot and must be protected before shared deployment.

## Tested

- `tests/v6_ocr.py` — actual scanned pages, source preview, invalid PDF check, no unauthorised update, duplicate prevention: PASS.
- `tests/smoke.py` — contract lifecycle, import approval, ledger, reports, exact-format export: PASS (OCR disabled to preserve the legacy safety scenario).
- `tests/v2.py`, `tests/v3.py`, `tests/v5_fast.py`, `tests/v5_documents.py`, `tests/v5_integration.py`: PASS.
- JavaScript syntax and Python compilation: PASS.
- **Full V4 regression suite did not finish in the available time and is not counted as passed for V6.** Desktop Excel verification also remains outstanding.

## Not production-ready

- Real-world staff OCR benchmarking and invoice segmentation/matching, especially handwriting, are incomplete.
- Sage/Sicon read-only data reconciliation and customer-to-equipment migration remain incomplete.
- PostgreSQL/shared hosting, secure user identity via the existing PulseFitness.ai session, roles, upload malware checks, encryption, remote backups, source-document lifecycle and monitoring remain incomplete. Microsoft standalone sign-in remains parked.
- Excel exports have automated structural checks but still need visual and operational sign-off in desktop Microsoft Excel; the fixed approved template currently has finite preformatted row capacity.
