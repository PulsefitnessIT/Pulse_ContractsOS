# Pulse Contracts OS — Production SaaS Blueprint

## Product promise

Give every Pulse Fitness colleague **one straightforward place** to find contracts, update details, upload commercial documents, view monthly invoice activity, manage renewals and obtain the **exact approved Maintenance Master Excel workbook** on demand. Staff should not be asked to maintain parallel spreadsheets or dozens of validation queues.

The first local working prototype is provided in this package. The hosted multi-user SaaS is the next engineering phase, not something implied to be live already.

## Five-screen information architecture

1. **Overview** — simple dashboard, current status, contract classifications, invoice preview trend, key renewal exceptions.
2. **Contracts** — familiar filtered register; client record reveals all 37 existing columns plus source documents and revision history; status filter switches active/expired without row copying.
3. **Import documents** — upload PDF, XLSX and CSV; preview extracted fields and proposed changes next to invoice source and evidence; confirm or reject.
4. **Invoices** — monthly register, preview vs confirmed-sent totals, edit and add entries, director summary export.
5. **Reports** — quarterly warranties/contracts by sales manager, weekly values, directors' summaries, *exact-layout Excel backup*.

## Data domains

| Domain | Keys | Important distinctions |
|---|---|---|
| Customer | Sage account ID, canonical legal name | Parent billing account may have many sites |
| Site | Site account ID, location | Several contracts can exist for one site |
| Contract | Verified contract number and internal immutable ID | Contract number can be absent or historical; never use site name as sole key |
| Contract coverage | Contract ID + asset ID + coverage dates | Machine warranty dates are not always the same as the contract dates |
| Asset | Serial number, item/model code | Quantity/serial and console details extracted per machine |
| Invoice | Invoice number, account and period | Invoice number differs from invoice classification code and contract number |
| Invoice line | Invoice ID + line ID | Equipment sales invoices do not equal recurring maintenance income |
| Document | SHA-256, type, original file, upload actor | Repeated file hashes are flagged |
| Extracted field | Document ID + page + bounding evidence | Confidence and handwritten vs printed source retained |
| Change history | Actor, old/new value, action, approval | Every agreed change can be traced/reversed |

## Exact-template Excel export — non-negotiable requirement

- Store a **version-controlled approved XLSX template** rather than generating a workbook design anew.
- Maintain original worksheet names/order and all 37 columns in the Maintenance Database and Expired worksheets.
- Preserve site colours, fonts, fills, comments, number formats, merged cells, filters, dropdowns, charts and formulas.
- Make registered modifications to value cells only; never replace a formula with a cached result.
- Update the approved table ranges or explicitly block additional rows when no capacity remains.
- Generate an Excel file at any time, with all **approved** information.
- Keep versioned snapshots and database backups; one is not a substitute for the other.
- Use an automated workbook comparison suite plus real desktop Excel opening/recalculation testing before release.
- Support optional importing of a *previously exported and subsequently amended* workbook using a version token, field-by-field conflict detection and user approval.

## Suggested production stack

- **Web client:** React/Next.js, TypeScript, accessible component library, AG Grid or TanStack Table. Clear form labels, forgiving input validation, UK dates/GBP.
- **API:** Python FastAPI or Node/NestJS; strict typed schemas, idempotent mutation endpoints.
- **Database:** PostgreSQL with transactional updates, row-level access policies and migrations.
- **File storage:** Azure Blob Storage or AWS S3 with server-side encryption and versioning.
- **Intelligent documents:** Azure Document Intelligence / AWS Textract as page/table OCR; large-language-model extraction for contract clauses *after* OCR; grounded evidence and low-confidence review.
- **Identity:** Microsoft Entra ID, SSO, MFA, least privilege, role-specific permissions.
- **Corporate workflow:** Outlook/Power Automate for quarterly distribution, reminders and alerts.
- **Sage 200/Sicon:** begin with read-only integration and then controlled write-back once contractual API routes and authoritative data ownership are agreed.
- **Observability:** structured logs, retention policies, monitoring and audited admin actions; scheduled recovery testing.

