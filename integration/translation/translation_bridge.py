"""Display-only English translation of the Intake summary with Intake's NVIDIA text model.

The Intake agent normalises every complaint into French; the application is in English.
The translation never feeds a gate, the router or a decision: the French summary stays the
reference and is shown beside it. Same DPAPI key handling as Intake (process environment).
Run `python translation_bridge.py` once to prepare the n8n header credential.
"""
from collections import Counter
import json
import os
from pathlib import Path
import re
import secrets
import time

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
TOKEN_FILE = ROOT / '.runtime/translation-bridge/access.token'
CREDENTIAL_ID = 'municipalTranslationDev'
# Same hosted model and endpoint as the Intake agent (intake-agent/local_intake/nvidia.py).
TEXT_MODEL = 'nvidia/nemotron-3.5-lightning-30b-a3b'
TEXT_URL = 'https://integrate.api.nvidia.com/v1/chat/completions'
PROMPT_VERSION = 'translate-summary-en-v1'
PROMPT = (Path(__file__).parent / 'prompts' / f'{PROMPT_VERSION}.txt').read_text(encoding='utf-8')
MARKERS = ('[EMAIL]', '[TELEPHONE]', '[NOM]')


class Summary(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=3000)


class TranslationFailure(RuntimeError):
    pass


def credential():
    key = os.environ.get('NVIDIA_API_KEY', '')
    if (os.environ.get('TRANSLATION_ALLOW_NVIDIA_CALLS') != '1' or os.environ.get('INTAKE_NVIDIA_KEY_SOURCE') != 'project-dpapi'
            or not key or re.search(r'[^\x21-\x7e]|["\']', key)):
        raise TranslationFailure('NVIDIA_CALLS_DISABLED_OR_CREDENTIAL_MISSING')
    return key


def validate(source, output):
    """Structural invariants only; they do not prove the translation is faithful."""
    if not isinstance(output, dict) or set(output) != {'en'} or not isinstance(output['en'], str) \
            or not output['en'].strip() or len(output['en']) > 6000:
        raise TranslationFailure('TRANSLATION_SCHEMA_INVALID')
    if Counter(re.findall(r'\d+', output['en'])) != Counter(re.findall(r'\d+', source.text)):
        raise TranslationFailure('TRANSLATION_NUMBERS_CHANGED')
    if any(output['en'].count(m) != source.text.count(m) for m in MARKERS):
        raise TranslationFailure('TRANSLATION_PLACEHOLDERS_CHANGED')
    return output


def translate(source, client):
    payload = {'model': TEXT_MODEL, 'messages': [{'role': 'system', 'content': PROMPT},
               {'role': 'user', 'content': '<summary>\n' + source.text + '\n</summary>'}],
               'temperature': 0.2, 'top_p': 0.95, 'max_tokens': 2000, 'stream': False,
               'chat_template_kwargs': {'enable_thinking': False}, 'response_format': {'type': 'json_object'}}
    response = client.post(TEXT_URL, json=payload, headers={'Authorization': 'Bearer ' + credential(), 'Accept': 'application/json'})
    if response.status_code != 200:
        raise TranslationFailure('NVIDIA_HTTP_' + str(response.status_code))
    data = response.json()
    if data.get('model') != TEXT_MODEL:
        raise TranslationFailure('NVIDIA_MODEL_MISMATCH')
    choices = data.get('choices')
    if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
        raise TranslationFailure('NVIDIA_TEXT_INCOMPLETE_OR_REFUSED')
    try:
        output = json.loads(choices[0]['message']['content'])
    except (KeyError, TypeError, ValueError):
        raise TranslationFailure('TRANSLATION_SCHEMA_INVALID') from None
    return validate(source, output)


def create_app(token=None, client_factory=None):
    if token is None and TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    factory = client_factory or (lambda: httpx.Client(timeout=httpx.Timeout(60, connect=10), trust_env=False,
                                                      follow_redirects=False, transport=httpx.HTTPTransport(retries=0)))
    service = FastAPI(title='Summary translation bridge', version='2.0', docs_url=None, redoc_url=None, openapi_url=None)

    @service.get('/healthz')
    def health():
        try:
            credential()
            key = True
        except TranslationFailure:
            key = False
        return {'status': 'ready' if token and key else 'unconfigured'}

    @service.post('/translate')
    def run(source: Summary, x_municipal_translation_key: str = Header(default='')):
        if not token:
            raise HTTPException(503, 'TRANSLATION_BRIDGE_UNCONFIGURED')
        if not secrets.compare_digest(x_municipal_translation_key, token):
            raise HTTPException(401, 'TRANSLATION_CREDENTIAL_INVALID')
        started = time.perf_counter()
        try:
            with factory() as client:
                output = translate(source, client)
        except TranslationFailure as error:
            raise HTTPException(502, str(error)) from None
        except httpx.TimeoutException:
            raise HTTPException(504, 'NVIDIA_TIMEOUT') from None
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, 'NVIDIA_TEXT_PROCESSING_FAILED') from None
        return {**output, 'provider': 'nvidia', 'model': TEXT_MODEL, 'prompt_version': PROMPT_VERSION,
                'kind': 'machine_translation', 'elapsed_seconds': round(time.perf_counter() - started, 3)}

    return service


def prepare_credential():
    """Plaintext bridge credential stays in ignored storage; imported into n8n."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        try:
            with TOKEN_FILE.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    if len(token) < 32 or not all(c.isalnum() or c in '_-' for c in token):
        raise RuntimeError('Invalid bridge credential file; not overwritten.')
    payload = [{'id': CREDENTIAL_ID, 'name': 'Municipal translation bridge (development)',
                'type': 'httpHeaderAuth', 'data': {'name': 'X-Municipal-Translation-Key', 'value': token}}]
    (TOKEN_FILE.parent / 'n8n-credential.json').write_text(json.dumps(payload), encoding='utf-8')
    print('Prepared translation bridge credential in ignored local storage; no secret displayed.')


if __name__ == '__main__':
    prepare_credential()
else:
    app = create_app()
