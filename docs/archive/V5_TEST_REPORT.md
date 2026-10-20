# V5 quality check — 17 October 2026

All seven command-line test suites passed on test copies. JavaScript passed `node --check`.

| Test | Verified |
|---|---|
| Smoke | 642 active and 8,381 expired source records import; editing, archiving, notes, history, financial summaries, original Excel package export |
| V2 | Equipment catalogue matching, approved equipment linking and normal new-row Excel styles |
| V3 | Digital PDF contract/invoice/reference separation; source retention; duplicate upload rejection; conflict approval |
| V4 | Version locking, renewal history, approved Excel diff/apply, conflicts, backup creation |
| V5 fast | Printed invoice page grouping with continuation pages and unassigned equipment schedule pages; new vs transferred Excel records |
| V5 integration | Create a genuinely new Excel contract, move a full row to Expired, reject stale overrides, retain original site-row styles; valid eight-tab export |
| V5 documents | The actual 21-page scanned invoice does not yield fictional contract data without OCR; synthetic readable PDF generates printed invoice group plus exact 260G-AAP catalogue match |

A **negative OCR result** is an expected and important safety finding, not proof of live OCR performance. No source/customer production records were modified in these tests.

Outstanding sign-offs: live OCR accuracy, Excel desktop compatibility, PulseFitness.ai authenticated hosting, Sage/Sicon read-only integration, genuine simultaneous multi-user load, secure off-site backup restoration and supplier data processing approval.
