# SmartQuote — Customer PDF quotation release gate (next pilot build)

**Purpose:** enable Pulse Fitness to prepare a quote in Contracts OS, check it,
approve exact source-derived maintenance values and download an itemised,
customer-ready PDF to send using the normal customer email process.

**Status:** built into draft PR #5 for the next supervised pilot. Not yet
merged, staged with live Pulse data, commercially signed off or deployed.

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
