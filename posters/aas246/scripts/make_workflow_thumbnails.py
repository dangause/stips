#!/usr/bin/env python
"""Generate Panel 6 workflow thumbnails (4 mini figures for the showcase grid).

Each thumbnail is 5x5 inches at 200 dpi (~1000 px square) — designed to read
at the size of a small card inside the merged Panel 6 strip of the iPoster.

Data sources (all CSVs already on disk from prior pipeline runs):
  - Transients:      /Users/dangause/.../2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv
  - Exoplanets:      /Users/dangause/.../hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv
  - Variables:       /Users/dangause/.../cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv
  - Extended objs:   /Users/dangause/.../extended_objects/.../<TBD figure>

If a CSV path is missing, the script prints a warning and skips that thumbnail.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets"

LC_PATHS = {
    "transients": Path("/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv"),
    "exoplanets": Path("/Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv"),
    "variables":  Path("/Users/dangause/Developer/lick/lsst/data/nickel/cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv"),
    # Extended objects: TBD — handled in Task 9
}

BAND_COLOR = {"r": "#d62728", "i": "#8c564b", "b": "#1f77b4", "v": "#2ca02c"}


def load_csv(path: Path) -> list[dict] | None:
    if not path.exists():
        print(f"[warn] missing CSV: {path}")
        return None
    return list(csv.DictReader(open(path)))


def thumb_transients(out: Path) -> None:
    rows = load_csv(LC_PATHS["transients"])
    if not rows:
        return
    rows = [r for r in rows if r.get("mag") and r["mag"].lower() != "nan"
            and float(r.get("snr") or 0) >= 5]
    fig, ax = plt.subplots(figsize=(5, 5))
    for band in ["r", "i"]:
        pts = [r for r in rows if r["band"] == band]
        x = [float(r["days_since_explosion"]) for r in pts]
        y = [float(r["mag"]) for r in pts]
        ax.scatter(x, y, s=20, color=BAND_COLOR[band], edgecolor="black",
                    lw=0.4, label=f"{band.upper()} (N={len(pts)})", alpha=0.85)
    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion")
    ax.set_ylabel("AB magnitude")
    ax.set_title("Transients (DIA)\nSN 2023ixf early plateau",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right", framealpha=0.85)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    thumb_transients(OUT_DIR / "panel6_transients.png")


if __name__ == "__main__":
    main()
