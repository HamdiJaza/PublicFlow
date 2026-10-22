"""Workspace-only runtime preparation; delivered RAG files remain read-only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'rag-agent/Knowledge_Agent'
RUNTIME=ROOT/'.runtime/knowledge-agent/Knowledge_Agent'
DATA=ROOT/'.runtime/knowledge-data'
BASELINE=ROOT/'project-docs/integration/knowledge-delivery-baseline.json'
GENERATION_MODEL='qwen2.5:3b'  # User selected the delivered model already installed on the recovery PC.
OLLAMA_URL='http://127.0.0.1:11435'  # Project-only server; shared model artifacts, no global settings changes.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure():
    """Never select a paid provider or inherit a different model accidentally."""
    os.environ.update(GENERATION_PROVIDER='ollama',OLLAMA_MODEL=GENERATION_MODEL,EMBEDDING_MODEL='bge-m3',
        OLLAMA_URL=OLLAMA_URL,QDRANT_PATH=str(DATA/'qdrant'),CHUNK_STRATEGY='structure',
        TOP_K='3',SCORE_THRESHOLD='0.40',HF_HOME=str(ROOT/'.runtime/huggingface'),
        HF_HUB_DISABLE_IMPLICIT_TOKEN='1',HF_HUB_DISABLE_TELEMETRY='1',HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false')


def prepare():
    inventory=json.loads((DELIVERY/'PACKAGE_CONTENTS.json').read_text(encoding='utf-8'))
    records=list(inventory['files'])
    records.append({'path':'PACKAGE_CONTENTS.json','sha256':digest(DELIVERY/'PACKAGE_CONTENTS.json')})
    for record in records:
        path=(DELIVERY/record['path']).resolve()
        if not path.is_relative_to(DELIVERY.resolve()) or not path.is_file() or digest(path)!=record['sha256']:
            raise RuntimeError('Delivered RAG inventory mismatch: '+record['path'])
    baseline={'scope':'New RAG delivery; hashes of original files before integration','files':records}
    if BASELINE.exists():
        old=json.loads(BASELINE.read_text(encoding='utf-8'))
        if old['files']!=records:raise RuntimeError('Delivery differs from the preserved integration baseline.')
    else:
        BASELINE.write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8')
    archive=ROOT/'.runtime/backups/knowledge-delivery.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as output:
            for record in records:output.write(DELIVERY/record['path'],record['path'])
    for record in records:
        target=RUNTIME/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and digest(target)!=record['sha256']:raise RuntimeError('Runtime source changed: '+record['path'])
        if not target.exists():shutil.copyfile(DELIVERY/record['path'],target)
    configure()
    return len(records)


if __name__=='__main__':print('Verified and preserved '+str(prepare())+' RAG delivery files; created isolated runtime copy.')
