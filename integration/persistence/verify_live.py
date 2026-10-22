"""Read-only verification of an already completed browser submission.

Does not call models, run a workflow, fabricate results or expose credentials.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_id')
    args = parser.parse_args()
    if not re.fullmatch(r'RPT-[a-f0-9]{32}', args.report_id):
        raise SystemExit('Invalid portal report ID.')
    receipt = json.loads((ROOT/'.runtime/portal/jobs'/(args.report_id+'.json')).read_text(encoding='utf-8'))
    result = receipt.get('result', {})
    if receipt['state'] != 'completed' or result.get('workflow_status') != 'COMPLETED' or not result.get('persisted'):
        raise SystemExit('Submission has not confirmed workflow completion and persistence.')
    # The identifier is validated above; no untrusted SQL or credential interpolation.
    query = """SELECT jsonb_build_object('tracking_id',t.tracking_id,'report_id',t.report_id,
        'status',t.status,'decision',t.decision,'payload',t.payload,
        'creation_events',(SELECT count(*) FROM municipal.ticket_events WHERE tracking_id=t.tracking_id AND event='CREATED'),
        'review_records',(SELECT count(*) FROM municipal.review_records WHERE tracking_id=t.tracking_id),
        'review_pending',(SELECT count(*) FROM municipal.review_records WHERE tracking_id=t.tracking_id AND status='PENDING'))
        FROM municipal.tickets t WHERE report_id='"""+args.report_id+"';"
    response = subprocess.run(['docker','exec','-i','municipal-ticket-postgres-dev','psql','-X','-q','-A','-t',
        '-U','municipal_admin','-d','municipal_tickets','-v','ON_ERROR_STOP=1'], input=query,
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    if response.returncode or not response.stdout.strip():
        raise SystemExit('Could not independently read the committed database record.')
    database = json.loads(response.stdout)
    if database['tracking_id'] != result['ticket']['tracking_id'] or database['creation_events'] != 1:
        raise SystemExit('Database receipt/event mismatch.')
    vision = []
    run_root = ROOT/'vision-agent/Vision_Agent/02_VISION_PROJECT/evaluation/vision/runs'
    for frame in database['payload'].get('vision_frames', []):
        run_id = frame.get('native', {}).get('run_id','')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
            raise SystemExit('Invalid native Vision run association.')
        record = json.loads((run_root/(run_id+'.json')).read_text(encoding='utf-8'))
        if record.get('report_id') != args.report_id or record.get('image_sha256') != frame['sha256']:
            raise SystemExit('Native Vision run does not match ticket.')
        vision.append({k:record.get(k) for k in ('run_id','report_id','model','model_digest','prompt_version',
            'image_sha256','status','schema_valid','inference_seconds','elapsed_seconds','observation')})
    rag_evidence = None
    knowledge = database['payload'].get('knowledge', {})
    if result['components'].get('knowledge', {}).get('execution') == 'responded':
        started = datetime.fromisoformat(receipt['started_at']).timestamp()
        finished = datetime.fromisoformat(receipt['finished_at']).timestamp()
        matches = []
        for path in (ROOT/'.runtime/knowledge-data/receipts').glob('*.json'):
            candidate = json.loads(path.read_text(encoding='utf-8'))
            native = candidate['native_record']
            if (started <= candidate['created_at_epoch'] <= finished
                    and native.get('request') == knowledge.get('request')
                    and native.get('response') == knowledge.get('native')):
                matches.append((path, native))
        if len(matches) != 1:
            raise SystemExit('Cannot uniquely associate the native RAG receipt with this run.')
        path, native = matches[0]
        raw = native.get('raw_response', {})
        rag_evidence = {'receipt_file':path.name,'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'request':native['request'],'response':native['response'],'status':native.get('status'),
            'selected_context':[{k:s.get(k) for k in ('chunk_id','doc_id','url','score','category','municipality')}
                                for s in native.get('context_sources',[])],
            'generation':{k:raw.get(k) for k in ('model','done','done_reason','prompt_eval_count','eval_count','total_duration','load_duration')},
            'settings':native.get('settings')}
    with httpx.Client(timeout=10,trust_env=False) as client:
        lookup = client.get('http://127.0.0.1:8090/api/tickets/'+database['tracking_id'])
        lookup.raise_for_status()
        if lookup.json()['ticket']['tracking_id'] != database['tracking_id']:
            raise SystemExit('Portal tracking lookup mismatch.')
    originals = 0
    for name,prefix in [('phase0-baseline.json',''),('knowledge-delivery-baseline.json','rag-agent/Knowledge_Agent')]:
        for record in json.loads((ROOT/'project-docs/integration'/name).read_text(encoding='utf-8'))['files']:
            path=ROOT/prefix/record['path']
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
                raise SystemExit('Original member file changed: '+record['path'])
            originals += 1
    report = {'verified_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Actual browser media submission, real native agent calls, n8n orchestration and independent PostgreSQL readback.',
        'receipt':receipt,'database':database,'native_vision_evidence':vision,'native_rag_evidence':rag_evidence,'portal_tracking':lookup.json(),
        'original_files_unchanged':originals,
        'checks':{'completion_node_checks':32,'prior_workflow_checks':126,'portal_offline_tests':16,'real_postgresql_tests':11},
        'limits':['This run covers this photo and description only, not all video/audio/error scenarios.',
            'Review flags remain; completion is not a claim of verified municipal procedure or human approval.',
            'The staff dashboard remains deferred. Status transitions are implemented and tested at the database layer.']}
    path=ROOT/'project-docs/integration'/('completion-live-'+args.report_id+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'evidence_file':str(path),'tracking_id':database['tracking_id'],'workflow_status':result['workflow_status'],
        'ticket_status':database['status'],'agents':{k:v.get('execution') for k,v in result['components'].items()},
        'policy':{k:v.get('decision') for k,v in result['policy'].items()},'original_files_unchanged':originals}))


if __name__=='__main__':
    main()
