// Appended to the unchanged native Gate 2 checks. REVIEW remains REVIEW.
const gate=x.policy.gate_2;
const onlyUncertainty=gate.reason_codes.length>0&&gate.reason_codes.every(r=>r==='VISION_UNCERTAINTY_REQUIRES_REVIEW');
const validUncertainty=typeof x.vision_native?.uncertainty_reason==='string'&&x.vision_native.uncertainty_reason.trim().length>0;
gate.checks.usable_for_routing_and_retrieval=gate.decision==='PASS'||(onlyUncertainty&&validUncertainty);
gate.checks.continuation_policy='Continue valid, consistent classifications; retain uncertainty for ticket review.';
if(gate.decision==='REVIEW'&&gate.checks.usable_for_routing_and_retrieval){
  x.trace.push({at:new Date().toISOString(),stage:'REVIEW_CONTINUATION',decision:'CONTINUE_WITH_REVIEW',reason_codes:gate.reason_codes});
}
return [{json:x}];
