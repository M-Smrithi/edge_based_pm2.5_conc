#!/usr/bin/env python3
"""Command line for the platform.  python manage.py --help"""
from __future__ import annotations
import argparse, getpass, json, os, sys, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core.config as C


def _con():
    if os.environ.get("AIOT_HOME"): C.set_home(os.environ["AIOT_HOME"])
    C.ensure_dirs()
    from app import db
    con = db.connect(); db.migrate(con); return con


def cmd_init(a):
    con = _con(); print("database ready at", C.DB_PATH)


def cmd_create_admin(a):
    from app import security as SE
    con = _con()
    pw = os.environ.get(a.password_env) if a.password_env else None
    if not pw:
        pw = getpass.getpass("Password: "); 
        if pw != getpass.getpass("Repeat: "): sys.exit("Passwords differ.")
    try:
        con.execute("INSERT INTO users(email,name,password_hash,role,created_utc) VALUES(?,?,?,?,?)", (a.email.lower(), a.name, SE.hash_password(pw), a.role, SE.iso())) if not SE.password_problems(pw, a.email) and SE.EMAIL_RE.match(a.email) else sys.exit("Invalid email or weak password: " + ", ".join(SE.password_problems(pw, a.email)))
    except Exception as e:
        sys.exit(f"Could not create user: {e}")
    SE.audit("user_created_cli", a.email.lower(), dict(role=a.role), con=con); print("created", a.role, a.email)


def cmd_audit(a):
    from core import audit_files
    d = audit_files.run_audit(Path(a.src), C.AUDITS); print(json.dumps(d["summary"], indent=1, default=str)); print("reports in", C.AUDITS)


def cmd_ingest(a):
    from app import services as SV
    con = _con(); src = Path(a.src); files = sorted(p for p in src.iterdir() if p.is_file())
    bid = con.execute("INSERT INTO batches(created_utc,user_id,n_files,note) VALUES(datetime('now'),NULL,?,?)", (len(files), f"CLI ingest of {src}")).lastrowid
    tally = {}
    for i, p in enumerate(files, 1):
        with open(p, "rb") as fh: r = SV.intake_file(con, fh, p.name, None, bid)
        tally[r["status"]] = tally.get(r["status"], 0) + 1
        if i % 25 == 0 or i == len(files): print(f"  {i}/{len(files)}", tally, flush=True)
    print("done:", tally)


def _wait(con, jid):
    last = None
    while True:
        r = con.execute("SELECT status,progress,message,error FROM jobs WHERE id=?", (jid,)).fetchone()
        line = f"[{r['status']}] {r['progress']*100:5.1f}% {r['message'] or ''}"
        if line != last: print(line, flush=True); last = line
        if r["status"] in ("succeeded", "failed", "cancelled"):
            if r["status"] == "failed": sys.exit("job failed: " + (r["error"] or ""))
            return r
        time.sleep(3)


def cmd_retrain(a):
    from app import jobs
    con = _con()
    params = dict(run_experiment=not a.no_experiment, force=a.force, new_benchmark=a.new_benchmark, note=a.note or "")
    if a.trials: params["trials"] = a.trials
    jid = jobs.enqueue(con, "retrain", params, None); print("job", jid, "queued"); _wait(con, jid)
    print(json.dumps(json.loads(con.execute("SELECT result FROM jobs WHERE id=?", (jid,)).fetchone()[0]), indent=1))


def cmd_promote(a):
    from app import services as SV
    con = _con(); res = SV.promote(con, a.model_id, None, a.model_id); print(json.dumps(res, indent=1))
    sys.exit(0 if res["promoted"] else 1)


def cmd_verify(a):
    from core import datasets as D, train as T
    ok = True
    for d in sorted(C.DATASETS.glob("ds-*")):
        if d.name.endswith((".building",)): continue
        good = D.verify_version(d); ok &= good; print("dataset", d.name, "OK" if good else "CHECKSUM MISMATCH")
    for m in sorted(C.MODELS.glob("model-*")):
        if m.name.endswith((".building", ".failed")): continue
        v = T.verify_model(m); ok &= v["ok"]; print("model", m.name, "OK" if v["ok"] else v)
    sys.exit(0 if ok else 1)


def cmd_restore(a):
    from core import datasets as D, ingest as I
    con = _con(); wanted = {r["sha256"]: r["file_name"] for r in con.execute("SELECT sha256,file_name FROM files")}
    have = 0
    for p in Path(a.src).glob("*.csv"):
        sha = I.sha256_file(p)
        if sha in wanted: D.store_original(p); have += 1
    missing = [n for s, n in wanted.items() if not D.original_path(s).exists()]
    print(f"restored {have} originals; still missing {len(missing)}", missing[:10])


def cmd_serve(a):
    from app import create_app
    app = create_app(); print(f"Serving on http://{a.host}:{a.port}  (Ctrl+C to stop)")
    app.run(host=a.host, port=a.port, debug=False, threaded=True)


def cmd_test(a):
    suite = unittest.defaultTestLoader.discover(str(C.ROOT / "tests"), top_level_dir=str(C.ROOT))
    r = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if r.wasSuccessful() else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init").set_defaults(f=cmd_init)
    p = sp.add_parser("create-admin"); p.add_argument("--email", required=True); p.add_argument("--name", default="")
    p.add_argument("--role", default="admin", choices=["admin", "analyst"]); p.add_argument("--password-env", help="read the password from this environment variable instead of prompting"); p.set_defaults(f=cmd_create_admin)
    p = sp.add_parser("audit"); p.add_argument("src"); p.set_defaults(f=cmd_audit)
    p = sp.add_parser("ingest"); p.add_argument("src"); p.set_defaults(f=cmd_ingest)
    p = sp.add_parser("retrain"); p.add_argument("--trials", type=int); p.add_argument("--no-experiment", action="store_true"); p.add_argument("--force", action="store_true")
    p.add_argument("--new-benchmark", action="store_true"); p.add_argument("--note"); p.set_defaults(f=cmd_retrain)
    p = sp.add_parser("promote"); p.add_argument("model_id"); p.set_defaults(f=cmd_promote)
    sp.add_parser("verify").set_defaults(f=cmd_verify)
    p = sp.add_parser("restore-originals"); p.add_argument("src"); p.set_defaults(f=cmd_restore)
    p = sp.add_parser("serve"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=5055); p.set_defaults(f=cmd_serve)
    sp.add_parser("test").set_defaults(f=cmd_test)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
