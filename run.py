"""Run on 127.0.0.1:8000. For shared pilots use a managed TLS reverse proxy."""
import os, uvicorn
from app.pilot_access import PILOT_MODE,secret,COOKIE_SECURE
if __name__=='__main__':
    host=os.environ.get('PULSE_BIND_HOST','127.0.0.1')
    if host not in ('127.0.0.1','::1','localhost'):
        raise SystemExit('For safety this launcher binds to localhost only. Use an authenticated HTTPS reverse proxy for remote coordinators.')
    if PILOT_MODE:secret()
    uvicorn.run('app.main:app',host=host,port=int(os.environ.get('PULSE_PORT','8000')),reload=False,workers=1)
