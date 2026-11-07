"""Dashboard aggregates derived from a dataset version (derived artifact: dashboard.json, not part of the checksum)."""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

import core.config as C
from core import datasets as D, ingest as I, schema as S

# CPCB National AQI sub-index bands for 24-h PM2.5 (ug/m3); applied here to HOURLY values as a descriptive grouping only.
BANDS = [("Good", 0, 30), ("Satisfactory", 30, 60), ("Moderate", 60, 90), ("Poor", 90, 120), ("Very poor", 120, 250), ("Severe", 250, 1e9)]


def _cat_share(v: np.ndarray) -> list[float]:
    n = max(len(v), 1)
    return [round(100 * float(((v >= lo) & (v < hi)).sum()) / n, 2) for _, lo, hi in BANDS]


def compute(dataset_dir: Path, info=None) -> dict:
    rec = D.load_records(dataset_dir)
    codes, st, ts, y, X = rec["codes"], rec["station"], rec["ts_ns"], rec["y"].astype(np.float64), rec["X"]
    t = pd.to_datetime(ts)
    df = pd.DataFrame({"st": st, "y": y, "month": t.to_period("M").astype(str), "hour": t.hour, "moy": t.month})
    monthly = df.groupby("month").y.agg(["mean", "count"]).reset_index()
    stations = []
    for i, c in enumerate(codes):
        m = st == i
        if not m.any():
            continue
        v = y[m]
        meta = I.station_meta(c, info)
        stations.append(dict(station=c, **{k: meta[k] for k in ("verified", "state", "city", "location", "agency")},
                             rows=int(m.sum()), mean=round(float(v.mean()), 2), median=round(float(np.median(v)), 2),
                             p95=round(float(np.percentile(v, 95)), 2), first=str(t[m].min())[:10], last=str(t[m].max())[:10],
                             category_share=_cat_share(v),
                             sensor_coverage={n: round(100 * float(1 - np.isnan(X[m, j]).mean()), 1) for j, n in enumerate(S.FEATURE_NAMES)}))
    sm = df.groupby(["st", "month"]).y.mean().round(2).reset_index()
    station_monthly = {}
    for r in sm.itertuples():
        station_monthly.setdefault(codes[r.st], []).append([r.month, r.y])
    states = {}
    for s in stations:
        if s["state"]:
            states.setdefault(s["state"], []).append(s)
    state_rows = [dict(state=k, stations=len(v), rows=int(sum(x["rows"] for x in v)),
                       mean=round(float(np.average([x["mean"] for x in v], weights=[x["rows"] for x in v])), 2)) for k, v in states.items()]
    out = dict(
        dataset_version=rec["manifest"]["dataset_version"], bands=[dict(label=b, lo=lo, hi=None if hi > 1e8 else hi) for b, lo, hi in BANDS],
        overall=dict(rows=int(len(y)), stations=len(stations), mean=round(float(y.mean()), 2), median=round(float(np.median(y)), 2),
                     p95=round(float(np.percentile(y, 95)), 2), category_share=_cat_share(y),
                     first=str(t.min())[:10], last=str(t.max())[:10]),
        monthly=[dict(month=r.month, mean=round(r.mean, 2), n=int(r.count)) for r in monthly.itertuples()],
        hour_profile=[round(float(v), 2) for v in df.groupby("hour").y.mean().reindex(range(24)).fillna(0)],
        month_profile=[round(float(v), 2) for v in df.groupby("moy").y.mean().reindex(range(1, 13)).fillna(0)],
        stations=sorted(stations, key=lambda s: s["station"]), station_monthly=station_monthly,
        states=sorted(state_rows, key=lambda r: -r["mean"]))
    return out


def write(dataset_dir: Path, info=None) -> Path:
    d = compute(dataset_dir, info)
    p = Path(dataset_dir) / "dashboard.json"
    p.write_text(json.dumps(d))
    return p
