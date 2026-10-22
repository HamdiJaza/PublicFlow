"""Actual n8n HTTP handoff; recorded real Intake, optional real local Vision.

Never calls Gemini. Manual-trigger fixture replaces webhook/Intake execution;
all media-transfer, Vision, gates and routing nodes are the development nodes.
"""

import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'intake-agent'))
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from local_intake.media import read_verified_image

IMAGE='sha256:526daa38b68e923cc00c5280d18b4da5d489f115a73bdbf3b8e452b184197a9a'
VISION_ROOT=ROOT/'vision-agent/Vision_Agent/02_VISION_PROJECT'


def saved_intake():
    source=ROOT/'project-docs/integration/preparation-live-validation-new-key-04.json'
    public=json.loads(source.read_text(encoding='utf-8'))
    if public['errors'] or public['calls'][0]['status']!='SUCCESS':raise RuntimeError('Saved Intake was not successful')
    for path in (ROOT/'.runtime/preparation-live').glob('*/actual-result.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('started_at_utc')==public['started_at_utc']:
            native=value['native_response']
            data,evidence=read_verified_image(native['media'][0]['path'])
            if hashlib.sha256(data).hexdigest()!=native['media'][0]['sha256']:raise RuntimeError('Retained image changed')
            return native,public,hashlib.sha256(source.read_bytes()).hexdigest()
    raise RuntimeError('Private recorded Intake result is unavailable; no image substituted')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-vision',action='store_true')
    args=parser.parse_args()
    mode='real-vision' if args.real_vision else 'transport-double'
    target=ROOT/'project-docs/integration'/('vision-'+mode+'-result.json')
    if target.exists():raise SystemExit('Existing result found; inspect before repeating local inference.')
    native,prior,source_hash=saved_intake()
    expected=native['media'][0]['sha256']
    plan=json.loads((ROOT/'intake-agent/live-test-plan.json').read_text(encoding='utf-8'))
    photo=ROOT/plan['image']
    assert hashlib.sha256(photo.read_bytes()).hexdigest()==plan['image_sha256']
    w=json.loads((ROOT/'n8n/vision-integration/municipal-intake-vision-development.json').read_text(encoding='utf-8'))
    w=copy.deepcopy(w);w['id']='municipalVisionEngineCheck'
    seed={'json':{'body':{'report_id':'RPT-VISION-ENGINE-'+str(time.time_ns()),'description':plan['text'],'location':json.dumps({'latitude':36.8,'longitude':10.18})}},
          'binary':{'image':{'data':base64.b64encode(photo.read_bytes()).decode(),'mimeType':'image/jpeg','fileName':'approved-waste.jpg'}}}
    for node in w['nodes']:
        if node['name']=='Citizen Webhook':node.update(type='n8n-nodes-base.manualTrigger',typeVersion=1,parameters={})
        elif node['name']=='HTTP Intake':
            node.update(type='n8n-nodes-base.code',typeVersion=2,parameters={'mode':'runOnceForAllItems','jsCode':'// RECORDED REAL INTAKE RESPONSE; no new Gemini request.\nreturn [{json:'+json.dumps({'statusCode':200,'body':native},ensure_ascii=False)+'}];'})
        elif node['name']=='Attach Intake Response':
            code=node['parameters']['jsCode']
            node['parameters']['jsCode']=code.replace('return [{json:x}];',"x.components.intake={execution:'recorded_response_replayed',inference:'recorded_real_gemini_result',source_record_sha256:'"+source_hash+"',new_provider_calls:0};return [{json:x}];")
        elif node['name']=='Respond to Citizen':node.update(type='n8n-nodes-base.code',typeVersion=2,parameters={'mode':'runOnceForAllItems','jsCode':'return $input.all();'})
    w['nodes'].append({'id':'offline-seed','name':'Recorded-input fixture','type':'n8n-nodes-base.code','typeVersion':2,'position':[0,0],
                      'parameters':{'mode':'runOnceForAllItems','jsCode':'return ['+json.dumps(seed,ensure_ascii=False)+'];'}})
    w['connections']['Citizen Webhook']={'main':[[{'node':'Recorded-input fixture','type':'main','index':0}]]}
    w['connections']['Recorded-input fixture']={'main':[[{'node':'Input Check','type':'main','index':0}]]}
    server=None;thread=None;listener=None;calls=[]
    if not args.real_vision:
        service=FastAPI()
        @service.post('/vision')
        def fake_vision(image:UploadFile=File(),report_id:str=Form(),description:str=Form()):
            data=image.file.read();digest=hashlib.sha256(data).hexdigest()
            assert digest==expected and description==native['cleaned_text']
            calls.append({'sha256':digest,'report_id':report_id})
            return {'report_id':report_id,'run_id':'OFFLINE-FIXTURE_UPLOAD-'+digest[:12],
                    'category':'WASTE','severity':'LOW','description':'TEST DOUBLE ONLY','evidence':['TEST DOUBLE ONLY'],
                    'text_image_consistent':True,'confidence':0.8,'uncertainty_reason':None}
        listener=socket.socket();listener.bind(('0.0.0.0',0));listener.listen(128)
        port=listener.getsockname()[1]
        next(n for n in w['nodes'] if n['name']=='HTTP Vision')['parameters']['url']=f'http://host.docker.internal:{port}/vision'
        node=next(n for n in w['nodes'] if n['name']=='Attach Vision Response')
        node['parameters']['jsCode']=node['parameters']['jsCode'].replace('return [{json:x}];',"x.components.vision.inference='TEST_DOUBLE';return [{json:x}];")
        server=uvicorn.Server(uvicorn.Config(service,log_level='error',access_log=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.1)
        if not server.started:raise RuntimeError('Vision double did not start')
    folder=ROOT/'.runtime/vision-checks';folder.mkdir(parents=True,exist_ok=True)
    workflow_file=folder/(mode+'.json');workflow_file.write_text(json.dumps(w,ensure_ascii=False),encoding='utf-8')
    started=time.perf_counter()
    command=['docker','run','--rm','--mount',f'type=bind,source={folder},target=/checks,readonly',
        '--mount',f'type=bind,source={ROOT/".runtime/media-bridge"},target=/bridge,readonly',
        '-e','N8N_DIAGNOSTICS_ENABLED=false','-e','N8N_VERSION_NOTIFICATIONS_ENABLED=false','-e','N8N_TEMPLATES_ENABLED=false',
        '--entrypoint','sh',IMAGE,'-c',
        '(n8n import:credentials --input=/bridge/n8n-credential.json >/tmp/cred.log 2>&1 || { cat /tmp/cred.log; exit 1; }) && (n8n import:workflow --input=/checks/'+workflow_file.name+' >/tmp/import.log 2>&1 || { cat /tmp/import.log; exit 1; }) && n8n execute --id=municipalVisionEngineCheck --rawOutput']
    try:
        process=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=2400)
        secret=(ROOT/'.runtime/media-bridge/access.token').read_text(encoding='utf-8').strip()
        (folder/(mode+'.log')).write_text((process.stdout+'\n'+process.stderr).replace(secret,'[REDACTED_MEDIA_KEY]'),encoding='utf-8')
        start=process.stdout.find('\n{\n  "data":')
        if process.returncode or start<0:raise RuntimeError('n8n execution result missing; inspect ignored local engine log')
        result,_=json.JSONDecoder().raw_decode(process.stdout[start+1:])
        runs=result['data']['resultData']['runData']
        final=runs['Respond to Citizen'][0]['data']['main'][0][0]['json']
        context=runs['Attach Verified Media'][0]['data']['main'][0][0]['json']
        assert final['report_id']==seed['json']['body']['report_id']
        assert context['original']['description']==plan['text']
        assert context['original']['location']==json.loads(seed['json']['body']['location'])
        summary={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'mode':mode,
                 'intake_execution':'Recorded real Gemini response; no new Intake inference',
                 'new_gemini_calls':0,'scope':'Actual n8n HTTP media bridge and Vision; manual trigger replaces webhook',
                 'execution_status':result['status'],'duration_seconds':round(time.perf_counter()-started,3),
                 'citizen_response':final,'prepared_image_sha256':expected,'errors':[]}
        summary['context_checks']={'report_id_preserved':True,'original_description_preserved':True,'location_preserved':True}
        if 'Attach Vision Response' in runs:
            attached=runs['Attach Vision Response'][0]['data']['main'][0][0]['json']
            summary['vision_http']=attached['vision_http'];summary['vision_native']=attached['vision_native']
            if args.real_vision and summary['vision_native']:
                run=summary['vision_native']['run_id']
                artifact=json.loads((VISION_ROOT/'evaluation/vision/runs'/(run+'.json')).read_text(encoding='utf-8'))
                assert artifact['image_sha256']==expected
                assert artifact['description']==native['cleaned_text']
                summary['context_checks']['cleaned_text_forwarded_to_vision']=True
                summary['vision_evidence']={'model':artifact['model'],'model_digest':artifact.get('model_digest'),
                    'prompt_version':artifact['prompt_version'],'status':artifact['status'],
                    'image_sha256':artifact['image_sha256'],'schema_valid':artifact['schema_valid'],
                    'local_model_calls':1+len(artifact.get('stages',[])),
                    'inference_seconds':artifact.get('inference_seconds'),'elapsed_seconds':artifact['elapsed_seconds']}
        if final['policy']['gate_1']['decision']!='PASS':summary['errors'].append('GATE_1_NOT_PASS')
        if not final.get('policy',{}).get('gate_2'):summary['errors'].append('VISION_NOT_REACHED')
        if not args.real_vision:
            if len(calls)!=1 or final.get('policy',{}).get('gate_2',{}).get('decision')!='PASS':summary['errors'].append('TRANSPORT_CHECK_FAILED')
        target.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'mode':mode,'errors':summary['errors'],'policy':final['policy'],
            'overall':final['decision'],'report':target.relative_to(ROOT).as_posix()},indent=2))
        return int(bool(summary['errors']))
    finally:
        if server:server.should_exit=True
        if thread:thread.join(10)
        if listener:listener.close()


if __name__=='__main__':raise SystemExit(main())
