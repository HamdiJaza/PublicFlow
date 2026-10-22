const x=JSON.parse(JSON.stringify($('Input Check').first().json));
const received=$input.first().json;
const status=Number.isInteger(received.statusCode)?received.statusCode:null;
let native=received.body;
if(typeof native==='string'){try{native=JSON.parse(native);}catch{native=null;}}
const message=JSON.stringify(received.error||'');
x.intake_http={status_code:status,body:native??null,
  transport_error:status===null?(/timed?out|ETIMEDOUT|ESOCKETTIMEDOUT/i.test(message)?'TIMEOUT':'UNAVAILABLE'):null};
x.intake_native=status===200 && native && typeof native==='object' && !Array.isArray(native)?native:null;
x.components.intake={execution:status!==null?'responded':'unavailable',inference:'not_independently_verified',api:'POST /analyser'};
x.trace.push({at:new Date().toISOString(),stage:'INTAKE_HTTP',decision:status===200?'RECEIVED':'REVIEW',reason_codes:status===200?[]:[x.intake_http.transport_error==='TIMEOUT'?'INTAKE_TIMEOUT':'INTAKE_HTTP_FAILED']});
return [{json:x}];
