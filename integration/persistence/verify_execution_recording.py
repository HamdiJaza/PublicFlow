"""Match a persisted ticket to retained n8n execution/node data. No model calls."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from test_database import sql

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_id')
    args=parser.parse_args()
    if not re.fullmatch(r'RPT-[a-f0-9]{32}',args.report_id):raise SystemExit('Invalid report ID.')
    rows=sql("SELECT jsonb_build_object('execution_id',payload#>>'{provenance,execution_id}','tracking_id',tracking_id) FROM municipal.tickets WHERE report_id='"+args.report_id+"';")
    if len(rows)!=1 or not re.fullmatch(r'\d+',rows[0]['execution_id']):raise SystemExit('No matching ticket execution ID.')
    script=(ROOT/'integration/persistence/inspect_execution.cjs').read_text(encoding='utf-8')
    result=subprocess.run(['docker','exec','-i','municipal-n8n-dev','node','-',rows[0]['execution_id'],args.report_id],
        input=script,text=True,encoding='utf-8',capture_output=True,timeout=30)
    if result.returncode:raise SystemExit('Saved execution verification failed: '+result.stderr.strip())
    proof=json.loads(result.stdout)
    assert proof['final_output']['tracking_id']==rows[0]['tracking_id']
    target=ROOT/'project-docs/integration'/('n8n-recorded-'+args.report_id+'.json')
    target.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:proof[k] for k in ('execution_id','execution_status','execution_url','final_output')}))
    print('Recorded nodes:',len(proof['recorded_nodes']))


if __name__=='__main__':main()
