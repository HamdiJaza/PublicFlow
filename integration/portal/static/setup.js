'use strict';
const $ = id => document.getElementById(id);
let token;
const session = fetch('/api/session').then(r => r.json()).then(s => { token = s.token; });
const LABELS = { n8n: 'Workflow engine (n8n)', intake: 'Complaint preparation (Intake, NVIDIA)', vision: 'Visual analysis (Vision, local)', media: 'Media checks', knowledge: 'Procedure search (RAG)', evidence: 'Procedure sources verified', ollama: 'Local models (Ollama)', persistence: 'Ticket database (PostgreSQL)' };

async function health() {
  try {
    const h = await fetch('/api/health').then(r => r.json());
    const list = $('services'); list.replaceChildren();
    for (const [name, ready] of Object.entries(h.services)) {
      const row = document.createElement('div'); row.className = 'service-row';
      const label = document.createElement('span'), state = document.createElement('strong');
      label.textContent = LABELS[name] || name;
      state.textContent = ready ? 'Available' : 'Unavailable'; state.className = ready ? 'service-ok' : 'service-off';
      row.append(label, state); list.append(row);
    }
    $('saveKey').disabled = h.services.intake;
    if (h.services.intake) { $('key').disabled = true; $('key').value = ''; $('message').textContent = 'Complaint preparation is running. Citizens can send complaints.'; }
    else $('key').disabled = false;
  } catch { $('services').textContent = 'The portal is not responding.'; }
}

$('keyForm').addEventListener('submit', async e => {
  e.preventDefault(); $('saveKey').disabled = true; $('message').textContent = 'Saving the key and starting Intake…';
  try {
    await session;
    const key = $('key').value.trim(); $('key').value = '';
    const r = await fetch('/api/setup/intake', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Portal-Token': token }, body: JSON.stringify({ key }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Setup failed.');
    $('message').textContent = data.message;
  } catch (e) { $('message').textContent = e.message; }
  finally { $('key').value = ''; $('saveKey').disabled = false; await health(); }
});
health(); setInterval(health, 15000);
