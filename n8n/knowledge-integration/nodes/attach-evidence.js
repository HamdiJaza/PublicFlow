const x=JSON.parse(JSON.stringify($('Attach Knowledge Response').first().json));
const r=$input.first().json;
x.knowledge_evidence_http={status_code:Number.isInteger(r.statusCode)?r.statusCode:null};
x.knowledge_evidence=r.statusCode===200&&r.body&&typeof r.body==='object'&&!Array.isArray(r.body)?r.body:null;
return [{json:x}];
