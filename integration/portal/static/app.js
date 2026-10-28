'use strict';
/* Citizen portal front-end. Talks only to the local portal API; n8n alone runs the agents and policy gates.
   Citizens sign in with their CIN first; the complaint space is shown only after sign-in. */
const $ = id => document.getElementById(id);
const form = $('reportForm');
const KINDS = ['image', 'audio', 'video'];
const defaults = Object.fromEntries(KINDS.map(k => [k, $(k + 'Name').textContent]));
const LIMITS_MB = { image: 10, audio: 30, video: 50 };
const KIND_LABELS = { image: 'Photo', audio: 'Voice note', video: 'Video' };
let token, polling, previewURL, requestKey = null, signedIn = false;

const element = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
};
const pretty = value => value == null || value === '' ? null
  : String(value).replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());
const dateFmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Tunis' });
const when = iso => { const d = new Date(iso); return isNaN(d) ? String(iso) : dateFmt.format(d); };
const session = fetch('/api/session').then(r => r.json()).then(s => { token = s.token; });
const post = (path, body) => session.then(() => fetch(path, { method: 'POST', credentials: 'same-origin',
  headers: { 'X-Portal-Token': token, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));

const TICKET_STATUS = { OPEN: 'Assigned to the team doing the work', NEEDS_REVIEW: 'Being checked by your municipality', IN_PROGRESS: 'Work in progress', RESOLVED: 'Resolved', REJECTED: 'Rejected' };
const STATUS_BADGE = { OPEN: 'pass', IN_PROGRESS: 'processing', RESOLVED: 'pass', NEEDS_REVIEW: 'review', REJECTED: 'reject' };
const CATEGORY = { ROAD_DAMAGE: 'Road damage', STREET_LIGHTING: 'Street lighting', WASTE: 'Waste', WATER_LEAK: 'Water leak' };
const SEVERITY = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High' };
const REGION = { GRAND_TUNIS: 'Greater Tunis' };
const DECISION = {
  PASS: { badge: 'pass', label: 'Accepted', title: 'Your complaint has been accepted' },
  REVIEW: { badge: 'review', label: 'Needs review', title: 'Your municipality will check your complaint' },
  REJECT: { badge: 'reject', label: 'Rejected', title: 'Your complaint could not be accepted' },
};
const REASONS = {
  VISION_UNCERTAINTY_REQUIRES_REVIEW: 'The automatic photo analysis is not certain',
  IMAGE_TEXT_MISMATCH_OR_UNCLEAR: 'The photo and the description do not clearly match',
  VISION_CATEGORY_UNSUPPORTED_OR_UNCLEAR: 'The problem type was not recognised automatically',
  KNOWLEDGE_NO_SUPPORTED_ANSWER: 'No municipal procedure could be verified in the sources',
  INTAKE_PROVENANCE_INVALID: 'The complaint preparation could not be verified',
  INVALID_DESCRIPTION: 'The description is too short or too long', INVALID_LOCATION: 'The location or municipality is invalid',
  UNSUPPORTED_MEDIA_TYPE: 'This file format is not supported', MISSING_IMAGE: 'No photo was received',
};
const STAGES = {
  INPUT_CHECK: 'Submission check', INTAKE_HTTP: 'Complaint preparation (Intake)', GATE_1_INTAKE: 'Policy gate 1 · preparation',
  GATE_1_PREPARATION: 'Policy gate 1 · preparation', SUMMARY_TRANSLATION: 'Summary translated to English',
  VISION_HTTP: 'Photo analysis (Vision)', GATE_2_VISION: 'Policy gate 2 · image', REVIEW_CONTINUATION: 'Continued with uncertainty kept',
  VISION_FRAME_AGREEMENT: 'Agreement between video frames', DEPARTMENT_ROUTING: 'Team chosen by a fixed rule',
  KNOWLEDGE_REQUEST_MAPPING: 'Procedure search prepared', KNOWLEDGE_HTTP: 'Procedure search (RAG)', GATE_3_KNOWLEDGE: 'Policy gate 3 · sources',
  TICKET_ASSEMBLY: 'Ticket assembled', POSTGRES_PERSISTENCE: 'Saved to the complaint database',
};
const SERVICE_NAMES = { n8n: 'workflow engine', intake: 'complaint preparation', vision: 'photo analysis', media: 'media checks', knowledge: 'procedure search', evidence: 'procedure sources', ollama: 'local models', persistence: 'complaint database' };

/* ---------- helpers ---------- */
function show(el, message) { el.textContent = message || ''; el.hidden = !message; }
function error(message) { show($('formError'), message); }
function busy(on) { $('fields').disabled = on; $('loading').classList.toggle('show', on); }
function evidenceType() { return $('typeVideo').checked ? 'video' : 'photo'; }
async function readJSON(response, fallback) {
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && signedIn) { signOutLocally('Your session has ended. Please sign in again.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
  return data;
}

/* ---------- sign in / create account ---------- */
// CIN rule for the demo: digits only, exactly 8, starting with 0. Checked again by the server.
function cinProblem(value) {
  if (!value) return 'Enter your CIN.';
  if (!/^[0-9]+$/.test(value)) return 'The CIN can only contain digits.';
  if (value[0] !== '0') return 'The CIN must start with 0.';
  if (value.length !== 8) return 'The CIN must contain exactly 8 digits.';
  return '';
}
for (const id of ['loginCin', 'registerCin']) {
  // Non-digits are removed as the citizen types or pastes; the length is capped at 8.
  $(id).addEventListener('input', () => {
    const digits = $(id).value.replace(/[^0-9]/g, '').slice(0, 8);
    if (digits !== $(id).value) $(id).value = digits;
    if ($(id).getAttribute('aria-invalid') === 'true') fieldError(id, cinProblem(digits));
  });
  $(id).addEventListener('blur', () => { if ($(id).value) fieldError(id, cinProblem($(id).value)); });
}
function fieldError(id, message) {
  $(id + 'Error').textContent = message;
  $(id).setAttribute('aria-invalid', String(Boolean(message)));
  return Boolean(message);
}
for (const button of document.querySelectorAll('.eye-toggle')) {
  button.addEventListener('click', () => {
    const input = $(button.dataset.target), visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(visible));
    button.querySelector('span').textContent = visible ? 'Hide password' : 'Show password';
  });
}
// One sign-in screen for citizens and staff: an audience switch, then one of four forms.
const AUTH_FORMS = { login: 'loginForm', register: 'registerForm', 'staff-login': 'staffLoginForm', 'staff-register': 'staffRegisterForm' };
const AUTH_FOCUS = { login: 'loginCin', register: 'registerCin', 'staff-login': 'staffUsername', 'staff-register': 'staffRole' };
function authMode(mode, focus = true) {
  const staff = mode.startsWith('staff');
  for (const [name, id] of Object.entries(AUTH_FORMS)) $(id).hidden = name !== mode;
  $('citizenForms').hidden = staff; $('staffForms').hidden = !staff;
  for (const [id, on] of [['audienceCitizen', !staff], ['audienceStaff', staff]]) {
    $(id).setAttribute('aria-selected', String(on)); $(id).tabIndex = on ? 0 : -1;
  }
  for (const id of ['loginError', 'registerError', 'staffLoginError', 'staffRegisterError']) show($(id));
  if (staff) staffSetup();
  if (focus) $(AUTH_FOCUS[mode]).focus();
}
function notify(message) {
  $('authNoticeText').textContent = message || '';
  $('authNotice').hidden = !message;
}
$('authNoticeClose').addEventListener('click', () => notify(''));
$('audienceCitizen').addEventListener('click', () => { notify(''); authMode('login'); });
$('audienceStaff').addEventListener('click', () => { notify(''); authMode('staff-login'); });
for (const [id, other] of [['audienceCitizen', 'audienceStaff'], ['audienceStaff', 'audienceCitizen']]) {
  $(id).addEventListener('keydown', e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault(); $(other).click(); $(other).focus();
  });
}
$('toRegister').addEventListener('click', e => { e.preventDefault(); notify(''); authMode('register'); });
$('toLogin').addEventListener('click', e => { e.preventDefault(); authMode('login'); });
$('toStaffRegister').addEventListener('click', e => { e.preventDefault(); notify(''); authMode('staff-register'); });
$('toStaffLogin').addEventListener('click', e => { e.preventDefault(); authMode('staff-login'); });
$('footerStaff').addEventListener('click', e => {
  if (signedIn) return;  // the footer link only switches the sign-in screen
  e.preventDefault(); notify(''); authMode('staff-login'); $('authView').scrollIntoView({ block: 'start' });
});

/* ---------- staff sign-in (forwarded by this portal to the staff console) ---------- */
let staffOrganisations = null;
async function staffSetup() {
  try {
    const status = await fetch('/api/staff/status').then(r => r.json());
    $('staffBootstrap').hidden = !status.bootstrap;
  } catch { /* the sign-in itself reports an unavailable console */ }
  if (staffOrganisations) return;
  try {
    staffOrganisations = (await readJSON(await fetch('/api/staff/organisations'), 'The organisation list is unavailable.')).organisations;
    fillStaffOrganisations();
  } catch (e) { show($('staffRegisterError'), e.message); }
}
function fillStaffOrganisations() {
  const kind = $('staffRole').value === 'MUNICIPALITY' ? 'MUNICIPALITY' : 'UTILITY';
  const options = (staffOrganisations || []).filter(o => o.kind === kind).map(o => {
    const option = element('option', o.name_en || o.name_fr); option.value = o.code; return option;
  });
  const placeholder = element('option', 'Choose…'); placeholder.value = '';
  $('staffOrg').replaceChildren(placeholder, ...options);
}
$('staffRole').addEventListener('change', fillStaffOrganisations);

$('staffLoginForm').addEventListener('submit', async event => {
  event.preventDefault();
  const username = $('staffUsername').value.trim().toLowerCase(), password = $('staffPassword').value;
  const invalid = [fieldError('staffUsername', username ? '' : 'Enter your username.'),
    fieldError('staffPassword', password ? '' : 'Enter your password.')].some(Boolean);
  show($('staffLoginError'));
  if (invalid) { event.target.querySelector('[aria-invalid="true"]')?.focus(); return; }
  const button = event.submitter; button.disabled = true;
  try {
    const data = await readJSON(await post('/api/staff/login', { username, password }), 'Sign-in failed. Please try again.');
    location.href = data.redirect;  // the staff console: municipality, utility or administrator
  } catch (e) { show($('staffLoginError'), e.message); button.disabled = false; }
});
$('staffRegisterForm').addEventListener('submit', async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  data.username = (data.username || '').trim().toLowerCase();
  const invalid = [
    fieldError('staffOrg', data.organisation ? '' : 'Choose your organisation.'),
    fieldError('staffName', (data.display_name || '').trim().length >= 2 ? '' : 'Enter your full name.'),
    fieldError('staffNote', (data.request_note || '').trim().length >= 5 ? '' : 'Give your department and job title.'),
    fieldError('staffNewUsername', /^[a-z][a-z0-9._-]{2,31}$/.test(data.username) ? '' : 'Use 3 to 32 lowercase letters, digits, dot, dash or underscore.'),
    fieldError('staffNewPassword', (data.password || '').length >= 10 ? '' : 'The password must contain at least 10 characters.'),
  ].some(Boolean);
  show($('staffRegisterError'));
  if (invalid) { event.target.querySelector('[aria-invalid="true"]')?.focus(); return; }
  const button = event.submitter; button.disabled = true;
  try {
    await readJSON(await post('/api/staff/register', data), 'The request could not be sent.');
    event.target.reset(); fillStaffOrganisations();
    authMode('staff-login');
    notify('Request sent. You can sign in as soon as the administrator approves your account.');
  } catch (e) { show($('staffRegisterError'), e.message); } finally { button.disabled = false; }
});