## Import rules

1. Fingerprint the file and refuse an accidental duplicate import.
2. Classify pages and group continuing invoice pages, equipment schedules, certificates and handwritten notes into the correct document groups.
3. Extract customer, delivery site, account, printed invoice number, printed line details and handwritten contract references.
4. Match using verified contract references, Sage account IDs, dates, site identifiers and serial numbers; never only similar names.
5. Distinguish **new agreement**, **update existing**, **create equipment**, **attach invoice**, **duplicate**, **date conflict**, **insufficient evidence**.
6. Preserve exact original text and page-level reference for each proposed change.
7. Present risk or conflict only when necessary; allow grouped approval of unambiguous values.
8. Never infer a maintenance contract's annual value from an equipment sales invoice total.
9. Never overwrite Sage/Sicon information without authorized review and an integration rule.
10. Store approval with author and timestamp. Reconcile and retry failed downstream writes safely.

## Example University acceptance scenario

Fictionalised acceptance scenario based on a 21-page source layout: one equipment register (pp. 1–2), several invoice groups, two handwritten contract numbers **C912345** (Central Campus) and **C912346** (East Campus). Different documents contain different types of dates. A production importer must link the customer to relevant sites, preserve equipment-specific warranty expiry dates, identify the two contract references, and flag discrepancies rather than silently resolving them.

The local prototype contains **manually transcribed demonstration proposals** for the two references only when the *exact source PDF fingerprint* matches. It does **not** purport to recognize handwriting or create a complete asset register automatically. These require the planned OCR and asset modules.

## Launch acceptance gates

- Staff can find, edit and archive a contract in a maximum of a few clicks.
- The 642 current contracts, 8,381 historical agreements, 1,564 weekly entries and all populated invoice/quote rows are migrated without loss.
- A coordinator unfamiliar with the platform can complete the principal tasks without verbal instructions.
- All write operations are audited and reversible by authorized personnel.
- The imported Example University document produces two reviewable references, equipment-level evidence, safe invoice grouping, and no accidental duplicates.
- Monthly invoice preview numbers are separated from confirmed-sent values and cash/revenue reporting.
- Quarterly sales reports are generated dynamically by region/manager.
- Exact-layout Excel exports pass structural checks and desk-side Excel verification, including formula recalculation, colours, filters and adding an entry.
- Backups can be restored and tested.
- Permission controls, GDPR assessment, DPIA where indicated, penetration test and operational runbook pass sign-off before staff rollout.

## Delivery programme

- **Sprint 1–2:** field mapping, Excel baseline and authenticated read-only contracts application.
- **Sprint 3–4:** coordinator CRUD, notes, assets, audit trail, active/expired workflow.
- **Sprint 5–6:** OCR integration, invoice grouping, handwritten-number review, source citations and duplicate protection.
- **Sprint 7–8:** invoice register, weekly values, sales reports, notifications, director dashboard and production-grade Excel export.
- **Sprint 9–10:** staged user acceptance, security, backup recovery and go-live readiness.
- **Later:** approved Sage 200/Sicon write-back, SharePoint/Outlook ingestion, broader asset warranty data.

Timings are indicative and require confirmed scope and named engineering resources.


## Version 2: approved UI and export specification

- Match PulseFitness.ai navigation style: black global header, Pulse Fitness logo/name, light blue active states, horizontal Operations and module nav, clear light workspace. All controls must remain functional; the pilot is not integrated with existing authentication yet.
- Keep 8-tab Master Excel export structurally compatible with approved workbook; newly created rows must receive existing normal data-row styles by column, not reserved blank-row green formatting.
- Never infer contract amount, payment frequency or entitlements from equipment retail catalogue, invoice sales value or generic product warranty.
- Catalogue from 2026 Master Input file contains 6,875 unique SKU variants (first occurrence if duplicate code). Link equipment separately to contracts and provide an individual machine register export.
- Eventually add explicit asset import proposals with page-level evidence, serial-number deduplication, per-machine warranty and invoice references.
