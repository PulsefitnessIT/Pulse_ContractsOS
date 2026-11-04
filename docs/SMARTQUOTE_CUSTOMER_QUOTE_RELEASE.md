# SmartQuote — Customer PDF quotation release gate (next pilot build)

**Purpose:** enable Pulse Fitness to prepare a quote in Contracts OS, check it,
approve exact source-derived maintenance values and download an itemised,
customer-ready PDF to send using the normal customer email process.

**Status:** built into draft PR #5 for the next supervised pilot. Not yet
merged, staged with live Pulse data, commercially signed off or deployed.

## Shortest path to the first genuine customer quotation

This branch now includes a staff-facing **Customer quotation readiness**
check at the top of SmartQuote. It distinguishes required approval gates from
the Sage fallback, which is optional for a current-machine SKU found in the
August 2026 Master. **All release gates remain OFF by default.**

1. **Deploy the protected pilot first:** IT must provision the approved
   private Contracts OS Master and SQLite snapshot, HTTPS/TLS, named pilot
   accounts and backups. The source repository contains neither a live
   customer database nor the deployed service.
2. **Obtain the original four V10 files:** On a Windows IT/admin workstation
   with the GitHub CLI signed into the private PulseFitness organisation,
   run `./scripts/prepare_smartquote_v10_bundle.ps1` from this repository.
   The script fetches exactly the original `catalog.json`, `configs.json`,
   `pricing.json` and compressed August 2026 master from the private
   `PulsefitnessIT/Pulse_SmartQuote` handoff branch. It creates a source ZIP
   and deliberately downloads **no customer records**. Alternatively,
   manually create the same four-file ZIP.
3. **Activate original V10 sources:** In Contracts OS SmartQuote, an Admin
   uploads that ZIP into **Original V10 & August Price Source Setup**,
   reviews its source counts and fingerprints, then activates it. The V10
   product picker **now reads this same active ZIP**. It no longer requires
   the separate `PULSE_SMARTQUOTE_CATALOG_JSON` variable.
4. **Upload the provided Sage Price List:** Use **Sage Price List Refresh**,
   enter the actual verified export date, inspect the 21,120-item preview and
   activate the correct snapshot. This extends quoting to legacy equipment
   codes *already mapped* to a verified V10 service configuration.
5. **Authorise real commercial data:** In **Customer Quotation — Commercial
   Setup**, explicitly review and approve the genuine maintenance rates
   and Silver/Gold/Platinum multipliers, upload the approved T&Cs PDF,
   verify company issuer details and enable customer issuance only after
   an internal acceptance quotation.
6. **Make the first quotation:** Start with a *confirmed exact V10 machine
   that has an August Master List Price and an eligible Active maintenance
   configuration*. Select the real customer, add the exact equipment SKU,
   confirm serials and quantities, choose a cover package and term, **save**,
   then **Preview V10 price**. The new release panel tells staff which
   equipment, dates, pricing source or commercial approvals are still missing.
7. **Issue the PDF:** A named Coordinator can prepare and review the internal
   draft; an Admin verifies the quote and records its explicit commercial
   approval. The issued PDF is immutably archived and can then be downloaded
   by Coordinators and Admins for manual customer emailing.

**The original V10 handoff source currently contains 4,012 catalogue rows
(4,007 distinct SKU values), 490 service configuration records, and a
provisional price policy.** Exact-source identity alone is insufficient to
approve an equipment line. Ambiguous or ineligible machines remain blocked
until resolved. No sign-off is inferred from a passing test.

The application also exposes an explicit, read-only API
`GET /api/quoting/release-check` to show staff which prerequisites remain.
Sage-only inventory lines do **not** become maintainable equipment automatically.

## Source onboarding from the app — no Python setup for staff

An authenticated pilot Administrator can now stage the complete original
SmartQuote V10/August pricing source **from the SmartQuote screen**.
IT environment variables are optional when the original source files are
uploaded and approved through the protected admin interface.

1. In the private `PulsefitnessIT/Pulse_SmartQuote` repository, retrieve the
   original `data/catalog.json`, `data/configs.json`,
   `data/pricing.json` and `data/rrp_2026_source.json.gz`.
2. Zip **exactly those four files** (they can be under one `data/` folder).
   Do not zip the customer database, invoices, archived quote files,
   passwords, API credentials or unrelated source files.
3. Open **Contracts OS → SmartQuote → Original V10 & August Price Source Setup**.
   Upload the ZIP, check the displayed source counts, the August date and
   the tariff SHA-256, record the reference and the original-source
   attestation, then **Activate**.
4. Open **Sage Price List Refresh** and upload the full genuine Sage export.
   The provided **Sage Price List.xlsx** uses five columns including
   Manufacturer and 21,120 item codes. Enter its actual confirmed
   export date, preview changed prices and activate the latest snapshot.
5. Complete **Customer Quotation — Commercial Setup**. Approve tariff
   rates/packages/minimums, the real maintenance T&Cs, the correct Pulse
   issuer details, and lastly the explicit customer-PDF issuance switch.
6. Build a real quotation using an exact V10 equipment code, inspect the
   internal PDF, obtain the quotation-specific manager authorisation and
   download the final issued customer PDF.

