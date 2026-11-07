import io, json, os, re, subprocess, time, unittest
from pathlib import Path
import numpy as np
from tests import helpers as H
import core.config as C

PW = "Sturdy-Pass-9876"


class Base(H.TmpHome):
    @classmethod
    def setUpClass(cls):
        cls.t = H.TmpHome(); cls.t.setUpHome(); cls.home = cls.t.home
        os.environ["AIOT_HOLDOUT_FRAC"] = "0.3"; C.HOLDOUT_STATION_FRAC = 0.3
        from app import create_app, security
        cls.app = create_app({"AIOT_HOME": str(cls.home), "TESTING": False})
        with cls.app.app_context():
            security.create_user("boss@example.org", PW, "admin"); security.create_user("viewer@example.org", PW, "analyst")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("AIOT_HOLDOUT_FRAC", None); C.HOLDOUT_STATION_FRAC = 0.15; cls.t.tearDownHome()

    def client(self, who=None):
        c = self.app.test_client(); tok = c.get("/api/csrf").get_json()["token"]; c.h = {"X-CSRF-Token": tok}
        if who:
            r = c.post("/api/auth/login", json={"email": who, "password": PW}, headers=c.h); assert r.status_code == 200, r.get_json(); c.h = {"X-CSRF-Token": r.get_json()["csrf"]}
        return c

    def upload(self, c, name, df=None, raw=None):
        data = raw if raw is not None else df.to_csv(index=False).encode()
        r = c.post("/api/admin/files/upload", data={"files": (io.BytesIO(data), name)}, headers=c.h, content_type="multipart/form-data")
        return r, (r.get_json() or {}).get("results", [{}])[0]

    def run_job(self, kind, params, user_email="boss@example.org"):
        from app.db import connect
        from app import worker
        con = connect(); uid = con.execute("SELECT id FROM users WHERE email=?", (user_email,)).fetchone()[0]
        jid = con.execute("INSERT INTO jobs(kind,status,params,created_utc,user_id) VALUES(?,?,?,datetime('now'),?)", (kind, "running", json.dumps(params), uid)).lastrowid
        con.close(); worker.run(jid)
        con = connect(); row = dict(con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()); con.close(); return row


