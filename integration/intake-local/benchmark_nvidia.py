"""One bounded NVIDIA free-development-endpoint experiment; no integration changes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

import httpx

from benchmark_cleaning import ROOT, HERE, pipeline, check, fingerprints

MODEL = 'nvidia/nemotron-3.5-lightning-30b-a3b'
ENDPOINT = 'https://integrate.api.nvidia.com/v1/chat/completions'
TARGET = ROOT/'project-docs/integration/intake-nvidia-nemotron-benchmark-01.json'
MAX_CALLS = 13


class BenchmarkStopped(RuntimeError):
    """Codes only, never raw provider exceptions/requests/headers."""


def explicit_key():
    value=os.environ.get('NVIDIA_API_KEY','')
    if os.environ.get('INTAKE_NVIDIA_KEY_SOURCE')!='project-dpapi' or not value:
        raise BenchmarkStopped('PROJECT_NVIDIA_KEY_MISSING_USE_POWERSHELL_WRAPPER')
    if re.search(r'[^\x21-\x7e]|[\"\']',value) or re.match(r'^(?:NVIDIA_API_KEY|NGC_API_KEY)=|^https?://',value,re.I):
        raise BenchmarkStopped('NVIDIA_KEY_FORMAT_INVALID')
    return value


def payload(text):
    return {'model':MODEL,'messages':[{'role':'system','content':pipeline.PROMPT},
            {'role':'user','content':f'<report_text>\n{text}\n</report_text>'}],
            'max_tokens':2000,'temperature':1.0,'top_p':0.95,'stream':False,
            'chat_template_kwargs':{'enable_thinking':False},
            'response_format':{'type':'json_object'}}


def sanitize(value, key):
    if isinstance(value,dict):return {k:sanitize(v,key) for k,v in value.items()}
    if isinstance(value,list):return [sanitize(v,key) for v in value]
    if isinstance(value,str):
        return re.sub(r'nvapi-[A-Za-z0-9_-]{16,}','[REDACTED_NVIDIA_KEY]',value.replace(key,'[REDACTED_NVIDIA_KEY]'))
    return value


class BoundedClient:
    def __init__(self,client):
        self.client=client
        self.attempts=0
        self.stopped=False

    def complete(self,text,key):
        if self.stopped or self.attempts>=MAX_CALLS:raise BenchmarkStopped('CALL_BUDGET_OR_STOP_REACHED')
        self.attempts+=1
        try:
            response=self.client.post(ENDPOINT,json=payload(text),headers={
                'Authorization':'Bearer '+key,'Accept':'application/json'})
            if response.status_code!=200:
                raise BenchmarkStopped('NVIDIA_HTTP_'+str(response.status_code))
            data=response.json()
            choices=data.get('choices')
            if not isinstance(choices,list) or len(choices)!=1:raise BenchmarkStopped('NVIDIA_CHOICES_INVALID')
            choice=choices[0]
            message=choice.get('message',{})
            content=message.get('content')
            if choice.get('finish_reason')!='stop':raise BenchmarkStopped('NVIDIA_GENERATION_INCOMPLETE')
            if not isinstance(content,str) or not content.strip():raise BenchmarkStopped('NVIDIA_CONTENT_MISSING')
            if message.get('tool_calls') or message.get('refusal'):raise BenchmarkStopped('NVIDIA_TOOL_CALL_OR_REFUSAL')
            try:output=json.loads(content)
            except ValueError:raise BenchmarkStopped('NVIDIA_OUTPUT_NOT_JSON') from None
            usage=data.get('usage') if isinstance(data.get('usage'),dict) else {}
            return output, {'http_status':response.status_code,'provider_model':data.get('model'),
                'response_id':data.get('id'),'finish_reason':choice['finish_reason'],
                'raw_output':content,'reasoning_output_present':bool(message.get('reasoning_content') or message.get('reasoning')),
                'usage':{k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if k in usage}}
        except Exception as error:
            self.stopped=True
            if isinstance(error,BenchmarkStopped):raise
            if isinstance(error,httpx.TimeoutException):raise BenchmarkStopped('NVIDIA_TIMEOUT') from None
            raise BenchmarkStopped('NVIDIA_TRANSPORT_OR_RESPONSE_ERROR') from None


def load_plan():
    path=HERE/'nvidia-benchmark-plan.json'
    plan=json.loads(path.read_text(encoding='utf-8'))
    fixtures=HERE/'cleaning-cases.json'
    if (plan['endpoint']!=ENDPOINT or plan['model']!=MODEL or plan['maximum_inference_calls']!=MAX_CALLS
            or plan['retries']!=0 or plan['catalog_free_endpoint_status']!='Available'
            or plan['http_timeout_seconds']!=150
            or hashlib.sha256(fixtures.read_bytes()).hexdigest()!=plan['fixtures_sha256']):
        raise BenchmarkStopped('UNEXPECTED_PLAN_OR_FIXTURES')
    cases=json.loads(fixtures.read_text(encoding='utf-8'))
    if len(cases)!=14 or sum(not c.get('skip_empty') for c in cases)!=MAX_CALLS:
        raise BenchmarkStopped('FIXTURE_CALL_BUDGET_INVALID')
    return plan,cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not args.run:parser.error('No calls made. Use the project PowerShell wrapper after saving your NVIDIA key.')
    if TARGET.exists():raise SystemExit('Existing NVIDIA result found; inspect it instead of repeating calls.')
    plan,cases=load_plan()
    key=explicit_key()
    before=fingerprints()
    marker=ROOT/'.runtime/nvidia-benchmark/run-01.started'
    marker.parent.mkdir(parents=True,exist_ok=True)
    # Persistent single-use marker also prevents concurrent launches/repeats after a crash.
    with marker.open('x',encoding='utf-8') as stream:stream.write(datetime.now(timezone.utc).isoformat())
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Standalone real NVIDIA text benchmark; not Intake API/n8n integration',
        'execution':'REAL_NVIDIA_API','plan':plan,'credential_source':'User-supplied project key via Windows DPAPI',
        'prompt_sha256':hashlib.sha256(pipeline.PROMPT.encode()).hexdigest(),
        'configuration':{k:v for k,v in payload('').items() if k!='messages'},
        'provider_reported_cost':None,'gemini_calls':0,'cases':[],'errors':[],
        'maximum_calls':MAX_CALLS,'retries':0,'fallback_enabled':False}
    started=time.perf_counter()
    # No redirects or SDK retries; fixed NVIDIA HTTPS endpoint only.
    with httpx.Client(timeout=httpx.Timeout(150,connect=10),trust_env=False,follow_redirects=False,
                      transport=httpx.HTTPTransport(retries=0)) as http:
        controller=BoundedClient(http)
        try:
            for case in cases:
                text,emails,phones=pipeline.masquer_texte(case['text'])
                row={'id':case['id'],'input_text':case['text'],'model_input_text':text,
                     'pre_masked_emails':emails,'pre_masked_phones':phones,
                     'expected_languages':case['languages'],'expected_quality':case['quality']}
                report['cases'].append(row)
                if not text.strip():
                    output={'language':'unknown','cleaned_text':'','text_quality':'EMPTY'}
                    row['execution']='DETERMINISTIC_EMPTY_BYPASS'
                else:
                    row['execution']='REAL_NVIDIA_API_ATTEMPT'
                    tick=time.perf_counter()
                    try:
                        output,metadata=controller.complete(text,key)
                        row.update(metadata)
                        row['execution']='REAL_NVIDIA_API_COMPLETED'
                    finally:row['wall_seconds']=round(time.perf_counter()-tick,3)
                row['output']=output
                row['automatic_issues']=check(case,output)
                row['automatic_checks_passed']=not row['automatic_issues']
                print(json.dumps({'case':case['id'],'issues':row['automatic_issues'],
                                  'seconds':row.get('wall_seconds',0)}),flush=True)
                if 'SCHEMA_INVALID' in row['automatic_issues']:raise BenchmarkStopped('NVIDIA_NATIVE_FIELDS_INVALID')
        except BenchmarkStopped as error:
            report['errors'].append(str(error))
        except Exception:
            report['errors'].append('BENCHMARK_UNEXPECTED_ERROR')
        finally:
            report['provider_call_attempts']=controller.attempts
            report['duration_seconds']=round(time.perf_counter()-started,3)
            report['cases_completed']=sum('output' in row for row in report['cases'])
            report['model_cases_passing_checks']=sum(row.get('automatic_checks_passed',False) for row in report['cases'] if row['execution']=='REAL_NVIDIA_API_COMPLETED')
            report['original_and_agent_files_unchanged']=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
            public=sanitize(report,key)
            with TARGET.open('x',encoding='utf-8') as stream:json.dump(public,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'result':TARGET.relative_to(ROOT).as_posix(),'calls':controller.attempts,'errors':report['errors']}))
    return int(bool(report['errors']) or not report['original_and_agent_files_unchanged'])


if __name__=='__main__':raise SystemExit(main())
