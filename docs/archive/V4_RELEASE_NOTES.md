# Pulse Contracts OS — V4 change log

**17 October 2026 | Controlled local pilot, not approved for company-wide use.**

## Delivered and tested

1. **Safe editing / revision control:** Every contract and editable financial entry has a revision number. When a second coordinator tries to save a stale version, the API refuses the update with HTTP 409; the UI asks the user to reopen the current record. Saving without a revision is refused with HTTP 428.
2. **Renewal history:** The contract editor includes **Renew Contract**. The previous period, value, user-supplied actor and timestamp are stored separately. The agreed active record is updated without deleting previous details.
3. **Eight-sheet Excel Master export:** The approved Excel template remains the basis for all exports. Original styles, formulas, tables, dropdowns and worksheet order are retained; new contract rows use standard contract-cell styles.
4. **Safe Excel re-import:** Exported files carry an invisible version identifier in their *Office document core properties*. In **Import Documents → Re-import an edited Excel Master**, compare changed values against both the original export snapshot and current database before approving changes. Covers Maintenance Database, Expired, Weekly Values, Invoices and Quotes. All edits are opt-in.
5. **Stable matching:** Existing contract records use `Record ID` and ledgers use `Original source` or `Quote ID`, not Excel row number alone. Duplicate identifiers and archived/live sheet moves are flagged, not silently merged.
6. **Conflict protection in imports:** Approved PDF/CSV proposals updating an existing agreement also require the reviewed record revision. Invoice amount is never automatically interpreted as annual contract income.
7. **Local backup:** SQLite online snapshot with integrity check, startup backup at most once per 24h, 14 latest local backups retained, and a local-only manual backup endpoint. **Separate encrypted off-machine disaster recovery is still required.**
8. **Equipment reference:** Existing 2026 catalogue with 6,875 SKUs is retained. Customer equipment linking and manual verification remain available. A catalogue specification is not proof of contractual entitlement.
9. **Basic UX:** Import Documents now includes a simple Excel change-review interface. Contract editor includes a Renew Contract action. The PulseFitness.ai-style black header/blue tabs are preserved. Monthly invoice chart year follows the current calendar year.
10. **Automated QA:** Existing smoke, equipment/export, document approval, and V4 round-trip tests pass in isolated temporary databases. No actual customer records were modified during testing.

## Important limits — do not describe as completed

- **Live scanned handwriting OCR:** Azure Document Intelligence adapter exists but needs approved endpoint/credentials, real-world quality measurement and legal/data governance checks. The Example University example remains labelled manually transcribed, not a generic OCR success.
- **Sage/Sicon live integration:** Not configured or verified; no automatic write-back. A system owner must confirm customer/contract endpoint permissions and field ownership.
- **Hosted multi-user deployment:** Revisions prevent silent lost updates at the API level, but the included program remains bound to `127.0.0.1`. Production hosting, secured database services, device access and operational monitoring have not been implemented.
- **Staff login:** Microsoft sign-in is **parked**, as requested. For a hosted release, use a verified existing PulseFitness.ai portal session or another approved identity/role model; the `actor` text in this pilot is not authenticated and is not an enterprise-grade audit identity.
- **Edited workbook new-record creation:** New Excel rows are surfaced for review but not automatically created. Add them in the platform to check site/contract duplicates.
- **Excel archival sheet moves:** Never cut/paste between current and expired inside an exported workbook and expect automated reconciliation. Use **Move to expired history** in the platform.
- **Excel compatibility:** XML structure and style checks pass. Opening and re-saving in the team's actual Microsoft Excel versions still requires coordinator sign-off; Excel may remove workbook tracking properties in some workflows, in which case a fresh export is needed.
- **Backup limitations:** 14 backups are on the same machine and can be lost with that machine; install separate offsite backups and practise restoration before roll-out.
- **Capacity:** Preformatted free contract/expired rows in the approved Excel template have a maximum; the platform refuses to go beyond rather than generating an incorrectly styled workbook. Large-scale deployment requires template growth and reporting recalculation tests.
- **No email delivery, signed-in portal integration, or scheduled sales report distribution:** Requires live integrations/access.

## How to test V4

```powershell
py -m pip install -r requirements.txt
py tests/smoke.py
py tests/v2.py
py tests/v3.py
py tests/v4.py
```

Each test works on a **temporary copy** of the approved workbook/database. The new tests verify safe editing, Excel export metadata, three-way differences, explicit conflict acceptance, finance row updates, renewal history and backup creation.

## Next production approval gates

- Representative scanned document testing (at least 50 distinct documents, including poor scans and handwriting) and field-by-field error measurement.
- End-to-end customer/asset reconciliation with actual Sage/Sicon read-only export, including centrally billed agreements.
- Portal-authenticated staff roles; UK/EU hosting, penetration test, retention and malware scanning.
- Controlled Excel desktop sign-off with the coordinators and directors; reconciled contract and invoice figures.
- Multi-user acceptance on staging and a documented restore drill.
