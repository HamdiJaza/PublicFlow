const x=$input.first().json;
const gates=['gate_1','gate_2','gate_3'];
x.review_reasons=[...new Set(x.review_reasons||[])];x.errors=[...new Set(x.errors||[])];
const rejected=x.decision==='REJECT'||x.trace.some(s=>s.stage==='INPUT_CHECK'&&s.decision==='REJECT');
if(!/^[A-Za-z0-9_-]{3,64}$/.test(x.report_id||'')){
  x.report_id='REJECTED-'+String($execution.id);
}
for(const key of gates)if(!x.policy[key]){
  x.policy[key]={decision:'NOT_RUN',reason_codes:['UPSTREAM_RESULT_UNUSABLE']};
}
x.decision=rejected?'REJECT':gates.every(k=>x.policy[k]?.decision==='PASS')&&!x.review_reasons.length?'PASS':'REVIEW';
const usable=x.policy.gate_2?.checks?.usable_for_routing_and_retrieval===true;
x.priority=usable&&['LOW','MEDIUM','HIGH'].includes(x.vision?.severity)?x.vision.severity:null;
x.trace.push({at:new Date().toISOString(),stage:'TICKET_ASSEMBLY',decision:x.decision,reason_codes:x.review_reasons});
const knowledge=x.knowledge_native||null, verified=x.policy.gate_3?.decision==='PASS';
x.persistence_request={
  report_id:x.report_id,decision:x.decision,
  input_identity:{original:x.original,media:(x.intake_native?.media||[]).map(m=>({id:m.id,sha256:m.sha256}))},
  summary:x.intake_native?.cleaned_text||null,location:x.original?.location||null,
  category:usable?x.vision.category:null,severity:usable?x.vision.severity:null,
  department:usable?x.department||null:null,organisation:usable?x.organisation||null:null,priority:x.priority,priority_rule:'severity_to_priority_v1',
  review_reasons:x.review_reasons,errors:x.errors,policy:x.policy,trace:x.trace,components:x.components,
  vision_frames:(x.vision_frames||[]).map(f=>({media_id:f.media_id,sha256:f.sha256,native:f.native,gate_2:f.gate_2})),
  summary_translation:x.summary_translation||null,
  knowledge:{answer_found:knowledge?.answer_found===true,verified,
    procedure:verified?knowledge.procedure:null,deadline:verified?knowledge.deadline:null,
    sources:x.knowledge_evidence?.receipt_verified===true&&Array.isArray(knowledge?.sources)?knowledge.sources:[],
    native:knowledge,evidence:x.knowledge_evidence||null,request:x.knowledge_request||null},
  provenance:{workflow:'municipal-completion-v1',execution_id:String($execution.id)}
};
return [{json:x}];
