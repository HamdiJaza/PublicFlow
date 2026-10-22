const x=$input.first().json;
x.decision='REVIEW';
x.review_reasons.push('DOWNSTREAM_NOT_INTEGRATED');
x.trace.push({at:new Date().toISOString(),stage:'DOWNSTREAM_CHECKPOINT',decision:'REVIEW',reason_codes:['DOWNSTREAM_NOT_INTEGRATED']});
return [{json:x}];
