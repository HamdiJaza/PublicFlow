"""Loopback citizen portal. n8n alone orchestrates agents and makes policy decisions.

Citizens sign in with their CIN before filing a complaint; the account link stays on
this computer and is never sent to n8n or stored in a ticket.
"""
import asyncio
from contextlib import asynccontextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.middleware.trustedhost import TrustedHostMiddleware

from citizens import CitizenError, Citizens

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WEBHOOK = 'http://127.0.0.1:5679/webhook/municipal-ticket-development'
WORKFLOW = 'http://127.0.0.1:5679/workflow/municipalCompletionDev'
TICKET_LOOKUP = 'http://127.0.0.1:5679/webhook/municipal-ticket-status'
COMMUNES = 'http://127.0.0.1:5679/webhook/municipal-communes'
STAFF = 'http://127.0.0.1:8091'
STAFF_ADMIN = STAFF + '/admin'
STAFF_SESSION_SECONDS = 8 * 3600  # same lifetime as the staff console's own sessions
MAX_BODY = 52 * 1024 * 1024
SESSION_SECONDS = 12 * 3600
LIMITS = {'image': 10 * 1024**2, 'audio': 30 * 1024**2, 'video': 50 * 1024**2}
MIMES = {
    'image': {'image/jpeg', 'image/png', 'image/webp'},
    'audio': {'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/mpeg', 'audio/mp3',
              'audio/mp4', 'audio/x-m4a', 'audio/ogg', 'audio/webm', 'audio/flac', 'audio/x-flac'},
    'video': {'video/mp4', 'video/webm', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'},
}
SERVICES = {
    'n8n': 'http://127.0.0.1:5679/healthz',
    'intake': 'http://127.0.0.1:8012/',
    'vision': 'http://127.0.0.1:8010/openapi.json',
    'media': 'http://127.0.0.1:8013/healthz',
    'knowledge': 'http://127.0.0.1:8020/health',
    'evidence': 'http://127.0.0.1:8021/healthz',
    'ollama': 'http://127.0.0.1:11435/api/version',
    'persistence': TICKET_LOOKUP + '?tracking_id=00000000-0000-0000-0000-000000000000',
}
TRACKING = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')


def now():
    return datetime.now(timezone.utc).isoformat()


class BodyLimit:
    """Bound multipart uploads, including requests without Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        try:
            too_large = int(headers.get(b'content-length', b'0')) > MAX_BODY
        except ValueError:
            too_large = True
        if too_large:
            return await JSONResponse({'detail': 'Uploads are limited to 52 MB in total.'}, 413)(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > MAX_BODY:
                raise HTTPException(413, 'Uploads are limited to 52 MB in total.')
            return message

        await self.app(scope, limited_receive, send)


def configure_intake(key):
    """Secret passes via stdin only, never command arguments, logs or result data."""
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', str(HERE / 'Configure_Intake.ps1')]
    try:
        # Background PowerShell children can inherit capture-pipe handles and
        # keep communicate() waiting after the setup process has exited.
        # This helper's output is deliberately discarded, including errors.
        result = subprocess.run(command, input=key, text=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=55, cwd=ROOT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def create_app(runtime=None, transport=None, configure=None):
    directory = Path(runtime or ROOT / '.runtime/portal')
    jobs = directory / 'jobs'
    token = secrets.token_urlsafe(32)
    tasks = set()
    admission = asyncio.Lock()
    setup_lock = asyncio.Lock()
    configure = configure or configure_intake
    citizens = Citizens(directory)
    citizen_sessions, citizen_failures = {}, {}

    def citizen(request):
        session = citizen_sessions.get(request.cookies.get('citizen_session', ''))
        if not session or session['expires'] < time.time():
            return None
        return citizens.get(session['account'])

    def signed_in(request):
        account = citizen(request)
        if not account:
            raise HTTPException(401, 'Please sign in with your CIN.')
        return account

    def save(record):
        target = jobs / (record['report_id'] + '.json')
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(target)

    def read(report_id):
        if not re.fullmatch(r'RPT-[a-f0-9]{32}', report_id):
            raise HTTPException(404, 'Submission not found.')
        path = jobs / (report_id + '.json')
        if not path.is_file():
            raise HTTPException(404, 'Submission not found.')
        return json.loads(path.read_text(encoding='utf-8'))

    async def lookup(client, tracking_id):
        response = await client.get(TICKET_LOOKUP, params={'tracking_id': tracking_id})
        body = response.json()
        if response.status_code == 404 and body == {'ticket': None, 'error': None}:
            return None
        if (response.status_code != 200 or not isinstance(body.get('ticket'), dict)
                or body['ticket'].get('tracking_id') != tracking_id or body['ticket'].get('persisted') is not True):
            raise ValueError('Unconfirmed ticket lookup')
        return body['ticket']

    @asynccontextmanager
    async def lifespan(service):
        jobs.mkdir(parents=True, exist_ok=True)
        for path in jobs.glob('RPT-*.json'):
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('state') in ('queued', 'running'):
                record.update(state='interrupted', finished_at=now(),
                              error='The portal restarted while this complaint was being processed. Check the n8n execution before sending it again.')
                save(record)
                # Only this portal's generated upload files; never member originals.
                for uploaded in jobs.glob(record['report_id'] + '-*.upload'):
                    uploaded.unlink()
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title='Municipalité Automatisée — citizen portal', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')

    @app.middleware('http')
    async def same_origin(request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if origin and origin not in ('http://127.0.0.1:8090', 'http://localhost:8090', 'http://testserver'):
                return JSONResponse({'detail': 'Origin not allowed.'}, 403)
            if not secrets.compare_digest(request.headers.get('x-portal-token', ''), token):
                return JSONResponse({'detail': 'Please reload the page and try again.'}, 403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.get('/')
    async def page():
        return FileResponse(HERE / 'static/index.html')

    @app.get('/setup')
    async def setup_page():
        # Key setup lives in the authenticated maintenance console.
        return RedirectResponse(STAFF_ADMIN, 303)

    @app.get('/api/session')
    async def session():
        return {'token': token, 'workflow_url': WORKFLOW}

    @app.get('/api/health')
    async def health():
        async with httpx.AsyncClient(timeout=2, trust_env=False, transport=transport) as client:
            async def check(name, url):
                try:
                    response = await client.get(url)
                    ready = response.status_code == 200
                    body = response.json()
                    if name == 'media':
                        ready = ready and body.get('status') == 'ready'
                    elif name == 'evidence':
                        ready = ready and body.get('status') == 'ready' and body.get('index_present') is True
                    elif name == 'knowledge':
                        ready = ready and body.get('index_manifest_present') is True
                    elif name == 'persistence':
                        ready = response.status_code == 404 and body == {'ticket': None, 'error': None}
                    return name, bool(ready)
                except (httpx.HTTPError, ValueError):
                    return name, False
            statuses = dict(await asyncio.gather(*(check(k, v) for k, v in SERVICES.items())))
        return {'services': statuses, 'ready': all(statuses.values()), 'persistence': statuses['persistence'],
                'note': 'Availability only; no inference is triggered.'}

    @app.post('/api/setup/intake')
    async def setup_intake(request: Request):
        if admission.locked() or setup_lock.locked():
            raise HTTPException(409, 'A complaint is being processed. Wait for it to finish before changing the key.')
        async with setup_lock:
            if len(await request.body()) > 4096:
                raise HTTPException(400, 'Invalid key.')
            try:
                data = await request.json()
                key = data.get('key')
            except (ValueError, AttributeError):
                key = None
            if not isinstance(key, str) or not re.fullmatch(r'nvapi-[A-Za-z0-9_-]{20,200}', key):
                raise HTTPException(400, 'Enter only the NVIDIA API key (it starts with nvapi-).')
            ok = await asyncio.to_thread(configure, key)
            key = None
            if not ok:
                raise HTTPException(503, 'Intake did not start. Check the local setup; the key is never displayed.')
            return {'configured': True, 'message': 'Key encrypted for this Windows account. Intake started; no model was called during setup.'}

    async def dispatch(record, data, uploads):
        record.update(state='running', started_at=now())
        save(record)
        try:
            with ExitStack() as stack:
                files = [(kind, (name, stack.enter_context(path.open('rb')), mime))
                         for kind, name, path, mime in uploads]
                # No automatic retry: a disconnected response may already have executed.
                async with httpx.AsyncClient(timeout=httpx.Timeout(7500, connect=5),
                                             trust_env=False, transport=transport) as client:
                    response = await client.post(WEBHOOK, data=data, files=files)
                result = response.json()
                if (response.status_code not in (200, 201, 202, 422, 503) or not isinstance(result, dict)
                        or result.get('report_id') != record['report_id']
                        or result.get('decision') not in ('PASS', 'REVIEW', 'REJECT')
                        or not isinstance(result.get('trace'), list)
                        or not isinstance(result.get('policy'), dict)
                        or not isinstance(result.get('persisted'), bool)):
                    raise ValueError('Unexpected n8n response')
                record.update(state='completed', result=result, webhook_http_status=response.status_code)
        except asyncio.CancelledError:
            record.update(state='interrupted', error='The portal was stopped during processing. Check n8n before sending the complaint again.')
            raise
        except (httpx.HTTPError, ValueError):
            record.update(state='failed', error='The workflow engine did not return a valid result. Check the n8n execution before sending again; nothing is retried automatically.')
        except Exception:
            record.update(state='failed', error='Local processing failed. No ticket was confirmed.')
        finally:
            record['finished_at'] = now()
            save(record)
            for _, _, path, _ in uploads:
                path.unlink(missing_ok=True)
            admission.release()

    @app.post('/api/reports', status_code=202)
    async def submit(request: Request):
        account = signed_in(request)
        # Retrying a browser POST with the same UUID returns its existing job.
        key = request.headers.get('idempotency-key', '')
        try:
            report_id = 'RPT-' + uuid.UUID(key).hex
        except ValueError:
            raise HTTPException(400, 'Invalid submission reference.') from None
        if (jobs / (report_id + '.json')).exists():
            if report_id not in citizens.reports(account['account']):
                raise HTTPException(409, 'Invalid submission reference.')
            return {'report_id': report_id, 'existing': True}
        if admission.locked() or setup_lock.locked():
            raise HTTPException(409, 'Another complaint is already being processed on this computer. Please wait for it to finish.')
        await admission.acquire()
        uploads = []
        started = False
        try:
            async with request.form(max_files=3, max_fields=3, max_part_size=4096) as form:
                pairs = list(form.multi_items())
                if len({k for k, _ in pairs}) != len(pairs) or any(k not in ('description', 'address', 'commune', *LIMITS) for k, _ in pairs):
                    raise HTTPException(422, 'Unknown or duplicate form fields.')
                description, address, commune = form.get('description', ''), form.get('address', ''), form.get('commune', '')
                if not isinstance(description, str) or len(description) > 3000 or not isinstance(address, str) or len(address) > 300:
                    raise HTTPException(422, 'The description or address is too long.')
                # Chosen by the citizen, never inferred; the database checks that it exists.
                if not isinstance(commune, str) or (commune and not re.fullmatch(r'COMMUNE_[A-Z0-9_]{2,31}', commune)):
                    raise HTTPException(422, 'Invalid municipality.')
                selected = {k: v for k, v in pairs if k in LIMITS}
                if (('video' in selected and len(selected) != 1) or
                        ('video' not in selected and 'image' not in selected)):
                    raise HTTPException(422, 'Add a photo with a description or voice note, or a single video.')
                if 'image' in selected and 'audio' not in selected and len(description.strip()) < 5:
                    raise HTTPException(422, 'Add a description of at least 5 characters to the photo.')
                media = []
                for kind, upload in selected.items():
                    if not isinstance(upload, UploadFile) or upload.content_type not in MIMES[kind]:
                        raise HTTPException(422, 'This media format is not supported.')
                    if not upload.size or upload.size > LIMITS[kind]:
                        raise HTTPException(413, 'The file is empty or too large.')
                    path = jobs / (report_id + '-' + kind + '.upload')
                    # Generated basename: do not propagate a local path from the citizen's filename.
                    suffix = Path(upload.filename or '').suffix.lower()
                    filename = kind + (suffix if re.fullmatch(r'\.[a-z0-9]{1,6}', suffix) else '.bin')
                    uploads.append((kind, filename, path, upload.content_type))
                    digest = hashlib.sha256()
                    with path.open('xb') as output:
                        while chunk := await upload.read(1024 * 1024):
                            output.write(chunk)
                            digest.update(chunk)
                    media.append({'kind': kind, 'size': upload.size, 'sha256': digest.hexdigest()})
                data = {'report_id': report_id, 'description': description}
                location = {k: v for k, v in (('address', address.strip()), ('commune', commune)) if v}
                if location:
                    data['location'] = json.dumps(location, ensure_ascii=False)
                record = {'report_id': report_id, 'state': 'queued', 'submitted_at': now(),
                          'media': media, 'workflow_url': WORKFLOW,
                          'storage': 'LOCAL_EXECUTION_RECEIPT_NOT_TICKET_DATABASE'}
                save(record)
                # Account link kept only on this computer (never sent to n8n).
                await asyncio.to_thread(citizens.add_report, account['account'], report_id)
                task = asyncio.create_task(dispatch(record, data, uploads))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
                started = True
                return {'report_id': report_id, 'existing': False}
        finally:
            if not started:
                for _, _, path, _ in uploads:
                    path.unlink(missing_ok=True)
                admission.release()

    @app.get('/api/reports/{report_id}')
    async def report(request: Request, report_id: str):
        # A citizen only reads the receipts of their own submissions.
        if report_id not in citizens.reports(signed_in(request)['account']):
            raise HTTPException(404, 'Submission not found.')
        return read(report_id)

    @app.get('/api/tickets/{tracking_id}')
    async def ticket(request: Request, tracking_id: str):
        signed_in(request)
        if not TRACKING.fullmatch(tracking_id):
            raise HTTPException(404, 'No complaint matches this tracking ID.')
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False, transport=transport) as client:
                found = await lookup(client, tracking_id)
        except (httpx.HTTPError, ValueError, AttributeError):
            raise HTTPException(503, 'The complaint database is unavailable right now.') from None
        if found is None:
            raise HTTPException(404, 'No complaint matches this tracking ID.')
        return {'ticket': found, 'error': None}

    # ---------- Citizen accounts (CIN) ----------
    async def credentials(request):
        if len(await request.body()) > 2048:
            raise HTTPException(413, 'Request too large.')
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, 'Invalid request.') from None
        if not isinstance(data, dict):
            raise HTTPException(400, 'Invalid request.')
        return str(data.get('cin', '')).strip(), data.get('password')

    def open_citizen_session(account):
        session = secrets.token_urlsafe(32)
        citizen_sessions[session] = {'account': account['account'], 'expires': time.time() + SESSION_SECONDS}
        response = JSONResponse({'authenticated': True, 'cin_hint': account['cin_hint']})
        response.set_cookie('citizen_session', session, max_age=SESSION_SECONDS, httponly=True, samesite='strict', path='/')
        return response

    @app.post('/api/citizen/register')
    async def citizen_register(request: Request):
        cin, password = await credentials(request)
        try:
            account = await asyncio.to_thread(citizens.create, cin, password)
        except CitizenError as error:
            raise HTTPException(422, str(error)) from None
        return open_citizen_session(account)

    @app.post('/api/citizen/login')
    async def citizen_login(request: Request):
        cin, password = await credentials(request)
        count, last = citizen_failures.get(cin, (0, 0))
        if count >= 5 and time.time() - last < 60:
            raise HTTPException(429, 'Too many attempts. Try again in one minute.')
        account = await asyncio.to_thread(citizens.verify, cin, password)
        if not account:
            citizen_failures[cin] = (count + 1, time.time())
            raise HTTPException(401, 'Incorrect CIN or password.')
        citizen_failures.pop(cin, None)
        return open_citizen_session(account)

    @app.post('/api/citizen/logout')
    async def citizen_logout(request: Request):
        citizen_sessions.pop(request.cookies.get('citizen_session', ''), None)
        response = JSONResponse({'authenticated': False})
        response.delete_cookie('citizen_session', path='/')
        return response

    @app.get('/api/citizen/me')
    async def citizen_me(request: Request):
        account = citizen(request)
        return {'authenticated': bool(account), 'cin_hint': account['cin_hint'] if account else None}

    @app.get('/api/citizen/reports')
    async def citizen_reports(request: Request):
        account = signed_in(request)
        items = []
        for report_id in reversed(citizens.reports(account['account'])[-50:]):
            try:
                record = read(report_id)
            except HTTPException:
                continue
            ticket = (record.get('result') or {}).get('ticket') or {}
            items.append({'report_id': report_id, 'submitted_at': record.get('submitted_at'), 'state': record.get('state'),
                          'decision': (record.get('result') or {}).get('decision'), 'tracking_id': ticket.get('tracking_id'),
                          'category': ticket.get('category'), 'status': ticket.get('status')})

        # Current status from the database through n8n; the receipt value is only a fallback.
        async with httpx.AsyncClient(timeout=10, trust_env=False, transport=transport) as client:
            async def refresh(item):
                if not item['tracking_id']:
                    return
                try:
                    current = await lookup(client, item['tracking_id'])
                    if current:
                        item.update(status=current.get('status'), updated_at=current.get('updated_at'),
                                    organisation_name=current.get('organisation_name'), category=current.get('category'))
                except (httpx.HTTPError, ValueError, AttributeError):
                    item['status_unconfirmed'] = True
            await asyncio.gather(*(refresh(i) for i in items))
        return {'reports': items}

    # ---------- Staff sign-in on the same screen, forwarded to the staff console ----------
    async def staff_call(method, path, payload=None):
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, transport=transport) as client:
                response = await client.request(method, STAFF + path, json=payload)
            return response, response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'The staff console is unavailable right now.') from None

    async def small_json(request):
        if len(await request.body()) > 4096:
            raise HTTPException(413, 'Request too large.')
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, 'Invalid request.') from None
        if not isinstance(data, dict):
            raise HTTPException(400, 'Invalid request.')
        return data

    def relay_error(response, body, fallback):
        detail = body.get('detail') if isinstance(body, dict) and isinstance(body.get('detail'), str) else fallback
        raise HTTPException(response.status_code if response.status_code in (400, 401, 403, 409, 422, 429) else 503, detail)

    @app.get('/api/staff/status')
    async def staff_status():
        response, body = await staff_call('GET', '/api/me')
        return {'bootstrap': bool(body.get('bootstrap'))}

    @app.post('/api/staff/login')
    async def staff_login(request: Request):
        data = await small_json(request)
        response, body = await staff_call('POST', '/api/login', {'username': data.get('username'), 'password': data.get('password')})
        if response.status_code != 200:
            relay_error(response, body, 'Sign-in failed.')
        session = response.cookies.get('staff_session')
        if not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', session):
            raise HTTPException(503, 'The staff console did not open a session.')
        role = (body.get('account') or {}).get('role')
        result = JSONResponse({'redirect': STAFF + ('/admin' if role == 'ADMIN' else '/console')})
        # Cookies are scoped to the host, not the port: the console on :8091 receives this session.
        result.set_cookie('staff_session', session, max_age=STAFF_SESSION_SECONDS, httponly=True, samesite='strict', path='/')
        return result

    @app.get('/api/staff/organisations')
    async def staff_organisations():
        response, body = await staff_call('GET', '/api/register/organisations')
        if response.status_code != 200 or not isinstance(body.get('organisations'), list):
            raise HTTPException(503, 'The organisation list is unavailable.')
        return {'organisations': [{k: o.get(k) for k in ('code', 'kind', 'name_fr', 'name_en')} for o in body['organisations'] if isinstance(o, dict)]}

    @app.post('/api/staff/register')
    async def staff_register(request: Request):
        data = await small_json(request)
        fields = {k: data.get(k) for k in ('username', 'display_name', 'password', 'role', 'organisation', 'request_note')}
        response, body = await staff_call('POST', '/api/register', fields)
        if response.status_code != 200:
            relay_error(response, body, 'The request could not be sent.')
        return {'pending': True}

    @app.get('/api/communes')
    async def communes():
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False, transport=transport) as client:
                response = await client.get(COMMUNES)
            body = response.json()
            if response.status_code != 200 or not isinstance(body.get('communes'), list):
                raise ValueError('Unconfirmed commune list')
            return {'communes': [{'code': c['code'], 'name_fr': c['name_fr'],
                                  'name_en': c['name_en'] if isinstance(c.get('name_en'), str) else None,
                                  'region': c['region'] if isinstance(c.get('region'), str) and re.fullmatch(r'[A-Z][A-Z_]{1,39}', c['region']) else None}
                                 for c in body['communes']
                                 if isinstance(c, dict) and re.fullmatch(r'COMMUNE_[A-Z0-9_]{2,31}', str(c.get('code')))
                                 and isinstance(c.get('name_fr'), str)]}
        except (httpx.HTTPError, ValueError, AttributeError, KeyError):
            raise HTTPException(503, 'The municipality list is unavailable.') from None

    return app


app = create_app()
