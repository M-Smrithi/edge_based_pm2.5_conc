"""Authenticated admin API. Every route requires a session; mutating routes require the admin role (backend-enforced)."""
from __future__ import annotations
import csv, io, json, shutil
from pathlib import Path

from flask import Blueprint, Response, abort, g, jsonify, request, session

import core.config as C
from app import jobs, security as SE, services as SV
from app.db import get_db, tx
from app.security import admin_area, audit, iso

bp = Blueprint("admin_api", __name__, url_prefix="/api")


def _page():
    try: page = max(1, int(request.args.get("page", 1))); size = min(200, max(1, int(request.args.get("size", 25))))
    except ValueError: abort(400, description="bad paging")
    return page, size, (page - 1) * size


def _rows(cur): return [dict(r) for r in cur]


# =============================== auth ===============================
@bp.post("/auth/login")
def login():
    b = request.get_json(silent=True) or {}
    u, msg = SE.login(str(b.get("email", "")), str(b.get("password", "")))
    if not u: return jsonify(error=msg), 401
    return jsonify(user=dict(email=u["email"], name=u["name"], role=u["role"]), csrf=SE.csrf_token())


@bp.post("/auth/logout")
def logout():
    if g.user: audit("logout", g.user["email"])
    session.clear(); return jsonify(ok=True)


@bp.get("/auth/me")
def me():
    return jsonify(user=None if not g.user else dict(email=g.user["email"], name=g.user["name"], role=g.user["role"]), csrf=SE.csrf_token())


@bp.post("/auth/password")
@admin_area(write_role="analyst")
def change_password():
    b = request.get_json(silent=True) or {}
    from werkzeug.security import check_password_hash
    if not check_password_hash(g.user["password_hash"], str(b.get("current", ""))): return jsonify(error="Current password is incorrect."), 400
    p = SE.password_problems(str(b.get("new", "")), g.user["email"])
    if p: return jsonify(error="Password needs: " + ", ".join(p)), 400
    get_db().execute("UPDATE users SET password_hash=? WHERE id=?", (SE.hash_password(b["new"]), g.user["id"]))
    audit("password_changed", g.user["email"]); return jsonify(ok=True)


# =============================== overview ===============================
@bp.get("/admin/overview")
@admin_area
def overview():
    con = get_db(); one = lambda q, *a: con.execute(q, a).fetchone()[0]
    act = SV.get_active(con); last_ds = one("SELECT id FROM dataset_versions ORDER BY created_utc DESC, id DESC LIMIT 1") if one("SELECT COUNT(*) FROM dataset_versions") else None
    entries = SV.accepted_entries(con); sig = SV.signature(entries) if entries else None
    stale = None
    if last_ds and sig:
        try: stale = json.loads((C.DATASETS / last_ds / "manifest.json").read_text()).get("signature") != sig
        except OSError: stale = None
    du = sum(f.stat().st_size for f in C.STORAGE.rglob("*") if f.is_file()) if C.STORAGE.exists() else 0
    return jsonify(
        files={s: one("SELECT COUNT(*) FROM files WHERE status=?", s) for s in ("accepted", "accepted_recovered", "pending_review", "rejected")},
        datasets=one("SELECT COUNT(*) FROM dataset_versions"), latest_dataset=last_ds, new_files_since_latest=bool(stale) if stale is not None else bool(entries and not last_ds),
        models={s: one("SELECT COUNT(*) FROM models WHERE status=?", s) for s in ("candidate", "active", "rejected", "archived")},
        active_model=dict(act) if act else None, experiments=one("SELECT COUNT(*) FROM experiments"),
        jobs_running=one("SELECT COUNT(*) FROM jobs WHERE status='running'"), jobs_queued=one("SELECT COUNT(*) FROM jobs WHERE status='queued'"),
        jobs_failed_recent=one("SELECT COUNT(*) FROM jobs WHERE status='failed' AND created_utc > datetime('now','-7 day')"),
        recent_jobs=_rows(con.execute("SELECT id,kind,status,progress,message,created_utc FROM jobs ORDER BY id DESC LIMIT 5")),
        recent_audit=_rows(con.execute("SELECT ts,user_email,action,target FROM audit_log ORDER BY id DESC LIMIT 8")),
        storage_mb=round(du / 1e6, 1), users=one("SELECT COUNT(*) FROM users WHERE active=1"))


