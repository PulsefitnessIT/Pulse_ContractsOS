# Pulse Contracts OS V11 — Independent Pilot Reliability

17 October 2026 | Development package; **not deployed or production-approved**

## Delivered

1. **Excel table auto-expansion.** Added `app/table_growth.py` to extend approved Excel table ranges and filter arrows when contracts, expired records, weekly values, invoices or quotes exceed the original preformatted table capacity. Table metadata, worksheet dimensions and relevant dropdown/conditional formatting ranges update together.
2. **Working renewal calculations for new rows.** Newly inserted Maintenance Database rows beyond row 803 now receive the original renewal-status formula and normal cell styles. No staff action is required to copy formulas down.
3. **Excel export checks.** Exports are rejected if they contain malformed/missing tables, records lie outside filterable tables or the active/expired record totals differ from the saved database snapshot.
4. **Improved export readiness information.** The reporting page describes Excel export readiness; `/api/export/preflight` exposes template headroom and confirms automatic table growth.
5. **Invoice recognition scorecard.** Coordinators can download a CSV of already verified invoice numbers, showing detected versus corrected references. No extra verification form and no automatic amendment of contracts. The file protects against Excel formula injection.
6. **Separate IT staging package.** `Dockerfile.pilot`, `compose.pilot.yml` and `V11_SHARED_PILOT_SETUP.md` describe a single-instance, local-port Docker deployment behind an organisation-managed HTTPS reverse proxy. The application stays separate from Emergent, MongoDB, PulseFitness.ai and Sicon.
7. **Regression coverage.** New tests demonstrate table expansion across all five registers, style and formula preservation, validation range growth beyond 2,495 rows, unchanged worksheet structure and a safe invoice scorecard.

## Restrictions and known limitations
- **Not hosted.** No shared environment has been installed. The provided Compose file is a deployment starting point for IT; a secure HTTPS/VPN gateway, persistent storage and off-host backup plan must be established before office access.
- **Not yet desktop-Excel signed off.** OOXML files pass structural checks, but office users must test the filtered workbook, print/export layout, formulas and colours in Microsoft Excel.
- **No quantified recognition accuracy yet.** Scorecard measures only invoice numbers that a coordinator has already checked. Handwritten contract references still require manual confirmation.
- **No external updates.** The application does not connect or write to PulseFitness.ai, Sage, Sicon or a live finance system.
- **Limited SQLite concurrency.** One managed application instance with local SQLite WAL is appropriate only for a small pilot; multi-instance production service will require a suitable shared database.
- **Some manually edited Excel structures are rejected.** Staff must preserve the original eight tabs and essential columns when re-importing.

## Rollout advice
Install in an isolated staging environment, use accounts with appropriate permissions, test concurrent coordinator workflows and 20+ real invoices, confirm the Excel export in desktop Microsoft Excel, and rehearse restoring an off-host backup. Do not replace the authoritative Maintenance Master during the pilot.
