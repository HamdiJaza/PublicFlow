'use strict';
// Shared helpers. Untrusted text is only ever inserted with textContent (h()), never innerHTML.
const Staff = (() => {
  let csrf = '';
  // Interface text with {name} placeholders filled from vars.
  const t = (text, vars = {}) => text.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : '{' + k + '}'));
  const STATUS = { NEEDS_REVIEW: 'Needs review', OPEN: 'Open', IN_PROGRESS: 'In progress', RESOLVED: 'Resolved', REJECTED: 'Rejected' };
  const CATEGORY = { ROAD_DAMAGE: 'Road damage', STREET_LIGHTING: 'Street lighting', WASTE: 'Waste', WATER_LEAK: 'Water leak' };
  const SEVERITY = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High' };
  const ROLE = { ADMIN: 'Administrator (maintenance)', MUNICIPALITY: 'Municipality', UTILITY: 'Utility (STEG / SONEDE)' };
  const REGION = { GRAND_TUNIS: 'Greater Tunis' };
  const REASON = {
    VISION_UNCERTAINTY_REQUIRES_REVIEW: 'The photo analysis expresses a doubt',
    IMAGE_TEXT_MISMATCH_OR_UNCLEAR: 'The photo and the description do not clearly match',
    VISION_CATEGORY_UNSUPPORTED_OR_UNCLEAR: 'Problem type not recognised by the analysis',
    VISION_SEVERITY_UNCLEAR: 'Severity not determined',
    VISION_EVIDENCE_MISSING: 'No visual evidence cited',
    VISION_FRAME_CATEGORY_CONFLICT: 'The video frames disagree on the category',
    VISION_FRAME_SEVERITY_CONFLICT: 'The video frames disagree on the severity',
    VISION_TIMEOUT: 'The image analysis did not answer in time', VISION_UNAVAILABLE: 'Image analysis service unavailable',
    KNOWLEDGE_NO_SUPPORTED_ANSWER: 'No verified municipal procedure found',
    KNOWLEDGE_PARAPHRASE_REQUIRES_REVIEW: 'Procedure was paraphrased, to be checked',
    KNOWLEDGE_EVIDENCE_UNVERIFIED: 'Procedure sources not verified',
    KNOWLEDGE_DEADLINE_REQUIRES_REVIEW: 'Announced deadline to be checked',
    INTAKE_PROVENANCE_INVALID: 'Complaint preparation could not be verified',
    INTAKE_PREPARATION_INCOMPLETE: 'Complaint preparation incomplete',
    NO_DEPARTMENT_RULE: 'No routing rule for this category',
    UPSTREAM_RESULT_UNUSABLE: 'Step not run (previous result unusable)',
    EXECUTION_NOT_DONE: 'Work not done (returned by the utility)',
    REOPENED_BY_MUNICIPALITY: 'Reopened by the municipality', STAFF_REVIEW_REQUESTED: 'Review requested',
  };
  const ERROR = {
    VERSION_CONFLICT: 'This ticket was changed in the meantime. It has been reloaded: check it and try again.',
    INVALID_STATUS_TRANSITION: 'This action is no longer possible in the current state of the ticket.',
    NOTE_REQUIRED: 'Add a note of at least 5 characters explaining your decision.',
    ORGANISATION_INVALID: 'Choose a valid organisation.',
    CLASSIFICATION_INVALID: 'Choose a category and a severity.',
    TICKET_NOT_FOUND: 'Ticket not found or outside your scope.',
    STAFF_ACTION_FORBIDDEN: 'Your role does not allow this action.',
    STAFF_ACTOR_INVALID: 'Your organisation is not active. Contact the administrator.',
    STAFF_REQUEST_INVALID: 'Invalid request.', STAFF_REQUEST_FAILED: 'The operation failed.',
    COMMUNE_INVALID: 'Code: COMMUNE_ followed by capital letters (e.g. COMMUNE_LA_MARSA). Name: 2 to 120 characters.',
    COMMUNE_EXISTS: 'This municipality already exists.', ORGANISATION_LOCKED: 'This organisation cannot be disabled.',
    ORGANISATION_NOT_FOUND: 'Organisation not found.', DATABASE_UNAVAILABLE: 'The ticket database is unavailable.',
  };
  const label = (map, value, fallback = 'Not provided') => (value == null ? fallback : map[value] || String(value));

  function h(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value == null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) if (child != null && child !== false) node.append(child instanceof Node ? child : String(child));
    return node;
  }

  async function api(path, options = {}) {
    const init = { method: options.method || 'GET', headers: { Accept: 'application/json' }, credentials: 'same-origin' };
    if (options.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(options.body); }
    if (init.method !== 'GET') init.headers['X-Staff-CSRF'] = csrf;
    let response, data = {};
    try { response = await fetch(path, init); data = await response.json().catch(() => ({})); }
    catch { throw Object.assign(new Error('Server unreachable. Check that the staff console is running.'), { status: 0 }); }
    if (response.status === 401 && !options.allow401) { location.href = '/login'; throw new Error('Session expired.'); }
    if (!response.ok) {
      const code = data.code || data.detail;
      throw Object.assign(new Error(ERROR[code] || (typeof data.detail === 'string' ? data.detail : 'Unexpected error.')),
        { status: response.status, code });
    }
    return data;
  }

  async function session(expectedRoles) {
    const me = await api('/api/me', { allow401: true });
    if (!me.authenticated) { location.href = '/login'; throw new Error('login'); }
    csrf = me.csrf;
    if (expectedRoles && !expectedRoles.includes(me.account.role)) { location.href = '/'; throw new Error('role'); }
    return me.account;
  }

  function bindLogout(button) {
    button.addEventListener('click', async () => {
      // Back to the shared sign-in screen of the portal, with a confirmation.
      try { await api('/api/logout', { method: 'POST' }); } finally { location.href = 'http://127.0.0.1:8090/#staff-signed-out'; }
    });
  }

  const dateFmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Tunis' });
  const date = value => (value ? dateFmt.format(new Date(value)) : '');
  const badge = status => h('span', { class: 'badge s-' + status }, label(STATUS, status));
  const priority = value => h('span', { class: 'badge p-' + (value || 'none') },
    value ? t('{p} priority', { p: label(SEVERITY, value) }) : 'Priority not set');
  const orgLabel = o => (o ? o.name_en || o.name_fr : 'Not assigned');

  function busy(button) {
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    return () => { button.disabled = false; button.removeAttribute('aria-busy'); };
  }
  function notice(container, kind, text) {
    container.replaceChildren(text ? h('div', { class: 'notice ' + kind, role: kind === 'error' ? 'alert' : 'status' }, text) : '');
  }

  return { t, STATUS, CATEGORY, SEVERITY, ROLE, REGION, REASON, label, h, api, session, bindLogout, date, badge, priority, orgLabel, busy, notice };
})();
