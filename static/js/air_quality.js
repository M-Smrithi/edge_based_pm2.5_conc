(async function () {
  const { $, h, api, fmt, empty, clear, table } = UI; const body = $('#aq-body');
  const LAB = ['Good', 'Satisfactory', 'Moderate', 'Poor', 'Very poor', 'Severe'];
  let D;
  try { D = await api('/api/public/dashboard'); } catch (e) { return UI.errorBox(body, e); }
  if (!D.available) return empty(body, 'No air-quality data yet', 'The dashboard fills in once a dataset version has been published by an administrator.');
  const o = D.overall;
  const sel = h('select', { id: 'st', 'aria-label': 'Station' }, h('option', { value: '' }, `All stations (${D.stations.length})`), D.stations.map(s => h('option', { value: s.station }, `${s.station} — ${[s.city, s.state].filter(Boolean).join(', ') || 'unverified location'}`)));
  const kp = h('div', { class: 'grid g4' }), tl = h('div', { class: 'card' }), cat = h('div', { class: 'card' }), prof = h('div', { class: 'grid g2' }), sTab = h('div', { class: 'card' }), stTab = h('div', { class: 'card' });
  clear(body).append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('div', { class: 'grow' }, h('label', { for: 'st' }, 'Station'), sel))), kp, tl, h('div', { class: 'grid g2' }, cat, h('div', { class: 'card' }, h('h3', {}, 'Highest-PM2.5 states'), sTab)), prof, h('div', { class: 'card' }, h('h3', {}, 'Stations'), stTab));
  const kpi = (v, l, s) => h('div', { class: 'card kpi' }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, l), s ? h('div', { class: 's' }, s) : null);
  function monthDate(m) { const [y, mo] = m.split('-'); return +y + (+mo - 1) / 12; }
  async function render(code) {
    let data = D, s = null, monthly = D.monthly.map(x => ({ x: monthDate(x.month), y: x.mean, m: x.month }));
    if (code) { try { data = await api('/api/public/dashboard?station=' + encodeURIComponent(code)); } catch (e) { return UI.toast(e.message, 'err'); } s = data.selected.station; monthly = data.selected.monthly.map(x => ({ x: monthDate(x.month), y: x.mean, m: x.month })); }
    const src = s || o, share = s ? s.category_share : o.category_share;
    clear(kp).append(kpi(fmt.n(src.mean, 1), 'mean PM2.5 (µg/m³)', s ? `${s.city || s.station}${s.state ? ', ' + s.state : ''}` : 'all stations, all hours'), kpi(fmt.n(src.median, 1), 'median PM2.5 (µg/m³)', ''), kpi(fmt.n(src.p95, 1), '95th percentile (µg/m³)', ''), kpi(fmt.n(src.rows), 'hourly records', s ? `${fmt.day(s.first)} → ${fmt.day(s.last)}` : `${o.stations} stations`));
    clear(tl).append(h('h3', {}, 'Monthly mean PM2.5' + (s ? ' — ' + s.station : '')), h('div', { id: 'tl-c' }));
    Charts.line($('#tl-c'), { series: [{ name: 'Monthly mean', points: monthly }], xlabel: 'Year', ylabel: 'µg/m³', xfmt: v => Math.round(v), yfmt: v => fmt.n(v, 0), zero: true, title: 'Monthly mean PM2.5', tipx: x => { const m = monthly.reduce((a, b) => Math.abs(b.x - x) < Math.abs(a.x - x) ? b : a); return m.m; } });
    clear(cat).append(h('h3', {}, 'Share of hours by category'), h('p', { class: 'muted small' }, 'CPCB PM2.5 breakpoints (µg/m³): ' + D.bands.map(b => `${b.label} ${b.lo}–${b.hi ?? '+'}`).join(' · ')), h('div', { id: 'cat-c' }));
    Charts.share($('#cat-c'), LAB, share, true);
  }
  clear(sTab); table(sTab, { cols: [{ key: 'state', label: 'State' }, { key: 'stations', label: 'Stations', num: true }, { key: 'mean', label: 'Mean µg/m³', num: true, render: r => fmt.n(r.mean, 1) }], rows: D.states, pageSize: 8, sortKey: 'mean', desc: true });
  clear(prof).append(h('div', { class: 'card' }, h('h3', {}, 'Average by hour of day'), h('div', { id: 'hp' })), h('div', { class: 'card' }, h('h3', {}, 'Average by month'), h('div', { id: 'mp' })));
  Charts.bars($('#hp'), { groups: D.hour_profile.map((v, i) => ({ label: i % 3 === 0 ? String(i) : '', bars: [{ name: 'Mean', value: v, color: '#3157d5' }] })), ylabel: 'µg/m³', xlabel: 'Hour (local)', title: 'Mean PM2.5 by hour', yfmt: v => fmt.n(v, 0) });
  Charts.bars($('#mp'), { groups: D.month_profile.map((v, i) => ({ label: ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'][i], bars: [{ name: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i], value: v, color: '#e8833a' }] })), ylabel: 'µg/m³', xlabel: 'Month', title: 'Mean PM2.5 by month', yfmt: v => fmt.n(v, 0) });
  table(stTab, { cols: [{ key: 'station', label: 'Station' }, { key: 'city', label: 'City', render: r => r.city || '—' }, { key: 'state', label: 'State', render: r => r.state || '—' }, { key: 'mean', label: 'Mean', num: true, render: r => fmt.n(r.mean, 1) }, { key: 'p95', label: 'P95', num: true, render: r => fmt.n(r.p95, 1) }, { key: 'rows', label: 'Records', num: true, render: r => fmt.n(r.rows) },
    { label: 'Categories', render: r => { const d = h('div', { style: null }); Charts.share(d, LAB, r.category_share, false); d.style.minWidth = '120px'; return d; } }], rows: D.stations, search: ['station', 'city', 'state'], pageSize: 12, sortKey: 'mean', desc: true, onRow: r => { sel.value = r.station; render(r.station); window.scrollTo({ top: 0, behavior: 'smooth' }); } });
  sel.addEventListener('change', () => render(sel.value)); render('');
})();
