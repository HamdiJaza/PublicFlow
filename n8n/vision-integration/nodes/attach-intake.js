const x=JSON.parse(JSON.stringify($('Input Check').first().json));
const received=$input.first().json;
const status=Number.isInteger(received.statusCode)?received.statusCode:null;
let native=received.body;
if(typeof native==='string'){try{native=JSON.parse(native);}catch{native=null;}}
const message=JSON.stringify(received.error||'');
x.intake_http={status_code:status,body:native??null,
  transport_error:status===null?(/timed?out|ETIMEDOUT|ESOCKETTIMEDOUT/i.test(message)?'TIMEOUT':'UNAVAILABLE'):null};
x.intake_native=status===200&&native&&typeof native==='object'&&!Array.isArray(native)?native:null;
x.components.intake={execution:status!==null?'responded':'unavailable',inference:'not_independently_verified',api:'POST /analyser'};
const header=received.headers?.['x-intake-provenance'];
if(header!==undefined){
  try{
    const p=JSON.parse(header);
    if(!['gemini','nvidia'].includes(p.text_provider)||!['gemini','nvidia'].includes(p.transcription_provider)||
       !['French','preserve-input-language'].includes(p.normalization)||
       !Number.isInteger(p.provider_call_attempts)||p.provider_call_attempts<0||
       !Array.isArray(p.calls)||p.calls.length>3)throw new Error('invalid');
    if(p.text_provider==='nvidia'&&p.transcription_provider==='nvidia'&&p.provider_call_attempts!==p.calls.length)throw new Error('invalid');
    const calls=p.calls.map(c=>{
      if(!['text','transcription'].includes(c.stage)||c.provider!=='nvidia'||
         c.model!==(c.stage==='text'?'nvidia/nemotron-3.5-lightning-30b-a3b':'openai/whisper-large-v3')||
         !['REAL_PROVIDER','TEST_DOUBLE'].includes(c.inference_mode)||!['SUCCESS','ERROR','ATTEMPTED'].includes(c.status))throw new Error('invalid');
      return {stage:c.stage,provider:c.provider,model:c.model,inference_mode:c.inference_mode,status:c.status,
        ...(c.stage==='text'?{prompt_version:typeof c.prompt_version==='string'?c.prompt_version:null}:{}),
        ...(/^[a-f0-9]{64}$/.test(c.prompt_sha256||'')?{prompt_sha256:c.prompt_sha256}:{}),
        ...(typeof c.elapsed_seconds==='number'&&Number.isFinite(c.elapsed_seconds)?{elapsed_seconds:c.elapsed_seconds}:{})};
    });
    x.components.intake.service_reported_provenance={text_provider:p.text_provider,transcription_provider:p.transcription_provider,
      normalization:p.normalization,...(p.language_scope==='source-report'?{language_scope:p.language_scope}:{}),provider_call_attempts:p.provider_call_attempts,calls};
    x.components.intake.provenance_status='service_reported';
  }catch{x.components.intake.provenance_status='invalid';}
}
x.trace.push({at:new Date().toISOString(),stage:'INTAKE_HTTP',decision:status===200?'RECEIVED':'REVIEW',reason_codes:status===200?[]:[x.intake_http.transport_error==='TIMEOUT'?'INTAKE_TIMEOUT':'INTAKE_HTTP_FAILED']});
return [{json:x}];
