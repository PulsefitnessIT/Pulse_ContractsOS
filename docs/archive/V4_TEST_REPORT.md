# Pulse Contracts OS V4 — Test report
**Date:** 17 October 2026

This build was tested using isolated temporary copies of the approved Maintenance Master and the platform database. No real contract records in the shipped demo database were changed by the tests.

| Suite | Scope | Result |
|---|---|---|
| `tests/smoke.py` | Active/expired imports, contract edits, archiving, weekly/invoice reports, legacy file import and eight-sheet Excel output | PASS |
| `tests/v2.py` | Equipment catalogue lookup, field suggestions, new contract row styling, Excel formulas and table definitions | PASS |
| `tests/v3.py` | PDF evidence, duplicate-document prevention, explicit field conflict approval, manual scanned PDF proposals, equipment linking | PASS |
| `tests/v4.py` | Version locking, renewal audit, Excel download tracking, three-way comparison, reviewed field updates, weekly values re-import, conflict rejection and local backup | PASS |
| JavaScript syntax | `node --check app/static/app.js` | PASS |
| Python compilation | `python -m compileall -q app` | PASS |

**Not tested:** full Microsoft Excel desktop re-save/reopen, network-hosted concurrency and security, live OCR service, existing PulseFitness.ai user identity, real Sage/Sicon APIs, and independent data reconciliation with source systems. These remain rollout gates.
