"""Translation bridge contract tests with a fake NVIDIA client: no real provider call.

Run: .runtime/nvidia-intake-venv/Scripts/python.exe -B integration/translation/test_translation_bridge.py
"""
import json
import os
from pathlib import Path
import sys
import unittest

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translation_bridge as bridge  # noqa: E402

TOKEN = 'T' * 40
SOURCE = {'text': 'La chaussée présente 2 nids-de-poule près de [NOM].'}
EN = {'en': 'The road has 2 potholes near [NOM].'}


def fake(content, status=200, model=bridge.TEXT_MODEL):
    def handler(request):
        assert request.headers['authorization'] == 'Bearer nvapi-test-only'
        assert '<summary>' in json.loads(request.content)['messages'][1]['content']
        return httpx.Response(status, json={'model': model, 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(content)}}]})
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


class TranslationBridgeTest(unittest.TestCase):
    def setUp(self):
        os.environ.update(NVIDIA_API_KEY='nvapi-test-only', INTAKE_NVIDIA_KEY_SOURCE='project-dpapi', TRANSLATION_ALLOW_NVIDIA_CALLS='1')

    def call(self, content, key=TOKEN, body=SOURCE, **kwargs):
        client = TestClient(bridge.create_app(token=TOKEN, client_factory=fake(content, **kwargs)))
        return client.post('/translate', json=body, headers={'X-Municipal-Translation-Key': key})

    def test_valid_translation(self):
        response = self.call(EN)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()['en'], response.json()['kind']), (EN['en'], 'machine_translation'))

    def test_changed_number_is_refused(self):
        self.assertEqual(self.call({'en': 'The road has 3 potholes near [NOM].'}).json()['detail'], 'TRANSLATION_NUMBERS_CHANGED')

    def test_dropped_placeholder_is_refused(self):
        self.assertEqual(self.call({'en': 'The road has 2 potholes near Ali.'}).json()['detail'], 'TRANSLATION_PLACEHOLDERS_CHANGED')

    def test_schema(self):
        self.assertEqual(self.call(EN | {'fr': 'x'}).status_code, 502)
        self.assertEqual(self.call({'en': ''}).status_code, 502)

    def test_provider_failures(self):
        self.assertEqual(self.call(EN, status=429).json()['detail'], 'NVIDIA_HTTP_429')
        self.assertEqual(self.call(EN, model='other/model').json()['detail'], 'NVIDIA_MODEL_MISMATCH')

    def test_credentials(self):
        self.assertEqual(self.call(EN, key='wrong').status_code, 401)
        os.environ['TRANSLATION_ALLOW_NVIDIA_CALLS'] = '0'
        self.assertEqual(self.call(EN).json()['detail'], 'NVIDIA_CALLS_DISABLED_OR_CREDENTIAL_MISSING')
        unconfigured = TestClient(bridge.create_app(token='', client_factory=fake(EN)))
        self.assertEqual(unconfigured.post('/translate', json=SOURCE).status_code, 503)

    def test_input_contract(self):
        self.assertEqual(self.call(EN, body={'text': ''}).status_code, 422)
        self.assertEqual(self.call(EN, body=SOURCE | {'extra': 1}).status_code, 422)


if __name__ == '__main__':
    unittest.main(verbosity=2)
