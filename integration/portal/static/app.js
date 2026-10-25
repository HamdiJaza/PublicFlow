'use strict';
/* Citizen portal front-end. Talks only to the local portal API; n8n alone runs the agents and policy gates. */
const $ = id => document.getElementById(id);
const form = $('reportForm');
const KINDS = ['image', 'audio', 'video'];
const defaults = Object.fromEntries(KINDS.map(k => [k, $(k + 'Name').textContent]));
const LIMITS_MB = { image: 10, audio: 30, video: 50 };
const KIND_LABELS = { image: 'Photo', audio: 'Voice note', video: 'Video' };
let token, polling, previewURL, requestKey = null;

const element = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
};
const pretty = value => value == null || value === '' ? null
  : String(value).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
const when = iso => { const d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString('en-GB'); };
const session = fetch('/api/session').then(r => r.json()).then(s => { token = s.token; });

const TICKET_STATUS = { OPEN: 'Open', NEEDS_REVIEW: 'Awaiting municipal review', IN_PROGRESS: 'In progress', RESOLVED: 'Resolved', REJECTED: 'Rejected' };
const DECISION = {
  PASS: { badge: 'pass', label: 'Accepted', title: 'Your complaint has been accepted' },
  REVIEW: { badge: 'review', label: 'Needs review', title: 'Your complaint needs a human check' },
  REJECT: { badge: 'reject', label: 'Rejected', title: 'Your complaint could not be accepted' },
};
const STAGES = {
  INPUT_CHECK: 'Submission check', INTAKE_HTTP: 'Complaint preparation (Intake)', GATE_1_INTAKE: 'Policy gate 1 · intake',
  GATE_1_PREPARATION: 'Policy gate 1 · intake', VISION_HTTP: 'Visual analysis (Vision)', GATE_2_VISION: 'Policy gate 2 · vision',
  REVIEW_CONTINUATION: 'Continued with uncertainty kept', KNOWLEDGE_REQUEST_MAPPING: 'Procedure search prepared',
  KNOWLEDGE_HTTP: 'Procedure search (RAG)', GATE_3_KNOWLEDGE: 'Policy gate 3 · sources', TICKET_ASSEMBLY: 'Ticket assembled',
  POSTGRES_PERSISTENCE: 'Saved to the ticket database',
};
const SERVICE_NAMES = { n8n: 'workflow engine', intake: 'complaint preparation', vision: 'visual analysis', media: 'media checks', knowledge: 'procedure search', evidence: 'procedure sources', ollama: 'local models', persistence: 'ticket database' };

/* ---------- helpers ---------- */
function error(message) { $('formError').textContent = message || ''; $('formError').hidden = !message; }
function busy(on) { $('fields').disabled = on; $('loading').classList.toggle('show', on); }
function evidenceType() { return $('typeVideo').checked ? 'video' : 'photo'; }

function clearFile(kind) {
  $(kind).value = '';
  $(kind + 'Name').textContent = defaults[kind];
  $(kind + 'Card').classList.remove('filled');
}
function refreshPreview() {
  if (previewURL) { URL.revokeObjectURL(previewURL); previewURL = null; }
  const selected = evidenceType() === 'video' ? $('video').files[0] : $('image').files[0];
  const box = $('preview'); box.replaceChildren(); box.hidden = !selected;
  if (!selected) return;
  previewURL = URL.createObjectURL(selected);
  const media = element(selected.type.startsWith('video/') ? 'video' : 'img');
  media.src = previewURL;
  if (media.tagName === 'VIDEO') media.controls = true; else media.alt = 'Preview of the selected file';
  const remove = element('button', 'Remove file', 'ghost remove'); remove.type = 'button';
  remove.addEventListener('click', () => { clearFile(selected.type.startsWith('video/') ? 'video' : 'image'); refreshPreview(); });
  box.append(media, remove);
}
function applyEvidenceType() {
  const video = evidenceType() === 'video';
  $('photoGroup').hidden = video; $('videoGroup').hidden = !video;
  // Keep the submission consistent with the backend rule: a video is always sent alone.
  if (video) { clearFile('image'); clearFile('audio'); } else clearFile('video');
  $('descriptionTag').textContent = video ? 'Optional with a video' : 'Required with a photo, unless you add a voice note';
  $('descriptionTag').classList.toggle('required', !video);
  refreshPreview();
}

