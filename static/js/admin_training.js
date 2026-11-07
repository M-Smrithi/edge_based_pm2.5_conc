(async function () {
  const { $, h, api, fmt, clear, toast, dialog, statusBadge, table, empty, poll } = UI; const page = $('#page'); const CAN = document.body.dataset.role === 'admin';
  const ctl = h('div', { class: 'card' }), jl = h('div', { class: 'card' }), jd = h('div');
  clear(page).append(ctl, jl, jd);
  let ds = [], models = [];
  async function loadCtl() {
    let o, d; try { [o, d] = await Promise.all([api('/api/admin/overview'), api('/api/admin/datasets')]); } catch (e) { return UI.errorBox(ctl, e, loadCtl); }
    ds = d.rows;
    const sel = h('select', { id: 'ds' }, ds.length ? ds.map(x => h('option', { value: x.id }, `${x.id} — ${fmt.n(x.rows)} records`)) : h('option', { value: '' }, 'No dataset version yet'));
    const ne = h('input', { id: 'ne', type: 'number', min: 5, max: 300, placeholder: 'default 60' }), ms = h('input', { id: 'ms', type: 'number', step: 0.05, min: 0.01, max: 1, placeholder: 'default 0.2' }), sd = h('input', { id: 'sd', type: 'number', min: 0, placeholder: 'default 42' });
    clear(ctl).append(h('h3', {}, 'Train & retrain'),
      o.new_files_since_latest ? h('div', { class: 'notice warn' }, 'Accepted files changed since the last dataset version — retraining will build a new version first.') : null,
      CAN ? h('div', { class: 'stack' }, h('div', { class: 'card flat' }, h('strong', {}, 'Retrain on all accumulated data'), h('p', { class: 'muted small' }, 'Builds a new dataset version if accepted files changed, trains all candidates on the frozen benchmark, selects on validation only, then runs the missing-data experiments. The result is a CANDIDATE model; the active model is not touched until you promote it.'),
        h('button', { class: 'btn primary', onclick: () => retrain() }, 'Retrain on all accumulated data')),
        h('details', {}, h('summary', {}, 'Advanced: train on a specific dataset version'), h('div', { class: 'grid g2 mt' }, h('div', { class: 'field' }, h('label', { for: 'ds' }, 'Dataset version'), sel), h('div', { class: 'field' }, h('label', { for: 'ne' }, 'Trees per forest'), ne), h('div', { class: 'field' }, h('label', { for: 'ms' }, 'Bootstrap fraction per tree'), ms, h('div', { class: 'hint' }, 'Every training row is eligible for every tree; no rows are discarded.')), h('div', { class: 'field' }, h('label', { for: 'sd' }, 'Seed'), sd)),
          h('button', { class: 'btn', disabled: !ds.length, onclick: () => start('train', { dataset_version: sel.value, n_estimators: ne.value || null, max_samples: ms.value || null, seed: sd.value || null }) }, 'Train candidate model'))) : h('div', { class: 'notice' }, 'Your role is read-only.'));
  }
  async function retrain() {
    const t = h('input', { type: 'number', min: 1, max: 50, placeholder: 'settings default' }), nb = h('input', { type: 'checkbox' });
    const extra = h('div', {}, h('div', { class: 'field' }, h('label', {}, 'Trials per missing-data scenario'), t), h('label', { class: 'inline' }, nb, h('span', {}, 'Freeze a new benchmark (breaks comparability with earlier results)')));
    if (!(await dialog({ title: 'Retrain on all accumulated data', body: 'This can take several minutes. You can follow progress below and cancel at any time.', confirm: 'Start', extra }))) return;
    start('retrain', { run_experiment: true, new_benchmark: nb.checked, trials: t.value || null });
  }
  async function start(kind, params) {
    for (const k of Object.keys(params)) if (params[k] === null || params[k] === '') delete params[k];
    try { const r = await api('/api/admin/jobs', { method: 'POST', json: { kind, params } }); toast(`Job #${r.job_id} queued`, 'ok'); loadJobs(); openJob(r.job_id); } catch (e) { toast(e.message, 'err'); }
  }
  let selected = null, stopLog = null;
  async function loadJobs() {
    let d; try { d = await api('/api/admin/jobs?size=15'); } catch (e) { return UI.errorBox(jl, e, loadJobs); }
    clear(jl).append(h('h3', {}, 'Jobs'), h('div', { id: 'jt' }));
    d.rows.length ? table($('#jt'), { cols: [{ key: 'id', label: 'Job', render: r => '#' + r.id }, { key: 'kind', label: 'Kind', render: r => r.kind.replace(/_/g, ' ') }, { key: 'status', label: 'Status', render: r => statusBadge(r.status) },
      { label: 'Progress', render: r => h('div', { class: 'progress-cell' }, h('div', { class: 'bar' }, h('i', { class: '', 'data-w': r.progress })), h('div', { class: 'small muted' }, r.message || '')) }, { key: 'created_utc', label: 'Created', render: r => fmt.date(r.created_utc) },
      { label: '', render: r => h('div', { class: 'inline' }, h('button', { class: 'btn sm', onclick: () => openJob(r.id) }, 'Log'), CAN && (r.status === 'running' || r.status === 'queued') ? h('button', { class: 'btn sm danger', onclick: () => cancel(r.id) }, 'Cancel') : null) }], rows: d.rows, pageSize: 15 }) : empty($('#jt'), 'No jobs yet', 'Start a training job above.');
    $('#jt').querySelectorAll('i[data-w]').forEach(i => i.style.width = (i.dataset.w * 100) + '%'); return d;
  }
  async function cancel(id) { if (!(await dialog({ title: `Cancel job #${id}?`, body: 'The job will be stopped. Partial outputs are discarded and the active model is not affected.', confirm: 'Cancel job', danger: true }))) return; try { await api(`/api/admin/jobs/${id}/cancel`, { method: 'POST' }); toast('Cancelled', 'ok'); loadJobs(); } catch (e) { toast(e.message, 'err'); } }
  async function openJob(id) {
    selected = id; clear(jd).append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('h3', {}, `Job #${id}`), h('span', { id: 'jst' })), h('div', { class: 'bar' }, h('i', { id: 'jbar' })), h('p', { class: 'small muted', id: 'jmsg' }), h('div', { id: 'jres' }), h('pre', { class: 'log', id: 'jlog', tabindex: 0, 'aria-label': 'Job log' }, 'Loading…')));
    if (stopLog) stopLog(); stopLog = poll(async () => { if (selected !== id) return; const j = await api('/api/admin/jobs/' + id); $('#jst').replaceChildren(statusBadge(j.status)); $('#jbar').style.width = (j.progress * 100) + '%'; $('#jmsg').textContent = j.error ? 'Error: ' + j.error : j.message || ''; const lg = $('#jlog'); const atEnd = lg.scrollTop + lg.clientHeight >= lg.scrollHeight - 30; lg.textContent = j.log || '(no output yet)'; if (atEnd) lg.scrollTop = lg.scrollHeight;
      const rs = $('#jres'); if (j.result) { const r = JSON.parse(j.result); rs.replaceChildren(h('div', { class: 'notice ok' }, 'Result: ' + Object.entries(r).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · '), r.model_id ? h('span', {}, ' · ', h('a', { href: '/admin/models' }, 'Review in Model Registry →')) : null)); } }, 2500);
  }
  await loadCtl(); const first = await loadJobs(); if (first && first.rows.length) openJob((first.rows.find(r => r.status === 'running') || first.rows[0]).id);
  let sig = ''; poll(async () => { const d = await api('/api/admin/jobs?size=15'); const s = d.rows.map(r => r.id + r.status + Math.round(r.progress * 100) + (r.message || '')).join('|'); if (s !== sig) { sig = s; await loadJobs(); } }, 4000);
})();
