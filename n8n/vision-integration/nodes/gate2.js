// Native Vision schema; no invented uncertainty boolean, agent version or scores.
const x=$input.first().json, v=x.vision_native, http=x.vision_http||{}, problems=[];
const object=o=>o!==null&&typeof o==='object'&&!Array.isArray(o);
const meaningful=s=>typeof s==='string'&&s.trim().length>0;
const accepted=['ROAD_DAMAGE','STREET_LIGHTING','WASTE','WATER_LEAK'];
const fields=['category','severity','description','evidence','text_image_consistent','confidence','uncertainty_reason','report_id','run_id'];
if(http.transport_error)problems.push(http.transport_error==='TIMEOUT'?'VISION_TIMEOUT':'VISION_UNAVAILABLE');
else if(http.status_code!==200)problems.push('VISION_HTTP_FAILED');
else if(!object(v))problems.push('VISION_INVALID_JSON');
else {
  if(fields.some(k=>!(k in v))||Object.keys(v).some(k=>!fields.includes(k)))problems.push('VISION_SCHEMA_INVALID');
  if(v.report_id!==x.report_id)problems.push('VISION_REPORT_ID_MISMATCH');
  const digest=x.media_transfer?.sha256;
  if(!meaningful(v.run_id)||typeof digest!=='string'||!v.run_id.endsWith('_UPLOAD-'+digest.slice(0,12)))problems.push('VISION_RUN_MEDIA_MISMATCH');
  if(!accepted.includes(v.category))problems.push('VISION_CATEGORY_UNSUPPORTED_OR_UNCLEAR');
  if(!['LOW','MEDIUM','HIGH'].includes(v.severity))problems.push('VISION_SEVERITY_UNCLEAR');
  if(!meaningful(v.description)||v.description.length>600)problems.push('VISION_DESCRIPTION_INVALID');
  if(!Array.isArray(v.evidence)||v.evidence.length===0||v.evidence.length>6||!v.evidence.every(meaningful))problems.push('VISION_EVIDENCE_MISSING');
  if(v.text_image_consistent!==true)problems.push('IMAGE_TEXT_MISMATCH_OR_UNCLEAR');
  if(v.uncertainty_reason!==null)problems.push('VISION_UNCERTAINTY_REQUIRES_REVIEW');
  if(typeof v.confidence!=='number'||!Number.isFinite(v.confidence)||v.confidence<0||v.confidence>1)problems.push('VISION_CONFIDENCE_MISSING_OR_INVALID');
  // No confidence cutoff: the model estimate is uncalibrated, not correctness evidence.
  if(x.media_transfer?.verified!==true)problems.push('VISION_MEDIA_NOT_VERIFIED');
}
x.decision=problems.length?'REVIEW':'PASS';x.review_reasons.push(...problems);
x.policy.gate_2={decision:x.decision,reason_codes:problems,checks:{scope:'Native visual evidence and text consistency',confidence_scope:'Uncalibrated model estimate; no numerical acceptance threshold',native_response_preserved:object(v)}};
x.trace.push({at:new Date().toISOString(),stage:'GATE_2_VISION',media_id:x.current_media?.id||null,decision:x.decision,reason_codes:problems});
return [{json:x}];