/* ---------- service readiness ---------- */
async function readiness() {
  const pill = $('readiness'), alert = $('readinessAlert');
  try {
    const h = await fetch('/api/health').then(r => r.json());
    pill.className = 'status-pill ' + (h.ready ? 'ready' : 'busy');
    $('readinessText').textContent = h.ready ? 'All services ready' : 'Some services are starting';
    if (h.ready) { alert.hidden = true; return; }
    const missing = Object.keys(h.services).filter(k => !h.services[k]).map(k => SERVICE_NAMES[k] || k);
    alert.replaceChildren(document.createTextNode('Not ready yet: ' + missing.join(', ') + '. You can prepare your complaint now; sending will work once every service is up. '));
    const a = element('a', 'Open system setup'); a.href = '/setup'; alert.append(a);
    alert.hidden = false;
  } catch {
    pill.className = 'status-pill down'; $('readinessText').textContent = 'Portal unreachable';
    alert.textContent = 'The local portal is not responding. Run Start_MunicipaliteAuto.cmd again.'; alert.hidden = false;
  }
}

/* ---------- tabs ---------- */
const motion = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
function showTab(name) {
  for (const t of ['Report', 'Track']) {
    const active = t === name;
    $('tab' + t).setAttribute('aria-selected', String(active));
    $('tab' + t).tabIndex = active ? 0 : -1;
    $('panel' + t).hidden = !active;
  }
  try { sessionStorage.setItem('municipal-tab', name); } catch { /* storage optional */ }
}
$('tabReport').addEventListener('click', () => showTab('Report'));
$('tabTrack').addEventListener('click', () => showTab('Track'));
// Tabs follow the WAI-ARIA pattern: arrow keys move between them, only the active one is in the Tab order.
for (const [id, name, other] of [['tabReport', 'Report', 'tabTrack'], ['tabTrack', 'Track', 'tabReport']]) {
  $(id).addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); showTab(name === 'Report' ? 'Track' : 'Report'); $(other).focus();
  });
}
$('startBtn').addEventListener('click', () => {
  showTab('Report');
  $('panelReport').scrollIntoView({ behavior: motion(), block: 'start' });
  $('description').focus({ preventScroll: true });
});
$('trackShortcut').addEventListener('click', () => {
  showTab('Track');
  $('panelTrack').scrollIntoView({ behavior: motion(), block: 'start' });
  $('trackId').focus({ preventScroll: true });
});

/* ---------- result rendering ---------- */
function fact(label, value, fallback) {
  const card = element('div', undefined, 'fact');
  card.append(element('small', label));
  card.append(element('strong', value || fallback || 'Not determined', value ? '' : 'empty'));
  return card;
}
function trackingBox(trackingId, status, note) {
  const box = element('div', undefined, 'tracking');
  box.append(element('small', 'Your tracking ID'));
  const row = element('div', undefined, 'tracking-id');
  row.append(element('code', trackingId));
  const copy = element('button', 'Copy', 'ghost'); copy.type = 'button';
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(trackingId); copy.textContent = 'Copied'; }
    catch { copy.textContent = 'Select and copy manually'; }
    setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
  });
  row.append(copy); box.append(row);
  box.append(element('p', (status ? 'Current status: ' + (TICKET_STATUS[status] || status) + '. ' : '') + (note || 'Keep this ID to follow your complaint in the "Track a complaint" tab.')));
  return box;
}
function knowledgeSection(k, executed) {
  const wrap = element('div', undefined, 'procedure');
  wrap.append(element('div', 'Applicable municipal procedure', 'section-title'));
  if (k?.verified && k.procedure) {
    wrap.append(element('p', k.procedure));
    if (k.deadline) wrap.append(element('p', 'Expected deadline: ' + k.deadline));
  } else {
    wrap.append(element('p', executed
      ? 'The procedure search ran, but no source was verified well enough to publish a procedure for this complaint. Nothing is invented in its place.'
      : 'The procedure search was not run for this complaint.'));
  }
  const sources = (k?.sources || []).filter(s => typeof s.url === 'string' && s.url.startsWith('https://'));
  if (sources.length) {
    const list = element('div', undefined, 'source-list');
    for (const s of sources) { const a = element('a', 'Source: ' + (s.chunk_id || s.url)); a.href = s.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; list.append(a); }
    wrap.append(list);
  }
  return wrap;
}
function showReference(id) { $('resultWrap').classList.add('visible'); $('reference').textContent = 'Submission reference: ' + id; }

