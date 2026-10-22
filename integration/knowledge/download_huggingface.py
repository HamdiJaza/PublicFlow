"""Fetch original BAAI BGE-M3 weights; downloading does not register an Ollama model."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from common import ROOT

REVISION='5617a9f61b028005a4858fdac845db406aefb181'
REPOSITORY='BAAI/bge-m3'
# Published at the pinned official Hugging Face checkpoint page.
WEIGHT_SHA256='b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38'
FILES=['pytorch_model.bin','config.json','modules.json','config_sentence_transformers.json',
       'sentence_bert_config.json','1_Pooling/config.json','sentencepiece.bpe.model',
       'tokenizer.json','tokenizer_config.json','special_tokens_map.json']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--label',default='hf-01')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',args.label):raise SystemExit('Invalid run label')
    if not args.download:
        print(json.dumps({'repository':REPOSITORY,'revision':REVISION,'files':FILES,
                         'downloaded':False,'next':'Pass --download for the approved public weights download.'}))
        return 0
    report_path=ROOT/f'project-docs/integration/knowledge-huggingface-download-{args.label}.json'
    if report_path.exists():raise SystemExit('Existing download evidence preserved; select a new run label to retry.')
    folder=(ROOT/'.runtime/hf-bge-m3'/REVISION).resolve()
    if not folder.is_relative_to(ROOT.resolve()):raise SystemExit('Model destination escapes the workspace')
    report={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'repository':REPOSITORY,
            'revision':REVISION,'files':[],'errors':[],'checkpoint_download_complete':False,
            'ollama_model_registered':False,'rag_retrieval_verified':False}
    try:
        for relative in FILES:
            target=(folder/relative).resolve()
            if not target.is_relative_to(folder):raise ValueError('Invalid model file path')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if relative=='pytorch_model.bin':
                    with target.open('rb') as source:
                        if hashlib.file_digest(source,'sha256').hexdigest()!=WEIGHT_SHA256:
                            raise ValueError('Existing checkpoint hash mismatch; original file preserved')
                else:raise ValueError('Existing non-weight file preserved; inspect before continuing')
            else:
                partial=target.with_name(target.name+'.partial')
                if partial.exists():raise ValueError('Partial model download preserved; inspect before retrying')
                url=f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{relative}'
                request=urllib.request.Request(url,headers={'User-Agent':'Municipal-RAG-Recovery/1.0'})
                checksum=hashlib.sha256();size=0
                # Default system/session networking is respected. No proxy or TLS bypass.
                with urllib.request.urlopen(request,timeout=120) as response,partial.open('xb') as output:
                    while chunk:=response.read(1024*1024):
                        size+=len(chunk)
                        if size>(3*1024**3 if relative=='pytorch_model.bin' else 64*1024**2):
                            raise ValueError('Model file exceeds the expected download limit')
                        checksum.update(chunk);output.write(chunk)
                if relative=='pytorch_model.bin' and checksum.hexdigest()!=WEIGHT_SHA256:
                    raise ValueError('Downloaded checkpoint hash mismatch; partial file preserved')
                partial.rename(target)
            with target.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
            report['files'].append({'path':relative,'bytes':target.stat().st_size,'sha256':digest})
            print('Verified downloaded file: '+relative,flush=True)
        report['checkpoint_download_complete']=True
    except (OSError,ValueError,urllib.error.URLError) as error:
        # Do not persist signed CDN URLs, inherited proxy credentials or provider bodies.
        report['errors'].append({'type':type(error).__name__,
            'reason':'Download or file validation failed; no model/index readiness is claimed.'})
    with report_path.open('x',encoding='utf-8') as output:json.dump(report,output,indent=2)
    print(json.dumps({'report':report_path.relative_to(ROOT).as_posix(),
                     'checkpoint_download_complete':report['checkpoint_download_complete'],
                     'ollama_model_registered':False,'errors':report['errors']}))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
