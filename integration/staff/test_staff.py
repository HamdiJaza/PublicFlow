"""Staff console contract tests. n8n is replaced by an httpx MockTransport: no real database.

Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B integration/staff/test_staff.py
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import create_app  # noqa: E402

SECRET = 'S' * 48
TICKET = '0f8fad5b-d9cb-469f-a165-70867728950e'


class StaffConsoleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'secret.txt').write_text(SECRET, encoding='ascii')
        self.calls = []
        self.reply = lambda payload: {'ok': True, 'tickets': [], 'counts': {}, 'organisations': []}

        def handler(request):
            if request.url.path == '/api/health':
                return httpx.Response(200, json={'services': {'n8n': True}})
            self.calls.append((dict(request.headers), json.loads(request.content)))
            result = self.reply(self.calls[-1][1])
            return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

        self.app = create_app(runtime=root / 'staff', transport=httpx.MockTransport(handler), secret_path=root / 'secret.txt')
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def bootstrap(self):
        if self.client.get('/api/me').json().get('bootstrap'):
            response = self.client.post('/api/bootstrap', json={'username': 'ingenieur', 'display_name': 'Ingénieur', 'password': 'motdepasse-admin'})
        else:
            response = self.client.post('/api/login', json={'username': 'ingenieur', 'password': 'motdepasse-admin'})
        self.assertEqual(response.status_code, 200, response.text)
        return self.client.get('/api/me').json()['csrf']

    def login_as(self, username, role, organisation):
        csrf = self.bootstrap()
        created = self.client.post('/api/admin/accounts', headers={'X-Staff-CSRF': csrf}, json={
            'username': username, 'display_name': 'Agent ' + username, 'password': 'motdepasse-agent', 'role': role, 'organisation': organisation})
        self.assertEqual(created.status_code, 200, created.text)
        self.client.post('/api/logout', headers={'X-Staff-CSRF': csrf})
        response = self.client.post('/api/login', json={'username': username, 'password': 'motdepasse-agent'})
        self.assertEqual(response.status_code, 200, response.text)
        return self.client.get('/api/me').json()['csrf']

    def test_bootstrap_only_once(self):
        self.assertTrue(self.client.get('/api/me').json()['bootstrap'])
        self.bootstrap()
        self.assertFalse(TestClient(self.app).get('/api/me').json()['bootstrap'])
        again = self.client.post('/api/bootstrap', json={'username': 'autre', 'display_name': 'Autre', 'password': 'motdepasse-autre'})
        self.assertEqual(again.status_code, 409)

    def test_wrong_password_and_lockout(self):
        self.bootstrap()
        for _ in range(5):
            self.assertEqual(self.client.post('/api/login', json={'username': 'ingenieur', 'password': 'faux-mot-de-passe'}).status_code, 401)
        self.assertEqual(self.client.post('/api/login', json={'username': 'ingenieur', 'password': 'motdepasse-admin'}).status_code, 429)

    def test_password_is_hashed_on_disk(self):
        self.bootstrap()
        stored = (Path(self.tmp.name) / 'staff/accounts.json').read_text(encoding='utf-8')
        self.assertNotIn('motdepasse-admin', stored)

    def test_post_requires_csrf(self):
        self.bootstrap()
        response = self.client.post('/api/admin/accounts', json={'username': 'x'})
        self.assertEqual(response.status_code, 401)

    def test_roles_are_separated(self):
        csrf = self.bootstrap()
        self.assertEqual(self.client.get('/api/tickets').status_code, 403)
        self.client.post('/api/logout', headers={'X-Staff-CSRF': csrf})
        self.login_as('agent.steg', 'UTILITY', 'STEG')
        self.assertEqual(self.client.get('/api/admin/accounts').status_code, 403)
        self.assertEqual(self.client.get('/api/admin/overview').status_code, 403)

    def test_n8n_receives_identity_but_never_password(self):
        csrf = self.login_as('agent.tunis', 'MUNICIPALITY', 'COMMUNE_TUNIS')
        self.reply = lambda p: {'ok': True, 'ticket': {'tracking_id': TICKET}}
        response = self.client.post('/api/tickets/' + TICKET + '/actions', headers={'X-Staff-CSRF': csrf},
                                    json={'action': 'approve', 'expected_version': 1, 'note': 'Photo vérifiée',
                                          'organisation': 'STEG', 'category': 'STREET_LIGHTING', 'severity': 'HIGH'})
        self.assertEqual(response.status_code, 200, response.text)
        headers, payload = self.calls[-1]
        self.assertEqual(headers['x-staff-secret'], SECRET)
        self.assertEqual(payload['actor'], {'name': 'Agent agent.tunis (agent.tunis)', 'role': 'MUNICIPALITY', 'organisation': 'COMMUNE_TUNIS'})
        self.assertEqual(payload['action'], 'approve')
        self.assertNotIn('motdepasse', json.dumps(payload))

    def test_database_codes_map_to_http(self):
        csrf = self.login_as('agent.tunis', 'MUNICIPALITY', 'COMMUNE_TUNIS')
        self.reply = lambda p: {'ok': False, 'error': 'VERSION_CONFLICT'}
        response = self.client.post('/api/tickets/' + TICKET + '/actions', headers={'X-Staff-CSRF': csrf},
                                    json={'action': 'start', 'expected_version': 1, 'note': 'Début des travaux'})
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VERSION_CONFLICT'))
        self.reply = lambda p: {'ok': False, 'error': 'TICKET_NOT_FOUND'}
        self.assertEqual(self.client.get('/api/tickets/' + TICKET).status_code, 404)

    def test_unknown_action_rejected_before_n8n(self):
        csrf = self.login_as('agent.tunis', 'MUNICIPALITY', 'COMMUNE_TUNIS')
        before = len(self.calls)
        response = self.client.post('/api/tickets/' + TICKET + '/actions', headers={'X-Staff-CSRF': csrf}, json={'action': 'delete'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.calls), before)

    def test_engine_unavailable_is_503(self):
        self.login_as('agent.sonede', 'UTILITY', 'SONEDE')
        self.reply = lambda p: httpx.Response(503, json={'ok': False, 'error': 'DATABASE_UNAVAILABLE'})
        self.assertEqual(self.client.get('/api/tickets').status_code, 503)

    def test_missing_secret_is_503(self):
        self.login_as('agent.sonede', 'UTILITY', 'SONEDE')
        (Path(self.tmp.name) / 'secret.txt').unlink()
        self.assertEqual(self.client.get('/api/tickets').status_code, 503)

    def test_disabled_account_loses_session(self):
        csrf = self.bootstrap()
        self.client.post('/api/admin/accounts', headers={'X-Staff-CSRF': csrf}, json={
            'username': 'agent.steg', 'display_name': 'Agent', 'password': 'motdepasse-agent', 'role': 'UTILITY', 'organisation': 'STEG'})
        agent = TestClient(self.app)
        self.assertEqual(agent.post('/api/login', json={'username': 'agent.steg', 'password': 'motdepasse-agent'}).status_code, 200)
        self.assertEqual(agent.get('/api/tickets').status_code, 200)
        self.client.patch('/api/admin/accounts/agent.steg', headers={'X-Staff-CSRF': csrf}, json={'active': False})
        self.assertEqual(agent.get('/api/tickets').status_code, 401)

    def test_last_admin_cannot_disable_self(self):
        csrf = self.bootstrap()
        response = self.client.patch('/api/admin/accounts/ingenieur', headers={'X-Staff-CSRF': csrf}, json={'active': False})
        self.assertEqual(response.status_code, 422)

    def test_foreign_origin_refused(self):
        self.bootstrap()
        response = self.client.post('/api/logout', headers={'Origin': 'http://evil.example'})
        self.assertEqual(response.status_code, 403)

    ORGS = [{'code': 'COMMUNE_ARIANA', 'kind': 'MUNICIPALITY', 'name_fr': "Commune de l'Ariana", 'active': True},
            {'code': 'STEG', 'kind': 'UTILITY', 'name_fr': 'STEG', 'active': True},
            {'code': 'COMMUNE_OLD', 'kind': 'MUNICIPALITY', 'name_fr': 'Ancienne', 'active': False}]

    def request_account(self, **overrides):
        self.reply = lambda p: {'ok': True, 'organisations': self.ORGS}
        data = {'username': 'agent.ariana', 'display_name': 'Agent Ariana', 'password': 'motdepasse-agent',
                'role': 'MUNICIPALITY', 'organisation': 'COMMUNE_ARIANA', 'request_note': 'Service voirie, chef d’équipe'} | overrides
        return TestClient(self.app).post('/api/register', json=data)

    def test_registration_waits_for_admin_approval(self):
        csrf = self.bootstrap()
        self.assertEqual(self.request_account().status_code, 200)
        # The system lookup for the form uses the catalogue action, never a person's identity.
        self.assertEqual((self.calls[-1][1]['action'], self.calls[-1][1]['actor']['role']), ('organisations', 'ADMIN'))
        visitor = TestClient(self.app)
        pending = visitor.post('/api/login', json={'username': 'agent.ariana', 'password': 'motdepasse-agent'})
        self.assertEqual(pending.status_code, 403)
        self.assertIn('waiting for the administrator', pending.json()['detail'])
        listed = {a['username']: a for a in self.client.get('/api/admin/accounts').json()['accounts']}
        self.assertTrue(listed['agent.ariana']['pending'])
        self.client.patch('/api/admin/accounts/agent.ariana', headers={'X-Staff-CSRF': csrf}, json={'active': True})
        self.assertEqual(visitor.post('/api/login', json={'username': 'agent.ariana', 'password': 'motdepasse-agent'}).status_code, 200)

    def test_refused_request_is_deleted(self):
        csrf = self.bootstrap()
        self.request_account()
        self.assertEqual(self.client.post('/api/admin/accounts/agent.ariana/refuse', headers={'X-Staff-CSRF': csrf}).status_code, 200)
        self.assertNotIn('agent.ariana', [a['username'] for a in self.client.get('/api/admin/accounts').json()['accounts']])
        self.assertEqual(self.client.post('/api/admin/accounts/ingenieur/refuse', headers={'X-Staff-CSRF': csrf}).status_code, 422)

    def test_registration_rejects_admin_inactive_or_mismatched_organisation(self):
        self.bootstrap()
        self.assertEqual(self.request_account(role='ADMIN').status_code, 422)
        self.assertEqual(self.request_account(organisation='COMMUNE_OLD').status_code, 422)
        self.assertEqual(self.request_account(role='UTILITY').status_code, 422)  # Ariana is not a utility
        self.assertEqual(self.request_account(request_note='').status_code, 422)

    def test_sign_in_pages_point_to_the_shared_screen(self):
        self.assertEqual(self.client.get('/login', follow_redirects=False).status_code, 200)  # first start: bootstrap page
        self.bootstrap()
        visitor = TestClient(self.app)
        self.assertEqual(visitor.get('/login', follow_redirects=False).headers['location'], 'http://127.0.0.1:8090/#staff')
        self.assertEqual(visitor.get('/register', follow_redirects=False).headers['location'], 'http://127.0.0.1:8090/#staff-register')

    def test_pages_redirect_by_role(self):
        self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/login')
        self.bootstrap()
        self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/admin')
        self.assertEqual(self.client.get('/console', follow_redirects=False).status_code, 303)


if __name__ == '__main__':
    unittest.main(verbosity=2)
