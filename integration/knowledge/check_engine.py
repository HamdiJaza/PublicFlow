"""Real n8n Knowledge nodes with labelled upstream/answer doubles and real 503/422 checks."""
import asyncio
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import socket
import re
import subprocess
import sys
import threading
import time

import httpx
from fastapi import FastAPI,Request,Response
import uvicorn

from common import ROOT,GENERATION_MODEL

TARGET=ROOT/'project-docs/integration/knowledge-engine-results.json'
WORK=ROOT/'.runtime/knowledge-engine-check'
TEST_ID='municipalKnowledgeEngineCheck'
ROUTE='municipal-knowledge-engine-check'


def command(*args):
    result=subprocess.run(['docker','compose','-f',str(ROOT/'n8n/intake-integration/compose.dev.yaml'),*args],
        cwd=ROOT,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError('DEVELOPMENT_CLI_FAILED: '+args[-1])


def wait_ready(http):
    for _ in range(100):
        try:
            response=http.get('http://127.0.0.1:5679/webhook/'+ROUTE,timeout=2)
            if 'Did you mean to make a POST request?' in response.json().get('message',''):return
        except (httpx.HTTPError,ValueError):pass
        time.sleep(.5)
    raise RuntimeError('TEST_WEBHOOK_NOT_REGISTERED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',help='Save a separate run without overwriting archived evidence.')
    parser.add_argument('--skip-missing-index-case',action='store_true',help='Run the remaining model-free cases after real indexing.')
    args=parser.parse_args()
    if args.label and not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',args.label):parser.error('Use a short filename-safe label.')
    target=TARGET.with_name('knowledge-engine-'+args.label+'.json') if args.label else TARGET
    if target.exists():raise SystemExit('Existing engine evidence preserved; no repeat run made.')
    with httpx.Client(trust_env=False,timeout=5) as http:
        if http.get('http://127.0.0.1:8020/health').json()['index_manifest_present'] and not args.skip_missing_index_case:
            raise SystemExit('A real index now exists: skip this no-inference unavailable-resource protocol.')
    WORK.mkdir(parents=True,exist_ok=True)
    workflow=json.loads((ROOT/'n8n/knowledge-integration/municipal-knowledge-development.json').read_text(encoding='utf-8'))
    workflow.update(id=TEST_ID,name='SYNTHETIC UPSTREAM - Knowledge engine checks - NO AI')
    nodes={n['name']:n for n in workflow['nodes']}
    nodes['Citizen Webhook']['parameters']['path']=ROUTE;nodes['Citizen Webhook']['webhookId']=ROUTE
    seed={'id':'synthetic-upstream','name':'SYNTHETIC Upstream','type':'n8n-nodes-base.code','typeVersion':2,'position':[0,-350],
        'parameters':{'mode':'runOnceForAllItems','jsCode':"""const body=$input.first().json.body;
return [{json:{report_id:body.report_id,engine_case:body.case,original:{description:'SYNTHETIC original',location:null},
intake_native:{cleaned_text:'SYNTHETIC question'},vision:{category:'WASTE',severity:'LOW'},department:'SANITATION_DEPARTMENT',
policy:{gate_1:{decision:'PASS'},gate_2:{decision:body.case==='upstream_review'?'REVIEW':'PASS'}},
components:{intake:{execution:'SYNTHETIC_TEST'},vision:{execution:'SYNTHETIC_TEST'},knowledge:{execution:'not_called'},persistence:{execution:'not_called'}},
integration:{local_source_sha256:'SYNTHETIC-ONLY'},review_reasons:[],errors:[],trace:[{stage:'SYNTHETIC_UPSTREAM',decision:'TEST_FIXTURE'}]}}];"""}}
    workflow['nodes'].append(seed)
    def link(source,target):workflow['connections'][source]={'main':[[{'node':target,'type':'main','index':0}]]}
    link('Citizen Webhook','SYNTHETIC Upstream');link('SYNTHETIC Upstream','Prepare Knowledge Request')
    nodes['HTTP Knowledge']['parameters']['url']="={{ ['native_unavailable','native_contract_error'].includes($json.engine_case) ? 'http://host.docker.internal:8020/knowledge' : 'http://host.docker.internal:8095/knowledge' }}"
    nodes['HTTP Knowledge']['parameters']['jsonBody']="={{ $json.engine_case === 'native_contract_error' ? {...$json.knowledge_request,report_id:'UNSUPPORTED'} : $json.knowledge_request }}"
    nodes['HTTP Knowledge']['parameters']['options']['timeout']=500
    evidence=nodes['Read Knowledge Evidence'];evidence.pop('credentials',None)
    evidence['parameters'].pop('authentication',None);evidence['parameters'].pop('genericAuthType',None)
    evidence['parameters']['url']='http://host.docker.internal:8095/evidence/verify'
    native_scope='validation 422' if args.skip_missing_index_case else 'actual missing-index 503 and validation 422'
    workflow['meta']['test_scope']='Explicit synthetic upstream and positive/refusal/evidence fixtures; native API used only for '+native_scope+'. No real AI inference.'
    (WORK/'workflow.json').write_text(json.dumps(workflow),encoding='utf-8')
    state={'case':'','calls':[]}
    service=FastAPI(title='SYNTHETIC RAG/evidence doubles, never real model results')
    @service.post('/knowledge')
    async def knowledge(request:Request):
        native=await request.json();state['calls'].append({'stage':'SYNTHETIC_KNOWLEDGE','fields':sorted(native)})
        assert set(native)=={'category','department','description','strategy','prompt_version'}
        case=state['case']
        if case=='timeout':await asyncio.sleep(1.5)
        body={'procedure':'SYNTHETIC ONLY: this sentence is an offline test response.','deadline':None,'answer_found':True,
            'sources':[{'chunk_id':'DOC-WASTE-02#01','url':'https://example.invalid/source','score':.7}]}
        if case=='refusal':body.update(procedure=None,answer_found=False,sources=[])
        if case=='invalid_schema':body['is_mock']=True
        headers={} if case=='missing_receipt' else {'X-Knowledge-Receipt':'b'*32,'X-Knowledge-Receipt-SHA256':'a'*64}
        return Response(json.dumps(body),media_type='application/json',headers=headers)
    @service.post('/evidence/verify')
    async def evidence_check(request:Request):
        state['calls'].append({'stage':'SYNTHETIC_EVIDENCE'})
        if state['case']=='bad_evidence':return Response(status_code=409)
        return {'receipt_verified':True,'request_response_match':True,'indexed_context_verified':True,'sources_match_selected_context':True,
            'source_count':0 if state['case']=='refusal' else 1,'provider':'ollama','generation_model':GENERATION_MODEL,'generation_recorded':True,
            'embedding_model':'bge-m3:latest','embedding_digest':'a'*64,'procedure_verbatim_in_context':state['case']!='paraphrase'}
    listener=socket.socket();listener.bind(('0.0.0.0',8095));listener.listen(128)
    server=uvicorn.Server(uvicorn.Config(service,log_level='critical',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),'scope':workflow['meta']['test_scope'],
        'real_embedding_calls':0,'real_generation_calls':0,'cases':[],'errors':[]}
    imported=False;started=time.perf_counter()
    try:
        thread.start();command('stop','n8n')
        command('run','--rm','--no-deps','-v',str(WORK)+':/checks:ro','n8n','import:workflow','--input=/checks/workflow.json');imported=True
        command('run','--rm','--no-deps','n8n','publish:workflow','--id='+TEST_ID);command('up','-d','n8n')
        with httpx.Client(trust_env=False,timeout=60) as http:
            wait_ready(http)
            cases=[('supported','PASS'),('refusal','REVIEW'),('paraphrase','REVIEW'),('invalid_schema','REVIEW'),('missing_receipt','REVIEW'),
                ('bad_evidence','REVIEW'),('timeout','REVIEW'),('native_unavailable','REVIEW'),('native_contract_error','REVIEW'),('upstream_review','REVIEW')]
            if args.skip_missing_index_case:cases=[case for case in cases if case[0]!='native_unavailable']
            for case,decision in cases:
                state.update(case=case,calls=[])
                response=http.post('http://127.0.0.1:5679/webhook/'+ROUTE,json={'case':case,'report_id':'RPT-RAG-ENGINE-'+case.replace('_','-')})
                result=response.json();report['cases'].append({'case':case,'http_status':response.status_code,'citizen_response':result,'synthetic_http_calls':list(state['calls'])})
                assert response.status_code==202,(case,response.status_code)
                assert result['policy']['gate_3']['decision']==decision,(case,result['policy'].get('gate_3'))
                if case=='native_unavailable':assert 'KNOWLEDGE_NOT_READY_OR_BUSY' in result['policy']['gate_3']['reason_codes']
                if case=='native_contract_error':assert 'KNOWLEDGE_CONTRACT_REJECTED' in result['policy']['gate_3']['reason_codes']
                if case=='timeout':assert 'KNOWLEDGE_TIMEOUT' in result['policy']['gate_3']['reason_codes']
                if case=='upstream_review':assert not state['calls']
                assert result['persisted'] is False and result['review_queued'] is False
                print('PASS development n8n / labelled Knowledge case: '+case,flush=True)
    except Exception as error:
        report['errors'].append(str(error) if isinstance(error,(AssertionError,RuntimeError)) else type(error).__name__)
    finally:
        try:
            try:
                if imported:
                    command('stop','n8n');command('run','--rm','--no-deps','n8n','unpublish:workflow','--id='+TEST_ID)
            finally:command('up','-d','n8n')
        except Exception:report['errors'].append('TEMPORARY_WORKFLOW_CLEANUP_FAILED')
        server.should_exit=True
        if thread.is_alive():thread.join(5)
        listener.close();report['duration_seconds']=round(time.perf_counter()-started,3)
        with target.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    print(json.dumps({'report':target.relative_to(ROOT).as_posix(),'cases':len(report['cases']),'errors':report['errors']}))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
