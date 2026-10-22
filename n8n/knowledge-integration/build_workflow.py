"""New development workflow; preserve the validated Intake/Vision export unchanged."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def build():
    workflow=json.loads((ROOT/'n8n/vision-integration/municipal-intake-vision-development.json').read_text(encoding='utf-8'))
    workflow['id']='municipalKnowledgeIntegrationDev'
    workflow['name']='Municipal - Intake + Vision + Knowledge - DEVELOPMENT ONLY'
    workflow['active']=False;workflow['pinData']={}
    workflow['settings']['executionTimeout']=7200
    nodes={n['name']:n for n in workflow['nodes']}
    # Rebind only this development copy; the verified upstream export remains intact.
    input_code=nodes['Input Check']['parameters']['jsCode']
    before,encoded=input_code.split('integration:',1)
    config,end=json.JSONDecoder().raw_decode(encoded.lstrip())
    config.update(trusted_safe_root=(ROOT/'.runtime/intake/safe').as_posix(),
        local_source_sha256=hashlib.sha256(b''.join(path.read_bytes() for path in
            sorted((ROOT/'intake-agent/local_intake').glob('*.py')))).hexdigest())
    nodes['Input Check']['parameters']['jsCode']=before+'integration:'+json.dumps(config)+encoded.lstrip()[end:]
    nodes['Citizen Webhook']['parameters']['path']='municipal-full-development'
    nodes['Citizen Webhook']['webhookId']='municipal-full-development'
    def add(node):workflow['nodes'].append(node);nodes[node['name']]=node
    def code(name,filename):
        params={'mode':'runOnceForAllItems','jsCode':(HERE/'nodes'/filename).read_text(encoding='utf-8')}
        if name in nodes:nodes[name].update(parameters=params,disabled=False)
        else:add({'id':name.lower().replace(' ','-'),'name':name,'type':'n8n-nodes-base.code','typeVersion':2,'position':[0,0],'parameters':params})
    def condition(name):
        node=copy.deepcopy(nodes['Intake PASS?']);node.update(id=name.lower().replace(' ','-'),name=name,disabled=False);add(node)
    def link(source,*branches):
        workflow['connections'][source]={'main':[[{'node':n,'type':'main','index':0} for n in branch] for branch in branches]}
    for name,filename in [('Prepare Knowledge Request','prepare.js'),('Attach Knowledge Response','attach.js'),
                           ('Attach Knowledge Evidence','attach-evidence.js'),('Gate 3 - Sources','gate3.js')]:code(name,filename)
    condition('Knowledge Request PASS?');condition('Knowledge Receipt Available?')
    nodes['Sources PASS?']['disabled']=False
    nodes['HTTP Knowledge'].update(disabled=False,retryOnFail=False,onError='continueRegularOutput')
    for key in ['maxTries','waitBetweenTries']:nodes['HTTP Knowledge'].pop(key,None)
    nodes['HTTP Knowledge']['parameters']={'method':'POST','url':'http://host.docker.internal:8020/knowledge','sendBody':True,'specifyBody':'json',
        'jsonBody':'={{ $json.knowledge_request }}','options':{'timeout':420000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}}
    add({'id':'read-knowledge-evidence','name':'Read Knowledge Evidence','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[0,0],
        'retryOnFail':False,'onError':'continueRegularOutput','credentials':{'httpHeaderAuth':{'id':'municipalKnowledgeEvidenceDev','name':'Municipal Knowledge evidence (development)'}},
        'parameters':{'method':'POST','url':'http://host.docker.internal:8021/evidence/verify','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
            'sendBody':True,'specifyBody':'json','jsonBody':'={{ {receipt_id:$json.knowledge_receipt.id,receipt_sha256:$json.knowledge_receipt.sha256,native_request:$json.knowledge_request,native_response:$json.knowledge_native} }}',
            'options':{'timeout':15000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}}})
    nodes['Downstream unavailable']['parameters']['jsCode']="""const x=$input.first().json;
x.decision='REVIEW';x.review_reasons.push('PERSISTENCE_NOT_INTEGRATED');
x.trace.push({at:new Date().toISOString(),stage:'PERSISTENCE_CHECKPOINT',decision:'REVIEW',reason_codes:['PERSISTENCE_NOT_INTEGRATED']});
return [{json:x}];"""
    response=nodes['Format API Response']['parameters']['jsCode']
    response=response.replace('intake-vision-multimedia-v2','intake-vision-knowledge-v1')
    response=response.replace('Knowledge and ticket storage were not called.','Knowledge runs only after validated upstream results. Ticket storage is unavailable.')
    nodes['Format API Response']['parameters']['jsCode']=response
    link('Department Rules',['Prepare Knowledge Request'])
    link('Prepare Knowledge Request',['Knowledge Request PASS?'])
    link('Knowledge Request PASS?',['HTTP Knowledge'],['Audit Summary'])
    link('HTTP Knowledge',['Attach Knowledge Response'])
    link('Attach Knowledge Response',['Knowledge Receipt Available?'])
    link('Knowledge Receipt Available?',['Read Knowledge Evidence'],['Gate 3 - Sources'])
    link('Read Knowledge Evidence',['Attach Knowledge Evidence'])
    link('Attach Knowledge Evidence',['Gate 3 - Sources'])
    link('Gate 3 - Sources',['Sources PASS?'])
    link('Sources PASS?',['Downstream unavailable'],['Audit Summary'])
    workflow['connections'].pop('Mock Ticket Creation',None)
    workflow['meta']['knowledge_contract']='POST /knowledge; native JSON and v4_grounded unchanged; receipt headers are integration-only'
    workflow['meta']['knowledge_scope']='Commune de Tunis (user confirmed); no missing report location is inferred'
    workflow['meta']['knowledge_gate']='Actual indexed context and conservative verbatim support; paraphrases, refusals, deadlines or unverified evidence require REVIEW'
    row=['Prepare Knowledge Request','Knowledge Request PASS?','HTTP Knowledge','Attach Knowledge Response','Knowledge Receipt Available?',
         'Read Knowledge Evidence','Attach Knowledge Evidence','Gate 3 - Sources','Sources PASS?','Downstream unavailable']
    for col,name in enumerate(row):nodes[name]['position']=[col*270,2100]
    for col,name in enumerate(['Audit Summary','Format API Response','Respond to Citizen']):nodes[name]['position']=[col*270,2450]
    for col,node in enumerate(n for n in workflow['nodes'] if n.get('disabled')):node['position']=[col*270,2800]
    return workflow


if __name__=='__main__':
    (HERE/'municipal-knowledge-development.json').write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Built separate native Knowledge integration workflow; existing Intake/Vision workflow preserved.')
