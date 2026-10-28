'use strict';
(async () => {
  const { h, api, label, STATUS, ROLE, REGION, busy, notice, date, orgLabel } = Staff;
  const $ = id => document.getElementById(id);
  const account = await Staff.session(['ADMIN']);
  Staff.bindLogout($('logout'));
  $('userName').textContent = account.display_name;
  let organisations = [];
  const SERVICES = { n8n: 'n8n orchestrator', intake: 'Intake agent (NVIDIA)', translation: 'Summary translation (NVIDIA)', media: 'Media service (blurring, images)',
    vision: 'Vision agent', knowledge: 'Knowledge agent (RAG)', evidence: 'Source verification', ollama: 'Ollama (RAG)', persistence: 'Ticket database' };

  // Tabs (arrow keys move between tabs, as in the WAI-ARIA pattern).
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function show(tab) {
    for (const x of tabs) {
      const on = x === tab;
      x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1;
      $(x.getAttribute('aria-controls')).hidden = !on;
    }
    tab.focus();
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => show(tab));
    tab.addEventListener('keydown', e => {
      const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (next !== undefined) { e.preventDefault(); show(tabs[(next + tabs.length) % tabs.length]); }
    });
  });

  // ---------- Overview ----------
  async function overview() {
    $('services').replaceChildren(h('li', {}, 'Checking…'));
    try {
      const [health, stats] = await Promise.all([api('/api/admin/health'), api('/api/admin/overview').catch(e => ({ error: e.message }))]);
      const rows = Object.entries(SERVICES).map(([key, name]) => [name, health.services[key] === true]);
      rows.unshift(['Citizen portal', health.portal], ['Console ↔ n8n link (secret)', health.staff_webhook_secret]);
      $('services').replaceChildren(...rows.map(([name, up]) => h('li', {}, h('span', {}, name), h('span', { class: up ? 'up' : 'down' }, up ? 'Available' : 'Unavailable'))));
      if (stats.error) { notice($('overviewNotice'), 'error', 'Statistics unavailable: ' + stats.error); $('stats').replaceChildren(); return; }
      notice($('overviewNotice'), 'info', '');
      const stat = (value, text) => h('div', { class: 'stat' }, h('div', { class: 'value' }, String(value)), h('div', { class: 'label' }, text));
      $('stats').replaceChildren(stat(stats.total, 'Tickets in total'),
        ...Object.keys(STATUS).map(s => stat(stats.by_status[s] || 0, label(STATUS, s))),
        stat(stats.last_ticket_at ? date(stats.last_ticket_at) : '—', 'Latest complaint'));
    } catch (error) { notice($('overviewNotice'), 'error', error.message); }
  }
  $('refreshHealth').addEventListener('click', async e => { const restore = busy(e.currentTarget); await overview(); restore(); });

  // ---------- Organisations ----------
  const orgName = code => (code ? orgLabel(organisations.find(o => o.code === code) || { name_fr: code }) : '—');
  async function loadOrganisations() {
    try { organisations = (await api('/api/admin/organisations')).organisations; }
    catch (error) { notice($('communesNotice'), 'error', error.message); return; }
    $('organisations').replaceChildren(...organisations.map(o => h('tr', {},
      h('td', {}, o.name_en || o.name_fr, o.name_en ? h('div', { class: 'muted' }, 'Official name: ' + o.name_fr) : null),
      h('td', { class: 'mono' }, o.code), h('td', {}, o.kind === 'MUNICIPALITY' ? 'Municipality' : 'National utility'),
      h('td', {}, o.region ? label(REGION, o.region) : '—'),
      h('td', {}, o.active ? 'Active' : 'Disabled'),
      h('td', {}, o.kind === 'MUNICIPALITY' && o.code !== 'COMMUNE_TUNIS' ? h('button', { class: 'button small', type: 'button', onclick: async e => {
        const restore = busy(e.currentTarget);
        try { await api('/api/admin/communes/' + o.code, { method: 'PATCH', body: { active: !o.active } }); await loadOrganisations(); }
        catch (error) { restore(); notice($('communesNotice'), 'error', error.message); }
      } }, o.active ? 'Disable' : 'Enable') : null))));
    fillOrgSelect();
  }
  const slug = text => 'COMMUNE_' + text.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase()
    .replace(/^COMMUNE\s+(DE\s+|D'|DU\s+|DES\s+)?/, '').replace(/^(L'|LA\s+|LE\s+)/, '').replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 31);
  let codeEdited = false;
  $('cCode').addEventListener('input', () => { codeEdited = true; });
  $('cName').addEventListener('input', () => { if (!codeEdited) $('cCode').value = slug($('cName').value); });
  $('communeForm').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target, data = Object.fromEntries(new FormData(form));
    const restore = busy(event.submitter);
    try {
      await api('/api/admin/communes', { method: 'POST', body: data });
      form.reset(); codeEdited = false; $('communeError').textContent = '';
      notice($('communesNotice'), 'success', 'Municipality added. It now appears in the citizen form.');
      await loadOrganisations();
    } catch (error) { $('communeError').textContent = error.message; }
    restore();
  });

  // ---------- Accounts ----------
  function fillOrgSelect() {
    const role = $('aRole').value;
    $('aOrgField').hidden = role === 'ADMIN';
    $('aOrg').replaceChildren(h('option', { value: '' }, 'Choose…'), ...organisations
      .filter(o => o.active && o.kind === (role === 'MUNICIPALITY' ? 'MUNICIPALITY' : 'UTILITY')).map(o => h('option', { value: o.code }, orgLabel(o))));
  }
  $('aRole').addEventListener('change', fillOrgSelect);
  const randomPassword = () => {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789', bytes = crypto.getRandomValues(new Uint8Array(16));
    return [...bytes].map(b => alphabet[b % alphabet.length]).join('');
  };
  $('generate').addEventListener('click', () => { $('aPassword').value = randomPassword(); $('aPassword').select(); });

  const actionButton = (text, kind, onclick) => h('button', { class: 'button small' + (kind ? ' ' + kind : ''), type: 'button', onclick: async e => {
    const restore = busy(e.currentTarget);
    try { await onclick(); await loadAccounts(); } catch (error) { restore(); notice($('accountsNotice'), 'error', error.message); }
  } }, text);

  async function loadAccounts() {
    try {
      const { accounts } = await api('/api/admin/accounts');
      const pending = accounts.filter(a => a.pending), others = accounts.filter(a => !a.pending);
      $('pendingCount').textContent = pending.length ? '(' + pending.length + ')' : '';
      $('requestsCard').hidden = !pending.length;
      $('requests').replaceChildren(...pending.map(a => h('tr', {},
        h('td', { class: 'mono' }, a.username), h('td', {}, a.display_name),
        h('td', {}, orgName(a.organisation), h('div', { class: 'muted' }, label(ROLE, a.role))),
        h('td', {}, a.request_note || ''),
        h('td', {}, h('span', { class: 'row' },
          actionButton('Approve', 'primary', async () => {
            await api('/api/admin/accounts/' + a.username, { method: 'PATCH', body: { active: true } });
            notice($('accountsNotice'), 'success', 'Account ' + a.username + ' approved. The person can now sign in.');
          }),
          actionButton('Refuse', 'danger', async () => {
            if (!confirm('Refuse the request from ' + a.username + '? It will be deleted.')) throw new Error('Cancelled.');
            await api('/api/admin/accounts/' + a.username + '/refuse', { method: 'POST' });
            notice($('accountsNotice'), 'success', 'Request from ' + a.username + ' refused.');
          }))))));
      $('accounts').replaceChildren(...others.map(a => h('tr', {},
        h('td', { class: 'mono' }, a.username), h('td', {}, a.display_name), h('td', {}, label(ROLE, a.role)),
        h('td', {}, a.organisation ? orgName(a.organisation) : '—'), h('td', {}, a.active ? 'Active' : 'Disabled'),
        h('td', {}, h('span', { class: 'row' },
          h('button', { class: 'button small', type: 'button', onclick: () => resetPassword(a) }, 'Password'),
          a.username === account.username ? null : actionButton(a.active ? 'Disable' : 'Enable', a.active ? 'danger' : '', async () => {
            if (a.active && !confirm('Disable the account ' + a.username + '? The person will be signed out.')) throw new Error('Cancelled.');
            await api('/api/admin/accounts/' + a.username, { method: 'PATCH', body: { active: !a.active } });
          }))))));
    } catch (error) { notice($('accountsNotice'), 'error', error.message); }
  }
  $('accountForm').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target, data = Object.fromEntries(new FormData(form));
    if (data.role === 'ADMIN') delete data.organisation;
    const restore = busy(event.submitter);
    try {
      const { account: created } = await api('/api/admin/accounts', { method: 'POST', body: data });
      form.reset(); fillOrgSelect(); $('accountError').textContent = '';
      notice($('accountsNotice'), 'success', 'Account ' + created.username + ' created. Give the temporary password through a safe channel.');
      await loadAccounts();
    } catch (error) { $('accountError').textContent = error.message; }
    restore();
  });

  function resetPassword(a) {
    const dialog = $('passwordDialog');
    $('pwFor').textContent = 'Account: ' + a.username + ' (' + a.display_name + ')';
    $('pwValue').value = randomPassword(); $('pwError').textContent = '';
    dialog.showModal(); $('pwValue').select();
    $('passwordForm').onsubmit = async event => {
      event.preventDefault();
      const restore = busy(event.submitter);
      try {
        await api('/api/admin/accounts/' + a.username, { method: 'PATCH', body: { password: $('pwValue').value } });
        dialog.close(); notice($('accountsNotice'), 'success', 'Password of ' + a.username + ' changed.');
      } catch (error) { $('pwError').textContent = error.message; }
      restore();
    };
  }
  $('pwCancel').addEventListener('click', () => $('passwordDialog').close());

  // ---------- NVIDIA key ----------
  $('keyForm').addEventListener('submit', async event => {
    event.preventDefault();
    const input = $('key'), restore = busy(event.submitter);
    notice($('keyNotice'), 'info', 'Configuring… (up to one minute)');
    try {
      const result = await api('/api/admin/intake-key', { method: 'POST', body: { key: input.value.trim() } });
      notice($('keyNotice'), 'success', result.message);
    } catch (error) { notice($('keyNotice'), 'error', error.message); }
    input.value = ''; restore();
  });

  await loadOrganisations();
  await Promise.all([overview(), loadAccounts()]);
})();
