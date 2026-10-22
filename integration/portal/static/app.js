'use strict';
const $ = id => document.getElementById(id);
const form = $('reportForm');
const defaults = Object.fromEntries(['image','audio','video'].map(k => [k,$(k+'Name').textContent]));
let token, polling, startTime, previewURL, requestKey = null;
const element = (tag, text, className) => { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(className) el.className=className; return el; };
const session = fetch('/api/session').then(r=>r.json()).then(s=>{token=s.token;});
function error(message) { $('formError').textContent=message; $('formError').hidden=!message; }
function busy(on) { $('fields').disabled=on; $('loading').classList.toggle('show',on); }
async function readiness() {
  try {
    const h=await fetch('/api/health').then(r=>r.json()), box=$('readiness');
    box.replaceChildren(); box.className='alert '+(h.ready?'success':'warning');
    if(h.ready) box.textContent='Services disponibles. Vous pouvez envoyer un signalement.';
    else {
      const names={n8n:'n8n',intake:'Intake',vision:'Vision',media:'médias',knowledge:'RAG',evidence:'sources RAG',ollama:'modèles locaux',persistence:'base de tickets'};
      box.append(document.createTextNode('Services à préparer : '+Object.keys(h.services).filter(k=>!h.services[k]).map(k=>names[k]).join(', ')+'. '));
      const a=element('a','Ouvrir la configuration'); a.href='/setup'; box.append(a);
    }
  } catch { $('readiness').textContent='Le portail local est indisponible. Relancez Start_MunicipaliteAuto.cmd.'; }
}
function showReference(id) { $('resultWrap').classList.add('visible'); $('reference').textContent='Référence d’exécution : '+id; }
function render(record) {
  const result=record.result, body=$('resultBody'); body.replaceChildren();
  $('resultTitle').textContent=result?.persisted?'Traitement terminé · signalement enregistré':result?'Résultat du traitement':'Traitement interrompu';
  $('globalBadge').textContent=result?.decision || record.state.toUpperCase();
  $('globalBadge').className='badge '+({PASS:'confirm',REVIEW:'insufficient',REJECT:'offtopic'}[result?.decision]||'offtopic');
  if(!result) { body.append(element('p',record.error||'Résultat indisponible.','alert error')); return; }
  const explanations={PASS:'Les contrôles ont accepté ce signalement.',REVIEW:result.persisted?'Le traitement automatique est terminé. Le signalement est enregistré avec les points à vérifier.':'Le résultat demande une vérification ; son enregistrement n’est pas confirmé.',REJECT:'Ce signalement a été refusé par les contrôles.'};
  body.append(element('p',explanations[result.decision],'alert '+(result.decision==='PASS'?'success':'warning')));
  const metrics=element('div',undefined,'result-summary');
  for(const [label,component] of [['Préparation','intake'],['Analyse visuelle','vision'],['Recherche documentaire','knowledge']]) {
    const c=result.components?.[component]||{}, card=element('div',undefined,'metric');
    card.append(element('small',label));
    const states={responded:'Réponse reçue',not_called:'Non exécutée',unavailable:'Indisponible'};
    card.append(element('strong',states[c.execution]||c.execution||'Non renseignée'));
    metrics.append(card);
  }
  body.append(metrics);
  if(result.visual_assessment) {
    const v=result.visual_assessment;
    if(v.category) body.append(element('p','Catégorie : '+v.category));
    if(v.severity) body.append(element('p','Gravité estimée : '+v.severity));
  }
  if(result.routing?.department) body.append(element('p','Service : '+result.routing.department));
  if(result.routing?.priority) body.append(element('p','Priorité : '+result.routing.priority));
  if(result.persisted && result.ticket?.tracking_id) {
    body.append(element('p','Référence de suivi : '+result.ticket.tracking_id));
    const statuses={OPEN:'Ouvert',NEEDS_REVIEW:'À vérifier',IN_PROGRESS:'En cours',RESOLVED:'Résolu',REJECTED:'Refusé'};
    body.append(element('p','Statut du ticket : '+(statuses[result.ticket.status]||result.ticket.status)));
    const follow=element('button','Actualiser le statut du ticket','secondary'); follow.type='button';
    const statusLine=element('p','Le statut est lu dans la base de tickets.','hint');
    follow.addEventListener('click',async()=>{
      follow.disabled=true;
      try {const response=await fetch('/api/tickets/'+encodeURIComponent(result.ticket.tracking_id));
        const current=await response.json();if(!response.ok)throw new Error(current.detail||'Lecture impossible.');
        statusLine.textContent='Statut actuel : '+(statuses[current.ticket.status]||current.ticket.status)+' · Mise à jour : '+new Date(current.ticket.updated_at).toLocaleString('fr-FR');
      } catch(e){statusLine.textContent=e.message;}finally{follow.disabled=false;}
    });
    body.append(follow,statusLine);
  }
  if(result.components?.knowledge?.execution==='responded') {
    body.append(element('h3','Recherche documentaire'));
    const k=result.knowledge;
    if(k?.verified && k.procedure)body.append(element('p',k.procedure));
    else body.append(element('p','La recherche a été exécutée. Aucune procédure suffisamment vérifiée n’est publiée pour ce signalement.'));
    if(k?.verified && k.deadline)body.append(element('p','Délai vérifié : '+k.deadline));
    for(const source of k?.sources||[])if(typeof source.url==='string'&&source.url.startsWith('https://')) {
      const a=element('a',source.chunk_id+' · Source consultée','workflow-link');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';body.append(a);
    }
  }
  body.append(element('p',result.persisted?'Enregistrement confirmé par le backend.':'Aucun ticket enregistré. Ce résultat est conservé comme reçu d’exécution local.','alert '+(result.persisted?'success':'warning')));
  if(result.decision==='REVIEW' && !result.review_queued) body.append(element('p','La demande de revue n’est pas encore enregistrée dans une file municipale.','demo-note'));
  const reasons=[...new Set([...(result.errors||[]),...(result.review_reasons||[])])];
  if(reasons.length) { const list=element('ul',undefined,'reason-list'); reasons.forEach(r=>list.append(element('li',r))); body.append(list); }
  body.append(element('h3','Étapes réellement exécutées'));
  const labels={INPUT_CHECK:'Contrôle de l’envoi',INTAKE_HTTP:'Appel Intake',GATE_1_INTAKE:'Contrôle Intake',GATE_1_PREPARATION:'Contrôle Intake',VISION_HTTP:'Appel Vision',GATE_2_VISION:'Contrôle Vision',REVIEW_CONTINUATION:'Poursuite avec incertitude conservée',KNOWLEDGE_REQUEST_MAPPING:'Préparation de la recherche',KNOWLEDGE_HTTP:'Appel RAG',GATE_3_KNOWLEDGE:'Contrôle des sources',TICKET_ASSEMBLY:'Création du signalement',POSTGRES_PERSISTENCE:'Enregistrement dans la base'};
  const trace=element('ol',undefined,'trace');
  for(const step of result.trace) {
    const li=element('li',(labels[step.stage]||step.stage)+' · '+step.decision);
    if(step.reason_codes?.length) li.append(element('small',step.reason_codes.join(', ')));
    trace.append(li);
  }
  body.append(trace);
  const download=element('a','Télécharger le reçu d’exécution','workflow-link');
  download.href='/api/reports/'+record.report_id; download.download=record.report_id+'.json'; body.append(download);
}
async function poll(id) {
  clearTimeout(polling);
  try {
    const response=await fetch('/api/reports/'+id);
    if(!response.ok) throw new Error('Le reçu de cette exécution est indisponible.');
    const record=await response.json(); showReference(id);
    if(['queued','running'].includes(record.state)) {
      busy(true); startTime=Date.parse(record.started_at||record.submitted_at);
      const seconds=Math.floor((Date.now()-startTime)/1000);
      $('loadingText').textContent='Traitement automatique en cours · '+Math.floor(seconds/60)+' min '+seconds%60+' s. Les modèles locaux peuvent prendre plusieurs minutes.';
      $('resultTitle').textContent='Traitement en cours'; $('globalBadge').textContent='EN COURS';
      $('globalBadge').className='badge'; $('resultBody').replaceChildren(element('p','n8n exécute le workflow. Les étapes confirmées et la décision apparaîtront ici à la fin. Vous pouvez recharger cette page sans relancer l’analyse.'));
      polling=setTimeout(()=>poll(id),2000);
    } else { busy(false); requestKey=null; render(record); readiness(); }
  } catch(e) {
    error(e.message+' Vérification du résultat dans quelques secondes ; aucun nouvel envoi.');
    polling=setTimeout(()=>poll(id),5000);
  }
}
for(const kind of ['image','audio','video']) {
  $(kind).addEventListener('change',()=>{
    $(kind+'Name').textContent=$(kind).files[0]?.name||defaults[kind];
    if(previewURL) URL.revokeObjectURL(previewURL);
    const selected=$('video').files[0]||$('image').files[0]; $('preview').replaceChildren(); $('preview').hidden=!selected;
    if(selected) { previewURL=URL.createObjectURL(selected); const el=element(selected.type.startsWith('video/')?'video':'img'); el.src=previewURL; if(el.tagName==='VIDEO') el.controls=true; else el.alt='Aperçu du média sélectionné'; $('preview').append(el); }
  });
}
form.addEventListener('submit',async event=>{
  event.preventDefault(); error('');
  const image=$('image').files[0], audio=$('audio').files[0], video=$('video').files[0];
  if((video&&(image||audio))||(!video&&!image)) return error('Choisissez une photo avec texte/audio, ou une vidéo seule.');
  if(image&&!audio&&$('description').value.trim().length<5) return error('Ajoutez une description de 5 caractères minimum à la photo.');
  for(const [name,file,max] of [['Photo',image,10],['Audio',audio,30],['Vidéo',video,50]]) if(file && (!file.size||file.size>max*1024*1024)) return error(name+' : fichier vide ou supérieur à '+max+' Mo.');
  busy(true);
  try {
    await session;
    const data=new FormData(); data.append('description',$('description').value); data.append('address',$('address').value);
    for(const [kind,file] of Object.entries({image,audio,video})) if(file) data.append(kind,file);
    requestKey=requestKey||crypto.randomUUID();
    const response=await fetch('/api/reports',{method:'POST',headers:{'X-Portal-Token':token,'Idempotency-Key':requestKey},body:data});
    const result=await response.json(); if(!response.ok) throw new Error(result.detail||'Envoi impossible.');
    sessionStorage.setItem('municipal-last-report',result.report_id); await poll(result.report_id);
  } catch(e) { busy(false); error(e.message); }
});
form.addEventListener('reset',()=>{
  requestKey=null; error(''); clearTimeout(polling); sessionStorage.removeItem('municipal-last-report');
  $('resultWrap').classList.remove('visible'); $('preview').replaceChildren(); $('preview').hidden=true;
  if(previewURL) URL.revokeObjectURL(previewURL);
  for(const k of Object.keys(defaults)) $(k+'Name').textContent=defaults[k];
});
readiness(); setInterval(readiness,15000);
const previous=sessionStorage.getItem('municipal-last-report');
if(previous && /^RPT-[a-f0-9]{32}$/.test(previous)) poll(previous);
