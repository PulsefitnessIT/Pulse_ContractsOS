# Pulse Fitness SmartQuote — release gates and execution backlog

**Prepared:** 3 November 2026  
**Delivery target:** One staff-facing SmartQuote module inside Contracts OS.
**Current decision:** Original V10 stays the internal reference; the unified
module is not yet permitted to issue real customer quotations.

## Evidence baseline

Original repository: `PulsefitnessIT/Pulse_SmartQuote`, source branch
`feature/contracts-os-accepted-handoff`. Original V10 includes equipment
import, matching, historical identity, pricing, local approval exceptions and
watermarked/PDF version archiving. The original `data/pricing.json` describes
its tariffs as **provisional**. The pricing source metadata states 4,012 SKU
rows, 490 service configurations and 635 legacy crosswalk rows; these are
reported source counts, not confirmation of pricing accuracy or completeness.

Integration: `PulsefitnessIT/Pulse_ContractsOS`,
`feature/unified-smartquote-intake`. The native module implements draft
persistence, restricted SKU catalogue lookup, partial V10-standard pricing
preview, date staging, read-only Sage references, historical quote viewing,
accepted archived-PDF intake and a contract-setup review workbench. It does
**not** yet issue a priced, commercially authorised PDF directly from the
unified platform, and the full original engine parity has **not** been
established on a protected real catalogue snapshot.

## P0 release blockers

- [ ] **SQ-01 | Freeze and validate source evidence.** Privately stage the
      complete original V10 runtime/database and the approved 2020–2026
      equipment masters. Document source date, owner, SHA-256, exact unique SKU,
      duplicates, legacy variants, console options, original quote count,
      PDF-version count and unresolved RRP values. Never commit customer
      records, original master pricing or signed PDFs to GitHub.
  - Owner: contracts data owner + IT; gate: every imported source item is
    traceable to an exact authoritative source or explicitly unapproved.
- [ ] **SQ-02 | One canonical catalogue.** Bring Master Price List and
      equipment catalogue identity into one controlled interface with
      manufacturer, current and legacy SKU, model, console, original and
      approved RRP, effective date, coverage eligibility and notes. Retain
      historical identities as evidence without treating old prices as current.
  - Gate: no duplicate/ambiguous SKU silently auto-selected; unknown RRPs
    cannot be substituted or shown as verified prices.
- [ ] **SQ-03 | Full engine parity.** Port/reuse actual original V10 equipment
      matching and price rules, including console, minimum floor, discounts,
      quantity rounding, term/year stages, leap-year cover and negative cases.
      Freeze rule-version and approved input snapshots on each issued quote.
      Run `scripts/check_v10_price_parity.py` on protected authentic sources.
  - Gate: no penny discrepancies on the agreed representative source cases
    covering Silver, Gold and Platinum, legacy, strength console, staged dates,
    manual rates, minimums, discounts and Sage-only/ambiguous SKUs.
- [ ] **SQ-04 | Commercial policy approval.** Obtain written service director
      / pricing manager approval of Silver/Gold/Platinum rate and package
      factors, PPM, wear parts/belts/transport exclusions, pricing floors,
      manual override permission and discount thresholds. Version approval by
      effective date, approver and exact source hash. Allow instant issue of
      compliant routine quotes; route ONLY policy exceptions for manager
      approval. A Sage sales-price row is not automatically approved RRP.
  - Gate: API cannot issue an unapproved rate, restricted manual price,
    unresolved SKU, or unapproved discount.
- [ ] **SQ-05 | Customer-ready numbered PDFs.** Integrate approved Pulse
      branded maintenance quotation template, line totals, term totals,
      coverage, VAT treatment, validity date, customer/site, equipment/serial
      rows, exclusions, service visits, source/effective tariff version.
      Give every issued revision a unique number, PDF SHA-256, immutable
      snapshot and reproducible lookup; keep preview PDFs watermarked.
  - Gate: 100% of issued PDFs reproduce approved values; old bytes remain
    retrievable even after catalogue or pricing changes.
