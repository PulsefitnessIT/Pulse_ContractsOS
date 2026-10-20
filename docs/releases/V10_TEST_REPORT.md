# Version 10 critical-priority test report

Tested **17 October 2026** on an isolated copy of the V9 pilot database, not the live PulseFitness.ai environment.

## Passed

- Protected pilot: unauthenticated request rejected (401); Viewer write rejected (403); write without CSRF rejected (403).
- Two coordinators editing the same contract revision concurrently: exactly one HTTP 200 and one HTTP 409; persisted change attributed to authenticated user rather than client-supplied username.
- Two coordinators adding weekly value entries concurrently: two separate Excel source rows allocated; no source-row collision.
- Eight-tab Excel export quality: all worksheet names/order, active/expired column parity, key columns, five table filters and structure checks passed; 642 active and 8,381 historical records in unchanged sample database.
- Excel export integrity under a concurrent-edit test: exported workbook structurally valid; table filters and formulas retained as supported by the template.
- Recovery bundle: SQLite online snapshot, original workbook, product catalogue and test uploaded document packaged; hashes verified; complete extracted snapshot validated in disposable directory; 9,023 contracts and 3,570 ledger entries present in sample data.
- Earlier smoke, V4 Excel round-trip, V5 fast comparison, V8 invoice review, V9 batch-import/review tests passed independently during this development turn.

## Partially tested / not established

- V7 matching test printed its matching assertions as passed, but a combined regression command timed out after its output; a complete clean full-suite run is **not claimed**.
- Hosted shared access and remote TLS connectivity **not tested**: the available environment cannot deploy a live staff server.
- Real desktop Microsoft Excel acceptance **not tested**: checks validate OOXML structure and content but not Excel's visible user interface or printing.
- OCR accuracy across 50–100 varied invoices **not tested**; quality meter starts with no verified sample and cannot claim real-world accuracy.
- No full security penetration test, no failover test, no production off-host disaster recovery, no live Sage/Sicon integration.

## Workbook template headroom in the bundled pilot sample

| Register | Free preformatted rows |
|---|---:|
| Maintenance Database | 160 |
| Expired | 113 |
| Weekly Values | 120 |
| Invoices | 130 |
| Quotes | 100 |

A future release should automatically extend these Excel tables without altering the approved visible layout. Until then, the application explicitly blocks additions that would exceed template capacity.

**Disposition:** Suitable for further isolated technical testing; **not authorised for company-wide live use**.
