import json, unittest
import numpy as np
from tests import helpers as H
import core.config as C
from core import benchmark as B, datasets as D, experiments as E, sim, train as T, schema as S, metrics as M
from core.gateway import EdgeGateway


class TestSimulator(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0); self.n = 6000
        self.X = rng.normal(50, 10, (self.n, 12)); self.X[rng.random(self.X.shape) < .05] = np.nan
        self.st = np.repeat(np.arange(3), 2000); self.ts = np.tile(np.arange(2000), 3) * 3_600_000_000_000
        self.ts[1000:] += 5 * 3_600_000_000_000          # a gap inside every station's series

    def test_random_exact_rate_of_observed_cells_and_seeded(self):
        for rate in (.1, .2):
            Xm, m = sim.inject(self.X, rate, "random", 7)
            obs = (~np.isnan(self.X)).sum(); self.assertEqual(m["masked_cells"], round(rate * obs))
            self.assertTrue(np.all(np.isnan(Xm[np.isnan(self.X)])), "natural NaNs stay NaN")
            Xm2, _ = sim.inject(self.X, rate, "random", 7); self.assertTrue(np.array_equal(Xm, Xm2, equal_nan=True))
            Xm3, _ = sim.inject(self.X, rate, "random", 8); self.assertFalse(np.array_equal(Xm, Xm3, equal_nan=True))

    def test_consecutive_blocks_contiguous_one_sensor_one_station_no_gap_crossing(self):
        for seed in range(5):
            Xm, m = sim.inject(self.X, .1, "consecutive", seed, self.st, self.ts)
            self.assertEqual(m["masked_cells"], round(.1 * (~np.isnan(self.X)).sum()))
            masked = np.isnan(Xm) & ~np.isnan(self.X)
            for f in range(12):
                rows = np.flatnonzero(masked[:, f])
                # split into runs of consecutive row indices; each run must lie in one station & unbroken hourly segment
                runs = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
                for r in runs:
                    if len(r) < 2: continue
                    self.assertEqual(len(set(self.st[r])), 1)
                    self.assertTrue(np.all(np.diff(self.ts[r]) == 3_600_000_000_000), "run crosses a time gap")
        lens = [len(r) for f in range(12) for r in np.split(np.flatnonzero(np.isnan(Xm[:, f]) & ~np.isnan(self.X[:, f])), [])]
        self.assertGreater(m["blocks"], 5)

    def test_consecutive_is_actually_clustered_vs_random(self):
        def adj(Xm):
            mk = np.isnan(Xm) & ~np.isnan(self.X); return int((mk[1:] & mk[:-1]).sum())
        self.assertGreater(adj(sim.inject(self.X, .1, "consecutive", 1, self.st, self.ts)[0]), 5 * adj(sim.inject(self.X, .1, "random", 1)[0]))

    def test_zero_rate_changes_nothing_and_input_untouched(self):
        orig = self.X.copy(); Xm, m = sim.inject(self.X, 0.0, "none", 0)
        self.assertTrue(np.array_equal(Xm, orig, equal_nan=True)); self.assertEqual(m["masked_cells"], 0)
        sim.inject(self.X, .2, "random", 1); self.assertTrue(np.array_equal(self.X, orig, equal_nan=True))