class TestAccessControl(Base, unittest.TestCase):
    def test_all_admin_routes_require_authentication(self):
        c = self.app.test_client(); n = 0
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith("/api/admin") or rule.rule == "/api/auth/password":
                n += 1; path = re.sub(r"<[^>]+>", "1", rule.rule)
                for m in rule.methods - {"HEAD", "OPTIONS"}:
                    r = c.open(path, method=m, json={}) if m != "GET" else c.get(path)
                    self.assertIn(r.status_code, (401, 403), f"{m} {rule.rule} -> {r.status_code}")
        self.assertGreater(n, 25)

    def test_admin_pages_redirect_to_login(self):
        c = self.app.test_client()
        for p in ("/admin", "/admin/datasets", "/admin/models", "/admin/audit", "/admin/settings", "/admin/training", "/admin/experiments"):
            r = c.get(p); self.assertEqual(r.status_code, 302, p); self.assertIn("/admin/login", r.headers["Location"])

    def test_no_public_registration(self):
        paths = " ".join(r.rule for r in self.app.url_map.iter_rules()).lower()
        for w in ("register", "signup", "sign-up"): self.assertNotIn(w, paths)
        c = self.client(); self.assertEqual(c.post("/api/admin/users", json={"email": "x@y.org", "password": PW, "role": "admin"}, headers=c.h).status_code, 401)

    def test_csrf_enforced(self):
        c = self.app.test_client()
        self.assertEqual(c.post("/api/auth/login", json={"email": "boss@example.org", "password": PW}).status_code, 403)
        self.assertEqual(c.post("/api/auth/login", json={"email": "boss@example.org", "password": PW}, headers={"X-CSRF-Token": "forged"}).status_code, 403)
        c2 = self.client("boss@example.org"); c2.h = {}
        self.assertEqual(c2.post("/api/admin/jobs", json={"kind": "train"}).status_code, 403)
        self.assertEqual(self.app.test_client().post("/api/public/predict", json={"features": {}}).status_code, 403)

    def test_password_hashed_and_generic_login_errors(self):
        from app.db import connect
        h = connect().execute("SELECT password_hash FROM users WHERE email='boss@example.org'").fetchone()[0]
        self.assertTrue(h.startswith("scrypt:") and PW not in h)
        c = self.client(); a = c.post("/api/auth/login", json={"email": "boss@example.org", "password": "nope"}, headers=c.h).get_json()
        b = c.post("/api/auth/login", json={"email": "ghost@example.org", "password": "nope"}, headers=c.h).get_json(); self.assertEqual(a, b)

    def test_lockout_after_repeated_failures(self):
        from app import security
        with self.app.app_context(): security.create_user("lock@example.org", PW, "analyst")
        c = self.client()
        for _ in range(C.MAX_FAILED_LOGINS): self.assertEqual(c.post("/api/auth/login", json={"email": "lock@example.org", "password": "bad"}, headers=c.h).status_code, 401)
        r = c.post("/api/auth/login", json={"email": "lock@example.org", "password": PW}, headers=c.h)
        self.assertEqual(r.status_code, 401); self.assertIn("Too many", r.get_json()["error"])

    def test_analyst_is_read_only(self):
        c = self.client("viewer@example.org")
        self.assertEqual(c.get("/api/admin/overview").status_code, 200)
        self.assertEqual(c.get("/api/admin/audit").status_code, 200)
        for path, body in [("/api/admin/jobs", {"kind": "retrain"}), ("/api/admin/users", {"email": "q@q.org", "password": PW, "role": "admin"}), ("/api/admin/files/upload", {}), ("/api/admin/models/model-0001/promote", {"confirm": "model-0001"}), ("/api/admin/models-rollback", {})]:
            r = c.post(path, json=body, headers=c.h); self.assertEqual(r.status_code, 403, path)
        self.assertEqual(c.put("/api/admin/settings", json={"default_trials": 3}, headers=c.h).status_code, 403)

    def test_weak_password_and_last_admin_protection(self):
        c = self.client("boss@example.org")
        self.assertEqual(c.post("/api/admin/users", json={"email": "w@w.org", "password": "short1", "role": "analyst"}, headers=c.h).status_code, 400)
        self.assertEqual(c.post("/api/admin/users", json={"email": "boss@example.org", "password": PW, "role": "analyst"}, headers=c.h).status_code, 409)
        uid = c.get("/api/admin/settings").get_json()["users"][0]["id"]
        self.assertEqual(c.post(f"/api/admin/users/{uid}/active", json={"active": False}, headers=c.h).status_code, 400)

    def test_deactivated_user_session_stops_working(self):
        from app import security
        from app.db import connect
        with self.app.app_context(): security.create_user("tmp@example.org", PW, "analyst")
        c = self.client("tmp@example.org"); self.assertEqual(c.get("/api/admin/overview").status_code, 200)
        con = connect(); con.execute("UPDATE users SET active=0 WHERE email='tmp@example.org'"); con.close()
        self.assertEqual(c.get("/api/admin/overview").status_code, 401)

    def test_security_headers_and_cookie(self):
        r = self.app.test_client().get("/")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"]); self.assertEqual(r.headers["X-Frame-Options"], "DENY"); self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("HttpOnly", "; ".join(self.app.test_client().get("/api/csrf").headers.getlist("Set-Cookie")))

    def test_no_hardcoded_credentials_in_source(self):
        bad = []
        for p in list((C.ROOT / "app").rglob("*.py")) + list((C.ROOT / "core").rglob("*.py")) + [C.ROOT / "manage.py"]:
            for i, l in enumerate(p.read_text().splitlines(), 1):
                if re.search(r"(password|secret|token)\s*=\s*[\"'][^\"']{6,}[\"']", l, re.I) and "environ" not in l and "dummy" not in l: bad.append(f"{p.name}:{i}")
        self.assertEqual(bad, [])


