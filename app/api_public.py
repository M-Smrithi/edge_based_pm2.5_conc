"""Public JSON API (no login). Reads only derived, non-sensitive aggregates and the active model."""
from __future__ import annotations
import io, json, re, secrets
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Blueprint, abort, jsonify, request, send_file

import core.config as C
from app import services as SV
from app.db import get_db
from app.security import csrf_token, iso, now
from core import analytics, experiments as E, metrics as M, schema as S

bp = Blueprint("public_api", __name__, url_prefix="/api")
_dash_cache: dict = {}


def band_of(v: float) -> str:
    for label, lo, hi in analytics.BANDS:
        if lo <= v < hi: return label
    return analytics.BANDS[-1][0]


def _dashboard():
    """Dashboard aggregates of the dataset behind the active model (or the newest dataset)."""
    con = get_db(); a = SV.get_active(con)
    ds = a["dataset_version"] if a else None
    if not ds:
        r = con.execute("SELECT id FROM dataset_versions ORDER BY created_utc DESC, id DESC LIMIT 1").fetchone(); ds = r["id"] if r else None
    if not ds: return None
    p = C.DATASETS / ds / "dashboard.json"
    if not p.exists(): return None
    key = (str(p), p.stat().st_mtime)
    if key not in _dash_cache:
        _dash_cache.clear(); _dash_cache[key] = json.loads(p.read_text())
    return _dash_cache[key]


def _latest_experiment(con):
    a = SV.get_active(con)
    r = None
    if a: r = con.execute("SELECT * FROM experiments WHERE model_id=? ORDER BY created_utc DESC, id DESC LIMIT 1", (a["id"],)).fetchone()
    if not r: r = con.execute("SELECT * FROM experiments ORDER BY created_utc DESC, id DESC LIMIT 1").fetchone()
    return r


@bp.get("/csrf")
def csrf(): return jsonify(token=csrf_token())


@bp.get("/public/status")
def status():
    con = get_db(); a = SV.get_active(con); d = _dashboard(); e = _latest_experiment(con)
    out = dict(model_available=bool(a), data_available=bool(d), experiment_available=bool(e))
    if a:
        met = json.loads(a["metrics_json"]); man = json.loads((C.MODELS / a["id"] / "manifest.json").read_text())
        sel = next(c for c in met["candidates"] if c["name"] == met["selected"])
        out["model"] = dict(id=a["id"], algorithm=met["selected"].replace("_", " "), trained_utc=man["created_utc"], train_rows=man["train_rows"],
                            test=met.get("test"), latency_ms=sel["latency_ms"], size_mb=sel["size_mb"], dataset_version=a["dataset_version"],
                            benchmark_id=a["benchmark_id"], sensors=len(S.FEATURE_NAMES))
    if d: out["data"] = d["overall"]; out["data"]["dataset_version"] = d["dataset_version"]
    return jsonify(out)


@bp.get("/public/dashboard")
def dashboard():
    d = _dashboard()
    if not d: return jsonify(available=False)
    st = request.args.get("station")
    out = dict(available=True, dataset_version=d["dataset_version"], bands=d["bands"], overall=d["overall"],
               hour_profile=d["hour_profile"], month_profile=d["month_profile"], states=d["states"],
               stations=[{k: s[k] for k in ("station", "city", "state", "location", "rows", "mean", "median", "p95", "first", "last", "category_share", "verified")} for s in d["stations"]])
    if st:
        s = next((x for x in d["stations"] if x["station"] == st), None)
        if not s: abort(404, description="Unknown station.")
        out["selected"] = dict(station=s, monthly=[dict(month=m, mean=v) for m, v in d["station_monthly"].get(st, [])])
    else:
        out["monthly"] = d["monthly"]
    return jsonify(out)


@bp.get("/public/research")
def research():
    con = get_db(); e = _latest_experiment(con)
    if not e: return jsonify(available=False)
    exp_dir = C.EXPERIMENTS / e["id"]
    res = json.loads((exp_dir / "results.json").read_text()); man = json.loads((exp_dir / "manifest.json").read_text())
    summ = E.summarise(res)
    mm = json.loads((C.MODELS / e["model_id"] / "metrics.json").read_text())
    bench = json.loads((C.BENCHMARKS / e["benchmark_id"] / "benchmark.json").read_text())
    ds = json.loads((C.DATASETS / e["dataset_version"] / "manifest.json").read_text())
    figs = sorted(p.name for p in (exp_dir / "figures").glob("*.png")) if (exp_dir / "figures").exists() else []
    return jsonify(available=True, experiment=man, summary=summ, latency=res["latency"], candidates=mm["candidates"], selected=mm["selected"],
                   selection_rule=mm["selection_rule"], split_counts=mm["split_counts"],
                   benchmark={k: bench[k] for k in ("benchmark_id", "t1", "t2", "n_test_temporal", "n_test_spatial", "holdout_stations", "seed", "created_from_dataset")},
                   dataset={k: ds[k] for k in ("dataset_version", "rows", "n_files", "n_stations", "ts_min", "ts_max", "complete_case_rows", "natural_missing_pct_by_sensor", "duplicates")},
                   figures=figs, samples=res["samples"],
                   model_is_active=bool((a := SV.get_active(con)) and a["id"] == e["model_id"]))


