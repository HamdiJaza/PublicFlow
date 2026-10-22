"""Bounded outage/restart test for the isolated development ticket database.

Requires explicit permission to stop this development service. Makes no model
calls; the test submission is invalid before any agent is called. Always starts
the same database again in finally. Never removes containers, volumes or data.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid

import httpx

ROOT=Path(__file__).resolve().parents[2]
NAME='municipal-ticket-postgres-dev'
BASE='http://127.0.0.1:5679/webhook/'


def main():
    for path in (ROOT/'.runtime/portal/jobs').glob('RPT-*.json'):
        if json.loads(path.read_text(encoding='utf-8')).get('state') in ('queued','running'):
            raise SystemExit('Active portal job; outage check skipped without stopping anything.')
    proof=json.loads((ROOT/'.runtime/persistence/concurrency-proof.json').read_text(encoding='utf-8'))
    report={'scope':'Real n8n/PostgreSQL outage and restart with labelled invalid input; no AI calls.',
            'started_at':datetime.now(timezone.utc).isoformat()}
    with httpx.Client(timeout=30,trust_env=False) as c:
        before=c.get(BASE+'municipal-ticket-status',params={'tracking_id':proof['tracking_id']})
        before.raise_for_status()
        try:
            subprocess.run(['docker','stop',NAME],check=True,capture_output=True,timeout=30)
            status=c.get(BASE+'municipal-ticket-status',params={'tracking_id':proof['tracking_id']})
            report['lookup_outage']={'http_status':status.status_code,'body':status.json()}
            assert status.status_code==503 and status.json()['ticket'] is None
            result=c.post(BASE+'municipal-ticket-development',data={
                'report_id':'TEST-DB-OFFLINE-'+uuid.uuid4().hex,
                'description':'SYNTHETIC no-media input during database outage; no agents called'})
            report['save_outage']={'http_status':result.status_code,'body':result.json()}
            assert result.status_code==503
            assert result.json()['persisted'] is False and result.json()['ticket'] is None
            assert result.json()['workflow_status']=='FAILED'
            assert all(result.json()['components'][k]['execution']=='not_called' for k in ('intake','vision','knowledge'))
        finally:
            subprocess.run(['docker','start',NAME],check=True,capture_output=True,timeout=30)
        for _ in range(30):
            after=c.get(BASE+'municipal-ticket-status',params={'tracking_id':proof['tracking_id']})
            if after.status_code==200:break
            time.sleep(.5)
        after.raise_for_status()
        assert after.json()['ticket']==before.json()['ticket']
        report['same_ticket_survived_restart']=True
        report['tracking_id_checked']=proof['tracking_id']
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (ROOT/'project-docs/integration/completion-database-outage-20261018.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Verified: failed writes never claim persistence; lookup reports database unavailable; committed ticket survives restart.')


if __name__=='__main__':main()