class TestFilesAndCumulative(Base, unittest.TestCase):
    def test_upload_flow_duplicates_decisions_and_originals(self):
        from core import ingest as I, datasets as D
        c = self.client("boss@example.org")
        df = H.make_station_csv(21, 2600)
        r, x = self.upload(c, "AA021.csv", df); self.assertEqual(x["status"], "accepted"); fid = x["id"]
        sha = I.sha256_file(D.original_path(x["sha256"])); self.assertEqual(sha, x["sha256"])
        r, x2 = self.upload(c, "AA021.csv", df); self.assertEqual(x2["status"], "duplicate"); self.assertIn("Byte-identical", x2["reasons"][0])
        r, x3 = self.upload(c, "AA021_copy.csv", df); self.assertEqual(x3["status"], "duplicate")
        df2 = df.iloc[:1500].copy(); df2.loc[:99, "PM10 (ug/m3)"] = 1.0
        r, x4 = self.upload(c, "AA021_copy2.csv", df2); self.assertTrue(x4["stored"]); self.assertEqual(x4["overlap"]["kind"], "overlaps_existing"); self.assertGreater(x4["overlap"]["shared"], 1000)
        self.assertEqual(self.upload(c, "notes.txt", raw=b"hi")[1]["status"], "rejected")
        self.assertEqual(self.upload(c, "AA030.csv", raw=b"")[1]["status"], "rejected")
        self.assertEqual(self.upload(c, "../../evil.csv", H.make_station_csv(1, 100, drop_cols=["PM2.5 (ug/m3)"]))[1]["file_name"], "evil.csv")
        old = C.MAX_UPLOAD_FILE_BYTES; C.MAX_UPLOAD_FILE_BYTES = 1000
        try: self.assertEqual(self.upload(c, "AA031.csv", df)[1]["status"], "rejected")
        finally: C.MAX_UPLOAD_FILE_BYTES = old
        r, p = self.upload(c, "AA022.csv", H.make_station_csv(22, 2600, drop_cols=["AT (degree C)"])); self.assertEqual(p["status"], "pending_review")
        d = c.post(f"/api/admin/files/{p['id']}/decision", json={"action": "approve_structural_absence"}, headers=c.h); self.assertEqual(d.get_json()["status"], "accepted_recovered")
        self.assertEqual(c.post(f"/api/admin/files/{p['id']}/decision", json={"action": "approve_blank_unit", "feature": "RH"}, headers=c.h).status_code, 400)
        self.assertEqual(c.post(f"/api/admin/files/{p['id']}/decision", json={"action": "reject"}, headers=c.h).get_json()["status"], "rejected")
        acts = [a["action"] for a in c.get("/api/admin/audit?size=200").get_json()["rows"]]
        for a in ("upload", "upload_duplicate_bytes", "file_decision", "login"): self.assertIn(a, acts)
        lst = c.get("/api/admin/files?status=rejected&q=evil").get_json(); self.assertEqual(lst["total"], 1)

    def test_full_lifecycle_cumulative_promotion_rollback_and_failure_safety(self):
        from app.db import connect
        from core import datasets as D
        c = self.client("boss@example.org")
        for i in range(1, 11): self.assertEqual(self.upload(c, f"AA{i:03d}.csv", H.make_station_csv(i, 3000))[1]["status"], "accepted")
        # public endpoints are empty-state safe before any model exists
        pub = self.app.test_client(); pub.h = {"X-CSRF-Token": pub.get("/api/csrf").get_json()["token"]}
        self.assertFalse(pub.get("/api/public/research").get_json()["available"]); self.assertEqual(pub.post("/api/public/predict", json={"features": {}}, headers=pub.h).status_code, 503)
        # real subprocess dispatch works
        r = c.post("/api/admin/jobs", json={"kind": "build_dataset", "params": {"note": "first"}}, headers=c.h); self.assertEqual(r.status_code, 202); jid = r.get_json()["job_id"]
        for _ in range(120):
            j = c.get(f"/api/admin/jobs/{jid}").get_json()
            if j["status"] in ("succeeded", "failed"): break
            time.sleep(1)
        self.assertEqual(j["status"], "succeeded", j.get("error") or j.get("log")); self.assertIn("ds-0001", j["result"])
        self.assertTrue(c.get("/api/admin/datasets").get_json()["benchmarks"][0]["active"])
        # train + experiment (inline worker), candidate does not become active
        j = self.run_job("retrain", {"run_experiment": True, "trials": 2}); self.assertEqual(j["status"], "succeeded", j["error"]); res = json.loads(j["result"]); m1 = res["model_id"]
        models = c.get("/api/admin/models").get_json()["rows"]; self.assertEqual([m["status"] for m in models], ["candidate"])
        self.assertFalse(pub.get("/api/public/status").get_json()["model_available"])
        # promotion needs typed confirmation and passes checks
        self.assertEqual(c.post(f"/api/admin/models/{m1}/promote", json={"confirm": "nope"}, headers=c.h).status_code, 400)
        r = c.post(f"/api/admin/models/{m1}/promote", json={"confirm": m1}, headers=c.h); self.assertEqual(r.status_code, 200, r.get_json()); self.assertTrue(r.get_json()["promoted"])
        st = pub.get("/api/public/status").get_json(); self.assertTrue(st["model_available"]); self.assertEqual(st["model"]["id"], m1)
        self.assertTrue(pub.get("/api/public/research").get_json()["available"])
        p = pub.post("/api/public/predict", json={"features": {"PM10": 150}}, headers=pub.h).get_json(); self.assertEqual(len(p["missing"]), 11); self.assertTrue(np.isfinite(p["prediction"]))
        # ---- cumulative: new batch incl. overlapping re-upload; retrain uses ALL files; old versions/benchmark untouched
        n_before = len(list(C.ORIGINALS.glob("*.csv")))
        for i in (11, 12): self.upload(c, f"AA{i:03d}.csv", H.make_station_csv(i, 3000))
        r, ov = self.upload(c, "AA001_copy.csv", H.make_station_csv(1, 3000).iloc[:1200].assign(**{"PM10 (ug/m3)": 3.0})); self.assertEqual(ov["overlap"]["kind"], "overlaps_existing")
        self.assertEqual(len(list(C.ORIGINALS.glob("*.csv"))), n_before + 3)
        self.assertTrue(c.get("/api/admin/overview").get_json()["new_files_since_latest"])
        j = self.run_job("retrain", {"run_experiment": False}); self.assertEqual(j["status"], "succeeded", j["error"]); r2 = json.loads(j["result"]); self.assertEqual(r2["dataset_version"], "ds-0002")
        man1 = json.loads((C.DATASETS / "ds-0001" / "manifest.json").read_text()); man2 = json.loads((C.DATASETS / "ds-0002" / "manifest.json").read_text())
        self.assertEqual(man1["n_files"], 10); self.assertEqual(man2["n_files"], 13); self.assertGreater(man2["rows"], man1["rows"])
        self.assertGreater(man2["duplicates"]["conflicting"], 0, "conflicting duplicate records are counted, not silently dropped")
        self.assertTrue(D.verify_version(C.DATASETS / "ds-0001"))
        self.assertEqual(c.get("/api/admin/datasets").get_json()["benchmarks"].__len__(), 1)
        m2 = r2["model_id"]; self.assertEqual(c.get(f"/api/admin/models/{m2}").get_json()["benchmark_id"], "bench-v1")
        # retrain with no changes reuses the dataset version
        j = self.run_job("build_dataset", {}); self.assertEqual(json.loads(j["result"])["dataset_version"], "ds-0002")
        # ---- failed training must not touch the active model
        shutil_target = C.DATASETS / "ds-0002" / "records.npz"; shutil_target.chmod(0o644)
        with open(shutil_target, "ab") as f: f.write(b"corrupt")
        j = self.run_job("train", {"dataset_version": "ds-0002"}); self.assertEqual(j["status"], "failed"); self.assertIn("checksum", j["error"])
        self.assertEqual(c.get("/api/admin/overview").get_json()["active_model"]["id"], m1)
        self.assertTrue(list(C.MODELS.glob("*.building")) == [])
        # ---- promotion blocks: regressing candidate and corrupted artifact
        con = connect(); met = json.loads(con.execute("SELECT metrics_json FROM models WHERE id=?", (m2,)).fetchone()[0])
        for k in met["test"]: met["test"][k]["rmse"] = met["test"][k]["rmse"] * 1.5
        con.execute("UPDATE models SET metrics_json=? WHERE id=?", (json.dumps(met), m2)); con.close()
        r = c.post(f"/api/admin/models/{m2}/promote", json={"confirm": m2}, headers=c.h)
        self.assertEqual(r.status_code, 409); self.assertFalse(r.get_json()["promoted"]); self.assertEqual(c.get("/api/admin/overview").get_json()["active_model"]["id"], m1)
        bad = [x["key"] for x in r.get_json()["checks"] if not x["ok"]]; self.assertIn("beats_median_baseline" if "beats_median_baseline" in bad else "non_regression_vs_active", bad)
        self.assertEqual(c.post(f"/api/admin/models/{m1}/reject", json={}, headers=c.h).status_code, 409)       # active cannot be rejected
        self.assertEqual(c.post(f"/api/admin/models/{m2}/reject", json={"note": "worse"}, headers=c.h).status_code, 200)
        r = c.post(f"/api/admin/models/{m2}/promote", json={"confirm": m2}, headers=c.h); self.assertEqual(r.status_code, 409)   # rejected can never be promoted
        # ---- rollback path: promote a third equal model, then roll back
        j = self.run_job("train", {"dataset_version": "ds-0001"}); 
        shutil_target.write_bytes(shutil_target.read_bytes()[:-7])      # restore ds-0002 for later runs
        m3 = json.loads(j["result"])["model_id"]; con = connect()
        r = c.post(f"/api/admin/models/{m3}/promote", json={"confirm": m3}, headers=c.h)
        self.assertEqual(r.status_code, 200, r.get_json())   # same data+seed => identical metrics => non-regression holds
        act = c.get("/api/admin/overview").get_json()["active_model"]["id"]; self.assertEqual(act, m3)
        self.assertEqual(c.post("/api/admin/models-rollback", json={"to": m1, "confirm": "wrong"}, headers=c.h).status_code, 400)
        self.assertEqual(c.post("/api/admin/models-rollback", json={"to": m1, "confirm": m1}, headers=c.h).status_code, 200)
        self.assertEqual(c.get("/api/admin/overview").get_json()["active_model"]["id"], m1)
        st = {m["id"]: m["status"] for m in c.get("/api/admin/models").get_json()["rows"]}; self.assertEqual((st[m1], st[m3]), ("active", "archived"))
        ev = [e["action"] for e in c.get("/api/admin/models").get_json()["events"]]; self.assertIn("promoted", ev)

    def test_public_csv_prediction(self):
        from app.db import connect
        pub = self.app.test_client(); pub.h = {"X-CSRF-Token": pub.get("/api/csrf").get_json()["token"]}
        if not pub.get("/api/public/status").get_json()["model_available"]: self.skipTest("depends on lifecycle test having promoted a model (run the whole module)")
        n_files = connect().execute("SELECT COUNT(*) FROM files").fetchone()[0]; n_ds = len(list(C.DATASETS.glob("ds-*")))
        csv = b"station,timestamp,PM10 (ug/m3),NO2 (ug/m3),CO (ug/m3),PM2.5 (ug/m3)\nAA001,2023-01-01 00:00,120,30,900,70\nAA001,2023-01-01 01:00,,40,1100,80\nAA001,2023-01-01 02:00,oops,-5,abc,\n"
        r = pub.post("/api/public/predict-csv", data={"file": (io.BytesIO(csv), "t.csv")}, headers=pub.h, content_type="multipart/form-data"); j = r.get_json(); self.assertEqual(r.status_code, 200, j)
        self.assertEqual(j["rows"], 3); self.assertIn("CO", j["conversions"][0]); self.assertEqual(j["non_numeric_values"], 2); self.assertIsNotNone(j["evaluation"])
        self.assertEqual(j["rows_all_sensors_missing"], 1)   # row 3 has only invalid values; self.assertIn("never added", j["note"])
        d = pub.get("/api/public/predict-download/" + j["token"]); self.assertEqual(d.status_code, 200); self.assertIn(b"pm25_prediction", d.data); self.assertIn(b"imputed_sensors", d.data)
        self.assertEqual(connect().execute("SELECT COUNT(*) FROM files").fetchone()[0], n_files); self.assertEqual(len(list(C.DATASETS.glob("ds-*"))), n_ds)   # not added to training
        self.assertEqual(pub.get("/api/public/predict-download/../../etc/passwd").status_code, 404); self.assertEqual(pub.get("/api/public/predict-download/short").status_code, 404)
        con = connect(); con.execute("UPDATE prediction_runs SET expires_utc='2000-01-01T00:00:00+00:00'"); con.close(); self.assertEqual(pub.get("/api/public/predict-download/" + j["token"]).status_code, 404)
        for name, data, code in [("a.txt", b"x", 400), ("b.csv", b"foo,bar\n1,2\n", 400), ("c.csv", b"PM10\n", 400), ("d.csv", b"\xff\xfe\x00\x01", 400)]:
            self.assertEqual(pub.post("/api/public/predict-csv", data={"file": (io.BytesIO(data), name)}, headers=pub.h, content_type="multipart/form-data").status_code, code, name)
        old = C.MAX_PREDICT_ROWS; C.MAX_PREDICT_ROWS = 2
        try: self.assertEqual(pub.post("/api/public/predict-csv", data={"file": (io.BytesIO(csv), "t.csv")}, headers=pub.h, content_type="multipart/form-data").status_code, 413)
        finally: C.MAX_PREDICT_ROWS = old
        self.assertEqual(pub.post("/api/public/predict", json=[1, 2], headers=pub.h).status_code, 400)

    def test_zz_public_and_admin_pages_render(self):
        pub = self.app.test_client()
        for p in ("/", "/air-quality", "/predict", "/research", "/methodology", "/admin/login"):
            self.assertEqual(pub.get(p).status_code, 200, p)
        for p in ("/about", "/nope"):
            self.assertEqual(pub.get(p).status_code, 404, p)
        c = self.client("boss@example.org")
        for p in ("/admin", "/admin/", "/admin/datasets", "/admin/training", "/admin/experiments", "/admin/models", "/admin/audit", "/admin/settings"):
            self.assertEqual(c.get(p).status_code, 200, p)
        self.assertEqual(pub.get("/api/public/figure/exp-0001/../../x.png").status_code, 404)


