# SmartQuote — Everyday-use release acceptance

**Release decision: NOT YET APPROVED.** This is the working founder/technical
checklist for a Contracts Coordinator product, not a director-demo checklist.

## Build policy

Until all critical gates are accepted, continue software development on
`feature/unified-smartquote-intake`, keep PR #5 in draft, and run source,
security and automated acceptance tests. **No automatic Windows executables,
installation bundles or releases.** Packaging workflows are manual-only.

## What an everyday coordinator must be able to do

1. Open SmartQuote with their own login; see plainly what to do first.
2. Find a customer/site without inventing a legal name or cover entitlement.
3. Start from the approved equipment catalogue **or** upload up to 12 sales
   invoice PDFs in one screen, then verify extracted item codes.
4. Edit machine model/code, serial, cover start and quantity without removing
   the whole quote. Recover an inadvertently removed line.
5. See and correct duplicate serials, unmapped items, OCR misses, conflicting
   consoles, outdated Sage prices and incomplete contract dates.
6. Save and later reopen a draft without losing their work. A separate user's
   edit must cause a revision conflict, never silently overwrite.
7. See **Silver, Gold and Platinum** using the same machines and dates.
   Incomplete variants must show no false final amount.
8. Prepare an INTERNAL, clearly marked PDF with correct customer/site,
   equipment, serials, dates, pricing, exclusions and financial totals.
9. Submit a quotation for named Administrator review. Outstanding serials
   require a documented manager exception, not a fabricated number.
10. Obtain a numbered customer PDF only after approved terms, issuer details,
    V10 service tariffs, source fingerprints and individual quote sign-off.
    Issued PDFs must be immutable and downloadable afterwards.

## Release gates — all mandatory

| Gate | Objective proof | Status |
| --- | --- | --- |
| Data import and preservation | Signed-off Master/Sage/V10 snapshots; customer/site counts and archived quotes reconciled | Pending real-data acceptance |
| Equipment coverage | Unambiguous SKU, console/strength variant and maintenance eligibility; every exception reviewable | In progress |
| Commercial model | Named responsible manager signs the original V10 Silver/Gold/Platinum rates, minimums, discount rules and cover exclusions | Awaiting commercial sign-off |
| Pricing accuracy | Recreate at least 10 real historic quotations covering current models, Sage-only legacy, multiple serials, discounts, staged dates and all 3 tiers; explain every difference | Pending real-world parity |
| Invoice-assisted entry | At least 5 representative multi-page/poor-scan invoices reviewed against their originals; no parts wrongly treated as maintainable machines | Pending real-world OCR UAT |
| Coordinator usability | At least 3 real coordinators independently complete a new quote, saved-edit quote, invoice-to-quote and renewal scenario without developer intervention; address blocking confusion | Pending human testing |
| PDF / legal | Director approves actual one-to-one customer PDF content, issuer identity, VAT, maintenance T&Cs and exclusions | Pending document sign-off |
| Access and audit | Two simultaneous coordinators, Admin, Viewer, login/logout/expiry and full quote/source history verified | Automated coverage; manual test pending |
| Resilience | Dedicated secure private data storage, off-host backup, actual restore, regression tests and documented rollback | Pending IT acceptance |
| Release engineering | Latest commit: Python 3.11 and 3.12 tests, Node coordinator tests, dependency audit and server image pass; final Windows pack built **once** and tested using protected representative runtime | Pending final release commit |

All **customer files, Sage prices, contract workbooks and signing secrets** stay
outside the public GitHub repository. Do not publish a pilot/data folder,
real source ZIP, invoice PDF or customer quotation as a CI artifact.

## Non-negotiable product rules

- **Equipment source precedence:** verified current August Master List Price,
  then exact Sage Sales Price for eligible legacy equipment absent from that
  Master. Source price comparisons are informational, not a new arbitrary
  percentage-approval threshold.
- Positive Sage price or invoice-detected code **does not** prove a machine is
  maintenance-eligible.
- No guessed console, model, serial, warranty entitlement, legal customer,
  quote value or maintenance tariff.
- Never overwrite staff-edited contract records with a newly exported Master
  without reconciliation.
- No partial totals presented as full customer offers.
- Quotes with missing individual serials must archive the responsible
  manager's specific exception reason.
- A complete quote comparison or passing developer test **never** authorises
  the underlying service percentage rates or commercial terms.
- A frozen issued quote never changes retroactively after a Sage refresh.

## Founder's release rule

Do not mark the software ready for everyday use until all gates have named
owners, evidence and explicit acceptance. A passing CI run is necessary, but
not sufficient. The implementation should remain a draft PR until then.
