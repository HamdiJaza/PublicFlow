"""Deterministic checks of native RAG receipts; no model calls or invented citations."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import time
import unicodedata

from common import DATA,RUNTIME,GENERATION_MODEL

RECEIPTS=DATA/'receipts'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC',value).casefold().replace('’',"'").split())


def verify_receipt(receipt_id,expected_sha,request,response,*,runtime=RUNTIME,receipts=RECEIPTS,now=None):
    """Only a recorded, fresh native run with the exact request/response is eligible."""
    if not re.fullmatch('[a-f0-9]{32}',receipt_id) or not re.fullmatch('[a-f0-9]{64}',expected_sha):
        raise ValueError('Invalid receipt reference')
    receipt=json.loads((receipts/(receipt_id+'.json')).read_text(encoding='utf-8'))
    if sha(receipt)!=expected_sha:raise ValueError('Receipt digest mismatch')
    age=(time.time() if now is None else now)-receipt['created_at_epoch']
    if not 0<=age<3600:raise ValueError('Receipt expired')
    record=receipt['native_record']
    # Compare native defaults as well as explicit fields, not a caller-supplied ID.
    from api.schema import KnowledgeRequest,KnowledgeResponse
    if KnowledgeRequest.model_validate(request).model_dump()!=record.get('request'):
        raise ValueError('Native request does not match the recorded run')
    if set(response)!={'procedure','deadline','answer_found','sources'}:
        raise ValueError('Invalid native response fields')
    KnowledgeResponse.model_validate(response)
    if record.get('status')!='completed' or response!=record.get('response'):
        raise ValueError('Native response does not match the recorded run')
    strategy=record['request']['strategy'] or 'structure'
    if strategy not in ['structure','fixed']:raise ValueError('Unknown strategy')
    manifest=json.loads((runtime/f'data/index_{strategy}.json').read_text(encoding='utf-8'))
    catalog=json.loads((runtime/f'data/catalog_{strategy}.json').read_text(encoding='utf-8'))
    if catalog['manifest_sha256']!=sha(manifest):raise ValueError('Catalog/index mismatch')
    for relative,expected in manifest['files'].items():
        path=(runtime/relative).resolve()
        if not path.is_relative_to(runtime.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Corpus changed since indexing')
    if hashlib.sha256((runtime/'rag/ingest.py').read_bytes()).hexdigest()!=manifest['chunker_sha256']:
        raise ValueError('Chunker changed since indexing')
    embedding=manifest['embedding']
    if embedding['provider']!='ollama' or embedding['model'] not in ['bge-m3','bge-m3:latest'] or embedding['dimension']!=1024:
        raise ValueError('Unexpected embedding configuration')
    if record['settings']!={'score_threshold':.4,'top_k':3,'provider':'ollama','model':GENERATION_MODEL}:
        raise ValueError('Unexpected native execution configuration')
    with (runtime/'rag/sources.csv').open(encoding='utf-8-sig',newline='') as stream:
        ledger={r['doc_id']:r for r in csv.DictReader(stream)}
    chunks={r['chunk_id']:r for r in catalog['chunks']}
    selected=record.get('context_sources',[])
    if selected!=[hit for hit in record.get('retrieved',[]) if hit['score']>=.4]:
        raise ValueError('Recorded context differs from native selection policy')
    if len(selected)>3:raise ValueError('Unexpected context count')
    sources=[];texts=[];ids=set()
    for hit in selected:
        chunk=chunks.get(hit['chunk_id']);row=ledger.get(hit['doc_id'])
        if not chunk or not row or row['include_in_index']!='true':raise ValueError('Unaudited context source')
        if hit['chunk_id'] in ids:raise ValueError('Duplicate context source')
        ids.add(hit['chunk_id'])
        if any(hit.get(k)!=chunk.get(k) for k in ['doc_id','text','url','category','include_in_index']):
            raise ValueError('Context is not the indexed chunk')
        if hit['url']!=row['url'] or row['verification_status'] not in ['reviewed_page','reviewed_guide_scope']:
            raise ValueError('Unreviewed source reference')
        if request['category']!='NONE' and hit['category']!=request['category']:
            raise ValueError('Source category mismatch')
        score=hit['score']
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not .4<=score<=1:
            raise ValueError('Context score outside the native retrieval policy')
        sources.append({'chunk_id':hit['chunk_id'],'url':hit['url'],'score':round(score,4)})
        texts.append(hit['text'])
    expected_sources=sources if response['answer_found'] else []
    if response['sources']!=expected_sources:raise ValueError('Returned citations differ from actual context')
    raw=record.get('raw_response',{});generation=record.get('generation_request',{})
    generation_recorded=(generation.get('model')==GENERATION_MODEL and raw.get('model')==GENERATION_MODEL and raw.get('done') is True)
    procedure=response['procedure']
    verbatim=bool(procedure and len(normalized(procedure))>=20 and any(normalized(procedure) in normalized(t) for t in texts))
    return {'receipt_verified':True,'request_response_match':True,'indexed_context_verified':True,
        'sources_match_selected_context':True,'source_count':len(expected_sources),'retrieval_threshold':.4,
        'generation_recorded':generation_recorded,'provider':'ollama','generation_model':GENERATION_MODEL,
        'embedding_model':embedding['model'],'embedding_digest':embedding['digest'],
        'procedure_verbatim_in_context':verbatim,'deadline_policy':'No service deadline is certified by this integration',
        'knowledge_scope':'Commune de Tunis and cited national Tunisian services',
        'semantic_limit':'Verbatim support and category matching do not prove question-specific applicability or source currentness'}