@bp.get("/public/figure/<exp_id>/<name>")
def figure(exp_id, name):
    if not re.fullmatch(r"exp-\d{4,}", exp_id) or not re.fullmatch(r"[a-z_]+\.png", name): abort(404)
    p = C.EXPERIMENTS / exp_id / "figures" / name
    if not p.is_file(): abort(404)
    return send_file(p, mimetype="image/png", max_age=3600)


@bp.get("/public/methodology")
def methodology():
    return jsonify(features=[dict(name=n, unit=S.FEATURES[n].unit, label=S.FEATURES[n].label, valid_range=list(S.FEATURES[n].valid_range)) for n in S.FEATURE_NAMES],
                   target=dict(name=C.TARGET, unit="µg/m³"), rates=C.MISSING_RATES, patterns=C.PATTERNS, block_len_range=list(C.BLOCK_LEN_RANGE),
                   train_frac=C.TRAIN_FRAC, val_frac=C.VAL_FRAC, holdout_station_frac=C.HOLDOUT_STATION_FRAC, default_trials=C.DEFAULT_TRIALS,
                   latency_records=C.LATENCY_N_RECORDS, min_station_rows=C.MIN_STATION_VALID_ROWS, bands=[dict(label=b, lo=lo, hi=None if hi > 1e8 else hi) for b, lo, hi in analytics.BANDS])


# ------------------------------------------------------------------ prediction
def _purge_predictions(con):
    for r in con.execute("SELECT token,path FROM prediction_runs WHERE expires_utc < ?", (iso(),)).fetchall():
        try: Path(r["path"]).unlink(missing_ok=True)
        except OSError: pass
        con.execute("DELETE FROM prediction_runs WHERE token=?", (r["token"],))


@bp.post("/public/predict")
def predict():
    con = get_db(); a, gw = SV.active_gateway(con)
    if not gw: return jsonify(error="No active model is available yet."), 503
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("features", {}), dict): abort(400, description="Send JSON: {\"features\": {sensor: value}}")
    rec = {k: v for k, v in body["features"].items() if isinstance(k, str) and len(k) < 20}
    out = gw.process_record(rec)
    pm = out["prediction"]
    return jsonify(model_id=a["id"], prediction=round(pm, 2), unit="µg/m³", category=band_of(pm), missing=out["missing"], invalid=out["invalid"],
                   unknown_fields=out["unknown_fields"], imputed=out["imputed"], n_provided=len(S.FEATURE_NAMES) - len(out["missing"]),
                   latency_ms=dict(preprocess=round(out["preprocess_ms"], 4), inference=round(out["inference_ms"], 3), total=round(out["total_ms"], 3)),
                   note="Estimate for the same hour from co-located sensor readings. Missing/invalid readings were replaced by training-set medians.")


def _resolve_columns(cols):
    """Map uploaded headers to canonical sensors using only verified header resolution (alias / SI conversion)."""
    res = S.resolve_header([str(c).strip() for c in cols])
    mapping, notes = {}, []
    for n in S.FEATURE_NAMES:
        r = res[n]
        if r["status"] in ("exact", "converted"):
            mapping[n] = (r["raw"], r.get("factor", 1.0))
            if r["status"] == "converted": notes.append(f"{n}: '{r['raw']}' converted ×{r['factor']:g}")
    for c in cols:                      # bare canonical names ("PM10", "AT", ...) are accepted too
        c2 = str(c).strip()
        if c2 in S.FEATURE_NAMES and c2 not in mapping: mapping[c2] = (c, 1.0)
    return mapping, notes


