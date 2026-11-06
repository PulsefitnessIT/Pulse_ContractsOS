PULSE FITNESS SMARTQUOTE + CONTRACTS OS - PRIVATE WINDOWS PILOT
===============================================================
This is a SUPERVISED, LOOPBACK-ONLY workstation pilot. It is not
a public website, shared server, certified production release,
or automatic commercial quotation approval.

The ZIP contains:
- Pulse_ContractsOS_SmartQuote_Pilot.exe
- Start_SmartQuote_ContractsOS_Pilot.bat
- This guide
No Python installation, Docker, customer data, company secrets,
price lists, customer terms or approved quote are included.

FIRST RUN (WINDOWS)
-------------------
1. Extract ALL files to a private, writable local folder.
2. Place a copy of your latest manager-approved Maintenance Master
   .xlsx in a separate, access-controlled location.
3. Double-click Start_SmartQuote_ContractsOS_Pilot.bat.
4. Provide the complete Master path (copy/paste from Explorer) and
   type APPROVED to authorise making a NEW LOCAL source-backed database.
   If a private_runtime folder already exists, the launcher refuses to
   overwrite it or import a different Master automatically.
5. Create a named Admin login and a unique password of 12+ characters.
6. Sign in at http://127.0.0.1:18080 . Only this PC can connect.
7. Open the SmartQuote tab > Original V10 & August Price Source Setup.
   Use the recovered four-file ZIP named
     Pulse_SmartQuote_V10_ContractsOS_Import_4files.zip
   Review the hashes/record counts and activate the genuine source.
8. Open SmartQuote > Sage Price List Refresh. Upload the complete Sage
   price list (Sage Price List.xlsx), verify the true export date,
   review differences, and activate. Do not label the October seed
   as current just because it was uploaded.
9. Use SmartQuote > Customer quotation readiness to see remaining
   commercial approval requirements.
10. Verify source equipment and try an INTERNAL draft PDF. Do not send
    this document to a customer.
11. An authorised Administrator must approve actual tariff multipliers,
    equipment exceptions, approved terms, VAT, registered supplier
    details and the specific customer quote before any issue.

NORMAL USE
----------
Double-click Start_SmartQuote_ContractsOS_Pilot.bat and log in.
The URL is http://127.0.0.1:18080 . Keep the command window open.
Use "Save & calculate price" to preview source-based prices. Download
the marked internal draft PDF to check the quote. Coordinator roles
can then download manager-approved, numbered customer PDFs.

PRICE/SCOPE POLICY
------------------
- August 2026 Master List Prices take precedence for exact SKUs.
- The exact current Sage Sales Price is a fallback only where the
  machine is absent from the August Master AND its V10 maintenance
  service mapping is verified.
- Some console/strength variants remain blocked for technical review.
- V10 rates, Silver/Gold/Platinum and current maintenance T&Cs are
  PROVISIONAL unless a real authorised manager approves them.
- The quote software never sends emails, activates Sage/Sicon
  agreements or automatically renews an agreement.

DATA PROTECTION
---------------
The data created by first run is in ./private_runtime alongside the EXE.
It contains confidential customers, accounts, prices, quote snapshots,
authentication information and an auto-created session signing secret.
NEVER upload this folder to GitHub or send it as a support attachment.
Back it up to approved encrypted company storage. Keep Windows drive and
folder access restricted to authorised employees.
The portable test server listens only on 127.0.0.1. Never publish it to
the Internet or run it from an open file share.
For multiple users, IT must deploy the separate HTTPS/VPN staging server
with secure cookies, monitored backups and user accounts.

NOT CERTIFIED FOR LIVE CUSTOMER QUOTING
---------------------------------------
Use with real customer quotations only AFTER customer-source reconciliation,
Sage freshness review, contract tariff/terms sign-off, quote PDF acceptance,
an approved data/backup restore test and a real security/IT pilot sign-off.
The application intentionally does not certify those conditions itself.

If Windows blocks an unknown EXE, verify its SHA256 against the GitHub
Actions build output and ask Pulse Fitness IT to approve the executable.
Do not bypass corporate security settings.

Repository: https://github.com/PulsefitnessIT/Pulse_ContractsOS
Development PR: https://github.com/PulsefitnessIT/Pulse_ContractsOS/pull/5