function enterSpace(cinHint) {
  signedIn = true;
  $('authView').hidden = true; $('appView').hidden = false; $('accountBar').hidden = false;
  $('accountId').textContent = 'CIN ••••••' + cinHint;
  document.title = 'Complaint space · PublicFlow';
  loadCommunes(); readiness();
  try { const tab = sessionStorage.getItem('municipal-tab'); if (TABS.includes(tab)) showTab(tab); } catch { /* storage optional */ }
  const previous = sessionStorage.getItem('municipal-last-report');
  if (previous && /^RPT-[a-f0-9]{32}$/.test(previous)) poll(previous);
  $('spaceTitle').focus();
}
function signOutLocally(message) {
  signedIn = false; clearTimeout(polling);
  try { sessionStorage.removeItem('municipal-last-report'); } catch { /* storage optional */ }
  $('appView').hidden = true; $('accountBar').hidden = true; $('authView').hidden = false;
  document.title = 'Sign in · PublicFlow';
  form.reset(); $('resultWrap').classList.remove('visible');
  authMode('login'); notify(message);
}
async function authSubmit(event, path, prefix, check) {
  event.preventDefault();
  const cin = $(prefix + 'Cin').value, password = $(prefix + 'Password').value;
  const invalid = [fieldError(prefix + 'Cin', cinProblem(cin)), ...check(password)].some(Boolean);
  show($(prefix + 'Error'));
  if (invalid) { event.target.querySelector('[aria-invalid="true"]')?.focus(); return; }
  const button = event.submitter; button.disabled = true;
  try {
    const data = await readJSON(await post(path, { cin, password }), 'The request failed. Please try again.');
    event.target.reset(); notify('');
    enterSpace(data.cin_hint);
  } catch (e) { show($(prefix + 'Error'), e.message); } finally { button.disabled = false; }
}
$('loginForm').addEventListener('submit', e => authSubmit(e, '/api/citizen/login', 'login',
  password => [fieldError('loginPassword', password ? '' : 'Enter your password.')]));
