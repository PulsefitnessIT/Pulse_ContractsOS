# Pulse Fitness — first-login Setup Centre (19 November 2026)

## What changed

The top-right Settings → Setup & settings opens one dedicated administrator page, NOT the historical technical screens. Sign out and Export Excel Master remain in the same menu. Coordinator and Viewer accounts cannot modify commercial settings.

The first successful Administrator sign-in on a device opens a six-step setup wizard. Its first-open, deferred, and completed state is saved to the private SQLite database, not browser storage. It can be reopened from Settings.

The Windows launcher already requires a confirmed Maintenance Master workbook and a named local Administrator before initial sign-in; the wizard checks those data and guides the additional commercial setup.

## Guided steps

1. Maintenance contracts: verify the approved workbook and stored contracts are readable. No overwrite.
2. Equipment prices: confirm or upload the active Unified Master price CSV. It requires SKU and Price GBP columns, with optional Description, Product Group, Price Status. Review all changes; activation needs the Administrator's reason and held-price confirmation. Unmentioned SKUs and issued quotes are retained.
3. Company details: verified legal company name, company number, registered address, service email, telephone, and VAT number as applicable. Approval evidence is required.
4. Agreement terms: upload the legally approved current maintenance terms PDF. This does not replace the separately approved signed maintenance agreement template.
5. Maintenance rates: review the maintenance tariff rate groups and Silver/Gold/Platinum multipliers independently of equipment prices. If the approved rate policy is not staged, the screen explains that Commercial and IT must resolve it. No historical percentage is silently approved.
6. Finish setup: every prerequisite is checked again by the server. Continue with internal drafts permits pilot work but leaves setup incomplete; separate customer PDF release authorisation remains blocked until commercial approvals and tests pass.

## Safety controls

- No setup action automatically enables customer PDF issue.
- All writes use existing authenticated, CSRF-protected API approval routes and record the named staff actor.
- Admin-only permissions are enforced on the server, not in the browser.
- A completed wizard still reports any subsequently broken prerequisite.
- Private customer details, prices, credentials, terms and fonts are never committed to the public repository.
- Windows live data remains under %LOCALAPPDATA%\Pulse Fitness\Contracts OS\data. Do not delete on upgrade or put the live DB in OneDrive.

## Remaining dependency

The Unified Master Price List is authoritative for equipment item-price reference. The customer-issue engine still needs a separately verified maintenance tariff policy. The wizard exposes this truthfully rather than referring coordinators to the old V10 source screens or treating equipment prices as approved maintenance rates.

## Verification

Python synthetic tests: tests/test_setup_wizard.py
JavaScript tests: tests/test_setup_centre_ui.cjs
Windows executable self-test verifies setup source and UI assets; the real packaged smoke test logs in as fictional Coordinator and Admin, checks permission denial and saved first-login status, and confirms that unfinished commercial approvals cannot be marked complete.
