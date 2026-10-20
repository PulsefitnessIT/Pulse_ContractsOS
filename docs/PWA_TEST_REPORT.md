# Pulse Contracts OS – PWA smoke-test results

Scope: development-source feature, not central HTTPS deployment or managed Windows installation acceptance.

PASS: JavaScript syntax checks (`node --check` worker and install helper).
PASS: Python compilation (`python -m compileall -q app tests/v13_pwa.py`).
PASS: PWA manifest names/scope/icons and required files present.
PASS: Public manifest + service worker while pilot authentication enabled; expected content types and root worker scope.
PASS: Unauthenticated root redirects to `/pilot/login`; unauthenticated contract API returns HTTP 401.
PASS: Signed-in Viewer can load root and permitted contract API.
PASS: Signed-in root sets `Cache-Control: no-store`.
PASS: Service worker caches generic offline help only, never authenticated HTML, API or downloads.

Fixture: disposable copy of the original V12 pilot database and approved Excel workbook, isolated in a temporary directory during test. No modifications to real contract data.

NOT YET TESTED: Browser installation on an actual Windows PC, HTTPS reverse proxy, organisation browser policies, multi-user shared-server pilot, production security assessment.
