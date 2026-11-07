/* Tiny dependency-free SVG chart library: line, bars (grouped, error bars), horizontal bars, scatter, stacked share bar. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const PAL = ['#3157d5', '#e8833a', '#177a4d', '#8c2d5a', '#0f8aa6', '#b08a00'];
  const el = (n, a, ...k) => { const e = document.createElementNS(NS, n); for (const [x, v] of Object.entries(a || {})) if (v != null) e.setAttribute(x, v); k.flat().forEach(c => c != null && e.append(c.nodeType ? c : document.createTextNode(c))); return e; };
  let tip; const showTip = (e, html) => { if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; document.body.append(tip); } tip.textContent = html; tip.style.left = Math.min(innerWidth - 270, e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; tip.hidden = false; };
  const hideTip = () => tip && (tip.hidden = true);
  function nice(max) { if (max <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(max))), f = max / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; }
  function ticks(lo, hi, n = 5) { const span = hi - lo, step = nice(span / n); const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10)); return out; }
  function frame(host, { w = 720, h = 320, title, desc, m = { l: 56, r: 16, t: 14, b: 44 } }) {
    host.textContent = ''; host.classList.add('chart');
    const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': title || 'chart' }, title ? el('title', {}, title) : null, desc ? el('desc', {}, desc) : null);
    host.append(svg); return { svg, w, h, m, iw: w - m.l - m.r, ih: h - m.t - m.b };
  }
  function axes(f, { xt, yt, xl, yl, xfmt = v => v, yfmt = v => v, ylo, yhi }) {
    const g = el('g'); f.svg.append(g);
    yt.forEach(v => { const y = f.m.t + f.ih - (v - ylo) / (yhi - ylo) * f.ih; g.append(el('line', { x1: f.m.l, x2: f.m.l + f.iw, y1: y, y2: y, class: 'gridl' }), el('text', { x: f.m.l - 8, y: y + 4, 'text-anchor': 'end' }, yfmt(v))); });
    xt.forEach(t => g.append(el('text', { x: t.x, y: f.m.t + f.ih + 18, 'text-anchor': 'middle' }, t.label)));
    g.append(el('line', { x1: f.m.l, x2: f.m.l + f.iw, y1: f.m.t + f.ih, y2: f.m.t + f.ih, class: 'ax' }));
    if (xl) g.append(el('text', { x: f.m.l + f.iw / 2, y: f.h - 6, 'text-anchor': 'middle' }, xl));
    if (yl) g.append(el('text', { transform: `rotate(-90)`, x: -(f.m.t + f.ih / 2), y: 14, 'text-anchor': 'middle' }, yl));
  }
  function legend(host, items) { const d = document.createElement('div'); d.className = 'legend'; items.forEach(i => { const s = document.createElement('span'); const k = document.createElement('i'); k.style.background = i.color; if (i.dash) k.style.opacity = .55; s.append(k, i.name); d.append(s); }); host.append(d); }
  /* line: series [{name,color,dash,points:[{x,y,err}]}]; x numeric or {date}. */
  function line(host, o) {
    const f = frame(host, o); const all = o.series.flatMap(s => s.points);
    let xs = all.map(p => p.x), xlo = Math.min(...xs), xhi = Math.max(...xs); if (xlo === xhi) { xlo -= 1; xhi += 1; }
    let ylo = o.ymin ?? Math.min(...all.map(p => p.y - (p.err || 0))), yhi = Math.max(...all.map(p => p.y + (p.err || 0)));
    const pad = (yhi - ylo) * .08 || 1; if (o.ymin == null) ylo = Math.max(o.zero ? 0 : -Infinity, ylo - pad); yhi += pad; if (o.zero) ylo = 0;
    const X = x => f.m.l + (x - xlo) / (xhi - xlo) * f.iw, Y = y => f.m.t + f.ih - (y - ylo) / (yhi - ylo) * f.ih;
    const xt = (o.xticks || ticks(xlo, xhi, 6).map(v => ({ v, label: o.xfmt ? o.xfmt(v) : v }))).map(t => ({ x: X(t.v), label: t.label }));
    axes(f, { xt, yt: ticks(ylo, yhi), xl: o.xlabel, yl: o.ylabel, yfmt: o.yfmt, ylo, yhi });
    o.series.forEach((s, i) => {
      const c = s.color || PAL[i % PAL.length], pts = s.points.filter(p => p.y != null);
      f.svg.append(el('path', { d: pts.map((p, j) => (j ? 'L' : 'M') + X(p.x).toFixed(1) + ' ' + Y(p.y).toFixed(1)).join(''), fill: 'none', stroke: c, 'stroke-width': s.width || 2, 'stroke-dasharray': s.dash || null, 'stroke-linejoin': 'round' }));
      if (pts.length <= 60) pts.forEach(p => {
        if (p.err) f.svg.append(el('line', { x1: X(p.x), x2: X(p.x), y1: Y(p.y - p.err), y2: Y(p.y + p.err), stroke: c, 'stroke-width': 1.4 }));
        f.svg.append(el('circle', { cx: X(p.x), cy: Y(p.y), r: 3.6, fill: '#fff', stroke: c, 'stroke-width': 2 }));
      });
    });
    const hit = el('rect', { x: f.m.l, y: f.m.t, width: f.iw, height: f.ih, fill: 'transparent' }); f.svg.append(hit);
    const dot = el('circle', { r: 5, fill: '#14182b', opacity: 0 }); f.svg.append(dot);
    hit.addEventListener('mousemove', e => { const r = f.svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * f.w; let best = null;
      o.series.forEach(s => s.points.forEach(p => { if (p.y == null) return; const d = Math.abs(X(p.x) - px); if (!best || d < best.d) best = { d, p, s }; }));
      if (best) { dot.setAttribute('cx', X(best.p.x)); dot.setAttribute('cy', Y(best.p.y)); dot.setAttribute('opacity', 1); showTip(e, `${best.s.name}\n${o.tipx ? o.tipx(best.p.x) : best.p.x}: ${o.yfmt ? o.yfmt(best.p.y) : best.p.y.toFixed(2)}${best.p.err ? ' ± ' + best.p.err.toFixed(2) : ''}`); } });
    hit.addEventListener('mouseleave', () => { hideTip(); dot.setAttribute('opacity', 0); });
    if (o.series.length > 1 || o.legend) legend(host, o.series.map((s, i) => ({ name: s.name, color: s.color || PAL[i % PAL.length], dash: s.dash })));
  }
  /* bars: groups [{label, bars:[{name,color,value,err}]}] */
  function bars(host, o) {
    const f = frame(host, o); const vals = o.groups.flatMap(g => g.bars.map(b => b.value + (b.err || 0)));
    const yhi = nice(Math.max(...vals) * 1.08), ylo = 0; const gw = f.iw / o.groups.length;
    axes(f, { xt: o.groups.map((g, i) => ({ x: f.m.l + gw * (i + .5), label: g.label })), yt: ticks(0, yhi), xl: o.xlabel, yl: o.ylabel, yfmt: o.yfmt, ylo, yhi });
    const Y = v => f.m.t + f.ih - v / yhi * f.ih; const names = new Map();
    o.groups.forEach((g, i) => { const n = g.bars.length, bw = Math.min(46, gw * .7 / n);
      g.bars.forEach((b, j) => { const x = f.m.l + gw * i + gw / 2 + (j - n / 2) * bw + 1; const c = b.color || PAL[j % PAL.length]; names.set(b.name, c);
        const r = el('rect', { x, y: Y(b.value), width: bw - 2, height: Math.max(0, f.m.t + f.ih - Y(b.value)), fill: c, rx: 3 }); f.svg.append(r);
        if (b.err) f.svg.append(el('line', { x1: x + bw / 2 - 1, x2: x + bw / 2 - 1, y1: Y(b.value - b.err), y2: Y(b.value + b.err), stroke: '#14182b', 'stroke-width': 1.3 }));
        r.addEventListener('mousemove', e => showTip(e, `${g.label} · ${b.name}\n${o.yfmt ? o.yfmt(b.value) : b.value.toFixed(2)}${b.err ? ' ± ' + b.err.toFixed(2) : ''}`)); r.addEventListener('mouseleave', hideTip); }); });
    if (o.refline != null) { f.svg.append(el('line', { x1: f.m.l, x2: f.m.l + f.iw, y1: Y(o.refline), y2: Y(o.refline), stroke: '#8b93a7', 'stroke-dasharray': '4 4' }), el('text', { x: f.m.l + f.iw, y: Y(o.refline) - 5, 'text-anchor': 'end' }, o.reflabel || '')); }
    if (names.size > 1) legend(host, [...names].map(([name, color]) => ({ name, color })));
  }
  function hbars(host, o) {   // items [{label,value,color,hl}]
    const rowH = 28, h = o.items.length * rowH + 30, f = frame(host, { w: o.w || 720, h, title: o.title, m: { l: o.left || 170, r: 56, t: 6, b: 24 } });
    const max = nice(Math.max(...o.items.map(i => i.value)) * 1.05 || 1); const X = v => v / max * f.iw;
    ticks(0, max, 4).forEach(v => f.svg.append(el('line', { x1: f.m.l + X(v), x2: f.m.l + X(v), y1: f.m.t, y2: f.m.t + o.items.length * rowH, class: 'gridl' }), el('text', { x: f.m.l + X(v), y: f.m.t + o.items.length * rowH + 16, 'text-anchor': 'middle' }, v)));
    o.items.forEach((it, i) => { const y = f.m.t + i * rowH; const c = it.color || (it.hl ? PAL[0] : '#c5ccdb');
      f.svg.append(el('text', { x: f.m.l - 8, y: y + 18, 'text-anchor': 'end', 'font-weight': it.hl ? 700 : null, fill: it.hl ? '#14182b' : null }, it.label), el('rect', { x: f.m.l, y: y + 5, width: X(it.value), height: rowH - 11, fill: c, rx: 3 }), el('text', { x: f.m.l + X(it.value) + 6, y: y + 18 }, o.fmt ? o.fmt(it.value) : it.value.toFixed(2))); });
  }
  function scatter(host, o) {  // points [{x,y}], o.diag
    const f = frame(host, { ...o, m: { l: 56, r: 16, t: 14, b: 44 } }); const lim = nice(o.lim || Math.max(...o.points.map(p => Math.max(p.x, p.y))));
    const X = v => f.m.l + v / lim * f.iw, Y = v => f.m.t + f.ih - v / lim * f.ih;
    axes(f, { xt: ticks(0, lim, 5).map(v => ({ x: X(v), label: v })), yt: ticks(0, lim, 5), xl: o.xlabel, yl: o.ylabel, ylo: 0, yhi: lim });
    if (o.diag) f.svg.append(el('line', { x1: X(0), y1: Y(0), x2: X(lim), y2: Y(lim), stroke: '#14182b', 'stroke-dasharray': '5 4', 'stroke-width': 1.2 }));
    const g = el('g', { fill: o.color || '#3157d5', 'fill-opacity': .22 }); o.points.forEach(p => { if (p.x <= lim && p.y <= lim) g.append(el('circle', { cx: X(p.x), cy: Y(p.y), r: 2.2 })); }); f.svg.append(g);
  }
  function histogram(host, o) {  // values, lo, hi, bins
    const bins = new Array(o.bins).fill(0), w = (o.hi - o.lo) / o.bins; o.series.forEach(s => { s.counts = new Array(o.bins).fill(0); s.values.forEach(v => { const k = Math.floor((v - o.lo) / w); if (k >= 0 && k < o.bins) s.counts[k]++; }); });
    const f = frame(host, o), ymax = nice(Math.max(...o.series.flatMap(s => s.counts)) * 1.08), X = v => f.m.l + (v - o.lo) / (o.hi - o.lo) * f.iw, Y = v => f.m.t + f.ih - v / ymax * f.ih;
    axes(f, { xt: ticks(o.lo, o.hi, 6).map(v => ({ x: X(v), label: v })), yt: ticks(0, ymax, 4), xl: o.xlabel, yl: 'Records', ylo: 0, yhi: ymax });
    o.series.forEach((s, si) => s.counts.forEach((c, i) => f.svg.append(el('rect', { x: X(o.lo + i * w) + 1, y: Y(c), width: Math.max(1, X(o.lo + w) - X(o.lo) - 2), height: f.m.t + f.ih - Y(c), fill: s.color || PAL[si], 'fill-opacity': .5 }))));
    legend(host, o.series.map((s, i) => ({ name: s.name, color: s.color || PAL[i] })));
  }
  const CATC = ['#2e9e6b', '#8bbf3f', '#e5b829', '#e8833a', '#d64545', '#8c2d5a'];
  function share(host, labels, vals, withLegend) {
    host.textContent = ''; const bar = document.createElement('div'); bar.className = 'cat'; bar.setAttribute('role', 'img'); bar.setAttribute('aria-label', labels.map((l, i) => `${l} ${vals[i]}%`).join(', '));
    vals.forEach((v, i) => { const s = document.createElement('span'); s.style.width = v + '%'; s.style.background = CATC[i]; s.title = `${labels[i]}: ${v}%`; bar.append(s); }); host.append(bar);
    if (withLegend) legend(host, labels.map((l, i) => ({ name: `${l} ${vals[i]}%`, color: CATC[i] })));
  }
  window.Charts = { line, bars, hbars, scatter, histogram, share, PAL, CATC };
})();
