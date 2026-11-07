"""The 12-sensor schema, verified header/unit resolution and the (small) set of verified unit conversions.

Principles
* A header is accepted only if name AND unit match exactly, or if a conversion is mathematically exact SI
  (e.g. ug/m3 -> mg/m3 is /1000). Conversions that need assumptions (ppb<->ug/m3 needs temperature, pressure and
  molecular weight; 'Nm3' is a different reference volume) are NOT performed.
* Blank-unit or contradictory-unit columns are never guessed. They are surfaced for administrator review.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

import core.config as C


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    unit: str
    label: str
    valid_range: tuple
    exact: tuple                 # accepted raw headers (name + unit exactly)
    conversions: tuple = ()      # (raw header, multiplier, rationale) exact SI conversions to `unit`
    stem: str = ""               # header stem used to find variants like 'WS ()' for review proposals


FEATURES: dict[str, FeatureSpec] = {f.name: f for f in [
    FeatureSpec("PM10", "ug/m3", "PM10", (0, 1000), ("PM10 (ug/m3)",), stem="PM10"),
    FeatureSpec("NO", "ug/m3", "Nitric oxide", (0, 500), ("NO (ug/m3)",),
                (("NO (mg/m3)", 1000.0, "1 mg = 1000 ug"),), stem="NO"),
    FeatureSpec("NO2", "ug/m3", "Nitrogen dioxide", (0, 500), ("NO2 (ug/m3)",), stem="NO2"),
    FeatureSpec("NOx", "ppb", "Nitrogen oxides", (0, 500), ("NOx (ppb)",), stem="NOx"),
    FeatureSpec("SO2", "ug/m3", "Sulphur dioxide", (0, 500), ("SO2 (ug/m3)",), stem="SO2"),
    FeatureSpec("CO", "mg/m3", "Carbon monoxide", (0, 50), ("CO (mg/m3)",),
                (("CO (ug/m3)", 0.001, "1 ug = 0.001 mg"), ("CO (ng/m3)", 1e-6, "1 ng = 1e-6 mg")), stem="CO"),
    FeatureSpec("O3", "ug/m3", "Ozone", (0, 500), ("Ozone (ug/m3)",), stem="Ozone"),
    FeatureSpec("RH", "%", "Relative humidity", (0, 100), ("RH (%)",), stem="RH"),
    FeatureSpec("WS", "m/s", "Wind speed", (0, 50), ("WS (m/s)",), stem="WS"),
    FeatureSpec("WD", "degrees", "Wind direction", (0, 360), ("WD (deg)", "WD (degree)"), stem="WD"),
    FeatureSpec("SR", "W/m2", "Solar radiation", (0, 1500), ("SR (W/mt2)",), stem="SR"),
    FeatureSpec("AT", "deg C", "Ambient temperature", (-10, 55), ("AT (degree C)",), stem="AT"),
]}
FEATURE_NAMES = list(FEATURES)
RAW_TO_CANON = {raw: n for n, s in FEATURES.items() for raw in s.exact}

NON_FEATURES = {"station", "timestamp", C.TARGET}


def assert_no_leakage(names) -> None:
    bad = [n for n in names if n in NON_FEATURES or n.lower().startswith("pm2.5") or "pm25" in n.lower()]
    if bad:
        raise ValueError(f"Target leakage / identifier used as feature: {bad}")
    unknown = [n for n in names if n not in FEATURES]
    if unknown:
        raise ValueError(f"Unknown features: {unknown}")


_UNIT_RE = re.compile(r"^\s*(?P<stem>.+?)\s*\((?P<unit>.*)\)\s*$")


def resolve_header(header: list[str]) -> dict:
    """Resolve each canonical feature against the raw header.

    status per feature:
      exact      header matches exactly                       -> usable as-is
      converted  verified exact SI conversion available        -> usable after conversion (logged)
      blank_unit same stem, empty unit '()'                    -> NEEDS REVIEW (proposal only, never guessed)
      bad_unit   same stem, unit contradicts / not convertible -> unusable column (never mapped)
      absent     no column for this sensor                      -> structural absence
    """
    res = {}
    cols = list(header)
    for name, spec in FEATURES.items():
        hit = next((h for h in spec.exact if h in cols), None)
        if hit:
            res[name] = dict(status="exact", raw=hit)
            continue
        conv = next(((h, m, why) for h, m, why in spec.conversions if h in cols), None)
        if conv:
            res[name] = dict(status="converted", raw=conv[0], factor=conv[1], rationale=conv[2])
            continue
        variants = []
        for c in cols:
            m = _UNIT_RE.match(c)
            if m and m.group("stem").strip().lower() == spec.stem.lower():
                variants.append((c, m.group("unit").strip()))
        blank = [c for c, u in variants if u == ""]
        if blank:
            res[name] = dict(status="blank_unit", raw=blank[0], note="unit missing in header")
        elif variants:
            res[name] = dict(status="bad_unit", raw=variants[0][0],
                             note=f"unit '{variants[0][1]}' is not verifiably convertible to {spec.unit}")
        else:
            res[name] = dict(status="absent")
    return res


def target_status(header: list[str]) -> str:
    if C.TARGET_RAW in header:
        return "ok"
    pm = [h for h in header if h.upper().startswith("PM2")]
    return "unit_mismatch" if pm else "absent"
