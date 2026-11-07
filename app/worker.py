"""Job worker process:  python -m app.worker <job_id>.  Runs one job, records progress/result in the DB, then
dispatches the next queued job. A failed job never changes the active model."""
from __future__ import annotations
import json, sys, traceback
from pathlib import Path

import numpy as np

import core.config as C
from app import jobs, services as SV
from app.db import connect, migrate, tx
from app.security import audit, iso
from core import benchmark as B, datasets as D, experiments as E, train as T


class Ctx:
    def __init__(self, con, jid): self.con, self.jid = con, jid
    def progress(self, frac, msg=""):
        self.con.execute("UPDATE jobs SET progress=?, message=? WHERE id=? AND status='running'", (round(float(frac), 4), str(msg)[:200], self.jid))
    def sub(self, lo, hi):
        return lambda f, m="": self.progress(lo + (hi - lo) * f, m)


def step_build(ctx, p, lo=0.0, hi=1.0, user=None):
    con = ctx.con
    entries = SV.accepted_entries(con)
    if not entries: raise RuntimeError("No accepted files to build a dataset from.")
    sig = SV.signature(entries)
    last = con.execute("SELECT id FROM dataset_versions ORDER BY created_utc DESC, id DESC LIMIT 1").fetchone()
    if last and not p.get("force"):
        lm = json.loads((C.DATASETS / last["id"] / "manifest.json").read_text())
        if lm.get("signature") == sig:
            print(f"accepted files unchanged since {last['id']}; reusing it", flush=True)
            return last["id"]
    ds = SV.next_id("ds", C.DATASETS, con, "dataset_versions")
    print(f"building {ds} from {len(entries)} accepted files", flush=True)
    man = D.build_version(entries, C.DATASETS / ds, meta=dict(signature=sig, note=p.get("note", "")), progress=ctx.sub(lo, hi * 0.9))
    with tx(con):
        con.execute("INSERT INTO dataset_versions(id,created_utc,created_by,rows,n_files,n_stations,records_sha256,note,job_id) VALUES(?,?,?,?,?,?,?,?,?)",
                    (ds, man["created_utc"], ctx.user_id, man["rows"], man["n_files"], man["n_stations"], man["records_sha256"], p.get("note", ""), ctx.jid))
        audit("dataset_version_created", ds, dict(rows=man["rows"], files=man["n_files"], duplicates=man["duplicates"]), ctx.user, con)
    active_b = con.execute("SELECT id FROM benchmarks WHERE active=1").fetchone()
    if p.get("new_benchmark") or not active_b:
        bid = SV.next_id("bench", C.BENCHMARKS, con, "benchmarks").replace("bench-000", "bench-v").replace("bench-00", "bench-v").replace("bench-0", "bench-v")
        rec = D.load_records(C.DATASETS / ds)
        b = B.create(rec, bid, C.BENCHMARKS / bid)
        with tx(con):
            con.execute("UPDATE benchmarks SET active=0")
            con.execute("INSERT INTO benchmarks(id,created_utc,dataset_version,sha256,active,created_by) VALUES(?,?,?,?,1,?)", (bid, b["created_utc"], ds, b["benchmark_sha256"], ctx.user_id))
            audit("benchmark_created", bid, dict(dataset=ds, test_temporal=b["n_test_temporal"], test_spatial=b["n_test_spatial"]), ctx.user, con)
    ctx.progress(hi, f"dataset {ds} ready")
    return ds


def step_train(ctx, p, ds, lo=0.0, hi=1.0):
    con = ctx.con
    bid = p.get("benchmark_id") or (con.execute("SELECT id FROM benchmarks WHERE active=1").fetchone() or {"id": None})["id"]
    if not bid: raise RuntimeError("No benchmark exists. Build a dataset version first.")
    mid = SV.next_id("model", C.MODELS, con, "models")
    params = {k: p[k] for k in ("n_estimators", "max_samples", "seed") if p.get(k) is not None}
    out = T.train(C.DATASETS / ds, C.BENCHMARKS / bid, C.MODELS / mid, params, progress=ctx.sub(lo, hi))
    man, met = out["manifest"], out["metrics"]
    with tx(con):
        con.execute("INSERT INTO models(id,created_utc,dataset_version,benchmark_id,selected,model_sha256,status,metrics_json,job_id,status_changed_utc) VALUES(?,?,?,?,?,?,'candidate',?,?,?)",
                    (mid, man["created_utc"], ds, bid, man["selected"], man["model_sha256"], json.dumps(met), ctx.jid, iso()))
        SV._event(con, mid, "created", ctx.user, dict(job=ctx.jid))
        audit("model_trained", mid, dict(dataset=ds, benchmark=bid, selected=man["selected"]), ctx.user, con)
    return mid


