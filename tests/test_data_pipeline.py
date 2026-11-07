import tempfile, unittest
from pathlib import Path
import numpy as np, pandas as pd
from tests import helpers as H
import core.config as C
from core import ingest as I, schema as S, datasets as D, benchmark as B, audit_files


class TestSchema(unittest.TestCase):
    def test_exact_and_alias(self):
        r = S.resolve_header(H.HEADER)
        self.assertTrue(all(r[n]["status"] in ("exact", "converted") for n in S.FEATURE_NAMES))
        r = S.resolve_header(["WD (degree)"] + [h for h in H.HEADER if h != "WD (deg)"])
        self.assertEqual(r["WD"]["status"], "exact")

    def test_verified_unit_conversion_only(self):
        r = S.resolve_header(["CO (ug/m3)", "NO (mg/m3)"])
        self.assertEqual((r["CO"]["status"], r["CO"]["factor"]), ("converted", 0.001))
        self.assertEqual((r["NO"]["status"], r["NO"]["factor"]), ("converted", 1000.0))

    def test_unit_guessing_is_refused(self):
        r = S.resolve_header(["SO2 (ppb)", "AT (degree)", "RH ()", "WS (km/h)"])
        for n in ("SO2", "AT", "RH", "WS"):
            self.assertNotIn(r[n]["status"], ("exact", "converted"), n)
        self.assertEqual(r["RH"]["status"], "blank_unit")

    def test_no_target_leakage(self):
        self.assertNotIn("PM2.5", S.FEATURE_NAMES)
        S.assert_no_leakage(S.FEATURE_NAMES)
        with self.assertRaises(Exception): S.assert_no_leakage(S.FEATURE_NAMES + ["PM2.5"])

    def test_target_status(self):
        self.assertEqual(S.target_status(H.HEADER), "ok")
        self.assertEqual(S.target_status(["From Date"]), "absent")
        self.assertEqual(S.target_status(["PM2.5 (mg/m3)"]), "unit_mismatch")


class TestCanonicalize(unittest.TestCase):
    def test_cleaning_policy(self):
        df = H.make_station_csv(1, 300, dup_rows=10, bad_target=0.1)
        df.loc[5, "PM10 (ug/m3)"] = 99999       # out of range -> NaN, row kept
        df.loc[6, "PM2.5 (ug/m3)"] = -5          # invalid target -> row dropped
        out, rep = I.canonicalize(df, "AA001")
        self.assertEqual(rep["duplicate_timestamps_removed"], 10)
        self.assertTrue(out["PM2.5"].notna().all())
        self.assertGreater(rep["rows_dropped_missing_target"], 0)
        self.assertEqual(rep["out_of_range_set_nan"]["PM10"], 1)
        self.assertTrue(np.isnan(out.loc[out.timestamp == pd.Timestamp(df.loc[5, "From Date"]), "PM10"]).all())
        self.assertTrue(out[S.FEATURE_NAMES].isna().any(axis=1).any(), "rows with partial missing inputs must be kept")
        self.assertTrue(out.timestamp.is_monotonic_increasing)

    def test_all_missing_sensor_rows_dropped(self):
        df = H.make_station_csv(2, 50)
        df.loc[3, H.HEADER[3:]] = np.nan
        out, rep = I.canonicalize(df, "AA001")
        self.assertEqual(rep["rows_dropped_all_sensors_missing"], 1)

    def test_co_conversion_applied(self):
        df = H.make_station_csv(3, 50).rename(columns={"CO (mg/m3)": "CO (ug/m3)"})
        df["CO (ug/m3)"] = df["CO (ug/m3)"] * 1000
        out, rep = I.canonicalize(df, "AA001")
        self.assertTrue(out["CO"].dropna().between(0, 5).all())
        self.assertEqual(rep["mapping_log"][0]["action"], "unit_conversion")

    def test_station_name_normalisation(self):
        self.assertEqual(I.station_from_filename("AP001_copy.csv"), "AP001")
        self.assertEqual(I.station_from_filename("ap001-2.csv"), "AP001")
        self.assertEqual(I.station_from_filename("AP001.csv"), "AP001")
        self.assertEqual(I.station_from_filename("../../etc/passwd.csv"), "passwd")  # directory components are stripped
        self.assertIsNone(I.station_from_filename("bad name.csv"))