function render(record) {
  const result = record.result, body = $('resultBody'); body.replaceChildren();
  const badge = $('globalBadge');
  if (!result) {
    $('resultTitle').textContent = record.state === 'interrupted' ? 'Processing was interrupted' : 'Processing failed';
    badge.textContent = record.state === 'interrupted' ? 'Interrupted' : 'Failed'; badge.className = 'badge reject';
    body.append(element('p', record.error || 'No result is available for this submission.', 'alert error'));
    body.append(element('p', 'No ticket was created. Please check with the municipality before sending the same complaint again.', 'hint'));
    return;
  }
  const d = DECISION[result.decision] || { badge: '', label: result.decision, title: 'Processing result' };
  const saved = result.persisted && result.ticket?.tracking_id;
  $('resultTitle').textContent = saved && result.decision !== 'REJECT' ? d.title + ' and saved' : d.title;
  badge.textContent = d.label; badge.className = 'badge ' + d.badge;

  const messages = {
    PASS: 'All automatic checks passed. Your complaint has been recorded and routed to the municipal department below.',
    REVIEW: saved ? 'Automatic processing finished, but some points need a municipal agent to confirm them. Your complaint is saved and queued for review.'
                  : 'The result needs a human check, and saving to the ticket database could not be confirmed.',
    REJECT: 'The submission did not pass the checks, so it was not routed to a department. See the reasons below.',
  };
  body.append(element('p', messages[result.decision] || '', 'alert ' + (result.decision === 'PASS' ? 'success' : result.decision === 'REJECT' ? 'error' : 'warning')));

  if (saved) {
    const box = trackingBox(result.ticket.tracking_id, result.ticket.status);
    const refresh = element('button', 'Refresh status', 'ghost'); refresh.type = 'button';
    refresh.addEventListener('click', async () => {
      refresh.disabled = true;
      try {
        const response = await fetch('/api/tickets/' + encodeURIComponent(result.ticket.tracking_id));
        const current = await response.json();
        if (!response.ok) throw new Error(current.detail || 'The status could not be read.');
        box.lastChild.textContent = 'Current status: ' + (TICKET_STATUS[current.ticket.status] || current.ticket.status) + ' · updated ' + when(current.ticket.updated_at) + '.';
      } catch (e) { box.lastChild.textContent = e.message; } finally { refresh.disabled = false; }
    });
    box.querySelector('.tracking-id').append(refresh);
    body.append(box);
  } else {
    body.append(element('p', 'No ticket was saved in the municipal database. This result is kept only as a local execution receipt.', 'alert warning'));
  }

  const facts = element('div', undefined, 'facts');
  facts.append(fact('Problem type', pretty(result.visual_assessment?.category)));
  facts.append(fact('Severity', pretty(result.visual_assessment?.severity)));
  facts.append(fact('Department', pretty(result.routing?.department), 'Not assigned'));
  facts.append(fact('Priority', pretty(result.routing?.priority), 'Not assigned'));
  body.append(facts);

  body.append(knowledgeSection(result.knowledge, result.components?.knowledge?.execution === 'responded'));

  const reasons = [...new Set([...(result.errors || []), ...(result.review_reasons || [])])];
  if (reasons.length) {
    body.append(element('div', result.decision === 'REJECT' ? 'Why it was rejected' : 'Points flagged for review', 'section-title'));
    const list = element('ul', undefined, 'reason-list'); reasons.forEach(r => list.append(element('li', pretty(r) || r))); body.append(list);
    if (result.decision === 'REVIEW' && !result.review_queued) body.append(element('p', 'The review request is not yet in a municipal queue.', 'hint'));
  }

  // Technical details stay available but out of the citizen's way.
  const details = element('details');
  details.append(element('summary', 'Processing details'));
  const inner = element('div', undefined, 'details-body');
  const components = element('div', undefined, 'components');
  const states = { responded: 'Responded', not_called: 'Not run', unavailable: 'Unavailable', committed: 'Committed', failed_or_unconfirmed: 'Failed or unconfirmed' };
  for (const [label, key] of [['Complaint preparation', 'intake'], ['Visual analysis', 'vision'], ['Procedure search', 'knowledge'], ['Database', 'persistence']]) {
    const c = result.components?.[key] || {}, card = element('div', undefined, 'component');
    card.append(element('small', label)); card.append(document.createTextNode(states[c.execution] || pretty(c.execution) || 'Not reported'));
    components.append(card);
  }
  inner.append(components);
  inner.append(element('div', 'Steps actually executed', 'section-title'));
  const trace = element('ol', undefined, 'trace');
  for (const step of result.trace || []) {
    const tone = ['PASS', 'COMMITTED', 'ACCEPTED'].includes(step.decision) ? 'ok' : ['REJECT', 'FAILED'].includes(step.decision) ? 'bad' : 'warn';
    const li = element('li'); li.append(document.createTextNode((STAGES[step.stage] || pretty(step.stage)) + ' · '));
    li.append(element('span', pretty(step.decision), tone));
    if (step.reason_codes?.length) li.append(element('small', step.reason_codes.join(', ')));
    trace.append(li);
  }
  inner.append(trace);
  const links = element('div', undefined, 'inline-links');
  const download = element('a', 'Download execution receipt (JSON)'); download.href = '/api/reports/' + record.report_id; download.download = record.report_id + '.json';
  links.append(download); inner.append(links);
  details.append(inner); body.append(details);
}

