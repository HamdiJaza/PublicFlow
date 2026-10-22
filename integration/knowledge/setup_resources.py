"""Cache only the public tokenizer, then build fresh real BGE/Qdrant indexes."""
import json
import os
import sys
from common import ROOT,RUNTIME,configure,prepare


def main():
    prepare();configure();sys.path.insert(0,str(RUNTIME))
    # Some tokenizer-library versions still inspect Hub metadata with
    # local_files_only=True. Normal indexing must use the recovered cache only.
    # Set this before importing transformers/huggingface_hub (they cache flags).
    if '--download-tokenizer' in sys.argv:os.environ['HF_HUB_OFFLINE']='0'
    from config import Settings
    from rag.embeddings import OllamaEmbeddings
    from transformers import AutoTokenizer
    settings=Settings.from_env()
    if '--download-tokenizer' in sys.argv:
        AutoTokenizer.from_pretrained(settings.tokenizer_model,token=False)
        print('Cached public BGE-M3 tokenizer; no Hugging Face model weights requested.',flush=True)
    if '--tokenizer-only' in sys.argv:return
    model=OllamaEmbeddings(settings).model_info()
    from rag.ingest import ingest
    present=[(RUNTIME/f'data/index_{strategy}.json').exists() for strategy in ['structure','fixed']]
    if any(present):
        if not all(present):raise RuntimeError('Partial indexes found; inspect before any rebuild.')
        print('Existing indexes preserved. Checking resources, without rebuilding.',flush=True)
    else:ingest(settings,['structure','fixed'])
    from scripts.check_setup import check
    check()
    # Export actual indexed payloads only after successful native ingestion. This
    # lets the separate bridge verify context without opening a locked Qdrant DB.
    from qdrant_client import QdrantClient
    from evidence import sha
    client=QdrantClient(path=str(settings.qdrant_path))
    try:
        for strategy in ['structure','fixed']:
            manifest=json.loads((RUNTIME/f'data/index_{strategy}.json').read_text(encoding='utf-8'))
            points=[];offset=None
            while True:
                batch,offset=client.scroll(collection_name='municipal_'+strategy,limit=100,offset=offset,with_payload=True,with_vectors=False)
                points.extend(p.payload for p in batch)
                if offset is None:break
            if len(points)!=manifest['chunks']:raise RuntimeError('Actual index/catalog count mismatch')
            (RUNTIME/f'data/catalog_{strategy}.json').write_text(json.dumps({'manifest_sha256':sha(manifest),'chunks':points},ensure_ascii=False),encoding='utf-8')
    finally:client.close()
    summary={'scope':'Actual local indexing/resource checks; not generation accuracy',
        'embedding_model':model['name'],'embedding_digest':model['digest'],
        'indexes':{s:json.loads((RUNTIME/f'data/index_{s}.json').read_text(encoding='utf-8')) for s in ['structure','fixed']}}
    # Public manifests omit machine-local storage paths.
    for manifest in summary['indexes'].values():manifest['qdrant_path']='[PROJECT_RUNTIME_QDRANT]'
    (ROOT/'project-docs/integration/knowledge-index-results.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
