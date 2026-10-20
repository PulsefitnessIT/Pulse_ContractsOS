"""Desktop PWA integration test. Requires a disposable copy of the original V12 pilot ZIP."""
from __future__ import annotations
import json,os,sys,tempfile,zipfile
from pathlib import Path
from fastapi.testclient import TestClient

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
V12=Path(os.getenv('PULSE_PWA_TEST_V12','/mnt/data/Pulse_Fitness_Contracts_Platform_v12_Reporting_and_PPM.zip'))

def test():
    m=json.loads((BASE/'app/static/manifest.webmanifest').read_text())
    assert m['display']=='standalone' and m['scope']=='/' and m['start_url']=='/'
    for icon in m['icons']:
        assert icon['src'].startswith('/static/')
        assert (BASE/'app'/icon['src'].lstrip('/')).is_file()
    sw=(BASE/'app/static/sw.js').read_text()
    assert 'cache.addAll(SAFE_ASSETS)' in sw and "req.mode !== 'navigate'" in sw
    assert '/api/' not in sw and 'localStorage' not in sw and 'indexedDB' not in sw
    assert 'caches.put' not in sw and 'cache.put' not in sw
    assert 'Connection required' in (BASE/'app/static/offline.html').read_text()
    with tempfile.TemporaryDirectory(prefix='pulse-pwa-test-') as tmp:
        with zipfile.ZipFile(V12) as z:
            for name in ('contracts.sqlite3','approved_master.xlsx'):
                (Path(tmp)/name).write_bytes(z.read('Pulse_Contracts_Platform/data/'+name))
        os.environ.update(PULSE_DATA_DIR=tmp,PULSE_PILOT_MODE='1',
            PULSE_AUTO_BACKUP='0',PULSE_SESSION_SECRET='test-signing-secret-pwa-staging-2026-very-long',
            PULSE_COOKIE_SECURE='0')
        from app.main import app
        from app.pilot_access import provision_user
        provision_user('pwatestrunner','pwa-review-password-123','Viewer')
        with TestClient(app,follow_redirects=False) as client:
            resp=client.get('/')
            assert resp.status_code==303 and resp.headers.get('location')=='/pilot/login'
            assert client.get('/api/contracts').status_code==401
            manifest=client.get('/manifest.webmanifest')
            assert manifest.status_code==200 and manifest.headers['content-type'].startswith('application/manifest+json')
            assert manifest.json()['name']=='Pulse Contracts OS'
            worker=client.get('/sw.js')
            assert worker.status_code==200 and worker.headers['content-type'].startswith('application/javascript')
            assert worker.headers['service-worker-allowed']=='/'
            assert worker.headers['cache-control']=='no-cache'
            for path in ('/static/offline.html','/static/icons/contracts-192.png','/static/icons/contracts-512.png','/pilot/login'):
                assert client.get(path).status_code==200
            login=client.post('/api/pilot/login',json={
                'username':'pwatestrunner','password':'pwa-review-password-123'})
            assert login.status_code==200,login.text
            page=client.get('/')
            assert page.status_code==200 and page.headers['cache-control']=='no-store'
            assert 'Install desktop app' in page.text and '/manifest.webmanifest' in page.text
            assert '/static/pwa-install.js' in page.text
            assert client.get('/api/contracts',params={'limit':1}).status_code==200
    print('PWA integration checks passed')

if __name__=='__main__':test()
