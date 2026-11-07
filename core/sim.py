"""Artificial sensor-failure injection on numpy arrays. Only INPUT cells are masked; targets are never touched.
Rates are fractions of OBSERVED (non-NaN) input cells, so natural and artificial missingness stay separable."""
from __future__ import annotations
import numpy as np
import core.config as C


def _segments(station: np.ndarray, ts_ns: np.ndarray) -> np.ndarray:
    brk = np.zeros(len(ts_ns), dtype=bool)
    brk[0] = True
    brk[1:] = (station[1:] != station[:-1]) | ((ts_ns[1:] - ts_ns[:-1]) != 3_600_000_000_000)
    return np.cumsum(brk) - 1


def _finish(X, mask, elig, rate, pattern, seed, extra):
    Xm = X.copy()
    Xm[mask] = np.nan
    n_elig, n_mask = int(elig.sum()), int(mask.sum())
    meta = dict(pattern=pattern, requested_rate=rate, seed=int(seed), eligible_cells=n_elig, masked_cells=n_mask,
                achieved_rate=(n_mask / n_elig if n_elig else 0.0), natural_missing_rate=float(1 - elig.mean()),
                total_missing_rate=float(np.isnan(Xm).mean()), **extra)
    return Xm, meta


def inject_random(X, rate, seed):
    elig = ~np.isnan(X)
    idx = np.flatnonzero(elig.ravel())
    k = int(round(rate * len(idx)))
    rng = np.random.default_rng(seed)
    pick = rng.choice(idx, size=k, replace=False) if k else np.array([], dtype=np.int64)
    m = np.zeros(elig.size, dtype=bool)
    m[pick] = True
    return _finish(X, m.reshape(elig.shape), elig, rate, "random", seed, {})


def inject_consecutive(X, rate, seed, station, ts_ns, block_range=C.BLOCK_LEN_RANGE):
    """Blocks of L~U{6..48} contiguous hourly records of ONE sensor at ONE station, confined to unbroken hourly
    segments; drawn until the count of newly masked OBSERVED cells equals round(rate*observed); last block truncated."""
    elig = ~np.isnan(X)
    n_target = int(round(rate * int(elig.sum())))
    mask = np.zeros_like(elig)
    n_rows, n_feat = elig.shape
    rng = np.random.default_rng(seed)
    seg = _segments(station, ts_ns)
    starts = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
    lens = np.r_[starts[1:], n_rows] - starts
    done = blocks = attempts = 0
    while done < n_target and attempts < 2_000_000:
        attempts += 1
        L = int(rng.integers(block_range[0], block_range[1] + 1))
        ok = np.flatnonzero(lens >= L)
        if len(ok) == 0:
            L = int(lens.max()); ok = np.flatnonzero(lens >= L)
        s = int(rng.choice(ok, p=lens[ok] / lens[ok].sum()))
        a = int(starts[s] + rng.integers(0, lens[s] - L + 1))
        f = int(rng.integers(0, n_feat))
        rows = np.arange(a, a + L)
        new = rows[elig[rows, f] & ~mask[rows, f]][: n_target - done]
        if len(new) == 0:
            continue
        mask[new, f] = True
        done += len(new)
        blocks += 1
    if done != n_target:
        raise RuntimeError(f"Could not reach requested missingness ({done}/{n_target}).")
    return _finish(X, mask, elig, rate, "consecutive", seed, dict(blocks=blocks, block_len_range=list(block_range)))


def inject(X, rate, pattern, seed, station=None, ts_ns=None):
    if rate == 0.0 or pattern == "none":
        return _finish(X, np.zeros(X.shape, bool), ~np.isnan(X), 0.0, "none", seed, {})
    if pattern == "random":
        return inject_random(X, rate, seed)
    if pattern == "consecutive":
        if station is None or ts_ns is None:
            raise ValueError("consecutive pattern requires station and timestamp arrays")
        return inject_consecutive(X, rate, seed, np.asarray(station), np.asarray(ts_ns, dtype=np.int64))
    raise ValueError(f"unknown pattern {pattern!r}")
