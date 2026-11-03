# SmartQuote Phase 1 — source-backed equipment reconciliation and V10 price parity

**Date:** 3 November 2026  
**Development branch:** `feature/unified-smartquote-intake`  
**Status:** Engineering progress, **not commercially authorised** and **not deployed**.

## What is now implemented

1. **Verbatim original V10 price_line arithmetic**
   - `app/_smartquote_price_line_v10.py` contains the exact original
     `engine.price_line` function body from
     `PulsefitnessIT/Pulse_SmartQuote`,
     `feature/contracts-os-accepted-handoff`, `engine.py` Git blob
     `b40a845ec9abc751ceff16574208fb7995168a8e`.
   - It executes with independent, source-derived pricing mappings for
     each call, so concurrent coordinator previews do not mutate a global
     pricing state.
   - `app/quote_pricing.py` now calls this original logic for exact unique
     SKU, standard-level RRP pricing. Source-eligibility, invalid quantity,
     discounts, console identity, missing RRP and approvals remain guarded.
   - The prior V10 inclusive ACT/ACT staged-date routine remains intact in
     `app/_smartquote_staged_v10.py`. Manual and historical V10 arithmetic
     branches are regression-tested as *reference only*. This does **not**
     enable arbitrary historical or Sage-derived prices on customer quotes.

2. **Canonical catalogue and original legacy-code analysis**
   - `GET /api/quoting/catalogue/reconciliation` returns source-provenance
     hashes and aggregate SKU, duplicate, unmapped, missing-RRP, console,
     legacy-code and historical-index completeness counts.
   - `GET /api/quoting/catalogue/reconciliation/worklist` displays
     source-linked review items, paginated, without any RRP figures.
   - `GET /api/quoting/catalogue/legacy/resolve?code=...` resolves a *whole*
     original legacy code to possible current SKUs. Multiple target SKUs
     remain ambiguous; even one mapped target needs staff identity review.
   - `GET /api/quoting/catalogue/historical/search?q=...` can look up
     the authentic 2020–2026 historical identity index by whole/partial SKU,
     model, name or prior alias. It returns original model, console, year
     and source descriptions only: **no historical RRP or replacement SKU
     approval**.
   - A read-only equipment reconciliation and historical-model search panel
     is available from the unified **SmartQuote** workspace. No catalogue/
     Master Price List editing, legal coverage sign-off or customer issue
     controls were enabled.

3. **Pin exact private source snapshots**
   - `scripts/pin_smartquote_v10_sources.py` creates a new SHA-256 manifest
     in the **private staging filesystem** after IT confirms the original
     V10 source snapshot. It will not overwrite an existing manifest.
   - `PULSE_SMARTQUOTE_SOURCE_MANIFEST`, when configured, makes the pricing
     preview fail closed if an original catalogue, service-configuration or
     pricing-policy source differs from its privately pinned hash.
   - A pinned hash proves **the identity of the files**, not commercial
     approval of RRP, packages, rates or customer agreement terms.

4. **Stronger original-engine parity gate**
   - `scripts/check_v10_price_parity.py` verifies that the vendored V10
     function matches the original V10 function source exactly.
   - Using an authorised complete original V10 runtime, it samples across
     rate groups and console variants and compares original source engine,
     isolated original-function execution and the unified preview.
   - Each selected source item is checked for Silver/Gold/Platinum, three
     discounts, three quantities (27 numerical cases per source SKU).
   - Any discrepancy or unexpectedly blocked comparison causes a
     **nonzero exit**; exclusions are counted but cannot count as tested
     prices. The report contains no customer-specific data or values.
   - The original `data/catalog.json` was not available as a usable,
     IT-staged real source in this development session. Therefore a
     real-source complete parity report does **not** yet exist. CI exercises
     synthetic cases only.

## How IT stages the source evidence

Never copy real customer files, catalogue price lists or signed PDFs into
the source repository. On an access-controlled isolated staging host:

1. Securely copy the authentic full V10 runtime with:
   `engine.py`, `data/catalog.json`, `data/configs.json`,
   `data/pricing.json`, `data/legacy.json` and
   `data/historical_catalogue_index.json` (or `.json.gz`) where present.
   The currently recorded original V10 pricing JSON describes its tariff
   policy as **provisional**.
2. Record the original source owner/date (from evidence, not inferred) and
   create a **new** manifest (example path only):

```bash
python scripts/pin_smartquote_v10_sources.py \
  --smartquote-root /secure/v10-original \
  --output /secure/smartquote_source_manifest.json \
  --owner "Actual authorised source custodian" \
  --effective-date 2026-11-03 \
  --confirm-source-snapshot
```

3. Configure these host-managed environment variables (do **not** publish
   their private paths as public deployment examples):

```text
PULSE_SMARTQUOTE_CATALOG_JSON=/secure/v10-original/data/catalog.json
PULSE_SMARTQUOTE_CONFIGS_JSON=/secure/v10-original/data/configs.json
PULSE_SMARTQUOTE_PRICING_JSON=/secure/v10-original/data/pricing.json
PULSE_SMARTQUOTE_LEGACY_JSON=/secure/v10-original/data/legacy.json
PULSE_SMARTQUOTE_HISTORICAL_INDEX=/secure/v10-original/data/historical_catalogue_index.json.gz
PULSE_SMARTQUOTE_SOURCE_MANIFEST=/secure/smartquote_source_manifest.json
```

   Use the correct JSON (not gzip) historical path if that is what the
   authentic runtime contains. Leave a path **unset** rather than pointing
   to guessed, empty or synthetic source material.
4. Generate the private reconciliation status report, resolve duplicates,
   missing RRPs and ambiguous console/service mappings with the data owner.
5. Run the strict original-source parity check in the same isolated
   environment:

```bash
python scripts/check_v10_price_parity.py /secure/v10-original --max-skus 300
```

   The checker requires the original engine's own helper modules; copy the
   authentic release as an intact runtime rather than an isolated
   `engine.py` file. Do not allow internet-facing access to that test
   runtime.

## Important original V10 facts / caveats

The original `data/pricing.json` records approximate source metadata:
**4,012 SKU rows, 490 service configurations and 635 legacy crosswalk
rows**. These **are metadata counts** and have **not yet** been independently
reconciled against the private source records in this branch.

The authoritative price hierarchy, historical catalogues, console variants
and signed customer price conditions must be approved by Pulse Fitness's
commercial/data owners. Historical 2020–2026 model evidence can identify a
machine, but **must not** be promoted to a current RRP or quotation rate.

Sage Sales Price records remain reference-only. Source rate `Active` is an
operational label, **not** a commercial pricing approval. Neither a pinned
manifest nor an exact arithmetic match changes those controls.

## Remaining Phase 1 release blockers

- [ ] Private source verification of the complete authentic V10 product,
      service, legacy and historical 2020–2026 masters and exact row counts.
- [ ] Manager/data-owner resolution of duplicate current SKUs, missing RRPs,
      legacy conflicts, source console rules and inactive rates.
- [ ] Written approval of current RRP precedence, approved fallback sources,
      maintenance tiers, discounts, minimums and exclusions.
- [ ] Strict **real-source** parity report using all relevant rate/console
      groups, with no unexpected missing comparisons or penny differences.
- [ ] Source-controlled effective-dated approval workflow and exception
      rules; no ability to approve a tariff by simply setting a JSON flag.
- [ ] Unified invoice/asset/document import and exact historical-customer
      migration, customer-ready PDF issuance and server deployment follow
      in later workstreams.

The latest synthetic GitHub CI is necessary but **not sufficient** for any
customer quotation. `commercially_approved=false`,
`issue_quote_enabled=false` and `contract_setup_enabled=false` are
intentionally retained.
