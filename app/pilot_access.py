"""Optional, independent staging-pilot authentication.

NO Microsoft or PulseFitness.ai dependency. Passwords use PBKDF2-HMAC-SHA256;
signed, expiring httpOnly session cookies and CSRF protection for API writes.
Suitable for a small supervised pilot behind a managed TLS reverse proxy,
NOT a replacement for production identity management or security assessment.
"""
from __future__ import annotations
import base64, contextvars, datetime as dt, hashlib, hmac, json, os, secrets, sqlite3, time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .store import DATA, DB

PILOT_MODE = os.getenv('PULSE_PILOT_MODE', '0') == '1'
SESSION_COOKIE='pulse_contracts_session'
CSRF_COOKIE='pulse_contracts_csrf'
COOKIE_SECURE = os.getenv('PULSE_COOKIE_SECURE','1') == '1'
SESSION_TTL = 8 * 60 * 60
ROLES={'Admin','Coordinator','Viewer'}
_actor=contextvars.ContextVar('pulse_actor',default=None)
_actor_role=contextvars.ContextVar('pulse_actor_role',default=None)
_fails={}


def actor(fallback='Coordinator'):
    return _actor.get() or fallback


def current_role():
    """Effective role from the verified session, not the username."""
    return _actor_role.get() if PILOT_MODE else 'Coordinator'


def configure_users():
    os.makedirs(DATA,exist_ok=True)
    with sqlite3.connect(DB,timeout=20) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS pilot_users(
            username TEXT PRIMARY KEY, password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)''')


def password_hash(password: str, salt_hex: str):
    return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt_hex),350_000).hex()


def provision_user(username,password,role='Coordinator'):
    if role not in ROLES: raise ValueError('Unknown role')
    username=username.strip().casefold()
    if not (3<=len(username)<=64) or not all(x.isalnum() or x in '._-' for x in username):
        raise ValueError('Use a 3–64 character username with letters, numbers, dots, underscores or hyphens')
    if len(password)<12 or len(password)>256:raise ValueError('Password length must be 12–256 characters')
    configure_users()
    salt=secrets.token_hex(16)
    with sqlite3.connect(DB,timeout=20) as con:
        con.execute('''INSERT INTO pilot_users(username,password_salt,password_hash,role,created_at)
            VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET
            password_salt=excluded.password_salt,password_hash=excluded.password_hash,
            role=excluded.role,disabled=0''', (username,salt,password_hash(password,salt),role,dt.datetime.now(dt.timezone.utc).isoformat()))
    return username


def check_password(username,password):
    with sqlite3.connect(DB,timeout=20) as con:
        row=con.execute('SELECT password_salt,password_hash,role,disabled FROM pilot_users WHERE username=?',(username,)).fetchone()
    # Constant-time comparison even when user doesn't exist.
    if row:
        supplied=password_hash(password,row[0]);expected=row[1]
    else:
        supplied=password_hash(password,'00'*16);expected='00'*32
    if not hmac.compare_digest(supplied,expected) or not row or row[3]: return None
    return {'username':username,'role':row[2]}


def secret():
    s=os.environ.get('PULSE_SESSION_SECRET','')
    if len(s)<32:raise RuntimeError('PULSE_SESSION_SECRET must be at least 32 characters when pilot mode is enabled')
    return s.encode('utf-8')


def sign_session(user):
    body={'sub':user['username'],'role':user['role'],'exp':int(time.time())+SESSION_TTL,'csrf':secrets.token_urlsafe(28)}
    text=base64.urlsafe_b64encode(json.dumps(body,separators=(',',':')).encode()).decode().rstrip('=')
    signature=hmac.new(secret(),text.encode(),hashlib.sha256).hexdigest()
    return text+'.'+signature,body


def read_session(cookie):
    if not cookie:return None
    try:
        data,sig=cookie.rsplit('.',1)
        expected=hmac.new(secret(),data.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected):return None
        body=json.loads(base64.urlsafe_b64decode(data+'='*(-len(data)%4)))
        if body.get('exp',0)<=time.time() or body.get('role') not in ROLES:return None
        with sqlite3.connect(DB,timeout=20) as con:
            result=con.execute('SELECT role,disabled FROM pilot_users WHERE username=?',(body.get('sub'),)).fetchone()
        if not result or result[1] or result[0]!=body['role']:return None
        return body
    except (ValueError,TypeError,KeyError,sqlite3.Error,UnicodeDecodeError):return None


def limited(request,username):
    key=(request.client.host if request.client else 'unknown',username)
    current=time.monotonic();recent=[t for t in _fails.get(key,[]) if current-t<300]
    _fails[key]=recent
    return len(recent)>=6


def failed(request,username):
    key=(request.client.host if request.client else 'unknown',username)
    _fails.setdefault(key,[]).append(time.monotonic())


def login(username,password,request):
    username=username.strip().casefold()
    if limited(request,username):raise HTTPException(429,'Too many unsuccessful attempts. Try again in five minutes.')
    result=check_password(username,password)
    if not result:
        failed(request,username)
        raise HTTPException(401,'Incorrect username or password')
    _fails.pop((request.client.host if request.client else 'unknown',username),None)
    return result


async def pilot_middleware(request:Request,call_next):
    if not PILOT_MODE:return await call_next(request)
    path=request.url.path
    if path in ('/pilot/login','/api/pilot/login','/api/health','/manifest.webmanifest','/sw.js') or path.startswith('/static/'):
        return await call_next(request)
    session=read_session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        if path.startswith('/api/'):
            return JSONResponse({'detail':'Sign in to the independent Contracts pilot'},status_code=401)
        return RedirectResponse('/pilot/login',status_code=303)
    if request.method not in ('GET','HEAD','OPTIONS') and path.startswith('/api/'):
        if session['role']=='Viewer':return JSONResponse({'detail':'Read-only account'},status_code=403)
        if path.startswith('/api/admin/') and session['role']!='Admin':
            return JSONResponse({'detail':'Administrator access required'},status_code=403)
        csrf=request.headers.get('X-Pulse-CSRF','')
        if not csrf or not hmac.compare_digest(csrf,session.get('csrf','')):
            return JSONResponse({'detail':'Session verification missing. Refresh and try again.'},status_code=403)
    token=_actor.set(session['sub'])
    role_token=_actor_role.set(session['role'])
    try:
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        return response
    finally:
        _actor_role.reset(role_token)
        _actor.reset(token)
