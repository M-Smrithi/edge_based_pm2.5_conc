"""Domain services: file intake, review decisions, dataset signatures, model registry (promotion checks, rollback)."""
from __future__ import annotations
import hashlib, json, os, re, shutil, tempfile
from pathlib import Path

import numpy as np

import core.config as C
from app.db import tx
from app.security import audit, iso
from core import benchmark as B, datasets as D, experiments as E, ingest as I, metrics as M, schema as S, train as T
from core.gateway import EdgeGateway

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def clean_filename(name: str) -> str:
    return SAFE_NAME.sub("_", Path(name or "").name)[:80] or "upload.csv"


# =============================== file intake ======================================
def intake_file(con, stream, filename: str, user, batch_id: int | None = None) -> dict:
    """Validate and register ONE uploaded CSV. Stream is spooled to a private temp file with a hard size cap.
    The original is stored content-addressed and never modified."""
    name = clean_filename(filename)
    C.INCOMING.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=C.INCOMING, suffix=".part"); size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := stream.read(1 << 20):
                size += len(chunk)
                if size > C.MAX_UPLOAD_FILE_BYTES:
                    return dict(file_name=name, status="rejected", reasons=[f"File exceeds {C.MAX_UPLOAD_FILE_BYTES // 2**20} MB limit."], stored=False)
                out.write(chunk)
        info = I.load_stations_info()
        a = I.audit_file(Path(tmp), display_name=name, info=info)
        sha = a["sha256"]
        same = con.execute("SELECT id,file_name,status,uploaded_utc FROM files WHERE sha256=?", (sha,)).fetchone()
        if same:
            audit("upload_duplicate_bytes", name, dict(sha256=sha, existing=same["file_name"]), user)
            return dict(file_name=name, status="duplicate", stored=False, sha256=sha, existing=dict(same),
                        reasons=[f"Byte-identical to '{same['file_name']}' (already {same['status']}); not added again."])
        _, new = D.store_original(Path(tmp))
        overlap = _overlap(con, a, Path(tmp)) if a["verdict"] in ("accepted", "accepted_recovered", "pending_review") else None
        with tx(con):
            cur = con.execute(
                "INSERT INTO files(file_name,sha256,size_bytes,station,status,audit_json,reasons,decisions_json,batch_id,uploaded_by,uploaded_utc,overlap_json)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, sha, size, a.get("station"), a["verdict"], json.dumps(a, default=str), " | ".join(a["reasons"]), "{}",
                 batch_id, user["id"] if user else None, iso(), json.dumps(overlap) if overlap else None))
            audit("upload", name, dict(verdict=a["verdict"], sha256=sha, rows=a.get("rows")), user, con)
        return dict(file_name=name, id=cur.lastrowid, status=a["verdict"], stored=True, sha256=sha, reasons=a["reasons"],
                    rows=a.get("rows"), valid_rows=a.get("valid_rows"), station=a.get("station"), overlap=overlap,
                    proposals=a.get("proposals", []))
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def _overlap(con, a, tmp_path: Path) -> dict | None:
    """Explain how this file relates to files already registered for the same station."""
    if not a.get("station"): return None
    others = con.execute("SELECT file_name,sha256 FROM files WHERE station=? AND status IN ('accepted','accepted_recovered')", (a["station"],)).fetchall()
    if not others: return dict(kind="new_station_or_first_file", shared=0, new=int(a.get("valid_rows", 0)), with_files=[])
    mine = set(I.station_keys(tmp_path).timestamp.astype("int64"))
    seen, per = set(), []
    for o in others:
        ts = set(I.station_keys(D.original_path(o["sha256"])).timestamp.astype("int64"))
        sh = len(mine & ts); seen |= ts
        per.append(dict(file_name=o["file_name"], shared_timestamps=sh))
    shared = len(mine & seen)
    return dict(kind="overlaps_existing" if shared else "extends_existing", shared=shared, new=len(mine - seen), with_files=per,
                note="Overlapping timestamps are de-duplicated when a dataset version is built (first-uploaded record kept; conflicting values counted).")


