#!/usr/bin/env python
"""Plot zero point vs time, one panel per target, colored by band.

Tells the "photometric stability across the campaign" story for the poster.
Reads analysis/calib_metrics/combined.csv (multi-target output of
scripts/analysis/run_calib_metrics_batch.py) and writes
analysis/calib_metrics/zeropoint_vs_time.png.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "analysis" / "calib_metrics" / "combined.csv"
OUT_PATH = REPO_ROOT / "analysis" / "calib_metrics" / "zeropoint_vs_time.png"

# Band → color mapping. Sloan g/r and Cousins R distinct so the eye separates them.
BAND_COLORS = {
    "b": "#1f77b4",
    "v": "#2ca02c",
    "r": "#d62728",
    "i": "#8c564b",
    "halpha": "#e377c2",
    "oiii": "#17becf",
    "rp": "#ff7f0e",
    "gp": "#9467bd",
}
BAND_LABEL = {"b": "B", "v": "V", "r": "R", "i": "I", "halpha": "Hα",
              "oiii": "[O III]", "rp": "r'", "gp": "g'"}

TARGETS_ORDER = ["2023ixf", "2020wnt", "hd189733", "ac_and", "extended_objects"]
TARGET_TITLES = {
    "2023ixf": "SN 2023ixf (M101) — dense field",
    "2020wnt": "SN 2020wnt — sparse field",
    "hd189733": "HD 189733 — exoplanet transit",
    "ac_and": "AC Andromedae — variable star",
    "extended_objects": "Extended objects — galaxies/nebulae",
}


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_day(s: str) -> datetime | None:
    try:
        return datetime.strptime(str(int(float(s))), "%Y%m%d")
    except Exception:
        return None


def main() -> None:
    rows = list(csv.DictReader(open(CSV_PATH)))
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharey=False)
    axes = axes.flatten()

    for ax, target in zip(axes, TARGETS_ORDER):
        trows = [r for r in rows if r["target"] == target]
        bands_seen = []

        # Plot one band at a time so legend order is stable
        for band in BAND_COLORS:
            pts = [
                (parse_day(r["day_obs"]), to_float(r["zeroPoint"]))
                for r in trows
                if r["band"] == band
            ]
            pts = [(d, zp) for d, zp in pts if d is not None and zp is not None]
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.scatter(
                xs,
                ys,
                color=BAND_COLORS[band],
                edgecolor="black",
                lw=0.3,
                s=18,
                alpha=0.7,
                label=f"{BAND_LABEL[band]} (N={len(pts)})",
            )
            bands_seen.append(band)

        ax.set_title(f"{TARGET_TITLES[target]}  (N={len(trows)})", fontsize=10)
        ax.set_ylabel("Zero point (AB mag)")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(axis="x", labelrotation=30, labelsize=8)
        if bands_seen:
            ax.legend(fontsize=8, loc="best", framealpha=0.85)

    # Last panel: combined overlay across all targets
    ax = axes[5]
    for band in BAND_COLORS:
        pts = [
            (parse_day(r["day_obs"]), to_float(r["zeroPoint"]))
            for r in rows
            if r["band"] == band
        ]
        pts = [(d, zp) for d, zp in pts if d is not None and zp is not None]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.scatter(
            xs,
            ys,
            color=BAND_COLORS[band],
            edgecolor="black",
            lw=0.2,
            s=10,
            alpha=0.5,
            label=f"{BAND_LABEL[band]} (N={len(pts)})",
        )
    ax.set_title("All campaigns overlay  (N=1,457)", fontsize=10)
    ax.set_ylabel("Zero point (AB mag)")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    ax.legend(fontsize=8, loc="best", ncol=2, framealpha=0.85)

    fig.suptitle(
        "Photometric zero-point stability across the Nickel campaigns",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PATH, dpi=150)
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
