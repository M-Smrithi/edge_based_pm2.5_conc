(async function () {
  const { $, h, api, upload, fmt, clear, toast, empty } = UI;
  let M, status;
  try { [M, status] = await Promise.all([api('/api/public/methodology'), api('/api/public/status')]); } catch (e) { return UI.errorBox($('#ps-status'), e); }
  if (!status.model_available) $('#ps-status').append(h('div', { class: 'notice warn', role: 'status' }, 'No model is active yet, so predictions are unavailable. An administrator needs to train and promote a model first.'));
  else $('#ps-status').append(h('div', { class: 'notice' }, `Active model: ${status.model.id} (${status.model.algorithm}).`));
  const tabs = { one: [$('#tab-one'), $('#p-one')], csv: [$('#tab-csv'), $('#p-csv')] };
  Object.entries(tabs).forEach(([k, [b, p]]) => b.addEventListener('click', () => Object.entries(tabs).forEach(([k2, [b2, p2]]) => { b2.setAttribute('aria-selected', k === k2); p2.hidden = k !== k2; })));
  const F = $('#one-fields'); const inputs = {};
  M.features.forEach(f => { const i = h('input', { type: 'text', inputmode: 'decimal', id: 'f-' + f.name, name: f.name, placeholder: 'leave empty if unavailable', autocomplete: 'off' }); inputs[f.name] = i;
    F.append(h('div', { class: 'field' }, h('label', { for: 'f-' + f.name }, `${f.label} (${f.name})`), i, h('div', { class: 'hint' }, `${f.unit} · valid ${f.valid_range[0]}–${f.valid_range[1]}`))); });
  const out = $('#one-result'), BAND = ['#2e9e6b', '#8bbf3f', '#e5b829', '#e8833a', '#d64545', '#8c2d5a'], BL = M.bands.map(b => b.label);
  $('#one-form').addEventListener('reset', () => clear(out).append(h('div', { class: 'empty' }, h('h3', {}, 'No estimate yet'), h('p', {}, 'Fill in any readings and press Estimate.'))));
  $('#one-form').addEventListener('submit', async e => {
    e.preventDefault(); const features = {}; for (const [k, i] of Object.entries(inputs)) if (i.value.trim() !== '') features[k] = i.value.trim();
    const btn = e.submitter; btn.disabled = true;
    try {
      const r = await api('/api/public/predict', { method: 'POST', json: { features } });
      const c = BAND[BL.indexOf(r.category)] || '#555';
      clear(out).append(h('div', { class: 'result', role: 'status' }, h('div', {}, h('div', { class: 'muted small' }, 'Estimated PM2.5'), h('div', { class: 'big' }, fmt.n(r.prediction, 1), h('span', { class: 'muted small' }, ' µg/m³'))), h('span', { class: 'pill', style: null, id: 'pill' }, r.category)),
        h('p', { class: 'small muted' }, `${r.n_provided} of ${M.features.length} readings used. ${r.missing.length ? 'The rest were substituted:' : 'No substitution was needed.'}`),
        h('div', { class: 'imputed' }, M.features.map(f => r.missing.includes(f.name) ? h('span', { class: 'chip imp', title: r.invalid.includes(f.name) ? 'Invalid or out of range' : 'Not provided' }, `${f.name} → ${fmt.n(r.imputed[f.name], 2)} ${f.unit}${r.invalid.includes(f.name) ? ' (invalid input)' : ''}`) : h('span', { class: 'chip' }, `${f.name} = ${features[f.name]}`))),
        r.unknown_fields.length ? h('p', { class: 'small muted' }, 'Ignored fields: ' + r.unknown_fields.join(', ')) : null,
        h('p', { class: 'small muted' }, `Latency (simulation on the server): preprocess ${fmt.ms(r.latency_ms.preprocess)}, inference ${fmt.ms(r.latency_ms.inference)}. Model ${r.model_id}.`), h('p', { class: 'small muted' }, r.note));
      $('#pill').style.background = c;
    } catch (err) { toast(err.message, 'err'); } finally { btn.disabled = false; }
  });
  const drop = $('#drop'), file = $('#file'), res = $('#csv-result');
  drop.addEventListener('click', () => file.click()); drop.addEventListener('keydown', e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), file.click()));
  ['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); })); ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => e.dataTransfer.files[0] && send(e.dataTransfer.files[0])); file.addEventListener('change', () => file.files[0] && send(file.files[0]));
  async function send(f) {
    if (!f.name.toLowerCase().endsWith('.csv')) return toast('Please choose a .csv file.', 'err');
    if (f.size > 5 * 1024 * 1024) return toast('File is larger than 5 MB.', 'err');
    clear(res).append(h('div', { class: 'card' }, h('div', { class: 'bar' }, h('i', { id: 'pg' })), h('p', { class: 'muted small' }, 'Uploading and predicting…')));
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await upload('/api/public/predict-csv', fd, p => $('#pg').style.width = (p * 100) + '%'); file.value = '';
      const cols = ['timestamp', 'station', ...M.features.map(x => x.name), 'n_imputed', 'pm25_prediction', 'category'].filter(c => r.preview.some(x => c in x));
      clear(res).append(h('div', { class: 'card stack' }, h('div', { class: 'row' }, h('h3', {}, `${fmt.n(r.rows)} rows predicted`), h('a', { class: 'btn primary right', href: '/api/public/predict-download/' + r.token, download: '' }, 'Download results (CSV)')),
        h('div', { class: 'grid g3' }, h('div', { class: 'kpi' }, h('div', { class: 'v' }, fmt.n(r.mean_prediction, 1)), h('div', { class: 'l' }, 'mean estimate µg/m³')), h('div', { class: 'kpi' }, h('div', { class: 'v' }, r.recognised.length + '/' + M.features.length), h('div', { class: 'l' }, 'sensor columns found')), h('div', { class: 'kpi' }, h('div', { class: 'v' }, fmt.n(r.rows_all_sensors_missing)), h('div', { class: 'l' }, 'rows with no usable sensor'))),
        r.absent_sensors.length ? h('div', { class: 'notice warn' }, 'Columns not found (imputed for every row): ' + r.absent_sensors.join(', ')) : null, r.conversions.length ? h('div', { class: 'notice' }, 'Unit conversions applied: ' + r.conversions.join('; ')) : null,
        r.non_numeric_values ? h('div', { class: 'notice warn' }, `${r.non_numeric_values} non-numeric value(s) were treated as missing.`) : null, r.unrecognised.length ? h('p', { class: 'small muted' }, 'Ignored columns: ' + r.unrecognised.join(', ')) : null,
        r.evaluation ? h('div', { class: 'notice ok' }, `Your file includes PM2.5 actuals: MAE ${fmt.n(r.evaluation.mae, 2)}, RMSE ${fmt.n(r.evaluation.rmse, 2)} µg/m³ over ${fmt.n(r.evaluation.n)} rows.`) : null,
        h('div', {}, h('div', { class: 'small muted' }, 'Missing share by sensor (before imputation)'), h('div', { class: 'imputed' }, M.features.map(f => h('span', { class: 'chip' + (r.missing_pct_by_sensor[f.name] > 0 ? ' imp' : '') }, `${f.name} ${fmt.n(r.missing_pct_by_sensor[f.name], 1)}%`)))),
        h('div', { id: 'prev' }), h('p', { class: 'small muted' }, `${r.note} Download link expires after ${r.expires_hours} hours.`)));
      UI.table($('#prev'), { cols: cols.map(c => ({ key: c, label: c, num: c !== 'timestamp' && c !== 'station' && c !== 'category', render: x => x[c] == null ? h('span', { class: 'muted' }, 'imputed') : (typeof x[c] === 'number' ? fmt.n(x[c], c === 'n_imputed' ? 0 : 2) : x[c]) })), rows: r.preview, pageSize: 10 });
    } catch (e) { clear(res).append(h('div', { class: 'notice bad', role: 'alert' }, e.message)); }
  }
})();
