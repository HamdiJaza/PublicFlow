'use strict';
(async () => {
  const { api, busy, notice } = Staff;
  const $ = id => document.getElementById(id);
  const me = await api('/api/me', { allow401: true }).catch(() => ({ authenticated: false }));
  if (me.authenticated) { location.href = '/'; return; }
  if (me.bootstrap) { $('loginForm').hidden = true; $('bootstrapForm').hidden = false; $('bUsername').focus(); }
  else $('username').focus();

  $('showPassword').addEventListener('change', e => { $('password').type = e.target.checked ? 'text' : 'password'; });

  $('loginForm').addEventListener('submit', async event => {
    event.preventDefault();
    const restore = busy(event.submitter);
    notice($('loginNotice'), 'info', '');
    try {
      await api('/api/login', { method: 'POST', allow401: true, body: { username: $('username').value, password: $('password').value } });
      location.href = '/';
    } catch (error) {
      notice($('loginNotice'), 'error', error.message);
      $('password').select();
      restore();
    }
  });

  $('bootstrapForm').addEventListener('submit', async event => {
    event.preventDefault();
    const restore = busy(event.submitter);
    try {
      await api('/api/bootstrap', { method: 'POST', allow401: true,
        body: { username: $('bUsername').value, display_name: $('bName').value, password: $('bPassword').value } });
      location.href = '/';
    } catch (error) {
      notice($('bootstrapNotice'), 'error', error.message);
      restore();
    }
  });
})();
