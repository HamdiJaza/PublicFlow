"""Bounded sequential n8n graph; agent implementations remain unchanged."""
import copy


def extend(workflow, here):
    nodes={n['name']:n for n in workflow['nodes']}
    def clone(source,name):
        node=copy.deepcopy(nodes[source]);node.update(name=name,id=name.lower().replace(' ','-'))
        workflow['nodes'].append(node);nodes[name]=node
        return node
    def code(name,script):
        node={'id':name.lower().replace(' ','-'),'name':name,'type':'n8n-nodes-base.code','typeVersion':2,
              'position':[0,0],'parameters':{'mode':'runOnceForAllItems','jsCode':script}}
        workflow['nodes'].append(node);nodes[name]=node
    def condition(name,expression):
        node=clone('Intake PASS?',name)
        node['parameters']['conditions']['conditions'][0]['leftValue']=expression
    def link(source,*branches):
        workflow['connections'][source]={'main':[[{'node':n,'type':'main','index':0} for n in branch] for branch in branches]}

    condition('Video Submission?',"={{ $json.submission.mode === 'video' ? 'PASS' : 'OTHER' }}")
    condition('Audio Submission?',"={{ $json.submission.mode === 'image_audio' ? 'PASS' : 'OTHER' }}")
    for kind,parts in [('Audio',['image','audio']),('Video',['video'])]:
        node=clone('HTTP Intake','HTTP Intake '+kind)
        node['parameters']['bodyParameters']['parameters']=[
            {'parameterType':'formBinaryData','name':part,'inputDataFieldName':part} for part in parts
        ]+[{'parameterType':'formData','name':'texte','value':'={{ $json.original.description }}'}]
    link('Input PASS?',['Video Submission?'],['Audit Summary'])
    link('Video Submission?',['HTTP Intake Video'],['Audio Submission?'])
    link('Audio Submission?',['HTTP Intake Audio'],['HTTP Intake'])
    for name in ['HTTP Intake','HTTP Intake Audio','HTTP Intake Video']:link(name,['Attach Intake Response'])

    code('Aggregate Frames',(here/'nodes/aggregate-frames.js').read_text(encoding='utf-8'))
    condition('All Frames PASS?',"={{ $json.decision }}")
    condition('More Frames?',"={{ $json.submission.mode === 'video' ? 'PASS' : 'OTHER' }}")
    for index in range(1,4):
        suffix='' if index==1 else f' {index}'
        select=f'Select Frame {index}'
        code(select,f"""const x=$input.first().json;
x.current_media=x.intake_native.media[{index-1}];
x.vision_frames=x.vision_frames||[];
x.visual_assessment={{expected_frames:x.submission?.mode==='video'?3:1,attempted_frames:x.vision_frames.length,assessed_frames:x.vision_frames.filter(f=>f.http.status_code===200&&f.native!==null).length,coverage:'INCOMPLETE'}};
return [{{json:x}}];""")
        if index>1:
            for source in ['Read Verified Media','Attach Verified Media','Verified Media PASS?','HTTP Vision','Attach Vision Response','Gate 2 - Vision','Vision PASS?']:
                clone(source,source+suffix)
        read=nodes['Read Verified Media'+suffix]
        read['parameters']['jsonBody']='={{ {path: $json.current_media.path, sha256: $json.current_media.sha256} }}'
        nodes['Attach Verified Media'+suffix]['parameters']['jsCode']=(here/'nodes/attach-media.js').read_text(encoding='utf-8').replace("$('Select Frame 1')",f"$('{select}')")
        nodes['Attach Vision Response'+suffix]['parameters']['jsCode']=(here/'nodes/attach-vision.js').read_text(encoding='utf-8').replace("$('Attach Verified Media')",f"$('Attach Verified Media{suffix}')")
        record=f'Record Frame {index}'
        code(record,(here/'nodes/record-frame.js').read_text(encoding='utf-8'))
        link(select,['Read Verified Media'+suffix])
        link('Read Verified Media'+suffix,['Attach Verified Media'+suffix])
        link('Attach Verified Media'+suffix,['Verified Media PASS?'+suffix])
        link('Verified Media PASS?'+suffix,['HTTP Vision'+suffix],['Audit Summary'])
        link('HTTP Vision'+suffix,['Attach Vision Response'+suffix])
        link('Attach Vision Response'+suffix,['Gate 2 - Vision'+suffix])
        link('Gate 2 - Vision'+suffix,[record])
        link(record,['Vision PASS?'+suffix])
        target='More Frames?' if index==1 else ('Select Frame 3' if index==2 else 'Aggregate Frames')
        link('Vision PASS?'+suffix,[target],['Audit Summary'])
    link('Intake PASS?',['Select Frame 1'],['Audit Summary'])
    link('More Frames?',['Select Frame 2'],['Aggregate Frames'])
    link('Aggregate Frames',['All Frames PASS?'])
    link('All Frames PASS?',['Department Rules'],['Audit Summary'])
    response=nodes['Format API Response']['parameters']['jsCode']
    nodes['Format API Response']['parameters']['jsCode']=response.replace('intake-vision-integration-v1','intake-vision-multimedia-v2').replace('routing:{','visual_assessment:x.visual_assessment||null,routing:{')
    workflow['meta']['multimedia_contract']='image-text | image-audio [+ text] | video [+ text]; native Intake unchanged'
    workflow['meta']['video_policy']='Three sequential frame checks; stop on REVIEW; unanimous category and severity; no combined confidence'
    rows=[['Citizen Webhook','Input Check','Input PASS?','Video Submission?','Audio Submission?','HTTP Intake','Attach Intake Response','Gate 1 - Intake','Intake PASS?'],
          ['HTTP Intake Video','HTTP Intake Audio']]
    for index in range(1,4):
        suffix='' if index==1 else f' {index}'
        rows.append([f'Select Frame {index}','Read Verified Media'+suffix,'Attach Verified Media'+suffix,'Verified Media PASS?'+suffix,
                     'HTTP Vision'+suffix,'Attach Vision Response'+suffix,'Gate 2 - Vision'+suffix,f'Record Frame {index}','Vision PASS?'+suffix]+(['More Frames?'] if index==1 else []))
    rows.append(['Aggregate Frames','All Frames PASS?','Department Rules','Downstream unavailable','Audit Summary','Format API Response','Respond to Citizen'])
    for row,names in enumerate(rows):
        for col,name in enumerate(names):nodes[name]['position']=[col*270,row*300]
    for col,node in enumerate(n for n in workflow['nodes'] if n.get('disabled')):node['position']=[col*270,2100]
