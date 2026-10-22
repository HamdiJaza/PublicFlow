"""Authenticated integration evidence service, separate from the native RAG API."""
import json
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel,ConfigDict,Field

from common import DATA,ROOT,RUNTIME,configure
from evidence import verify_receipt

TOKEN_FILE=ROOT/'.runtime/knowledge-bridge/access.token'
CREDENTIAL_ID='municipalKnowledgeEvidenceDev'


class Reference(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    receipt_id:str=Field(pattern='^[a-f0-9]{32}$')
    receipt_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    native_request:dict
    native_response:dict


def create_app(token=None,verifier=verify_receipt):
    service=FastAPI(title='Development Knowledge evidence bridge',version='1.0')
    @service.get('/healthz')
    def health():return {'status':'ready' if token else 'unconfigured','index_present':(RUNTIME/'data/index_structure.json').is_file()}
    @service.post('/evidence/verify')
    def verify(reference:Reference,x_municipal_knowledge_key:str=Header(default='')):
        if not token:raise HTTPException(503,'Evidence credential is not configured.')
        if not secrets.compare_digest(x_municipal_knowledge_key,token):raise HTTPException(401,'Invalid evidence credential.')
        try:return verifier(reference.receipt_id,reference.receipt_sha256,reference.native_request,reference.native_response)
        except (OSError,ValueError,KeyError,TypeError):raise HTTPException(409,'Native knowledge evidence could not be verified.') from None
    return service


def prepare_credential():
    TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True)
    if not TOKEN_FILE.exists():
        with TOKEN_FILE.open('x',encoding='utf-8') as output:output.write(secrets.token_urlsafe(32))
    token=TOKEN_FILE.read_text(encoding='utf-8').strip()
    if len(token)<32 or any(not(c.isalnum() or c in '_-') for c in token):raise RuntimeError('Invalid existing evidence credential')
    credential=[{'id':CREDENTIAL_ID,'name':'Municipal Knowledge evidence (development)','type':'httpHeaderAuth',
        'data':{'name':'X-Municipal-Knowledge-Key','value':token}}]
    (TOKEN_FILE.parent/'n8n-credential.json').write_text(json.dumps(credential),encoding='utf-8')
    print('Prepared separate evidence credential in ignored storage; no secret displayed.')


if __name__=='__main__':prepare_credential()
else:
    configure();sys.path.insert(0,str(RUNTIME))
    app=create_app(TOKEN_FILE.read_text(encoding='utf-8').strip() if TOKEN_FILE.is_file() else None)
