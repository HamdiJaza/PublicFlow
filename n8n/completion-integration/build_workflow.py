"""Complete automatic processing; preserve strict prior workflow and native agents."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def build():
    spec=importlib.util.spec_from_file_location('previous_builder',ROOT/'n8n/knowledge-integration/build_workflow.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    w=previous.build()
    w.update(id='municipalCompletionDev',name='Municipalité Automatisée - Traitement automatique complet + PostgreSQL')
    # Keep real webhook runs inspectable in n8n's Executions view for the demo.
    w['settings'].update(saveDataSuccessExecution='all',saveDataErrorExecution='all',
                         saveManualExecutions=True,saveExecutionProgress=True)
    nodes={n['name']:n for n in w['nodes']}
    nodes['Citizen Webhook']['parameters']['path']='municipal-ticket-development'
    nodes['Citizen Webhook']['webhookId']='municipal-ticket-development'
    def code(name,file):
        n=nodes.get(name,{'id':name.lower().replace(' ','-'),'name':name,'type':'n8n-nodes-base.code','typeVersion':2,'position':[0,0]})
        n['parameters']={'mode':'runOnceForAllItems','jsCode':(HERE/'nodes'/file).read_text(encoding='utf-8')}
        if name not in nodes:w['nodes'].append(n);nodes[name]=n
    def link(name,*branches):
        w['connections'][name]={'main':[[{'node':target,'type':'main','index':0} for target in branch] for branch in branches]}
    for suffix in ['', ' 2',' 3']:
        gate=nodes['Gate 2 - Vision'+suffix]['parameters']
        gate['jsCode']=gate['jsCode'].replace('return [{json:x}];','')+(HERE/'nodes/continuation.js').read_text(encoding='utf-8')
        nodes['Vision PASS?'+suffix]['parameters']['conditions']['conditions'][0]['leftValue']="={{ $json.policy.gate_2.checks.usable_for_routing_and_retrieval ? 'PASS' : 'BLOCK' }}"
    code('Aggregate Frames','aggregate.js')
    nodes['All Frames PASS?']['parameters']['conditions']['conditions'][0]['leftValue']="={{ $json.policy.gate_2.checks.usable_for_routing_and_retrieval ? 'PASS' : 'BLOCK' }}"
    prepare=nodes['Prepare Knowledge Request']['parameters']['jsCode']
    prepare=prepare.replace("x.policy.gate_2?.decision!=='PASS'","x.policy.gate_2?.checks?.usable_for_routing_and_retrieval!==true")
    nodes['Prepare Knowledge Request']['parameters']['jsCode']=prepare
    code('Assemble Ticket','finalize.js');code('Confirm Persistence','persisted.js');code('Format API Response','response.js')
    # All early outcomes and both RAG outcomes finish through one atomic save.
    for source,connection in list(w['connections'].items()):
        for branch in connection['main']:
            for edge in branch:
                if edge['node'] in ['Audit Summary','Downstream unavailable']:edge['node']='Assemble Ticket'
    for old in ['Audit Summary','Downstream unavailable']:
        nodes[old]['disabled']=True;w['connections'].pop(old,None)
    pg={'id':'persist-ticket','name':'Persist Ticket','type':'n8n-nodes-base.postgres','typeVersion':2.6,
        'position':[300,2450],'retryOnFail':False,'onError':'continueRegularOutput',
        'credentials':{'postgres':{'id':'municipalTicketsDev','name':'Municipal PostgreSQL tickets (development)'}},
        'parameters':{'operation':'executeQuery','query':'SELECT municipal.save_report($1::jsonb) AS saved;',
            'options':{'queryReplacement':'={{ [JSON.stringify($json.persistence_request)] }}','connectionTimeout':5,'queryBatching':'single'}}}
    w['nodes'].append(pg);nodes[pg['name']]=pg
    link('Assemble Ticket',['Persist Ticket']);link('Persist Ticket',['Confirm Persistence']);link('Confirm Persistence',['Format API Response'])
    link('Format API Response',['Respond to Citizen'])
    for i,name in enumerate(['Assemble Ticket','Persist Ticket','Confirm Persistence','Format API Response','Respond to Citizen']):nodes[name]['position']=[i*300,2450]
    # Read-only status webhook; UUID lookup is parameterized and returns no private agent traces.
    lookup=copy.deepcopy(pg);lookup.update(id='lookup-ticket',name='Lookup Ticket',position=[300,3100])
    lookup['parameters']['query']='SELECT municipal.ticket_status($1::text) AS ticket;'
    lookup['parameters']['options']['queryReplacement']="={{ [String($json.query?.tracking_id || '')] }}"
    w['nodes'].extend([
      {'id':'ticket-status-webhook','name':'Ticket Status Webhook','type':'n8n-nodes-base.webhook','typeVersion':2,
       'webhookId':'municipal-ticket-status','position':[0,3100],
       'parameters':{'path':'municipal-ticket-status','httpMethod':'GET','responseMode':'responseNode','options':{}}},lookup,
      {'id':'ticket-status-response','name':'Ticket Status Response','type':'n8n-nodes-base.respondToWebhook','typeVersion':1.4,'position':[600,3100],
       'parameters':{'respondWith':'json','responseBody':"={{ {ticket:$json.ticket || null,error:$json.error?'DATABASE_UNAVAILABLE':null} }}",'options':{'responseCode':"={{ $json.error ? 503 : $json.ticket ? 200 : 404 }}"}}}])
    link('Ticket Status Webhook',['Lookup Ticket']);link('Lookup Ticket',['Ticket Status Response'])
    w['meta']['review_policy']='Usable uncertainty continues to RAG; quality decisions retained; every outcome persists as a ticket/status.'
    w['meta']['video_policy']='Three sequential frames; valid uncertain frames continue; conflicting or invalid observations are saved for review.'
    return w


if __name__=='__main__':
    (HERE/'municipal-completion-development.json').write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Built separate completion workflow; strict archived development exports preserved.')
