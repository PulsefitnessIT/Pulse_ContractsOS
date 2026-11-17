# SmartQuote coordinator journey — Pulse Fitness internal pilot

Status: developed and regression-tested on 6 November 2026, but not deployed or authorised for customer issue.

## Coordinator workflow

1. **Customer and site:** enter/confirm legal customer, site, Silver/Gold/Platinum cover, term and discount. An existing Contracts OS site may be selected; a source label is not assumed to prove customer identity.
2. **Invoice/delivery-note PDF drop:** upload 1–12 sales invoices or delivery notes, each at most 20 MB (60 MB per batch). The importer recognises the 2018 legacy Pulse format, the 2026 Sage invoice format and older Pulse delivery notes. Original PDFs are retained as source evidence.
3. **Automatic matching:** compare item codes read from actual PDF **table rows** against the **one active unified Master Price List**. A positively priced machine code is included automatically, with source invoice and page. There is no matching checkbox. Exact spare-part and non-machine codes are recognised but excluded. Held/unpriced codes go to price review. **Only unmatched codes** need coordinator correction using the unified Master equipment search; corrected codes do not falsely inherit PDF source provenance.
4. **One batch for quantities and serials:** the document reader now proposes quantities and individual serial numbers from equipment rows, including serial lists continued onto the following page. Delivery notes distinguish **quantity sent** from **quantity received**; items with zero received (such as TO FOLLOW) are excluded. Suggested values remain **provisional** until the coordinator checks and confirms them together in one table. Where a document layout is unrecognised or values cannot be read, no quantity or serial number is invented. Commercial customer issue is blocked for unverified imported quantities. Missing individual serials remain subject to manager exception procedures.
5. **Save & calculate internal quote:** one button saves the draft and calculates from the single Master, without old V10 equipment mapping as a gate. Editable rate percentages or per-unit annual fixed charges are preserved in saved drafts. The default percentages are **historical guides**, not commercially approved Pulse maintenance tariffs.
6. **Download branded internal PDF:** the server recomputes against the exact active Master version and returns a Pulse Fitness branded A4 PDF with equipment schedule, customer/site, cover, term, annual and term values, assumptions and a prominent **INTERNAL DRAFT — NOT AUTHORISED FOR CUSTOMER ISSUE** warning. It includes all listed serials, paginated as necessary. It is not a valid customer quotation, does not attach fabricated terms and requires no pop-up window.
7. **Manager/commercial release:** the separate customer-issue path still requires approved rates, verified machine eligibility and configuration, signed-off terms, verified Pulse issuer details, a named Admin's approval, valid equipment quantities and serials/exception record, and IT release enablement. This development does not enable customer issue or transmit emails.

## Security and audit behaviour

- Staff access to the quick quote and server PDF is restricted to signed-in Coordinator/Admin roles.
- Auto-matched source codes and pages are reverified against the original PDF evidence and the current Master when saving the draft.
- Price-book changes or changes to draft fields invalidate a previously calculated estimate.
- Re-import of the same invoice/code does not silently double-count it within a draft. Cross-document matches with overlapping serial numbers are not automatically added twice.
- Original customer invoices and delivery notes, source records, prices and licensed font binaries remain outside the public GitHub repository. Public regression tests use fictional data.
- Historical issued PDFs and pricing source audit snapshots are not changed.

## Acceptance tests before everyday Pulse use

Protected deployment and login configuration; loading the real merged Sage/Master; review of conflicting price codes; real-world invoices (including OCR/scans and console variants); coordinator UAT and old-workbook parity checks; approved Silver/Gold/Platinum tariffs and exclusions; legally reviewed terms and issuer details; A4 print review; backups and privacy testing.

Synthetic integration tests now exercise PDF evidence → automatic Master code match → validated draft → batch quantity confirmation → preserved rate → price calculation → branded PDF. This is *not* equivalent to completing live Pulse acceptance on real invoices.
