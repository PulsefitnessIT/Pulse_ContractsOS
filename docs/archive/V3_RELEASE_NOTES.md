# Pulse Fitness Contracts OS — Version 3

**Status:** local staff-demo application. **Not** an authorised or securely hosted live system.

## What works

1. **Reviewable document imports:** upload text-based PDFs, CSV or Excel. Read C-prefixed contract reference candidates from PDF text without confusing them with invoice numbers. Preserve invoice references, account references, product-code candidates and their PDF page numbers for review.
2. **Scanned-document option:** when Pulse Fitness IT explicitly configures the optional Azure AI Document Intelligence endpoint and secret, scanned PDFs can be sent to its `prebuilt-layout` reader. Extracted lines are passed through the *same conservative candidate parser*. This connection was implemented but **not tested against a live Azure tenant** here. Handwriting accuracy and document grouping must be validated before production.
3. **Editable review:** staff can inspect the actual uploaded document, correct suggested contract details, enter a proposal when a scan has no readable text, search for the correct contract and explicitly choose an existing record.
4. **Field comparison and approval:** existing values are shown beside suggested values. The reviewer must explicitly opt in to overwrite every conflicting field. Contract details are not copied directly from invoices without approval. Newly created document-based contracts must have a customer and contract number.
5. **Catalogue-assisted equipment linking:** stock codes identified in a readable document can be checked against the 2026 product catalogue. Staff select the precise active contract and confirm serial, quantity, dates and invoice reference. Source file and page numbers are retained in the link's notes. Document-provenance duplicate checks prevent an identical link from being accepted twice.
6. **Exact-template Excel export:** uses the original approved eight-sheet workbook. Existing table definitions, filters, original-style rows, date/currency formats, formulas, historic notes and director/report tabs are preserved. Equipment details are available as a separate CSV register rather than adding unwanted sheets to the familiar Master.
7. **PulseFitness.ai-like UI:** the black portal header, blue navigation accents and pale workspace from V2 remain.

## Test coverage performed

- V1 smoke tests: contract lifecycle, approval and duplicate-upload handling, weekly values, invoices, historical archiving and Excel structural integrity.
- V2 tests: equipment search/link, suggested console/frame details and new-row Excel styles.
- V3 tests: PDF reference separation, original-file access, editable proposals, conflict rejection and explicit replacement, manual fallback for unreadable PDFs, catalogue-backed equipment link and duplicate prevention, exact-format workbook export.

Run from the project root:

```powershell
py tests/smoke.py
py tests/v2.py
py tests/v3.py
```

Each test creates a disposable database and does not overwrite the included pilot data.

## Optional OCR setup (IT configuration only)

Azure Document Intelligence uses the `2024-11-30` REST layout API. Configure these environment variables **only after IT approval and confirmation of data residency and processing terms**:

```powershell
$env:PULSE_AZURE_DOC_ENDPOINT="https://<your-azure-document-intelligence-resource>.cognitiveservices.azure.com"
$env:PULSE_AZURE_DOC_KEY="<securely-supplied-key>"
py run.py
```

Never copy secrets into `.py` files, SharePoint document notes or the ZIP. In a production system, replace environment keys with managed secrets, and validate recognised handwritten references and invoice grouping before reliance.

Without this configuration, a scanned PDF is stored for review and its contract details can be entered manually. The Example University sample is a clearly labelled *hand-transcribed demo*, not a successful OCR test.

## Important remaining work

- **Corporate sign-in and deployment:** Microsoft Entra ID, user roles, central database, secure storage, file antivirus checks, encrypted backups and restore drills, application monitoring.
- **Document extraction quality:** sampled invoice recognition, reliable multi-page invoice grouping, handwriting field confidence, serial/quantity association, verified customer/site/account matching.
- **Sage/Sicon integration:** validate API permissions, canonical customer IDs, account mappings and field ownership; introduce read-only synchronisation before any approved write-back.
- **Excel acceptance:** visual tests using Microsoft Excel on Pulse's approved PCs, including all filters, report recalculation, printing/PDF and row movement.
- **Multi-user protections:** optimistic locking, audit users authenticated by SSO, approvals and transactional imports, limiting updates while Excel copies are out of date.

Do not use this build for live financial decisions or expose it directly to the internet. Version 3 is a working pilot that demonstrates the import approval flow, not a completed production SaaS.
