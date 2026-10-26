# Unified Contracts OS — Contract Setup Workbench development

Protected development branch: feature/unified-smartquote-intake. No live deployment.

## Implemented after accepted-quote intake

- Importing an accepted SmartQuote revision automatically creates exactly one matching setup case.
- One staged, auditable coordinator workbench appears directly below the accepted quote (no new application or separate manual case creation).
- Group verification of Sage customer account, Sicon site ID, contract reference, purchase order, billing frequency and billing contact.
- The accepted quotation stays immutable; verified administrative corrections are stored separately with staff/time audit history.
- Individual missing machine serials can be verified against evidence without replacing archived quote/line details.
- Signed PDF evidence upload to private server storage only after required details and pricing are approved; coordinator attests they checked signatures.
- Clear order of operations: signed agreement, Sicon contract imported, then Sicon equipment imported. External confirmations require real references and evidence.
- Two distinct contract/equipment mapping previews preserve staged cover dates, one serial per machine, package, annual and first-period values.
- Previews say REVIEW_ONLY_MAPPING_PLAN_NOT_A_SICON_IMPORT and cannot be mistaken for a real ready-to-upload Sage/Sicon workbook.
- Existing Maintenance Master register, ledger, equipment, invoices, customer history, and Excel export are not overwritten.
- Case revisions guard against concurrent staff edits. Repeat confirmations using the same external Sicon reference are idempotent.
- The two real Sicon import templates and approved revised agreement PDF are still required for mapping and sandbox validation.

## Coordinator workflow

1. Open Accepted quotes, review the quote — its Contract Setup Workbench is already there.
2. If needed, correct just the Sage/Sicon references, billing details and missing serial numbers together.
3. Use the approved agreement; upload the customer's signed copy and confirm signatures were checked.
4. Complete the Sicon contract import using the separately approved mapping. Confirm the returned Sicon contract number.
5. Complete the equipment import as a separate batch referencing that contract. Confirm the batch.
6. Future-dated cover is scheduled, not automatically activated or billed by this pilot.

## Release gates

- All customer data, templates, signed agreements and local databases stay in protected runtime outside GitHub.
- There is no Sicon API/write-back here; entering a contract number records what a coordinator says was imported, it does not prove an API transaction.
- Both actual Sicon Excel import templates need verified field mappings and a successful controlled trial import.
- The revised Maintenance Agreement still requires approved legal terms and a signed schedule for staged packages.
- Managers must approve source RRPs, Sage fallback and package tariffs before customer issue.
- Run synthetic CI and then supervised UAT with Mandy and Claire on disposable approved pilot records.