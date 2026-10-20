# Pulse Contracts OS – installable desktop PWA (development preview)

## Staff experience
- Open the independent Contracts OS HTTPS site using Edge or Chrome on Windows.
- Click **Install desktop app**, or browser menu -> **Apps** -> **Install this site as an app**.
- Windows creates an app entry/desktop shortcut; staff can pin it to Start or the taskbar.
- The application opens in its own window, without requiring Python on the staff computer.
- Signing in still uses the existing independent pilot users; the app does not integrate with Microsoft sign-in or PulseFitness.ai.

## IT / deployment prerequisites
1. Deploy the **full application** and confidential runtime database separately from GitHub on an IT-managed shared server (V12/V13 source ZIP is *not* itself a deployment).
2. Serve via HTTPS with a trusted certificate (secure context is mandatory for PWA installation/service workers on network URLs).
3. Use a managed reverse proxy, VPN/restricted network, central backups, access control, security review and correct `PULSE_SESSION_SECRET`, `PULSE_PILOT_MODE=1`, `PULSE_COOKIE_SECURE=1`.
4. **Do not expose** the local pilot's backend port directly to staff or the internet.
5. Install from the organisation's HTTPS hostname (each hostname installs separately). Updates to UI are delivered when staff relaunch/connect and the browser refreshes assets.
6. Browser-managed installation depends on Chromium/Edge install support and IT browser policy; no Microsoft Store/EXE distribution is required.

## Security and offline policy
- The service worker precaches **only a generic offline help page and original icon**.
- No customer data, login sessions, HTML dashboards, contract API responses, invoices, exported workbooks or database content is cached for offline use by our service worker.
- Every real application request goes to the central server. Network failure shows a generic **Connection required** page.
- PWA is not an offline-capable contracts editor. Staff must reconnect to view/change records.
- Admins should not assume browser HTTP caches or endpoint/device-level storage can substitute for endpoint controls. A formal security review is still required before wider release.

## Implementation
- `app/static/manifest.webmanifest`: installed app identity, icons, colours and standalone display.
- `app/static/sw.js`: narrow navigation-only offline behaviour, no data caching.
- `app/static/pwa-install.js`: Edge/Chrome install prompt/button.
- `app/static/icons`: original 192/512 PNG and SVG artwork.
- `app/main.py`: serves worker at root scope and manifest with correct MIME.
- `app/pilot_access.py`: installation metadata accessible before authentication; root and API still protected.

## Release state
This is the desktop PWA feature code and testable source package, not confirmation of live HTTPS deployment. A staff desktop app becomes installable when the system is deployed at a suitable HTTPS address.
