'use strict';
(async () => {
  const { h, t, api, label, STATUS, CATEGORY, SEVERITY, REASON, badge, priority, date, busy, notice, orgLabel } = Staff;
  const $ = id => document.getElementById(id);
  const account = await Staff.session(['MUNICIPALITY', 'UTILITY']);
  const municipality = account.role === 'MUNICIPALITY';
  Staff.bindLogout($('logout'));

  let organisations = [];
  try { organisations = (await api('/api/organisations')).organisations; } catch (error) { notice($('listNotice'), 'error', error.message); }
  const orgName = code => (code ? orgLabel(organisations.find(o => o.code === code) || { name_fr: code }) : 'Not assigned');
  $('orgName').textContent = orgName(account.organisation);
  $('userName').textContent = account.display_name;
  $('userRole').textContent = municipality ? 'Municipality: supervision and assignment' : 'Utility: carrying out the work';
  document.title = 'Tickets · ' + orgName(account.organisation);

  const FILTERS = municipality ? ['NEEDS_REVIEW', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'REJECTED', 'ALL'] : ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'ALL'];
  const state = { filter: FILTERS[0], tickets: [], counts: {}, selected: null, dirty: false };

  // Proposal only: the municipality confirms or changes it.
  const suggested = category => ({ ROAD_DAMAGE: account.organisation, WASTE: account.organisation, STREET_LIGHTING: 'STEG', WATER_LEAK: 'SONEDE' })[category];

  function renderFilters() {
    const total = Object.values(state.counts).reduce((a, b) => a + b, 0);
    $('filters').replaceChildren(...FILTERS.map(value => h('button', {
      class: 'chip', type: 'button', 'aria-pressed': String(state.filter === value),
      onclick: () => { state.filter = value; loadList(); },
    }, value === 'ALL' ? 'All' : label(STATUS, value), h('span', { class: 'count' }, '(' + (value === 'ALL' ? total : state.counts[value] || 0) + ')'))));
  }

  function renderList() {
    const query = $('search').value.trim().toLowerCase();
    const shown = state.tickets.filter(x => !query || [x.summary, x.address, x.tracking_id].some(v => (v || '').toLowerCase().includes(query)));
    $('listStatus').textContent = t('{n} ticket(s) shown', { n: shown.length });
    if (!shown.length) {
      $('list').replaceChildren(h('li', { class: 'empty' }, query ? 'No ticket matches the search.'
        : state.filter === 'NEEDS_REVIEW' ? 'Nothing to review. Good work!' : 'No ticket in this category.'));
      return;
    }
    $('list').replaceChildren(...shown.map(x => h('li', {}, h('button', {
      class: 'item', type: 'button', 'aria-current': String(state.selected === x.tracking_id),
      onclick: () => select(x.tracking_id),
    },
      h('span', { class: 'line' }, badge(x.status), priority(x.priority)),
      h('span', { class: 'title' }, label(CATEGORY, x.category, 'Category to be determined')),
      h('span', { class: 'summary', lang: 'fr' }, x.summary || 'No description'),
      h('span', { class: 'line muted' }, x.address ? x.address + ' · ' : '', date(x.created_at),
        municipality && x.organisation && x.organisation !== account.organisation ? ' · ' + orgName(x.organisation) : '')))));
  }

  async function loadList() {
    renderFilters();
    try {
      const data = await api('/api/tickets' + (state.filter === 'ALL' ? '' : '?status=' + state.filter));
      state.tickets = data.tickets; state.counts = data.counts;
      notice($('listNotice'), 'info', '');
    } catch (error) { state.tickets = []; notice($('listNotice'), 'error', error.message); }
    renderFilters(); renderList();
  }

  // ---------- Detail ----------
  const fact = (term, value) => [h('dt', {}, term), h('dd', {}, value ?? 'Not provided')];
  const section = (title, ...content) => h('section', { class: 'card' }, h('h2', { class: 'section-title' }, title), ...content);
  const DECISION = { PASS: 'passed', REVIEW: 'needs review', REJECT: 'rejected', NOT_RUN: 'not run' };

  // English translation of the French Intake summary when available; the original stays one click away.
  function summary(x) {
    const english = x.summary_translation?.en;
    if (!english) return [h('p', { class: 'muted' }, 'Complaint summary (prepared in French by the Intake agent)'),
      h('p', { class: 'note', lang: 'fr' }, x.summary || 'No description.')];
    return [h('p', { class: 'muted' }, "Complaint summary (machine translation of the Intake agent's French summary)"),
      h('p', { class: 'note' }, english),
      h('details', {}, h('summary', {}, 'Show the original French summary'), h('p', { class: 'note', lang: 'fr' }, x.summary || ''))];
  }

  function analysis(x) {
    const gates = [['gate_1', 'Gate 1: complaint preparation'], ['gate_2', 'Gate 2: image analysis'], ['gate_3', 'Gate 3: procedure and sources']];
    const items = gates.map(([key, name]) => {
      const g = x.gates?.[key] || {}, reasons = Array.isArray(g.reason_codes) ? g.reason_codes : [];
      return h('li', { class: g.decision || '' }, h('strong', {}, name + ': ' + (DECISION[g.decision] || 'unknown')),
        reasons.length ? h('ul', { class: 'reasons' }, reasons.map(r => h('li', {}, label(REASON, r)))) : null);
    });
    const vision = (x.vision || [])[0];
    return section('Automatic analysis (AI)',
      h('p', { class: 'muted' }, 'Proposal of the AI agents, checked by fixed rules. The final decision belongs to the municipality.'),
      h('ul', { class: 'gates' }, items),
      vision ? h('dl', { class: 'facts' },
        fact('What the model sees', vision.description),
        fact('Visible evidence', Array.isArray(vision.evidence) ? vision.evidence.join('; ') : null),
        fact('Stated doubt', vision.uncertainty_reason || 'None'),
        fact('Model confidence', typeof vision.confidence === 'number' ? Math.round(vision.confidence * 100) + '% (uncalibrated estimate)' : null),
        x.vision.length > 1 ? fact('Frames analysed', t('{n} frames from the video', { n: x.vision.length })) : null) : h('p', {}, 'No image analysis available.'),
      x.ai_classification ? h('p', { class: 'notice info' }, t("AI's initial classification: {c}, {s} severity. It was corrected by the municipality.",
        { c: label(CATEGORY, x.ai_classification.category, 'none'), s: label(SEVERITY, x.ai_classification.severity, 'unset').toLowerCase() })) : null);
  }

  function procedure(x) {
    const k = x.knowledge || {};
    if (k.verified !== true || !k.procedure) return section('Municipal procedure', h('p', {}, 'No verified procedure in the sources. Nothing is invented in its place.'));
    return section('Municipal procedure', h('p', { class: 'note', lang: 'fr' }, k.procedure),
      h('p', { class: 'muted' }, 'Quoted from the municipal source document (in French).'),
      h('ul', {}, (k.sources || []).map(s => h('li', {}, h('a', { href: s.url, rel: 'noreferrer noopener', target: '_blank' }, s.chunk_id),
        ' (similarity ' + Number(s.score).toFixed(2) + ')'))));
  }

  function historySection(x) {
    const names = { CREATED: 'Ticket created automatically', REVIEWED: 'Reviewed and assigned', ASSIGNED: 'Reassigned', STATUS_CHANGED: 'Status changed', COMMENT: 'Internal note' };
    return section('History', h('ol', { class: 'timeline' }, (x.events || []).slice().reverse().map(e => h('li', {},
      h('div', {}, h('strong', {}, names[e.event] || e.event), e.to ? ': ' + label(STATUS, e.to) : '',
        e.organisation && e.event !== 'COMMENT' && e.event !== 'STATUS_CHANGED' ? ' → ' + orgName(e.organisation) : ''),
      h('div', { class: 'when' }, date(e.at) + ' · ' + (e.actor === 'n8n' ? 'system' : e.actor)),
      e.corrections && Object.keys(e.corrections).length ? h('div', { class: 'note' }, 'Correction: ' + Object.entries(e.corrections)
        .map(([k, v]) => (k === 'category' ? label(CATEGORY, v.from, 'none') + ' → ' + label(CATEGORY, v.to) : label(SEVERITY, v.from, 'none') + ' → ' + label(SEVERITY, v.to))).join('; ')) : null,
      e.note ? h('p', { class: 'note' }, e.note) : null,
      e.public_note ? h('p', { class: 'note muted' }, 'Message to the citizen: ' + e.public_note) : null))));
  }

  // One action form. fields: subset of category, severity, organisation, public_note.
  function actionBox(x, { title, text, action, button, kind = 'primary', fields = [] }) {
    const id = action + '-' + x.version;
    const errorId = id + '-error';
    const choice = (name, labelText, options, value) => h('div', { class: 'field' }, h('label', { for: id + name }, labelText),
      h('select', { id: id + name, name, required: true }, h('option', { value: '' }, 'Choose…'),
        options.map(([code, text]) => h('option', { value: code, selected: code === value }, text))));
    const form = h('form', { class: 'action-box', novalidate: true },
      h('h3', {}, title), text ? h('p', { class: 'muted' }, text) : null,
      fields.includes('category') || fields.includes('severity') ? h('div', { class: 'grid-2' },
        fields.includes('category') ? choice('category', 'Category', Object.entries(CATEGORY), x.category) : null,
        fields.includes('severity') ? choice('severity', 'Severity (= priority)', Object.entries(SEVERITY), x.severity) : null) : null,
      fields.includes('organisation') ? choice('organisation', 'Organisation doing the work',
        organisations.map(o => [o.code, orgLabel(o)]), x.organisation || suggested(x.category)) : null,
      h('div', { class: 'field' }, h('label', { for: id + 'note' }, 'Internal note (required)'),
        h('textarea', { id: id + 'note', name: 'note', required: true, maxlength: 2000, 'aria-describedby': errorId })),
      fields.includes('public_note') ? h('div', { class: 'field' }, h('label', { for: id + 'public' }, 'Message to the citizen (optional)'),
        h('textarea', { id: id + 'public', name: 'public_note', maxlength: 500, 'aria-describedby': id + 'publicHint' }),
        h('span', { class: 'hint', id: id + 'publicHint' }, "Shown in the citizen's tracking page. No names or personal data.")) : null,
      h('p', { class: 'field-error', id: errorId, role: 'alert' }),
      h('button', { class: 'button ' + kind, type: 'submit' }, button));
    form.addEventListener('input', () => { state.dirty = true; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      const error = form.querySelector('.field-error');
      if ((data.note || '').trim().length < 5) { error.textContent = 'Add a note of at least 5 characters.'; form.elements.note.focus(); return; }
      for (const name of ['category', 'severity', 'organisation']) if (name in data && !data[name]) { error.textContent = 'Complete every choice.'; form.elements[name].focus(); return; }
      error.textContent = '';
      const restore = busy(event.submitter);
      try {
        const result = await api('/api/tickets/' + x.tracking_id + '/actions', { method: 'POST', body: { action, expected_version: x.version, ...data } });
        state.dirty = false;
        render(result.ticket, 'Saved: ' + title.toLowerCase() + '.');
        loadList();
      } catch (failure) {
        restore();
        if (failure.code === 'VERSION_CONFLICT') { state.dirty = false; await select(x.tracking_id, failure.message, 'error'); }
        else error.textContent = failure.message;
      }
    });
    return form;
  }

  function actions(x) {
    const boxes = [];
    const executor = x.organisation === account.organisation;
    if (municipality && x.status === 'NEEDS_REVIEW') {
      boxes.push(actionBox(x, { title: 'Approve and assign', action: 'approve', button: 'Approve and send',
        text: "Correct the AI's proposal if needed, then choose who does the work.", fields: ['category', 'severity', 'organisation', 'public_note'] }));
      boxes.push(actionBox(x, { title: 'Reject the complaint', action: 'reject', button: 'Reject', kind: 'danger',
        text: 'Off-topic, duplicate or unusable complaint.', fields: ['public_note'] }));
    }
    if (municipality && ['OPEN', 'IN_PROGRESS'].includes(x.status)) {
      boxes.push(actionBox(x, { title: 'Reassign', action: 'reassign', button: 'Reassign', fields: ['organisation'],
        text: 'The ticket goes back to "Open" at the new organisation.' }));
    }
    if (executor && x.status === 'OPEN') {
      boxes.push(actionBox(x, { title: 'Take charge', action: 'start', button: 'Start the work' }));
      boxes.push(actionBox(x, { title: 'Work not possible', action: 'not_done', button: 'Return to the municipality', kind: 'danger',
        text: 'For example: not our network, address not found.' }));
    }
    if (executor && x.status === 'IN_PROGRESS') {
      boxes.push(actionBox(x, { title: 'Work done', action: 'done', button: 'Mark as resolved', fields: ['public_note'] }));
      boxes.push(actionBox(x, { title: 'Work not done', action: 'not_done', button: 'Return to the municipality', kind: 'danger',
        text: 'Explain why; the municipality decides what happens next.' }));
    }
    if (municipality && x.status === 'OPEN') {
      boxes.push(actionBox(x, { title: 'Reject the ticket', action: 'reject', button: 'Reject', kind: 'danger', fields: ['public_note'] }));
    }
    if (municipality && x.status === 'RESOLVED') {
      boxes.push(actionBox(x, { title: 'Reopen', action: 'reopen', button: 'Reopen for review', kind: 'danger',
        text: 'The problem persists: the ticket goes back to "Needs review".' }));
    }
    if (!boxes.length) boxes.push(h('p', { class: 'muted' }, x.status === 'IN_PROGRESS' ? 'Work in progress at ' + orgName(x.organisation) + '.'
      : 'No action is needed from you on this ticket.'));
    return section('Actions', h('div', { class: 'actions-grid' }, boxes));
  }

  function commentBox(x) {
    const form = h('form', { novalidate: true },
      h('div', { class: 'field' }, h('label', { for: 'comment' }, 'Add an internal note'),
        h('textarea', { id: 'comment', name: 'note', maxlength: 2000 }), h('span', { class: 'hint' }, 'Visible to the municipality and the assigned organisation, never to the citizen.')),
      h('p', { class: 'field-error', role: 'alert' }), h('button', { class: 'button', type: 'submit' }, 'Add note'));
    form.addEventListener('input', () => { state.dirty = true; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const note = form.elements.note.value.trim(), error = form.querySelector('.field-error');
      if (note.length < 2) { error.textContent = 'The note is empty.'; return; }
      const restore = busy(event.submitter);
      try { state.dirty = false; render((await api('/api/tickets/' + x.tracking_id + '/comments', { method: 'POST', body: { note } })).ticket, 'Note added.'); }
      catch (failure) { restore(); error.textContent = failure.message; }
    });
    return h('section', { class: 'card' }, form);
  }

  function render(x, message, kind = 'success') {
    state.selected = x.tracking_id;
    const copy = h('button', { class: 'button small', type: 'button', onclick: async () => {
      try { await navigator.clipboard.writeText(x.tracking_id); copy.textContent = 'Copied'; } catch { copy.textContent = 'Copy failed'; }
    } }, 'Copy ID');
    $('detailBody').replaceChildren(
      h('button', { class: 'button small back', type: 'button', onclick: () => { $('console').classList.remove('show-detail'); history.replaceState(null, '', '/console'); } }, '← Back to the list'),
      h('div', { id: 'detailNotice', 'aria-live': 'polite' }, message ? h('div', { class: 'notice ' + kind, role: kind === 'error' ? 'alert' : 'status' }, message) : null),
      h('section', { class: 'card' },
        h('div', { class: 'detail-head' }, h('h2', { id: 'detailTitle', tabindex: '-1' }, label(CATEGORY, x.category, 'Category to be determined')),
          h('span', { class: 'row' }, badge(x.status), priority(x.priority))),
        ...summary(x),
        h('dl', { class: 'facts' },
          fact('Tracking ID', h('span', { class: 'row' }, h('span', { class: 'mono' }, x.tracking_id), copy)),
          fact('Address given', x.location?.address || 'Not given'),
          fact('Municipality', x.commune_name),
          fact('Organisation in charge', orgName(x.organisation)),
          fact('Severity', label(SEVERITY, x.severity)),
          fact('Received', date(x.created_at)), fact('Updated', date(x.updated_at))),
        x.review?.status === 'PENDING' ? h('div', { class: 'notice info spaced' }, h('strong', {}, 'Why it needs review: '),
          (x.review.reason_codes || []).map(r => label(REASON, r)).join('; ')) : null),
      actions(x), analysis(x), procedure(x), historySection(x), commentBox(x));
    $('placeholder').hidden = true; $('detailBody').hidden = false;
    $('console').classList.add('show-detail');
    renderList();
  }

  async function select(id, message, kind) {
    if (state.dirty && !confirm('Unsaved input will be lost. Continue?')) return;
    state.dirty = false;
    try {
      const data = await api('/api/tickets/' + id);
      render(data.ticket, message, kind);
      history.replaceState(null, '', '/console#ticket=' + id);
      $('detailTitle').focus();
    } catch (error) { notice($('listNotice'), 'error', error.message); }
  }

  $('search').addEventListener('input', renderList);
  $('refresh').addEventListener('click', async e => { const restore = busy(e.currentTarget); await loadList(); restore(); });
  // Background refresh only when nothing is being typed.
  setInterval(() => { if (document.visibilityState === 'visible' && !state.dirty) loadList(); }, 60000);
  await loadList();
  const deep = /^#ticket=([a-f0-9-]{36})$/.exec(location.hash);
  if (deep) select(deep[1]);
})();
