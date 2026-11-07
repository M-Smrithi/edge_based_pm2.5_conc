/* Shared helpers: safe DOM builder, API client (CSRF), toasts, dialogs, tables, formatters. No innerHTML with data. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'text') el.textContent = v;
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const clear = el => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
  const fmt = {
    n: (v, d = 0) => v == null || Number.isNaN(+v) ? '—' : (+v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }),
    pct: (v, d = 1) => v == null ? '—' : (+v).toFixed(d) + '%',
    date: s => s ? String(s).replace('T', ' ').slice(0, 16) : '—',
    day: s => s ? String(s).slice(0, 10) : '—',
    bytes: b => b == null ? '—' : b > 1e9 ? (b / 1e9).toFixed(2) + ' GB' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : b > 1e3 ? (b / 1e3).toFixed(0) + ' kB' : b + ' B',
    ms: v => v == null ? '—' : (+v < 0.1 ? (+v).toFixed(3) : (+v).toFixed(2)) + ' ms',
    pm: v => v == null ? '—' : (+v).toFixed(1),
  };
  let csrf = ($('meta[name=csrf]') || {}).content || '';
  async function api(path, opt = {}) {
    const o = { method: opt.method || 'GET', headers: { Accept: 'application/json' }, credentials: 'same-origin' };
    if (o.method !== 'GET') o.headers['X-CSRF-Token'] = csrf;
    if (opt.json !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(opt.json); }
    if (opt.form) o.body = opt.form;
    let r;
    try { r = await fetch(path, o); } catch (e) { throw new Error('Network error — is the server running?'); }
    let data = null;
    try { data = await r.json(); } catch (e) { /* non-JSON */ }
    if (r.status === 401 && location.pathname.startsWith('/admin') && !location.pathname.startsWith('/admin/login')) { location.href = '/admin/login'; }
    if (!r.ok) { const err = new Error((data && data.error) || ('Request failed (' + r.status + ')')); err.status = r.status; err.data = data; throw err; }
    if (data && data.csrf) csrf = data.csrf;
    return data;
  }
  function upload(path, form, onProgress) {   // XHR for real upload progress
    return new Promise((res, rej) => {
      const x = new XMLHttpRequest(); x.open('POST', path); x.setRequestHeader('X-CSRF-Token', csrf); x.setRequestHeader('Accept', 'application/json');
      if (x.upload && onProgress) x.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded / e.total);
      x.onload = () => { let d = null; try { d = JSON.parse(x.responseText); } catch (e) {} x.status >= 200 && x.status < 300 ? res(d) : rej(new Error((d && d.error) || 'Upload failed (' + x.status + ')')); };
      x.onerror = () => rej(new Error('Network error during upload.')); x.send(form);
    });
  }
  function toast(msg, type) {
    let box = $('.toasts'); if (!box) { box = h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' }); document.body.append(box); }
    const t = h('div', { class: 'toast ' + (type || '') }, msg); box.append(t); setTimeout(() => t.remove(), type === 'err' ? 7000 : 4000);
  }
  function dialog({ title, body, confirm = 'Confirm', danger = false, typeToConfirm = null, cancel = 'Cancel', extra = null }) {
    return new Promise(res => {
      const prev = document.activeElement; let input = null;
      const ok = h('button', { class: 'btn ' + (danger ? 'danger' : 'primary'), type: 'button' }, confirm);
      const no = h('button', { class: 'btn', type: 'button' }, cancel);
      const kids = [h('h3', { id: 'dlg-t' }, title), typeof body === 'string' ? h('p', { class: 'muted' }, body) : body];
      if (typeToConfirm) { input = h('input', { type: 'text', 'aria-label': 'Type ' + typeToConfirm + ' to confirm', autocomplete: 'off' }); ok.disabled = true; input.addEventListener('input', () => ok.disabled = input.value.trim() !== typeToConfirm); kids.push(h('div', { class: 'field' }, h('label', {}, 'Type ', h('span', { class: 'mono' }, typeToConfirm), ' to confirm'), input)); }
      if (extra) kids.push(extra);
      const m = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'dlg-t' }, kids, h('div', { class: 'row' }, no, ok));
      const bg = h('div', { class: 'modal-bg' }, m); const close = v => { bg.remove(); document.removeEventListener('keydown', key); prev && prev.focus && prev.focus(); res(v); };
      const key = e => { if (e.key === 'Escape') close(false); if (e.key === 'Tab') { const f = $$('button,input,select,textarea,a[href]', m).filter(x => !x.disabled); if (!f.length) return; const a = f[0], z = f[f.length - 1]; if (e.shiftKey && document.activeElement === a) { z.focus(); e.preventDefault(); } else if (!e.shiftKey && document.activeElement === z) { a.focus(); e.preventDefault(); } } };
      ok.onclick = () => close(input ? input.value.trim() : true); no.onclick = () => close(false); bg.addEventListener('mousedown', e => e.target === bg && close(false));
      document.addEventListener('keydown', key); document.body.append(bg); (input || no).focus();
    });
  }
  function empty(el, title, text, action) { clear(el).append(h('div', { class: 'empty' }, h('h3', {}, title), h('p', {}, text), action || null)); }
  function skeleton(el, n = 3) { clear(el); for (let i = 0; i < n; i++) el.append(h('div', { class: 'skel', style: null, 'aria-hidden': 'true' }, ' '), h('div', { class: 'sr' }, 'Loading')); }
  function errorBox(el, e, retry) { clear(el).append(h('div', { class: 'notice bad', role: 'alert' }, e.message || String(e), retry ? h('button', { class: 'btn sm', onclick: retry, style: null }, ' Retry') : null)); }
  /* Sortable, searchable, paginated table. cols: [{key,label,num,render(row),sort}] */
  function table(el, { cols, rows, pageSize = 15, search = null, empty: em = 'No rows to show.', onRow = null, sortKey = null, desc = false }) {
    let q = '', page = 0, sk = sortKey, sd = desc;
    const wrap = h('div'); const ctl = h('div', { class: 'row', style: null });
    let input = null;
    if (search) { input = h('input', { type: 'search', placeholder: 'Search…', 'aria-label': 'Search table', class: 'grow' }); input.addEventListener('input', () => { q = input.value.toLowerCase(); page = 0; draw(); }); wrap.append(h('div', { class: 'field' }, input)); }
    const holder = h('div'); wrap.append(holder); clear(el).append(wrap);
    function draw() {
      let r = rows.filter(x => !q || search.some(k => String(x[k] ?? '').toLowerCase().includes(q)));
      if (sk) { const c = cols.find(c => c.key === sk); r = [...r].sort((a, b) => { const va = c.sort ? c.sort(a) : a[sk], vb = c.sort ? c.sort(b) : b[sk]; return (va > vb ? 1 : va < vb ? -1 : 0) * (sd ? -1 : 1); }); }
      const pages = Math.max(1, Math.ceil(r.length / pageSize)); page = Math.min(page, pages - 1); const view = r.slice(page * pageSize, (page + 1) * pageSize);
      clear(holder);
      if (!r.length) { holder.append(h('div', { class: 'empty' }, em)); return; }
      const th = cols.map(c => h('th', { class: (c.num ? 'num ' : '') + (c.key ? 'sort' : ''), 'aria-sort': sk === c.key ? (sd ? 'descending' : 'ascending') : null, tabindex: c.key ? 0 : null,
        onclick: c.key ? () => { sd = sk === c.key ? !sd : false; sk = c.key; draw(); } : null, onkeydown: c.key ? e => { if (e.key === 'Enter') { sd = sk === c.key ? !sd : false; sk = c.key; draw(); } } : null },
        c.label, sk === c.key ? (sd ? ' ↓' : ' ↑') : ''));
      const tb = view.map(row => h('tr', { onclick: onRow ? () => onRow(row) : null, class: onRow ? 'clickable' : null }, cols.map(c => h('td', { class: c.num ? 'num' : '' }, c.render ? c.render(row) : (row[c.key] ?? '—')))));
      holder.append(h('div', { class: 'tablewrap' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, th)), h('tbody', {}, tb))));
      if (r.length > pageSize) holder.append(h('div', { class: 'pager' }, h('span', {}, `${page * pageSize + 1}–${Math.min(r.length, (page + 1) * pageSize)} of ${r.length}`),
        h('button', { class: 'btn sm', disabled: page === 0, onclick: () => { page--; draw(); } }, 'Previous'), h('button', { class: 'btn sm', disabled: page >= pages - 1, onclick: () => { page++; draw(); } }, 'Next')));
    }
    draw(); return { redraw: draw, setRows: r => { rows = r; draw(); } };
  }
  const badge = (text, kind) => h('span', { class: 'badge ' + (kind || '') }, text);
  const STATUS = { accepted: 'ok', accepted_recovered: 'ok', pending_review: 'warn', rejected: 'bad', duplicate: '', candidate: 'info', active: 'ok', archived: '', succeeded: 'ok', failed: 'bad', running: 'info', queued: '', cancelled: '' };
  const statusBadge = s => badge(String(s).replace(/_/g, ' '), STATUS[s]);
  function download(name, text, type = 'text/csv') { const a = h('a', { href: URL.createObjectURL(new Blob([text], { type })), download: name }); document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
  function toCSV(rows, cols) { const esc = v => { v = v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }; return [cols.join(',')].concat(rows.map(r => cols.map(c => esc(r[c])).join(','))).join('\n'); }
  function poll(fn, ms) { let stop = false; (async function loop() { if (stop) return; try { await fn(); } catch (e) {} setTimeout(loop, ms); })(); return () => { stop = true; }; }
  // mobile nav
  document.addEventListener('DOMContentLoaded', () => {
    const b = $('.burger'), n = $('.nav'); if (b && n) b.addEventListener('click', () => { const o = n.classList.toggle('open'); b.setAttribute('aria-expanded', o); });
    const sb = $('#sidebtn'), sd = $('.side'); if (sb && sd) sb.addEventListener('click', () => sd.classList.toggle('open'));
    const lo = $('#logout'); if (lo) lo.addEventListener('click', async e => { e.preventDefault(); try { await api('/api/auth/logout', { method: 'POST' }); } finally { location.href = '/admin/login'; } });
  });
  window.UI = { $, $$, h, clear, fmt, api, upload, toast, dialog, empty, skeleton, errorBox, table, badge, statusBadge, download, toCSV, poll };
})();
