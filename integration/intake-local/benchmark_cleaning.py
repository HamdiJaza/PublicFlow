"""Bounded local-only text benchmark; never configures an agent or calls Gemini.

Uses the delivered cleaning prompt, synthetic reports and installed model only.
Automatic checks are limited invariants; semantic review must inspect outputs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'intake-agent'))
from local_intake import pipeline

MODEL = 'qwen3:4b'
DIGEST = '359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7'
BASE = 'http://127.0.0.1:11434/'
SCHEMA = {'type':'object', 'properties':{
    'language':{'type':'string','enum':['fr','en','ar','mixed','unknown']},
    'cleaned_text':{'type':'string'},
    'text_quality':{'type':'string','enum':['CLEAR','VAGUE','EMPTY']}},
    'required':['language','cleaned_text','text_quality'], 'additionalProperties':False}


def request(endpoint, body=None, timeout=10):
    # Fixed loopback address; ignore all proxy settings. No model pull endpoint.
    if endpoint not in {'api/tags','api/version','api/ps','api/chat','api/generate'}:
        raise ValueError('Unexpected endpoint')
    data = None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE+endpoint,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as response:
        return json.load(response)


def check(case, output):
    problems=[]
    if (not isinstance(output,dict) or set(output)!=set(SCHEMA['required'])
            or not all(isinstance(output.get(k),str) for k in SCHEMA['required'])):
        return ['SCHEMA_INVALID']
    if output['language'] not in case['languages']:problems.append('LANGUAGE_MISMATCH')
    if output['text_quality']!=case['quality']:problems.append('QUALITY_MISMATCH')
    text=output['cleaned_text'].casefold()
    if case.get('skip_empty') and text.strip():problems.append('EMPTY_INPUT_INVENTED_TEXT')
    if case['quality']=='CLEAR' and not text.strip():problems.append('CLEAR_TEXT_EMPTY')
    for index,alternatives in enumerate(case['anchors']):
        if not any(anchor.casefold() in text for anchor in alternatives):
            problems.append('REQUIRED_CONTENT_MISSING_'+str(index+1))
    for token in case.get('forbidden',[]):
        if token.casefold() in text:problems.append('UNMASKED_TEST_PERSONAL_DATA_OR_PROFANITY')
    return list(dict.fromkeys(problems))


def fingerprints():
    baseline=json.loads((ROOT/'project-docs/integration/phase0-baseline.json').read_text(encoding='utf-8'))
    paths=[ROOT/f['path'] for f in baseline['files']]
    paths+=list((ROOT/'intake-agent/local_intake').glob('*.py'))
    return {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Run the bounded local benchmark')
    args=parser.parse_args()
    if not args.run:parser.error('Use --run to start local inference; no calls made.')
    target=ROOT/'project-docs/integration/intake-qwen3-4b-benchmark-01.json'
    if target.exists():raise SystemExit('Existing benchmark found; inspect it instead of overwriting.')
    cases=json.loads((HERE/'cleaning-cases.json').read_text(encoding='utf-8'))
    if len(cases)>14:raise SystemExit('Case budget exceeded')
    before=fingerprints()
    models=request('api/tags')['models']
    installed=next((m for m in models if m['name']==MODEL),None)
    if not installed or installed['digest']!=DIGEST:raise SystemExit('Pinned installed model not verified; no download attempted.')
    if request('api/ps')['models']:raise SystemExit('Another model is loaded; refusing to disturb the current Ollama workload.')
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Standalone local text benchmark, not an Intake API or n8n integration test',
        'data':'Synthetic fixtures only; fictional names/contact examples',
        'model':MODEL,'model_digest':DIGEST,'model_details':installed['details'],
        'ollama_version':request('api/version')['version'],
        'prompt_sha256':hashlib.sha256(pipeline.PROMPT.encode()).hexdigest(),
        'cases_sha256':hashlib.sha256((HERE/'cleaning-cases.json').read_bytes()).hexdigest(),
        'configuration':{'think':False,'temperature':0,'num_ctx':4096,'num_predict':2000,
                         'per_case_deadline_seconds':90,'retries':0,'structured_json_schema':SCHEMA},
        'gemini_calls':0,'model_call_attempts':0,'model_unload_requests':0,
        'cases':[],'errors':[],
        'limits':'Automatic checks are anchors/types, not proof of semantic fidelity, general PII removal, dialect quality or calibrated accuracy. No audio/media, privacy detector or policy gate exercised.'}
    started=time.perf_counter()
    try:
        for case in cases:
            masked,emails,phones=pipeline.masquer_texte(case['text'])
            row={'id':case['id'],'input_text':case['text'],'model_input_text':masked,
                 'pre_masked_emails':emails,'pre_masked_phones':phones,
                 'expected_languages':case['languages'],'expected_quality':case['quality']}
            report['cases'].append(row)
            if not masked.strip():
                row.update(execution='DETERMINISTIC_EMPTY_BYPASS',output={'language':'unknown','cleaned_text':'','text_quality':'EMPTY'})
            else:
                report['model_call_attempts']+=1
                tick=time.perf_counter()
                response=request('api/chat',{
                    'model':MODEL,'messages':[{'role':'system','content':pipeline.PROMPT},
                        {'role':'user','content':f'<report_text>\n{masked}\n</report_text>'}],
                    'format':SCHEMA,'think':False,'stream':False,'keep_alive':'60s',
                    'options':{'temperature':0,'num_ctx':4096,'num_predict':2000}},timeout=90)
                row['wall_seconds']=round(time.perf_counter()-tick,3)
                row['execution']='REAL_LOCAL_OLLAMA'
                row['completion_metadata']={k:response.get(k) for k in
                    ('model','done','done_reason','total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')}
                row['raw_output']=response.get('message',{}).get('content')
                row['thinking_output_present']=bool(response.get('message',{}).get('thinking'))
                if response.get('done') is not True or response.get('done_reason')!='stop':
                    row['error']='INCOMPLETE_GENERATION'
                    report['errors'].append(case['id']+':INCOMPLETE_GENERATION')
                    break
                try:row['output']=json.loads(row['raw_output'])
                except (TypeError,ValueError):row['output']=None
                if report['model_call_attempts']==1:report['loaded_model_memory_sample']=request('api/ps')
            row['automatic_issues']=check(case,row['output'])
            row['automatic_checks_passed']=not row['automatic_issues']
            print(json.dumps({'case':case['id'],'seconds':row.get('wall_seconds',0),
                              'issues':row['automatic_issues']},ensure_ascii=False),flush=True)
    except Exception as error:
        # No payloads, credentials, provider bodies or stack traces in errors.
        report['errors'].append(type(error).__name__)
    finally:
        if report['model_call_attempts']:
            try:
                report['model_unload_requests']+=1
                unloaded=request('api/generate',{'model':MODEL,'keep_alive':0},timeout=20)
                report['model_unload_confirmed']=unloaded.get('done') is True
            except Exception as error:report['errors'].append('UNLOAD_'+type(error).__name__)
        report['duration_seconds']=round(time.perf_counter()-started,3)
        report['original_and_agent_files_unchanged']=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
        report['automatic_pass_count']=sum(r.get('automatic_checks_passed',False) for r in report['cases'])
        report['cases_completed']=sum('automatic_issues' in r for r in report['cases'])
        # Exclusive creation preserves results even when another launch races.
        with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'report':target.relative_to(ROOT).as_posix(),'completed':report['cases_completed'],
        'automatic_pass_count':report['automatic_pass_count'],'errors':report['errors']},ensure_ascii=False))
    return int(bool(report['errors']) or report['cases_completed']!=len(cases) or not report['original_and_agent_files_unchanged'])


if __name__=='__main__':raise SystemExit(main())
