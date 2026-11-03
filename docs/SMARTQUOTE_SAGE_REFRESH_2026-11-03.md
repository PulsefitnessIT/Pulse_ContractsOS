# SmartQuote — Sage Price List Refresh (controlled pilot)

**Owner:** Pulse Fitness IT / authorised pricing administrators  
**Scope:** The unified SmartQuote workspace inside Contracts OS  
**State:** Implemented in feature branch for supervised pilot; not production or commercial tariff approval

## Operational pricing hierarchy

1. **Current equipment listed in the 24 August 2026 Master Price List:** use the original workbook's **List Price** for the exact product code and variant. A conflicting master code is a review exception; Sage does not override that conflict.
2. **Older equipment absent from the August 2026 master:** use the **exact Sage Sales Price** as the equipment RRP basis for internal V10 maintenance calculations. Sage's export is expected to cover current and historical item codes. A price alone is not proof of a match to V10 equipment, console or an eligible maintenance tariff.
3. **Administrator correction:** when equipment prices require changing, a named pilot administrator may set a local, audited GBP effective price for an exact SKU. Old price-list files and original quotations are not rewritten. When the source export is refreshed, previous source-bound overrides require re-verification; stale overrides block the affected internal quote rather than applying a potentially obsolete value.

The original V10 \`price_line\` formula, including one-unit rounding, still computes the indicative maintenance price. **Customer quotation issue and tariff approval remain disabled**.

## Preparing the Sage export

From Sage 200, export the **complete item-code Sales Price list**, not customer-specific invoice prices. The uploaded real-world Sage file contains **21,120 rows**. Supply CSV (UTF-8) or XLSX with these four required columns plus the optional fifth **Manufacturer** column, starting on the first worksheet:

| A | B | C | D |
|---|---|---|---|
| Code | Name | Product Group Description | Sales Price |

**All** exact Sage item codes are retained in the source snapshot, including parts, accessories, non-maintenance groups and zero-price items. They remain accessible for reference but are **not automatically maintainable equipment**: the original V10 equipment and service configuration must separately validate coverage before pricing. Zero-price rows are held as unpriced; an authorised administrator can audit-correct the effective price of an exact code before any internal quote preview.

The real Sage workbook includes an additional **Manufacturer** column (E), and 367 codes contain spaces or supplier-specific characters such as `#`, `*`, `&`, `(`, `)` and `+`. The parser now preserves these exact codes. Four-decimal source amounts are preserved as imported evidence and the effective GBP source price is rounded to pence using half-up rounding.

For a spreadsheet, formulas in the five source columns are not trusted as source evidence. Export fixed source values instead.

## Administrator workflow

1. Log into the **protected Contracts OS staging pilot** with an **Admin** account.
2. Open **SmartQuote → Sage Price List Refresh**.
3. Select the full Sage CSV/XLSX export and enter its actual source/export date.
4. Select **Compare with current Sage list**. The preview identifies added codes, changed prices, changed product names/groups, removed codes and unchanged entries.
5. Inspect the differences. If unusually many codes have been removed, verify that this is an entire export rather than a filtered subset; a separate explicit confirmation is then required.
6. Provide a meaningful reason and select **Activate reviewed Sage price list**.
7. The new snapshot becomes the source for equipment absent from the August master. The old snapshots remain archived. Use **Review changes** to see the item-level price and identity differences.
8. Recheck any locally amended equipment prices whose source snapshot fingerprint changed. The system refuses to silently carry source-bound corrections into a replacement export.

Uploads **do not** change Sage 200, the original SmartQuote read-only database, the August master spreadsheet, previous issued quote PDFs or existing contract records.

## Data protection and change controls

- Files are accepted only from named authenticated pilot Administrators; API writes also require the existing protected session, origin validation and CSRF token.
- The upload limit is **16 MB**, up to **60,000 rows**; large/deceptive spreadsheets, invalid *non-zero* prices, conflicting codes and unsafe formulas are rejected. Source rows with £0 are retained but not automatically priced.
- Candidate price rows are compressed and stored in the private Contracts OS SQLite database, never in GitHub.
- A preview is bound to the authenticated administrator, current active source checksum and creation time; it expires after **two hours**.
- A later import or replacement invalidates an earlier preview. Activate uses a SQLite immediate transaction and fails closed on concurrent changes.
- The exact imported file checksum, source date, administrator, previous source checksum, summary and per-SKU changes are persisted.
- Snapshot activation is distinct from commercial approval. Explicit customer-quote issuance remains disabled until maintenance tariffs and quotation documents are signed off.
- Source files are staged within an access-controlled environment and protected by existing Contracts OS backups.

## API and code

| Endpoint | Purpose |
|---|---|
| \`POST /api/quoting/sage-refresh/preview\` | Multipart CSV/XLSX + \`source_date\`; validate, compare and stage |
| \`POST /api/quoting/sage-refresh/activate\` | Confirm a previously staged import and record its audit |
| \`GET /api/quoting/sage-refresh/status\` | List current local Sage snapshot and retained versions |
| \`GET /api/quoting/sage-refresh/changes\` | Paginated source-SKU changes for one version |
| \`GET /api/quoting/prices/{sku}\` | Admin effective price and revision history |
| \`PUT /api/quoting/prices/{sku}\` | Admin exact SKU price correction |
| \`POST /api/quoting/prices/{sku}/revert\` | Restore current source price, preserving audit |

Backend: \`app/quote_sage_refresh.py\`, \`app/quote_sage_reference.py\`, \`app/quote_price_overrides.py\`, \`app/quote_pricing.py\`  
Frontend: \`app/static/quote-sage-refresh.js\`, \`app/static/quoting-workspace.js\`  
Tests: \`tests/test_quote_sage_refresh.py\`, \`tests/test_quote_price_overrides.py\`, \`tests/test_quote_sage_reference.py\`

## Actual Sage export validation — uploaded 3 November 2026

The user-provided **Sage Price List.xlsx** is an \`ExportData\` worksheet with
columns A–E:
\`Code | Name | Product Group Description | Sales Price | Manufacturer\`.
Its raw workbook SHA-256 is
\`68d578a6e2baeba6c380813fc9a280b5f74dda5f9f55d0a936fe25a62dd28636\`.

Source validation results:
- **21,120** total source rows / **21,120** unique exact item codes; no duplicates observed.
- **16,599** positive source prices and **4,521** zero-price records.
- **367** original code strings require the extended Sage character set.
- **1,246** source price amounts have more than two decimal places.
- **37** source product groups; the old narrow equipment-group allowlist
  would have silently lost genuine Sage item codes, including Free Weights,
  Base Units and non-maintenance stock codes.

The full price list must remain outside the code repository. This document
records metadata and aggregate findings only. An internal audit workbook
and exact-code exception worklist were delivered separately to the user.

**Important:** the original export/effective date of the source has not been
independently verified from the uploaded filename or workbook. An authorised
staging administrator must enter the genuine Sage export date when creating
the protected import preview. No source activation, Sage write, final
SmartQuote catalogue reconciliation or customer quotation has occurred yet.

## Outstanding release gates

The development branch uses **fictional regression fixtures**. It has not yet loaded a real Pulse Fitness Sage export into a live staging environment, nor established real-source V10 parity for the entire historical equipment catalogue.

The future operational work remains a complete real Sage import, a factual code-level reconciliation against the August 2026 current list, staff acceptance testing, approved maintenance tariff/coverage rules, rollback procedure, production identity and security assessment, and signed-off customer quotation/PDF generation.

No API writes to Sage 200, Sicon or the original SmartQuote database are introduced by this change.
