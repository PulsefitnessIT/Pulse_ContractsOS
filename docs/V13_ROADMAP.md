# V13 roadmap — contacts and preventative maintenance

**Status:** Planned, not yet implemented in this GitHub repository.

## Customer contact research
- Search approved public/official sources for the customer site telephone, shared business email, and official website.
- Store proposed details with source URL, retrieval date and confidence/evidence.
- Distinguish physical site contact versus parent billing organisation.
- Never silently replace existing verified contact records.
- Allow coordinators to accept, correct or dismiss recommendations.

Acceptance: ambiguous site names do not result in automatic changes; every approved detail retains provenance.

## PPM service history
- Import the messy DJ Service Planner March 2020 workbook using source row/cell traceability.
- Reuse the V12 proposed matches as a review queue, not as confirmation of a completed visit.
- Classify completed, planned, cancelled and unclear entries separately.
- Calculate last service from confirmed completed visits only.
- Calculate next due date using the verified agreement's servicing entitlement.
- Make repeated uploads idempotent and all approved changes auditable/reversible.

Acceptance: planned appointments are never incorrectly shown as completed; uncertain entries are reviewed.

## Usability and reports
- Show verified contacts, service history, equipment, contract, and invoices on one searchable customer profile.
- Keep the compact default contracts table.
- Preserve the familiar exact-format eight-sheet Excel export.
- Ensure new approved information contributes to appropriate reports without introducing additional verification worksheets.

## Regression gate
Run V12 tests plus new security, matching, PPM, export and concurrent-edit scenarios. No V13 release until results are recorded.