$('registerForm').addEventListener('submit', e => authSubmit(e, '/api/citizen/register', 'register', password => [
  fieldError('registerPassword', password.length >= 8 ? '' : 'The password must contain at least 8 characters.'),
  fieldError('registerConfirm', $('registerConfirm').value === password ? '' : 'The two passwords do not match.')]));
$('logoutBtn').addEventListener('click', async () => {
  try { await post('/api/citizen/logout', {}); } finally { signOutLocally('You have signed out.'); }
});

/* ---------- complaint form ---------- */
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

async function loadCommunes() {
  const select = $('commune');
  try {
    const data = await readJSON(await fetch('/api/communes'), 'The municipality list is unavailable.');
    if (!Array.isArray(data.communes) || !data.communes.length) throw new Error();
    const previous = select.value, groups = new Map();
    for (const c of data.communes) {
      const key = c.region || '';
      if (!groups.has(key)) groups.set(key, []);
      const option = element('option', c.name_en || c.name_fr); option.value = c.code;
      groups.get(key).push(option);
    }
    select.replaceChildren(...[...groups].flatMap(([region, options]) => {
      if (!region) return options;
      const group = document.createElement('optgroup'); group.label = REGION[region] || region; group.append(...options);
      return [group];
    }));
    if (data.communes.some(c => c.code === previous)) select.value = previous;
  } catch {
    // The default option stays: without the list, the database also routes to the demo municipality.
    $('communeHint').textContent = 'The municipality list is unavailable: only the Municipality of Tunis is offered for now.';
  }
}

