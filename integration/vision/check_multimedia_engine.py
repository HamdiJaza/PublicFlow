"""Real development n8n engine, explicitly synthetic HTTP agents. Zero AI calls."""
import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import threading
import time

import httpx
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from PIL import Image
import uvicorn

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.runtime/multimedia-engine-check'
WORKFLOW=ROOT/'n8n/vision-integration/municipal-intake-vision-development.json'
TARGET=ROOT/'project-docs/integration/multimedia-engine-results-05.json'
COMPOSE=['docker','compose','-f',str(ROOT/'n8n/intake-integration/compose.dev.yaml')]
TEST_ID='municipalMultimediaEngineCheck'


def command(*args):
    result=subprocess.run([*COMPOSE,*args],cwd=ROOT,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError('DEVELOPMENT_CLI_FAILED: '+args[-1])


def wait_ready(http):
    for _ in range(80):
        try:
            # healthz answers before Express installs webhook routes on startup.
            if http.get('http://127.0.0.1:5679/rest/settings',timeout=2).status_code==200:
                route=http.get('http://127.0.0.1:5679/webhook/municipal-multimedia-engine-check',timeout=2)
                if route.headers.get('content-type','').startswith('application/json') and 'Did you mean to make a POST request?' in route.json().get('message',''):
                    return
        except httpx.HTTPError:pass
        time.sleep(.5)
    raise RuntimeError('DEVELOPMENT_N8N_NOT_READY')


def main():
    if TARGET.exists():raise SystemExit('Existing engine results preserved; choose a new report before rerunning.')
    WORK.mkdir(parents=True,exist_ok=True)
    workflow=json.loads(WORKFLOW.read_text(encoding='utf-8'))
    workflow['id']=TEST_ID;workflow['name']='SYNTHETIC ONLY - Multimedia engine checks - NO AI'
    workflow.pop('versionId',None)
    workflow['settings']['saveDataErrorExecution']='all'
    workflow['settings']['saveDataSuccessExecution']='all'
    nodes={n['name']:n for n in workflow['nodes']}
    nodes['Citizen Webhook']['parameters']['path']='municipal-multimedia-engine-check'
    nodes['Citizen Webhook']['webhookId']='municipal-multimedia-engine-check'
    for node in workflow['nodes']:
        if node['type']=='n8n-nodes-base.httpRequest':
            params=node['parameters']
            route='/analyser' if node['name'].startswith('HTTP Intake') else '/vision' if node['name'].startswith('HTTP Vision') else '/media/resolve'
            params['url']='http://host.docker.internal:8094'+route
            params.pop('authentication',None);params.pop('genericAuthType',None);node.pop('credentials',None)
    workflow['meta']['test_scope']='All HTTP endpoints are explicit doubles; not real AI or privacy evidence'
    (WORK/'workflow.json').write_text(json.dumps(workflow),encoding='utf-8')
    config=json.JSONDecoder().raw_decode(nodes['Input Check']['parameters']['jsCode'].split('integration:',1)[1].lstrip())[0]
    buf=io.BytesIO();Image.new('RGB',(64,64),(90,100,110)).save(buf,format='PNG');png=buf.getvalue();digest=hashlib.sha256(png).hexdigest()
    state={'case':'','calls':[],'frame':0}
    service=FastAPI(title='SYNTHETIC engine-check HTTP doubles: NO AI')

    @service.post('/analyser')
    async def intake(texte:str=Form(''),image:UploadFile|None=File(None),audio:UploadFile|None=File(None),video:UploadFile|None=File(None)):
        parts=[kind for kind,value in [('image',image),('audio',audio),('video',video)] if value]
        state['calls'].append({'stage':'intake','parts':parts,'text':texte})
        for upload in [image,audio,video]:
            if upload and not await upload.read():return Response(status_code=422)
        if state['case']=='intake_failure':return Response(status_code=503)
        media=[]
        for i in range(1,4 if video else 2):
            media.append({'id':f'image_video_{i}' if video else 'image_independante','source':'video' if video else 'image',
                'path':config['trusted_safe_root']+'/'+'b'*32+'/image_'+str(i)*32+'.png','sha256':digest,
                'face_processing':{'sha256':digest,'detector':'YuNet','detector_completed':True,'write_and_decode_verified':True,
                    'faces_detected':0,'model_sha256':config['yunet_model_sha256']}})
        return {'schema_version':'intake-preparation-v1','language':'fr','cleaned_text':'SYNTHETIC waste report',
            'text_quality':'CLEAR','transcription_audio':'SYNTHETIC speech' if audio else '',
            'transcription_video':'SYNTHETIC speech' if video else '', 'media':media,'preparation_status':'READY',
            'processing_errors':[],'avertissements':[]}

    @service.post('/media/resolve')
    async def bridge(request:Request):
        reference=await request.json();state['calls'].append({'stage':'bridge','sha256':reference.get('sha256')})
        if state['case']=='expired_second' and state['frame']==1:return Response(status_code=409)
        if reference.get('sha256')!=digest:return Response(status_code=409)
        return Response(png,media_type='image/png',headers={'X-Content-SHA256':digest,'X-Media-Verification':'receipt-and-hash-checked'})

    @service.post('/vision')
    async def vision(image:UploadFile=File(...),report_id:str=Form(...),description:str=Form(...)):
        data=await image.read();state['frame']+=1
        state['calls'].append({'stage':'vision','frame':state['frame'],'hash_matches':hashlib.sha256(data).hexdigest()==digest,'report_id':report_id,'description':description})
        return {'report_id':report_id,'run_id':f'SYNTHETIC_FRAME{state["frame"]}_UPLOAD-'+digest[:12],
            'category':'ROAD_DAMAGE' if state['case']=='conflict' and state['frame']==2 else 'WASTE',
            'severity':'LOW','description':'SYNTHETIC ONLY','evidence':['SYNTHETIC ONLY'],'confidence':.8,'text_image_consistent':True,
            'uncertainty_reason':'SYNTHETIC uncertainty' if state['case']=='uncertain_second' and state['frame']==2 else None}

    listener=socket.socket();listener.bind(('0.0.0.0',8094));listener.listen(128)
    server=uvicorn.Server(uvicorn.Config(service,log_level='critical',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Real development n8n multipart, code nodes and branches with explicitly synthetic HTTP services',
        'real_ai_calls':0,'real_privacy_processing':False,'cases':[],'errors':[]}
    imported=False;started=time.perf_counter()
    try:
        thread.start()
        command('stop','n8n')
        command('run','--rm','--no-deps','-v',str(WORK)+':/checks:ro','n8n','import:workflow','--input=/checks/workflow.json');imported=True
        command('run','--rm','--no-deps','n8n','publish:workflow','--id='+TEST_ID)
        command('up','-d','n8n')
        with httpx.Client(trust_env=False,timeout=60) as http:
            wait_ready(http)
            for case,mode,expected_frames in [('image_text','image_text',1),('image_audio','image_audio',1),('video','video',3),
                    ('uncertain_second','video',2),('conflict','video',3),('expired_second','video',1),('intake_failure','image_audio',0)]:
                state.update(case=case,calls=[],frame=0)
                data={'report_id':'RPT-ENGINE-'+case.replace('_','-'),'location':'{"latitude":36.8,"longitude":10.18}'}
                if mode=='image_text':data['description']='SYNTHETIC municipal report'
                files={'video':('synthetic.mp4',b'SYNTHETIC VIDEO DOUBLE','video/mp4')} if mode=='video' else {'image':('synthetic.png',png,'image/png')}
                if mode=='image_audio':files['audio']=('synthetic.wav',b'SYNTHETIC AUDIO DOUBLE','audio/wav')
                response=http.post('http://127.0.0.1:5679/webhook/municipal-multimedia-engine-check',data=data,files=files)
                try:result=response.json()
                except ValueError:
                    report['cases'].append({'case':case,'status':response.status_code,'response_excerpt':response.text[:1000],'synthetic_calls':list(state['calls'])})
                    raise RuntimeError('ENGINE_RESPONSE_NOT_JSON')
                row={'case':case,'status':response.status_code,'citizen_response':result,'synthetic_calls':list(state['calls'])}
                report['cases'].append(row)
                assert response.status_code==202,(case,response.status_code)
                assert result['report_id']==data['report_id']
                assert state['frame']==expected_frames,(case,state['frame'])
                assert all(c.get('hash_matches',True) for c in state['calls'])
                assert result['policy']['gate_1']['decision']==('REVIEW' if case=='intake_failure' else 'PASS')
                if expected_frames:
                    assert result['visual_assessment']['assessed_frames']==expected_frames
                    assert result['visual_assessment']['attempted_frames']==expected_frames
                    assert len([t for t in result['trace'] if t['stage']=='GATE_2_VISION' and t.get('media_id')])==expected_frames
                    assert result['policy']['gate_2']['decision']==('REVIEW' if case in ['conflict','uncertain_second','expired_second'] else 'PASS')
                assert result['persisted'] is False and result['review_queued'] is False
                print('PASS real n8n engine / synthetic HTTP: '+case,flush=True)
    except Exception as error:
        report['errors'].append(str(error) if isinstance(error,(AssertionError,RuntimeError)) else type(error).__name__)
    finally:
        try:
            if imported:
                command('stop','n8n');command('run','--rm','--no-deps','n8n','unpublish:workflow','--id='+TEST_ID);command('up','-d','n8n')
        except Exception:report['errors'].append('TEMPORARY_WORKFLOW_CLEANUP_FAILED')
        server.should_exit=True
        if thread.is_alive():thread.join(5)
        listener.close();report['duration_seconds']=round(time.perf_counter()-started,3)
        with TARGET.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    print(json.dumps({'report':TARGET.relative_to(ROOT).as_posix(),'cases':len(report['cases']),'errors':report['errors']}))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
