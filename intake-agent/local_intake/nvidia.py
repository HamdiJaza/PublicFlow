"""Bounded NVIDIA preparation adapters. No visual inference or Gemini fallback."""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import time
import wave

import httpx

from . import pipeline
from .runtime import confined, state

TEXT_MODEL='nvidia/nemotron-3.5-lightning-30b-a3b'
TEXT_URL='https://integrate.api.nvidia.com/v1/chat/completions'
ASR_MODEL='openai/whisper-large-v3'
ASR_SERVER='grpc.nvcf.nvidia.com:443'
ASR_FUNCTION='b702f636-f60c-4a3d-a6f4-f3568c13bd7d'
PROMPT_VERSION='nvidia-normalize-fr-v2'
PROMPT=(Path(__file__).parent/'prompts'/f'{PROMPT_VERSION}.txt').read_text(encoding='utf-8')
TIMEOUT_SECONDS=150
MAX_CALLS=3  # At most two supplied speech sources and one text preparation.


class NvidiaFailure(RuntimeError):
    pass


def credential(test_double=False):
    if test_double:return 'OFFLINE-TEST-ONLY'
    key=os.environ.get('NVIDIA_API_KEY','')
    if (os.environ.get('INTAKE_ALLOW_NVIDIA_CALLS')!='1'
            or os.environ.get('INTAKE_NVIDIA_KEY_SOURCE')!='project-dpapi' or not key
            or re.search(r'[^\x21-\x7e]|[\"\']',key)):
        raise NvidiaFailure('NVIDIA_CALLS_DISABLED_OR_CREDENTIAL_MISSING')
    return key


def begin(stage,model,test_double):
    request=state()
    if request.provider_failed or request.provider_calls>=MAX_CALLS:
        raise NvidiaFailure('PROVIDER_STOP_OR_BUDGET_REACHED')
    request.provider_calls+=1
    record={'stage':stage,'provider':'nvidia','model':model,
            'inference_mode':'TEST_DOUBLE' if test_double else 'REAL_PROVIDER',
            'status':'ATTEMPTED'}
    if stage=='text':record.update(prompt_version=PROMPT_VERSION,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),normalization='French')
    request.provider_trace.append(record)
    return record,time.perf_counter()


def finish(record,started,error=None):
    record['elapsed_seconds']=round(time.perf_counter()-started,3)
    record['status']='ERROR' if error else 'SUCCESS'
    if error:
        record['error_code']=error
        state().provider_failed=True


def validate_cleaning(source,output):
    if (not isinstance(output,dict) or set(output)!={'language','cleaned_text','text_quality'}
            or output['language'] not in {'fr','en','ar','mixed','unknown'} or output['text_quality'] not in {'CLEAR','VAGUE','EMPTY'}
            or not isinstance(output['cleaned_text'],str) or len(output['cleaned_text'])>12000
            or (output['text_quality']=='CLEAR' and not output['cleaned_text'].strip())):
        raise NvidiaFailure('NVIDIA_TEXT_SCHEMA_INVALID')
    text=output['cleaned_text']
    # Limited script-consistency check, not a fabricated language detector.
    # Inconsistent model labels must be reviewed rather than overwritten.
    source_letters=re.sub(r'\[(?:EMAIL|TELEPHONE|NOM)\]','',source)
    arabic=bool(re.search(r'[\u0621-\u063a\u0641-\u064a]',source_letters))
    latin=bool(re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]',source_letters))
    if arabic and ((latin and output['language']!='mixed') or (not latin and output['language'] not in {'ar','unknown'})):
        raise NvidiaFailure('NVIDIA_SOURCE_LANGUAGE_INCONSISTENT')
    for marker in ('[EMAIL]','[TELEPHONE]'):
        if source.count(marker)!=text.count(marker):raise NvidiaFailure('NVIDIA_PLACEHOLDERS_CHANGED')
    if Counter(re.findall(r'\d+',source))!=Counter(re.findall(r'\d+',text)):
        raise NvidiaFailure('NVIDIA_NUMBERS_CHANGED')
    # These checks are limited invariants, not semantic or complete PII verification.
    return output


