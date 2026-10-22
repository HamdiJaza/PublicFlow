// Preparation evidence only; never classify the incident in Intake/Gate 1.
const x=$input.first().json,r=x.intake_native,http=x.intake_http||{},reasons=[];
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const meaningful=v=>typeof v==='string'&&v.trim().length>0;
const strings=v=>Array.isArray(v)&&v.every(s=>typeof s==='string');
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const video=x.submission?.mode==='video',audio=x.submission?.has_audio===true;
let decision='REVIEW';
if(http.transport_error)reasons.push(http.transport_error==='TIMEOUT'?'INTAKE_TIMEOUT':'INTAKE_UNAVAILABLE');
else if([400,413,415,422].includes(http.status_code)){decision='REJECT';reasons.push('INTAKE_INPUT_REJECTED');}
else if(http.status_code!==200)reasons.push('INTAKE_HTTP_FAILED');
else if(!object(r))reasons.push('INTAKE_INVALID_JSON');
else{
  const fields=['schema_version','language','cleaned_text','text_quality','transcription_audio','transcription_video','media','preparation_status','processing_errors','avertissements'];
  if(r.schema_version!=='intake-preparation-v1'||fields.some(k=>!(k in r))||Object.keys(r).some(k=>!fields.includes(k))||
    !['READY','REVIEW'].includes(r.preparation_status)||!strings(r.processing_errors)||!strings(r.avertissements)||
    typeof r.transcription_audio!=='string'||typeof r.transcription_video!=='string'||!['CLEAR','VAGUE','EMPTY'].includes(r.text_quality))reasons.push('INTAKE_PREPARATION_SCHEMA_INVALID');
  if(r.preparation_status!=='READY'||!strings(r.processing_errors)||r.processing_errors.length)reasons.push('INTAKE_PREPARATION_INCOMPLETE');
  if(r.text_quality!=='CLEAR'||!meaningful(r.cleaned_text)||!['fr','en','ar','mixed'].includes(r.language))reasons.push('INTAKE_TEXT_INCOMPLETE');
  if(audio&&!meaningful(r.transcription_audio))reasons.push('INTAKE_AUDIO_TRANSCRIPT_REQUIRED');
  if((!audio&&r.transcription_audio!=='')||(!video&&r.transcription_video!==''))reasons.push('INTAKE_UNEXPECTED_TRANSCRIPT');
  if(strings(r.avertissements)&&r.avertissements.some(w=>!/^Données masquées \(\d+ email\(s\), \d+ téléphone\(s\)\)\.$/.test(w)))reasons.push('INTAKE_PROCESSING_WARNING');
  const root=(x.integration.trusted_safe_root||'').replace(/\\/g,'/').replace(/\/$/,'');
  const expected=video?3:1,media=r.media;
  if(!Array.isArray(media)||media.length!==expected)reasons.push('INTAKE_PREPARED_MEDIA_REQUIRED');
  if(Array.isArray(media)){
    const paths=new Set();let requestDirectory=null;
    for(const [index,m] of media.entries()){
      const p=object(m)&&m.face_processing;
      const path=object(m)&&typeof m.path==='string'?m.path.replace(/\\/g,'/'):'';
      if(!object(m)||m.id!==(video?'image_video_'+(index+1):'image_independante')||m.source!==(video?'video':'image'))reasons.push('INTAKE_PREPARED_MEDIA_REQUIRED');
      if(x.integration.privacy_invariant!=='checked_yunet_output_v1'||!root||!path.startsWith(root+'/')||
        !/^[a-f0-9]{32}\/image_[a-f0-9]{32}\.png$/.test(path.slice(root.length+1))||
        !object(p)||p.detector!=='YuNet'||p.detector_completed!==true||p.write_and_decode_verified!==true||
        !Number.isInteger(p.faces_detected)||p.faces_detected<0||!hash(m.sha256)||p.sha256!==m.sha256||
        !hash(p.model_sha256)||!hash(x.integration.yunet_model_sha256)||p.model_sha256!==x.integration.yunet_model_sha256)reasons.push('PRIVACY_PROCESSING_UNVERIFIED');
      const directory=path.slice(root.length+1).split('/')[0];
      if(paths.has(path)||(requestDirectory!==null&&directory!==requestDirectory))reasons.push('INTAKE_MEDIA_ASSOCIATION_INVALID');
      paths.add(path);requestDirectory=directory;
    }
  }
  // A silent video may have no transcript. Intake must still provide usable text.
  if(!reasons.length)decision='PASS';
}
const unique=[...new Set(reasons)];
x.policy.gate_1={decision,reason_codes:unique,checks:{scope:'Text, speech and required visual preparation only',
  privacy_scope:'Checked local face-processing evidence; not complete PII anonymization',native_response_preserved:object(r)}};
x.decision=decision;
if(decision==='REJECT')x.errors.push(...unique);else x.review_reasons.push(...unique);
x.trace.push({at:new Date().toISOString(),stage:'GATE_1_PREPARATION',decision,reason_codes:unique});
return [{json:x}];