async function readiness() {
  const pill = $('readiness'), alert = $('readinessAlert');
  try {
    const h = await fetch('/api/health').then(r => r.json());
    pill.className = 'status-pill ' + (h.ready ? 'ready' : 'busy');
    $('readinessText').textContent = h.ready ? 'All services ready' : 'Some services are starting';
    if (h.ready) { alert.hidden = true; return; }
    const missing = Object.keys(h.services).filter(k => !h.services[k]).map(k => SERVICE_NAMES[k] || k);
    alert.textContent = 'Not ready yet: ' + missing.join(', ') + '. You can prepare your complaint now; sending will work once every service is up.';
    alert.hidden = !signedIn;
  } catch {
    pill.className = 'status-pill down'; $('readinessText').textContent = 'Portal unreachable';
    alert.textContent = 'The local portal is not responding. Run Start_MunicipaliteAuto.cmd again.'; alert.hidden = !signedIn;
  }
}

/* ---------- tabs ---------- */
const TABS = ['Report', 'Mine', 'Track'];
const motion = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
function showTab(name) {
  for (const x of TABS) {
    const active = x === name;
    $('tab' + x).setAttribute('aria-selected', String(active));
    $('tab' + x).tabIndex = active ? 0 : -1;
    $('panel' + x).hidden = !active;
  }
  try { sessionStorage.setItem('municipal-tab', name); } catch { /* storage optional */ }
  if (name === 'Mine') loadMyReports();
}
// Tabs follow the WAI-ARIA pattern: arrow keys move between them, only the active one is in the Tab order.
TABS.forEach((name, i) => {
  $('tab' + name).addEventListener('click', () => showTab(name));
  $('tab' + name).addEventListener('keydown', event => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    const target = event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : step === undefined ? null : (i + step + TABS.length) % TABS.length;
    if (target === null) return;
    event.preventDefault(); showTab(TABS[target]); $('tab' + TABS[target]).focus();
  });
});

