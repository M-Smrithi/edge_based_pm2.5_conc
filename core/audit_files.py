"""Reproducible audit of every CSV in a directory.  Never modifies inputs.
Usage: python -m core.audit_files [DIR] [--out storage/audits]
Writes audit_<UTC>.json (machine-readable), audit_latest.json, audit_latest.md (human-readable), audit_latest.csv."""
from __future__ import annotations
import argparse, collections, json, platform, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import core.config as C
from core import ingest as I


def run_audit(src: Path, out: Path | None = None, info_path: Path | None = None) -> dict:
    src = Path(src)
    info = I.load_stations_info(info_path)
    files = sorted(p for p in src.iterdir() if p.is_file())
    results, by_hash = [], collections.defaultdict(list)
    for p in files:
        a = I.audit_file(p, info=info)
        results.append(a)
        by_hash[a["sha256"]].append(a["file_name"])
    dup_groups = {h: n for h, n in by_hash.items() if len(n) > 1}
    verdicts = collections.Counter(a["verdict"] for a in results)
    usable = [a for a in results if a["verdict"] in ("accepted", "accepted_recovered")]
    codes = [a["station"] for a in results if a["station"]]
    meta = dict(
        stations_info_path=str(info_path or C.STATIONS_INFO),
        stations_info_found=info is not None,
        stations_info_rows=None if info is None else int(len(info)),
        codes_verified=sum(1 for c in codes if info is not None and c in info.index),
        codes_total=len(codes),
        codes_unverified=[c for c in codes if info is None or c not in info.index],
    )
    summary = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source_dir=str(src), n_files=len(results), verdicts=dict(verdicts),
        usable_files=len(usable),
        usable_valid_rows=int(sum(a.get("valid_rows", 0) for a in usable)),
        usable_complete_case_rows=int(sum(a.get("complete_case_rows", 0) for a in usable)),
        byte_identical_groups=len(dup_groups),
        recoverable_with_review=int(verdicts.get("pending_review", 0)),
        unusable=int(verdicts.get("rejected", 0)),
        no_target=int(sum(1 for a in results if a.get("target_status") == "absent")),
        pending_with_unit_proposal=int(sum(1 for a in results if a["verdict"] == "pending_review" and a["proposals"])),
        environment=dict(python=platform.python_version(), pandas=pd.__version__, platform=platform.platform()),
        stations_info=meta,
    )
    doc = dict(summary=summary, byte_identical_groups=dup_groups, files=results)
    if out:
        out = Path(out); out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for name in (f"audit_{stamp}.json", "audit_latest.json"):
            (out / name).write_text(json.dumps(doc, indent=1, default=str))
        (out / "audit_latest.md").write_text(render_md(doc))
        rows = [dict(file=a["file_name"], station=a["station"], verdict=a["verdict"], rows=a.get("rows"),
                     valid_rows=a.get("valid_rows"), target_valid=a.get("target_valid"), ts_min=a.get("ts_min"),
                     ts_max=a.get("ts_max"), complete_case_rows=a.get("complete_case_rows"),
                     missing_sensors=";".join(a.get("structural_absence", [])), sha256=a["sha256"],
                     reason=" | ".join(a["reasons"])) for a in results]
        pd.DataFrame(rows).to_csv(out / "audit_latest.csv", index=False)
    return doc


def render_md(doc: dict) -> str:
    s, f = doc["summary"], doc["files"]
    L = [f"# Data audit\n", f"Generated {s['generated_utc']} from `{s['source_dir']}`.\n",
         "## Summary\n", f"| Item | Count |\n|---|---|", f"| Files audited | {s['n_files']} |"]
    for k, v in s["verdicts"].items():
        L.append(f"| Verdict `{k}` | {v} |")
    L += [f"| Usable files (accepted + recovered) | {s['usable_files']} |",
          f"| Usable valid rows (PM2.5 present, ≥1 sensor) | {s['usable_valid_rows']:,} |",
          f"| …of which complete-case (all 12 sensors) | {s['usable_complete_case_rows']:,} |",
          f"| Files lacking a PM2.5 target | {s['no_target']} |",
          f"| Pending review (sensor unavailable / unit unverified) | {s['recoverable_with_review']} |",
          f"| Byte-identical duplicate groups | {s['byte_identical_groups']} |", ""]
    m = s["stations_info"]
    L += ["## stations_info.csv", "", f"Found: **{m['stations_info_found']}** ({m['stations_info_path']}); rows: {m['stations_info_rows']}; "
          f"station codes verified against it: {m['codes_verified']}/{m['codes_total']}. "
          "Metadata is optional: without it stations are still processed, only state/city labels are unavailable.\n"]
    cat = {"accepted": "Usable as-is", "accepted_recovered": "Usable after verified header recovery (alias / SI unit conversion)",
           "pending_review": "Potentially recoverable — needs administrator decision", "rejected": "Unusable for supervised training"}
    for v, title in cat.items():
        sub = [a for a in f if a["verdict"] == v]
        L += [f"## {title} ({len(sub)})", ""]
        if not sub: L += ["_none_", ""]; continue
        L += ["| File | Rows | Valid rows | Period | Notes |", "|---|---|---|---|---|"]
        for a in sub:
            per = f"{str(a.get('ts_min',''))[:10]} → {str(a.get('ts_max',''))[:10]}"
            note = "; ".join(a["reasons"])[:160] or ("; ".join(f"{m['feature']}←{m['raw']}" for m in a.get("mapping_log", []))[:160])
            L.append(f"| {a['file_name']} | {a.get('rows','')} | {a.get('valid_rows','')} | {per} | {note} |")
        L.append("")
    if doc["byte_identical_groups"]:
        L += ["## Byte-identical files", ""] + [f"- `{h[:12]}…`: {', '.join(n)}" for h, n in doc["byte_identical_groups"].items()] + [""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default=str(C.INCOMING))
    ap.add_argument("--out", default=str(C.AUDITS))
    ns = ap.parse_args()
    d = run_audit(Path(ns.src), Path(ns.out))
    print(json.dumps(d["summary"], indent=1, default=str))
