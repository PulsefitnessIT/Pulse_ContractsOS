# Where missing information comes from

The Maintenance Master is a contract-level register. Machine details and negotiated maintenance terms must be sourced separately.

| Existing Maintenance Database field | Recommended authoritative source | Safe automatic action |
|---|---|---|
| Customer / site | Sage/Sicon verified site reference, invoices | Suggest a match; coordinator confirms |
| Contract number | Sage/Sicon agreement or signed contract; handwritten annotation is provisional | Propose only until verified |
| Invoice Code (`CON-...`, `WAR-...`) | Sage stock/item code mapping or verified service invoicing record | Add only on unique confirmed code match |
| Contract / warranty type | Signed maintenance/warranty agreement | Require confirmation; product catalogue does not decide cover |
| Start date / Expiry date | Signed agreement or verified contract record | Flag printed vs handwritten conflicts |
| Contract term, Services per year, Response target | Contract schedule or signed SLA | Never infer from equipment model |
| Payment frequency, Contract amount (£), Original amount (£) | Sage billing / accepted quotation / signed agreement | Preserve original amounts and evidence; no equipment RRP substitution |
| Site notes, Original amount notes, Price review history | Previous Maintenance Master, dated correspondence | Preserve provenance and existing content |
| Consoles / software | 2026 equipment catalogue matched to actual invoice line/serial | Show a field suggestion only if the contract field is blank |
| Frame / upholstery finish | 2026 equipment catalogue matched to actual machine variant | Show a field suggestion only if blank |
| Beds and belts covered, Upholstery covered | Signed agreement/exclusions | Never derive warranty cover from product specifications |
| Last service recorded | Sicon engineering/job completion records | Read only until an authoritative API is verified |
| Invoice account / Site account | Verified Sage/Sicon account fields | Match by identifiers; do not rely on name alone |
| Sage Checked and Updated | Explicit user verification | Staff action with audit history |

## New equipment register

The 2026 Master Input File's **Assembled Database** was indexed to create **6,875 unique stock-code variants**. It is a reference catalogue, not a customer asset register.

Once an invoice or asset schedule is reviewed, attach machines to the correct agreement by `SKU + serial number` and capture quantity, installation date, warranty expiry and source invoice number. This creates a searchable equipment list within the platform. Export it separately from the standard eight-tab Master using the **Equipment register CSV** button.

## Excel export contract

The normal **Excel Master** export must preserve the eight familiar tabs, column order, all existing cell contents, per-column formatting, colour fills, filters, calculations and director reporting. Newly filled reserved rows take their style from ordinary contract data cells, **not** the preformatted blank-entry green band. A distinct, coordinator-approved machine schedule could be added later as a *separate* export, not silently inserted into the familiar Master.

## Production import workflow still needed

Scanned invoice OCR, line grouping, handwriting recognition, robust customer matching, duplicate detection and evidence-linked review are outstanding production work. The Example University demonstration uses manually entered invoice facts, not functioning automated OCR. Likewise, no Sage/Sicon synchronisation occurs in this local pilot.