def clean_text(text):
    record=None
    try:
        factory=state().settings.nvidia_http_factory
        key=credential(factory is not None)
        if len(text)>16000:raise NvidiaFailure('NVIDIA_TEXT_INPUT_TOO_LONG')
        payload={'model':TEXT_MODEL,'messages':[{'role':'system','content':PROMPT},
                 {'role':'user','content':f'<report_text>\n{text}\n</report_text>'}],
                 'temperature':1.0,'top_p':0.95,'max_tokens':2000,'stream':False,
                 'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_object'}}
        client=factory() if factory else httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS,connect=10),
            trust_env=False,follow_redirects=False,transport=httpx.HTTPTransport(retries=0))
        with client:
            record,started=begin('text',TEXT_MODEL,factory is not None)
            response=client.post(TEXT_URL,json=payload,headers={'Authorization':'Bearer '+key,'Accept':'application/json'})
            record['http_status']=response.status_code
            if response.status_code!=200:raise NvidiaFailure('NVIDIA_HTTP_'+str(response.status_code))
            data=response.json()
            if data.get('model')!=TEXT_MODEL:raise NvidiaFailure('NVIDIA_MODEL_MISMATCH')
            choices=data.get('choices')
            if not isinstance(choices,list) or len(choices)!=1:raise NvidiaFailure('NVIDIA_CHOICES_INVALID')
            choice=choices[0];message=choice.get('message',{})
            if choice.get('finish_reason')!='stop' or message.get('tool_calls') or message.get('refusal'):
                raise NvidiaFailure('NVIDIA_TEXT_INCOMPLETE_OR_REFUSED')
            output=validate_cleaning(text,json.loads(message['content']))
            usage=data.get('usage') if isinstance(data.get('usage'),dict) else {}
            record['usage']={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if isinstance(usage.get(k),int)}
        finish(record,started)
        return output
    except Exception as error:
        code=str(error) if isinstance(error,NvidiaFailure) else ('NVIDIA_TIMEOUT' if isinstance(error,httpx.TimeoutException) else 'NVIDIA_TEXT_PROCESSING_FAILED')
        if record is not None:finish(record,started,code)
        return {'language':'unknown','cleaned_text':'','text_quality':'EMPTY','avertissement':code}


def recognize_wav(wav_path,key):
    import riva.client
    # The catalog's hosted gRPC route is authoritative; no invented HTTP URL.
    auth=riva.client.Auth(uri=ASR_SERVER,use_ssl=True,
        metadata_args=[['function-id',ASR_FUNCTION],['authorization','Bearer '+key]],
        options=[('grpc.enable_retries',0)])
    try:
        config=riva.client.RecognitionConfig(language_code='multi',sample_rate_hertz=16000,
            audio_channel_count=1,max_alternatives=1,enable_automatic_punctuation=True)
        config.custom_configuration['task']='transcribe'
        request=riva.client.proto.riva_asr_pb2.RecognizeRequest(config=config,audio=wav_path.read_bytes())
        return riva.client.ASRService(auth).stub.Recognize(request,metadata=auth.get_auth_metadata(),timeout=TIMEOUT_SECONDS)
    finally:auth.channel.close()


def transcribe_audio(path):
    record=None
    try:
        request=state()
        source=confined(path,request.raw)
        # Preserve the original conversion tool, but reject over-limit speech
        # before conversion instead of silently truncating it.
        probe=pipeline._lancer(['ffprobe','-v','error','-show_format','-of','json',str(source)])
        if probe.returncode!=0:raise NvidiaFailure('NVIDIA_AUDIO_INVALID')
        duration=float(json.loads(probe.stdout or b'{}').get('format',{}).get('duration',0))
        if not 0<duration<=120:raise NvidiaFailure('NVIDIA_AUDIO_DURATION_INVALID')
        wav=confined(pipeline.convertir_en_wav(str(source)),request.raw)
        with wave.open(str(wav),'rb') as audio:
            if (audio.getnchannels()!=1 or audio.getframerate()!=16000 or audio.getsampwidth()!=2
                    or audio.getnframes()==0):raise NvidiaFailure('NVIDIA_WAV_FORMAT_INVALID')
        factory=request.settings.nvidia_asr_factory
        key=credential(factory is not None)
        if factory is None:
            import riva.client  # Fail before counting an attempt if dependency is missing.
        record,started=begin('transcription',ASR_MODEL,factory is not None)
        response=factory(wav,key) if factory else recognize_wav(wav,key)
        transcripts=[]
        for result in response.results:
            if not result.alternatives:raise NvidiaFailure('NVIDIA_ASR_ALTERNATIVE_MISSING')
            transcripts.append(result.alternatives[0].transcript)
        text=' '.join(transcripts).strip()
        if not text or text=='[AUCUNE_PAROLE]':raise NvidiaFailure('NVIDIA_NO_INTELLIGIBLE_SPEECH')
        if len(text)>12000:raise NvidiaFailure('NVIDIA_TRANSCRIPT_TOO_LONG')
        record['audio_duration_seconds']=duration
        finish(record,started)
        return {'transcription':text}
    except Exception as error:
        code=str(error) if isinstance(error,NvidiaFailure) else 'NVIDIA_TRANSCRIPTION_FAILED'
        if callable(getattr(error,'code',None)):
            try:
                status=error.code().name
                if status in {'UNAUTHENTICATED','PERMISSION_DENIED','RESOURCE_EXHAUSTED','DEADLINE_EXCEEDED','UNAVAILABLE'}:
                    code='NVIDIA_ASR_'+status
            except Exception:pass
        if record is not None:finish(record,started,code)
        return {'transcription':'','avertissement':code}