def apply_decision(con, file_id: int, decision: dict, user) -> dict:
    row = con.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if not row: raise LookupError("file not found")
    dec = json.loads(row["decisions_json"] or "{}")
    kind = decision.get("action")
    a_old = json.loads(row["audit_json"])
    if kind == "reject":
        status = "rejected"; reasons = (row["reasons"] or "") + " | Rejected by administrator."
    else:
        if kind == "approve_blank_unit":
            f = decision.get("feature")
            prop = next((p for p in a_old.get("proposals", []) if p["feature"] == f), None)
            if not prop: raise ValueError("No blank-unit proposal exists for that feature.")
            dec.setdefault("blank_unit", {})[f] = prop["raw"]
        elif kind == "approve_structural_absence":
            dec["structural_absence"] = list(a_old.get("structural_absence", []))
        elif kind == "reopen":
            dec = {}
        else:
            raise ValueError("unknown action")
        a = I.audit_file(D.original_path(row["sha256"]), display_name=row["file_name"], info=I.load_stations_info(), decisions=dec)
        status, reasons = a["verdict"], " | ".join(a["reasons"]); a_old = a
    with tx(con):
        con.execute("UPDATE files SET status=?, reasons=?, decisions_json=?, audit_json=? WHERE id=?",
                    (status, reasons, json.dumps(dec), json.dumps(a_old, default=str), file_id))
        audit("file_decision", row["file_name"], dict(decision=decision, new_status=status), user, con)
    return dict(id=file_id, status=status)


def accepted_entries(con) -> list[dict]:
    rows = con.execute("SELECT file_name,sha256,station,decisions_json FROM files WHERE status IN ('accepted','accepted_recovered') ORDER BY id").fetchall()
    return [dict(file_name=r["file_name"], sha256=r["sha256"], station=r["station"], decisions=json.loads(r["decisions_json"] or "{}")) for r in rows]


def signature(entries: list[dict]) -> str:
    h = hashlib.sha256()
    for e in entries: h.update(f"{e['sha256']}|{json.dumps(e['decisions'], sort_keys=True)}\n".encode())
    return h.hexdigest()


def get_setting(con, key, default=None):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(con, key, value):
    con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def next_id(prefix: str, root: Path, con=None, table=None) -> str:
    n = 0
    for p in Path(root).glob(f"{prefix}-*"):
        m = re.match(rf"^{prefix}-(\d+)", p.name)
        if m: n = max(n, int(m.group(1)))
    if con and table:
        for r in con.execute(f"SELECT id FROM {table}"):
            m = re.match(rf"^{prefix}-(\d+)", r["id"])
            if m: n = max(n, int(m.group(1)))
    return f"{prefix}-{n + 1:04d}"


# =============================== model registry ====================================
def get_active(con):
    return con.execute("SELECT * FROM models WHERE status='active'").fetchone()


def _event(con, model_id, action, user, detail=None):
    con.execute("INSERT INTO model_events(ts,model_id,action,user_email,detail) VALUES(?,?,?,?,?)",
                (iso(), model_id, action, user["email"] if user else None, json.dumps(detail, default=str) if detail else None))


def _scores_on(model_id: str, dataset_version: str, benchmark_id: str) -> dict:
    """Score a stored model on a frozen benchmark's test sets (0% added missingness)."""
    mdir = C.MODELS / model_id
    man = json.loads((mdir / "manifest.json").read_text())
    if man["benchmark_id"] == benchmark_id:
        t = json.loads((mdir / "metrics.json").read_text()).get("test", {})
        if t: return {k: dict(rmse=v["rmse"], mae=v["mae"]) for k, v in t.items()}
    rec = D.load_records(C.DATASETS / dataset_version); lab = B.assign(rec, B.load(C.BENCHMARKS / benchmark_id))
    gw = EdgeGateway.load(mdir); out = {}
    for name, code in (("test_temporal", B.TEST_T), ("test_spatial", B.TEST_S)):
        m = lab == code
        if m.any():
            p = gw.predict_array(rec["X"][m].astype(np.float64)); out[name] = M.regression(rec["y"][m], p)
    return out


