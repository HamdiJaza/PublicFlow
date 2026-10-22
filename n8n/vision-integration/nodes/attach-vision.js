const x=JSON.parse(JSON.stringify($('Attach Verified Media').first().json));
const received=$input.first().json;
const status=Number.isInteger(received.statusCode)?received.statusCode:null;
let body=received.body;
if(typeof body==='string'){try{body=JSON.parse(body);}catch{body=null;}}
const message=JSON.stringify(received.error||'');
x.vision_http={status_code:status,transport_error:status===null?(/timed?out|ETIMEDOUT|ESOCKETTIMEDOUT/i.test(message)?'TIMEOUT':'UNAVAILABLE'):null};
x.vision_native=status===200&&body&&typeof body==='object'&&!Array.isArray(body)?body:null;
x.vision=x.vision_native; // Existing deterministic department rules consume this native object.
x.components.vision={execution:status!==null?'responded':'unavailable',inference:'not_independently_verified',api:'POST /vision',declared_model:'qwen2.5vl:3b',declared_prompt_version:'v11'};
x.trace.push({at:new Date().toISOString(),stage:'VISION_HTTP',media_id:x.current_media?.id||null,decision:status===200?'RECEIVED':'REVIEW',reason_codes:status===200?[]:['VISION_HTTP_FAILED']});
return [{json:x}];
