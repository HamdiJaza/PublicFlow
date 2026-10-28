// Display-only English translation of the French Intake summary; never changes gates, routing or the decision.
const x=JSON.parse(JSON.stringify($('Intake PASS?').first().json));
const received=$input.first().json, status=Number.isInteger(received.statusCode)?received.statusCode:null;
let body=received.body;
if(typeof body==='string'){try{body=JSON.parse(body);}catch{body=null;}}
const ok=status===200&&body&&typeof body==='object'&&body.kind==='machine_translation'&&typeof body.en==='string';
x.summary_translation=ok?{en:body.en,provider:body.provider,model:body.model,prompt_version:body.prompt_version}:null;
x.components.translation={execution:ok?'responded':status===null?'unavailable':'failed',scope:'display_only'};
x.trace.push({at:new Date().toISOString(),stage:'SUMMARY_TRANSLATION',decision:ok?'TRANSLATED':'SKIPPED',reason_codes:ok?[]:['TRANSLATION_UNAVAILABLE']});
return [{json:x}];