@bp.post("/public/predict-csv")
def predict_csv():
    con = get_db(); a, gw = SV.active_gateway(con)
    if not gw: return jsonify(error="No active model is available yet."), 503
    f = request.files.get("file")
    if not f or not f.filename: abort(400, description="Choose a CSV file.")
    if not f.filename.lower().endswith(".csv"): abort(400, description="Only .csv files are accepted.")
    raw = f.read(C.MAX_PREDICT_FILE_BYTES + 1)
    if len(raw) > C.MAX_PREDICT_FILE_BYTES: abort(413, description=f"File exceeds {C.MAX_PREDICT_FILE_BYTES // 2**20} MB.")
    try:
        df = pd.read_csv(io.BytesIO(raw), nrows=C.MAX_PREDICT_ROWS + 1, encoding_errors="strict")
    except UnicodeDecodeError: abort(400, description="File is not valid UTF-8 text.")
    except Exception as e: abort(400, description=f"Could not parse CSV: {str(e)[:120]}")
    if len(df) == 0: abort(400, description="The file has a header but no rows.")
    if len(df) > C.MAX_PREDICT_ROWS: abort(413, description=f"File exceeds {C.MAX_PREDICT_ROWS:,} rows.")
    df.columns = [str(c).strip() for c in df.columns]
    mapping, notes = _resolve_columns(df.columns)
    if not mapping:
        abort(400, description="No recognised sensor columns. Expected any of: " + ", ".join(S.FEATURE_NAMES) + " (or CPCB headers such as 'PM10 (ug/m3)').")
    A = np.full((len(df), len(S.FEATURE_NAMES)), np.nan); nonnumeric = 0
    for j, n in enumerate(S.FEATURE_NAMES):
        if n in mapping:
            col, fac = mapping[n]
            v = pd.to_numeric(df[col], errors="coerce"); nonnumeric += int((v.isna() & df[col].notna()).sum())
            A[:, j] = v.to_numpy() * fac
    clean = gw.preprocess_array(A)
    pred = gw.model.predict(clean)
    miss = np.isnan(A) | ~np.isfinite(A) | (A < gw._lo) | (A > gw._hi)
    out = pd.DataFrame(index=df.index)
    for c in df.columns:
        if str(c).lower() in ("station", "timestamp", "from date", "id", "to date") : out[c] = df[c]
    for j, n in enumerate(S.FEATURE_NAMES): out[n] = np.where(miss[:, j], np.nan, A[:, j])
    out["imputed_sensors"] = [";".join(n for n, m in zip(S.FEATURE_NAMES, r) if m) for r in miss]
    out["n_imputed"] = miss.sum(1); out["pm25_prediction"] = np.round(pred, 2); out["category"] = [band_of(v) for v in pred]
    evaluation = None
    tcol = next((c for c in df.columns if c in (C.TARGET, C.TARGET_RAW)), None)
    if tcol:
        t = pd.to_numeric(df[tcol], errors="coerce"); ok = t.notna().to_numpy() & t.between(*C.TARGET_RANGE).to_numpy()
        if ok.sum() > 0: out["pm25_actual"] = t; evaluation = M.regression(t[ok], pred[ok])
    _purge_predictions(con)
    token = secrets.token_urlsafe(18); C.PREDICTIONS.mkdir(parents=True, exist_ok=True); path = C.PREDICTIONS / f"{token}.csv"
    out.to_csv(path, index=False)
    con.execute("INSERT INTO prediction_runs(token,created_utc,expires_utc,rows,model_id,path) VALUES(?,?,?,?,?,?)",
                (token, iso(), iso(now() + timedelta(hours=C.PREDICTION_TTL_HOURS)), len(out), a["id"], str(path)))
    prev = out.head(50).replace({np.nan: None}).to_dict("records")
    return jsonify(token=token, rows=int(len(out)), model_id=a["id"], recognised=list(mapping), unrecognised=[c for c in df.columns if c not in {m[0] for m in mapping.values()}][:30],
                   conversions=notes, absent_sensors=[n for n in S.FEATURE_NAMES if n not in mapping], non_numeric_values=nonnumeric,
                   missing_pct_by_sensor={n: round(100 * float(miss[:, j].mean()), 1) for j, n in enumerate(S.FEATURE_NAMES)},
                   rows_all_sensors_missing=int(miss.all(1).sum()), evaluation=evaluation, preview=prev,
                   mean_prediction=round(float(pred.mean()), 2), expires_hours=C.PREDICTION_TTL_HOURS,
                   note="Uploaded data is used only for this prediction. It is never added to the training data.")


@bp.get("/public/predict-download/<token>")
def predict_download(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,40}", token): abort(404)
    r = get_db().execute("SELECT * FROM prediction_runs WHERE token=? AND expires_utc >= ?", (token, iso())).fetchone()
    if not r or not Path(r["path"]).is_file(): abort(404, description="This result has expired.")
    return send_file(r["path"], mimetype="text/csv", as_attachment=True, download_name="pm25_predictions.csv")


@bp.get("/public/template.csv")
def template():
    con = get_db(); a = SV.get_active(con)
    row = {n: "" for n in S.FEATURE_NAMES}
    if a:
        pre = json.loads((C.MODELS / a["id"] / "preprocessing.json").read_text()); row = {n: round(pre["medians"][n], 2) for n in S.FEATURE_NAMES}
    buf = io.StringIO(); pd.DataFrame([{"timestamp": "2023-01-01 08:00", **row}]).to_csv(buf, index=False)
    r = send_file(io.BytesIO(buf.getvalue().encode()), mimetype="text/csv", as_attachment=True, download_name="pm25_input_template.csv"); return r