class TestFrontendStatic(unittest.TestCase):
    def test_every_page_script_exists_and_templates_are_csp_clean(self):
        from app.pages import PUBLIC, ADMIN
        for k in PUBLIC: self.assertTrue((C.ROOT / "templates/public" / PUBLIC[k][0]).exists())
        for k, (f, _) in ADMIN.items():
            self.assertTrue((C.ROOT / "static/js" / f"admin_{k or 'overview'}.js").exists(), k)
        for p in (C.ROOT / "templates").rglob("*.html"):
            t = p.read_text()
            self.assertNotRegex(t, r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", f"inline script in {p.name}")
            self.assertNotRegex(t, r"\sstyle=\"", f"inline style attribute in {p.name}")
            self.assertNotRegex(t, r"\son(click|load|error)=", f"inline handler in {p.name}")
            self.assertNotRegex(t, r"https?://(?!www\.w3\.org)", f"external resource in {p.name}")

    def test_javascript_syntax(self):
        import shutil
        if not shutil.which("node"): self.skipTest("node not available")
        for f in sorted((C.ROOT / "static/js").glob("*.js")):
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True); self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr[:300]}")

    def test_no_innerhtml_with_data(self):
        for f in (C.ROOT / "static/js").glob("*.js"): self.assertNotRegex(f.read_text(), r"\.innerHTML\s*[+]?=|insertAdjacentHTML|document\.write", f.name)


if __name__ == "__main__":
    unittest.main()
