"""Sequential native Intake + unchanged native Vision; unavailable RAG/persistence."""

import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'n8n/intake-integration'))
from build_preparation_workflow import build_preparation


def build():
    workflow=build_preparation()
    workflow['id']='municipalIntakeVisionDev'
    workflow['name']='Municipal - Intake + Vision - DEVELOPMENT ONLY'
    workflow['settings']['executionTimeout']=6600
    nodes={n['name']:n for n in workflow['nodes']}
    config=json.JSONDecoder().raw_decode(nodes['Input Check']['parameters']['jsCode'].split('integration:',1)[1].lstrip())[0]
    nodes['Input Check']['parameters']['jsCode']=(HERE/'nodes/input-multimedia.js').read_text(encoding='utf-8').replace('__INTEGRATION_CONFIG__',json.dumps(config))
    nodes['Gate 1 - Intake']['parameters']['jsCode']=(HERE/'nodes/gate1-multimedia.js').read_text(encoding='utf-8')
    nodes['Citizen Webhook']['parameters']['path']='municipal-intake-vision'
    nodes['Citizen Webhook']['webhookId']='municipal-intake-vision-development'
    for name in ['HTTP Vision','Gate 2 - Vision','Vision PASS?','Department Rules']:
        nodes[name]['disabled']=False
    http=nodes['HTTP Vision']
    http['retryOnFail']=False
    http['onError']='continueRegularOutput'
    for key in ['maxTries','waitBetweenTries']:http.pop(key,None)
    http['parameters']={'method':'POST','url':'http://host.docker.internal:8010/vision',
        'sendBody':True,'contentType':'multipart-form-data','bodyParameters':{'parameters':[
            {'parameterType':'formBinaryData','name':'image','inputDataFieldName':'image'},
            {'parameterType':'formData','name':'report_id','value':'={{ $json.report_id }}'},
            {'parameterType':'formData','name':'description','value':'={{ $json.intake_native.cleaned_text }}'}]},
        'options':{'timeout':2000000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'json'}}}}
    def code(name,filename):
        node={'id':name.lower().replace(' ','-'),'name':name,'type':'n8n-nodes-base.code','typeVersion':2,'position':[1000,0],
              'parameters':{'mode':'runOnceForAllItems','jsCode':(HERE/'nodes'/filename).read_text(encoding='utf-8')}}
        if name in nodes:
            nodes[name].update(node,disabled=False)
        else:
            workflow['nodes'].append(node)
    code('Attach Verified Media','attach-media.js')
    code('Attach Vision Response','attach-vision.js')
    code('Attach Intake Response','attach-intake.js')
    # Native body contract is unchanged. Validate optional service provenance
    # separately; it is reported by Intake, not independent model verification.
    gate1=nodes['Gate 1 - Intake']['parameters']['jsCode']
    extra=(HERE/'nodes/gate1-provider-checks.js').read_text(encoding='utf-8')
    nodes['Gate 1 - Intake']['parameters']['jsCode']=gate1.replace('return [{json:x}];',extra)
    nodes['Gate 2 - Vision']['parameters']={'mode':'runOnceForAllItems','jsCode':(HERE/'nodes/gate2.js').read_text(encoding='utf-8')}
    check=copy.deepcopy(nodes['Intake PASS?']);check.update(id='verified-media-pass',name='Verified Media PASS?')
    workflow['nodes'].append(check)
    workflow['nodes'].append({'id':'read-verified-media','name':'Read Verified Media','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,
        'position':[850,0],'retryOnFail':False,'onError':'continueRegularOutput',
        'credentials':{'httpHeaderAuth':{'id':'municipalVerifiedMediaDev','name':'Municipal verified media (development)'}},
        'parameters':{'method':'POST','url':'http://host.docker.internal:8013/media/resolve',
            'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','sendBody':True,'specifyBody':'json',
            'jsonBody':'={{ {path: $json.intake_native.media[0].path, sha256: $json.intake_native.media[0].sha256} }}',
            'options':{'timeout':15000,'response':{'response':{'fullResponse':True,'neverError':True,'responseFormat':'file','outputPropertyName':'verified_image'}}}}})
    nodes['Downstream unavailable']['parameters']['jsCode']="""const x=$input.first().json;
x.decision='REVIEW';x.review_reasons.push('KNOWLEDGE_AND_PERSISTENCE_NOT_INTEGRATED');
x.trace.push({at:new Date().toISOString(),stage:'DOWNSTREAM_CHECKPOINT',decision:'REVIEW',reason_codes:['KNOWLEDGE_AND_PERSISTENCE_NOT_INTEGRATED']});
return [{json:x}];"""
    response=nodes['Format API Response']['parameters']['jsCode'].replace("orchestrator:'intake-preparation-v1'","orchestrator:'intake-vision-integration-v1'")
    response=response.replace('persisted:false,review_queued:false,','routing:{department:x.department||null},persisted:false,review_queued:false,')
    response=response.replace('Intake development integration only. Downstream agents and ticket storage were not called.','Intake and Vision development integration. Knowledge and ticket storage were not called.')
    nodes['Format API Response']['parameters']['jsCode']=response
    def edge(name):return {'node':name,'type':'main','index':0}
    def link(source,*branches):workflow['connections'][source]={'main':[[edge(n) for n in branch] for branch in branches]}
    link('Intake PASS?',['Read Verified Media'],['Audit Summary'])
    link('Read Verified Media',['Attach Verified Media'])
    link('Attach Verified Media',['Verified Media PASS?'])
    link('Verified Media PASS?',['HTTP Vision'],['Audit Summary'])
    link('HTTP Vision',['Attach Vision Response'])
    link('Attach Vision Response',['Gate 2 - Vision'])
    link('Gate 2 - Vision',['Vision PASS?'])
    link('Vision PASS?',['Department Rules'],['Audit Summary'])
    link('Department Rules',['Downstream unavailable'])
    rows=[['Citizen Webhook','Input Check','Input PASS?','HTTP Intake','Attach Intake Response','Gate 1 - Intake','Intake PASS?'],
          ['Read Verified Media','Attach Verified Media','Verified Media PASS?','HTTP Vision','Attach Vision Response','Gate 2 - Vision','Vision PASS?','Department Rules','Downstream unavailable'],
          ['Audit Summary','Format API Response','Respond to Citizen']]
    for row,names in enumerate(rows):
        for column,name in enumerate(names):
            next(node for node in workflow['nodes'] if node['name']==name)['position']=[column*260,row*320]
    for index,node in enumerate(n for n in workflow['nodes'] if n.get('disabled')):
        node['position']=[index*260,1000]
    from multimedia import extend
    extend(workflow, HERE)
    return workflow


if __name__=='__main__':
    (HERE/'municipal-intake-vision-development.json').write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Built separate Intake + Vision development workflow.')
