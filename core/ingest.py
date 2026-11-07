"""Safe CSV reading, per-file audit, canonicalisation and the documented cleaning policy.

Cleaning policy (applied in this order, every count is reported):
 1 parse timestamps (unparseable -> row dropped)         2 duplicate (station, timestamp) within a file -> keep first
 3 coerce numerics; +/-inf -> NaN                         4 value outside the physical range -> NaN (reading invalid)
 5 rows without a valid PM2.5 target are dropped          6 rows where every sensor is NaN are dropped
Rows with only SOME sensors missing are KEPT: incomplete inputs are central to this research and are handled
later by training-set median imputation.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import core.config as C
from core import schema as S

STATION_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
CODE_RE = re.compile(r"^[A-Z]{2}\d{3}$")


def sha256_file(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


REUPLOAD_RE = re.compile(r"^(?P<code>[A-Za-z]{2}\d{3})(?:[_-]?(?:copy|dup|duplicate|new|\d{1,2}))+$", re.I)


def station_from_filename(name: str) -> str | None:
    """Station id from the filename stem. Re-upload suffixes (AP001_copy, AP001-2) normalise to the base code so
    that their records are de-duplicated against the original station rather than counted as a new station."""
    stem = Path(name).stem
    if not STATION_RE.match(stem):
        return None
    m = REUPLOAD_RE.match(stem)
    return m.group("code").upper() if m else stem


def load_stations_info(path: Path = None) -> pd.DataFrame | None:
    path = path or C.STATIONS_INFO
    if not Path(path).exists():
        return None
    df = pd.read_csv(path)
    return df.set_index("file_name") if "file_name" in df.columns else None


def station_meta(code: str, info: pd.DataFrame | None) -> dict:
    """Geographic identity only when metadata confirms the station code. Never inferred from the filename."""
    if info is not None and code in info.index:
        r = info.loc[code]
        return dict(verified=True, state=str(r.get("state", "")), city=str(r.get("city", "")),
                    agency=str(r.get("agency", "")), location=str(r.get("station_location", "")).strip())
    return dict(verified=False, state=None, city=None, agency=None, location=None)


# ------------------------------------------------------------------------------------------------------
def read_csv_safely(path: Path) -> pd.DataFrame:
    if Path(path).stat().st_size == 0:
        raise ValueError("File is empty.")
    try:
        df = pd.read_csv(path, nrows=C.MAX_UPLOAD_ROWS + 1, low_memory=False, encoding_errors="strict")
    except UnicodeDecodeError:
        raise ValueError("File is not valid UTF-8 text.")
    except pd.errors.EmptyDataError:
        raise ValueError("File has no data.")
    except pd.errors.ParserError as e:
        raise ValueError(f"Malformed CSV: {str(e)[:160]}")
    if len(df) > C.MAX_UPLOAD_ROWS:
        raise ValueError(f"File exceeds the row limit ({C.MAX_UPLOAD_ROWS:,}).")
    if df.shape[1] < 2:
        raise ValueError("CSV has fewer than 2 columns.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def canonicalize(df: pd.DataFrame, station: str, decisions: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Raw frame -> canonical [station, timestamp, 12 features, PM2.5] + cleaning report.
    `decisions` (administrator-approved, audit-logged): {"blank_unit": {feature: raw_col}, "structural_absence": [feats]}"""
    decisions = decisions or {}
    res = S.resolve_header(list(df.columns))
    rep = dict(station=station, raw_rows=int(len(df)), mapping_log=[], structural_absence=[])
    out = pd.DataFrame({"timestamp": pd.to_datetime(df[C.TIME_COL], errors="coerce")})
    rep["invalid_timestamps"] = int(out.timestamp.isna().sum())
    for name, r in res.items():
        st = r["status"]
        if st == "exact":
            out[name] = pd.to_numeric(df[r["raw"]], errors="coerce")
            if r["raw"] != S.FEATURES[name].exact[0]:
                rep["mapping_log"].append(dict(feature=name, raw=r["raw"], action="alias", factor=1.0,
                                               rationale="alternate header with identical meaning and unit"))
        elif st == "converted":
            out[name] = pd.to_numeric(df[r["raw"]], errors="coerce") * r["factor"]
            rep["mapping_log"].append(dict(feature=name, raw=r["raw"], action="unit_conversion", factor=r["factor"],
                                           rationale=r["rationale"]))
        elif st == "blank_unit" and name in decisions.get("blank_unit", {}):
            out[name] = pd.to_numeric(df[r["raw"]], errors="coerce")
            rep["mapping_log"].append(dict(feature=name, raw=r["raw"], action="admin_approved_blank_unit", factor=1.0,
                                           rationale="administrator asserted the unit equals the canonical unit"))
        else:
            out[name] = np.nan
            rep["structural_absence"].append(name)
    out[C.TARGET] = pd.to_numeric(df[C.TARGET_RAW], errors="coerce")
    out = out[out.timestamp.notna()]
    n = len(out)
    out = out.drop_duplicates("timestamp", keep="first")
    rep["duplicate_timestamps_removed"] = int(n - len(out))
    cols = S.FEATURE_NAMES + [C.TARGET]
    out[cols] = out[cols].replace([np.inf, -np.inf], np.nan)
    oor = {}
    for name in S.FEATURE_NAMES:
        lo, hi = S.FEATURES[name].valid_range
        bad = out[name].notna() & ~out[name].between(lo, hi)
        oor[name] = int(bad.sum())
        out.loc[bad, name] = np.nan
    lo, hi = C.TARGET_RANGE
    bt = out[C.TARGET].notna() & ~out[C.TARGET].between(lo, hi)
    out.loc[bt, C.TARGET] = np.nan
    rep["out_of_range_set_nan"] = oor
    rep["target_out_of_range"] = int(bt.sum())
    n = len(out)
    out = out[out[C.TARGET].notna()]
    rep["rows_dropped_missing_target"] = int(n - len(out))
    n = len(out)
    out = out[out[S.FEATURE_NAMES].notna().any(axis=1)]
    rep["rows_dropped_all_sensors_missing"] = int(n - len(out))
    out = out.sort_values("timestamp").reset_index(drop=True)
    out.insert(0, "station", station)
    rep["rows_kept"] = int(len(out))
    return out, rep


