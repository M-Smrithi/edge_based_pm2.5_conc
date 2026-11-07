"""Training: candidate comparison on VALIDATION only, selection rule, artifact bundle. Test data is never used for
fitting, tuning or selection; test metrics are computed once, after selection, for reporting/promotion checks."""
from __future__ import annotations
import hashlib, json, os, platform, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor

import core.config as C
from core import benchmark as B, datasets as D, ingest as I, metrics as M, schema as S
from core.gateway import EdgeGateway


class Constant:
    """Median baseline (picklable, scikit-like)."""
    def __init__(self, v): self.v = float(v)
    def predict(self, X): return np.full(len(X), self.v)


DEFAULT_PARAMS = dict(
    n_estimators=60, max_samples=0.2, seed=C.SEED,
    candidates=[
        dict(name="random_forest_leaf10", kind="rf", min_samples_leaf=10, max_features=0.6),
        dict(name="random_forest_leaf30", kind="rf", min_samples_leaf=30, max_features=0.6),
        dict(name="extra_trees", kind="et", min_samples_leaf=10, max_features=0.8),
        dict(name="hist_gradient_boosting", kind="hgb", max_iter=250, learning_rate=0.08, max_leaf_nodes=63),
    ])


def _make(c, p):
    k = c["kind"]
    if k in ("rf", "et"):
        cls = RandomForestRegressor if k == "rf" else ExtraTreesRegressor
        return cls(n_estimators=p["n_estimators"], max_samples=p["max_samples"], bootstrap=True,
                   min_samples_leaf=c["min_samples_leaf"], max_features=c["max_features"], n_jobs=2, random_state=p["seed"])
    return HistGradientBoostingRegressor(max_iter=c["max_iter"], learning_rate=c["learning_rate"],
                                         max_leaf_nodes=c["max_leaf_nodes"], random_state=p["seed"])


def _single_record_ms(model, Xrow: np.ndarray, n=100) -> float:
    if hasattr(model, "set_params") and "n_jobs" in model.get_params():
        model.set_params(n_jobs=1)
    ts = []
    for i in range(n + 10):
        x = Xrow[i % len(Xrow)].reshape(1, -1)
        t = time.perf_counter_ns(); model.predict(x); ts.append((time.perf_counter_ns() - t) / 1e6)
    return float(np.median(ts[10:]))


def select(cands: list[dict]) -> dict:
    """Lowest validation RMSE; candidates within 1% of the best are decided by single-record latency, then val MAE, then size."""
    real = [c for c in cands if c["name"] != "median_baseline"]
    best = min(c["val"]["rmse"] for c in real)
    close = [c for c in real if c["val"]["rmse"] <= best * 1.01]
    return sorted(close, key=lambda c: (c["latency_ms"], c["val"]["mae"], c["size_mb"]))[0]


def hardware_info() -> dict:
    return dict(platform=platform.platform(), python=platform.python_version(), cpu_count=os.cpu_count(),
                machine=platform.machine(), sklearn=sklearn.__version__, numpy=np.__version__)


