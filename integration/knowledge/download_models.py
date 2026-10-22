"""Download BGE-M3 only; generation must reuse the approved installed Qwen model."""
import json
import sys
import urllib.request
from common import GENERATION_MODEL


def main():
    if '--download' not in sys.argv:raise SystemExit('No downloads made. Pass --download explicitly.')
    base='http://127.0.0.1:11434'
    with urllib.request.urlopen(base+'/api/tags',timeout=10) as response:
        installed={m['name'] for m in json.load(response)['models']}
    if GENERATION_MODEL not in installed:
        raise RuntimeError('Approved generation model is missing; no LLM will be downloaded automatically.')
    print(GENERATION_MODEL+': reusing installed model; no Qwen download.',flush=True)
    for model in ['bge-m3']:
        if model in installed or model+':latest' in installed:
            print(model+': already installed; preserved.',flush=True);continue
        request=urllib.request.Request(base+'/api/pull',data=json.dumps({'model':model,'stream':True}).encode(),headers={'Content-Type':'application/json'})
        previous=None
        with urllib.request.urlopen(request,timeout=600) as response:
            for line in response:
                value=json.loads(line)
                if 'error' in value:raise RuntimeError('Model download failed: '+model)
                total=value.get('total',0);completed=value.get('completed',0)
                bucket=int(100*completed/total)//10*10 if total else None
                state=(value.get('status'),bucket)
                if state!=previous:
                    print(model+': '+str(value.get('status',''))+(' '+str(bucket)+'%' if bucket is not None else ''),flush=True)
                    previous=state


if __name__=='__main__':main()
