"""Loopback staff console: municipality and STEG/SONEDE responsables, plus the maintenance admin.

People are authenticated here. n8n receives only the agent name, role and organisation,
and municipal.staff_api decides what each organisation may see and change.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
import secrets
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from accounts import AccountError, Accounts

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAFF_WEBHOOK = 'http://127.0.0.1:5679/webhook/municipal-staff'
PORTAL = 'http://127.0.0.1:8090'
TRANSLATION = 'http://127.0.0.1:8014'
ORIGINS = ('http://127.0.0.1:8091', 'http://localhost:8091', 'http://testserver')
SESSION_SECONDS = 8 * 3600
TRACKING = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')
STATUSES = {'OPEN', 'NEEDS_REVIEW', 'IN_PROGRESS', 'RESOLVED', 'REJECTED'}
TICKET_ACTIONS = {'approve', 'reassign', 'reject', 'start', 'done', 'not_done', 'reopen'}


def read_secret(path):
    try:
        value = Path(path).read_text(encoding='ascii').strip()
    except OSError:
        return None
    return value if re.fullmatch(r'[A-Za-z0-9_-]{40,100}', value) else None


def create_app(runtime=None, transport=None, secret_path=None):
    directory = Path(runtime or ROOT / '.runtime/staff')
    accounts = Accounts(directory / 'accounts.json')
    secret_path = Path(secret_path or ROOT / '.runtime/persistence/staff-webhook-password.txt')
    sessions = {}
    failures = {}

    @asynccontextmanager
    async def lifespan(service):
        directory.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title='Municipalité Automatisée — staff console', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')

    def current(request):
        session = sessions.get(request.cookies.get('staff_session', ''))
        if not session or session['expires'] < time.time():
            return None
        # A disabled account loses access at its next request.
        account = accounts.get(session['username'])
        if not account or not account['active']:
            sessions.pop(request.cookies.get('staff_session', ''), None)
            return None
        return session | {'account': account}

    @app.middleware('http')
    async def guard(request, call_next):
        if request.method in ('POST', 'PATCH'):
            origin = request.headers.get('origin')
            if origin and origin not in ORIGINS:
                return JSONResponse({'detail': 'Origin not allowed.'}, 403)
            session = current(request)
            if request.url.path not in ('/api/login', '/api/bootstrap', '/api/register') and (
                    not session or not secrets.compare_digest(request.headers.get('x-staff-csrf', ''), session['csrf'])):
                return JSONResponse({'detail': 'Session expired. Please sign in again.'}, 401)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    def need(request, *roles):
        session = current(request)
        if not session:
            raise HTTPException(401, 'Session expired. Please sign in again.')
        if roles and session['account']['role'] not in roles:
            raise HTTPException(403, "Your role does not allow this action.")
        return session['account']

    async def body(request, limit=8192):
        raw = await request.body()
        if len(raw) > limit:
            raise HTTPException(413, 'Request too large.')
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            raise HTTPException(400, 'Invalid request.') from None
        if not isinstance(data, dict):
            raise HTTPException(400, 'Invalid request.')
        return data

    async def staff_api(account, action, **fields):
        secret = read_secret(secret_path)
        if not secret:
            raise HTTPException(503, "The connection to the n8n engine is not configured (secret missing).")
        payload = {'action': action, **{k: v for k, v in fields.items() if v is not None},
                   'actor': {'name': account['display_name'] + ' (' + account['username'] + ')',
                             'role': account['role'], 'organisation': account['organisation']}}
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False, transport=transport) as client:
                response = await client.post(STAFF_WEBHOOK, json=payload, headers={'X-Staff-Secret': secret})
            result = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'The n8n engine or the ticket database is unavailable.') from None
        if response.status_code != 200 or not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
            raise HTTPException(503, 'The n8n engine or the ticket database is unavailable.')
        if not result['ok']:
            code = result.get('error') if isinstance(result.get('error'), str) else 'STAFF_REQUEST_FAILED'
            status = 404 if code == 'TICKET_NOT_FOUND' else 409 if code in ('VERSION_CONFLICT', 'INVALID_STATUS_TRANSITION', 'COMMUNE_EXISTS') else 422
            return JSONResponse({'detail': code, 'code': code}, status)
        return result

    # Pages
    @app.get('/')
    async def home(request: Request):
        session = current(request)
        if not session:
            return RedirectResponse('/login', 303)
        return RedirectResponse('/admin' if session['account']['role'] == 'ADMIN' else '/console', 303)

    @app.get('/login')
    async def login_page():
        # Staff sign in on the portal's shared screen; this page only serves the very first start.
        if accounts.has_admin():
            return RedirectResponse(PORTAL + '/#staff', 303)
        return FileResponse(HERE / 'static/login.html')

    # Former French paths, kept so existing bookmarks still work.
    @app.get('/connexion')
    async def old_login():
        return RedirectResponse('/login', 301)

    @app.get('/inscription')
    async def old_register():
        return RedirectResponse('/register', 301)

    @app.get('/console')
    async def console_page(request: Request):
        session = current(request)
        if not session or session['account']['role'] == 'ADMIN':
            return RedirectResponse('/', 303)
        return FileResponse(HERE / 'static/console.html')

    @app.get('/admin')
    async def admin_page(request: Request):
        session = current(request)
        if not session or session['account']['role'] != 'ADMIN':
            return RedirectResponse('/', 303)
        return FileResponse(HERE / 'static/admin.html')

    # Session
    @app.get('/api/me')
    async def me(request: Request):
        session = current(request)
        if not session:
            return {'authenticated': False, 'bootstrap': not accounts.has_admin()}
        return {'authenticated': True, 'account': session['account'], 'csrf': session['csrf']}

    def open_session(account):
        token = secrets.token_urlsafe(32)
        sessions[token] = {'username': account['username'], 'csrf': secrets.token_urlsafe(32),
                           'expires': time.time() + SESSION_SECONDS}
        response = JSONResponse({'account': account})
        response.set_cookie('staff_session', token, max_age=SESSION_SECONDS, httponly=True, samesite='strict', path='/')
        return response

    @app.post('/api/login')
    async def login(request: Request):
        data = await body(request, 2048)
        username = str(data.get('username', '')).strip().lower()
        blocked = failures.get(username, (0, 0))
        if blocked[0] >= 5 and time.time() - blocked[1] < 60:
            raise HTTPException(429, 'Too many attempts. Try again in one minute.')
        account = await asyncio.to_thread(accounts.verify, username, data.get('password'))
        if not account:
            failures[username] = (blocked[0] + 1, time.time())
            raise HTTPException(401, 'Incorrect username or password.')
        failures.pop(username, None)
        # Only shown after a correct password, so it does not reveal which accounts exist.
        if account['pending']:
            raise HTTPException(403, "Your account request is waiting for the administrator to approve it.")
        if not account['active']:
            raise HTTPException(403, "This account is disabled. Contact the administrator.")
        return open_session(account)

    async def system_organisations():
        # Public registration form: active organisation names only, read with the catalogue action.
        system = {'username': 'registration', 'display_name': 'Registration form', 'role': 'ADMIN', 'organisation': None}
        result = await staff_api(system, 'organisations')
        if isinstance(result, JSONResponse):
            raise HTTPException(503, 'The organisation list is unavailable.')
        return [{k: o.get(k) for k in ('code', 'kind', 'name_fr', 'name_en', 'region')} for o in result['organisations'] if o.get('active')]

    @app.get('/register')
    async def register_page():
        return RedirectResponse(PORTAL + '/#staff-register', 303)

    @app.get('/api/register/organisations')
    async def register_organisations():
        return {'organisations': await system_organisations()}

    @app.post('/api/register')
    async def register(request: Request):
        data = await body(request, 4096)
        role, organisation = data.get('role'), data.get('organisation')
        if role not in ('MUNICIPALITY', 'UTILITY'):
            raise HTTPException(422, 'Choose a municipality or a utility.')
        kind = 'MUNICIPALITY' if role == 'MUNICIPALITY' else 'UTILITY'
        if not any(o['code'] == organisation and o['kind'] == kind for o in await system_organisations()):
            raise HTTPException(422, 'Choose a valid organisation.')
        try:
            account = await asyncio.to_thread(accounts.create, str(data.get('username', '')).strip().lower(), data.get('display_name'),
                                              data.get('password'), role, organisation, data.get('request_note') or '')
        except AccountError as error:
            raise HTTPException(422, str(error)) from None
        return {'pending': True, 'username': account['username'],
                'message': "Request sent. You can sign in as soon as the administrator approves it."}

    @app.post('/api/bootstrap')
    async def bootstrap(request: Request):
        # First run only: the maintenance engineer creates the first administrator.
        if accounts.has_admin():
            raise HTTPException(409, 'An administrator already exists.')
        data = await body(request, 2048)
        try:
            account = await asyncio.to_thread(accounts.create, str(data.get('username', '')).strip().lower(),
                                              data.get('display_name'), data.get('password'), 'ADMIN', None)
        except AccountError as error:
            raise HTTPException(422, str(error)) from None
        return open_session(account)

    @app.post('/api/logout')
    async def logout(request: Request):
        sessions.pop(request.cookies.get('staff_session', ''), None)
        response = JSONResponse({'ok': True})
        response.delete_cookie('staff_session', path='/')
        return response

    # Responsables
    @app.get('/api/organisations')
    async def organisations(request: Request):
        return await staff_api(need(request, 'MUNICIPALITY', 'UTILITY'), 'organisations')

    @app.get('/api/tickets')
    async def tickets(request: Request, status: str | None = None):
        if status is not None and status not in STATUSES:
            raise HTTPException(400, 'Unknown status.')
        return await staff_api(need(request, 'MUNICIPALITY', 'UTILITY'), 'list', status=status)

    @app.get('/api/tickets/{tracking_id}')
    async def ticket(request: Request, tracking_id: str):
        account = need(request, 'MUNICIPALITY', 'UTILITY')
        if not TRACKING.fullmatch(tracking_id):
            raise HTTPException(404, 'TICKET_NOT_FOUND')
        return await staff_api(account, 'detail', tracking_id=tracking_id)

    @app.post('/api/tickets/{tracking_id}/actions')
    async def ticket_action(request: Request, tracking_id: str):
        account = need(request, 'MUNICIPALITY', 'UTILITY')
        data = await body(request)
        if not TRACKING.fullmatch(tracking_id) or data.get('action') not in TICKET_ACTIONS:
            raise HTTPException(400, 'Unknown action.')
        fields = {k: data.get(k) for k in ('expected_version', 'note', 'public_note', 'organisation', 'category', 'severity')}
        return await staff_api(account, data['action'], tracking_id=tracking_id, **fields)

    @app.post('/api/tickets/{tracking_id}/comments')
    async def ticket_comment(request: Request, tracking_id: str):
        account = need(request, 'MUNICIPALITY', 'UTILITY')
        data = await body(request)
        if not TRACKING.fullmatch(tracking_id):
            raise HTTPException(404, 'TICKET_NOT_FOUND')
        return await staff_api(account, 'comment', tracking_id=tracking_id, note=data.get('note'))

    # Maintenance administrator
    @app.get('/api/admin/overview')
    async def overview(request: Request):
        return await staff_api(need(request, 'ADMIN'), 'overview')

    @app.get('/api/admin/organisations')
    async def admin_organisations(request: Request):
        return await staff_api(need(request, 'ADMIN'), 'organisations')

    @app.post('/api/admin/communes')
    async def add_commune(request: Request):
        account = need(request, 'ADMIN')
        data = await body(request)
        return await staff_api(account, 'add_commune', code=data.get('code'), name_fr=data.get('name_fr'),
                               name_en=data.get('name_en'), region=data.get('region'))

    @app.patch('/api/admin/communes/{code}')
    async def set_commune(request: Request, code: str):
        account = need(request, 'ADMIN')
        data = await body(request)
        if not isinstance(data.get('active'), bool):
            raise HTTPException(400, 'Invalid request.')
        return await staff_api(account, 'set_active', code=code, active=data['active'])

    @app.get('/api/admin/accounts')
    async def list_accounts(request: Request):
        need(request, 'ADMIN')
        return {'accounts': accounts.list()}

    @app.post('/api/admin/accounts')
    async def create_account(request: Request):
        need(request, 'ADMIN')
        data = await body(request)
        try:
            return {'account': await asyncio.to_thread(accounts.create, str(data.get('username', '')).strip().lower(),
                    data.get('display_name'), data.get('password'), data.get('role'), data.get('organisation'))}
        except AccountError as error:
            raise HTTPException(422, str(error)) from None

    @app.patch('/api/admin/accounts/{username}')
    async def update_account(request: Request, username: str):
        admin = need(request, 'ADMIN')
        data = await body(request)
        active = data.get('active')
        if active is not None and not isinstance(active, bool):
            raise HTTPException(400, 'Invalid request.')
        if active is False and username == admin['username']:
            raise HTTPException(422, 'You cannot disable your own account.')
        try:
            account = await asyncio.to_thread(accounts.update, username, active, data.get('password'))
        except AccountError as error:
            raise HTTPException(422, str(error)) from None
        if active is False:
            for token in [t for t, s in sessions.items() if s['username'] == username]:
                sessions.pop(token)
        return {'account': account}

    @app.post('/api/admin/accounts/{username}/refuse')
    async def refuse_account(request: Request, username: str):
        need(request, 'ADMIN')
        try:
            await asyncio.to_thread(accounts.refuse, username)
        except AccountError as error:
            raise HTTPException(422, str(error)) from None
        return {'refused': username}

    @app.get('/api/admin/health')
    async def health(request: Request):
        need(request, 'ADMIN')
        async with httpx.AsyncClient(timeout=6, trust_env=False, transport=transport) as client:
            try:
                translation = (await client.get(TRANSLATION + '/healthz')).json().get('status') == 'ready'
            except (httpx.HTTPError, ValueError, AttributeError):
                translation = False
            try:
                response = await client.get(PORTAL + '/api/health')
                result = response.json()
                if response.status_code != 200 or not isinstance(result.get('services'), dict):
                    raise ValueError
            except (httpx.HTTPError, ValueError, AttributeError):
                result = None
        secret = read_secret(secret_path) is not None
        return {'portal': result is not None, 'services': (result or {}).get('services', {}) | {'translation': translation},
                'staff_webhook_secret': secret}

    @app.post('/api/admin/intake-key')
    async def intake_key(request: Request):
        # Reuses the portal endpoint so its "one complaint at a time" lock still applies.
        need(request, 'ADMIN')
        data = await body(request, 4096)
        try:
            async with httpx.AsyncClient(timeout=70, trust_env=False, transport=transport) as client:
                token = (await client.get(PORTAL + '/api/session')).json()['token']
                response = await client.post(PORTAL + '/api/setup/intake', json={'key': data.get('key')},
                                             headers={'X-Portal-Token': token})
            result = response.json()
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, 'The citizen portal is unavailable.') from None
        data = None
        if response.status_code != 200:
            raise HTTPException(response.status_code if response.status_code in (400, 409, 503) else 503,
                                result.get('detail', 'Configuration refused.'))
        return {'configured': True, 'message': 'Key encrypted for this Windows account. Intake restarted; no model was called.'}

    return app


app = create_app()
