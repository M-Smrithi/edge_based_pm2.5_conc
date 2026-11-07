"""Figures and tables computed from saved experiment/model artifacts only (no numbers are typed in)."""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core import experiments as E

INK, MUTED, GRID = "#1d2433", "#6b7385", "#e6e9f0"
COL = {"random": "#2f6fed", "consecutive": "#e8833a"}
LS = {"temporal": "-", "spatial": "--"}
SETNAME = {"temporal": "Temporal test (known stations, later period)", "spatial": "Spatial test (unseen stations)"}


def _style():
    plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "axes.grid": True, "grid.color": GRID,
                         "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                         "axes.titlesize": 11, "axes.titleweight": "bold", "legend.frameon": False, "savefig.dpi": 160})


def load_summary(exp_dir: Path):
    res = json.loads((Path(exp_dir) / "results.json").read_text())
    return res, pd.DataFrame(E.summarise(res))


def results_table(exp_dir: Path) -> pd.DataFrame:
    _, s = load_summary(exp_dir)
    out = s.rename(columns={"test_set": "test_set", "missing_rate": "added_missing_rate"})
    return out[["test_set", "added_missing_rate", "pattern", "n_trials", "mae", "mae_std", "rmse", "rmse_std", "r2", "r2_std",
                "mae_increase_pct", "rmse_increase_pct", "n"]]


