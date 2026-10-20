# Pulse Contracts OS V7 — Test Evidence

- `tests/v7_matching.py`: synthetic match-policy tests and real baseline database API checks, including duplicate references, contradicted customer sites, shared invoice accounts, read-only matching, preview and old-layout Excel export.
- `tests/smoke.py`: contract lifecycle, approvals, invoice/weekly entries, export, reporting and preservation of reference worksheet XML.
- `tests/v2.py`: equipment catalogue lookup and new-record formatting in template export.
- `tests/v3.py`: document candidate review, explicit conflict approvals and source lookup.
- `tests/v5_fast.py`: invoice grouping and Excel active-to-expired moves.
- `tests/v5_documents.py`: real scan unread-page detection (OCR disabled in safety test), text-PDF evidence and catalogue product lookup.
- `tests/v5_integration.py`: full eight-tab edited-Master comparison and safe Excel re-import transfer.
- `tests/v6_ocr.py`: real scanned-PDF printed-text recognition, image/page evidence and invoice OCR conflict warnings.

Tests use isolated temporary database copies or recreated temporary databases; the user-supplied Maintenance Master and existing V6 ZIP are not modified.

**Limits:** Automated tests do not certify live hosted security, reliable handwriting interpretation or Excel's desktop rendering/repair-warning behaviour. The V4 extended round-trip regression can be lengthy and must be explicitly checked before production release.
