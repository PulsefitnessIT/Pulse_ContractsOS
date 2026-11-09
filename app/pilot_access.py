"""Optional, independent staging-pilot authentication.

NO Microsoft or PulseFitness.ai dependency. Passwords use PBKDF2-HMAC-SHA256;
signed, expiring httpOnly session cookies and CSRF protection for API writes.
Suitable for a small supervised pilot behind a managed TLS reverse proxy,
NOT a replacement for production identity management or security assessment.
"""
from __future__ import annotations
import base64, binascii, contextvars, datetime as dt, hashlib, hmac, json, os, secrets, sqlite3, time
from urllib.parse import urlsplit
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .store import DATA, DB

PILOT_MODE = os.getenv('PULSE_PILOT_MODE', '0') == '1'
SESSION_COOKIE='pulse_contracts_session'
CSRF_COOKIE='pulse_contracts_csrf'
COOKIE_SECURE = os.getenv('PULSE_COOKIE_SECURE','1') == '1'
SESSION_TTL = 8 * 60 * 60
IDLE_TTL = 60 * 60
SESSION_TOUCH_INTERVAL = 60
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
    con.execute('''CREATE TABLE IF NOT EXISTS pilot_sessions(
        id_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
        issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL, revoked_at INTEGER NOT NULL DEFAULT 0
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_pilot_sessions_user ON pilot_sessions(username)')



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
        # Password/role changes must invalidate old login tickets immediately.
        con.execute('UPDATE pilot_sessions SET revoked_at=? WHERE username=? AND revoked_at=0',
                    (int(time.time()),username))
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


def _session_digest(session_id):
    return hashlib.sha256(session_id.encode('utf-8')).hexdigest()


def sign_session(user):
    """Persist each issued session so logout and offboarding revoke server access."""
    now_epoch=int(time.time())
    session_id=secrets.token_urlsafe(32)
    body={'sub':user['username'],'role':user['role'],
          'exp':now_epoch+SESSION_TTL,'csrf':secrets.token_urlsafe(28),
          'sid':session_id}
    value=base64.urlsafe_b64encode(json.dumps(body,separators=(',',':')).encode()).decode().rstrip('=')
    signature=hmac.new(secret(),value.encode(),hashlib.sha256).hexdigest()
    with sqlite3.connect(DB,timeout=20) as con:
        con.execute('INSERT INTO pilot_sessions(id_hash,username,issued_at,expires_at,last_seen_at)'
                    ' VALUES(?,?,?,?,?)',
                    (_session_digest(session_id),user['username'],now_epoch,body['exp'],now_epoch))
        con.execute('DELETE FROM pilot_sessions WHERE expires_at<?',(now_epoch-7*86400,))
    return value+'.'+signature,body


def read_session(cookie):
    if not cookie or len(cookie)>4096:return None
    try:
        data,sig=cookie.rsplit('.',1)
        expected=hmac.new(secret(),data.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected):return None
        body=json.loads(base64.urlsafe_b64decode(data+'='*(-len(data)%4)))
        if not isinstance(body,dict) or body.get('role') not in ROLES:return None
        if not isinstance(body.get('sid'),str) or len(body['sid'])<32:return None
        now_epoch=int(time.time())
        if not isinstance(body.get('exp'),int) or body['exp']<=now_epoch:return None
        with sqlite3.connect(DB,timeout=20) as con:
            user=con.execute('SELECT role,disabled FROM pilot_users WHERE username=?',
                             (body.get('sub'),)).fetchone()
            session=con.execute(
                'SELECT username,expires_at,last_seen_at,revoked_at '
                'FROM pilot_sessions WHERE id_hash=?',(_session_digest(body['sid']),)
            ).fetchone()
            if (not user or user[1] or user[0]!=body['role'] or
                not session or session[0]!=body['sub'] or session[3] or
                session[1]<=now_epoch or session[2]+IDLE_TTL<=now_epoch):
                return None
            if now_epoch-session[2]>=SESSION_TOUCH_INTERVAL:
                con.execute('UPDATE pilot_sessions SET last_seen_at=? '
                            'WHERE id_hash=? AND revoked_at=0',
                            (now_epoch,_session_digest(body['sid'])))
        return body
    except (ValueError,TypeError,KeyError,sqlite3.Error,UnicodeDecodeError,
            binascii.Error,AttributeError,IndexError):
        return None


def revoke_session(cookie):
    """Make a logout final even if the old browser cookie is copied elsewhere."""
    body=read_session(cookie)
    if not body:return False
    with sqlite3.connect(DB,timeout=20) as con:
        con.execute('UPDATE pilot_sessions SET revoked_at=? WHERE id_hash=?',
                    (int(time.time()),_session_digest(body['sid'])))
    return True


def revoke_user_sessions(username):
    """Administrative account revocation primitive; no session IDs exposed."""
    with sqlite3.connect(DB,timeout=20) as con:
        cursor=con.execute('UPDATE pilot_sessions SET revoked_at=? '
                           'WHERE username=? AND revoked_at=0',
                           (int(time.time()),str(username).strip().casefold()))
    return cursor.rowcount


def disable_user(username):
    """Disable a named pilot account and immediately revoke its sessions."""
    name=str(username).strip().casefold()
    with sqlite3.connect(DB,timeout=20) as con:
        user=con.execute('SELECT role,disabled FROM pilot_users WHERE username=?',
                         (name,)).fetchone()
        if user is None:raise ValueError('Unknown pilot account')
        if not user[1] and user[0]=='Admin':
            remaining=con.execute(
                "SELECT COUNT(*) FROM pilot_users WHERE role='Admin' "
                "AND disabled=0 AND username<>?",(name,)
            ).fetchone()[0]
            if remaining<1:raise ValueError('Cannot disable the last active administrator')
        con.execute('UPDATE pilot_users SET disabled=1 WHERE username=?',(name,))
        con.execute('UPDATE pilot_sessions SET revoked_at=? '
                    'WHERE username=? AND revoked_at=0',(int(time.time()),name))
    return name


def _public_origin_is_allowed(headers):
    """Fail closed on cross-origin login and write requests in server staging."""
    profile=os.environ.get('PULSE_DEPLOYMENT_ENV')
    if profile not in ('staging','local'):
        return True
    expected=os.environ.get('PULSE_PUBLIC_ORIGIN','').strip()
    supplied=(headers.get('origin') or '').strip()
    if not supplied:
        # Some clients omit Origin on same-site requests; require Referer then.
        supplied=(headers.get('referer') or '').strip()
    try:
        intended=urlsplit(expected)
        actual=urlsplit(supplied)
        expected_scheme='http' if profile=='local' else 'https'
        actual_port=actual.port or (80 if actual.scheme=='http' else 443)
        expected_port=intended.port or (80 if intended.scheme=='http' else 443)
        return (
            intended.scheme==expected_scheme and actual.scheme==expected_scheme
            and bool(intended.hostname)
            and (profile!='local' or intended.hostname=='127.0.0.1')
            and (actual.hostname,actual_port)==(intended.hostname,expected_port)
            and actual.username is None and actual.password is None
        )
    except ValueError:
        return False


def _sensitive_download_requires_staff(path,method):
    """Prevent read-only viewers bulk-exporting files and source documents."""
    if method not in ('GET','HEAD'):return False
    return (path.startswith('/api/export/') or
            path.startswith('/api/pilot/data-quality/') or
            path.endswith(('.csv','.xlsx','.zip','.pdf')) or
            path.endswith('/download') or
            path.endswith('/source') or
            path.endswith('/signed-agreement'))


def _administrator_only(path,method):
    if method in ('GET','HEAD','OPTIONS'):return False
    return (path.startswith('/api/admin/') or
            path.startswith('/api/pilot/master-sync/') or
            path.startswith('/api/master/reimport/'))



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
    if os.environ.get('PULSE_DEPLOYMENT_ENV')=='local':
        # Deny DNS-rebinding Host headers even on unauthenticated static
        # requests. The bundled app must only be accessed via its loopback
        # origin; its server binds to 127.0.0.1, never a network interface.
        host=request.headers.get('host','').lower().strip()
        intended=urlsplit(os.environ.get('PULSE_PUBLIC_ORIGIN',''))
        if host!=intended.netloc.lower():
            return JSONResponse({'detail':'Local access only'},status_code=403)
    unsafe=request.method not in ('GET','HEAD','OPTIONS')
    if unsafe and not _public_origin_is_allowed(request.headers):
        return JSONResponse({'detail':'Untrusted request origin'},status_code=403)
    if path in ('/pilot/login','/api/pilot/login','/api/health','/manifest.webmanifest','/sw.js') or path.startswith('/static/'):
        return await call_next(request)
    session=read_session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        if path.startswith('/api/'):
            return JSONResponse({'detail':'Sign in to the independent Contracts pilot'},status_code=401)
        return RedirectResponse('/pilot/login',status_code=303)
    if path.startswith('/api/') and session['role']=='Viewer' and _sensitive_download_requires_staff(path,request.method):
        return JSONResponse({'detail':'Document exports require a staff account'},status_code=403)
    if unsafe and path.startswith('/api/'):
        # Viewers can sign out, but cannot change any contract, quote or file.
        if session['role']=='Viewer' and path!='/api/pilot/logout':
            return JSONResponse({'detail':'Read-only account'},status_code=403)
        if _administrator_only(path,request.method) and session['role']!='Admin':
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
        response.headers['Referrer-Policy']='same-origin'
        return response
    finally:
        _actor_role.reset(role_token)
        _actor.reset(token)
