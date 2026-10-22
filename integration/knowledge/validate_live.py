"""Bounded real local RAG validation; no Intake/Vision or cloud calls."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import re
import time
import uuid

import httpx
from common import ROOT,RUNTIME,DATA,GENERATION_MODEL,OLLAMA_URL
from check_engine import command

TARGET=ROOT/'project-docs/integration/knowledge-live-qwen-3b-results.json'
WORK=ROOT/'.runtime/knowledge-live-check'
TEST_ID='municipalKnowledgeLiveCheck'
ROUTE='municipal-knowledge-live-check'


def wait_ready(http):
    for _ in range(100):
        try:
            response=http.get('http://127.0.0.1:5679/webhook/'+ROUTE,timeout=2)
            if 'Did you mean to make a POST request?' in response.json().get('message',''):return
        except (httpx.HTTPError,ValueError):pass
        time.sleep(.5)
    raise RuntimeError('TEST_WEBHOOK_NOT_REGISTERED')


def receipt_from_response(response):
    receipt_id=response.headers.get('x-knowledge-receipt','')
    if len(receipt_id)!=32 or any(c not in '0123456789abcdef' for c in receipt_id):raise RuntimeError('REAL_RECEIPT_MISSING')
    return json.loads((DATA/'receipts'/(receipt_id+'.json')).read_text(encoding='utf-8'))['native_record']


def evidence(http,request,response):
    token=(ROOT/'.runtime/knowledge-bridge/access.token').read_text(encoding='utf-8').strip()
    result=http.post('http://127.0.0.1:8021/evidence/verify',headers={'X-Municipal-Knowledge-Key':token},json={
        'receipt_id':response.headers['x-knowledge-receipt'],'receipt_sha256':response.headers['x-knowledge-receipt-sha256'],
        'native_request':request,'native_response':response.json()})
    if result.status_code!=200:raise RuntimeError('ACTUAL_INDEXED_CONTEXT_VERIFICATION_FAILED')
    return result.json()


def usage(record):
    raw=record.get('raw_response',{})
    return {k:raw[k] for k in ['model','done','done_reason','prompt_eval_count','eval_count','total_duration','load_duration','prompt_eval_duration','eval_duration'] if k in raw}


def execution(record):
    """A native no-context refusal completes retrieval without calling generation."""
    raw=record.get('raw_response',{});payload=record.get('generation_request',{})
    if not record.get('context_sources'):
        refusal={'procedure':None,'deadline':None,'answer_found':False,'sources':[]}
        if raw or payload or record.get('response')!=refusal:
            raise RuntimeError('INVALID_NO_CONTEXT_EXECUTION')
        return {'retrieval':'completed_no_context','generation_recorded':False}
    if payload.get('model')!=GENERATION_MODEL or raw.get('model')!=GENERATION_MODEL or raw.get('done') is not True:
        raise RuntimeError('REAL_GENERATION_NOT_RECORDED')
    return {'retrieval':'completed_with_context','generation_recorded':True}


def cleanup_development(imported):
    """Restart dev n8n even if import/publication/temporary-workflow cleanup failed."""
    try:
        if imported:
            command('stop','n8n')
            command('run','--rm','--no-deps','n8n','unpublish:workflow','--id='+TEST_ID)
    finally:
        command('up','-d','n8n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',help='Preserve a separate explicitly requested validation run.')
    parser.add_argument('--n8n-only-water',action='store_true',help='One real n8n request for the supported water diagnosis question; skip native repeats.')
    args=parser.parse_args()
    if args.label and not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',args.label):parser.error('Use a short filename-safe label.')
    if args.n8n_only_water and not args.label:parser.error('The additional water check needs its own report label.')
    target=TARGET.with_name('knowledge-live-'+args.label+'.json') if args.label else TARGET
    if target.exists():raise SystemExit('Existing real RAG result preserved; no repeat inference made.')
    if not (RUNTIME/'data/catalog_structure.json').is_file():raise SystemExit('Real index/catalog not ready; no inference made.')
    # Read-only Docker access check before spending any local model calls.
    # A blocked preflight does not create an incomplete live-inference report.
    command('ps','--format','json')
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),'generation_model':GENERATION_MODEL,'embedding_model':'bge-m3',
        'scope':'Real native RAG requests plus real n8n -> RAG -> evidence/Gate 3; n8n upstream is explicitly a fixture, not actual Intake/Vision',
        'maximum_generation_calls':1 if args.n8n_only_water else 4,'generation_calls':0,'cloud_calls':0,'native_cases':[],'n8n_case':None,'errors':[]}
    started=time.perf_counter();imported=False;development_touched=False
    try:
        with httpx.Client(trust_env=False,timeout=450) as http:
            health=http.get('http://127.0.0.1:8020/health').json()
            if not health['index_manifest_present'] or health['generation_model']!=GENERATION_MODEL or health['generation_provider']!='ollama':
                raise RuntimeError('REAL_RAG_CONFIG_NOT_READY')
            tags=http.get(OLLAMA_URL+'/api/tags').json()['models']
            report['model_artifacts']=[{k:m[k] for k in ['name','digest','size','details']} for m in tags if m['name'] in [GENERATION_MODEL,'bge-m3:latest']]
            native_cases=[] if args.n8n_only_water else [
                ('water_diagnosis','WATER_LEAK',"Comment vérifier une fuite avec les relevés du compteur d'eau ?"),
                ('electrical_contact','STREET_LIGHTING',"Quel numéro appeler pour signaler un câble électrique tombé au sol ?"),
                ('unsupported_repair_deadline','ROAD_DAMAGE',"Quel délai garanti de réparation est prévu pour un nid-de-poule ?")]
            for name,category,question in native_cases:
                request={'category':category,'description':question,'strategy':'structure','prompt_version':'v4_grounded'}
                before=time.perf_counter();response=http.post('http://127.0.0.1:8020/knowledge',json=request)
                row={'case':name,'request':request,'http_status':response.status_code,'elapsed_seconds':round(time.perf_counter()-before,3)}
                report['native_cases'].append(row)
                if response.status_code!=200:raise RuntimeError(name.upper()+'_NATIVE_HTTP_FAILED')
                row['native_response']=response.json();record=receipt_from_response(response)
                row['evidence']=evidence(http,request,response);row['usage']=usage(record)
                row['execution']=execution(record)
                report['generation_calls']+=int(row['execution']['generation_recorded'])
                print('PASS real local RAG processing: '+name,flush=True)

            # The integration check seeds only the upstream state. The original
            # three-agent workflow still enforces Gate 1 and Gate 2 normally.
            workflow=json.loads((ROOT/'n8n/knowledge-integration/municipal-knowledge-development.json').read_text(encoding='utf-8'))
            workflow.update(id=TEST_ID,name='REAL RAG - labelled upstream fixture - DEVELOPMENT CHECK')
            nodes={n['name']:n for n in workflow['nodes']}
            nodes['Citizen Webhook']['parameters']['path']=ROUTE;nodes['Citizen Webhook']['webhookId']=ROUTE
            seed={'id':'labelled-upstream','name':'Labelled Upstream Fixture','type':'n8n-nodes-base.code','typeVersion':2,'position':[0,-350],
                'parameters':{'mode':'runOnceForAllItems','jsCode':"""const b=$input.first().json.body;