class TestAudit(H.TmpHome, unittest.TestCase):
    def setUp(self): self.setUpHome()
    def tearDown(self): self.tearDownHome()

    def _a(self, df, name="AA001.csv"):
        p = self.home / name; H.write_csv(df, p)
        return I.audit_file(p, info=I.load_stations_info())

    def test_verdicts(self):
        self.assertEqual(self._a(H.make_station_csv(1))["verdict"], "accepted")
        self.assertEqual(self._a(H.make_station_csv(1), "AA002.csv")["station_meta"]["city"], "City2")
        self.assertEqual(self._a(H.make_station_csv(1, rename={"WD (deg)": "WD (degree)"}))["verdict"], "accepted_recovered")
        a = self._a(H.make_station_csv(1, drop_cols=["PM2.5 (ug/m3)"])); self.assertEqual(a["verdict"], "rejected")
        a = self._a(H.make_station_csv(1, drop_cols=["AT (degree C)"])); self.assertEqual(a["verdict"], "pending_review"); self.assertIn("AT", a["structural_absence"])
        a = self._a(H.make_station_csv(1, rename={"RH (%)": "RH ()"})); self.assertEqual(a["verdict"], "pending_review"); self.assertTrue(a["proposals"])
        a = self._a(H.make_station_csv(1).drop(columns=["From Date"])); self.assertEqual(a["verdict"], "rejected")

    def test_decision_makes_pending_usable(self):
        a = I.audit_file(self.home / "AA001.csv", info=None) if False else None
        p = self.home / "AA001.csv"; H.write_csv(H.make_station_csv(1, drop_cols=["AT (degree C)"]), p)
        a = I.audit_file(p, decisions={"structural_absence": ["AT"]}); self.assertEqual(a["verdict"], "accepted_recovered")

    def test_works_without_stations_info(self):
        p = self.home / "ZZ999.csv"; H.write_csv(H.make_station_csv(1), p)
        a = I.audit_file(p, info=None); self.assertEqual(a["verdict"], "accepted"); self.assertFalse(a["station_meta"]["verified"])

    def test_bad_files_rejected_not_crash(self):
        for name, content in [("AA003.csv", b""), ("AA004.csv", b"\xff\xfe\x00garbage"), ("AA005.csv", b"a,b\n1,2\n"), ("AA006.csv", b"From Date,PM2.5 (ug/m3)\nnot-a-date,5\n")]:
            p = self.home / name; p.write_bytes(content)
            self.assertEqual(I.audit_file(p)["verdict"], "rejected", name)

    def test_audit_script_reports_and_preserves_inputs(self):
        src = self.home / "in"; src.mkdir()
        H.write_csv(H.make_station_csv(1), src / "AA001.csv"); H.write_csv(H.make_station_csv(2, drop_cols=["AT (degree C)"]), src / "AA002.csv")
        before = {p.name: I.sha256_file(p) for p in src.iterdir()}
        doc = audit_files.run_audit(src, self.home / "out")
        self.assertEqual(doc["summary"]["verdicts"], {"accepted": 1, "pending_review": 1})
        self.assertTrue((self.home / "out" / "audit_latest.md").exists() and (self.home / "out" / "audit_latest.json").exists())
        self.assertEqual(before, {p.name: I.sha256_file(p) for p in src.iterdir()})