# =============================== files / datasets ===============================
@bp.post("/admin/files/upload")
@admin_area
def upload():
    con = get_db(); fl = request.files.getlist("files")
    if not fl: abort(400, description="No files received.")
    batch = request.form.get("batch_id")
    if not batch:
        batch = con.execute("INSERT INTO batches(created_utc,user_id,n_files,note) VALUES(?,?,?,?)", (iso(), g.user["id"], len(fl), request.form.get("note", "")[:200])).lastrowid
    else:
        batch = int(batch)
        con.execute("UPDATE batches SET n_files=n_files+? WHERE id=?", (len(fl), batch))
    res = [SV.intake_file(con, f.stream, f.filename, g.user, batch) for f in fl]
    return jsonify(batch_id=batch, results=res)


@bp.get("/admin/files")
@admin_area
def files():
    con = get_db(); page, size, off = _page(); w, a = [], []
    if s := request.args.get("status"): w.append("status=?"); a.append(s)
    if q := request.args.get("q"): w.append("(file_name LIKE ? OR station LIKE ?)"); a += [f"%{q}%"] * 2
    if b := request.args.get("batch"): w.append("batch_id=?"); a.append(int(b))
    W = ("WHERE " + " AND ".join(w)) if w else ""
    sort = {"name": "file_name", "date": "id DESC", "status": "status", "size": "size_bytes DESC"}.get(request.args.get("sort", "date"), "id DESC")
    total = con.execute(f"SELECT COUNT(*) FROM files {W}", a).fetchone()[0]
    rows = _rows(con.execute(f"SELECT id,file_name,station,status,size_bytes,reasons,uploaded_utc,batch_id,sha256,json_extract(audit_json,'$.rows') rows,json_extract(audit_json,'$.valid_rows') valid_rows,json_extract(audit_json,'$.ts_min') ts_min,json_extract(audit_json,'$.ts_max') ts_max FROM files {W} ORDER BY {sort} LIMIT ? OFFSET ?", a + [size, off]))
    return jsonify(total=total, page=page, size=size, rows=rows)


@bp.get("/admin/files/<int:fid>")
@admin_area
def file_detail(fid):
    r = get_db().execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if not r: abort(404)
    d = dict(r); d["audit"] = json.loads(d.pop("audit_json")); d["decisions"] = json.loads(d.pop("decisions_json") or "{}")
    d["overlap"] = json.loads(d["overlap_json"]) if d["overlap_json"] else None; d.pop("overlap_json")
    d["audit"].pop("feature_resolution", None)
    return jsonify(d)


@bp.post("/admin/files/<int:fid>/decision")
@admin_area
def file_decision(fid):
    try: return jsonify(SV.apply_decision(get_db(), fid, request.get_json(silent=True) or {}, g.user))
    except LookupError: abort(404)
    except ValueError as e: abort(400, description=str(e))


@bp.get("/admin/batches")
@admin_area
def batches():
    con = get_db()
    return jsonify(rows=_rows(con.execute("""SELECT b.id,b.created_utc,b.note,u.email user,
        (SELECT COUNT(*) FROM files f WHERE f.batch_id=b.id) files,
        (SELECT COUNT(*) FROM files f WHERE f.batch_id=b.id AND f.status IN ('accepted','accepted_recovered')) accepted,
        (SELECT COUNT(*) FROM files f WHERE f.batch_id=b.id AND f.status='pending_review') pending,
        (SELECT COUNT(*) FROM files f WHERE f.batch_id=b.id AND f.status='rejected') rejected
        FROM batches b LEFT JOIN users u ON u.id=b.user_id ORDER BY b.id DESC LIMIT 100""")))


