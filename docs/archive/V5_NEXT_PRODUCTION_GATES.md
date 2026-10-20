# Pulse Contracts OS — Next production gates

This checklist is for Pulse Fitness management and the developer implementing the module in PulseFitness.ai. Items are **not implemented** merely because they appear below.

## Gate A: Document-reading pilot

- [ ] IT approves the OCR provider, data-processing terms, storage jurisdiction, privacy notices, encryption and retention.
- [ ] Configure `PULSE_AZURE_DOC_ENDPOINT` and `PULSE_AZURE_DOC_KEY` on a secure pilot machine; do not commit credentials to source control.
- [ ] Test the 21-page Example University scan and at least 49 further representative real invoices/contracts, including difficult handwriting and mixed documents.
- [ ] Measure field-level correct extraction for contract references, invoice numbers, printed dates, handwritten dates, site addresses, item codes and serial numbers.
- [ ] Preserve evidence page numbers and any conflicting equipment versus agreement dates for coordinator review; never fill missing recurring contract values from equipment invoices.
- [ ] Build an approval screen where staff see the source image and proposed field side by side.

## Gate B: Staff acceptance and Excel

- [ ] In desktop Excel, confirm exported tabs, filters, formulas, conditional colours, site-specific fills and current/expired alignment.
- [ ] Test exporting, adding a contract, re-importing it, approving it, exporting again and checking its complete presentation.
- [ ] Test cut/paste of a complete active row to Expired and the reverse, ensuring incomplete transfers are rejected.
- [ ] Validate that invoice and weekly reports reconcile to known original workbook totals; invoices confirmed as sent must be separate from previews.
- [ ] Have at least two experienced coordinators and one new starter complete typical tasks without coaching. Log every confusing control.

## Gate C: Shared system release

- [ ] Host inside the PulseFitness.ai environment; use existing trusted PulseFitness.ai user sessions and roles instead of a new Microsoft sign-in.
- [ ] Disable anonymous mutation endpoints outside localhost; establish a verified actor identity, least-privilege access and full audit records.
- [ ] Migrate SQLite to suitable central transactional storage with version conflict handling, tested restore procedures and off-site encrypted backups.
- [ ] Scan uploads for malware, limit size/types, protect source document access and apply retention/deletion schedules.
- [ ] Complete staging load tests with concurrent coordinators, monitored background document-processing queues and failure alerts.
- [ ] Release progressively to a small pilot group, then to all staff after sign-off.

## Gate D: Source-system integration (after safe pilot)

- [ ] Obtain and confirm Sicon/Sage read-only customer, agreement, account and contract identifiers and their semantics.
- [ ] Use read-only reconciliation for invoice item codes and maintenance agreements; keep legacy references separately.
- [ ] Verify which system owns contract amount, classification, expiry date, Sage check and equipment entitlement. Do not write back to Sage/Sicon until authorised and tested.
- [ ] Add approved scheduled monthly director and quarterly sales reports using the existing communications infrastructure.

**Deployment policy:** this ZIP must not be exposed directly on an office LAN or the internet as-is. Running on `127.0.0.1` is appropriate for the local pilot only.