class TestDatasetsAndBenchmark(H.TmpHome, unittest.TestCase):
    def setUp(self):
        self.setUpHome(); self.entries = []
        for i in range(1, 11):
            p = self.home / f"AA{i:03d}.csv"; H.write_csv(H.make_station_csv(i, 3000, start="2019-01-01"), p)
            sha, _ = D.store_original(p); self.entries.append(dict(file_name=p.name, sha256=sha, station=f"AA{i:03d}"))
    def tearDown(self): self.tearDownHome()

    def test_originals_immutable_and_content_addressed(self):
        p = self.home / "AA001.csv"; sha, new = D.store_original(p); self.assertFalse(new)
        self.assertEqual(I.sha256_file(D.original_path(sha)), sha)
        self.assertEqual(D.original_path(sha).stat().st_mode & 0o777, 0o444)  # read-only (root can still bypass; mode is what we guarantee)

    def test_dedup_counts_and_atomic_build(self):
        # same station, overlapping timestamps: identical + conflicting duplicates are counted, first kept
        df = H.make_station_csv(1, 3000); df2 = df.copy(); df2.loc[:99, "PM10 (ug/m3)"] = 7.0; df2.loc[100:199, "PM10 (ug/m3)"] = df.loc[100:199, "PM10 (ug/m3)"]
        p = self.home / "AA001_copy.csv"; H.write_csv(df2.iloc[:200], p); sha, _ = D.store_original(p)
        ents = self.entries[:1] + [dict(file_name=p.name, sha256=sha, station="AA001")]
        man = D.build_version(ents, C.DATASETS / "ds-0001")
        self.assertGreater(man["duplicates"]["identical"] + man["duplicates"]["conflicting"], 150)
        self.assertGreater(man["duplicates"]["conflicting"], 0)
        self.assertEqual(man["n_stations"], 1)
        self.assertEqual(man["rows"], man["rows_before_dedup"] - man["duplicates"]["identical"] - man["duplicates"]["conflicting"])
        self.assertTrue(D.verify_version(C.DATASETS / "ds-0001"))
        with self.assertRaises(FileExistsError): D.build_version(ents, C.DATASETS / "ds-0001")
        self.assertFalse(list(C.DATASETS.glob("*.building")))

    def test_failed_build_leaves_nothing(self):
        bad = self.entries + [dict(file_name="x.csv", sha256="0" * 64, station="AA099")]
        with self.assertRaises(Exception): D.build_version(bad, C.DATASETS / "ds-0009")
        self.assertFalse((C.DATASETS / "ds-0009").exists()); self.assertFalse(list(C.DATASETS.glob("*.building")))

    def test_benchmark_is_frozen_and_spatially_disjoint(self):
        C.HOLDOUT_STATION_FRAC = 0.3
        try:
            man = D.build_version(self.entries, C.DATASETS / "ds-0001"); rec = D.load_records(C.DATASETS / "ds-0001")
            b = B.create(rec, "bench-v1", C.BENCHMARKS / "bench-v1"); bm = B.load(C.BENCHMARKS / "bench-v1")
            self.assertTrue(b["holdout_stations"], "need at least one held-out station")
            lab = B.assign(rec, bm); codes = np.array(rec["codes"])[rec["station"]]
            hold = np.isin(codes, b["holdout_stations"])
            self.assertFalse(np.any(hold & np.isin(lab, [B.TRAIN, B.VAL, B.TEST_T])), "held-out stations must never be used for training/validation/temporal test")
            self.assertEqual(int((lab == B.TEST_S).sum()), b["n_test_spatial"]); self.assertEqual(int((lab == B.TEST_T).sum()), b["n_test_temporal"])
            tr_ts, te_ts = rec["ts_ns"][lab == B.TRAIN], rec["ts_ns"][lab == B.TEST_T]
            self.assertLess(tr_ts.max(), te_ts.min(), "training period precedes the temporal test period")
            # cumulative growth: a new version with extra data must not change the frozen test records
            extra = self.home / "AA011.csv"; H.write_csv(H.make_station_csv(11, 3000, start="2019-01-01"), extra); sha, _ = D.store_original(extra)
            late = self.home / "AA001_late.csv"; H.write_csv(H.make_station_csv(99, 500, start="2019-06-01"), late); sha2, _ = D.store_original(late)
            D.build_version(self.entries + [dict(file_name="AA011.csv", sha256=sha, station="AA011"), dict(file_name="AA001_late.csv", sha256=sha2, station="AA001")], C.DATASETS / "ds-0002")
            rec2 = D.load_records(C.DATASETS / "ds-0002"); lab2 = B.assign(rec2, bm)
            self.assertEqual(int((lab2 == B.TEST_T).sum()), b["n_test_temporal"]); self.assertEqual(int((lab2 == B.TEST_S).sum()), b["n_test_spatial"])
            k = lambda r, l, c: sorted(zip(np.array(r["codes"])[r["station"]][l == c], r["ts_ns"][l == c]))
            self.assertEqual(k(rec, lab, B.TEST_T), k(rec2, lab2, B.TEST_T))
            with self.assertRaises(FileExistsError): B.create(rec, "bench-v1", C.BENCHMARKS / "bench-v1")
        finally:
            C.HOLDOUT_STATION_FRAC = 0.15


if __name__ == "__main__":
    unittest.main()
