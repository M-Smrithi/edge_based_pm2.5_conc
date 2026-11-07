"""Software-simulated edge gateway: validate -> detect missing -> median-impute -> local inference.
SOFTWARE SIMULATION on the host computer; NOT a deployment on physical edge hardware."""
from __future__ import annotations
import json, math, time
from pathlib import Path
import joblib
import numpy as np
import core.config as C
from core import schema as S


class EdgeGateway:
    def __init__(self, model, features, medians, ranges=None):
        self.model = model
        self.features = list(features)
        self._med = np.array([medians[f] for f in self.features], dtype=np.float64)
        self.medians = {f: float(medians[f]) for f in self.features}
        self.ranges = ranges or {f: S.FEATURES[f].valid_range for f in self.features}
        self._lo = np.array([self.ranges[f][0] for f in self.features])
        self._hi = np.array([self.ranges[f][1] for f in self.features])

    @classmethod
    def load(cls, model_dir: Path) -> "EdgeGateway":
        model_dir = Path(model_dir)
        pre = json.loads((model_dir / "preprocessing.json").read_text())
        model = joblib.load(model_dir / "model.joblib")
        return cls(model, pre["features"], pre["medians"], {k: tuple(v) for k, v in pre["ranges"].items()})

    def preprocess(self, record: dict):
        x = self._med.copy()
        missing, invalid = [], []
        for i, f in enumerate(self.features):
            v = record.get(f)
            ok = False
            if v is not None and v != "":
                try:
                    fv = float(v)
                    if math.isfinite(fv) and self._lo[i] <= fv <= self._hi[i]:
                        x[i] = fv; ok = True
                    else:
                        invalid.append(f)
                except (TypeError, ValueError):
                    invalid.append(f)
            if not ok:
                missing.append(f)
        unknown = [k for k in record if k not in self.features and k not in ("station", "timestamp", "id", "ID", "PM2.5")]
        return x.reshape(1, -1), dict(missing=missing, invalid=invalid, unknown_fields=unknown,
                                      imputed={f: self.medians[f] for f in missing})

    def preprocess_array(self, A: np.ndarray) -> np.ndarray:
        """Vectorised preprocess for a float array (n x n_features). Invalid/out-of-range -> missing -> median."""
        A = np.array(A, dtype=np.float64, copy=True)
        bad = ~np.isfinite(A) | (A < self._lo) | (A > self._hi)
        A[bad] = np.nan
        nan = np.isnan(A)
        A[nan] = np.broadcast_to(self._med, A.shape)[nan]
        return A

    def process_record(self, record: dict) -> dict:
        t0 = time.perf_counter_ns()
        x, info = self.preprocess(record)
        t1 = time.perf_counter_ns()
        y = float(self.model.predict(x)[0])
        t2 = time.perf_counter_ns()
        return dict(prediction=y, preprocess_ms=(t1 - t0) / 1e6, inference_ms=(t2 - t1) / 1e6,
                    total_ms=(t2 - t0) / 1e6, **info)

    def predict_array(self, A: np.ndarray) -> np.ndarray:
        return self.model.predict(self.preprocess_array(A))