- [ ] **SQ-06 | Data migration.** Move original V10 quote register, assets,
      customer/site references, pricing evidence, signed/versioned PDF
      snapshots and history to a private staging store, with idempotent
      migration and rollback. Do not merge legal customer names from fuzzy site
      matches.
  - Gate: original and target record counts/hashes and exceptions reconcile;
    all historical issued PDFs verify SHA-256.

## P1 UAT / internal launch blockers

- [ ] **SQ-07 | One upload panel.** Upload PDF sales invoices, asset
      spreadsheets, historical calculation workbooks and previous agreements,
      with explicit detected type and review before mutation. Handle multiple
      invoices, quantities, duplicate serials, new/legacy machine codes,
      excluded/non-Pulse rows and console options; preserve source document
      and the original equipment rows. Make a repeat upload idempotent.
  - Gate: all agreed representative real but protected file fixtures have
    zero silent omissions, duplicated assets or unexpected customer merges.
- [ ] **SQ-08 | Clear coordinator workflow.** Existing site selection ->
      one upload -> match exceptions -> choose tier and terms -> preview price
      -> approve only true exceptions -> issue PDF -> record outcome. Reopen
      saved work without losing history, with optimistic concurrency.
  - Gate: two coordinators can complete representative quotations without
    developer help; routine case target <=5 minutes, measured, not assumed.
- [ ] **SQ-09 | Acceptance and contract handover.** Separate 'quote issued'
      from 'sent', 'customer accepted', 'signed agreement checked' and 'contract
      active'. Preserve evidence and immutable PDF. Pass a reviewed accepted
      quote into Contracts OS only once; keep Sage/Sicon actual writes disabled
      until their sandbox mapping and permissions are validated.
  - Gate: no false acceptance/active status, duplicate contract or unapproved
    value transfer.
- [ ] **SQ-10 | Hosting, identity and recovery.** Use protected server
      staging, central MFA/identity policy where approved, auditable roles,
      HTTPS, security assessment, off-server backups, full restore rehearsal,
      data retention rules and concurrency/load tests. Select and validate
      final persistent storage architecture.
  - Gate: IT/security signs off and backup restore is witnessed.
- [ ] **SQ-11 | Commercial and coordinator acceptance.** Run baseline
      matching accuracy, case coverage and full end-to-end quote->PDF->handover
      scenarios with sales/maintenance managers and two coordinators.
  - Gate: 100% of issued line totals reconcile to approved source,
    no unresolved critical data/price/security defects, recorded sign-offs.

## Release strategy

**Release A — controlled internal quotation issue:** When SQ-01 to SQ-08,
SQ-10 and SQ-11 pass, staff may issue commercial PDFs while recording sending
and acceptance manually and retaining Sage/Sicon handoff under review.
Completion of SQ-09's **manual evidence and idempotent reviewed handover**
portion is required; live Sage/Sicon write transport is not.

**Release B — automated contract activation:** Only after explicit Sicon/Sage
sandbox testing, field mapping, duplicate prevention, audit trail and rollback
approval. These write integrations are not a dependency for a safe internal
quotation issuance release.

**Production guard:** Do not flip a pilot/live environment flag to bypass
pricing or security gates; require explicit version-controlled authorisation
with independent commercial and IT sign-off.

## Critical decisions for company owners

1. Which approved 2026 Master Price List and effective RRP rules are
   authoritative? Which Sage RRP list can be used only with manager approval?
2. What exact Silver, Gold, Platinum formulas and coverage exclusions are
   authorised, including base rate, package multipliers, discount and floor?
3. Who is permitted to approve an exception and to issue customer documents?
4. Is first release allowed to use reviewed/manual contract activation while
   preserving a traceable accepted-quote record? (Recommended: yes.)
5. Who signs commercial policy, IT security, source-migration reconciliation
   and coordinator UAT before release?

**No customer-specific values or approved pricing have been invented in this
backlog.**