All original V10/August bytes and the Sage list are stored in the **private
application database**, never in the source GitHub repository. The source
import and every change are audited. A replacement V10 ZIP automatically
disables the in-app customer-quote issuance setting until the revised sources
have been reviewed. An original provisional tariff remains unapproved until
commercially signed off.

**Important limitation:** the Sage export is an item-code source, not proof
of equipment maintenance coverage. A Sage-only SKU without a unique original
V10 service configuration remains unpriced until an approved equipment
mapping is provided. Only verified V10 equipment with valid pricing can reach
the customer-PDF step. Full original-vs-unified real numeric parity still
requires IT validation; synthetic test success does not prove it.

## In-app commercial onboarding (current build)

The next protected pilot now has **SmartQuote → Customer Quotation — Commercial
Setup**, restricted to a named Administrator. Commercial onboarding no longer
requires IT to prepare terms/issuer JSON files or manually set tariff
environment variables; the existing environment-pinned configuration remains
supported as an IT-managed override.

1. **Approve tariff:** after the authentic V10 price/config files are
   securely staged, inspect the exact source rate groups and Silver/Gold/
   Platinum multipliers. An authorised manager confirms each source rule,
   minimum charge, discount and outstanding parity issue, and records an
   approval reference and reason. The precise tariff source SHA-256 is
   captured. Source status marked `Provisional` is **not** auto-approved.
2. **Approve terms:** upload the actual approved maintenance terms PDF, record
   legal/commercial approval and confirm the entire document is current. The
   exact bytes are saved privately and appended to issued quotations.
3. **Supplier identity:** record factual verified legal company name,
   registered office, company number, service contact email and optional
   phone/VAT number. The source bytes are versioned and audited.
4. **Enable customer PDFs:** once the three preceding requirements are
   complete and an end-to-end approved-data acceptance test has been carried
   out, record the release decision and enable customer quote issuance.
   The app will still require an Administrator's approval for every individual
   quote. Issuance remains OFF by default.
5. Any update to an approved tariff, company identity or terms **automatically
   disables** the in-app customer issue switch, requiring review and
   reactivation. Every change is recorded in an append-only audit.

**IT override:** `PULSE_QUOTE_LIVE_ISSUANCE=0` explicitly disables customer
PDFs even if the Administrator switch is enabled. A matching
`PULSE_QUOTE_APPROVED_TARIFF_SHA256`, terms/issuer file hashes and
`PULSE_QUOTE_LIVE_ISSUANCE=1` may still be used on tightly managed
infrastructure. If any associated file/hash pair is partially provided,
the application fails closed. Never enable issue with unverified commercial
tariffs or placeholder company details.

The authenticated pilot and secure core source staging are still needed.
The UI cannot independently verify that a real person had commercial
authority to sign off tariffs; the company is responsible for controlling
Admin access and validating its genuine signed-off terms.

## Operational workflow

1. Open **Contracts OS → SmartQuote**, search an actual customer site and
   verify its legal customer name. Add equipment from the original V10
   catalogue using the exact SKU and correct console, quantity and optional
   serial numbers. Select Silver, Gold or Platinum, term years, discount and
   intended service commencement where known.
2. **Save draft**, then select **Preview V10 price**. The internal calculation
   takes the August 2026 master List Price first, and the exact Sage Sales Price
   for codes absent from the August master. IT-pinned, audited local
   administrator price corrections can replace an exact equipment RRP.
3. Select **Download internal draft PDF**. This is prominently marked **NOT FOR
   CUSTOMER**; it contains equipment, annual and term value, customer and site.
4. Select **Check customer issue readiness**. The app checks all exact items
   and service configurations, source pricing, console identity, discounted
   minimum charges, current equipment price evidence, a fixed tariff approval
   SHA-256, the approved terms PDF, verified issuer details, and IT's explicit
   opt-in flag.
5. A named **Admin** records a meaningful commercial approval reference,
   expiry date, and five mandatory attestations for customer identity,
   equipment/serials, rates/discount, scope/terms and VAT basis.
6. **Approve and create customer PDF** atomically freezes a unique
   `PFQ-YYYY-000001` quotation number, original source hashes, priced draft,
   contract dates, approval actor/reference, approved terms and the PDF.
7. **Download approved customer PDF**. Send it to the customer through the
   existing approved Pulse Fitness mailbox. **The app has not emailed it,
   activated a contract or written to Sage/Sicon.**
8. The same draft revision cannot be issued twice. To revise the quote,
   edit/save the draft (new revision), reprice and approve again. Previously
   issued PDFs remain accessible and do not change.

## Security and commercial release gates

**No customer PDF can be issued merely by generating an internal V10 price
preview.** The issued route requires:

- The protected pilot, logged-in **Admin** account, session and CSRF.
- Immutable original V10 source manifest and authentic August 2026 price
  evidence verified by SHA-256 at price-calculation time.
- A complete quote with exact product SKU, original service configuration and
  eligible **Active** rate group. Missing catalogues, duplicate SKUs,
  unknown console, mismatched August console identity, excluded equipment,
  unpriced Sage items, stale administrator corrections, overdue fallback prices,
  discounts below minimum or other review warnings block customer issuance.
