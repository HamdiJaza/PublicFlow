const x=$input.first().json, frames=x.vision_frames||[], blockers=[];
const expected=x.submission?.mode==='video'?3:1;
if(frames.length!==expected||new Set(frames.map(f=>f.media_id)).size!==expected)blockers.push('VISION_FRAME_COVERAGE_INCOMPLETE');
if(frames.some(f=>f.gate_2?.checks?.usable_for_routing_and_retrieval!==true))blockers.push('VISION_FRAME_UNUSABLE');
if(new Set(frames.map(f=>f.native?.category)).size!==1)blockers.push('VISION_FRAME_CATEGORY_CONFLICT');
if(new Set(frames.map(f=>f.native?.severity)).size!==1)blockers.push('VISION_FRAME_SEVERITY_CONFLICT');
const warnings=[...new Set(frames.flatMap(f=>f.gate_2?.reason_codes||[]))];
const reasons=[...new Set([...warnings,...blockers])];
x.decision=reasons.length?'REVIEW':'PASS';x.review_reasons.push(...reasons);
x.policy.gate_2={decision:x.decision,reason_codes:reasons,checks:{
  scope:'All required frames have usable native observations and agree on category and severity',
  usable_for_routing_and_retrieval:!blockers.length,uncertainty_retained:true,...x.visual_assessment}};
if(!blockers.length)x.vision=JSON.parse(JSON.stringify(frames[0].native));
x.trace.push({at:new Date().toISOString(),stage:'VISION_FRAME_AGREEMENT',decision:x.decision,reason_codes:reasons});
return [{json:x}];
