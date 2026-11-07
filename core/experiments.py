"""Missing-data experiments on the FROZEN benchmark test sets. One trained model and one set of training medians are
used for every scenario; the same test records/targets are used throughout; only input cells are masked."""
from __future__ import annotations
import json, os, shutil, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import core.config as C
from core import benchmark as B, datasets as D, ingest as I, metrics as M, schema as S, sim
from core.gateway import EdgeGateway
from core.train import hardware_info

SETS = {"temporal": B.TEST_T, "spatial": B.TEST_S}


def _lat(gw, X, ids, n_rec, warm):
    """Per-record latency through the gateway path: dict -> preprocess -> single predict. dict construction excluded."""
    pre, inf, tot = [], [], []
    recs = [{f: (None if np.isnan(v) else float(v)) for f, v in zip(gw.features, X[i])} for i in ids]
    for r in recs[:warm]: gw.process_record(r)
    for r in recs[warm:]:
        o = gw.process_record(r); pre.append(o["preprocess_ms"]); inf.append(o["inference_ms"]); tot.append(o["total_ms"])
    return pre, inf, tot


def run(model_dir: Path, dataset_dir: Path, benchmark_dir: Path, out_dir: Path, trials: int = C.DEFAULT_TRIALS,
        rates=C.MISSING_RATES, patterns=C.PATTERNS, sets=("temporal", "spatial"), progress=None, seed=C.EXPERIMENT_SEED) -> dict:
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"experiment exists: {out_dir.name}")
    tmp = out_dir.with_name(out_dir.name + ".building"); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    man_m = json.loads((Path(model_dir) / "manifest.json").read_text())
    bench = B.load(benchmark_dir)
    if man_m["benchmark_sha256"] != bench["benchmark_sha256"]:
        raise RuntimeError("model was trained against a different benchmark version")
    rec = D.load_records(dataset_dir); lab = B.assign(rec, bench)
    gw = EdgeGateway.load(model_dir)
    _nj = lambda n: gw.model.set_params(n_jobs=n) if hasattr(gw.model, 'set_params') and 'n_jobs' in gw.model.get_params() else None
    _nj(2)  # batch scoring may use both cores; latency below is measured single-threaded
    t0 = time.time(); rows = []; samples = {}
    scen = [(0.0, "none")] + [(r, p) for r in rates if r > 0 for p in patterns]
    total = len(sets) * sum(1 if r == 0 else trials for r, _ in scen); done = 0
    for sname in sets:
        m_ = lab == SETS[sname]
        if not m_.any():
            continue
        X = rec["X"][m_].astype(np.float64); y = rec["y"][m_].astype(np.float64)
        st, ts = rec["station"][m_], rec["ts_ns"][m_]
        for rate, pat in scen:
            for tr in range(1 if rate == 0 else trials):
                sd = seed + int(1000 * rate * 100) + tr
                Xm, meta = sim.inject(X, rate, pat, sd, st, ts)
                p = gw.predict_array(Xm)
                met = M.regression(y, p)
                rows.append(dict(test_set=sname, missing_rate=rate, pattern=pat, trial=tr, seed=sd, **met,
                                 achieved_rate=meta["achieved_rate"], natural_missing=meta["natural_missing_rate"],
                                 total_missing=meta["total_missing_rate"], masked_cells=meta["masked_cells"],
                                 eligible_cells=meta["eligible_cells"]))
                if tr == 0 and rate in (0.0, 0.2):
                    k = np.random.default_rng(5).choice(len(y), min(4000, len(y)), replace=False)
                    samples[f"{sname}|{rate}|{pat}"] = dict(y=y[k].round(2).tolist(), p=p[k].round(2).tolist())
                done += 1
                if progress: progress(done / total, f"{sname} {int(rate*100)}% {pat} trial {tr+1}")
    # latency: fixed record subset of the temporal test, per scenario (one trial each, gateway process_record path)
    lat = []
    _nj(1)
    if "temporal" in sets:
        m_ = lab == B.TEST_T
        X = rec["X"][m_].astype(np.float64); st, ts = rec["station"][m_], rec["ts_ns"][m_]
        ids = np.random.default_rng(seed).choice(len(X), C.LATENCY_N_RECORDS, replace=False)
        for rate, pat in scen:
            Xm, _ = sim.inject(X, rate, pat, seed + int(1000 * rate * 100), st, ts)
            pre, inf, tot = _lat(gw, Xm, ids, C.LATENCY_N_RECORDS, C.LATENCY_WARMUP)
            lat.append(dict(missing_rate=rate, pattern=pat, preprocess=M.latency(pre), inference=M.latency(inf), total=M.latency(tot)))
    res = dict(rows=rows, latency=lat, samples=samples)
    meta = dict(experiment_id=out_dir.name, created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                model_id=man_m["model_id"], model_sha256=man_m["model_sha256"], dataset_version=man_m["dataset_version"],
                benchmark_id=bench["benchmark_id"], benchmark_sha256=bench["benchmark_sha256"], trials=trials, rates=list(rates),
                patterns=list(patterns), seed=seed, block_len_range=list(C.BLOCK_LEN_RANGE), latency_records=C.LATENCY_N_RECORDS,
                latency_warmup=C.LATENCY_WARMUP, environment=hardware_info(), seconds=round(time.time() - t0, 1),
                test_rows={s: int((lab == SETS[s]).sum()) for s in sets},
                note="Software simulation on the host computer, not physical edge hardware.")
    (tmp / "results.json").write_text(json.dumps(dict(meta=meta, **res)))
    (tmp / "manifest.json").write_text(json.dumps(meta, indent=1))
    os.replace(tmp, out_dir)
    return meta


def summarise(results: dict) -> list[dict]:
    """Group trials -> mean/std per (test_set, rate, pattern) with the ΔRMSE vs the 0% reference of the same set."""
    import pandas as pd
    df = pd.DataFrame(results["rows"])
    g = df.groupby(["test_set", "missing_rate", "pattern"]).agg(
        n_trials=("trial", "count"), mae=("mae", "mean"), mae_std=("mae", "std"), rmse=("rmse", "mean"), rmse_std=("rmse", "std"),
        r2=("r2", "mean"), r2_std=("r2", "std"), n=("n", "first"), achieved=("achieved_rate", "mean")).reset_index()
    g[["mae_std", "rmse_std", "r2_std"]] = g[["mae_std", "rmse_std", "r2_std"]].fillna(0.0)
    base = g[g.missing_rate == 0].set_index("test_set")["rmse"]
    g["rmse_increase_pct"] = [0.0 if r.missing_rate == 0 else 100 * (r.rmse / base[r.test_set] - 1) for r in g.itertuples()]
    base_m = g[g.missing_rate == 0].set_index("test_set")["mae"]
    g["mae_increase_pct"] = [0.0 if r.missing_rate == 0 else 100 * (r.mae / base_m[r.test_set] - 1) for r in g.itertuples()]
    return g.to_dict("records")
