# Pulse Fitness Contracts OS + SmartQuote — Windows single-computer pilot

**This package runs completely on one Windows PC. No Azure account, no
in-house server computer, no Docker and no separate Python installation.**

It is a **supervised internal pilot**, not an approved public/production
release. Customer PDF issuance requires separate approved rates, terms
and sign-off.

## Updated coordinator workflow (19 November 2026)

- **Action Centre:** each task has its own responsive record card. Choose progress, optionally expand notes or the next review date, then select **Save update**. No horizontal table scroll is needed.
- **SmartQuote:** customer, site, contact, cover type, term, discount and contract dates are laid out in clear labelled columns. Existing price data comes from the unified Master Price List.
- **Settings (top right):** choose **Sign out** at the end of the shift. Administrators also have **Pricing & agreement settings**, **Data quality review** and **Service & Sicon records**; ordinary coordinators do not need the historic technical pages.
- **Contracts:** **Add contract** always starts a new record in the Maintenance Database. For existing records, choose **Print maintenance agreement** to open a **watermarked internal review copy** with recorded cover details and any linked equipment. It is not a signed legal agreement and MUST NOT be issued as one.
- **Dates:** UK-formatted dates show as DD/MM/YYYY; Excel serial-date values from source worksheets are displayed as UK dates, while the underlying stored values are preserved.
- **Data safety:** keep the original agreement and approved terms intact. The new print preview does not fabricate legal customer identity, equipment coverage, price approvals, exclusions or signatures.

## How to install

1. Download the **Windows single-PC pilot package** from the GitHub
   Actions artifact on the feature branch. Keep the package together:
   extract the complete ZIP, including its `_internal` folder, into a
   private Windows folder such as `C:\Pulse Fitness\Contracts OS`.
   **Do not extract the program or its live database to OneDrive.**
2. Double-click **Pulse Contracts OS.exe**. Windows may display an
   unsigned-software SmartScreen warning; the build is not code-signed.
   Pulse IT must first review and approve the exact GitHub build before
   running it with confidential company data.
3. On first launch, select the approved current
   **Master Maintenance Contract .xlsx** file. The program checks the
   workbook's expected format and imports the contract records to its
   own local database. It never modifies the selected original file.
   Do not use an outdated workbook or a duplicate export; data parity
   must be checked against the current operational Master.
4. Create a **named local Administrator** and a strong password
   (12 characters minimum). Save that password in Pulse's approved
   password manager; the program has no built-in password recovery.
5. The Windows launcher opens the default browser at an address such as
   `http://127.0.0.1:56789/`. This address is **only on that PC**.
   Enter the named Administrator credentials. Keep the small app
   control window open or minimised. Closing it stops the local app.
6. Under **SmartQuote → Unified Master Price List**, import and
   activate the approved reconciled Sage + Master price CSV. It
   contains source SKUs and prices, not approved contract tariffs.
   **Master overrides Sage on initial reconciliation; subsequent
   approved imports replace matching item prices only.**
7. Run two genuine invoice/delivery-note acceptance tests before
   entering real quotations. Exact machine SKUs match automatically,
   while spare parts, held prices and undelivered items are excluded.
   Confirm source quantities and serials, set a suitable internal
   service rate and download the watermarked internal PDF.

## If the application does not open

Use the **latest successfully verified Windows package** and extract the
**entire** ZIP before running \`Pulse Contracts OS.exe\`. The accompanying
\`_internal\` folder must be beside the executable; running it directly from
the ZIP preview will not work.

If startup fails, the launcher now shows an error dialog rather than
silently closing. It also writes a local diagnostic where possible:

\`%LOCALAPPDATA%\Pulse Fitness\Contracts OS\startup-diagnostics.txt\`

Send the exact on-screen error and a reviewed copy of this **local** file
to Pulse IT. It may contain workstation paths and must **never** be pasted
into the public GitHub repository or attached to public workflow runs.
Do not delete or replace the \`data\` folder to attempt a fix.

## Where files are stored

The app's **live** data are stored at:

`%LOCALAPPDATA%\Pulse Fitness\Contracts OS\data\`

- `contracts.sqlite3` — live contracts, Master price versions,
  source invoices and quotation records (database).
- `approved_master.xlsx` — approved original contract workbook.
- `backups\` — local snapshot backups.
- `%LOCALAPPDATA%\Pulse Fitness\Contracts OS\session.secret` —
  signing key for named local logins; never share or upload.

The app itself can be replaced or updated without overwriting the
working data, but **never delete or casually replace the data folder**.
Restrict PC access with a named Windows account, company device
encryption (BitLocker) and appropriate antivirus policies.

## OneDrive — backup only

A normal OneDrive-synchronised folder is **not safe for the live SQLite
database**, its WAL files or its locking files. The app refuses such a
live storage path.

Use **Create local backup** from the launcher. After it succeeds, use
Pulse-approved company OneDrive/SharePoint storage to keep a separate
protected off-PC copy of the backup **and the corresponding approved
Master workbook**. Follow the company's access control, retention
and encryption policy. Do not put raw confidential backups in a
personal OneDrive account. Periodically test recovery on a separate
disposable Windows machine.

## Operation

- The app is private to the computer; `127.0.0.1` cannot be accessed
  from other PCs. Only one running instance is allowed.
- Chrome or Edge is used for the existing Pulse-branded web interface.
  This is a local app launcher with a bundled Python engine, not a
  stand-alone static HTML page.
- The PC must stay on while SmartQuote is used. No cloud/in-house
  server is required, but **the launcher must be open**.
- Local PDF extraction works for PDFs containing selectable text.
  Scanned/photographed documents can require OCR; the desktop
  package deliberately leaves OCR off until locally configured.
- **Internal PDF quotes only** until Pulse approves the real maintenance
  tariffs and terms and completes commercial release acceptance.
- Contracts OS and SmartQuote use the same private local database and
  the same named staff login. Sage and Sicon are not modified.

## Operational sign-off before genuine everyday use

Check real contract counts, source workbook dates, renewals, all
historical notes, import/export parity, device backup restore,
pricing source integrity, two coordinators' sample quotations and
Pulse's approved tariff/terms/exclusion policies. Keep the previous
Master Excel workbook and SmartQuote process available as a fallback
until that verification is complete.

**If Windows warns that the app is unrecognised, do not bypass
company security policy to run it; obtain IT approval or signed
release first.** No customer records, original invoices, price
exports, proprietary fonts or secrets are bundled in GitHub binaries.
