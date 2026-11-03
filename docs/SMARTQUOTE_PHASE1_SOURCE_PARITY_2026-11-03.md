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

## Continued development — provenance and exception integrity

- The reconciliation summary now counts SKU-less source rows explicitly and
  includes them in the read-only catalogue exception worklist, retaining the
  original one-based source-row position rather than silently omitting them.
- The new read-only endpoint
  `GET /api/quoting/catalogue/reconciliation/legacy-worklist` shows the
  original crosswalk source-row position, old codes, recorded target SKU and
  factual mapping issues **without any RRP or proposed approved price**.
  Issues include missing/invalid old identifiers, invalid original rows,
  missing/invalid current SKU targets, duplicate target SKUs and crosswalks
  that point the same historical code to multiple products.
- A historical code with one real target **and** one missing/invalid target
  is now explicitly ambiguous: a coordinator must not auto-select the single
  remaining candidate.
- Missing-target counts are source **row** counts, not double-counted where
  a row contains both `old_code` and `old_sku`. Distinct ambiguous mappings
  and unresolved target references are reported separately.
- The SmartQuote reconciliation UI now includes the legacy worklist and
  missing-SKU source lines. The legacy list is read-only.
- New private manifests pin the optional `legacy.json` and
  `historical_catalogue_index.json` / `.json.gz` files when present.
  The manifest script refuses ambiguous dual historical index files.
  When source fingerprints are pinned, reconciliation and historical lookup
  fail closed if these evidence files change, disappear, or are added without
  a matching hash. The pricing-only preview continues to verify the three
  original V10 pricing sources.
- All these changes are **engineering safeguards**. They do not approve a
  tariff or enable customer quotation issuance.

### Source custodian note

After the verified private legacy/history evidence is staged, IT should
generate a **new** protected manifest rather than editing the old one or
committing evidence files to GitHub. The original manifest creation command
below now records optional evidence where present. When source evidence is
changed legitimately, it must be re-verified and pinned through a new,
recorded IT source-signoff operation; simply replacing a hash is not approval.

## Next development slice — tariff identity conflicts and traceable source rows

- The private reconciliation pass now records the original one-based catalogue
  source-row positions for every SKU group (including duplicate current SKUs).
  Coordinators can locate conflicting source rows without any exposed RRP.
- Duplicate V10 maintenance `rates[].group` entries and duplicate
  `console_rules[].name` entries are no longer silently accepted by the
  unified pricing preview. For an affected exact SKU, pricing fails closed
  with a source-conflict message. The verbatim original V10 arithmetic
  function is unchanged.
- Source-only `GET /api/quoting/catalogue/reconciliation/policy-worklist`
  returns rule identity, source-section and source-row coordinates for
  duplicate or incomplete original tariff/console identity rows. No rates,
  RRPs, percentages or prices are returned. The SmartQuote reconciliation
  screen displays this separate read-only worklist.
- `GET /api/quoting/catalogue/reconciliation` now includes
  `policy_rule_rows_requiring_review`, `policy_flag_counts` and
  `pricing_policy_source_rows` derived from the staged source evidence.
- These identity checks are distinct from commercial rate approval:
  the absence of a duplicate is **not** authorisation to quote.
- This round uses synthetic regression tests for duplicate pricing-policy
  rows, missing rule names, console conflicts and original source coordinates.
  No real price-master reconciliation, approved tariff or production migration
  is asserted.

## Continued development — historical evidence and private readiness gate

The staged 2020–2026 historical identity index now has a separate source-only
integrity audit in `app/quote_history_audit.py`. It reports case-normalised
duplicate historical keys, non-dictionary records, recorded SKU/key
disagreements, missing console identity, malformed aliases, duplicate or
missing alias targets and aliases pointing to multiple historic variants.
No historical or current prices are exposed, and no mapping is approved.
Historical exact-code alias searches now also recognise whole codes recorded in
different letter case. Case-colliding aliases remain explicit review exceptions,
rather than silently selecting a last-wins historical target.

The read-only endpoint
`GET /api/quoting/catalogue/reconciliation/historical-worklist`
supports pagination, original historical keys and issue filtering; the staff
SmartQuote source-audit screen displays the exceptions. A missing historical
index returns 503 rather than treating absent evidence as a clean result.

### IT-only private reconciliation readiness snapshot

On an access-controlled staging machine **after all authentic V10 files have
been provisioned and the IT source fingerprint manifest created**, run:

```bash
python -m scripts.smartquote_source_readiness \\
  --output /private/staging/smartquote-source-readiness.json
```

This creates a **new** aggregate-only JSON report outside the repository and
refuses overwrites. It includes source file hashes, source counts and overall
exception counts only; it contains no customer names, original SKUs, catalogue
prices, tariffs, private paths or commercial approvals. It reports:
- Source manifest fingerprints match the exact staged files.
- Both optional original legacy and historical evidence are staged.
- Required catalogue, policy, legacy and historical identity evidence is nonempty.
- No known SKU, policy, legacy or historical identity exceptions remain.

Exit code **0** means the factual identity evidence is sufficiently complete
to **run the private original-engine numerical parity check**, not that actual
V10 parity has been run or that any price is commercially approved. Exit code
**2** means source evidence remains unresolved or incomplete. Missing/corrupt
source files and pin mismatches fail closed.

The original parity checker, signed-off maintenance tariffs, coverage rules,
approved source precedence, quotation issuance and Sicon/Sage writes remain
separate release gates.

## Latest development — strict original-engine sampling and source pinning

The private `scripts/check_v10_price_parity.py` command now refuses to
execute an original V10 runtime unless `PULSE_SMARTQUOTE_SOURCE_MANIFEST`
points to a valid, matching IT-created manifest. The exact bytes that are
hashed are also the bytes parsed for the numerical comparison. Original
catalogue, configurations and pricing files are rechecked after original
engine import and after every sampled comparison; changes invalidate the run.

The comparison uses `scripts/parity_source_coverage.py` to choose candidates
in a deterministic round-robin across **distinct rate-group and console
families**. Every eligible source family must be sampled; a lower
`--max-skus` limit that omits a family is a non-passing parity run. The
aggregate-only report includes the number of eligible, sampled and missing
families, as well as original SKU omissions and policy rule conflicts.

Duplicate tariff group identities and duplicate console rule identities
now block the affected family from a clean parity pass. Missing or invalid
rate/console source rows also block the overall result. Other excluded
source SKUs are explicitly counted but must be reconciled separately. The
script distinguishes `numeric_comparisons_match` from `pass` to avoid
mistaking matching sampled arithmetic for full original-source coverage.

On the isolated staging host run:

```bash
export PULSE_SMARTQUOTE_SOURCE_MANIFEST=/secure/smartquote_source_manifest.json
python scripts/check_v10_price_parity.py /secure/v10-original --max-skus 300
```

No real source files, customer records, RRPs, maintenance rates or signed
PDFs belong in GitHub. A passing numerical parity result is **not** commercial
tariff authorisation, and it does not enable customer quote issuance. The
original V10 engine must be run only in a controlled disposable environment.

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
