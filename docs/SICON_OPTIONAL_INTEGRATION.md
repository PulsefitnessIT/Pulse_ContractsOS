# Pulse Contracts — Sicon integration is optional (manual-first)

**Development branch:** `feature/unified-smartquote-intake`
**Operational default:** `manual_excel`
**API calls to Sicon in this release:** **NONE**

## Coordinator workflow without any API key

The Contracts OS PWA must continue to function without Sicon credentials,
without network access to the Sicon server, and even when Sicon's WebAPI
module is unavailable.

1. Open **Accepted quotes**, and import the accepted SmartQuote handoff JSON.
2. Verify customer, site, equipment/serials, tariff approval, dates, billing
   references and the evidence behind discrepancies in the existing Setup Workbench.
3. Preview the populated maintenance agreement from IT's protected approved
   source PDF and archive the customer-signed agreement.
4. Generate the separate **Sicon Contract Excel** review-only import using
   the approved 239-column original template.
5. After the coordinator imports into Sicon and verifies the result, record
   the actual Sicon contract reference and evidence.
6. Generate the separate **Sicon Equipment Excel** review-only import using
   the original 29-named-field equipment template, **for each commencement
   date that has arrived**.
7. Record the real Sicon equipment batch reference and evidence; later-dated
   groups stay in the worklist.

**These are still draft import outputs** and must not be used on production
Sicon until IT, Contracts and Finance validate a sandbox import. The PDF is
a watermarked internal draft pending legal approval. Sicon prices, billing
stock codes, serials and SLA values are not silently inferred.

No step above calls an external API or depends on Sicon tokens. Existing
Contracts OS register/search/reporting/renewal functions also remain
independent of Sicon credentials.

## Future API adapter — deliberately non-operational

New read-only routes:

- `GET /api/smartquote/sicon/status` — returns the available manual mode,
  without reading or disclosing keys, environment variables or bearer tokens.
- `GET /api/smartquote/sicon/setups/{intake_id}/preview` — constructs a
  **NON-EXECUTABLE** mapping proposal for a contract header, staged contract
  lines and serialised equipment. It cannot send any information to Sicon.

Published Release 26 API operations documented in the plan:

- Contracts: `POST /api/Contract/CreateUpdateContract`
- Contract lines: `POST /api/ContractLine/PostContractLine`
- Equipment: `POST /api/SiconEquipment/PostNewEquipment`

Public spec:
https://webapidocs.blob.core.windows.net/published/Contracts.R260200c.json

Equipment spec:
https://webapidocs.blob.core.windows.net/published/CC.R260200c.json

The preview **deliberately leaves** required/uncertain API values blank:
numeric Sicon ContractID/ContractLineID, new-equipment ItemID/CustomerID,
unit price semantics, prorata flags, creation/update IDs, stock and warehouse
mapping, and equipment duplicate matching. A contract NUMBER is not a numeric
Sicon ContractID. Even setting `SICON_API_KEY` or
`SICON_API_WRITE_ENABLED=1` cannot enable live writes in this release.

## Required before enabling future integration

- Confirm WebAPI Release 26 support and modules in Pulse's installed Sicon.
- IT provisions an approved sandbox/test company and scoped credentials,
  outside GitHub, browser storage, and exported documents.
- Verify read-only customer/stock/equipment lookups and returned IDs.
- Verify create-vs-update conventions, required contract-line properties,
  API response types, retries and partial failure recovery.
- Validate 1–5 year and multiple staged commencement-date invoicing, prorata
  VAT and annual renewal amounts against Finance's expected results.
- Check serialised machine deduplication, existing warranties/service history,
  site locations, security, logs and access boundaries.
- Implement a server-side credential vault and a separately authorised,
  auditable, idempotent write client; default remains manual.
- Preserve the Excel fallback and a coordinator override even if integration
  is later implemented.

## Limits

- This is **online-to-Contracts-OS**, not an offline browser storage solution:
  staff still need their approved Contracts OS PWA server and its private
  database. "No Sicon API" does not mean "no company server".
- No account-specific configuration, credentials or live Sage/Sicon records
  have been accessed.
- No customer PDFs, prices, source workbooks, database files or secrets are
  stored in GitHub.
- Maintains `main`, `develop`, PulseFitness.ai, source registration and
  equipment tables without a migration.
