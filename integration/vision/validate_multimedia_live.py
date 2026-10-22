"""Bounded real n8n -> NVIDIA preparation -> unchanged local Vision validation."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'intake-agent'),str(ROOT/'intake-agent/tools')]
from local_intake import nvidia, preparation
from local_intake.app import create_app
from local_intake.runtime import Settings
from local_intake.media import read_verified_image
from validate_preparation_live import checked_vision_artifact

TARGET=ROOT/'project-docs/integration/multimedia-live-results.json'
PRIVATE=ROOT/'.runtime/multimedia-live/results.json'


def main():
    if '--run' not in sys.argv:raise SystemExit('No calls made. Use Run_Multimedia_Validation.ps1 for the controlled developer-endpoint test.')
    if TARGET.exists() or PRIVATE.exists():raise SystemExit('Existing results preserved; no repeat API calls made.')
    if os.environ.get('INTAKE_NVIDIA_KEY_SOURCE')!='project-dpapi' or not os.environ.get('NVIDIA_API_KEY'):
        raise SystemExit('No explicit saved project credential; no calls made.')
    import httpx
    import uvicorn
    plan=json.loads((ROOT/'intake-agent/live-test-plan.json').read_text(encoding='utf-8'))
    image=ROOT/plan['image']
    speech=ROOT/'.runtime/nvidia-provider-validation/synthetic-fr-v2.wav'
    fixture=json.loads(speech.with_name('synthetic-fr-v2-plan.json').read_text(encoding='utf-8'))
    if (hashlib.sha256(image.read_bytes()).hexdigest()!=plan['image_sha256'] or fixture['text']!=plan['text']
            or hashlib.sha256(speech.read_bytes()).hexdigest()!=fixture['wav_sha256']):
        raise SystemExit('Approved photo or synthetic speech changed; no calls made.')
    PRIVATE.parent.mkdir(parents=True,exist_ok=True)
    video=PRIVATE.parent/'synthetic-waste-video.mp4'
    if not video.exists():
        conversion=subprocess.run([str(ROOT/'.runtime/tools/ffmpeg.exe'),'-v','error','-loop','1','-framerate','5','-i',str(image),
            '-i',str(speech),'-t','4.2','-vf','scale=640:-2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(video)],
            capture_output=True,timeout=30)
        if conversion.returncode:raise SystemExit('Local synthetic video creation failed; no API calls made.')
    allowed={'image':plan['image_sha256'],'audio':fixture['wav_sha256'],'video':hashlib.sha256(video.read_bytes()).hexdigest()}
    with httpx.Client(timeout=5,trust_env=False) as http:
        for url in ['http://127.0.0.1:5679/rest/settings','http://127.0.0.1:8010/openapi.json','http://127.0.0.1:8013/healthz']:
            http.get(url).raise_for_status()
        readiness=http.get('http://127.0.0.1:5679/webhook/municipal-intake-vision')
        if 'Did you mean to make a POST request?' not in readiness.json().get('message',''):
            raise SystemExit('Development POST webhook not ready; no API calls made.')
    listener=socket.socket();listener.bind(('0.0.0.0',8012));listener.listen(128)
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Fresh development n8n -> real NVIDIA Intake -> unchanged local Ollama Vision',
        'data_scope':'Previously approved waste photo; locally synthesized French speech; constructed test video repeating the waste photo with that speech',
        'synthetic_input_is_not_a_real_incident_video':True,'maximum_nvidia_calls':4,'gemini_calls':0,'retries':0,'provider_reported_cost':None,
        'source_hashes':allowed,'cases':[],'native_responses':[],'provider_trace':[],'errors':[]}
    original_prepare=preparation.prepare_report;original_begin=nvidia.begin
    def checked_prepare(text,paths):
        if text!='':raise RuntimeError('UNAPPROVED_TEXT')
        for kind,path in paths.items():
            if path and hashlib.sha256(Path(path).read_bytes()).hexdigest()!=allowed[kind]:raise RuntimeError('UNAPPROVED_MEDIA')
        return original_prepare(text,paths)
    def bounded_begin(*args,**kwargs):
        if len(report['provider_trace'])>=4:raise nvidia.NvidiaFailure('CONTROLLED_CALL_LIMIT')
        row,started=original_begin(*args,**kwargs);report['provider_trace'].append(row);return row,started
    service=create_app(Settings(text_provider='nvidia',transcription_provider='nvidia'),preparation_only=True)
    async def recorded(scope,receive,send):
        body=[]
        async def observe(message):
            if scope.get('method')=='POST' and scope.get('path')=='/analyser' and message['type']=='http.response.body':
                body.append(message.get('body',b''))
                if not message.get('more_body'):report['native_responses'].append(json.loads(b''.join(body)))
            await send(message)
        await service(scope,receive,observe)
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    server=uvicorn.Server(uvicorn.Config(recorded,log_level='critical',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    started=time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{'INTAKE_ALLOW_NVIDIA_CALLS':'1','INTAKE_ALLOW_PAID_CALLS':'0'}))
            stack.enter_context(patch('local_intake.preparation.prepare_report',checked_prepare))
            stack.enter_context(patch('local_intake.nvidia.begin',bounded_begin))
            thread.start()
            for _ in range(100):
                if server.started:break
                time.sleep(.1)
            if not server.started:raise RuntimeError('CONTROLLED_INTAKE_NOT_STARTED')
            with httpx.Client(timeout=2500,trust_env=False) as http:
                for name in ['image_audio','video']:
                    prior_calls=len(report['provider_trace'])
                    report_id='RPT-MULTIMEDIA-'+uuid.uuid4().hex[:10]
                    files={'video':('synthetic-waste.mp4',video.read_bytes(),'video/mp4')} if name=='video' else {
                        'image':('waste.jpg',image.read_bytes(),'image/jpeg'),'audio':('synthetic-fr.wav',speech.read_bytes(),'audio/wav')}
                    response=http.post('http://127.0.0.1:5679/webhook/municipal-intake-vision',
                        data={'report_id':report_id,'location':'{"latitude":36.8,"longitude":10.18}'},files=files)
                    result=response.json();report['cases'].append({'case':name,'status':response.status_code,'citizen_response':result})
                    if response.status_code!=202 or result.get('report_id')!=report_id or result.get('policy',{}).get('gate_1',{}).get('decision')!='PASS':
                        raise RuntimeError(name.upper()+'_GATE1_FAILED')
                    if len(report['provider_trace'])-prior_calls!=2 or any(c['status']!='SUCCESS' for c in report['provider_trace']):
                        raise RuntimeError('EXPECTED_PROVIDER_CALLS_NOT_VERIFIED')
                    gate2=result.get('policy',{}).get('gate_2',{})
                    if not gate2 or any(reason.startswith(('VISION_HTTP','VISION_TIMEOUT','VISION_UNAVAILABLE','VISION_SCHEMA','VISION_RUN_MEDIA','VISION_REPORT_ID')) for reason in gate2.get('reason_codes',[])):
                        raise RuntimeError('LIVE_VISION_TRANSPORT_OR_CONTRACT_FAILED')
                    native=report['native_responses'][-1]
                    transcript=native['transcription_audio' if name=='image_audio' else 'transcription_video']
                    if not transcript.strip():raise RuntimeError('REAL_TRANSCRIPT_MISSING')
                    for media in native['media']:read_verified_image(media['path'])
                    runs=ROOT/'vision-agent/Vision_Agent/02_VISION_PROJECT/evaluation/vision/runs'
                    artifacts=[json.loads(p.read_text(encoding='utf-8')) for p in runs.glob('*.json')]
                    artifacts=[a for a in artifacts if a.get('report_id')==report_id]
                    expected=result.get('visual_assessment',{}).get('assessed_frames')
                    if not artifacts or len(artifacts)!=expected:raise RuntimeError('VISION_ACTUAL_ARTIFACT_COUNT_MISMATCH')
                    digests={m['sha256'] for m in native['media']}
                    verified=[]
                    for artifact in artifacts:
                        if artifact.get('image_sha256') not in digests:raise RuntimeError('VISION_IMAGE_HASH_MISMATCH')
                        verified.append(checked_vision_artifact(artifact,report_id,artifact['image_sha256']))
                    report['cases'][-1]['vision_evidence']=verified
                    if result['persisted'] or result['review_queued']:raise RuntimeError('FALSE_PERSISTENCE_CLAIM')
                    print('PASS live multimedia: '+name,flush=True)
    except Exception as error:
        report['errors'].append(str(error) if isinstance(error,RuntimeError) else type(error).__name__)
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        listener.close();report['duration_seconds']=round(time.perf_counter()-started,3)
        report['nvidia_call_attempts']=len(report['provider_trace'])
        report=json.loads(json.dumps(report).replace(os.environ['NVIDIA_API_KEY'],'[REDACTED]'))
        with PRIVATE.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
        public=json.loads(json.dumps(report))
        for native in public['native_responses']:
            for media in native.get('media',[]):media['path']='[REDACTED_LOCAL_MEDIA_PATH]'
        with TARGET.open('x',encoding='utf-8') as output:json.dump(public,output,ensure_ascii=False,indent=2)
    print(json.dumps({'report':TARGET.relative_to(ROOT).as_posix(),'calls':report['nvidia_call_attempts'],'errors':report['errors']}))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
