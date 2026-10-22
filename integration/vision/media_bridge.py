"""Authenticated local access to verified Intake images; no AI inference."""

import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'intake-agent'))

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from local_intake.media import read_verified_image
from local_intake.runtime import Settings

TOKEN_FILE = ROOT/'.runtime/media-bridge/access.token'
CREDENTIAL_ID = 'municipalVerifiedMediaDev'


class MediaReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def create_app(settings=None, token=None):
    settings = settings or Settings()
    if token is None and TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    service = FastAPI(title='Verified Intake media bridge', version='1.0')

    @service.get('/healthz')
    def health():
        return {'status':'ready' if token else 'unconfigured'}

    @service.post('/media/resolve')
    def resolve(reference: MediaReference, x_municipal_media_key: str = Header(default='')):
        if not token:
            raise HTTPException(503, 'Media bridge credential is not configured.')
        if not secrets.compare_digest(x_municipal_media_key, token):
            raise HTTPException(401, 'Invalid media access credential.')
        try:
            data, evidence = read_verified_image(reference.path, settings)
        except FileNotFoundError:
            raise HTTPException(404, 'Processed media or its receipt is unavailable.') from None
        except (ValueError, OSError, KeyError, TypeError):
            raise HTTPException(409, 'Media verification failed or retention expired.') from None
        digest = hashlib.sha256(data).hexdigest()
        if digest != reference.sha256:
            raise HTTPException(409, 'Media does not match the expected content hash.')
        # Intake writes retained PNGs. Never forward an arbitrary original upload.
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise HTTPException(415, 'Only verified prepared PNG images are supported.')
        return Response(data, media_type='image/png', headers={
            'X-Content-SHA256':digest, 'X-Media-Verification':'receipt-and-hash-checked',
            'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})

    return service


def prepare_credential():
    """Keep plaintext bridge credential in ignored storage; import into dev n8n."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        try:
            with TOKEN_FILE.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    if len(token)<32 or not all(c.isalnum() or c in '_-' for c in token):
        raise RuntimeError('Invalid bridge credential file; not overwritten.')
    payload=[{'id':CREDENTIAL_ID,'name':'Municipal verified media (development)',
              'type':'httpHeaderAuth','data':{'name':'X-Municipal-Media-Key','value':token}}]
    target=TOKEN_FILE.parent/'n8n-credential.json'
    target.write_text(json.dumps(payload),encoding='utf-8')
    print('Prepared bridge credential in ignored local storage; no secret displayed.')


if __name__ == '__main__':
    prepare_credential()
else:
    app = create_app()
