"""Portal contract tests: CIN accounts, municipality field, ownership. n8n is an httpx MockTransport.

Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B integration/portal/test_portal_commune.py
"""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import create_app  # noqa: E402

CIN, PASSWORD = '01234567', 'citizen-password'
TRACKING = '0f8fad5b-d9cb-469f-a165-70867728950e'
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
       b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


class PortalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sent = []
        self.communes = [{'code': 'COMMUNE_TUNIS', 'name_fr': 'Commune de Tunis', 'name_ar': 'بلدية تونس', 'name_en': 'Municipality of Tunis', 'region': 'GRAND_TUNIS'},
                         {'code': 'COMMUNE_BEN_AROUS', 'name_fr': 'Commune de Ben Arous', 'region': 'bad region'},
                         {'code': 'bad code', 'name_fr': 'Injected'}]

        self.staff_calls = []

        def handler(request):
            if request.url.port == 8091:  # the staff console
                self.staff_calls.append((request.url.path, json.loads(request.content) if request.content else None))
                if request.url.path == '/api/login':
                    body = self.staff_calls[-1][1]
                    if body['password'] == 'pending-password':
                        return httpx.Response(403, json={'detail': 'Your account request is waiting for the administrator to approve it.'})
                    return httpx.Response(200, json={'account': {'role': 'MUNICIPALITY'}},
                                          headers={'set-cookie': 'staff_session=' + 'S' * 43 + '; HttpOnly; Path=/; SameSite=strict'})
                if request.url.path == '/api/me':
                    return httpx.Response(200, json={'authenticated': False, 'bootstrap': False})
                if request.url.path == '/api/register/organisations':
                    return httpx.Response(200, json={'organisations': [{'code': 'STEG', 'kind': 'UTILITY', 'name_fr': 'STEG', 'name_en': 'STEG (electricity and gas)', 'secret': 'x'}]})
                if request.url.path == '/api/register':
                    return httpx.Response(200, json={'pending': True})
            if request.url.path.endswith('/municipal-communes'):
                return httpx.Response(200, json={'communes': self.communes})
            if request.url.path.endswith('/municipal-ticket-status'):
                tracking = request.url.params['tracking_id']
                return httpx.Response(200, json={'ticket': {'tracking_id': tracking, 'status': 'IN_PROGRESS', 'category': 'ROAD_DAMAGE',
                                                            'organisation_name': 'Commune de Tunis', 'persisted': True}, 'error': None})
            body = request.content.decode('latin-1')
            self.sent.append(body)
            report_id = body.split('name="report_id"\r\n\r\n', 1)[1].split('\r\n', 1)[0]
            return httpx.Response(200, json={'report_id': report_id, 'decision': 'REVIEW', 'trace': [], 'policy': {}, 'persisted': True,
                                             'ticket': {'tracking_id': TRACKING, 'status': 'NEEDS_REVIEW'}})

        self.app = create_app(runtime=self.tmp.name, transport=httpx.MockTransport(handler))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.token = self.client.get('/api/session').json()['token']

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def account(self, path, cin=CIN, password=PASSWORD, client=None):
        client = client or self.client
        return client.post('/api/citizen/' + path, headers={'X-Portal-Token': self.token}, json={'cin': cin, 'password': password})

    def submit(self, commune='COMMUNE_TUNIS', client=None):
        return (client or self.client).post('/api/reports', headers={'X-Portal-Token': self.token, 'Idempotency-Key': str(uuid.uuid4())},
                                            data={'description': 'Deep pothole', 'address': 'Avenue Habib Bourguiba', 'commune': commune},
                                            files={'image': ('photo.png', PNG, 'image/png')})

    def wait(self, report_id):
        for _ in range(50):
            if self.client.get('/api/reports/' + report_id).json()['state'] == 'completed':
                return
            time.sleep(0.05)

    def test_cin_rules(self):
        for bad in ('1234567', '11234567', '0123456', '012345678', '0123456a', ' 01234567x', ''):
            self.assertEqual(self.account('register', cin=bad).status_code, 422, bad)
        self.assertEqual(self.account('register').status_code, 200)

    def test_cin_is_not_stored_in_clear(self):
        self.assertEqual(self.account('register').json(), {'authenticated': True, 'cin_hint': '67'})
        stored = (Path(self.tmp.name) / 'citizens.json').read_text(encoding='utf-8')
        self.assertNotIn(CIN, stored)
        self.assertNotIn(PASSWORD, stored)

    def test_sign_in_is_required(self):
        self.assertEqual(self.submit().status_code, 401)
        self.assertEqual(self.client.get('/api/tickets/' + TRACKING).status_code, 401)
        self.assertEqual(self.client.get('/api/citizen/reports').status_code, 401)
        self.assertEqual(self.sent, [])

    def test_login_errors(self):
        self.account('register')
        self.client.post('/api/citizen/logout', headers={'X-Portal-Token': self.token})
        self.assertEqual(self.client.get('/api/citizen/me').json(), {'authenticated': False, 'cin_hint': None})
        self.assertEqual(self.account('register').status_code, 422)  # duplicate CIN
        self.assertEqual(self.account('login', password='wrong-password').status_code, 401)
        self.assertEqual(self.account('login', cin='09999999').status_code, 401)
        self.assertEqual(self.account('login').status_code, 200)

    def test_complaint_flow_and_my_complaints(self):
        self.account('register')
        response = self.submit()
        self.assertEqual(response.status_code, 202, response.text)
        report_id = response.json()['report_id']
        self.wait(report_id)
        location = self.sent[-1].split('name="location"\r\n\r\n', 1)[1].split('\r\n', 1)[0]
        self.assertEqual(json.loads(location), {'address': 'Avenue Habib Bourguiba', 'commune': 'COMMUNE_TUNIS'})
        self.assertNotIn(CIN, self.sent[-1])  # the CIN never travels to n8n
        reports = self.client.get('/api/citizen/reports').json()['reports']
        self.assertEqual([(r['report_id'], r['tracking_id'], r['status']) for r in reports], [(report_id, TRACKING, 'IN_PROGRESS')])
        self.assertEqual(self.client.get('/api/tickets/' + TRACKING).json()['ticket']['status'], 'IN_PROGRESS')

    def test_other_citizen_cannot_read_receipt(self):
        self.account('register')
        report_id = self.submit().json()['report_id']
        self.wait(report_id)
        other = TestClient(self.app)
        self.account('register', cin='07654321', client=other)
        self.assertEqual(other.get('/api/reports/' + report_id).status_code, 404)
        self.assertEqual(other.get('/api/citizen/reports').json()['reports'], [])

    def test_invalid_municipality_rejected(self):
        self.account('register')
        self.assertEqual(self.submit('Tunis; DROP').status_code, 422)
        self.assertEqual(self.sent, [])

    def test_municipality_list_is_filtered(self):
        self.assertEqual(self.client.get('/api/communes').json(),
                         {'communes': [{'code': 'COMMUNE_TUNIS', 'name_fr': 'Commune de Tunis', 'name_en': 'Municipality of Tunis', 'region': 'GRAND_TUNIS'},
                                       {'code': 'COMMUNE_BEN_AROUS', 'name_fr': 'Commune de Ben Arous', 'name_en': None, 'region': None}]})
        self.communes = None
        self.assertEqual(self.client.get('/api/communes').status_code, 503)

    def test_account_post_requires_portal_token(self):
        response = self.client.post('/api/citizen/register', json={'cin': CIN, 'password': PASSWORD})
        self.assertEqual(response.status_code, 403)

    def staff(self, path, body):
        return self.client.post('/api/staff/' + path, headers={'X-Portal-Token': self.token}, json=body)

    def test_staff_sign_in_hands_the_session_to_the_console(self):
        response = self.staff('login', {'username': 'tunis', 'password': 'good-password'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'redirect': 'http://127.0.0.1:8091/console'})
        cookie = response.headers['set-cookie']
        self.assertIn('staff_session=' + 'S' * 43, cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('samesite=strict', cookie.lower())

    def test_staff_pending_request_is_explained(self):
        response = self.staff('login', {'username': 'new.agent', 'password': 'pending-password'})
        self.assertEqual(response.status_code, 403)
        self.assertIn('waiting for the administrator', response.json()['detail'])
        self.assertNotIn('set-cookie', response.headers)

    def test_staff_request_is_forwarded_with_known_fields_only(self):
        body = {'username': 'agent.steg', 'display_name': 'Agent', 'password': 'long-enough-pw', 'role': 'UTILITY',
                'organisation': 'STEG', 'request_note': 'Network team', 'active': True}
        self.assertEqual(self.staff('register', body).json(), {'pending': True})
        self.assertNotIn('active', self.staff_calls[-1][1])
        orgs = self.client.get('/api/staff/organisations').json()['organisations']
        self.assertEqual(orgs, [{'code': 'STEG', 'kind': 'UTILITY', 'name_fr': 'STEG', 'name_en': 'STEG (electricity and gas)'}])
        self.assertEqual(self.client.get('/api/staff/status').json(), {'bootstrap': False})

    def test_setup_moved_to_admin_console(self):
        response = self.client.get('/setup', follow_redirects=False)
        self.assertEqual((response.status_code, response.headers['location']), (303, 'http://127.0.0.1:8091/admin'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
