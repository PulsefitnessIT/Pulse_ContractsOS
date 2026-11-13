# Founder engineering review — unified SmartQuote + Contracts OS

**Reviewed:** 2 November 2026  
**Branch:** `feature/unified-smartquote-intake` (not merged to `main`)  
**Scope:** integration routers, pilot identity controls, quotation persistence and
templates, source CI, original SmartQuote V10 handover adapter, Contracts OS
contract-setup/Sicon preview restrictions, desktop/PWA integration boundaries.

## Verdict

**Continue the unified product; do not release it commercially.** The accepted
quote intake and Contract Setup Workbench are sound foundations for a controlled
pilot. The quotation workspace required repair, and the verified SmartQuote
pricing engine is not yet running inside the Contracts OS service.

This is a targeted architectural and integration code review, not a completed
line-by-line audit of every historical archived release or an independent
penetration test.

## Found issues and remediation

| Severity | Finding | Result |
|---|---|---|
| High | Browser quotation view contained invalid JavaScript string concatenation | Rebuilt the view; source parsed by JavaScript compiler, checked by CI |
| High | Draft creation disappeared when original SmartQuote database was disconnected | Split independent native draft and historical register loading |
| High | Previous 'Viewer' write check compared a username to the literal role name | Verified role is now carried in the pilot session context; writes are forbidden to Viewer |
| Medium | Coordinator could create only one equipment line and couldn't reopen a draft | Added multi-line builder, saved-draft register, revision-aware edit and conflict response |
| Medium | Separate manual JSON transfer was still required for accepted source quotations | Added explicit archived-PDF-integrity-checked preview + direct intake action |
| Medium | Historic quote browser opened SQLite handles without guaranteed closure | Added deterministic read-only connection closure |
| Medium | Native drafts had no explicit readiness/serial checks | Added source-neutral readiness API and unit tests |
| Medium | No path for source-derived equipment lookup | Added optional privately staged SmartQuote V10 identity catalogue search (NO rates) |
| Medium | Browser code and quote-focused pytest were not covered by repository source CI | Extended source-validation workflow with JS syntax, backend regression tests |
| Open | Duplicate customer/contract identity and branch-wide migration test with real approved data | Requires protected representative staging snapshot and Sicon sandbox |
| Open | Full SmartQuote equipment matching, RRP/price calculations, manager approvals and PDF issuance | Not implemented in Contracts OS; original SmartQuote remains authoritative |
| Open | Corporate identity, MFA, protected hosting, monitoring, back-ups and staff rollout | Not production-approved |

## Current verified architecture

- **One user-facing Contracts OS shell:** SmartQuote, accepted-quote review,
  contract setup, equipment, invoicing and reporting navigation.
- **Two source stores for the pilot:** Contracts OS drafts/contract setup in
  `contracts.sqlite3`; read-only original SmartQuote history in a separately
  configured `smartquote_local.db`. This is not yet a single merged database.
- **Private catalogue:** optionally point `PULSE_SMARTQUOTE_CATALOG_JSON` at an
  IT-staged copy of the *original* V10 `data/catalog.json`. It exposes SKU
  identity only and blocks duplicate SKU auto-selection.
- **Accepted quote handover:** uses original PDF bytes, hash verification,
  the locked issued quote value snapshot and the same source-derived converter
  as the original SmartQuote app. Repeated imports are idempotent. Price
  approval is conservatively left false so staff must validate commercial
  authority; no Sicon write occurs.
- **Native quote drafts:** unpriced, additive records and revision-controlled
  edits. Users cannot force `approved=true` or create server-side prices by
  forging request bodies.

## Validation, not yet deployment

Source changes have been committed; GitHub source validation now runs Python
compile, JS parse, focused pytest and existing fictional-data regression suites.
Locally the authored quotation JavaScript parsed successfully in V8. **Passing
GitHub CI and end-to-end Windows testing must be confirmed before release;**
commit existence does not establish green CI.

The real user-provided catalogue, customer database, invoices, pricing source and
approved Sicon templates have NOT been imported to GitHub. Test with a disposable
protected snapshot only and reconcile source and target record counts and
financial hashes before considering migration.

## Next controlled engineering phase

1. Build a dedicated SmartQuote pricing service inside Contracts OS that imports
   source algorithms and approved pricing data without inventing RRPs.
2. Reconcile legacy/historic SKU, console, staged-cover and discount edge cases,
   including high-volume invoices and repeat serials.
3. Build role-controlled commercial approval and quotation PDF issuance with
   immutable snapshots and signed customer acceptance evidence.
4. Run parallel old/new quote calculations and PDF comparisons on approved
   fictional and authorised staging cases; block cutover on any mismatch.
5. Only then migrate historical quotes to one protected database, rehearse
   rollback and retire the original staff-facing SmartQuote application.
6. Keep Sage/Sicon import mapping in REVIEW_ONLY mode until Sicon sandbox proof
   and explicit IT/commercial release approval.
