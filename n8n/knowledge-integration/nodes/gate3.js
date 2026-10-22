// Deterministic source/context checks. Scores are retrieval similarities, not truth probabilities.
const x=$input.first().json,k=x.knowledge_native,http=x.knowledge_http||{},e=x.knowledge_evidence,reasons=[];
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const meaningful=v=>typeof v==='string'&&v.trim().length>0;
if(http.transport_error)reasons.push(http.transport_error==='TIMEOUT'?'KNOWLEDGE_TIMEOUT':'KNOWLEDGE_UNAVAILABLE');
else if(http.status_code!==200)reasons.push(http.status_code===503?'KNOWLEDGE_NOT_READY_OR_BUSY':http.status_code===422?'KNOWLEDGE_CONTRACT_REJECTED':'KNOWLEDGE_HTTP_FAILED');
else if(!object(k))reasons.push('KNOWLEDGE_INVALID_JSON');
else{
  const fields=['procedure','deadline','answer_found','sources'];
  if(fields.some(f=>!(f in k))||Object.keys(k).some(f=>!fields.includes(f))||typeof k.answer_found!=='boolean'||
    (k.procedure!==null&&!meaningful(k.procedure))||(k.deadline!==null&&!meaningful(k.deadline))||!Array.isArray(k.sources))reasons.push('KNOWLEDGE_NATIVE_SCHEMA_INVALID');
  if(k.answer_found!==true){
    reasons.push('KNOWLEDGE_NO_SUPPORTED_ANSWER');
    if(k.procedure!==null||k.deadline!==null||(Array.isArray(k.sources)&&k.sources.length))reasons.push('KNOWLEDGE_REFUSAL_INCONSISTENT');
  }else{
    if(!meaningful(k.procedure)||k.procedure.length>8000||['null','none'].includes(k.procedure.trim().toLowerCase()))reasons.push('KNOWLEDGE_PROCEDURE_INVALID');
    if(!Array.isArray(k.sources)||k.sources.length<1||k.sources.length>3)reasons.push('KNOWLEDGE_SOURCES_REQUIRED');
    if(Array.isArray(k.sources)){
      const ids=new Set();
      for(const s of k.sources){
        if(!object(s)||Object.keys(s).sort().join(',')!=='chunk_id,score,url'||!/^DOC-[A-Z]+-\d{2}#\d{2}$/.test(s.chunk_id||'')||
          typeof s.url!=='string'||!s.url.startsWith('https://')||typeof s.score!=='number'||!Number.isFinite(s.score)||s.score<.4||s.score>1||ids.has(s.chunk_id))reasons.push('KNOWLEDGE_SOURCE_INVALID');
        ids.add(s?.chunk_id);
      }
    }
    // The delivered ledger certifies no service response/repair commitment.
    if(k.deadline!==null)reasons.push('KNOWLEDGE_DEADLINE_REQUIRES_REVIEW');
  }
  if(!object(e)||e.receipt_verified!==true||e.request_response_match!==true||e.indexed_context_verified!==true||e.sources_match_selected_context!==true||e.source_count!==k.sources?.length)
    reasons.push('KNOWLEDGE_EVIDENCE_UNVERIFIED');
  else if(k.answer_found===true){
    if(e.provider!=='ollama'||e.generation_model!=='qwen2.5:3b'||!['bge-m3','bge-m3:latest'].includes(e.embedding_model)||!/^[a-f0-9]{64}$/.test(e.embedding_digest||'')||e.generation_recorded!==true)
      reasons.push('KNOWLEDGE_EXECUTION_UNVERIFIED');
    if(e.procedure_verbatim_in_context!==true)reasons.push('KNOWLEDGE_PARAPHRASE_REQUIRES_REVIEW');
  }
}
const unique=[...new Set(reasons)];x.decision=unique.length?'REVIEW':'PASS';x.review_reasons.push(...unique);
x.policy.gate_3={decision:x.decision,reason_codes:unique,checks:{scope:'Native schema, actual indexed source context and conservative verbatim procedure support',
  municipality:'Commune de Tunis',incident_location_inferred:false,semantic_limit:'No guarantee of semantic applicability, source currentness or real-world correctness',
  native_response_preserved:object(k),receipt_verified:object(e)&&e.receipt_verified===true}};
if(object(e)&&e.receipt_verified===true)x.components.knowledge={...x.components.knowledge,
  inference:e.generation_recorded?'native_generation_recorded':'no_generation_recorded',retrieval:'indexed_context_verified',
  configured_provider:e.provider,configured_generation_model:e.generation_model,embedding_model:e.embedding_model};
x.trace.push({at:new Date().toISOString(),stage:'GATE_3_KNOWLEDGE',decision:x.decision,reason_codes:unique});
return [{json:x}];
