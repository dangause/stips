#!/usr/bin/env python
"""Compare Nickel DIA lightcurves to ZTF (ALeRCE) photometry.

Pulls the public ALeRCE/ZTF lightcurves for SN 2023ixf (ZTF23aaklqou) and
SN 2020wnt (ZTF20acjeflr), filters to real detections (rb > 0.5), and overlays
them with the Nickel R/I points. Writes a two-panel figure to
analysis/sn_vs_ztf_comparison.png.

Bands:
  Nickel:  r (Cousins R), i (Cousins I), v (where present)
  ZTF:     fid=1 -> g (AB), fid=2 -> r (AB)

Cousins R and ZTF r differ by a small color term (~0.02-0.05 mag for typical
SNe), so overlap regions should agree at ~0.1 mag absent filter mismatch.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "analysis" / "sn_vs_ztf_comparison.png"

NICKEL_PATHS = {
    "SN 2023ixf": Path("/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv"),
    "SN 2020wnt": Path("/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_ps1_022226_repo/lightcurves/lightcurve_2020wnt.csv"),
}
EXPLOSION_MJD = {"SN 2023ixf": 60082.75, "SN 2020wnt": 59180.0}
ZTF_OIDS = {"SN 2023ixf": "ZTF23aaklqou", "SN 2020wnt": "ZTF20acjeflr"}

# ZTF: fid=1 -> g, fid=2 -> r
ZTF_BAND = {1: "g", 2: "r"}
ZTF_COLOR = {"g": "#2ca02c", "r": "#d62728"}
NICKEL_COLOR = {"r": "#d62728", "i": "#8c564b", "v": "#2ca02c"}

CACHE_DIR = Path("/tmp/alerce_cache")
CACHE_DIR.mkdir(exist_ok=True)


def fetch_ztf(oid: str) -> list[dict]:
    cache = CACHE_DIR / f"{oid}.json"
    if not cache.exists():
        url = f"https://api.alerce.online/ztf/v1/objects/{oid}/lightcurve"
        subprocess.run(["curl", "-sL", url, "-o", str(cache)], check=True)
    return json.loads(cache.read_text())["detections"]


def load_nickel(path: Path) -> list[dict]:
    return list(csv.DictReader(open(path)))


def plot_one(ax, sn: str) -> None:
    explosion = EXPLOSION_MJD[sn]
    oid = ZTF_OIDS[sn]

    # --- ZTF detections (rb > 0.5) ---
    ztf = [d for d in fetch_ztf(oid) if d.get("rb") and d["rb"] > 0.5]
    for fid in (1, 2):
        band = ZTF_BAND[fid]
        pts = [d for d in ztf if d["fid"] == fid and d.get("magpsf")]
        if not pts:
            continue
        x = np.array([d["mjd"] - explosion for d in pts])
        y = np.array([d["magpsf"] for d in pts])
        e = np.array([d.get("sigmapsf") or 0 for d in pts])
        ax.errorbar(
            x, y, yerr=e,
            fmt="o", markersize=3.5, mfc="white",
            color=ZTF_COLOR[band], lw=0, elinewidth=0.6,
            ecolor=ZTF_COLOR[band], alpha=0.7,
            label=f"ZTF {band} (N={len(pts)})",
        )

    # --- Nickel DIA points ---
    nickel = load_nickel(NICKEL_PATHS[sn])
    # drop rows without a valid magnitude (e.g. zero/negative diff flux)
    # and low-S/N noise points that don't represent real detections
    nickel = [
        r for r in nickel
        if r.get("mag") and r["mag"].lower() != "nan"
        and r.get("mag_err") and r["mag_err"].lower() != "nan"
        and float(r.get("snr") or 0) >= 5.0
    ]
    bands_seen = sorted({r["band"] for r in nickel})
    for band in bands_seen:
        pts = [r for r in nickel if r["band"] == band]
        x = np.array([float(r["days_since_explosion"]) for r in pts])
        y = np.array([float(r["mag"]) for r in pts])
        e = np.array([float(r["mag_err"]) for r in pts])
        ax.errorbar(
            x, y, yerr=e,
            fmt="s", markersize=4.5,
            color=NICKEL_COLOR.get(band, "black"),
            mec="black", mew=0.4, lw=0,
            elinewidth=0.6, ecolor=NICKEL_COLOR.get(band, "black"),
            alpha=0.95,
            label=f"Nickel {band.upper()} (N={len(pts)})",
        )

    # --- Quantitative R-band agreement (Nickel R vs ZTF r), nearest neighbour
    # in time, within 3 days. Reports mean residual + RMS as a single number
    # in the panel for the poster.
    nickel_r = [r for r in nickel if r["band"] == "r"]
    ztf_r = [d for d in ztf if d["fid"] == 2 and d.get("magpsf")]
    residuals = []
    for nr in nickel_r:
        nt = float(nr["days_since_explosion"])
        nm = float(nr["mag"])
        # nearest ZTF r in time
        best = min(
            (d for d in ztf_r), key=lambda d: abs((d["mjd"] - explosion) - nt),
            default=None,
        )
        if best is None:
            continue
        dt = abs((best["mjd"] - explosion) - nt)
        if dt > 3.0:
            continue
        residuals.append(nm - best["magpsf"])
    if residuals:
        arr = np.array(residuals)
        agree = (
            f"Nickel R − ZTF r (within 3 days):\n"
            f"N={len(arr)},  mean={arr.mean():+.3f},  RMS={float(np.sqrt((arr**2).mean())):.3f} mag"
        )
    else:
        agree = (
            "Nickel R − ZTF r:\n"
            "no overlap (ZTF r starts after\nNickel campaign ended)"
        )
    ax.text(
        0.02, 0.97, agree,
        transform=ax.transAxes, fontsize=9, va="top",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.85),
    )

    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion")
    ax.set_ylabel("AB magnitude")
    ax.set_title(f"{sn}  —  Nickel DIA vs ZTF (ALeRCE)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="lower right", framealpha=0.9, ncol=2)


def main() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    plot_one(axes[0], "SN 2023ixf")
    plot_one(axes[1], "SN 2020wnt")
    fig.suptitle(
        "Nickel DIA lightcurves vs ZTF (ALeRCE) — filled squares = Nickel, open circles = ZTF",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_PATH, dpi=150)
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