return [{json:{report_id:b.report_id,original:{description:b.description,location:null},intake_native:{cleaned_text:b.description},
vision:{category:b.category,severity:'LOW'},department:b.department,policy:{gate_1:{decision:'PASS'},gate_2:{decision:'PASS'}},
components:{intake:{execution:'UPSTREAM_FIXTURE_NOT_CALLED'},vision:{execution:'UPSTREAM_FIXTURE_NOT_CALLED'},knowledge:{execution:'not_called'},persistence:{execution:'not_called'}},
integration:{local_source_sha256:'UPSTREAM_FIXTURE'},review_reasons:[],errors:[],trace:[{stage:'LABELLED_UPSTREAM_FIXTURE',decision:'TEST_ONLY'}]}}];"""}}
            workflow['nodes'].append(seed)
            workflow['connections']['Citizen Webhook']={'main':[[{'node':'Labelled Upstream Fixture','type':'main','index':0}]]}
            workflow['connections']['Labelled Upstream Fixture']={'main':[[{'node':'Prepare Knowledge Request','type':'main','index':0}]]}
            workflow['meta']['test_scope']=report['scope']
            WORK.mkdir(parents=True,exist_ok=True);(WORK/'workflow.json').write_text(json.dumps(workflow),encoding='utf-8')
            development_touched=True
            command('stop','n8n');command('run','--rm','--no-deps','-v',str(WORK)+':/checks:ro','n8n','import:workflow','--input=/checks/workflow.json');imported=True
            command('run','--rm','--no-deps','n8n','publish:workflow','--id='+TEST_ID);command('up','-d','n8n');wait_ready(http)
            identifier='RPT-REAL-RAG-'+uuid.uuid4().hex[:10]
            query='Un tas de branches et de déchets est accumulé près d’une benne. Quelle procédure de signalement est documentée ?'
            category,department='WASTE','SANITATION_DEPARTMENT'
            if args.n8n_only_water:
                query="Comment vérifier une fuite avec les relevés du compteur d'eau ?"
                category,department='WATER_LEAK','WATER_SERVICES_DEPARTMENT'
            receipts_before=set((DATA/'receipts').glob('*.json'))
            before=time.perf_counter();response=http.post('http://127.0.0.1:5679/webhook/'+ROUTE,json={'report_id':identifier,'description':query,'category':category,'department':department})
            result=response.json();report['n8n_case']={'http_status':response.status_code,'elapsed_seconds':round(time.perf_counter()-before,3),'citizen_response':result}
            if response.status_code!=202 or result.get('report_id')!=identifier or result.get('components',{}).get('knowledge',{}).get('execution')!='responded':
                raise RuntimeError('REAL_N8N_KNOWLEDGE_TRANSPORT_FAILED')
            new_receipts=set((DATA/'receipts').glob('*.json'))-receipts_before
            matching=[json.loads(p.read_text(encoding='utf-8'))['native_record'] for p in new_receipts]
            matching=[r for r in matching if r['request']['description']==query]
            if len(matching)!=1:raise RuntimeError('N8N_NATIVE_RUN_NOT_CORRELATED')
            native=matching[0];report['n8n_case']['native_response']=native['response'];report['n8n_case']['usage']=usage(native)
            report['n8n_case']['execution']=execution(native)
            report['generation_calls']+=int(report['n8n_case']['execution']['generation_recorded'])
            if args.n8n_only_water and (not native['response']['answer_found'] or not native['response']['sources']):
                raise RuntimeError('POSITIVE_N8N_SOURCE_CASE_NOT_OBSERVED')
            if not result.get('policy',{}).get('gate_3',{}).get('checks',{}).get('receipt_verified'):
                raise RuntimeError('REAL_N8N_EVIDENCE_NOT_VERIFIED')
            if result['persisted'] or result['review_queued']:raise RuntimeError('FALSE_PERSISTENCE_CLAIM')
            print('PASS real n8n -> local RAG -> evidence/Gate 3 (labelled upstream fixture).',flush=True)
    except Exception as error:
        report['errors'].append(str(error) if isinstance(error,RuntimeError) else type(error).__name__)
    finally:
        if development_touched:
            try:
                cleanup_development(imported)
            except Exception:report['errors'].append('TEMPORARY_WORKFLOW_CLEANUP_FAILED')
        report['duration_seconds']=round(time.perf_counter()-started,3)
        with target.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    print(json.dumps({'report':target.relative_to(ROOT).as_posix(),'successful_generation_calls':report['generation_calls'],'errors':report['errors']}))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