/* ---------- polling ---------- */
async function poll(id) {
  clearTimeout(polling);
  try {
    const response = await fetch('/api/reports/' + id);
    if (!response.ok) throw new Error('The receipt for this submission is unavailable.');
    const record = await response.json(); showReference(id);
    if (['queued', 'running'].includes(record.state)) {
      busy(true);
      const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(record.started_at || record.submitted_at)) / 1000));
      $('loadingText').textContent = 'Processing your complaint · ' + Math.floor(seconds / 60) + ' min ' + (seconds % 60) + ' s elapsed. Local AI models can take several minutes.';
      $('resultTitle').textContent = 'Processing your complaint';
      $('globalBadge').textContent = 'Processing'; $('globalBadge').className = 'badge processing';
      const body = $('resultBody'); body.replaceChildren();
      body.append(element('p', 'Your complaint is being prepared, analysed and matched with municipal procedures. The outcome and your tracking ID will appear here. You can reload this page without sending the complaint again.'));
      const bar = element('div', undefined, 'progress'); bar.append(element('span')); body.append(bar);
      polling = setTimeout(() => poll(id), 2000);
    } else { busy(false); requestKey = null; render(record); readiness(); }
  } catch (e) {
    error(e.message + ' Checking again in a few seconds; nothing is resent.');
    polling = setTimeout(() => poll(id), 5000);
  }
}

/* ---------- form wiring ---------- */
$('description').addEventListener('input', () => { $('descriptionCount').textContent = String($('description').value.length); });
for (const radio of ['typePhoto', 'typeVideo']) $(radio).addEventListener('change', applyEvidenceType);
for (const kind of KINDS) {
  $(kind).addEventListener('change', () => {
    const file = $(kind).files[0];
    $(kind + 'Name').textContent = file ? file.name + ' · ' + (file.size / 1024 / 1024).toFixed(1) + ' MB' : defaults[kind];
    $(kind + 'Card').classList.toggle('filled', Boolean(file));
    error(''); refreshPreview();
  });
  const card = $(kind + 'Card');
  card.addEventListener('dragenter', () => card.classList.add('drag'));
  card.addEventListener('dragleave', () => card.classList.remove('drag'));
  card.addEventListener('drop', () => card.classList.remove('drag'));
}

