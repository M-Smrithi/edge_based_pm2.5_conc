(async function () {
  const { $, h, api, fmt, empty, clear } = UI; const k = $('#kpis'), ch = $('#home-chart'), note = $('#chart-note');
  const kpi = (v, l, s) => h('div', { class: 'card kpi', 'aria-label': `${v} — ${l}` }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, l), s ? h('div', { class: 's' }, s) : null);
  try {
    const [st, rs] = await Promise.all([api('/api/public/status'), api('/api/public/research')]);
    clear(k);
    if (st.data) k.append(kpi(fmt.n(st.data.stations), 'monitoring stations', `${fmt.n(st.data.rows)} hourly records · ${fmt.day(st.data.first)} → ${fmt.day(st.data.last)}`));
    else k.append(kpi('—', 'monitoring stations', 'No dataset has been published yet'));
    if (st.model) {
      const t = (st.model.test || {}).test_temporal;
      k.append(kpi(t ? fmt.n(t.rmse, 1) : '—', 'RMSE on unseen later period (µg/m³)', `${st.model.algorithm} · MAE ${t ? fmt.n(t.mae, 1) : '—'}`), kpi(fmt.ms(st.model.latency_ms), 'single-record inference benchmark', 'End-to-end processing latency is measured separately and varies by experiment.'));
    } else k.append(kpi('—', 'RMSE on unseen later period', 'No model is active yet'), kpi('—', 'single-record inference benchmark', ''));
    if (rs.available) {
      const s = rs.summary.filter(r => r.test_set === 'temporal'); const at = (p, r) => s.find(x => x.pattern === p && x.missing_rate === r);
      const r20 = at('random', 0.2);
      k.append(kpi(r20 ? '+' + fmt.n(r20.rmse_increase_pct, 0) + '%' : '—', 'RMSE increase at 20% missing readings', 'random pattern, temporal test'));
      const base = s.find(x => x.missing_rate === 0);
      const mk = (pat, color, dash) => ({ name: pat[0].toUpperCase() + pat.slice(1), color, dash, points: [{ x: 0, y: base.rmse, err: 0 }].concat(s.filter(x => x.pattern === pat).sort((a, b) => a.missing_rate - b.missing_rate).map(x => ({ x: x.missing_rate * 100, y: x.rmse, err: x.rmse_std }))) });
      Charts.line(ch, { series: [mk('random', '#3157d5'), mk('consecutive', '#e8833a', '6 4')], xlabel: 'Missing input readings (%)', ylabel: 'RMSE (µg/m³)', xticks: [0, 10, 20].map(v => ({ v, label: v + '%' })), yfmt: v => v, title: 'RMSE versus missing readings', tipx: x => x + '% missing' });
      note.textContent = `Mean ± standard deviation over ${rs.experiment.trials} seeded trials on ${fmt.n(rs.experiment.test_rows.temporal)} frozen test records.`;
    } else { k.append(kpi('—', 'RMSE increase at 20% missing', 'No experiment has been run yet')); empty(ch, 'No experiment results yet', 'Results appear here after an administrator runs the experiments.'); }
  } catch (e) { UI.errorBox(k, e); }
})();
