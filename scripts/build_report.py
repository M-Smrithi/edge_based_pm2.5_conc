#!/usr/bin/env python3
"""Builds docs/research_report.{md,pdf} from saved artifacts only (audit, dataset manifest, benchmark, model, experiment).
Usage: python scripts/build_report.py [--experiment exp-0001]   (defaults to the experiment of the active model)"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.config as C
from core import experiments as E, reporting


def load(a):
    from app.db import connect
    con = connect()
    if a.experiment: row = con.execute("SELECT * FROM experiments WHERE id=?", (a.experiment,)).fetchone()
    else:
        row = con.execute("SELECT e.* FROM experiments e JOIN models m ON m.id=e.model_id WHERE m.status='active' ORDER BY e.created_utc DESC LIMIT 1").fetchone() \
              or con.execute("SELECT * FROM experiments ORDER BY created_utc DESC LIMIT 1").fetchone()
    if not row: sys.exit("No experiment found.")
    e = dict(row); R = json.loads((C.EXPERIMENTS / e["id"] / "results.json").read_text())
    mm = json.loads((C.MODELS / e["model_id"] / "metrics.json").read_text()); mman = json.loads((C.MODELS / e["model_id"] / "manifest.json").read_text())
    return dict(e=e, R=R, summ={(r["test_set"], r["missing_rate"], r["pattern"]): r for r in E.summarise(R)}, mm=mm, mman=mman,
                bench=json.loads((C.BENCHMARKS / e["benchmark_id"] / "benchmark.json").read_text()),
                ds=json.loads((C.DATASETS / e["dataset_version"] / "manifest.json").read_text()),
                audit=json.loads((C.AUDITS / "audit_latest.json").read_text())["summary"] if (C.AUDITS / "audit_latest.json").exists() else None)


def f(x, d=2): return f"{x:,.{d}f}"


def content(D):
    e, S, mm, ds, b, au, man = D["e"], D["summ"], D["mm"], D["ds"], D["bench"], D["audit"], D["mman"]
    sel = next(c for c in mm["candidates"] if c["name"] == mm["selected"]); env = D["R"]["meta"]["environment"]
    sets = [s for s in ("temporal", "spatial") if ("%s" % s, 0.0, "none") in S]
    secs = []
    secs.append(("Abstract", [f"This report evaluates how the amount and pattern of missing IoT sensor readings affect the accuracy and local processing latency of a lightweight edge-style PM2.5 estimator. "
        f"A {mm['selected'].replace('_', ' ')} model was trained on {ds['n_stations']} CPCB monitoring stations ({ds['rows']:,} station-hour records, {ds['ts_min'][:10]} to {ds['ts_max'][:10]}) and evaluated on a frozen benchmark with 0%, 10% and 20% of input readings removed at random or in consecutive blocks ({e['trials']} seeded trials per scenario). "
        + " ".join(f"On the {s} test set RMSE moved from {f(S[(s,0.0,'none')]['rmse'])} µg/m³ with no added gaps to {f(S[(s,.1,'random')]['rmse'])} at 10% and {f(S[(s,.2,'random')]['rmse'])} at 20% (random pattern)." for s in sets)
        + " Edge behaviour is a software simulation on a general-purpose computer; no physical edge hardware was used."]))
    secs.append(("1. Research question and scope", ["How do the amount and pattern of missing IoT sensor readings affect prediction accuracy, robustness and local processing latency of a lightweight edge-based PM2.5 prediction pipeline? "
        "The study is an experimental evaluation of an existing approach (median imputation followed by a tree-ensemble regressor), not a new algorithm. The task is same-hour estimation of PM2.5 from twelve co-located readings (PM10, NO, NO2, NOx, SO2, CO, O3, RH, WS, WD, SR, AT); it is not forecasting and no lagged or future values are used."]))
    secs.append(("2. Data source and a change from the original proposal", [
        "The original report named the UCI Air Quality dataset. The experiments in this report use the station-wise hourly CPCB (Central Pollution Control Board, India) records distributed on Kaggle instead; the project owner approved this substitution. The two sources differ in geography, sensors, period, station count and missingness, so numbers from the earlier report are not comparable with the results here.",
        "The original report also stated that incomplete records would be removed. This study deliberately keeps records with some missing inputs, because incomplete inputs are the subject of the research; only records with no valid PM2.5 target, with an unparseable timestamp, or with no sensor value at all are dropped."]))
    if au:
        secs.append(("3. Data audit", [f"Every file received ({au['n_files']}) was audited without modification. Outcome: {au['verdicts'].get('accepted',0)} usable as-is, {au['verdicts'].get('accepted_recovered',0)} usable after verified header recovery (alternate headers with identical meaning or exact SI unit conversions such as CO µg/m³ → mg/m³), "
            f"{au['verdicts'].get('pending_review',0)} held for administrator review because a sensor column is absent or its unit is blank or unverifiable, and {au['verdicts'].get('rejected',0)} rejected (no PM2.5 column). Units were never guessed. The usable files contain {au['usable_valid_rows']:,} valid rows, of which {au['usable_complete_case_rows']:,} have all twelve sensors present. "
            f"Station metadata (stations_info.csv) matched {au['stations_info']['codes_verified']} of {au['stations_info']['codes_total']} station codes; the application also works without it."]))
    nm = ds["natural_missing_pct_by_sensor"]
    secs.append(("4. Method", [
        f"Cleaning: duplicate (station, timestamp) records are removed (first kept); values outside physical ranges become missing; records without a valid target are dropped. Dataset version {ds['dataset_version']} contains {ds['n_files']} files and {ds['rows']:,} unique records; duplicates removed: {ds['duplicates']['identical']:,} identical, {ds['duplicates']['conflicting']:,} conflicting. Natural missingness per sensor (%): " + ", ".join(f"{k} {v:.1f}" for k, v in nm.items()) + ".",
        f"Benchmark {b['benchmark_id']} (frozen): chronological cut-points at {b['t1'][:10]} (train/validation) and {b['t2'][:10]} (validation/test); {len(b['holdout_stations'])} stations chosen by a deterministic hash are never used for training and form the unseen-station test. Temporal test records: {b['n_test_temporal']:,}; unseen-station test records: {b['n_test_spatial']:,}.",
        f"Model: candidates were compared on validation data only ({', '.join(c['name'].replace('_',' ') for c in mm['candidates'])}). Rule: lowest validation RMSE; candidates within 1% are decided by single-record latency. Selected: {mm['selected'].replace('_',' ')}. Training-set medians are saved with the model and used for imputation.",
        f"Missingness experiments: 0%, 10%, 20% of the observed input cells of the frozen test records; random (uniform cells) and consecutive (contiguous runs of {e and D['R']['meta']['block_len_range'][0]}–{D['R']['meta']['block_len_range'][1]} hourly records on one sensor at one station, never across stations or time gaps). Targets are never masked. {e['trials']} seeded trials per scenario; the same test records are used in every scenario."]))
    rows = [["Test set", "Added", "Pattern", "MAE", "RMSE", "R²", "ΔRMSE"]]
    for s in sets:
        for k in sorted([k for k in S if k[0] == s], key=lambda k: (k[1], k[2])):
            r = S[k]; rows.append([s, f"{int(k[1]*100)}%", k[2] if k[1] else "—", f"{r['mae']:.2f} ± {r['mae_std']:.2f}" if r["n_trials"] > 1 else f"{r['mae']:.2f}", f"{r['rmse']:.2f} ± {r['rmse_std']:.2f}" if r["n_trials"] > 1 else f"{r['rmse']:.2f}", f"{r['r2']:.3f}", "—" if not k[1] else f"+{r['rmse_increase_pct']:.1f}%"])
    secs.append(("5. Results: accuracy and robustness", [("table", rows), "Values are mean ± standard deviation over trials (µg/m³). ΔRMSE is relative to the 0% scenario of the same test set. The 0% scenario still contains the natural gaps of the data, which are median-imputed."]))
    obs = []
    for s in sets:
        r10, c10, r20, c20 = S[(s, .1, "random")], S[(s, .1, "consecutive")], S[(s, .2, "random")], S[(s, .2, "consecutive")]
        obs.append(f"On the {s} test set RMSE rose by {r10['rmse_increase_pct']:.1f}% (random) and {c10['rmse_increase_pct']:.1f}% (consecutive) at 10% added missingness, and by {r20['rmse_increase_pct']:.1f}% and {c20['rmse_increase_pct']:.1f}% at 20%. "
                   f"The random-versus-consecutive RMSE gap at 20% was {abs(r20['rmse']-c20['rmse']):.2f} µg/m³, which is {'smaller' if abs(r20['rmse']-c20['rmse']) < max(r20['rmse_std'], c20['rmse_std']) * 2 else 'larger'} than twice the larger trial standard deviation ({max(r20['rmse_std'], c20['rmse_std']):.2f}).")
    if len(sets) == 2:
        a, bb = S[("temporal", 0.0, "none")]["rmse"], S[("spatial", 0.0, "none")]["rmse"]
        obs.append(f"Without added gaps, RMSE was {f(a)} on the temporal test and {f(bb)} on the unseen-station test, so {'generalising to unseen stations did not cost accuracy here' if bb <= a * 1.02 else 'unseen stations were harder than later periods at known stations'}; with only these two numbers per set this should not be over-interpreted.")
    secs.append(("6. Discussion", obs + [f"Training RMSE exceeded or approached validation RMSE for the candidates (selected: train {sel['train']['rmse']:.2f}, validation {sel['val']['rmse']:.2f}); see the model-comparison table. Error grows with the removed share of readings for both patterns; these data do not show that consecutive outages are systematically worse than random ones unless the gap above exceeds trial variability."]))
    lat = D["R"]["latency"]; lrows = [["Scenario", "Preprocess median (p95) ms", "Inference median (p95) ms", "End-to-end median (p95) ms"]]
    for l in lat: lrows.append([("0%" if l["missing_rate"] == 0 else f"{int(l['missing_rate']*100)}% {l['pattern']}"), f"{l['preprocess']['median']:.4f} ({l['preprocess']['p95']:.4f})", f"{l['inference']['median']:.3f} ({l['inference']['p95']:.3f})", f"{l['total']['median']:.3f} ({l['total']['p95']:.3f})"])
    secs.append(("7. Latency (software simulation)", [f"Latency was measured per record through the simulated gateway with a monotonic timer, separately for preprocessing (validation, missing-value detection, median imputation), inference (single-record prediction) and end-to-end, over {e and D['R']['meta']['latency_records'] - D['R']['meta']['latency_warmup']} timed records after {D['R']['meta']['latency_warmup']} warm-up records. Host: {env['platform']}, {env['cpu_count']} CPU(s), Python {env['python']}, scikit-learn {env['sklearn']}, NumPy {env['numpy']}.", ("table", lrows),
        "These figures describe this host only. They are not measurements of Raspberry Pi or other edge hardware and must not be read as such."]))
    mrows = [["Candidate", "Val RMSE", "Val MAE", "Train RMSE", "Latency ms", "Size MB"]] + [[c["name"].replace("_", " ") + (" ✓" if c["name"] == mm["selected"] else ""), f"{c['val']['rmse']:.2f}", f"{c['val']['mae']:.2f}", f"{c['train']['rmse']:.2f}", f"{c['latency_ms']:.2f}" if c["latency_ms"] else "—", f"{c['size_mb']:.1f}" if c["size_mb"] else "—"] for c in mm["candidates"]]
    secs.append(("8. Model comparison (validation only)", [("table", mrows), "The comparison was kept small and used validation data only; the test sets were not used for fitting, tuning or selection."]))
    secs.append(("9. Limitations", ["Software simulation only; no physical edge deployment, power, memory or network effects. Missingness is artificial and may not resemble real outages. Median imputation is the only strategy studied. "
        "Files lacking a sensor or having unverified units were held back or excluded rather than guessed, so the analysed network is a subset of the archive. The held-out-station test uses a small number of stations. Findings describe this dataset and model family and may not transfer to other regions, sensors or seasons. The estimates are not health advice."]))
    secs.append(("10. Reproducibility", [f"Model {e['model_id']} (sha256 {man['model_sha256'][:16]}…), dataset {e['dataset_version']} (records sha256 {ds['records_sha256'][:16]}…), benchmark {b['benchmark_id']} (sha256 {b['benchmark_sha256'][:16]}…), experiment {e['id']} (seed {e['seed']}, {e['trials']} trials). The Experiment Manager can re-run an experiment and reports whether all trial results are bit-identical on the same machine."]))
    return secs


def to_md(title, secs, figs):
    L = [f"# {title}", ""]
    for h, paras in secs:
        L += [f"## {h}", ""]
        for p in paras:
            if isinstance(p, tuple): L += ["| " + " | ".join(p[1][0]) + " |", "|" + "---|" * len(p[1][0])] + ["| " + " | ".join(r) + " |" for r in p[1][1:]] + [""]
            else: L += [p, ""]
        if h.startswith("5.") or h.startswith("7."):
            for fg in figs.get(h[:2], []): L += [f"![{fg.stem}](figures/{fg.name})", ""]
    return "\n".join(L)


def to_pdf(path, title, secs, figs):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    st = getSampleStyleSheet(); body = ParagraphStyle("b", parent=st["BodyText"], fontSize=9.5, leading=13.5, spaceAfter=7)
    h1 = ParagraphStyle("h", parent=st["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#14182b")); tt = ParagraphStyle("t", parent=st["Title"], fontSize=19, leading=23, textColor=colors.HexColor("#14182b"))
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.8*cm, bottomMargin=1.8*cm, title=title); el = [Paragraph(escape(title), tt), Paragraph("M. Smrithi · Manipal Institute of Technology (MIT), Manipal", st["Normal"]), Spacer(1, 12)]
    for h, paras in secs:
        el.append(Paragraph(escape(h), h1))
        for p in paras:
            if isinstance(p, tuple):
                rows = [[Paragraph(escape(str(c)), ParagraphStyle("c", fontSize=7.5, leading=9)) for c in r] for r in p[1]]
                t = Table(rows, repeatRows=1); t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#d5dae6")), ("VALIGN", (0, 0), (-1, -1), "TOP")])); el += [t, Spacer(1, 6)]
            else: el.append(Paragraph(escape(p), body))
        if h.startswith("5.") or h.startswith("7."):
            for fg in figs.get(h[:2], []):
                from PIL import Image as PI
                w, hh = PI.open(fg).size; W = 16.5 * cm; el += [Image(str(fg), width=W, height=W * hh / w), Spacer(1, 6)]
    doc.build(el)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--experiment"); a = ap.parse_args()
    D = load(a); exp_dir = C.EXPERIMENTS / D["e"]["id"]
    if not (exp_dir / "figures").exists(): reporting.make_figures(exp_dir, C.MODELS / D["e"]["model_id"])
    fg = exp_dir / "figures"; figs = {"5.": [fg / n for n in ("error_vs_missingness.png", "random_vs_consecutive.png", "error_increase.png", "actual_vs_predicted.png", "residuals.png") if (fg / n).exists()], "7.": [fg / "latency.png"] if (fg / "latency.png").exists() else []}
    title = "Edge-Based Air Quality Prediction Under Incomplete IoT Sensor Data — Experimental Report"
    secs = content(D); out = C.ROOT / "docs"; out.mkdir(exist_ok=True)
    import shutil; (out / "figures").mkdir(exist_ok=True)
    for p in fg.glob("*.png"): shutil.copy2(p, out / "figures" / p.name)
    figs = {k: [out / "figures" / p.name for p in v] for k, v in figs.items()}
    (out / "research_report.md").write_text(to_md(title, secs, figs)); to_pdf(out / "research_report.pdf", title, secs, figs)
    print("wrote", out / "research_report.md", out / "research_report.pdf")
