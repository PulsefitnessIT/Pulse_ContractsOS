# SmartQuote | Real source and historical quotation reconciliation
**Internal development evidence | 5 November 2026 | Not commercial approval**

The Pulse Fitness source workbooks were examined outside this public source-code repository. No raw pricing workbook, source-derived item prices, individual manager notes, or customer records have been added here. Detailed reconciliation files remain in the private development conversation and must be stored in protected business systems.

## Verified uploaded source versions

Original workbook checksums matched the previously audited August 24, 2026 Master and the full Sage item export. A fresh exact-item-code cross-reference covered:
- **Sage:** 21,120 distinct item codes; 16,599 positive Sales Prices and 4,521 zero Sales Prices.
- **Raw original August Master:** 5,082 positive List Price rows, representing 5,071 distinct codes across Main Gym, Rigs, Functional Training and Studio Equipment.
- **Intersection:** 5,004 exact codes present in both workbooks.
- **Master-only:** 67 exact codes. **Sage-only:** 16,116 exact codes.
- **Same two-decimal Master/Sage values:** 73 exact matched codes.
- **Different values:** 4,925 exact matched codes. Such differences are informational: the lists use different bases, and Pulse accepted current Master List Price first, exact Sage Sales Price only for machines absent from the Master. No arbitrary price-difference tolerance is approved.

**Critical scope distinction:** the pre-existing protected V10 source bundle contains a curated **4,640-row** August price extract (**4,632 unique codes**). Reading every positive List Price row in the complete workbook finds **5,082 rows**, a difference of **442 rows by extraction scope**. Do not automatically add or replace the 4,640 curated rows: confirm whether the additional raw entries represent sellable items, accessories, excluded equipment or items requiring new service configurations. This is not proof that the existing curated data is damaged.

**Raw Master conflicts:** seven exact codes have different original List Prices: four known from the earlier source audit, two further accessory/item variants in the broad raw extract, and one placeholder code. All must be held until the relevant original workbook rows have been reviewed. The existing curated extract already holds known conflicts; do not silently use a Sage value to resolve a present-but-conflicting Master code.

## Original maintenance quotation workbook

The historical .xls workbook was inspected as an original OLE/BIFF Excel document, without executing its embedded VBA macros. It contains one operational quote worksheet with approximately **329 equipment entries**, **282 distinct quoted part-number labels** and **42 item-specific notes**. It uses annual equipment maintenance amounts, a percentage field, quantity, monthly year-1/year-2/year-3 unit/line columns and overall annual/monthly and multi-year totals.

Historical percentage bands, **normal / half-discount / lowest**:
| Group | Historical percentages |
|---|---|
| Standard equipment | 3.00 / 2.75 / 2.50 |
| Treadmills and ellipticals | 3.75 / 3.50 / 3.25 |
| Fluid rowers | 13.00 / 12.75 / 12.50 |
| Fluid UBE / recumbent | 10.00 / 9.75 / 9.50 |
| Concept2 and some third-party equipment | 9.00 / 8.75 / 8.50 |

These patterns match the corresponding *provisional* V10 tariff-policy groups. This establishes historical **mathematical parity only**, not current commercial authority.

**Exceptions matter:** the historical workbook includes manually agreed Stepmill prices, labour-only products, items no longer considered serviceable because of parts support, a general Titan warning and special console/third-party arrangements. These notes must be reviewed with the Pulse pricing and service owners rather than silently converted to approved software rules. Several old part-number labels describe entire equipment families, and only a small minority exactly match current individual variant SKUs (10 raw Master, 12 Sage), so no automatic family/alias replacement is permitted.

**The historical workbook did not establish approved Silver/Gold/Platinum multiplier factors.** Do not interpret its historical Gold-like percentage approach as authority for the V10 provisional tier multipliers; those require a separate explicit approval with maintenance scope, discounts, exclusions, minimums, VAT basis and approved terms.

## Added protected review functionality

- Admin CSV: `/api/quoting/source-reconciliation.csv` — explicit V10/Master/Sage source reference and discrepancy review, including Master/Sage price bases and accepted source priority.
- Admin API: `/api/quoting/legacy-method-parity` — compares the five documented historical rate groups against current active source tariff bands, flags mismatches and explicitly reports that commercial approval is still missing.
- Both checks are staff-only, use private staged data, and **do not** modify quote prices, activate contracts or approve customer PDF issuance.

## Blocking release gates

1. Obtain sign-off on 442 additional raw Master rows versus the curated source scope and resolve the seven raw source conflicts where relevant to quoted equipment.
2. Confirm the actual effective/export date of the full Sage file. Zero-price Sage inventory must not become a maintenance value.
3. Verify each active maintenance configuration and installed console/variant (and any customer-specific exception).
4. Reconcile manually approved equipment charges, historic labour-only/no-parts exclusions and the Silver/Gold/Platinum tariffs as current signed-off policy.
5. Stage verified private data in the protected pilot; complete named-coordinator end-to-end quote tests, PDF/terms checks, access controls and backup/restore evidence before issuing real customer quotes.

Do not commit the uploaded files to the public GitHub repository.