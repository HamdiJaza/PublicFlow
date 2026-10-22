const x=$input.first().json;
const r=x.intake_native;
const reasons=[];
const object=v=>v!==null && typeof v==='object' && !Array.isArray(v);
const strings=v=>Array.isArray(v)&&v.every(s=>typeof s==='string');
const meaningful=v=>typeof v==='string'&&v.trim().length>0;
const http=x.intake_http||{};
let decision='REVIEW';
if(http.transport_error) reasons.push(http.transport_error==='TIMEOUT'?'INTAKE_TIMEOUT':'INTAKE_UNAVAILABLE');
else if([400,413,415,422].includes(http.status_code)) {
  decision='REJECT'; reasons.push('INTAKE_INPUT_REJECTED');
} else if(http.status_code!==200) reasons.push('INTAKE_HTTP_FAILED');
else if(!object(r)) reasons.push('INTAKE_INVALID_JSON');
else {
  const textFields=['language','cleaned_text','text_quality','description_image','transcription_audio','transcription_video','pertinence_municipale'];
  if(textFields.some(k=>typeof r[k]!=='string') || !strings(r.avertissements) || !strings(r.images_traitees) || !Array.isArray(r.descriptions_images_video)) reasons.push('INTAKE_NATIVE_SCHEMA_INVALID');
  for(const key of ['audio_direct_hors_sujet','audio_video_hors_sujet','contenu_audio_hors_sujet']) {
    if(r[key]!==null&&typeof r[key]!=='boolean') reasons.push('INTAKE_NATIVE_SCHEMA_INVALID');
  }
  for(const key of ['classification_citoyen','classification_audio','classification_video']) {
    const c=r[key];
    if(c!==null&&(!object(c)||typeof c.pertinent!=='boolean'||!meaningful(c.justification)||!['voirie','dechets','eclairage_public','signalisation','eau_assainissement','espace_vert','securite_urbaine','autre_municipal','hors_sujet','incertain'].includes(c.categorie))) reasons.push('INTAKE_CLASSIFICATION_INVALID');
  }
  if(!['CLEAR','VAGUE','EMPTY'].includes(r.text_quality)) reasons.push('INTAKE_NATIVE_SCHEMA_INVALID');
  if(r.text_quality!=='CLEAR'||!meaningful(r.cleaned_text)||!meaningful(r.language)||r.language==='unknown') reasons.push('INTAKE_TEXT_INCOMPLETE');
  if(r.pertinence_municipale!=='PERTINENTE'||!object(r.classification_citoyen)||r.classification_citoyen.pertinent!==true||['incertain','hors_sujet'].includes(r.classification_citoyen.categorie)) reasons.push('INTAKE_RELEVANCE_UNCLEAR');
  const v=r.validation_multimodale;
  if(typeof r.validation_humaine_requise!=='boolean'||!object(v)||typeof v.validation_humaine_requise!=='boolean'||!meaningful(v.motif)||!strings(v.elements_confirmes)||!strings(v.elements_incoherents)||!Array.isArray(v.evaluations_medias)||!['COHERENTE','PARTIELLEMENT_COHERENTE','INCOHERENTE','INFORMATION_INSUFFISANTE'].includes(v.coherence_multimodale)) reasons.push('INTAKE_VALIDATION_INVALID');
  else {
    if(r.validation_humaine_requise!==false||v.validation_humaine_requise!==false) reasons.push('INTAKE_HUMAN_REVIEW_REQUIRED');
    if(v.coherence_multimodale!=='COHERENTE') reasons.push('INTAKE_COHERENCE_UNCLEAR');
    const media=v.evaluations_medias;
    if(media.length!==1||!object(media[0])||media[0].id_media!=='image_independante'||!meaningful(media[0].justification)||media[0].statut!=='CONFIRME') reasons.push('INTAKE_IMAGE_NOT_CONFIRMED');
  }
  if(r.statut_image!=='CONFIRME'||!meaningful(r.description_image)) reasons.push('INTAKE_IMAGE_NOT_CONFIRMED');
  if(strings(r.avertissements)&&r.avertissements.some(w=>!/^Données masquées \(\d+ email\(s\), \d+ téléphone\(s\)\)\.$/.test(w))) reasons.push('INTAKE_PROCESSING_WARNING');
  const root=(x.integration.trusted_safe_root||'').replace(/\\/g,'/').replace(/\/$/,'');
  const paths=r.images_traitees;
  if(x.integration.privacy_invariant!=='checked_yunet_output_v1'||!root||!strings(paths)||paths.length!==1||paths.some(p=>{
    const normalized=p.replace(/\\/g,'/');
    if(!normalized.startsWith(root+'/'))return true;
    return !/^[a-f0-9]{32}\/image_[a-f0-9]{32}\.png$/.test(normalized.slice(root.length+1));
  })) reasons.push('PRIVACY_PROCESSING_UNVERIFIED');
  if(!reasons.length)decision='PASS';
}
const unique=[...new Set(reasons)];
x.policy.gate_1={decision,reason_codes:unique,checks:{privacy_scope:'Checked local face-processing invariant; not complete PII anonymization',native_response_preserved:object(r)}};
x.decision=decision;
if(decision==='REJECT')x.errors.push(...unique);else x.review_reasons.push(...unique);
x.trace.push({at:new Date().toISOString(),stage:'GATE_1_INTAKE',decision,reason_codes:unique});
return [{json:x}];