form.addEventListener('submit', async event => {
  event.preventDefault(); error('');
  const image = $('image').files[0], audio = $('audio').files[0], video = $('video').files[0];
  if (evidenceType() === 'video') {
    if (!video) return error('Please add a video, or switch to "Photo".');
  } else {
    if (!image) return error('Please add a photo, or switch to "Video".');
    if (!audio && $('description').value.trim().length < 5) return error('Please describe the problem (at least 5 characters) or add a voice note.');
  }
  for (const [kind, file] of Object.entries({ image, audio, video })) {
    if (file && (!file.size || file.size > LIMITS_MB[kind] * 1024 * 1024)) return error(KIND_LABELS[kind] + ': the file is empty or larger than ' + LIMITS_MB[kind] + ' MB.');
  }
  busy(true);
  try {
    await session;
    const data = new FormData();
    data.append('description', $('description').value); data.append('address', $('address').value);
    for (const [kind, file] of Object.entries({ image, audio, video })) if (file) data.append(kind, file);
    requestKey = requestKey || crypto.randomUUID();
    const response = await fetch('/api/reports', { method: 'POST', headers: { 'X-Portal-Token': token, 'Idempotency-Key': requestKey }, body: data });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'The complaint could not be sent.');
    sessionStorage.setItem('municipal-last-report', result.report_id);
    $('resultWrap').scrollIntoView({ behavior: motion(), block: 'start' });
    await poll(result.report_id);
  } catch (e) { busy(false); error(e.message); }
});

form.addEventListener('reset', () => {
  requestKey = null; error(''); clearTimeout(polling); sessionStorage.removeItem('municipal-last-report');
  $('resultWrap').classList.remove('visible');
  for (const k of KINDS) clearFile(k);
  $('descriptionCount').textContent = '0';
  // The browser restores the default radio after this handler; apply the photo layout then.
  setTimeout(applyEvidenceType, 0);
});

/* ---------- track a complaint ---------- */
$('trackForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('trackId').value.trim().toLowerCase(), out = $('trackResult'), err = $('trackError');
  out.replaceChildren(); err.hidden = true;
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(id)) {
    err.textContent = 'That does not look like a tracking ID. It has 36 characters, like 3f2a1c4e-9b7d-4e21-8c0a-5d6f7e8a9b0c.'; err.hidden = false; return;
  }
  $('trackBtn').disabled = true;
  try {
    const response = await fetch('/api/tickets/' + encodeURIComponent(id));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The ticket could not be read.');
    const t = data.ticket;
    const row = element('div', undefined, 'status-row');
    const badge = element('span', TICKET_STATUS[t.status] || t.status, 'badge ' + ({ OPEN: 'pass', IN_PROGRESS: 'processing', RESOLVED: 'pass', NEEDS_REVIEW: 'review', REJECTED: 'reject' }[t.status] || ''));
    row.append(badge);
    row.append(element('span', 'Created ' + when(t.created_at) + ' · last update ' + when(t.updated_at), 'timestamps'));
    out.append(trackingBox(t.tracking_id, null, 'This is the ticket recorded in the municipal database.'), row);
    const facts = element('div', undefined, 'facts');
    facts.append(fact('Problem type', pretty(t.category)));
    facts.append(fact('Severity', pretty(t.severity)));
    facts.append(fact('Department', pretty(t.department), 'Not assigned'));
    facts.append(fact('Priority', pretty(t.priority), 'Not assigned'));
    out.append(facts);
    if (t.summary) { const s = element('div', undefined, 'procedure'); s.append(element('div', 'Complaint summary', 'section-title'), element('p', t.summary)); out.append(s); }
    if (t.knowledge?.verified && t.knowledge.procedure) out.append(knowledgeSection(t.knowledge, true));
    if (t.review_queued) out.append(element('p', 'A municipal agent still needs to review this complaint.', 'alert warning'));
  } catch (e) { err.textContent = e.message; err.hidden = false; } finally { $('trackBtn').disabled = false; }
});

/* ---------- start ---------- */
applyEvidenceType();
readiness(); setInterval(readiness, 15000);
try { if (sessionStorage.getItem('municipal-tab') === 'Track') showTab('Track'); } catch { /* storage optional */ }
const previous = sessionStorage.getItem('municipal-last-report');
if (previous && /^RPT-[a-f0-9]{32}$/.test(previous)) poll(previous);
