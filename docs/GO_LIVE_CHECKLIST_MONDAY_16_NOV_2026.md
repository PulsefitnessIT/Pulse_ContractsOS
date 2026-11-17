# PULSE FITNESS | Contracts OS + SmartQuote — Monday 16 Nov 2026

**Edition: Friday 13 November 2026. Target: ONE Windows PC, no Azure,
no Docker on the PC, no in-house server.**

## Launch decision

- **GO (conditional):** controlled single-PC use for contract search/edit,
  coordinator actions, billing-previews and branded **INTERNAL** SmartQuote
  draft estimates after real-data checks below pass. Keep the existing
  Maintenance Master and current quoting workflow available.
- **NO-GO for full Excel replacement:** the five new operational source tabs
  are ingested and searchable **read-only**, but confirmed per-year PPM
  scheduling, editable commercial/MOD planners and Sicon contract
  reconciliation still need their own accepted operating workflows.
- **NO-GO for customer quotations:** current fast quotes use manually
  selected/historical maintenance rate assumptions; externally issued
  quotations require approved commercial tariffs and terms separately.
- **NO-GO for importing into an existing pilot without backup:** the
  latest Master must be imported through a *fresh* private profile or
  an explicit reviewed reconciliation. Do not overwrite a live database.

## Friday 13 November — installation owner + Contracts team

1. **Select the PC**: company-managed Windows 11 64-bit preferred,
   BitLocker/device security enabled, adequate free local storage
   (10 GB+ practical reserve) and a dedicated Windows user with IT
   access to the local app folder.
2. **Download the exact latest build** from the GitHub Actions
   `Windows single-PC pilot package` artifact on
   `feature/unified-smartquote-intake`. Require successful Windows
   executable self-test, both Python source test versions, dependency
   check and server-image check on the *same commit*. The EXE is
   currently **unsigned**: the IT owner must authorise execution.
3. **Extract the entire ZIP** to `C:\Pulse Fitness\Contracts OS`
   (or another local program folder). Do not run from OneDrive,
   Downloads ZIP preview or a network share. Keep the `_internal`
   folder beside the EXE.
4. **First run**: double-click `Pulse Contracts OS.exe`. Select
   `MASTER of Maintenance Contract Spreadsheet - NEW MASTER 12.11(2).xlsx`
   (the exact user-provided latest workbook), review the displayed
   source counts and accept. Keep the original intact.
5. **Confirm original Master data** in Contracts OS:
   - 600 commercial active contract rows
   - 57 MOD active register rows
   - 8,387 expired / historical rows
   - 1,410 commercial Service Planner source entries
   - 337 MOD Service Planner source entries
   - 1,725 Sicon Contracts source entries
   - 4,917 commercial annual PPM source entries
   - 1,296 MOD annual PPM source entries
   - The last five are SOURCE EVIDENCE, not auto-approved contract/PPM
     activity. Reconcile any difference to the uploaded workbook first.
6. **Create a named Administrator password**, store it using approved
   company credentials storage, and test log-in/log-out.
7. **SmartQuote price activation**: import
   `Pulse_Fitness_Unified_Master_Price_List_2026-11-05.csv` from a
   protected local copy, review the seven prior conflicting Master
   codes and all held/missing prices, verify the prices are still
   current as of 13 November, then activate the revision. The single
   Master prices override earlier Sage; future approved imports
   override matching codes only.
8. **Backup** using the app's create-backup button. Copy a *completed*
   backup to approved company OneDrive / SharePoint **separately from
   the LIVE database**. Perform at least one recovery check on a
   separate/disposable profile before relying on the data.

## Friday afternoon / Monday morning: four acceptance scenarios

Ask the contracts coordinator who will operate the PC to complete
the following on genuine samples. The existing workbook remains the
source of truth until this comparison is documented.

| Check | Proof to retain | Go/no-go |
| --- | --- | --- |
| Contract lookup, MOD and Expired | 10 varied records; compare dates, IDs, notes, values and DD mapping | Any missing or mismatched source field = NO-GO |
| Service/Sicon/PPM source | All five source registers show the expected row counts and sample details, with VERIFY unapproved | Missing source row = NO-GO |
| Real SmartQuote document | Test Evesham, Horizon and N100621 PDF; exact SKUs, quantities, serial lists, accessories and TO FOLLOW rows compared manually | Incorrect automatic inclusion = NO-GO |
| Excel export and recovery | Download exported 15-tab file; confirm two hidden annual sheets, notes, filters, formulas and source metadata; test backup restore | Any lost row/ID/hidden sheet = NO-GO |

Additionally, create one short-term and one multi-year internal
maintenance draft, change a rate, save/reopen, recalculate and verify
the annual/term arithmetic against the existing quotation workbook.
The PDF must be clearly marked
**INTERNAL DRAFT — NOT AUTHORISED FOR CUSTOMER ISSUE**.

## Monday 16 November — decision

**Proceed with a limited supervised pilot only when** the installing
staff member and Contracts owner have confirmed all four acceptance
scenarios, backups and the activated Master price-book version.
Record the app commit/version, local data snapshot SHA and any issues.

During the pilot the following remain in Excel/manual review:
- assigning or completing service planner/annual PPM records,
- resolving SICON ONLY and VERIFY entitlement statuses,
- financial recognition and posted invoicing,
- externally binding customer quotations.

For those workflows, the platform's source views are usable for
**review**, but are not a safe replacement for coordinated source
operations yet. This is a material distinction, not a cosmetic issue.

### Immediate escalation if any check fails

Close the desktop launcher, leave the private data directory intact,
retain the original Excel workbook, record the exact failing source
record and return to the established Excel/quotation workflow. Do
not manually edit `contracts.sqlite3` or copy its active WAL files
to OneDrive. Escalate to the platform developer / Pulse IT for a
reviewed fix and fresh build.
