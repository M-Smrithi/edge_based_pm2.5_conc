"""Content-addressed original storage and immutable dataset versions.

A dataset VERSION is a manifest listing accepted files (by sha256, in order) + mapping decisions + dedup policy,
materialised as records.npz (float32) and built in a temp dir that is renamed atomically. Versions are never edited."""
from __future__ import annotations
import hashlib, json, os, shutil, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import core.config as C
from core import ingest as I
from core import schema as S

DEDUP_POLICY = "key=(station,timestamp); keep first by file order; later duplicates counted as 'identical' or 'conflicting'"


def store_original(src: Path, originals_dir: Path | None = None) -> tuple[str, bool]:
    """Copy a file into storage/originals/<sha256>.csv (never overwrites). Returns (sha256, newly_stored)."""
    originals_dir = Path(originals_dir or C.ORIGINALS)
    originals_dir.mkdir(parents=True, exist_ok=True)
    sha = I.sha256_file(Path(src))
    dest = originals_dir / f"{sha}.csv"
    if dest.exists():
        return sha, False
    tmp = originals_dir / f".{sha}.{os.getpid()}.tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    os.chmod(dest, 0o444)
    return sha, True


def original_path(sha: str, originals_dir: Path | None = None) -> Path:
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("bad checksum")
    return Path(originals_dir or C.ORIGINALS) / f"{sha}.csv"


def _frame_to_arrays(df: pd.DataFrame):
    return df[S.FEATURE_NAMES].to_numpy(np.float32), df[C.TARGET].to_numpy(np.float32), df["timestamp"].to_numpy("datetime64[ns]").astype(np.int64)


def build_version(entries: list[dict], dest: Path, originals_dir: Path | None = None, meta: dict | None = None,
                  progress=None) -> dict:
    """entries: [{file_name, sha256, station?, decisions?}] in acceptance order. Atomic: dest appears only on success."""
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"dataset version already exists: {dest.name}")
    tmp = dest.with_name(dest.name + ".building")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        t0 = time.time()
        stations: dict[str, int] = {}
        parts, file_stats = [], []
        for i, e in enumerate(entries):
            path = original_path(e["sha256"], originals_dir)
            code = e.get("station") or I.station_from_filename(e["file_name"])
            raw = I.read_csv_safely(path)
            df, rep = I.canonicalize(raw, code, e.get("decisions"))
            sid = stations.setdefault(code, len(stations))
            X, y, ts = _frame_to_arrays(df)
            parts.append((np.full(len(df), sid, np.int32), ts, X, y, i))
            file_stats.append(dict(file_name=e["file_name"], sha256=e["sha256"], station=code, rows_kept=rep["rows_kept"],
                                   structural_absence=rep["structural_absence"], mapping_log=rep["mapping_log"]))
            if progress:
                progress((i + 1) / len(entries), f"canonicalised {e['file_name']}")
        if not parts:
            raise ValueError("no files to build")
        st = np.concatenate([p[0] for p in parts]); ts = np.concatenate([p[1] for p in parts])
        X = np.vstack([p[2] for p in parts]); y = np.concatenate([p[3] for p in parts])
        order_file = np.concatenate([np.full(len(p[0]), p[4], np.int32) for p in parts])
        n_in = len(st)
        # stable sort by (station, ts, file order) then drop later duplicates
        o = np.lexsort((order_file, ts, st))
        st, ts, X, y, order_file = st[o], ts[o], X[o], y[o], order_file[o]
        dup = np.r_[False, (st[1:] == st[:-1]) & (ts[1:] == ts[:-1])]
        same_prev = np.zeros(len(st), bool)
        idx = np.flatnonzero(dup)
        if len(idx):
            a = np.concatenate([X[idx], y[idx, None]], 1); b = np.concatenate([X[idx - 1], y[idx - 1, None]], 1)
            same_prev[idx] = np.all((a == b) | (np.isnan(a) & np.isnan(b)), axis=1)
        n_identical, n_conflict = int((dup & same_prev).sum()), int((dup & ~same_prev).sum())
        per_file_dups = np.bincount(order_file[dup], minlength=len(entries)).tolist()
        keep = ~dup
        st, ts, X, y, order_file = st[keep], ts[keep], X[keep], y[keep], order_file[keep]
        for i, fs in enumerate(file_stats):
            fs["duplicates_dropped"] = int(per_file_dups[i])
            fs["unique_contributed"] = int((order_file == i).sum())
        codes = [None] * len(stations)
        for c, i in stations.items():
            codes[i] = c
        np.savez_compressed(tmp / "records.npz", station=st, ts_ns=ts, X=X, y=y)
        per_station = []
        for i, c in enumerate(codes):
            m = st == i
            if m.any():
                per_station.append(dict(station=c, rows=int(m.sum()), first=str(np.datetime64(int(ts[m].min()), "ns"))[:19],
                                        last=str(np.datetime64(int(ts[m].max()), "ns"))[:19],
                                        complete_case=int((~np.isnan(X[m]).any(1)).sum())))
        miss = {n: round(float(np.isnan(X[:, j]).mean() * 100), 3) for j, n in enumerate(S.FEATURE_NAMES)}
        manifest = dict(
            dataset_version=dest.name, created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            n_files=len(entries), n_stations=len(per_station), rows_before_dedup=int(n_in), rows=int(len(st)),
            duplicates=dict(identical=n_identical, conflicting=n_conflict, policy=DEDUP_POLICY),
            ts_min=str(np.datetime64(int(ts.min()), "ns"))[:19], ts_max=str(np.datetime64(int(ts.max()), "ns"))[:19],
            complete_case_rows=int((~np.isnan(X).any(1)).sum()), natural_missing_pct_by_sensor=miss,
            features=S.FEATURE_NAMES, target=C.TARGET, stations=codes, per_station=per_station, files=file_stats,
            records_sha256=I.sha256_file(tmp / "records.npz"), build_seconds=round(time.time() - t0, 1), **(meta or {}))
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
        try:
            from core import analytics
            analytics.write(tmp, I.load_stations_info())
        except Exception as e:  # dashboard aggregates are optional; never fail the build for them
            manifest['analytics_error'] = str(e)
            (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
        os.replace(tmp, dest)
        return manifest
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def load_records(dir_: Path) -> dict:
    dir_ = Path(dir_)
    man = json.loads((dir_ / "manifest.json").read_text())
    with np.load(dir_ / "records.npz", allow_pickle=False) as z:
        rec = {k: z[k] for k in z.files}
    rec["codes"] = man["stations"]
    rec["manifest"] = man
    return rec


def verify_version(dir_: Path) -> bool:
    man = json.loads((Path(dir_) / "manifest.json").read_text())
    return I.sha256_file(Path(dir_) / "records.npz") == man["records_sha256"]