class TestModelPipeline(H.TmpHome, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = H.TmpHome(); cls.t.setUpHome(); C.HOLDOUT_STATION_FRAC = 0.3
        ents = []
        for i in range(1, 11):
            p = cls.t.home / f"AA{i:03d}.csv"; H.write_csv(H.make_station_csv(i, 3000), p); sha, _ = D.store_original(p); ents.append(dict(file_name=p.name, sha256=sha, station=f"AA{i:03d}"))
        D.build_version(ents, C.DATASETS / "ds-0001"); rec = D.load_records(C.DATASETS / "ds-0001"); B.create(rec, "bench-v1", C.BENCHMARKS / "bench-v1")
        cls.out = T.train(C.DATASETS / "ds-0001", C.BENCHMARKS / "bench-v1", C.MODELS / "model-0001",
                          dict(n_estimators=8, max_samples=0.5, candidates=[dict(name="rf", kind="rf", min_samples_leaf=10, max_features=0.6), dict(name="hgb", kind="hgb", max_iter=40, learning_rate=0.1, max_leaf_nodes=15)]))
        cls.rec, cls.bench = rec, B.load(C.BENCHMARKS / "bench-v1"); cls.lab = B.assign(rec, cls.bench)

    @classmethod
    def tearDownClass(cls): C.HOLDOUT_STATION_FRAC = 0.15; cls.t.tearDownHome()

    def test_artifacts_complete_and_verified(self):
        d = C.MODELS / "model-0001"
        for f in ("model.joblib", "preprocessing.json", "schema.json", "metrics.json", "manifest.json", "train.log"): self.assertTrue((d / f).exists(), f)
        man = json.loads((d / "manifest.json").read_text())
        for k in ("seed", "dataset_records_sha256", "benchmark_sha256", "model_sha256", "environment", "params"): self.assertIn(k, man)
        self.assertTrue(T.verify_model(d)["ok"])

    def test_medians_fitted_on_training_split_only(self):
        pre = json.loads((C.MODELS / "model-0001" / "preprocessing.json").read_text())
        X = self.rec["X"]; tr = self.lab == B.TRAIN
        for j, n in enumerate(S.FEATURE_NAMES):
            self.assertAlmostEqual(pre["medians"][n], round(float(np.nanmedian(X[tr, j])), 4), places=3)

    def test_selection_never_uses_test_data_and_rule(self):
        met = self.out["metrics"]; names = {c["name"] for c in met["candidates"]}
        self.assertIn("median_baseline", names); self.assertIn("test", met)
        cands = [dict(name="a", val=dict(rmse=10.0, mae=5), latency_ms=5.0, size_mb=1), dict(name="b", val=dict(rmse=10.05, mae=5), latency_ms=1.0, size_mb=1), dict(name="c", val=dict(rmse=12.0, mae=5), latency_ms=0.1, size_mb=1)]
        self.assertEqual(T.select(cands)["name"], "b")     # within 1% -> faster wins; 'c' is too inaccurate
        cands[1]["val"]["rmse"] = 10.5; self.assertEqual(T.select(cands)["name"], "a")

    def test_model_beats_baseline_on_both_test_sets(self):
        for k, v in self.out["metrics"]["test"].items(): self.assertLess(v["rmse"], v["baseline_rmse"], k)

    def test_gateway_imputation_and_validation(self):
        gw = EdgeGateway.load(C.MODELS / "model-0001")
        r = gw.process_record({"PM10": 100, "NO2": "abc", "RH": 500, "SO2": float("nan"), "bogus": 1})
        self.assertEqual(set(r["missing"]), set(S.FEATURE_NAMES) - {"PM10"})
        self.assertIn("NO2", r["invalid"]); self.assertIn("RH", r["invalid"]); self.assertIn("bogus", r["unknown_fields"])
        self.assertTrue(np.isfinite(r["prediction"]))
        for k in ("preprocess_ms", "inference_ms", "total_ms"): self.assertGreaterEqual(r[k], 0)
        pre = json.loads((C.MODELS / "model-0001" / "preprocessing.json").read_text())
        self.assertAlmostEqual(r["imputed"]["NO"], pre["medians"]["NO"])
        a = np.array([[100] + [np.nan] * 11]); b = np.array([[100] + [pre["medians"][n] for n in S.FEATURE_NAMES[1:]]])
        self.assertTrue(np.allclose(gw.preprocess_array(a), gw.preprocess_array(b)))
        self.assertTrue(np.isfinite(gw.process_record({})["prediction"]), "all-missing record still yields a finite estimate")

    def test_experiments_same_records_and_monotone_error(self):
        meta = E.run(C.MODELS / "model-0001", C.DATASETS / "ds-0001", C.BENCHMARKS / "bench-v1", C.EXPERIMENTS / "exp-0001", trials=3)
        res = json.loads((C.EXPERIMENTS / "exp-0001" / "results.json").read_text()); rows = res["rows"]
        self.assertEqual({(r["test_set"], r["n"]) for r in rows}, {("temporal", int((self.lab == B.TEST_T).sum())), ("spatial", int((self.lab == B.TEST_S).sum()))})
        s = {(r["test_set"], r["missing_rate"], r["pattern"]): r for r in E.summarise(res)}
        for ts in ("temporal", "spatial"):
            self.assertLessEqual(s[(ts, 0.0, "none")]["rmse"], s[(ts, .1, "random")]["rmse"] + 1e-6)
            self.assertLessEqual(s[(ts, .1, "random")]["rmse"], s[(ts, .2, "random")]["rmse"] + 1e-6)
            self.assertEqual(s[(ts, .1, "random")]["n_trials"], 3)
        for r in rows:
            if r["missing_rate"]: self.assertAlmostEqual(r["achieved_rate"], r["missing_rate"], places=4)
        self.assertEqual({(l["missing_rate"], l["pattern"]) for l in res["latency"]}, {(0.0, "none"), (.1, "random"), (.1, "consecutive"), (.2, "random"), (.2, "consecutive")})
        self.assertIn("preprocess", res["latency"][0]); self.assertIn("software simulation", meta["note"].lower())
        # reproducibility: same seed -> identical numbers
        E.run(C.MODELS / "model-0001", C.DATASETS / "ds-0001", C.BENCHMARKS / "bench-v1", C.EXPERIMENTS / "exp-0002", trials=3)
        r2 = json.loads((C.EXPERIMENTS / "exp-0002" / "results.json").read_text())["rows"]
        self.assertTrue(all(abs(a["rmse"] - b["rmse"]) < 1e-9 for a, b in zip(rows, r2)))

    def test_experiment_refuses_mismatched_benchmark(self):
        import shutil
        shutil.copytree(C.BENCHMARKS / "bench-v1", C.BENCHMARKS / "bench-vX")
        j = json.loads((C.BENCHMARKS / "bench-vX" / "benchmark.json").read_text()); j["benchmark_sha256"] = "0" * 64; (C.BENCHMARKS / "bench-vX" / "benchmark.json").write_text(json.dumps(j))
        with self.assertRaises(RuntimeError): E.run(C.MODELS / "model-0001", C.DATASETS / "ds-0001", C.BENCHMARKS / "bench-vX", C.EXPERIMENTS / "exp-0009", trials=1)

    def test_corrupt_artifact_detected(self):
        import shutil
        shutil.copytree(C.MODELS / "model-0001", C.MODELS / "model-0007")
        with open(C.MODELS / "model-0007" / "model.joblib", "ab") as f: f.write(b"x")
        self.assertFalse(T.verify_model(C.MODELS / "model-0007")["ok"])

    def test_failed_training_leaves_no_model_dir(self):
        with self.assertRaises(Exception): T.train(C.DATASETS / "ds-0001", C.BENCHMARKS / "bench-v1", C.MODELS / "model-0008", dict(candidates=[dict(name="x", kind="rf", min_samples_leaf="boom", max_features=0.5)]))
        self.assertFalse((C.MODELS / "model-0008").exists())


class TestMetrics(unittest.TestCase):
    def test_values(self):
        y, p = [1, 2, 3, 4], [1, 2, 3, 6]
        self.assertAlmostEqual(M.mae(y, p), .5); self.assertAlmostEqual(M.rmse(y, p), 1.0)
        self.assertAlmostEqual(M.r2(y, y), 1.0)


if __name__ == "__main__":
    unittest.main()