def make_figures(exp_dir: Path, model_dir: Path | None = None) -> list[str]:
    _style()
    exp_dir = Path(exp_dir); fig_dir = exp_dir / "figures"; fig_dir.mkdir(exist_ok=True)
    res, s = load_summary(exp_dir); made = []
    sets = [x for x in ("temporal", "spatial") if x in set(s.test_set)]

    def lines(ax, metric, pct=False):
        for ts in sets:
            for pat in ("random", "consecutive"):
                d = s[(s.test_set == ts) & (s.pattern == pat)].sort_values("missing_rate")
                z = s[(s.test_set == ts) & (s.missing_rate == 0)]
                d = pd.concat([z, d])
                x = d.missing_rate * 100
                y = d[metric + "_increase_pct"] if pct else d[metric]
                err = None if pct else d[metric + "_std"]
                ax.errorbar(x, y, yerr=err, color=COL[pat], ls=LS[ts], marker="o", ms=4, capsize=3, lw=1.8,
                            label=f"{pat.capitalize()} · {ts}")
        ax.set_xticks(sorted({0, *(s.missing_rate * 100)})); ax.set_xlabel("Artificially missing input readings (%)")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for a, m in zip(ax, ("mae", "rmse")):
        lines(a, m); a.set_ylabel(f"{m.upper()} (µg/m³)"); a.set_title(f"{m.upper()} vs missing readings")
    ax[1].legend(fontsize=8); fig.tight_layout(); fig.savefig(fig_dir / "error_vs_missingness.png"); plt.close(fig); made.append("error_vs_missingness.png")

    fig, ax = plt.subplots(figsize=(6.4, 4)); lines(ax, "rmse", pct=True)
    ax.set_ylabel("RMSE increase over 0% (%)"); ax.set_title("Relative error increase"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(fig_dir / "error_increase.png"); plt.close(fig); made.append("error_increase.png")

    fig, ax = plt.subplots(1, len(sets), figsize=(5.4 * len(sets), 4), squeeze=False)
    for a, ts in zip(ax[0], sets):
        d = s[(s.test_set == ts) & (s.missing_rate > 0)]
        rates = sorted(d.missing_rate.unique()); w = 0.36
        for i, pat in enumerate(("random", "consecutive")):
            dd = d[d.pattern == pat].sort_values("missing_rate")
            a.bar(np.arange(len(rates)) + (i - .5) * w, dd.rmse, w, yerr=dd.rmse_std, capsize=3, color=COL[pat], label=pat.capitalize())
        base = float(s[(s.test_set == ts) & (s.missing_rate == 0)].rmse.iloc[0]); a.axhline(base, color=MUTED, ls=":", lw=1.2)
        a.text(0.02, base, " 0% reference", color=MUTED, fontsize=8, va="bottom", transform=a.get_yaxis_transform())
        a.set_xticks(range(len(rates))); a.set_xticklabels([f"{int(r*100)}%" for r in rates]); a.set_ylabel("RMSE (µg/m³)")
        a.set_title(SETNAME[ts].split(" (")[0] + ": random vs consecutive"); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(fig_dir / "random_vs_consecutive.png"); plt.close(fig); made.append("random_vs_consecutive.png")

    lat = res.get("latency", [])
    if lat:
        lab = [("0%" if l["missing_rate"] == 0 else f"{int(l['missing_rate']*100)}% {l['pattern'][:4]}.") for l in lat]
        fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
        ax[0].bar(lab, [l["preprocess"]["median"] for l in lat], color="#2f6fed"); ax[0].set_title("Preprocessing latency (median)"); ax[0].set_ylabel("ms / record")
        ax[1].bar(lab, [l["inference"]["median"] for l in lat], color="#e8833a"); ax[1].set_title("Inference latency (median)"); ax[1].set_ylabel("ms / record")
        for a in ax: a.tick_params(axis="x", labelsize=8)
        fig.tight_layout(); fig.savefig(fig_dir / "latency.png"); plt.close(fig); made.append("latency.png")

    smp = res.get("samples", {})
    key = next((k for k in smp if k.startswith("temporal|0.0")), None) or next(iter(smp), None)
    key2 = next((k for k in smp if k.startswith("temporal|0.2")), None)
    if key:
        fig, ax = plt.subplots(1, 2 if key2 else 1, figsize=(10.5 if key2 else 5.2, 4.6), squeeze=False)
        for a, k, t in zip(ax[0], [key, key2], ["0% added missing", "20% added missing (random)"]):
            if not k: continue
            y, p = np.array(smp[k]["y"]), np.array(smp[k]["p"]); lim = max(np.percentile(y, 99.5), np.percentile(p, 99.5))
            a.hexbin(y, p, gridsize=45, extent=(0, lim, 0, lim), cmap="Blues", mincnt=1, bins="log")
            a.plot([0, lim], [0, lim], color=INK, lw=1, ls="--"); a.set_xlim(0, lim); a.set_ylim(0, lim)
            a.set_xlabel("Actual PM2.5 (µg/m³)"); a.set_ylabel("Predicted PM2.5 (µg/m³)"); a.set_title(f"Actual vs predicted · {t}")
        fig.tight_layout(); fig.savefig(fig_dir / "actual_vs_predicted.png"); plt.close(fig); made.append("actual_vs_predicted.png")
        fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
        for k, t, c in [(key, "0% added", "#2f6fed"), (key2, "20% added (random)", "#e8833a")]:
            if not k: continue
            y, p = np.array(smp[k]["y"]), np.array(smp[k]["p"]); r = p - y
            ax[0].hist(r, bins=np.linspace(-150, 150, 61), alpha=.55, color=c, label=t)
            ax[1].scatter(p, r, s=3, alpha=.25, color=c)
        ax[0].set_xlabel("Residual = predicted − actual (µg/m³)"); ax[0].set_ylabel("Records"); ax[0].set_title("Residual distribution"); ax[0].legend(fontsize=8)
        ax[1].axhline(0, color=INK, lw=1); ax[1].set_xlabel("Predicted (µg/m³)"); ax[1].set_ylabel("Residual (µg/m³)"); ax[1].set_title("Residuals vs predicted")
        fig.tight_layout(); fig.savefig(fig_dir / "residuals.png"); plt.close(fig); made.append("residuals.png")

    if model_dir and (Path(model_dir) / "metrics.json").exists():
        c = json.loads((Path(model_dir) / "metrics.json").read_text())["candidates"]
        names = [x["name"].replace("_", " ") for x in c]; sel = json.loads((Path(model_dir) / "metrics.json").read_text())["selected"]
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        cols = ["#2f6fed" if x["name"] == sel else "#c5ccdb" for x in c]
        ax[0].barh(names, [x["val"]["rmse"] for x in c], color=cols); ax[0].set_title("Validation RMSE (selection set)"); ax[0].set_xlabel("µg/m³"); ax[0].invert_yaxis()
        ax[1].barh(names, [x["latency_ms"] for x in c], color=cols); ax[1].set_title("Single-record latency"); ax[1].set_xlabel("ms"); ax[1].invert_yaxis()
        fig.tight_layout(); fig.savefig(fig_dir / "model_comparison.png"); plt.close(fig); made.append("model_comparison.png")
    table = results_table(exp_dir); table.to_csv(exp_dir / "results_table.csv", index=False)
    return made
