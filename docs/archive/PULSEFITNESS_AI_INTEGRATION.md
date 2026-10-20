# Integrating Pulse Contracts OS into PulseFitness.ai

**Scope:** integration plan, not a live integration or permission to modify the existing portal.

## Recommended navigation

Within the existing **Pulse Fitness Pro → Operations** workspace, add one **Contracts** module beside Documents and Reports. Keep the existing corporate navigation and styling; the user sees the same authenticated header, language settings and responsive menu. The module should have five subareas: Overview, Contracts, Import Documents, Invoices, Reports. Show Equipment under a contract or as the existing Equipment module's deep link rather than adding too many tabs.

## Integration contract

- **Front end:** mount the module at an authenticated internal path such as `/pulse/contracts`. Do not paste new authentication logic into the browser or trust user-supplied actor names.
- **SSO:** authorise via the main portal identity provider (recommended Microsoft Entra ID / OIDC), with the portal forwarding an authenticated identity to the contracts API through an approved server-side gateway. Validate audience, issuer, expiry and contract-area permissions at the API boundary.
- **Database:** PostgreSQL for shared contracts with unique stable IDs for customers, sites, agreements, invoices and equipment. Migrate the local SQLite data with an audited one-time importer; do not mount the existing local SQLite file on several machines.
- **Files:** scanned invoices and Excel uploads in encrypted object storage under short-lived, audited download permissions.
- **Actions:** review/approve API calls require the authenticated editor's ID and concurrency token; consider an additional reviewer for exceptions (date conflicts, financial amounts, contract number changes).
- **Sage/Sicon:** use a service connector with read-only customer and account resolution as the first milestone. Don't guess contract status or entitlement from a sales invoice or product catalogue.
- **Exact workbook:** pin the approved eight-sheet `.xlsx` template by a version identifier. Every export should retain the same sheet order, columns, styles, calculated cells, filters, dropdowns, metadata and original site colours; attach a separate export timestamp in the filename, not inserted into the approved layout.

## Acceptance gateway before staff launch

1. The current Excel format must be visually identical, with all new rows matching ordinary contract rows, and the Excel filters opening and sorting correctly.
2. Every approved document import must be traceable to its source filename/page, approving user and change record.
3. Uploading a previously processed file must not generate duplicate contracts or duplicate assets.
4. Missing or contradictory dates, prices, payment frequency or coverage remain unanswered until evidence is confirmed.
5. Test with at least two coordinators performing concurrent updates and a director generating an invoice report.
6. Complete security and restoration tests, then run parallel Excel/platform operation until reconciled and signed off.
