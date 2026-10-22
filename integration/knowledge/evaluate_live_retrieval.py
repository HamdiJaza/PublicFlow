"""Run the delivered retrieval evaluation on fresh real indexes, preserving references."""
from datetime import datetime,timezone
import json
import sys
from common import ROOT,RUNTIME,configure


def main():
    configure();sys.path.insert(0,str(RUNTIME))
    from config import Settings
    from evaluation.evaluate_retrieval import live,summarize
    target=ROOT/'project-docs/integration/knowledge-live-retrieval-results.json'
    if target.exists():raise SystemExit('Existing real retrieval report preserved; no repeat evaluation made.')
    rows,protocol=live(Settings.from_env())
    # Preserve exact expected documents, excluded-source coverage failures, ranks
    # and actual scores. Public report needs no local paths or full source texts.
    for row in rows:
        row['candidates']=[{k:hit[k] for k in ['chunk_id','doc_id','url','score','rank']} for hit in row['candidates']]
    for manifest in protocol['manifests'].values():manifest['qdrant_path']='[PROJECT_RUNTIME_QDRANT]'
    report={**protocol,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'score_threshold':.4,
        'metrics':summarize(rows),'results':rows,'generation_calls':0}
    with target.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    print(json.dumps({'report':target.relative_to(ROOT).as_posix(),'cases':len(rows),'metrics':report['metrics']}))


if __name__=='__main__':main()