@bp.get("/admin/datasets")
@admin_area
def datasets():
    con = get_db()
    return jsonify(rows=_rows(con.execute("SELECT * FROM dataset_versions ORDER BY created_utc DESC, id DESC")),
                   benchmarks=_rows(con.execute("SELECT * FROM benchmarks ORDER BY created_utc DESC, id DESC")),
                   accepted_files=len(SV.accepted_entries(con)))


@bp.get("/admin/datasets/<ds>")
@admin_area
def dataset_detail(ds):
    import re
    if not re.fullmatch(r"ds-\d{4,}", ds): abort(404)
    p = C.DATASETS / ds / "manifest.json"
    if not p.exists(): abort(404)
    m = json.loads(p.read_text()); m["files"] = [{k: f[k] for k in ("file_name", "station", "rows_kept", "duplicates_dropped", "unique_contributed", "structural_absence")} for f in m["files"]]
    return jsonify(m)


# =============================== jobs ===============================
@bp.post("/admin/jobs")
@admin_area
def create_job():
    con = get_db(); b = request.get_json(silent=True) or {}; kind = b.get("kind"); p = b.get("params") or {}
    if kind == "reproduce_experiment" and not con.execute("SELECT 1 FROM experiments WHERE id=?", (p.get("experiment_id"),)).fetchone(): abort(400, description="Unknown experiment.")
    if kind == "experiment" and not con.execute("SELECT 1 FROM models WHERE id=?", (p.get("model_id"),)).fetchone(): abort(400, description="Unknown model.")
    if kind in ("build_dataset", "retrain") and not SV.accepted_entries(con): abort(400, description="There are no accepted files to build from.")
    if kind == "train" and p.get("dataset_version") and not con.execute("SELECT 1 FROM dataset_versions WHERE id=?", (p["dataset_version"],)).fetchone(): abort(400, description="Unknown dataset version.")
    if kind == "train" and not con.execute("SELECT 1 FROM dataset_versions").fetchone(): abort(400, description="Build a dataset version first.")
    clean = {}
    for k, lo, hi in (("trials", 1, 50), ("n_estimators", 5, 300), ("seed", 0, 2**31)):
        if p.get(k) is not None:
            try: clean[k] = int(p[k])
            except (TypeError, ValueError): abort(400, description=f"{k} must be an integer")
            if not lo <= clean[k] <= hi: abort(400, description=f"{k} must be between {lo} and {hi}")
    if p.get("max_samples") is not None:
        try: clean["max_samples"] = float(p["max_samples"])
        except (TypeError, ValueError): abort(400, description="max_samples must be a number")
        if not 0.01 <= clean["max_samples"] <= 1: abort(400, description="max_samples must be 0.01-1")
    for k in ("dataset_version", "benchmark_id", "model_id", "experiment_id", "note"):
        if p.get(k): clean[k] = str(p[k])[:200]
    for k in ("new_benchmark", "force", "run_experiment"):
        if k in p: clean[k] = bool(p[k])
    try: jid = jobs.enqueue(con, kind, clean, g.user)
    except ValueError as e: abort(400, description=str(e))
    return jsonify(job_id=jid), 202


@bp.get("/admin/jobs")
@admin_area
def list_jobs():
    con = get_db(); jobs.reap_stale(con); page, size, off = _page()
    w = "WHERE status=?" if request.args.get("status") else ""; a = [request.args["status"]] if w else []
    total = con.execute(f"SELECT COUNT(*) FROM jobs {w}", a).fetchone()[0]
    return jsonify(total=total, rows=_rows(con.execute(f"SELECT id,kind,status,progress,message,error,created_utc,started_utc,finished_utc,params,result FROM jobs {w} ORDER BY id DESC LIMIT ? OFFSET ?", a + [size, off])))


@bp.get("/admin/jobs/<int:jid>")
@admin_area
def job(jid):
    con = get_db(); jobs.reap_stale(con); r = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    if not r: abort(404)
    d = dict(r); d["log"] = jobs.tail(d.get("log_path")); d.pop("log_path", None); d.pop("pid", None)
    return jsonify(d)