- A dedicated, company-approved tariff fingerprint, matching the exact V10
  `pricing.json` being used by the quote engine. The repository's
  provisional V10 rates are **not** implicitly approved just because tests pass.
- A real, commercially approved maintenance **terms PDF**, staged outside the
  repository and verified against the exact signed-off SHA-256.
- An IT-verified legal issuer JSON, protecting the actual trading company name,
  registered address, company number and verified service contact email.
- An administrator-supplied quote-specific sign-off reference and all five
  attestations.
- IT's `PULSE_QUOTE_LIVE_ISSUANCE=1` opt-in, which must remain off until the
  previous evidence is complete.

The source and effective line prices are checked again before the immutable
PDF is committed, including any changes in the local Sage/price source.
Issued archives include SHA-256 of both the archived PDF and immutable
pricing snapshot; downloads fail closed if either differs.

### Secure staging variables

All paths below are private protected-runtime paths, **not** GitHub files.
Do not set these to fictional data for customer use.

```bash
# Already required by source V10/August/Sage price integration:
PULSE_SMARTQUOTE_CATALOG_JSON=/secure/v10/data/catalog.json
PULSE_SMARTQUOTE_CONFIGS_JSON=/secure/v10/data/configs.json
PULSE_SMARTQUOTE_PRICING_JSON=/secure/v10/data/pricing.json
PULSE_SMARTQUOTE_SOURCE_MANIFEST=/secure/v10/source_manifest.json
PULSE_SMARTQUOTE_RRP_2026_SOURCE=/secure/v10/data/rrp_2026_source.json.gz
PULSE_SMARTQUOTE_DB=/secure/v10/original-smartquote.db

# Optional IT-managed overrides. Normally use the in-app Commercial Setup
# to approve the following sources and enable customer PDFs:
# Customer quotation release; do not enable before approval:
PULSE_QUOTE_APPROVED_TARIFF_SHA256=<SHA256-of-reviewed-pricing-json>
PULSE_QUOTE_TERMS_PDF=/secure/commercial/approved-maintenance-terms.pdf
PULSE_QUOTE_TERMS_SHA256=<SHA256-of-approved-terms-file>
PULSE_QUOTE_ISSUER_JSON=/secure/commercial/verified-issuer.json
PULSE_QUOTE_ISSUER_SHA256=<SHA256-of-verified-issuer-json>
PULSE_QUOTE_LIVE_ISSUANCE=1
```

Example `verified-issuer.json` **structure** (replace with verified facts):

```json
{
  "legal_name": "Pulse Fitness Ltd",
  "registered_address": "THE VERIFIED REGISTERED OFFICE ADDRESS",
  "contact_email": "APPROVED SERVICE CONTACT EMAIL",
  "company_number": "VERIFIED REGISTRATION NUMBER",
  "telephone": "VERIFIED CUSTOMER PHONE",
  "vat_number": "VERIFIED VAT NUMBER"
}
```

The company identity file is validated against the exact byte SHA-256. The
example values are placeholders, not verified Pulse details and must never
be deployed unchanged. On Windows, an authorised IT colleague can use
`Get-FileHash -Algorithm SHA256 <path>` to produce each exact fingerprint.

## Important boundaries

- The user-provided Sage Price List contains historical codes, parts and
  £0 items. An item code and Sales Price alone are insufficient for an
  authorised maintenance quote: the original product and coverage identity
  must be verified, or an approved future mapping must be created.
- The August 2026 Master contains current machines. Different console
  variants require review, rather than a single unverified generic price.
- Actual historical/source V10 parity against the real data still needs a
  supervised IT test; passing synthetic regression tests is not its
  substitute.
- A generated quotation is an **offer**; a maintenance contract still requires
  customer acceptance and the established contract setup process.
- Do not email a PDF generated with fictional/test source prices or without
  the actual attached maintenance terms. Stage approved commercial source
  data, run the sample end-to-end quote, inspect its PDF and have the
  Service/Aftersales manager sign off before first external use.

## Implemented code and checks

- `app/quote_customer_pdf.py`: customer PDF layout, equipment schedule,
  annual/term GBP totals, exclusions pointer, signed-off supplier identity,
  original maintenance terms appendix, unmistakable draft watermark.
- `app/quote_customer_issuance.py`: approval/readiness routes,
  customer PDF archive with price source fingerprints, commercial gates,
  irreversible quote-number assignment and read-only download.
- `app/static/quote-customer-issue.js`: staff quote approval UI and PDF
  download, wired into the existing unified SmartQuote workspace.
- `tests/test_quote_customer_issuance.py`: fictional customer tests for
  PDF formatting, appended terms, approval gating, archive integrity,
  duplicate issuance, authorisation, unsupported console and source data.
- CI: Python 3.11 and 3.12 source-safety tests, Node JavaScript checks,
  server image and dependency checks.

**Initial operating mode:** internal draft PDFs are available wherever
verified V10 pricing sources are staged. Customer-ready PDF controls stay
disabled until the documented release gates are satisfied.
