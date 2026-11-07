"""Background jobs: DB-tracked subprocess workers, one heavy job at a time, queue, cancel, stale detection."""
from __future__ import annotations
import json, os, signal, subprocess, sys
from pathlib import Path

import core.config as C
from app.db import tx
from app.security import audit, iso

KINDS = {"build_dataset", "train", "experiment", "retrain", "reproduce_experiment"}


def enqueue(con, kind: str, params: dict, user) -> int:
    if kind not in KINDS: raise ValueError("unknown job kind")
    with tx(con):
        cur = con.execute("INSERT INTO jobs(kind,status,params,created_utc,user_id) VALUES(?,?,?,?,?)",
                          (kind, "queued", json.dumps(params), iso(), user["id"] if user else None))
        jid = cur.lastrowid
        audit("job_enqueued", f"job-{jid}", dict(kind=kind, params=params), user, con)
    dispatch(con)
    return jid


def _alive(pid) -> bool:
    if not pid: return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return True
    stat_file = Path(f"/proc/{pid}/stat")
    if stat_file.exists():
        try:
            with open(stat_file) as f:
                return f.read().split(")")[-1].split()[0] != "Z"
        except (OSError, IOError):
            return False
    return True


def reap_stale(con):
    for r in con.execute("SELECT id,pid FROM jobs WHERE status='running'").fetchall():
        if not _alive(r["pid"]):
            con.execute("UPDATE jobs SET status='failed', error='worker process ended unexpectedly', finished_utc=? WHERE id=? AND status='running'", (iso(), r["id"]))


def dispatch(con):
    """Start the next queued job if capacity allows. Called after enqueue and by each worker on exit."""
    reap_stale(con)
    running = con.execute("SELECT COUNT(*) c FROM jobs WHERE status='running'").fetchone()["c"]
    if running >= C.MAX_CONCURRENT_JOBS: return None
    row = con.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if not row: return None
    C.JOBLOGS.mkdir(parents=True, exist_ok=True)
    log = C.JOBLOGS / f"job-{row['id']}.log"
    with tx(con):
        ok = con.execute("UPDATE jobs SET status='running', started_utc=?, log_path=?, message='starting' WHERE id=? AND status='queued'", (iso(), str(log), row["id"])).rowcount
    if not ok: return None
    env = dict(os.environ, AIOT_HOME=str(C.HOME), AIOT_DB=str(C.DB_PATH), PYTHONPATH=str(C.ROOT))
    with open(log, "ab") as lf:
        p = subprocess.Popen([sys.executable, "-m", "app.worker", str(row["id"])], cwd=str(C.ROOT), env=env,
                             stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    con.execute("UPDATE jobs SET pid=? WHERE id=?", (p.pid, row["id"]))
    return row["id"]


def cancel(con, job_id: int, user) -> str:
    r = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r: raise LookupError("job not found")
    if r["status"] == "queued":
        con.execute("UPDATE jobs SET status='cancelled', finished_utc=? WHERE id=?", (iso(), job_id))
    elif r["status"] == "running":
        try: os.killpg(os.getpgid(r["pid"]), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError): pass
        con.execute("UPDATE jobs SET status='cancelled', finished_utc=?, message='cancelled by administrator' WHERE id=?", (iso(), job_id))
    else:
        raise ValueError(f"job already {r['status']}")
    audit("job_cancelled", f"job-{job_id}", None, user, con)
    dispatch(con)
    return "cancelled"


def tail(path, n=200) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 60_000))
            return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-n:])
    except (FileNotFoundError, TypeError):
        return ""
