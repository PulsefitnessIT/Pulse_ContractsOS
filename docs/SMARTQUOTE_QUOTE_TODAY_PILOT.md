# SmartQuote — same-day internal quotation path

**Development date: 5 November 2026. Status: tested internal pilot only.**

This deliberately distinguishes an **internal maintenance quotation draft** from an
**approved customer-facing maintenance quote**, which still needs authorised
Pulse pricing, valid terms, verified equipment coverage, VAT treatment and
release controls.

## Available immediately outside deployment

A single-file offline HTML pilot was generated using the **private** verified
21,187-code unified Master price list and delivered directly in the user's
conversation. It is **not** committed to the public repository because it
embeds company-sensitive item prices. It runs locally without Python and lets
staff select equipment, enter customer/site, quantity, machine serials,
cover level, years, annual rate or fixed annual charge, then print a clearly
watermarked internal quotation schedule or save an editable JSON draft.

Browser smoke-tested with real-source SKU `260G-AAA`, three fictional
treadmills, a 3.75% historical *guide*, three years and a PDF print. This is
a software test, **not proof that the 3.75% rate or Gold cover is commercially
approved**.

## Integrated future pilot path

The Contracts OS quoting workspace now includes **Fast SmartQuote — price a
maintenance contract today**. It takes the equipment schedule already
entered by the coordinator and prices it from the active **unified Master
price book** via protected APIs under
`/api/quoting/quick-draft/`. The integrated path **does not require a V10
SKU configuration or tariff mapping** for internal estimates.

- `GET /status` — current Master revision and SHA, staff-only, no prices.
- `GET /search?q=...` — equipment-only source lookup; excludes Sage parts,
  held and £0 prices; no maintenance eligibility claims.
- `POST /preview` — line-by-line verified equipment price, editable annual
  rate or fixed price, optional discount, total, term total and issues.
  Backend uses Decimal arithmetic with penny rounding. Zero, held,
  missing, inventory-only or non-machine source records are blocked.
- Changes to the entered customer/equipment or manual rates invalidate a
  previously priced preview in the browser.
- Before browser printing, the current Master fingerprint is rechecked;
  a newly imported price list blocks printing stale figures.
- A printable internal document shows the customer-style equipment
  schedule and totals, **never a live/approved quotation number**.

Both integrated and offline interfaces deliberately show the rate as a
**historical editable guide**, *not* a V10 contract multiplier approved by
Pulse. Staff must confirm Silver/Gold/Platinum-specific tariffs and any
manually agreed exceptions independently.

## To use the integrated quick quote

1. IT deploys the protected Contracts OS internal pilot and establishes
   named Coordinator and Administrator logins.
2. Admin opens **Unified Master Price List**, uploads the protected combined
   price CSV, inspects held/zero conflicts and activates revision 1 with a
   recorded justification. No raw source data are committed to GitHub.
3. Coordinator opens SmartQuote, enters customer/site, selects actual equipment
   and quantities, then chooses **Fast SmartQuote → Load machines**.
4. Review percentages or annual fixed rates for each machine, calculate and
   print the **internal draft** for manager sign-off.
5. An external customer quote still requires approved maintenance terms,
   tariff, exclusions, source-mapping checks and normal commercial issuance.

**No production deployment or live commercial release has been performed.**
Do not treat a passing CI test as a signed-off customer contract. Existing
issued PDF snapshots and price audit versions remain unchanged.
