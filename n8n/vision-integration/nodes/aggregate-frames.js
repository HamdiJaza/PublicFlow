// No synthetic combined confidence or invented native response.
const x=$input.first().json, frames=x.vision_frames||[], reasons=[];
const expected=x.submission?.mode==='video'?3:1;
if(frames.length!==expected||new Set(frames.map(f=>f.media_id)).size!==expected)reasons.push('VISION_FRAME_COVERAGE_INCOMPLETE');
if(frames.some(f=>f.gate_2.decision!=='PASS'))reasons.push('VISION_FRAME_REQUIRES_REVIEW');
if(new Set(frames.map(f=>f.native?.category)).size!==1)reasons.push('VISION_FRAME_CATEGORY_CONFLICT');
if(new Set(frames.map(f=>f.native?.severity)).size!==1)reasons.push('VISION_FRAME_SEVERITY_CONFLICT');
x.decision=reasons.length?'REVIEW':'PASS';
x.review_reasons.push(...reasons);
x.policy.gate_2={decision:x.decision,reason_codes:reasons,checks:{scope:'All required frames pass native Gate 2 and agree on category and severity',
  confidence_scope:'No aggregated confidence; native per-frame estimates retained',...x.visual_assessment}};
// Deterministic router consumes an actual response after unanimous agreement.
if(!reasons.length)x.vision=JSON.parse(JSON.stringify(frames[0].native));
x.trace.push({at:new Date().toISOString(),stage:'VISION_FRAME_AGREEMENT',decision:x.decision,reason_codes:reasons});
return [{json:x}];
