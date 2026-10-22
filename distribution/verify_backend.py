"""Real n8n/DB check with intentionally invalid input; no AI/provider calls."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
base = 'http://127.0.0.1:' + os.getenv('MUNICIPAL_N8N_PORT', '5679')
report_id = 'RPT-' + uuid.uuid4().hex
body = json.dumps({'report_id': report_id, 'description': 'PACKAGE INVALID INPUT TEST: no media attached'}).encode()


def post():
    request = urllib.request.Request(base + '/webhook/municipal-ticket-development', data=body,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


first, second = post(), post()
assert first['persisted'] is True and first['decision'] == 'REJECT', first
assert second['persisted'] is True and second['ticket']['tracking_id'] == first['ticket']['tracking_id']
pg = os.getenv('MUNICIPAL_POSTGRES_CONTAINER', 'municipalite-auto-postgres')
sql = "SELECT json_build_object('tickets',count(*),'execution_id',min(payload#>>'{provenance,execution_id}')) FROM municipal.tickets WHERE report_id='" + report_id + "';"
result = subprocess.run(['docker', 'exec', '-i', pg, 'psql', '-X', '-tA', '-U', 'municipal_admin', '-d',
                         'municipal_tickets', '-v', 'ON_ERROR_STOP=1'], input=sql, capture_output=True, text=True)
assert result.returncode == 0, 'SQL verification failed'
database = json.loads(result.stdout)
assert database['tickets'] == 1
time.sleep(1)
script = r"""
const sqlite=require(require.resolve('sqlite3',{paths:['/usr/local/lib/node_modules/n8n']}));
const flatted=require(require.resolve('flatted',{paths:['/usr/local/lib/node_modules/n8n']}));
const db=new sqlite.Database('/home/node/.n8n/database.sqlite',sqlite.OPEN_READONLY);
db.get('SELECT e.status,e.finished,d.data FROM execution_entity e JOIN execution_data d ON d.executionId=e.id WHERE e.id=?',
 [process.argv[2]],(error,row)=>{
  if(error||!row||row.status!=='success'||!row.finished)throw Error('Missing finished execution');
  const runs=flatted.parse(row.data).resultData.runData;
  for(const name of ['Citizen Webhook','Input Check','Persist Ticket','Confirm Persistence','Respond to Citizen'])
    if(!runs[name]?.length)throw Error('Missing node: '+name);
  if(runs['HTTP Intake']?.length)throw Error('Invalid-input test unexpectedly called Intake');
  console.log(JSON.stringify({status:row.status,recorded_nodes:Object.keys(runs)}));db.close();
 });
"""
result = subprocess.run(['docker', 'exec', '-i', os.getenv('MUNICIPAL_N8N_CONTAINER', 'municipalite-auto-n8n'),
                         'node', '-', database['execution_id']], input=script, capture_output=True, text=True)
assert result.returncode == 0, 'n8n saved execution verification failed'
execution = json.loads(result.stdout)
with urllib.request.urlopen(base + '/webhook/municipal-ticket-status?tracking_id=' + first['ticket']['tracking_id']) as response:
    lookup = json.load(response)
assert lookup['ticket']['tracking_id'] == first['ticket']['tracking_id']
proof = {'scope': 'Fresh Windows package, actual n8n/SQL; intentionally invalid input; no AI inference',
         'persisted_reject': True, 'duplicate_created': False, 'ticket_lookup_verified': True,
         'recorded_execution': execution, 'report_id': report_id}
target = ROOT / '.runtime/distribution/backend-validation.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof, indent=2))
