# Stage the V12 source on Windows (without publishing customer data)

The source ZIP is not yet in GitHub. These steps only prepare local files for review. They do **not** automatically push to GitHub.

## Prerequisites
- Python 3.10 or later.
- Git for Windows.
- Your existing V12 archive downloaded from ChatGPT.

## Prepare source for inspection
1. Open PowerShell.
2. Clone the private repository and switch to the development branch:

```powershell
git clone https://github.com/PulsefitnessIT/Pulse_ContractsOS.git
cd Pulse_ContractsOS
git switch develop
```

3. Run the preparation tool, using the actual location of your V12 ZIP:

```powershell
python tools/prepare_v12_source.py "C:\Users\YOURUSERNAME\Downloads\Pulse_Fitness_Contracts_Platform_v12_Reporting_and_PPM.zip" "C:\Pulse_Contracts_V12_Source_Review"
```

4. Open `C:\Pulse_Contracts_V12_Source_Review\MIGRATION_REVIEW.json` and verify the **copied**, **skipped** and **flagged** lists.
5. Review all staged code to ensure no customer information, passwords, tokens or production settings remain.

## Publishing (only after explicit security review)
Do not commit a ZIP, a database, original invoices, actual customer Excel files, or the generated review report. Copy approved source files from the staging directory to the appropriate repository paths, then run the original V12 tests. Follow `docs/MIGRATION_CHECKLIST.md` before tagging a release.

**Note:** The tool deliberately excludes document files, images and binaries. Harmless branding assets and a sanitised empty Excel layout may need review and inclusion separately. This restriction protects data while the archive contents are still unknown.
