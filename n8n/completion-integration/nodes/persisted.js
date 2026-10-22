const x=JSON.parse(JSON.stringify($('Assemble Ticket').first().json));
const received=$input.first().json, s=received.saved;
const matched=s&&s.persisted===true&&s.report_id===x.report_id&&
  /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(s.tracking_id||'')&&['PASS','REVIEW','REJECT'].includes(s.decision)&&
  ['OPEN','NEEDS_REVIEW','IN_PROGRESS','RESOLVED','REJECTED'].includes(s.status)&&typeof s.review_queued==='boolean';
x.persisted=Boolean(matched);x.review_queued=matched?s.review_queued:false;x.ticket=matched?s:null;
x.workflow_status=matched?'COMPLETED':'FAILED';
if(matched)x.decision=s.decision;
else {if(x.decision!=='REJECT')x.decision='REVIEW';x.review_reasons.push('PERSISTENCE_FAILED_OR_UNCONFIRMED');}
x.components.persistence={execution:matched?'committed':'failed_or_unconfirmed',database:'PostgreSQL',deduplicated:matched?s.deduplicated:false};
x.trace.push({at:new Date().toISOString(),stage:'POSTGRES_PERSISTENCE',decision:matched?'COMMITTED':'FAILED',reason_codes:matched?[]:['PERSISTENCE_FAILED_OR_UNCONFIRMED']});
return [{json:x}];
