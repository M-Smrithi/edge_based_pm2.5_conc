(async function () {
  const { $, h, api, fmt, clear, empty } = UI; const page = $('#page'); let pg = 1, q = '', act = '';
  const box = h('div', { class: 'card' }); clear(page).append(box);
  clear(box).append(h('div', { class: 'row' }, h('div', { class: 'grow' }, h('label', { for: 'aq' }, 'Search'), h('input', { id: 'aq', type: 'search', placeholder: 'Target, user or detail' })), h('div', {}, h('label', { for: 'aa' }, 'Action'), h('select', { id: 'aa' }, h('option', { value: '' }, 'All actions'))), h('div', {}, h('label', { class: 'sr' }, 'Export'), h('a', { class: 'btn', id: 'ex', href: '/api/admin/audit?format=csv' }, 'Export CSV'))), h('div', { id: 'at', class: 'mt' }));
  let t; $('#aq').oninput = () => { clearTimeout(t); t = setTimeout(() => { q = $('#aq').value; pg = 1; load(); }, 300); }; $('#aa').onchange = () => { act = $('#aa').value; pg = 1; load(); };
  async function load() {
    $('#ex').href = `/api/admin/audit?format=csv&q=${encodeURIComponent(q)}&action=${encodeURIComponent(act)}`;
    let d; try { d = await api(`/api/admin/audit?page=${pg}&size=25&q=${encodeURIComponent(q)}&action=${encodeURIComponent(act)}`); } catch (e) { return UI.errorBox($('#at'), e, load); }
    const s = $('#aa'); if (s.options.length === 1) d.actions.forEach(a => s.append(h('option', { value: a }, a.replace(/_/g, ' ')))); s.value = act;
    const el = $('#at'); if (!d.rows.length) return empty(el, 'No audit entries', q || act ? 'Try clearing the filters.' : 'Administrative actions will be listed here.');
    clear(el).append(h('div', { class: 'tablewrap' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['When (UTC)', 'User', 'Action', 'Target', 'Detail'].map(x => h('th', {}, x)))), h('tbody', {}, d.rows.map(r => h('tr', {}, h('td', { class: 'small' }, fmt.date(r.ts)), h('td', {}, r.user_email || '—'), h('td', {}, UI.badge(r.action.replace(/_/g, ' '), /fail|blocked|reject|cancel/.test(r.action) ? 'warn' : '')), h('td', {}, r.target || '—'), h('td', { class: 'small muted pre' }, (r.detail || '').slice(0, 220))))))));
    const pages = Math.ceil(d.total / d.size); el.append(h('div', { class: 'pager' }, h('span', {}, `${fmt.n(d.total)} entries · page ${d.page} of ${pages}`), h('button', { class: 'btn sm', disabled: pg <= 1, onclick: () => { pg--; load(); } }, 'Previous'), h('button', { class: 'btn sm', disabled: pg >= pages, onclick: () => { pg++; load(); } }, 'Next')));
  }
  load();
})();