/* ---------- result rendering ---------- */
function fact(name, value, fallback) {
  const card = element('div', undefined, 'fact');
  card.append(element('small', name));
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
  box.append(element('p', (status ? 'Current status: ' + (TICKET_STATUS[status] || status) + '. ' : '') + (note || 'This complaint is also listed in "My complaints".')));
  return box;
}
function knowledgeSection(k, executed) {
  const wrap = element('div', undefined, 'procedure');
  wrap.append(element('div', 'Applicable municipal procedure', 'section-title'));
  if (k?.verified && k.procedure) {
    const text = element('p', k.procedure); text.lang = 'fr'; wrap.append(text);
    wrap.append(element('p', 'Quoted from the municipal source document (in French).', 'hint'));
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
function timelineSection(ticket) {
  const wrap = element('div', undefined, 'procedure');
  wrap.append(element('div', 'History', 'section-title'));
  const list = element('ol', undefined, 'trace');
  for (const step of ticket.timeline || []) {
    const li = element('li');
    li.append(element('strong', TICKET_STATUS[step.status] || step.status), document.createTextNode(' · ' + when(step.at)));
    if (step.message) li.append(element('small', 'Message from the team: ' + step.message));
    list.append(li);
  }
  wrap.append(list);
  return wrap;
}
// English translation of the Intake summary when available; the original French text otherwise.
function summarySection(ticket) {
  const s = element('div', undefined, 'procedure');
  s.append(element('div', 'Complaint summary', 'section-title'));
  if (ticket.summary_en) {
    s.append(element('p', ticket.summary_en), element('p', 'Machine translation of the summary prepared by the Intake agent.', 'hint'));
  } else {
    const text = element('p', ticket.summary); text.lang = 'fr'; s.append(text);
    s.append(element('p', 'Summary prepared in French by the Intake agent.', 'hint'));
  }
  return s;
}
function showReference(id) { $('resultWrap').classList.add('visible'); $('reference').textContent = 'Submission reference: ' + id; }

function render(record) {
  const result = record.result, body = $('resultBody'); body.replaceChildren();
  const badge = $('globalBadge');
  if (!result) {
    $('resultTitle').textContent = record.state === 'interrupted' ? 'Processing was interrupted' : 'Processing failed';
    badge.textContent = record.state === 'interrupted' ? 'Interrupted' : 'Failed'; badge.className = 'badge reject';
    body.append(element('p', record.error || 'No result is available for this submission.', 'alert error'));
    body.append(element('p', 'No ticket was created. Please check with your municipality before sending the same complaint again.', 'hint'));
    return;
  }
  const d = DECISION[result.decision] || { badge: '', label: result.decision, title: 'Processing result' };
  const saved = result.persisted && result.ticket?.tracking_id;
  $('resultTitle').textContent = saved && result.decision !== 'REJECT' ? d.title + ' and saved' : d.title;
  badge.textContent = d.label; badge.className = 'badge ' + d.badge;
  const messages = {
    PASS: 'All automatic checks passed. Your complaint is saved and assigned to the team below. Your municipality follows it.',
    REVIEW: saved ? 'Automatic processing finished, but some points need an agent of your municipality to confirm them. Your complaint is saved and will be checked.'
                  : 'The result needs a human check, and saving to the complaint database could not be confirmed.',
    REJECT: 'The submission did not pass the checks, so it was not assigned to any team. See the reasons below.',
  };
  body.append(element('p', messages[result.decision] || '', 'alert ' + (result.decision === 'PASS' ? 'success' : result.decision === 'REJECT' ? 'error' : 'warning')));

  if (saved) {
    const box = trackingBox(result.ticket.tracking_id, result.ticket.status);
    const refresh = element('button', 'Refresh status', 'ghost'); refresh.type = 'button';
    refresh.addEventListener('click', async () => {
      refresh.disabled = true;
      try {
        const current = await readJSON(await fetch('/api/tickets/' + encodeURIComponent(result.ticket.tracking_id)), 'The status could not be read.');
        box.lastChild.textContent = 'Current status: ' + (TICKET_STATUS[current.ticket.status] || current.ticket.status) + ' · updated ' + when(current.ticket.updated_at) + '.';
      } catch (e) { box.lastChild.textContent = e.message; } finally { refresh.disabled = false; }
    });
    box.querySelector('.tracking-id').append(refresh);
    body.append(box);
  } else {
    body.append(element('p', 'No ticket was saved in the municipal database. This result is kept only as a local execution receipt.', 'alert warning'));
  }

  const facts = element('div', undefined, 'facts');
  facts.append(fact('Problem type', CATEGORY[result.visual_assessment?.category]));
  facts.append(fact('Severity', SEVERITY[result.visual_assessment?.severity]));
  facts.append(fact('Team in charge', result.ticket?.organisation_name, 'Chosen by your municipality'));
  facts.append(fact('Municipality', result.ticket?.commune_name));
  body.append(facts);
  body.append(knowledgeSection(result.knowledge, result.components?.knowledge?.execution === 'responded'));

  const reasons = [...new Set([...(result.errors || []), ...(result.review_reasons || [])])];
  if (reasons.length) {
    body.append(element('div', result.decision === 'REJECT' ? 'Why it was rejected' : 'Points flagged for review', 'section-title'));
    const list = element('ul', undefined, 'reason-list'); reasons.forEach(r => list.append(element('li', REASONS[r] || pretty(r) || r))); body.append(list);
  }

  // Technical details stay available but out of the citizen's way.
  const details = element('details');
  details.append(element('summary', 'Processing details'));
  const inner = element('div', undefined, 'details-body');
  const components = element('div', undefined, 'components');
  const states = { responded: 'Responded', not_called: 'Not run', unavailable: 'Unavailable', committed: 'Committed', failed_or_unconfirmed: 'Failed or unconfirmed' };
  for (const [name, key] of [['Complaint preparation', 'intake'], ['Photo analysis', 'vision'], ['Procedure search', 'knowledge'], ['Database', 'persistence']]) {
    const c = result.components?.[key] || {}, card = element('div', undefined, 'component');
    card.append(element('small', name)); card.append(document.createTextNode(states[c.execution] || pretty(c.execution) || 'Not reported'));
    components.append(card);
  }
  inner.append(components);
  inner.append(element('div', 'Steps actually executed', 'section-title'));
  const trace = element('ol', undefined, 'trace');
  for (const step of result.trace || []) {
    const tone = ['PASS', 'COMMITTED', 'ACCEPTED', 'TRANSLATED'].includes(step.decision) ? 'ok' : ['REJECT', 'FAILED'].includes(step.decision) ? 'bad' : 'warn';
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
  if (!signedIn) return;
  try {
    const record = await readJSON(await fetch('/api/reports/' + id), 'The receipt for this submission is unavailable.');
    showReference(id);
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
    if (!signedIn) return;
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
  if (!$('commune').value) return error('Choose your municipality.');
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
    data.append('description', $('description').value); data.append('address', $('address').value); data.append('commune', $('commune').value);
    for (const [kind, file] of Object.entries({ image, audio, video })) if (file) data.append(kind, file);
    requestKey = requestKey || crypto.randomUUID();
    const response = await fetch('/api/reports', { method: 'POST', credentials: 'same-origin', headers: { 'X-Portal-Token': token, 'Idempotency-Key': requestKey }, body: data });
    const result = await readJSON(response, 'The complaint could not be sent.');
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

/* ---------- my complaints and tracking ---------- */
function ticketView(ticket, note) {
  const out = element('div');
  const row = element('div', undefined, 'status-row');
  row.append(element('span', TICKET_STATUS[ticket.status] || ticket.status, 'badge ' + (STATUS_BADGE[ticket.status] || '')));
  row.append(element('span', 'Created ' + when(ticket.created_at) + ' · last update ' + when(ticket.updated_at), 'timestamps'));
  out.append(trackingBox(ticket.tracking_id, null, note), row);
  const facts = element('div', undefined, 'facts');
  facts.append(fact('Problem type', CATEGORY[ticket.category]));
  facts.append(fact('Severity', SEVERITY[ticket.severity]));
  facts.append(fact('Team in charge', ticket.organisation_name, 'Not chosen yet'));
  facts.append(fact('Municipality', ticket.commune_name));
  out.append(facts);
  if (Array.isArray(ticket.timeline) && ticket.timeline.length) out.append(timelineSection(ticket));
  if (ticket.summary || ticket.summary_en) out.append(summarySection(ticket));
  if (ticket.knowledge?.verified && ticket.knowledge.procedure) out.append(knowledgeSection(ticket.knowledge, true));
  return out;
}
async function track(id) {
  const out = $('trackResult'), err = $('trackError');
  out.replaceChildren(); err.hidden = true;
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(id)) {
    show(err, 'That does not look like a tracking ID. It has 36 characters, like 3f2a1c4e-9b7d-4e21-8c0a-5d6f7e8a9b0c.'); return;
  }
  $('trackBtn').disabled = true;
  try {
    const data = await readJSON(await fetch('/api/tickets/' + encodeURIComponent(id)), 'The complaint could not be read.');
    out.append(ticketView(data.ticket, 'This is the complaint recorded in the municipal database.'));
  } catch (e) { show(err, e.message); } finally { $('trackBtn').disabled = false; }
}
$('trackForm').addEventListener('submit', event => { event.preventDefault(); track($('trackId').value.trim().toLowerCase()); });

async function loadMyReports() {
  const box = $('myReports'); box.replaceChildren(element('p', 'Loading…', 'hint'));
  try {
    const data = await readJSON(await fetch('/api/citizen/reports', { credentials: 'same-origin' }), 'Your complaints are unavailable right now.');
    if (!data.reports.length) { box.replaceChildren(element('p', 'You have not sent any complaint yet.', 'hint')); return; }
    const list = element('ul', undefined, 'my-reports');
    for (const r of data.reports) {
      const processing = ['queued', 'running'].includes(r.state);
      const li = element('li', undefined, 'my-report');
      const head = element('div', undefined, 'status-row');
      head.append(element('strong', CATEGORY[r.category] || 'Type not determined yet'));
      head.append(r.status ? element('span', TICKET_STATUS[r.status] || r.status, 'badge ' + (STATUS_BADGE[r.status] || ''))
        : element('span', processing ? 'Processing' : 'Not saved', 'badge ' + (processing ? 'processing' : 'reject')));
      li.append(head, element('small', 'Sent ' + when(r.submitted_at) + (r.organisation_name ? ' · ' + r.organisation_name : '')));
      if (r.tracking_id) {
        const open = element('button', 'View details', 'ghost'); open.type = 'button';
        open.addEventListener('click', () => { $('trackId').value = r.tracking_id; showTab('Track'); track(r.tracking_id); });
        li.append(open);
      }
      list.append(li);
    }
    box.replaceChildren(list);
  } catch (e) { box.replaceChildren(element('p', e.message, 'alert error')); }
}
$('refreshMine').addEventListener('click', loadMyReports);

/* ---------- start ---------- */
applyEvidenceType();
setInterval(() => { if (signedIn) readiness(); }, 15000);
readiness();
// Links from the staff console land here: #staff, #staff-register, #staff-signed-out.
function openSignIn() {
  const hash = location.hash.slice(1);
  if (hash === 'staff-signed-out') { authMode('staff-login'); notify('You have signed out of the staff area.'); }
  else if (hash === 'staff' || hash === 'staff-register') authMode(hash === 'staff' ? 'staff-login' : 'staff-register');
  else authMode('login');
  if (hash) history.replaceState(null, '', location.pathname);
}
fetch('/api/citizen/me', { credentials: 'same-origin' }).then(r => r.json())
  .then(me => { if (me.authenticated && !location.hash.startsWith('#staff')) enterSpace(me.cin_hint); else openSignIn(); })
  .catch(openSignIn);
