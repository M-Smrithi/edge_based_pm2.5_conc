from __future__ import annotations
import numpy as np


def mae(y, p): return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))
def rmse(y, p): return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def r2(y, p):
    y = np.asarray(y, float); p = np.asarray(p, float)
    t = np.sum((y - y.mean()) ** 2)
    return float("nan") if t == 0 else float(1 - np.sum((y - p) ** 2) / t)


def regression(y, p): return dict(mae=mae(y, p), rmse=rmse(y, p), r2=r2(y, p), n=int(len(y)))


def latency(values_ms):
    v = np.asarray(values_ms, float)
    return dict(mean=float(v.mean()), median=float(np.median(v)), p95=float(np.percentile(v, 95)), n=int(len(v)))
