'use strict';
const $=id=>document.getElementById(id);
let token;
const session=fetch('/api/session').then(r=>r.json()).then(s=>{token=s.token;});
async function health(){
  try {
    const h=await fetch('/api/health').then(r=>r.json()); $('services').replaceChildren();
    const labels={n8n:'Orchestration n8n',intake:'Intake NVIDIA',vision:'Vision locale',media:'Médias vérifiés',knowledge:'Recherche RAG',evidence:'Sources RAG vérifiées',ollama:'Modèles locaux',persistence:'Base de tickets PostgreSQL'};
    for(const [name,ready] of Object.entries(h.services)){
      const label=document.createElement('span'), state=document.createElement('strong');label.textContent=labels[name]||name;state.textContent=ready?'Disponible':'Indisponible';state.className=ready?'service-ok':'service-off';$('services').append(label,state);
    }
    $('saveKey').disabled=h.services.intake;
    if(h.services.intake) { $('key').disabled=true; $('key').value=''; $('message').textContent='Intake est démarré. Vous pouvez envoyer un signalement.'; }
  }catch{$('services').textContent='Portail indisponible.';}
}
$('keyForm').addEventListener('submit',async e=>{
  e.preventDefault(); $('saveKey').disabled=true; $('message').textContent='Configuration et démarrage en cours…';
  try {
    await session;
    const key=$('key').value.trim(); $('key').value='';
    const r=await fetch('/api/setup/intake',{method:'POST',headers:{'Content-Type':'application/json','X-Portal-Token':token},body:JSON.stringify({key})});
    const data=await r.json(); if(!r.ok) throw new Error(data.detail||'Configuration impossible.'); $('message').textContent=data.message;
  }catch(e){$('message').textContent=e.message;}
  finally{$('key').value='';$('saveKey').disabled=false;await health();}
});
health();setInterval(health,15000);
