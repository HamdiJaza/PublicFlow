const x=JSON.parse(JSON.stringify($('Prepare Knowledge Request').first().json));
const r=$input.first().json,status=Number.isInteger(r.statusCode)?r.statusCode:null;
let body=r.body;if(typeof body==='string'){try{body=JSON.parse(body);}catch{body=null;}}
const message=JSON.stringify(r.error||'');
x.knowledge_http={status_code:status,transport_error:status===null?(/timed?out|ETIMEDOUT|ESOCKETTIMEDOUT/i.test(message)?'TIMEOUT':'UNAVAILABLE'):null};
x.knowledge_native=status===200&&body&&typeof body==='object'&&!Array.isArray(body)?body:null;
x.knowledge_receipt={id:r.headers?.['x-knowledge-receipt']||null,sha256:r.headers?.['x-knowledge-receipt-sha256']||null};
x.components.knowledge={execution:status!==null?'responded':'unavailable',inference:'not_verified',api:'POST /knowledge'};
x.decision=status===200&&x.knowledge_native&&/^[a-f0-9]{32}$/.test(x.knowledge_receipt.id||'')&&/^[a-f0-9]{64}$/.test(x.knowledge_receipt.sha256||'')?'PASS':'REVIEW';
x.trace.push({at:new Date().toISOString(),stage:'KNOWLEDGE_HTTP',decision:status===200?'RECEIVED':'REVIEW',reason_codes:status===200?[]:[x.knowledge_http.transport_error==='TIMEOUT'?'KNOWLEDGE_TIMEOUT':'KNOWLEDGE_HTTP_FAILED']});
return [{json:x}];
