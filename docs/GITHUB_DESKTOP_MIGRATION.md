# Complete the source migration with GitHub Desktop (Windows)

This guide uses the **sanitised source-only bundle**, not the original V12 pilot ZIP. Never upload the original V12 ZIP or any customer workbook, invoice or database into the repository.

## What you need

- A Windows PC with access to the `PulsefitnessIT` GitHub account.
- GitHub Desktop (https://desktop.github.com/), signed in to that account.
- The **cleaned source ZIP** provided in ChatGPT.

You do **not** need to install Python or open a command prompt for this transfer.

## 7 steps

1. Install/open GitHub Desktop; sign in to the Pulse Fitness GitHub account.
2. Choose **File > Clone repository > URL** and enter `https://github.com/PulsefitnessIT/Pulse_ContractsOS.git`. Pick a convenient local folder and clone.
3. In GitHub Desktop, click **Fetch origin** (if available), then choose **Current branch > feature/pwa-desktop**. Do not commit on `main`.
4. In Windows File Explorer, open the new cleaned source ZIP and extract it. Open the inner `Pulse_ContractsOS_GitHub_Source` folder.
5. Copy **everything inside** that folder into the **root of the cloned `Pulse_ContractsOS` folder**. Keep the pre-existing hidden `.git` folder and `.github` folder intact. The correct layout has `Pulse_ContractsOS/app/main.py`, `Pulse_ContractsOS/tests/`, and `Pulse_ContractsOS/README.md` directly under your clone (not one more nested folder).
6. Return to GitHub Desktop. In **Changes**, verify code/docs/scripts are listed; **none** of these should be shown: `data/`, `pilot_data/`, `.env`, `.sqlite3`, `.xlsx`, `.pdf`, or original `*.zip` files. Commit the changes with the summary `Migrate sanitised V13 Contracts OS source`.
7. Click **Push origin**. The new code should now appear at `https://github.com/PulsefitnessIT/Pulse_ContractsOS/tree/feature/pwa-desktop`.

Please reply **Pushed**. We can verify the source, check automated validation and open a pull request into `develop`.

## What to keep out of GitHub

Operational databases, contracts, customers, service-planner source, catalogues, Excel Master, invoices, backups, tokens, employee credentials and server configuration. These belong in secure, backed-up company storage, provisioned separately to the eventual shared server.

## What is still needed to run the application

This source-only checkout cannot run with real records until the independent runtime receives its approved `approved_master.xlsx`, local database and catalogue **outside GitHub**. For an actual desktop PWA, IT must also deploy a secure HTTPS server and verify staff access. Python remains server-side only.

## About previous files

`docs/archive/` contains optional release notes from V3–V9; these do not run the platform. Keep `tests/` because old regression tests catch new bugs. Keep the legacy Windows setup scripts for developers for now: current wrappers still call them. The GitHub repository should contain just one current application source tree, not full historical version ZIPs.