def train(dataset_dir: Path, benchmark_dir: Path, out_dir: Path, params: dict | None = None, progress=None) -> dict:
    p = {**DEFAULT_PARAMS, **(params or {})}
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"model directory exists: {out_dir.name}")
    tmp = out_dir.with_name(out_dir.name + ".building")
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    logf = open(tmp / "train.log", "a")

    def log(msg, frac=None):
        line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}"
        logf.write(line + "\n"); logf.flush(); print(line, flush=True)
        if progress and frac is not None: progress(frac, msg)

    try:
        t_start = time.time()
        if not D.verify_version(dataset_dir):
            raise RuntimeError("dataset checksum mismatch - refusing to train")
        rec = D.load_records(dataset_dir); bench = B.load(benchmark_dir)
        lab = B.assign(rec, bench)
        counts = B.summary(lab)
        log(f"dataset {rec['manifest']['dataset_version']} benchmark {bench['benchmark_id']} splits {counts}", 0.02)
        X, y = rec["X"], rec["y"]
        tr, va = lab == B.TRAIN, lab == B.VAL
        if tr.sum() < 1000 or va.sum() < 100:
            raise RuntimeError("not enough training/validation rows")
        medians = {n: round(float(np.nanmedian(X[tr, j])), 4) if np.isfinite(X[tr, j]).any() else 0.0 for j, n in enumerate(S.FEATURE_NAMES)}
        med = np.array([medians[n] for n in S.FEATURE_NAMES], np.float32)

        def imp(A):
            A = A.copy(); nan = np.isnan(A); A[nan] = np.broadcast_to(med, A.shape)[nan]; return A
        Xtr, ytr, Xva, yva = imp(X[tr]), y[tr], imp(X[va]), y[va]
        log(f"train rows {len(ytr):,}  val rows {len(yva):,}  natural missing in train {np.isnan(X[tr]).mean()*100:.2f}%", 0.05)
        cands = []
        base = Constant(np.median(ytr))
        cands.append(dict(name="median_baseline", kind="baseline", val=M.regression(yva, base.predict(Xva)),
                          train=M.regression(ytr, base.predict(Xtr)), latency_ms=0.0, size_mb=0.0, fit_seconds=0.0))
        models = {"median_baseline": base}
        for i, c in enumerate(p["candidates"]):
            t = time.time(); m = _make(c, p).fit(Xtr, ytr); fit = time.time() - t
            pv = m.predict(Xva)
            tmpf = tmp / f".size_{c['name']}.joblib"; joblib.dump(m, tmpf, compress=3); size = tmpf.stat().st_size / 1e6; tmpf.unlink()
            pt = m.predict(Xtr[:200_000])
            rowx = Xva[np.random.default_rng(1).choice(len(Xva), 120, replace=False)]
            lat = _single_record_ms(m, rowx)
            cands.append(dict(name=c["name"], kind=c["kind"], config={k: v for k, v in c.items() if k not in ("name", "kind")},
                              val=M.regression(yva, pv), train=M.regression(ytr[:200_000], pt), latency_ms=lat,
                              size_mb=round(size, 2), fit_seconds=round(fit, 1)))
            models[c["name"]] = m
            log(f"{c['name']}: val RMSE {cands[-1]['val']['rmse']:.3f} MAE {cands[-1]['val']['mae']:.3f} "
                f"latency {lat:.2f} ms size {size:.1f} MB fit {fit:.0f}s", 0.1 + 0.8 * (i + 1) / len(p["candidates"]))
        chosen = select(cands)
        log(f"SELECTED {chosen['name']} (validation only)", 0.92)
        model = models[chosen["name"]]
        if hasattr(model, "set_params") and "n_jobs" in model.get_params(): model.set_params(n_jobs=1)
        joblib.dump(model, tmp / "model.joblib", compress=3)
        pre = dict(features=S.FEATURE_NAMES, medians=medians, ranges={n: list(S.FEATURES[n].valid_range) for n in S.FEATURE_NAMES},
                   imputation="training-set median; missing, non-finite or out-of-range readings are treated as missing")
        (tmp / "preprocessing.json").write_text(json.dumps(pre, indent=1))
        (tmp / "schema.json").write_text(json.dumps(dict(
            features=[dict(name=n, unit=S.FEATURES[n].unit, label=S.FEATURES[n].label, valid_range=list(S.FEATURES[n].valid_range))
                      for n in S.FEATURE_NAMES], target=dict(name=C.TARGET, unit="ug/m3", range=list(C.TARGET_RANGE)),
            task="same-hour PM2.5 estimation from co-located sensors (not forecasting)"), indent=1))
        # post-selection reporting on the frozen test sets (0% added missingness)
        gw = EdgeGateway(model, S.FEATURE_NAMES, medians)
        test = {}
        for name, code in (("test_temporal", B.TEST_T), ("test_spatial", B.TEST_S)):
            m_ = lab == code
            if m_.sum():
                pr = gw.predict_array(X[m_].astype(np.float64))
                test[name] = M.regression(y[m_], pr)
                test[name]["baseline_rmse"] = M.rmse(y[m_], base.predict(X[m_]))
        log(f"post-selection test: {json.dumps({k: round(v['rmse'], 3) for k, v in test.items()})}", 0.97)
        sha = I.sha256_file(tmp / "model.joblib")
        metrics = dict(candidates=cands, selected=chosen["name"], test=test, split_counts=counts,
                       selection_rule="lowest validation RMSE; within 1% -> lowest single-record latency, then val MAE, then size")
        (tmp / "metrics.json").write_text(json.dumps(metrics, indent=1))
        man = dict(model_id=out_dir.name, created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   dataset_version=rec["manifest"]["dataset_version"], dataset_records_sha256=rec["manifest"]["records_sha256"],
                   benchmark_id=bench["benchmark_id"], benchmark_sha256=bench["benchmark_sha256"], seed=p["seed"],
                   params={k: v for k, v in p.items() if k != "candidates"}, selected=chosen["name"],
                   model_sha256=sha, model_bytes=(tmp / "model.joblib").stat().st_size, train_rows=int(len(ytr)),
                   val_rows=int(len(yva)), medians_fitted_on="train split only", environment=hardware_info(),
                   train_seconds=round(time.time() - t_start, 1), artifacts=["model.joblib", "preprocessing.json", "schema.json",
                                                                        "metrics.json", "manifest.json", "train.log"])
        (tmp / "manifest.json").write_text(json.dumps(man, indent=1))
        log(f"done in {man['train_seconds']}s", 1.0)
        logf.close()
        os.replace(tmp, out_dir)
        return dict(manifest=man, metrics=metrics)
    except BaseException as e:
        log(f"FAILED: {type(e).__name__}: {e}")
        logf.close()
        # keep the log of a failed run next to (not inside) the model registry
        failed = out_dir.with_name(out_dir.name + ".failed")
        shutil.rmtree(failed, ignore_errors=True)
        os.replace(tmp, failed)
        raise


def verify_model(model_dir: Path) -> dict:
    """Checksum + reload + finite prediction + schema checks. Used by promotion."""
    model_dir = Path(model_dir); out = dict(checks={}, ok=False)
    try:
        man = json.loads((model_dir / "manifest.json").read_text())
        out["checks"]["checksum_matches"] = I.sha256_file(model_dir / "model.joblib") == man["model_sha256"]
        if not out["checks"]["checksum_matches"]:   # never unpickle an artifact whose checksum does not match
            out["error"] = "model.joblib does not match its recorded SHA-256; not loaded"
            return out
        gw = EdgeGateway.load(model_dir)
        out["checks"]["schema_matches"] = gw.features == S.FEATURE_NAMES
        pre = json.loads((model_dir / "preprocessing.json").read_text())
        out["checks"]["medians_complete_finite"] = all(np.isfinite(pre["medians"].get(n, np.nan)) for n in S.FEATURE_NAMES)
        r = gw.process_record({})
        out["checks"]["finite_prediction_all_missing"] = bool(np.isfinite(r["prediction"]))
        r = gw.process_record({n: pre["medians"][n] for n in S.FEATURE_NAMES})
        out["checks"]["finite_prediction_typical"] = bool(np.isfinite(r["prediction"]))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["ok"] = bool(out["checks"]) and all(out["checks"].values()) and "error" not in out
    return out


if __name__ == "__main__":
    ds, bm, name = sys.argv[1:4]
    train(C.DATASETS / ds, C.BENCHMARKS / bm, C.MODELS / name)
