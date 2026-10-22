const provenance=x.components.intake.service_reported_provenance;
const extraReasons=[];
if(x.components.intake.provenance_status==='invalid')extraReasons.push('INTAKE_PROVENANCE_INVALID');
if(provenance?.text_provider==='nvidia'){
  if(provenance.normalization!=='French')extraReasons.push('INTAKE_NORMALIZATION_MISMATCH');
  if(!provenance.calls.some(c=>c.stage==='text'&&c.status==='SUCCESS'))extraReasons.push('INTAKE_TEXT_INFERENCE_UNCONFIRMED');
  if(provenance.calls.some(c=>c.inference_mode==='TEST_DOUBLE'))extraReasons.push('INTAKE_TEST_DOUBLE_NOT_REAL_INFERENCE');
  if(x.submission&&provenance.transcription_provider==='nvidia'){
    const expected=x.submission.has_audio===true||(x.submission.mode==='video'&&typeof r?.transcription_video==='string'&&r.transcription_video.trim())?1:0;
    const speech=provenance.calls.filter(c=>c.stage==='transcription'&&c.status==='SUCCESS').length;
    if(speech!==expected)extraReasons.push('INTAKE_SPEECH_INFERENCE_UNCONFIRMED');
  }
}
if(extraReasons.length){
  x.policy.gate_1.reason_codes.push(...extraReasons);x.review_reasons.push(...extraReasons);
  if(x.decision!=='REJECT'){x.decision='REVIEW';x.policy.gate_1.decision='REVIEW';}
  x.trace.push({at:new Date().toISOString(),stage:'INTAKE_PROVIDER_CHECK',decision:x.policy.gate_1.decision,reason_codes:extraReasons});
}
return [{json:x}];
