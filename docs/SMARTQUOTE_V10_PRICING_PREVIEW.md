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
