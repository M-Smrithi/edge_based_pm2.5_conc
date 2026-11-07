(async function () {
  const { $, h, api, fmt, clear, toast, dialog, statusBadge, table, empty } = UI; const page = $('#page'); const CAN = document.body.dataset.role === 'admin';
  const act = h('div', { class: 'card' }), lst = h('div', { class: 'card' }), ev = h('div', { class: 'card' });
  clear(page).append(act, lst, ev);
  async function load() {
    let d; try { d = await api('/api/admin/models'); } catch (e) { return UI.errorBox(page, e, load); }
    const active = d.rows.find(m => m.status === 'active');
    clear(act).append(h('h3', {}, 'Active model'), active ? h('div', { class: 'grid g4' }, [['Model', active.id], ['Algorithm', active.selected.replace(/_/g, ' ')], ['Temporal RMSE', active.test && active.test.test_temporal ? fmt.n(active.test.test_temporal.rmse, 2) : '—'], ['Spatial RMSE', active.test && active.test.test_spatial ? fmt.n(active.test.test_spatial.rmse, 2) : '—']].map(([l, v]) => h('div', { class: 'kpi' }, h('div', { class: 'v', 'data-sm': 1 }, v), h('div', { class: 'l' }, l)))) : h('div', { class: 'notice warn' }, 'No model is active — the public Prediction Studio is currently unavailable. Review a candidate below and promote it.'));
    act.querySelectorAll('[data-sm]').forEach(v => v.style.fontSize = '1.3rem');
    if (!d.rows.length) empty(lst, 'No models yet', 'Train a model in the Model Training Center.'); else {
      clear(lst).append(h('h3', {}, 'Registry'), h('div', { id: 'mt' }));
      table($('#mt'), { cols: [{ key: 'id', label: 'Model' }, { key: 'status', label: 'Status', render: r => statusBadge(r.status) }, { key: 'selected', label: 'Algorithm', render: r => r.selected.replace(/_/g, ' ') }, { key: 'dataset_version', label: 'Dataset' }, { key: 'benchmark_id', label: 'Benchmark' },
        { label: 'Val RMSE', num: true, render: r => r.val ? fmt.n(r.val.rmse, 2) : '—' }, { label: 'Test RMSE (temp / spatial)', num: true, render: r => r.test ? `${fmt.n((r.test.test_temporal || {}).rmse, 2)} / ${fmt.n((r.test.test_spatial || {}).rmse, 2)}` : '—' }, { label: 'Latency', num: true, render: r => fmt.ms(r.latency_ms) }, { key: 'created_utc', label: 'Created', render: r => fmt.date(r.created_utc) },
        { label: '', render: r => h('div', { class: 'inline' }, h('button', { class: 'btn sm', onclick: () => info(r.id) }, 'Details'), CAN && (r.status === 'candidate') ? [h('button', { class: 'btn sm primary', onclick: () => promote(r.id) }, 'Promote'), h('button', { class: 'btn sm danger', onclick: () => setStatus(r.id, 'reject') }, 'Reject')] : null, CAN && r.status === 'archived' ? [h('button', { class: 'btn sm', onclick: () => rollback(r.id) }, 'Roll back to this')] : null, CAN && r.status === 'candidate' ? h('button', { class: 'btn sm', onclick: () => setStatus(r.id, 'archive') }, 'Archive') : null) }], rows: d.rows, pageSize: 10 });
    }
    clear(ev).append(h('h3', {}, 'Promotion & status history'), h('div', { id: 'evt' })); d.events.length ? table($('#evt'), { cols: [{ key: 'ts', label: 'When', render: r => fmt.date(r.ts) }, { key: 'model_id', label: 'Model' }, { key: 'action', label: 'Event', render: r => r.action.replace(/_/g, ' ') }, { key: 'user_email', label: 'By', render: r => r.user_email || 'system' }], rows: d.events, pageSize: 10 }) : empty($('#evt'), 'No events yet', '');
  }
  function checkList(c) { return h('ul', { style: null }, c.checks.map(x => h('li', { class: 'small' }, h('strong', {}, (x.ok ? '✓ ' : '✗ ') + x.key.replace(/_/g, ' ')), h('div', { class: x.ok ? 'muted' : '', style: null }, x.detail)))); }
  async function promote(id) {
    let c; try { c = await api(`/api/admin/models/${id}/checks`); } catch (e) { return toast(e.message, 'err'); }
    const body = h('div', {}, h('p', { class: 'muted' }, c.ok ? 'All promotion checks pass. The current active model (if any) will be archived and can be restored by rollback.' : 'Promotion is blocked until every check passes.'), checkList(c));
    if (!c.ok) { await dialog({ title: `Cannot promote ${id}`, body, confirm: 'Close', cancel: ' ' }); return; }
    const v = await dialog({ title: `Promote ${id}`, body, confirm: 'Promote to active', typeToConfirm: id }); if (!v) return;
    try { const r = await api(`/api/admin/models/${id}/promote`, { method: 'POST', json: { confirm: v } }); toast('Promoted — the public site now uses ' + id, 'ok'); load(); } catch (e) { toast(e.message, 'err'); load(); }
  }
  async function rollback(id) {
    const v = await dialog({ title: `Roll back to ${id}`, body: 'The model currently active will be archived (not deleted) and this archived model becomes active again after an integrity check.', confirm: 'Roll back', danger: true, typeToConfirm: id }); if (!v) return;
    try { await api('/api/admin/models-rollback', { method: 'POST', json: { to: id, confirm: v } }); toast('Rolled back to ' + id, 'ok'); load(); } catch (e) { toast(e.message, 'err'); }
  }
  async function setStatus(id, a) {
    const note = h('input', { type: 'text', placeholder: 'Reason (recorded)', 'aria-label': 'Reason' });
    if (!(await dialog({ title: `${a === 'reject' ? 'Reject' : 'Archive'} ${id}`, body: a === 'reject' ? 'Rejected models can never be promoted.' : 'Archived models stay available for rollback.', confirm: a === 'reject' ? 'Reject' : 'Archive', danger: a === 'reject', extra: h('div', { class: 'field' }, note) }))) return;
    try { await api(`/api/admin/models/${id}/${a}`, { method: 'POST', json: { note: note.value } }); toast('Done', 'ok'); load(); } catch (e) { toast(e.message, 'err'); }
  }
  async function info(id) {
    let m; try { m = await api('/api/admin/models/' + id); } catch (e) { return toast(e.message, 'err'); }
    const b = h('div', { class: 'stack' }, h('dl', { class: 'kv' }, h('dt', {}, 'Algorithm'), h('dd', {}, m.selected.replace(/_/g, ' ')), h('dt', {}, 'Trained on'), h('dd', {}, `${fmt.n(m.manifest.train_rows)} rows (${m.manifest.dataset_version}), validated on ${fmt.n(m.manifest.val_rows)}`), h('dt', {}, 'Benchmark'), h('dd', {}, m.manifest.benchmark_id), h('dt', {}, 'Seed'), h('dd', {}, m.manifest.seed), h('dt', {}, 'Checksum'), h('dd', { class: 'mono small' }, m.model_sha256.slice(0, 24) + '…'), h('dt', {}, 'Size'), h('dd', {}, fmt.bytes(m.manifest.model_bytes)), h('dt', {}, 'Environment'), h('dd', {}, `Python ${m.manifest.environment.python} · scikit-learn ${m.manifest.environment.sklearn}`), h('dt', {}, 'Train time'), h('dd', {}, m.manifest.train_seconds + ' s')),
      h('strong', {}, 'Training-set medians (imputation values)'), h('div', { class: 'imputed' }, Object.entries(m.preprocessing.medians).map(([k, v]) => h('span', { class: 'chip' }, `${k} ${fmt.n(v, 2)}`))), h('strong', {}, 'Candidates compared on validation data'), h('div', { id: 'cm' }));
    const p = dialog({ title: m.id, body: b, confirm: 'Close', cancel: ' ' }); table($('#cm'), { cols: [{ key: 'name', label: 'Candidate', render: c => c.name.replace(/_/g, ' ') + (c.name === m.selected ? ' ✓' : '') }, { label: 'Val RMSE', num: true, render: c => fmt.n(c.val.rmse, 2) }, { label: 'Latency', num: true, render: c => c.latency_ms ? fmt.ms(c.latency_ms) : '—' }], rows: m.metrics.candidates, pageSize: 8 }); await p;
  }
  load();
})();