def promotion_checks(con, model_id: str) -> dict:
    """Every check must pass before a candidate can become active."""
    m = con.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
    if not m: raise LookupError("model not found")
    checks = []
    def add(key, ok, detail): checks.append(dict(key=key, ok=bool(ok), detail=detail))
    add("status_is_candidate_or_archived", m["status"] in ("candidate", "archived"), f"status is '{m['status']}'")
    v = T.verify_model(C.MODELS / model_id)
    add("artifact_integrity", v["ok"], "checksum, reload, schema, medians and finite predictions verified" if v["ok"] else (v.get("error") or json.dumps(v["checks"])))
    metrics = json.loads(m["metrics_json"] or "{}")
    test = metrics.get("test", {})
    base_ok = bool(test) and all(t["rmse"] < t["baseline_rmse"] for t in test.values())
    add("beats_median_baseline", base_ok, "; ".join(f"{k}: RMSE {t['rmse']:.2f} vs baseline {t['baseline_rmse']:.2f}" for k, t in test.items()) or "no test metrics")
    sel = next((c for c in metrics.get("candidates", []) if c["name"] == metrics.get("selected")), None)
    add("latency_reported", bool(sel and sel.get("latency_ms") is not None), f"single-record latency {sel['latency_ms']:.2f} ms" if sel else "missing")
    act = get_active(con)
    if act and act["id"] != model_id:
        try:
            a = _scores_on(act["id"], m["dataset_version"], m["benchmark_id"])
            c = {k: dict(rmse=v["rmse"], mae=v["mae"]) for k, v in test.items()}
            worse = [k for k in c if k in a and c[k]["rmse"] > a[k]["rmse"] + 1e-9]
            note = "; ".join(f"{k}: candidate {c[k]['rmse']:.3f} vs active {a[k]['rmse']:.3f}" for k in c if k in a)
            if act["benchmark_id"] != m["benchmark_id"]:
                note += f" (active model re-scored on benchmark {m['benchmark_id']}; benchmarks differ, so overlap with its training data is possible)"
            add("non_regression_vs_active", not worse, note)
        except Exception as e:
            add("non_regression_vs_active", False, f"could not compare: {type(e).__name__}: {e}")
    else:
        add("non_regression_vs_active", True, "no active model to compare against")
    return dict(model_id=model_id, ok=all(c["ok"] for c in checks), checks=checks)


def promote(con, model_id: str, user, confirm: str) -> dict:
    if confirm != model_id:
        raise ValueError("Type the model id to confirm promotion.")
    res = promotion_checks(con, model_id)
    if not res["ok"]:
        audit("model_promotion_blocked", model_id, res, user, con)
        return dict(promoted=False, **res)
    with tx(con):
        old = get_active(con)
        if old:
            con.execute("UPDATE models SET status='archived', status_changed_utc=? WHERE id=?", (iso(), old["id"]))
            _event(con, old["id"], "archived_on_promotion", user, dict(replaced_by=model_id))
        con.execute("UPDATE models SET status='active', status_changed_utc=? WHERE id=?", (iso(), model_id))
        _event(con, model_id, "promoted", user, dict(previous=old["id"] if old else None))
        audit("model_promoted", model_id, dict(previous=old["id"] if old else None), user, con)
    invalidate_gateway()
    return dict(promoted=True, **res)


def set_model_status(con, model_id: str, status: str, user, note: str = "") -> None:
    m = con.execute("SELECT status FROM models WHERE id=?", (model_id,)).fetchone()
    if not m: raise LookupError("model not found")
    if m["status"] == "active": raise ValueError("The active model cannot be rejected or archived; promote or roll back to another model first.")
    if status not in ("rejected", "archived"): raise ValueError("bad status")
    with tx(con):
        con.execute("UPDATE models SET status=?, note=?, status_changed_utc=? WHERE id=?", (status, note[:300], iso(), model_id))
        _event(con, model_id, status, user, dict(note=note)); audit(f"model_{status}", model_id, dict(note=note), user, con)


def rollback(con, to_model: str, user, confirm: str) -> dict:
    """Re-activate a previously archived model. The model being replaced is archived (kept), never deleted."""
    if confirm != to_model: raise ValueError("Type the model id to confirm rollback.")
    m = con.execute("SELECT * FROM models WHERE id=?", (to_model,)).fetchone()
    if not m or m["status"] != "archived": raise ValueError("Only an archived model can be restored by rollback.")
    v = T.verify_model(C.MODELS / to_model)
    if not v["ok"]: raise ValueError("Rollback target failed integrity checks: " + (v.get("error") or json.dumps(v["checks"])))
    with tx(con):
        old = get_active(con)
        if old: con.execute("UPDATE models SET status='archived', status_changed_utc=? WHERE id=?", (iso(), old["id"])); _event(con, old["id"], "archived_on_rollback", user)
        con.execute("UPDATE models SET status='active', status_changed_utc=? WHERE id=?", (iso(), to_model))
        _event(con, to_model, "rolled_back_to", user, dict(replaced=old["id"] if old else None))
        audit("model_rollback", to_model, dict(replaced=old["id"] if old else None), user, con)
    invalidate_gateway()
    return dict(active=to_model)


# ---- active gateway cache ------------------------------------------------------
_GW = {}


def invalidate_gateway(): _GW.clear()


def active_gateway(con):
    a = get_active(con)
    if not a: return None, None
    key = (a["id"], a["model_sha256"])
    if key not in _GW:
        _GW.clear(); _GW[key] = EdgeGateway.load(C.MODELS / a["id"])
    return a, _GW[key]