def step_experiment(ctx, p, model_id, lo=0.0, hi=1.0, reproduces=None):
    con = ctx.con
    m = con.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
    if not m: raise RuntimeError("model not found")
    trials = int(p.get("trials") or SV.get_setting(con, "default_trials", C.DEFAULT_TRIALS))
    eid = SV.next_id("exp", C.EXPERIMENTS, con, "experiments")
    seed = int(p.get("seed") or C.EXPERIMENT_SEED)
    meta = E.run(C.MODELS / model_id, C.DATASETS / m["dataset_version"], C.BENCHMARKS / m["benchmark_id"], C.EXPERIMENTS / eid,
                 trials=trials, seed=seed, progress=ctx.sub(lo, hi))
    try:
        from core import reporting
        reporting.make_figures(C.EXPERIMENTS / eid, C.MODELS / model_id)
    except Exception as e:
        print("figure generation failed:", e, flush=True)
    repro = None
    if reproduces:
        a = json.loads((C.EXPERIMENTS / reproduces / "results.json").read_text())["rows"]
        b = json.loads((C.EXPERIMENTS / eid / "results.json").read_text())["rows"]
        diffs = [max(abs(x["mae"] - y["mae"]), abs(x["rmse"] - y["rmse"])) for x, y in zip(a, b) if (x["test_set"], x["missing_rate"], x["pattern"], x["trial"]) == (y["test_set"], y["missing_rate"], y["pattern"], y["trial"])]
        repro = dict(compared_rows=len(diffs), original_rows=len(a), max_abs_difference=float(max(diffs)) if diffs else None,
                     identical=bool(diffs) and len(diffs) == len(a) and max(diffs) < 1e-9)
    with tx(con):
        con.execute("INSERT INTO experiments(id,created_utc,model_id,benchmark_id,dataset_version,trials,seed,job_id,reproduces,reproduction_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (eid, meta["created_utc"], model_id, m["benchmark_id"], m["dataset_version"], trials, seed, ctx.jid, reproduces, json.dumps(repro) if repro else None))
        audit("experiment_completed", eid, dict(model=model_id, trials=trials, reproduces=reproduces, reproduction=repro), ctx.user, con)
    return eid


def run(jid: int):
    con = connect(); migrate(con)
    row = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    p = json.loads(row["params"]); user = con.execute("SELECT id,email FROM users WHERE id=?", (row["user_id"],)).fetchone()
    ctx = Ctx(con, jid); ctx.user = dict(user) if user else None; ctx.user_id = row["user_id"]
    try:
        k = row["kind"]
        if k == "build_dataset":
            result = dict(dataset_version=step_build(ctx, p))
        elif k == "train":
            ds = p.get("dataset_version") or con.execute("SELECT id FROM dataset_versions ORDER BY created_utc DESC, id DESC LIMIT 1").fetchone()["id"]
            result = dict(model_id=step_train(ctx, p, ds), dataset_version=ds)
        elif k == "experiment":
            result = dict(experiment_id=step_experiment(ctx, p, p["model_id"]))
        elif k == "reproduce_experiment":
            o = con.execute("SELECT * FROM experiments WHERE id=?", (p["experiment_id"],)).fetchone()
            result = dict(experiment_id=step_experiment(ctx, dict(trials=o["trials"], seed=o["seed"]), o["model_id"], reproduces=o["id"]))
        elif k == "retrain":
            ds = step_build(ctx, p, 0.0, 0.2)
            mid = step_train(ctx, p, ds, 0.2, 0.8)
            result = dict(dataset_version=ds, model_id=mid)
            if p.get("run_experiment", True):
                result["experiment_id"] = step_experiment(ctx, p, mid, 0.8, 1.0)
        else:
            raise RuntimeError("unknown job kind")
        cur = con.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()["status"]
        if cur == "running":
            con.execute("UPDATE jobs SET status='succeeded', progress=1, message='done', result=?, finished_utc=? WHERE id=?", (json.dumps(result), iso(), jid))
        print("job finished:", result, flush=True)
    except BaseException as e:
        traceback.print_exc()
        con.execute("UPDATE jobs SET status='failed', error=?, finished_utc=? WHERE id=? AND status='running'", (f"{type(e).__name__}: {e}"[:500], iso(), jid))
        audit("job_failed", f"job-{jid}", dict(error=str(e)[:300]), ctx.user, con)
    finally:
        try: jobs.dispatch(con)
        finally: con.close()


if __name__ == "__main__":
    run(int(sys.argv[1]))
