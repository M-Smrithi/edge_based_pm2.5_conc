"""Frozen, versioned evaluation benchmark.

Created once from a dataset version and then immutable. Later dataset versions are split against it, so the
temporal-test and spatial-test records never change:
  train     station not held out, ts < T1
  val       station not held out, T1 <= ts < T2
  test_temporal  frozen record keys (non-held-out stations, ts >= T2 at creation)
  test_spatial   frozen record keys (held-out stations, ts >= T2 at creation) -- stations never seen in training
  reserve   records that arrive after the benchmark was frozen inside the test window (kept, unused until a new benchmark)
  excluded  held-out stations' pre-T2 records; stations with < MIN_STATION_VALID_ROWS rows"""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import core.config as C

TRAIN, VAL, TEST_T, TEST_S, RESERVE, EXCLUDED = 0, 1, 2, 3, 4, 5
NAMES = {TRAIN: "train", VAL: "val", TEST_T: "test_temporal", TEST_S: "test_spatial", RESERVE: "reserve", EXCLUDED: "excluded"}
_MIN = 60_000_000_000


def is_holdout(code: str, seed: int | None = None, frac: float | None = None) -> bool:
    seed = C.SEED if seed is None else seed
    frac = C.HOLDOUT_STATION_FRAC if frac is None else frac
    h = int(hashlib.sha256(f"{seed}:{code}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < frac


def _keys(code_ids: np.ndarray, ts_ns: np.ndarray) -> np.ndarray:
    return (code_ids.astype(np.int64) << 40) | (ts_ns // _MIN)


def create(rec: dict, benchmark_id: str, dest: Path, seed: int | None = None) -> dict:
    seed = C.SEED if seed is None else seed
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"benchmark {benchmark_id} already exists and is frozen")
    codes, st, ts = rec["codes"], rec["station"], rec["ts_ns"]
    counts = np.bincount(st, minlength=len(codes))
    eligible = [c for i, c in enumerate(codes) if counts[i] >= C.MIN_STATION_VALID_ROWS]
    holdout = sorted(c for c in eligible if is_holdout(c, seed))
    train_pool = np.array([codes[i] in eligible and codes[i] not in holdout for i in st])
    pool_ts = np.sort(ts[train_pool])
    t1 = int(pool_ts[int(C.TRAIN_FRAC * len(pool_ts))])
    t2 = int(pool_ts[int(min(C.TRAIN_FRAC + C.VAL_FRAC, 0.9999) * len(pool_ts))])
    ids = {c: i for i, c in enumerate(sorted(codes))}
    cid = np.array([ids[c] for c in codes])[st]
    in_hold = np.isin(np.array(codes)[st], holdout) if holdout else np.zeros(len(st), bool)
    test_t = train_pool & (ts >= t2)
    test_s = in_hold & (ts >= t2)
    b = dict(benchmark_id=benchmark_id, created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             seed=seed, min_station_rows=C.MIN_STATION_VALID_ROWS, holdout_fraction=C.HOLDOUT_STATION_FRAC,
             train_frac=C.TRAIN_FRAC, val_frac=C.VAL_FRAC, t1_ns=t1, t2_ns=t2,
             t1=str(np.datetime64(t1, "ns"))[:19], t2=str(np.datetime64(t2, "ns"))[:19],
             station_ids=ids, eligible_stations=eligible, holdout_stations=holdout,
             ineligible_stations=sorted(set(codes) - set(eligible)),
             n_test_temporal=int(test_t.sum()), n_test_spatial=int(test_s.sum()),
             created_from_dataset=rec["manifest"]["dataset_version"], dataset_records_sha256=rec["manifest"]["records_sha256"])
    kt, ks = np.sort(_keys(cid[test_t], ts[test_t])), np.sort(_keys(cid[test_s], ts[test_s]))
    tmp = dest.with_name(dest.name + ".building"); tmp.mkdir(parents=True)
    np.savez_compressed(tmp / "keys.npz", test_temporal=kt, test_spatial=ks)
    h = hashlib.sha256(); h.update(kt.tobytes()); h.update(ks.tobytes()); h.update(json.dumps(holdout).encode())
    h.update(str((t1, t2)).encode())
    b["benchmark_sha256"] = h.hexdigest()
    (tmp / "benchmark.json").write_text(json.dumps(b, indent=1))
    os.replace(tmp, dest)
    return b


def load(dest: Path) -> dict:
    dest = Path(dest)
    b = json.loads((dest / "benchmark.json").read_text())
    with np.load(dest / "keys.npz", allow_pickle=False) as z:
        b["_kt"], b["_ks"] = z["test_temporal"], z["test_spatial"]
    return b


def assign(rec: dict, bench: dict) -> np.ndarray:
    """Split label per record of ANY dataset version against the frozen benchmark."""
    codes, st, ts = np.array(rec["codes"]), rec["station"], rec["ts_ns"]
    counts = np.bincount(st, minlength=len(codes))
    ids = bench["station_ids"]
    code_of_rec = codes[st]
    holdout = np.isin(code_of_rec, bench["holdout_stations"])
    eligible = np.isin(code_of_rec, bench["eligible_stations"]) | (counts[st] >= bench["min_station_rows"])
    lab = np.full(len(st), EXCLUDED, np.int8)
    ok = eligible & ~holdout
    lab[ok & (ts < bench["t1_ns"])] = TRAIN
    lab[ok & (ts >= bench["t1_ns"]) & (ts < bench["t2_ns"])] = VAL
    lab[ok & (ts >= bench["t2_ns"])] = RESERVE
    lab[holdout & (ts >= bench["t2_ns"])] = RESERVE
    # frozen test keys (only stations known to the benchmark can match)
    known = np.array([c in ids for c in codes])[st]
    cid = np.array([ids.get(c, 0) for c in codes])[st]
    k = _keys(cid, ts)
    lab[known & np.isin(k, bench["_kt"]) & ok] = TEST_T
    lab[known & np.isin(k, bench["_ks"]) & holdout] = TEST_S
    return lab


def summary(lab: np.ndarray) -> dict:
    return {NAMES[i]: int((lab == i).sum()) for i in NAMES}
