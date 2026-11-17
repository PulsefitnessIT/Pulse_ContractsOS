# Pulse Fitness — one unified Master Price List

**Pilot feature, 5 November 2026. Not yet deployed or commercially approved.**

## Current agreed source of truth

1. Import the **complete Sage item list** as the original inventory reference. It deliberately contains spare parts and other non-machine SKUs.
2. For an exact item code also appearing on the current **August 2026 Master**, choose that current Master **List Price**, replacing the corresponding Sage Sales Price as the current price.
3. Retain one record per code. Do not guess between conflicting original Master rows. **Hold** disputed prices and retain their original evidence.
4. After activating this one Master, every **new Admin-approved import** supersedes the current price for each exact code it contains, regardless of whether that item's previous source was Sage or the August Master. Unmentioned SKUs remain untouched.
5. Keep historical price-book versions and originally issued quotation PDFs; changing the Master NEVER reprices an already issued customer document.

The consolidated source-derived file from the previously verified private worksheets contains **21,187 distinct codes** (5,064 selected Master price references, 11,741 positive Sage-only references, 4,375 zero/unpriced Sage references, 7 conflicting raw Master price codes). These counts are source reconciliation findings, **not** machine counts or approved maintenance contract quotations.

The original workbook bytes and complete consolidated price book belong in protected Pulse storage, **not this public repository**.

## How to activate and update prices

In an IT-protected pilot, open **SmartQuote → Unified Master Price List** with a named Administrator account.

- For the first activation, upload the generated consolidated CSV (`Pulse_Fitness_Unified_Master_Price_List_2026-11-05.csv`) using **Review price changes**. Inspect the counts, held and zero-price records and provide an explanatory approval reason. Confirm the held/zero-price warning before activation.
- For any later price update, export a CSV from Excel containing at least **SKU,Price GBP**. For example, a newly approved `SKU-101,3250.00` replaces that exact code's current price. Additional optional columns are **Description**, **Product Group**, **Price Source** and **Price Status**. They update metadata only when populated; no other prices are deleted.
- A deliberate `HOLD` status clears eligibility to use that item's price; `0.00` records an unpriced item. Empty price without an explicit HOLD is rejected, as are duplicate codes, invalid numbers, ambiguous or tampered snapshots.
- The **Activate updated Master prices** button records an immutable source fingerprint, administrator name, reason, version number and a complete restorable source snapshot. Preview tokens are actor-bound, expire after two hours and reject concurrent price-book edits.
- **Download current Master price list** provides the current all-code list, including spare parts, at any time. A later import can contain only changed codes: it must not include the entire 21,187-row list.
- Original Sage refresh and old per-SKU overrides are retired as price authorities once this unified book is active. The preserved original source snapshots remain evidence.

Only **one active price-book version** is used by the coordinator's quote preview, all package comparisons and the approved customer quotation issue path. A source change during PDF creation blocks issuance; unchanged issued PDF snapshots are not rewritten. The current version SHA and revision are included in the price preview.

## What this does not approve

A price record is **not** proof that an item is a full machine, physically installed, eligible for cover or correctly mapped to a console. Sage-only spare parts remain reference inventory. Staff must still verify the actual machine, serials, maintenance configuration, package, source coverage, service tariff, discounts, exclusions, supplier details, maintenance terms and customer approval.

The old V10 catalogue still supplies historical service-configuration evidence during the pilot, **but is not the authority for the price** once the unified Master is activated. Replacing incomplete V10-only service mappings with a cleaner Pulse-maintained equipment catalogue is a separate development workstream.

## Outstanding deployment and acceptance gates

Protected IT deployment, importing the actual 21,187-row private CSV into the active pilot, reviewing the seven Master price conflicts, recording commercial owner approval, completing coordinator tests and verifying backup/restore remain outstanding. Automated synthetic CI passing does **not** certify the actual private merged price list as live, nor authorise live customer quotations.
