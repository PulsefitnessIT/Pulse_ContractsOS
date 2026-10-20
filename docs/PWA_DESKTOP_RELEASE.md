# Desktop PWA for Pulse Contracts OS

## State
The PWA implementation and full integration source are included in the downloadable source-only feature bundle. This GitHub branch contains independently reviewable installation assets. **The full application source is not yet in GitHub**, so this branch cannot run by itself.

## Windows installation
Deploy the independent FastAPI app at an IT-managed HTTPS URL. Sign in via Chrome or Edge and click **Install desktop app**, or use the browser menu > Apps > Install this site as an app. Python remains server-side; not required on staff devices.

## PWA security
- Caches only generic offline-help HTML and an original icon.
- Does **not** cache contracts, customer data, invoices, exports, dashboards or API responses.
- Requires online access/VPN for operational use.
- Still uses existing server-side authorisation; no Microsoft login, PulseFitness.ai integration or public release.
- Requires the full app, approved data migration, centrally hosted HTTPS, user acceptance and security review before staff rollout.

## Integration notes
The source bundle applies these app changes:
1. In `app/main.py`, serve `/manifest.webmanifest` with `application/manifest+json` and `/sw.js` with `application/javascript` and `Service-Worker-Allowed: /`.
2. In `app/pilot_access.py`, exempt only the public installation manifest and service-worker route from the pilot login redirect.
3. Add manifest/favicon/script links and `installPulseApp` button to `app/static/index.html`; add manifest and script to `pilot-login.html`.
4. Add button CSS to `app/static/styles.css`.
5. Include 192×192 and 512×512 original icon PNGs and run `tests/v13_pwa.py` with disposable pilot fixture data.
Do not publish the app source ZIP or databases as public GitHub release assets.
