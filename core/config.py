"""Central configuration. Environment variables override defaults; nothing secret lives in source."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("AIOT_HOME", ROOT))
STORAGE = Path(os.environ.get("AIOT_STORAGE", HOME / "storage"))
INSTANCE = Path(os.environ.get("AIOT_INSTANCE", HOME / "instance"))
DB_PATH = Path(os.environ.get("AIOT_DB", INSTANCE / "app.db"))

ORIGINALS = STORAGE / "originals"        # immutable, content-addressed copies of every received file
AUDITS = STORAGE / "audits"              # per-file audit reports (JSON)
DATASETS = STORAGE / "datasets"          # dataset versions (records + manifest + summaries)
BENCHMARKS = STORAGE / "benchmarks"      # frozen evaluation sets
MODELS = STORAGE / "models"              # model artifacts per version
EXPERIMENTS = STORAGE / "experiments"    # experiment outputs
PREDICTIONS = STORAGE / "predictions"    # public batch-prediction outputs (temporary)
JOBLOGS = STORAGE / "joblogs"
INCOMING = STORAGE / "incoming"          # staging for uploads in progress
STATIONS_INFO = Path(os.environ.get("AIOT_STATIONS_INFO", STORAGE / "metadata" / "stations_info.csv"))

TARGET = "PM2.5"
TARGET_RAW = "PM2.5 (ug/m3)"
TARGET_RANGE = (0.0, 1000.0)
TIME_COL = "From Date"

# ---- limits ---------------------------------------------------------------
MAX_UPLOAD_FILE_BYTES = int(os.environ.get("AIOT_MAX_UPLOAD_FILE_MB", 64)) * 1024 * 1024
MAX_REQUEST_BYTES = int(os.environ.get("AIOT_MAX_REQUEST_MB", 512)) * 1024 * 1024
MAX_UPLOAD_ROWS = int(os.environ.get("AIOT_MAX_UPLOAD_ROWS", 400_000))
MAX_PREDICT_FILE_BYTES = 5 * 1024 * 1024
MAX_PREDICT_ROWS = 20_000
MAX_CONCURRENT_JOBS = int(os.environ.get("AIOT_MAX_JOBS", 1))
PREDICTION_TTL_HOURS = 24

# ---- station eligibility ---------------------------------------------------
MIN_STATION_VALID_ROWS = 2000          # valid-target rows needed for a station to enter training/benchmarks

# ---- benchmark / split -------------------------------------------------------
TRAIN_FRAC, VAL_FRAC = 0.70, 0.15      # of valid rows in non-holdout stations (chronological cut-points)
HOLDOUT_STATION_FRAC = float(os.environ.get("AIOT_HOLDOUT_FRAC", 0.15))            # deterministic hash-based station hold-out
SEED = 42

# ---- experiments ------------------------------------------------------------
MISSING_RATES = [0.0, 0.10, 0.20]
PATTERNS = ["random", "consecutive"]
DEFAULT_TRIALS = 10
EXPERIMENT_SEED = 2024
BLOCK_LEN_RANGE = (6, 48)
LATENCY_N_RECORDS = 200
LATENCY_WARMUP = 20

# ---- auth ----------------------------------------------------------------------
MIN_PASSWORD_LEN = 12
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
SESSION_HOURS = 8


def set_home(home) -> None:
    """Re-point every storage/instance path (used by tests and by `AIOT_HOME`). Safe to call repeatedly."""
    g = globals()
    h = Path(home)
    g["HOME"] = h
    g["STORAGE"] = h / "storage"
    g["INSTANCE"] = h / "instance"
    g["DB_PATH"] = g["INSTANCE"] / "app.db"
    for name, sub in (("ORIGINALS", "originals"), ("AUDITS", "audits"), ("DATASETS", "datasets"), ("BENCHMARKS", "benchmarks"),
                      ("MODELS", "models"), ("EXPERIMENTS", "experiments"), ("PREDICTIONS", "predictions"),
                      ("JOBLOGS", "joblogs"), ("INCOMING", "incoming")):
        g[name] = g["STORAGE"] / sub
    g["STATIONS_INFO"] = g["STORAGE"] / "metadata" / "stations_info.csv"


def ensure_dirs() -> None:
    for p in (ORIGINALS, AUDITS, DATASETS, BENCHMARKS, MODELS, EXPERIMENTS, PREDICTIONS, JOBLOGS, INCOMING,
              STATIONS_INFO.parent, INSTANCE):
        Path(p).mkdir(parents=True, exist_ok=True)