# ------------------------------------------------------------------------------------------------------
def audit_file(path: Path, display_name: str | None = None, info: pd.DataFrame | None = None,
               decisions: dict | None = None) -> dict:
    """Full machine-readable audit of ONE file. Never modifies the file. Verdict is one of:
    accepted | accepted_recovered | pending_review | rejected."""
    path = Path(path)
    name = display_name or path.name
    a = dict(file_name=name, size_bytes=path.stat().st_size, sha256=sha256_file(path), reasons=[], proposals=[],
             verdict="rejected")
    code = station_from_filename(name)
    a["station"] = code
    a["station_meta"] = station_meta(code, info) if code else dict(verified=False)
    if not code:
        a["reasons"].append("Filename is not a safe station identifier (use letters/digits/_/-, max 32 chars).")
        return a
    if not name.lower().endswith(".csv"):
        a["reasons"].append("Only .csv files are accepted.")
        return a
    try:
        df = read_csv_safely(path)
    except ValueError as e:
        a["reasons"].append(str(e))
        return a
    header = list(df.columns)
    a["columns"] = header
    a["n_columns"] = len(header)
    a["rows"] = int(len(df))
    if C.TIME_COL not in header:
        a["reasons"].append(f"Missing timestamp column '{C.TIME_COL}'.")
        return a
    ts = pd.to_datetime(df[C.TIME_COL], errors="coerce")
    a["bad_timestamps"] = int(ts.isna().sum())
    if ts.notna().sum() == 0:
        a["reasons"].append("No parseable timestamps.")
        return a
    a["ts_min"], a["ts_max"] = str(ts.min()), str(ts.max())
    a["duplicate_timestamps"] = int(ts.dropna().duplicated().sum())
    a["target_status"] = S.target_status(header)
    if a["target_status"] != "ok":
        a["reasons"].append("No PM2.5 target column." if a["target_status"] == "absent"
                            else "PM2.5 column present but its unit header is not 'ug/m3'.")
        a["target_valid"] = 0
        return a
    tv = pd.to_numeric(df[C.TARGET_RAW], errors="coerce")
    a["target_valid"] = int(tv.notna().sum())
    a["target_missing_pct"] = round(100 * float(tv.isna().mean()), 2)
    res = S.resolve_header(header)
    a["feature_resolution"] = res
    unit_issues = {n: r for n, r in res.items() if r["status"] in ("blank_unit", "bad_unit")}
    a["unit_issues"] = {n: dict(raw=r["raw"], note=r.get("note", "")) for n, r in unit_issues.items()}
    # missingness per usable raw column
    miss = {}
    for n, r in res.items():
        if r["status"] in ("exact", "converted"):
            miss[n] = round(100 * float(pd.to_numeric(df[r["raw"]], errors="coerce").isna().mean()), 2)
        else:
            miss[n] = None
    a["missing_pct_by_feature"] = miss
    # conversions must be supported by evidence: converted values must fall in a plausible range
    for n, r in res.items():
        if r["status"] == "converted":
            v = pd.to_numeric(df[r["raw"]], errors="coerce") * r["factor"]
            med = float(v.median()) if v.notna().any() else float("nan")
            lo, hi = S.FEATURES[n].valid_range
            ok = bool(np.isfinite(med) and lo <= med <= hi)
            r["evidence_median_after_conversion"] = None if not np.isfinite(med) else round(med, 4)
            r["evidence_ok"] = ok
            if not ok:
                a["reasons"].append(f"{n}: conversion from '{r['raw']}' not supported by the data (median {med:.3g} outside range).")
    decisions = decisions or {}
    clean, rep = canonicalize(df, code, decisions)
    a["cleaning"] = rep
    a["mapping_log"] = rep["mapping_log"]
    a["valid_rows"] = rep["rows_kept"]
    a["structural_absence"] = rep["structural_absence"]
    a["complete_case_rows"] = int(clean[S.FEATURE_NAMES].notna().all(axis=1).sum())
    a["usable_sensors"] = [n for n in S.FEATURE_NAMES if n not in rep["structural_absence"]]
    if rep["rows_kept"] == 0:
        a["reasons"].append("No usable rows remain after cleaning.")
        return a
    # proposals for review (never applied automatically)
    for n in rep["structural_absence"]:
        r = res[n]
        if r["status"] == "blank_unit" and n not in decisions.get("blank_unit", {}):
            col = pd.to_numeric(df[r["raw"]], errors="coerce")
            lo, hi = S.FEATURES[n].valid_range
            inr = float(col.dropna().between(lo, hi).mean()) if col.notna().any() else 0.0
            a["proposals"].append(dict(kind="blank_unit", feature=n, raw=r["raw"], canonical_unit=S.FEATURES[n].unit,
                                       evidence=f"{100*inr:.0f}% of values fall inside the plausible {S.FEATURES[n].unit} range "
                                                f"{lo}-{hi}; the unit is NOT stated in the file"))
    if rep["structural_absence"]:
        why = []
        for n in rep["structural_absence"]:
            r = res[n]
            why.append(f"{n}: " + {"absent": "no column", "blank_unit": "blank unit in header",
                                    "bad_unit": r.get("note", "unverifiable unit")}.get(r["status"], r["status"]))
        a["reasons"].append("Sensor(s) unavailable: " + "; ".join(why))
        approved_abs = set(decisions.get("structural_absence", []))
        if set(rep["structural_absence"]) <= approved_abs | set(decisions.get("blank_unit", {})):
            a["verdict"] = "accepted_recovered"
        else:
            a["verdict"] = "pending_review"
            return a
    a["verdict"] = "accepted_recovered" if (rep["mapping_log"] or rep["structural_absence"]) else "accepted"
    if any(r.get("evidence_ok") is False for r in res.values() if r["status"] == "converted"):
        a["verdict"] = "rejected"
    return a


def station_keys(path: Path, decisions=None) -> pd.DataFrame:
    """(timestamp) frame for overlap detection (cheap)."""
    df = read_csv_safely(path)
    return pd.DataFrame({"timestamp": pd.to_datetime(df[C.TIME_COL], errors="coerce")}).dropna()
