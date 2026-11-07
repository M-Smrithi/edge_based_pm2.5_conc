(async function () {
  const { $, h, api, fmt, clear, statusBadge, table } = UI; const page = $('#page');
  async function load() {
    let o; try { o = await api('/api/admin/overview'); } catch (e) { return UI.errorBox(page, e, load); }
    const kpi = (v, l, s, href) => h('a', { class: 'card kpi', href: href || null, style: null }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, l), s ? h('div', { class: 's' }, s) : null);
    const acc = o.files.accepted + o.files.accepted_recovered;
    clear(page).append(
      o.new_files_since_latest ? h('div', { class: 'notice warn' }, 'Accepted files have changed since the latest dataset version. ', h('a', { href: '/admin/training' }, 'Retrain on all accumulated data →')) : null,
      !o.active_model ? h('div', { class: 'notice' }, 'No model is active. The public Prediction Studio is disabled until a model is promoted in the ', h('a', { href: '/admin/models' }, 'Model Registry'), '.') : null,
      h('div', { class: 'grid g4' }, kpi(fmt.n(acc), 'accepted files', `${o.files.pending_review} pending review · ${o.files.rejected} rejected`, '/admin/datasets'), kpi(o.latest_dataset || '—', 'latest dataset version', `${o.datasets} version(s) total`, '/admin/datasets'),
        kpi(o.active_model ? o.active_model.id : '—', 'active model', o.active_model ? o.active_model.selected.replace(/_/g, ' ') : `${o.models.candidate} candidate(s)`, '/admin/models'), kpi(String(o.jobs_running + o.jobs_queued), 'jobs running / queued', `${o.jobs_failed_recent} failed in last 7 days`, '/admin/training')),
      h('div', { class: 'grid g2' }, h('div', { class: 'card' }, h('h3', {}, 'Recent jobs'), h('div', { id: 'rj' })), h('div', { class: 'card' }, h('h3', {}, 'Recent activity'), h('div', { id: 'ra' }))),
      h('div', { class: 'grid g3' }, h('div', { class: 'card kpi' }, h('div', { class: 'v' }, fmt.n(o.experiments)), h('div', { class: 'l' }, 'experiments recorded')), h('div', { class: 'card kpi' }, h('div', { class: 'v' }, fmt.n(o.storage_mb, 0) + ' MB'), h('div', { class: 'l' }, 'storage used')), h('div', { class: 'card kpi' }, h('div', { class: 'v' }, fmt.n(o.users)), h('div', { class: 'l' }, 'active users'))));
    o.recent_jobs.length ? table($('#rj'), { cols: [{ key: 'id', label: '#', render: r => '#' + r.id }, { key: 'kind', label: 'Kind' }, { key: 'status', label: 'Status', render: r => statusBadge(r.status) }, { label: 'Progress', render: r => fmt.n(r.progress * 100, 0) + '%' }], rows: o.recent_jobs, pageSize: 5 }) : UI.empty($('#rj'), 'No jobs yet', 'Jobs appear when datasets are built or models trained.');
    o.recent_audit.length ? table($('#ra'), { cols: [{ key: 'ts', label: 'When', render: r => fmt.date(r.ts) }, { key: 'action', label: 'Action' }, { key: 'target', label: 'Target', render: r => r.target || '—' }], rows: o.recent_audit, pageSize: 8 }) : UI.empty($('#ra'), 'No activity yet', '');
  }
  load(); UI.poll(async () => { const o = await api('/api/admin/overview'); if (o.jobs_running || o.jobs_queued) load(); }, 8000);
})();
