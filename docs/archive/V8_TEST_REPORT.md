# V8 QA report — 17 October 2026

## Automated tests in disposable environments

| Suite | Result | Coverage |
|---|---|---|
| `tests/smoke.py` | Passed | contract edits, source handling, reporting, Excel Master export |
| `tests/v2.py` | Passed | equipment catalogue and new-row Excel styles |
| `tests/v3.py` | Passed | PDF evidence and approval workflow |
| `tests/v4.py` | Passed | revision conflict prevention, renewals, Excel round-trip, backup |
| `tests/v5_documents.py` | Passed | no fabricated text when OCR is deliberately switched off |
| `tests/v5_fast.py` | Passed | invoice grouping and Excel moves |
| `tests/v5_integration.py` | Passed | workbook new/moved records, site colours, eight-tab export |
| `tests/v6_ocr.py` | Passed | actual scan, original page preview, no auto updates |
| `tests/v7_matching.py` | Passed | account/site/contract matching and conflicts |
| `tests/v8_invoice_review.py` | Passed | verification, manual unreadable-page workflow, source attribution, audit history, staging safe contract proposals |

The V8 test suite used the real Example University PDF pages 3 and 16. A separate 11-page targeted OCR run was also inspected. No accuracy percentage was calculated from this single customer example. OCR hallucinations and false positives are still possible; the purpose of the gate is reviewability and avoiding silent contract changes.

## Required before company-wide rollout

Have coordinators validate diverse real invoice scans in the UI, complete an annotated correctness benchmark, inspect the Excel workbook in desktop Excel, test shared access/backup/restore, and obtain approval of the local data-handling and security approach. This is not a production certification.
