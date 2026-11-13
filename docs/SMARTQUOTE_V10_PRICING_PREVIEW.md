# Unified SmartQuote V10 — source-based pricing preview

**Development only — not a commercially approved quotation or customer-facing PDF.**

## Integrated in the unified platform

The Contracts OS SmartQuote tab supports native, editable quotation drafts with
multiple equipment rows, Silver/Gold/Platinum cover, 1–5 year terms and discounts.

A read-only pricing preview checks exact, unique SKUs against the original V10
catalogue, configs and pricing rules. It reproduces V10 standard tariff arithmetic:

1. Annual base = original SKU RRP × standard equipment-group rate.
2. Annual unit = (base × console factor + console uplift + group uplift)
   × package multiplier.
3. Discount is applied before unit-level rounding (ROUND_HALF_UP);
   rounded unit is then multiplied by the equipment quantity.
4. The configured minimum is calculated independently; below-minimum results
   require human review.
5. Annual, monthly and multi-year totals are explicitly partial if any SKU
   is unpriced.

**This is a conservative subset of the original V10 pricing engine.** It does
not yet port inferred historical matches, static Sage fallback, manual price
approvals, dated staged-cover calculations or customer PDF issuance.

## Protected server configuration

Point the Contracts OS server at the original operational V10 files, all
outside GitHub and outside browser assets:

- PULSE_SMARTQUOTE_CATALOG_JSON — V10 data/catalog.json
- PULSE_SMARTQUOTE_CONFIGS_JSON — V10 data/configs.json
- PULSE_SMARTQUOTE_PRICING_JSON — V10 data/pricing.json
- PULSE_SMARTQUOTE_DB — optional original smartquote_local.db for historical
  browsing and direct accepted-PDF handover

Use absolute paths and read-only filesystem permissions. The original
SmartQuote application need not be running separately for this pricing preview.
Missing/corrupt source files do not generate numbers. Verify the operational
catalogue is populated; the source repository alone is not a guarantee.

## Financial safeguards

- Every preview includes SHA-256 proofs of each staged JSON input file.
- The supplied V10 source policy says its tariffs are provisional.
- Every preview reports commercially_approved=false,
  issue_quote_enabled=false and contract_setup_enabled=false.
- Missing, duplicate and ineligible SKUs cannot be silently priced.
- Unverified console types, non-active tariff groups and below-minimum prices
  are visibly marked for review.
- Price previews never write to Sage, Sicon, accepted quotation tables or
  customer-facing PDFs.
- Package PPM allowances, wear-and-tear exclusions and customer terms
  still require separate verification.

## Verification gates before further rollout

1. Run Python syntax checks, the new fictional-source V10 pricing parity
   tests, the full Contracts OS synthetic regression suite and JS syntax checks.
2. Provision an approved protected V10 data snapshot in a disposable
   staging runtime; do not store customer assets in GitHub.
3. Compare unit and grand totals against the running original V10 engine
   on known Silver, Gold, Platinum, strength console, RRP exception, staged
   start date, and discount cases.
4. Obtain commercial sign-off, verify terms and PDF hashes, rehearse recovery.
5. Do not merge to main or retire the original SmartQuote until these pass.

## Development APIs

- GET /api/quoting/drafts
- GET /api/quoting/drafts/{id}
- POST /api/quoting/drafts
- PUT /api/quoting/drafts/{id} (optimistic revision protection)
- GET /api/quoting/catalogue/search?q=... (identity only)
- GET /api/quoting/drafts/{id}/price-preview (read-only)

Development branch: feature/unified-smartquote-intake.

## Original-engine parity harness (protected staging only)

From the Contracts OS source checkout, with dependencies available and an
approved disposable copy of the full original SmartQuote V10 source/runtime:

    python scripts/check_v10_price_parity.py /protected/staging/SmartQuoteV10 --max-skus 250

The checker invokes the original V10 price_line and this integration's
matching standard-rate calculation against identical original source SKUs for
Silver, Gold, Platinum and representative discounts. It compares annual/unit
and minimum values to the penny, prints aggregate mismatch counts rather than
customer details, and returns failure status on numeric differences.

This parity check must be run in a secured staging environment; it cannot run
in public GitHub CI because the authentic operational catalogue is intentionally
not committed. A numeric pass is necessary but not sufficient for release.

## Staged contract dates — source parity, 2 November 2026

The unified draft schema now accepts optional contract_start, contract_end
and cover_start for each equipment line. Both full contract dates must pass
V10 valid_contract before a draft can be saved; per-line start dates must fall
inside the period. An incomplete two-date set is accepted for preparation but
never yields an invented term total.

The original V10 staged_contracts.py calculation is retained verbatim in
app/_smartquote_staged_v10.py (upstream blob SHA recorded in file). It prorates
annual equipment line totals on inclusive dates, using 365 or 366 days for
each calendar year, and rounds once per machine line. Stage groups are
summarised by equipment commencement date. For an unpriced machine, the
result is explicitly a partial contract estimate, not an agreed charge.

The staged contract controls are still exploratory quotation previews;
no invoices, cover activation, Sicon imports or customer documents are produced.

## Sage sales-price reference — separate evidence, not an RRP

If the configured original SmartQuote SQLite source includes a manager-imported
active Sage price snapshot, the read-only integration may show the exact item's
sales-price record, original source date, overdue review indicator and file
SHA-256. References use original active sage_price_snapshots data, including
bounded gzip decoding; the original database is never edited.

**Sage figures DO NOT enter the calculated annual or staged contract totals.**
If a product code exists in the V10 catalogue (even if it conflicts or has no
valid RRP), the Sage record is not substituted for that catalogue SKU. For
Sage-only records, a pricing manager must first verify the Master Price List,
product/console identity, coverage and approved RRP before authorising pricing.
This intentionally keeps the original system's provisional static fallback
from being presented as commercially approved in the new platform.

Added regression suites: tests/test_quote_staging.py and
tests/test_quote_sage_reference.py. A green CI result and live V10 parity
comparisons are still required before any rollout.
