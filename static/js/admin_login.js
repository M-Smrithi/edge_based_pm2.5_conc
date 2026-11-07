(function () {
  const { $, api, h } = UI; const err = $('#err');
  $('#f').addEventListener('submit', async e => {
    e.preventDefault(); err.hidden = true; const b = e.submitter; b.disabled = true;
    try { await api('/api/auth/login', { method: 'POST', json: { email: $('#email').value, password: $('#pw').value } }); location.href = '/admin'; }
    catch (x) { err.textContent = x.message; err.hidden = false; $('#pw').value = ''; $('#pw').focus(); } finally { b.disabled = false; }
  });
})();