@bp.post("/admin/jobs/<int:jid>/cancel")
@admin_area
def cancel_job(jid):
    try: return jsonify(status=jobs.cancel(get_db(), jid, g.user))
    except LookupError: abort(404)
    except ValueError as e: abort(409, description=str(e))


# =============================== models / experiments ===============================
def _model_row(r):
    d = dict(r); m = json.loads(d.pop("metrics_json") or "{}")
    sel = next((c for c in m.get("candidates", []) if c["name"] == m.get("selected")), None)
    d["test"] = m.get("test"); d["val"] = sel["val"] if sel else None; d["latency_ms"] = sel["latency_ms"] if sel else None; d["size_mb"] = sel["size_mb"] if sel else None
    return d


@bp.get("/admin/models")
@admin_area
def models():
    con = get_db()
    return jsonify(rows=[_model_row(r) for r in con.execute("SELECT * FROM models ORDER BY created_utc DESC, id DESC")],
                   events=_rows(con.execute("SELECT * FROM model_events ORDER BY id DESC LIMIT 60")))


@bp.get("/admin/models/<mid>")
@admin_area
def model_detail(mid):
    r = get_db().execute("SELECT * FROM models WHERE id=?", (mid,)).fetchone()
    if not r: abort(404)
    d = dict(r); d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
    d["manifest"] = json.loads((C.MODELS / mid / "manifest.json").read_text()); d["preprocessing"] = json.loads((C.MODELS / mid / "preprocessing.json").read_text())
    return jsonify(d)


@bp.get("/admin/models/<mid>/checks")
@admin_area
def model_checks(mid):
    try: return jsonify(SV.promotion_checks(get_db(), mid))
    except LookupError: abort(404)


@bp.post("/admin/models/<mid>/promote")
@admin_area
def model_promote(mid):
    try: res = SV.promote(get_db(), mid, g.user, str((request.get_json(silent=True) or {}).get("confirm", "")))
    except LookupError: abort(404)
    except ValueError as e: abort(400, description=str(e))
    return jsonify(res), (200 if res["promoted"] else 409)


@bp.post("/admin/models/<mid>/<action>")
@admin_area
def model_status(mid, action):
    if action not in ("reject", "archive"): abort(404)
    try: SV.set_model_status(get_db(), mid, "rejected" if action == "reject" else "archived", g.user, str((request.get_json(silent=True) or {}).get("note", "")))
    except LookupError: abort(404)
    except ValueError as e: abort(409, description=str(e))
    return jsonify(ok=True)


@bp.post("/admin/models-rollback")
@admin_area
def model_rollback():
    b = request.get_json(silent=True) or {}
    try: return jsonify(SV.rollback(get_db(), str(b.get("to", "")), g.user, str(b.get("confirm", ""))))
    except ValueError as e: abort(400, description=str(e))


@bp.get("/admin/experiments")
@admin_area
def experiments():
    con = get_db()
    return jsonify(rows=_rows(con.execute("SELECT e.*, (SELECT status FROM models m WHERE m.id=e.model_id) model_status FROM experiments e ORDER BY created_utc DESC, id DESC")))


@bp.get("/admin/experiments/<eid>")
@admin_area
def experiment_detail(eid):
    import re
    from core import experiments as E
    if not re.fullmatch(r"exp-\d{4,}", eid): abort(404)
    r = get_db().execute("SELECT * FROM experiments WHERE id=?", (eid,)).fetchone()
    if not r: abort(404)
    res = json.loads((C.EXPERIMENTS / eid / "results.json").read_text())
    d = dict(r); d["meta"] = res["meta"]; d["summary"] = E.summarise(res); d["latency"] = res["latency"]
    d["reproduction"] = json.loads(d.pop("reproduction_json")) if d.get("reproduction_json") else None
    return jsonify(d)


