import io, os, shutil, sys, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import core.config as C

HEADER = ["From Date", "To Date", "PM2.5 (ug/m3)", "PM10 (ug/m3)", "NO (ug/m3)", "NO2 (ug/m3)", "NOx (ppb)", "SO2 (ug/m3)",
          "CO (mg/m3)", "Ozone (ug/m3)", "RH (%)", "WS (m/s)", "WD (deg)", "SR (W/mt2)", "AT (degree C)"]


def make_station_csv(seed=0, n=2600, start="2019-01-01", drop_cols=(), rename=None, nan_frac=0.05, dup_rows=0, bad_target=0.0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=n, freq="h")
    pm10 = np.abs(rng.normal(120, 50, n)) + 5
    d = {"From Date": ts.strftime("%Y-%m-%d %H:%M:%S"), "To Date": (ts + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
         "PM2.5 (ug/m3)": np.clip(pm10 * 0.55 + rng.normal(0, 8, n), 1, 600), "PM10 (ug/m3)": pm10,
         "NO (ug/m3)": np.abs(rng.normal(10, 5, n)), "NO2 (ug/m3)": np.abs(rng.normal(30, 10, n)), "NOx (ppb)": np.abs(rng.normal(25, 8, n)),
         "SO2 (ug/m3)": np.abs(rng.normal(8, 3, n)), "CO (mg/m3)": np.abs(rng.normal(1, .4, n)), "Ozone (ug/m3)": np.abs(rng.normal(30, 12, n)),
         "RH (%)": np.clip(rng.normal(60, 15, n), 5, 100), "WS (m/s)": np.abs(rng.normal(1.5, .6, n)), "WD (deg)": rng.uniform(0, 360, n),
         "SR (W/mt2)": np.abs(rng.normal(150, 80, n)), "AT (degree C)": rng.normal(26, 5, n)}
    df = pd.DataFrame(d)
    for c in HEADER[3:]:
        df.loc[rng.random(n) < nan_frac, c] = np.nan
    if bad_target:
        df.loc[rng.random(n) < bad_target, "PM2.5 (ug/m3)"] = np.nan
    if dup_rows:
        df = pd.concat([df, df.iloc[:dup_rows]], ignore_index=True)
    df = df.drop(columns=list(drop_cols))
    if rename: df = df.rename(columns=rename)
    return df


def write_csv(df, path):
    df.to_csv(path, index=False); return Path(path)


class TmpHome:
    """Isolated AIOT_HOME for a test case."""
    def setUpHome(self):
        self.home = Path(tempfile.mkdtemp(prefix="aiot_test_"))
        C.set_home(self.home); C.ensure_dirs()
        info = C.STATIONS_INFO
        info.write_text("file_name,state,city,agency,station_location\n" + "\n".join(f"AA{i:03d},TestState,City{i},CPCB,Loc{i}" for i in range(1, 30)) + "\n")
        os.environ["AIOT_HOME"] = str(self.home)
    def tearDownHome(self):
        shutil.rmtree(self.home, ignore_errors=True)
