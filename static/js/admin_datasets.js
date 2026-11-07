(async function () {
  const { $, h, api, upload, fmt, clear, toast, dialog, statusBadge, table, empty } = UI; const page = $('#page'); const CAN = document.body.dataset.role === 'admin';
  const up = h('div', { class: 'card' }), reg = h('div', { class: 'card' }), ver = h('div', { class: 'card' }), bat = h('div', { class: 'card' });
  clear(page).append(up, reg, ver, bat);
  // ---------------- upload ----------------
  const queue = h('div', { class: 'stack mt' }), file = h('input', { type: 'file', multiple: true, accept: '.csv,text/csv', class: 'sr', id: 'fi' });
  const drop = h('div', { class: 'drop', tabindex: 0, role: 'button', 'aria-label': 'Choose station CSV files' }, h('strong', {}, 'Drop station CSV files here, or click to choose'), h('div', { class: 'muted small' }, 'Batch upload supported. Each file is validated against the schema; originals are stored unmodified and never overwritten.'));
  clear(up).append(h('h3', {}, 'Upload station files'), CAN ? h('div', {}, drop, file, queue) : h('div', { class: 'notice' }, 'Your role is read-only; uploads are disabled.'));
  if (CAN) {
    drop.onclick = () => file.click(); drop.onkeydown = e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), file.click());
    ['dragover', 'dragenter'].forEach(v => drop.addEventListener(v, e => { e.preventDefault(); drop.classList.add('over'); })); ['dragleave', 'drop'].forEach(v => drop.addEventListener(v, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => run([...e.dataTransfer.files])); file.onchange = () => { run([...file.files]); file.value = ''; };
  }
  async function run(files) {
    files = files.filter(f => f.name.toLowerCase().endsWith('.csv') || (toast(`${f.name}: only .csv files are accepted.`, 'err'), false)); if (!files.length) return;
    const panel = h('div', { class: 'card flat' }), bar = h('div', { class: 'bar' }, h('i')), sum = h('div', { class: 'small muted' }, `0 of ${files.length} processed`), list = h('div'); panel.append(h('div', { class: 'row' }, h('strong', {}, `Batch of ${files.length} file(s)`)), bar, sum, list); queue.prepend(panel);
    let batch = null, done = 0; const tally = {}, rows = [];
    for (const f of files) {
      const fd = new FormData(); fd.append('files', f, f.name); if (batch) fd.append('batch_id', batch);
      try { const r = await upload('/api/admin/files/upload', fd); batch = r.batch_id; const x = r.results[0]; rows.push({ file: f.name, ...x }); tally[x.status] = (tally[x.status] || 0) + 1; }
      catch (e) { rows.push({ file: f.name, status: 'error', reasons: [e.message] }); tally.error = (tally.error || 0) + 1; }
      done++; bar.firstChild.style.width = (done / files.length * 100) + '%'; sum.textContent = `${done} of ${files.length} processed · ` + Object.entries(tally).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(' · ');
    }
    clear(list); table(list, { cols: [{ key: 'file', label: 'File' }, { key: 'status', label: 'Result', render: r => r.status === 'error' ? UI.badge('error', 'bad') : statusBadge(r.status) }, { label: 'Rows', num: true, render: r => r.valid_rows != null ? fmt.n(r.valid_rows) + ' valid' : '—' },
      { label: 'Explanation', render: r => h('div', {}, (r.reasons || []).join(' · ') || (r.overlap ? '' : 'Schema verified.'), r.overlap ? h('div', { class: 'small muted' }, overlapText(r.overlap)) : null, r.status === 'duplicate' ? h('div', { class: 'small muted' }, 'Same bytes as a file already stored — this is a re-upload, not new data.') : null) }], rows, pageSize: 10 });
    toast(`Upload finished: ${Object.entries(tally).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(', ')}`, 'ok'); loadReg(); loadBatches();
  }
  const overlapText = o => o.kind === 'new_station_or_first_file' ? `First file for this station: ${fmt.n(o.new)} records.` : o.shared ? `${fmt.n(o.shared)} timestamps already present in ${o.with_files.filter(w => w.shared_timestamps).map(w => w.file_name).join(', ')} (duplicate records — de-duplicated at build); ${fmt.n(o.new)} new.` : `Extends existing station data: ${fmt.n(o.new)} new records, no overlap.`;
  // ---------------- registry ----------------
  let st = '', q = '', pg = 1;
  clear(reg).append(h('div', { class: 'row' }, h('h3', {}, 'File registry'), h('span', { class: 'right muted small', id: 'regcount' })),
    h('div', { class: 'row' }, h('div', { class: 'grow' }, h('label', { for: 'rq' }, 'Search'), h('input', { id: 'rq', type: 'search', placeholder: 'Filename or station' })), h('div', {}, h('label', { for: 'rs' }, 'Status'), h('select', { id: 'rs' }, [['', 'All'], ['accepted', 'Accepted'], ['accepted_recovered', 'Accepted (recovered)'], ['pending_review', 'Pending review'], ['rejected', 'Rejected']].map(([v, l]) => h('option', { value: v }, l))))), h('div', { id: 'regt', class: 'mt' }));
  $('#rq').oninput = () => { clearTimeout(window.__t); window.__t = setTimeout(() => { q = $('#rq').value; pg = 1; loadReg(); }, 300); }; $('#rs').onchange = () => { st = $('#rs').value; pg = 1; loadReg(); };
  async function loadReg() {
    const t = $('#regt'); let d; try { d = await api(`/api/admin/files?page=${pg}&size=15&status=${encodeURIComponent(st)}&q=${encodeURIComponent(q)}`); } catch (e) { return UI.errorBox(t, e, loadReg); }
    $('#regcount').textContent = `${fmt.n(d.total)} file(s)`;
    if (!d.rows.length) return empty(t, st || q ? 'No files match' : 'No files uploaded yet', st || q ? 'Try clearing the filters.' : 'Upload station CSV files above to begin.');
    clear(t); t.append(h('div', { class: 'tablewrap' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['File', 'Station', 'Status', 'Rows', 'Valid', 'Period', 'Uploaded', ''].map((x, i) => h('th', { class: i > 2 && i < 5 ? 'num' : '' }, x)))), h('tbody', {}, d.rows.map(r => h('tr', {}, h('td', {}, r.file_name), h('td', {}, r.station || '—'), h('td', {}, statusBadge(r.status)), h('td', { class: 'num' }, fmt.n(r.rows)), h('td', { class: 'num' }, fmt.n(r.valid_rows)), h('td', { class: 'small' }, r.ts_min ? fmt.day(r.ts_min) + ' → ' + fmt.day(r.ts_max) : '—'), h('td', { class: 'small' }, fmt.date(r.uploaded_utc)), h('td', {}, h('button', { class: 'btn sm', onclick: () => detail(r.id) }, 'Details'))))))));
    const pages = Math.ceil(d.total / d.size); t.append(h('div', { class: 'pager' }, h('span', {}, `Page ${d.page} of ${pages}`), h('button', { class: 'btn sm', disabled: pg <= 1, onclick: () => { pg--; loadReg(); } }, 'Previous'), h('button', { class: 'btn sm', disabled: pg >= pages, onclick: () => { pg++; loadReg(); } }, 'Next')));
  }
  async function detail(id) {
    let d; try { d = await api('/api/admin/files/' + id); } catch (e) { return toast(e.message, 'err'); }
    const a = d.audit, body = h('div', { class: 'stack' });
    body.append(h('dl', { class: 'kv' }, h('dt', {}, 'Status'), h('dd', {}, statusBadge(d.status)), h('dt', {}, 'Station'), h('dd', {}, d.station || '—'), h('dt', {}, 'SHA-256'), h('dd', { class: 'mono' }, d.sha256.slice(0, 20) + '…'), h('dt', {}, 'Size'), h('dd', {}, fmt.bytes(d.size_bytes)), h('dt', {}, 'Rows'), h('dd', {}, `${fmt.n(a.rows)} (valid ${fmt.n(a.valid_rows)}, complete-case ${fmt.n(a.complete_case_rows)})`), h('dt', {}, 'Period'), h('dd', {}, a.ts_min ? `${fmt.day(a.ts_min)} → ${fmt.day(a.ts_max)}` : '—'), h('dt', {}, 'PM2.5 target'), h('dd', {}, a.target_status || '—'), h('dt', {}, 'Location'), h('dd', {}, a.station_meta && a.station_meta.verified ? `${a.station_meta.city}, ${a.station_meta.state} (verified from stations_info.csv)` : 'Not verified (no metadata match)')));
    if (d.reasons) body.append(h('div', { class: 'notice warn' }, d.reasons));
    if (a.mapping_log && a.mapping_log.length) body.append(h('div', {}, h('strong', {}, 'Header recovery log'), h('ul', {}, a.mapping_log.map(m => h('li', { class: 'small' }, `${m.feature} ← “${m.raw}” (${m.action}${m.factor !== 1 ? ', ×' + m.factor : ''}): ${m.rationale}`)))));
    if (a.missing_pct_by_feature) body.append(h('div', {}, h('strong', {}, 'Missing share per sensor'), h('div', { class: 'imputed' }, Object.entries(a.missing_pct_by_feature).map(([k, v]) => h('span', { class: 'chip' + (v == null ? ' imp' : '') }, `${k} ${v == null ? 'unavailable' : fmt.pct(v)}`)))));
    if (d.overlap) body.append(h('div', { class: 'notice' }, overlapText(d.overlap)));
    const acts = [];
    if (CAN && d.status === 'pending_review') {
      (a.proposals || []).forEach(p => acts.push(h('div', { class: 'card flat' }, h('div', { class: 'small' }, `${p.feature}: column “${p.raw}” has no unit. ${p.evidence}.`), h('button', { class: 'btn sm', onclick: () => decide(id, { action: 'approve_blank_unit', feature: p.feature }, `I assert that “${p.raw}” is in ${p.canonical_unit}`) }, `Approve ${p.feature} as ${p.canonical_unit}`))));
      acts.push(h('div', { class: 'card flat' }, h('div', { class: 'small' }, `Sensors unavailable in this file: ${(a.structural_absence || []).join(', ')}. Approving admits the file with those inputs always missing (they will be median-imputed). This is a modelling decision and is audit-logged.`), h('button', { class: 'btn sm', onclick: () => decide(id, { action: 'approve_structural_absence' }, 'Admit file with unavailable sensors') }, 'Admit with unavailable sensors')));
    }
    if (CAN && d.status !== 'rejected') acts.push(h('button', { class: 'btn sm danger', onclick: () => decide(id, { action: 'reject' }, 'Reject this file', true) }, 'Reject file'));
    if (CAN && Object.keys(d.decisions).length) acts.push(h('button', { class: 'btn sm', onclick: () => decide(id, { action: 'reopen' }, 'Remove all decisions') }, 'Undo decisions'));
    if (acts.length) body.append(h('div', { class: 'stack' }, h('strong', {}, 'Review actions'), ...acts));
    const ok = await dialog({ title: d.file_name, body, confirm: 'Close', cancel: ' ' }); 
  }
  async function decide(id, dec, text, danger) {
    document.querySelectorAll('.modal-bg').forEach(m => m.remove());
    if (!(await dialog({ title: 'Confirm decision', body: text + '. This is recorded in the audit log.', confirm: 'Confirm', danger }))) return;
    try { const r = await api(`/api/admin/files/${id}/decision`, { method: 'POST', json: dec }); toast('Updated: ' + r.status.replace(/_/g, ' '), 'ok'); loadReg(); loadVer(); } catch (e) { toast(e.message, 'err'); }
  }
  // ---------------- versions ----------------
  async function loadVer() {
    let d; try { d = await api('/api/admin/datasets'); } catch (e) { return UI.errorBox(ver, e, loadVer); }
    clear(ver).append(h('div', { class: 'row' }, h('h3', {}, 'Dataset versions & benchmarks'), CAN ? h('button', { class: 'btn primary right', disabled: !d.accepted_files, onclick: build }, 'Build new dataset version') : null),
      h('p', { class: 'muted small' }, `${fmt.n(d.accepted_files)} accepted file(s) are eligible. A version is an immutable snapshot of all accepted files; duplicates are removed by (station, timestamp). Training happens in the Model Training Center.`), h('div', { id: 'vt' }), h('h3', { class: 'mt' }, 'Frozen benchmarks'), h('div', { id: 'bt' }));
    d.rows.length ? table($('#vt'), { cols: [{ key: 'id', label: 'Version' }, { key: 'created_utc', label: 'Created', render: r => fmt.date(r.created_utc) }, { key: 'n_files', label: 'Files', num: true }, { key: 'n_stations', label: 'Stations', num: true }, { key: 'rows', label: 'Records', num: true, render: r => fmt.n(r.rows) }, { label: '', render: r => h('button', { class: 'btn sm', onclick: () => vdetail(r.id) }, 'Manifest') }], rows: d.rows, pageSize: 8 }) : empty($('#vt'), 'No dataset version yet', 'Accepted files become a dataset version when you build one.');
    d.benchmarks.length ? table($('#bt'), { cols: [{ key: 'id', label: 'Benchmark' }, { key: 'dataset_version', label: 'Frozen from' }, { key: 'created_utc', label: 'Created', render: r => fmt.date(r.created_utc) }, { label: 'Active', render: r => r.active ? UI.badge('active', 'ok') : '' }, { label: 'Checksum', render: r => h('span', { class: 'mono small' }, (r.sha256 || '').slice(0, 12)) }], rows: d.benchmarks, pageSize: 8 }) : empty($('#bt'), 'No benchmark yet', 'The first benchmark is frozen automatically when the first dataset version is built.');
  }
  async function build() {
    const note = h('input', { type: 'text', placeholder: 'Optional note (e.g. “added 2023 stations”)', 'aria-label': 'Note' }), nb = h('input', { type: 'checkbox', id: 'nb', style: null });
    const extra = h('div', {}, h('div', { class: 'field' }, h('label', { for: 'nbn' }, 'Note'), note), h('label', { class: 'inline' }, nb, h('span', {}, 'Freeze a NEW benchmark from this version (new results will not be comparable to old benchmarks)')));
    if (!(await dialog({ title: 'Build dataset version', body: 'All currently accepted files are snapshotted into a new immutable version. Existing versions are never modified.', confirm: 'Build', extra }))) return;
    try { const r = await api('/api/admin/jobs', { method: 'POST', json: { kind: 'build_dataset', params: { note: note.value, new_benchmark: nb.checked } } }); toast(`Job #${r.job_id} queued — follow it in the Model Training Center.`, 'ok'); } catch (e) { toast(e.message, 'err'); }
  }
  async function vdetail(id) {
    let m; try { m = await api('/api/admin/datasets/' + id); } catch (e) { return toast(e.message, 'err'); }
    const b = h('div', { class: 'stack' }, h('dl', { class: 'kv' }, h('dt', {}, 'Records'), h('dd', {}, fmt.n(m.rows) + ` (from ${fmt.n(m.rows_before_dedup)} before de-duplication)`), h('dt', {}, 'Duplicates'), h('dd', {}, `${fmt.n(m.duplicates.identical)} identical, ${fmt.n(m.duplicates.conflicting)} conflicting (first kept)`), h('dt', {}, 'Complete-case'), h('dd', {}, fmt.n(m.complete_case_rows)), h('dt', {}, 'Period'), h('dd', {}, `${fmt.day(m.ts_min)} → ${fmt.day(m.ts_max)}`), h('dt', {}, 'Checksum'), h('dd', { class: 'mono small' }, m.records_sha256.slice(0, 24) + '…')), h('div', { id: 'mf' }));
    const p = dialog({ title: `Dataset ${id}`, body: b, confirm: 'Close', cancel: ' ' }); table($('#mf'), { cols: [{ key: 'file_name', label: 'File' }, { key: 'unique_contributed', label: 'Unique', num: true, render: r => fmt.n(r.unique_contributed) }, { key: 'duplicates_dropped', label: 'Dup. dropped', num: true }], rows: m.files, search: ['file_name'], pageSize: 6 }); await p;
  }
  async function loadBatches() {
    let d; try { d = await api('/api/admin/batches'); } catch (e) { return UI.errorBox(bat, e); }
    clear(bat).append(h('h3', {}, 'Upload history'), h('div', { id: 'bh' })); d.rows.length ? table($('#bh'), { cols: [{ key: 'id', label: 'Batch', render: r => '#' + r.id }, { key: 'created_utc', label: 'When', render: r => fmt.date(r.created_utc) }, { key: 'user', label: 'By', render: r => r.user || 'command line' }, { key: 'files', label: 'Files', num: true }, { key: 'accepted', label: 'Accepted', num: true }, { key: 'pending', label: 'Pending', num: true }, { key: 'rejected', label: 'Rejected', num: true }], rows: d.rows, pageSize: 8 }) : empty($('#bh'), 'No uploads yet', '');
  }
  loadReg(); loadVer(); loadBatches();
})();