@bp.get("/admin/experiments/<eid>/results.csv")
@admin_area
def experiment_csv(eid):
    import re
    if not re.fullmatch(r"exp-\d{4,}", eid): abort(404)
    p = C.EXPERIMENTS / eid / "results_table.csv"
    if not p.exists(): abort(404)
    return Response(p.read_bytes(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={eid}_results.csv"})


# =============================== audit / settings / users ===============================
@bp.get("/admin/audit")
@admin_area
def audit_list():
    con = get_db(); page, size, off = _page(); w, a = [], []
    if x := request.args.get("action"): w.append("action=?"); a.append(x)
    if x := request.args.get("q"): w.append("(target LIKE ? OR user_email LIKE ? OR detail LIKE ?)"); a += [f"%{x}%"] * 3
    W = ("WHERE " + " AND ".join(w)) if w else ""
    total = con.execute(f"SELECT COUNT(*) FROM audit_log {W}", a).fetchone()[0]
    rows = _rows(con.execute(f"SELECT * FROM audit_log {W} ORDER BY id DESC LIMIT ? OFFSET ?", a + [size, off]))
    actions = [r[0] for r in con.execute("SELECT DISTINCT action FROM audit_log ORDER BY 1")]
    if request.args.get("format") == "csv":
        buf = io.StringIO(); wr = csv.writer(buf); wr.writerow(["ts", "user", "action", "target", "detail", "ip"])
        for r in _rows(con.execute(f"SELECT * FROM audit_log {W} ORDER BY id DESC LIMIT 20000", a)): wr.writerow([r["ts"], r["user_email"], r["action"], r["target"], r["detail"], r["ip"]])
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=audit_log.csv"})
    return jsonify(total=total, page=page, size=size, rows=rows, actions=actions)


@bp.get("/admin/settings")
@admin_area
def settings():
    con = get_db()
    users = _rows(con.execute("SELECT id,email,name,role,active,last_login_utc,created_utc FROM users ORDER BY id"))
    return jsonify(default_trials=SV.get_setting(con, "default_trials", C.DEFAULT_TRIALS), users=users, me=g.user["email"],
                   limits=dict(max_upload_file_mb=C.MAX_UPLOAD_FILE_BYTES // 2**20, max_upload_rows=C.MAX_UPLOAD_ROWS, max_predict_rows=C.MAX_PREDICT_ROWS,
                               min_password_len=C.MIN_PASSWORD_LEN, lockout_minutes=C.LOCKOUT_MINUTES, max_failed_logins=C.MAX_FAILED_LOGINS, session_hours=C.SESSION_HOURS,
                               prediction_ttl_hours=C.PREDICTION_TTL_HOURS))


@bp.put("/admin/settings")
@admin_area
def save_settings():
    con = get_db(); b = request.get_json(silent=True) or {}
    try: t = int(b.get("default_trials"))
    except (TypeError, ValueError): abort(400, description="default_trials must be an integer")
    if not 1 <= t <= 50: abort(400, description="default_trials must be between 1 and 50")
    SV.set_setting(con, "default_trials", t); audit("settings_changed", "default_trials", dict(value=t)); return jsonify(ok=True)


@bp.post("/admin/users")
@admin_area
def add_user():
    b = request.get_json(silent=True) or {}
    try: uid = SE.create_user(str(b.get("email", "")), str(b.get("password", "")), str(b.get("role", "analyst")), str(b.get("name", "")))
    except ValueError as e: abort(400, description=str(e))
    except Exception as e:
        if "UNIQUE" in str(e): abort(409, description="A user with that email already exists.")
        raise
    audit("user_created", b.get("email"), dict(role=b.get("role"))); return jsonify(id=uid), 201


@bp.post("/admin/users/<int:uid>/active")
@admin_area
def user_active(uid):
    b = request.get_json(silent=True) or {}; con = get_db(); on = 1 if b.get("active") else 0
    if uid == g.user["id"] and not on: abort(400, description="You cannot deactivate your own account.")
    if not on and con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0] == 0 and con.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()["role"] == "admin":
        abort(400, description="At least one active administrator is required.")
    con.execute("UPDATE users SET active=? WHERE id=?", (on, uid)); audit("user_active_changed", str(uid), dict(active=bool(on))); return jsonify(ok=True)
