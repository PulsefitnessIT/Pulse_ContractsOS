# PWA development checks

**Source package:** independent V13 source-only PWA feature bundle. No customer database is committed.

Verified using a disposable copy of V12 pilot data, not any live service:
- JavaScript syntax: service worker + install helper passed Node syntax checks.
- Python source: `compileall` passed.
- Manifest contains stable scope, start URL, standalone display and valid 192/512 PNG icon paths.
- `/manifest.webmanifest` and `/sw.js` respond with proper MIME types even before pilot sign-in.
- `/sw.js` has root service-worker scope.
- Unauthenticated root redirects to pilot sign-in; unauthenticated contracts API returns HTTP 401.
- Signed-in Viewer can open root and permitted read-only contracts API.
- Authenticated HTML is `Cache-Control: no-store`.
- Service worker only stores offline-help HTML and static icon, never business documents or API responses.

Still required before rollout:
- Import and verify the full application source in GitHub.
- Deploy full application with independent shared data behind IT-managed HTTPS reverse proxy.
- Windows Edge/Chrome install and update testing, browser policy check, multi-user pilot and security review.
