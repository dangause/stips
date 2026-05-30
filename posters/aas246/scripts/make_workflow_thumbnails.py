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
    "transients": Path(
        "/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv"
    ),
    "exoplanets": Path(
        "/Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv"
    ),
    "variables": Path(
        "/Users/dangause/Developer/lick/lsst/data/nickel/cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv"
    ),
    # Extended objects: TBD — handled in Task 9
}

BAND_COLOR = {"r": "#d62728", "i": "#8c564b", "b": "#1f77b4", "v": "#2ca02c"}

P_CY_AQR_DAYS = 0.061038  # known fundamental period


def load_csv(path: Path) -> list[dict] | None:
    if not path.exists():
        print(f"[warn] missing CSV: {path}")
        return None
    return list(csv.DictReader(open(path)))


def thumb_transients(out: Path) -> None:
    rows = load_csv(LC_PATHS["transients"])
    if not rows:
        return
    rows = [
        r
        for r in rows
        if r.get("mag") and r["mag"].lower() != "nan" and float(r.get("snr") or 0) >= 5
    ]
    fig, ax = plt.subplots(figsize=(5, 5))
    for band in ["r", "i"]:
        pts = [r for r in rows if r["band"] == band]
        x = [float(r["days_since_explosion"]) for r in pts]
        y = [float(r["mag"]) for r in pts]
        ax.scatter(
            x,
            y,
            s=20,
            color=BAND_COLOR[band],
            edgecolor="black",
            lw=0.4,
            label=f"{band.upper()} (N={len(pts)})",
            alpha=0.85,
        )
    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion")
    ax.set_ylabel("AB magnitude")
    ax.set_title(
        "Transients (DIA)\nSN 2023ixf early plateau", fontsize=12, fontweight="bold"
    )
    ax.legend(fontsize=9, loc="lower right", framealpha=0.85)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


def thumb_exoplanets(out: Path) -> None:
    rows = load_csv(LC_PATHS["exoplanets"])
    if not rows:
        return
    # Filter to B band (HD 189733 was observed in B)
    pts = [
        r
        for r in rows
        if r.get("band", "").lower() == "b"
        and r.get("flux")
        and r["flux"].lower() != "nan"
    ]
    if not pts:
        print("[warn] no usable rows for exoplanets thumbnail")
        return
    fig, ax = plt.subplots(figsize=(5, 5))
    mjd = np.array([float(r["mjd"]) for r in pts])
    # Center on the transit (use median MJD as t0 approximation)
    t0 = np.median(mjd)
    t_hours = (mjd - t0) * 24.0
    y = np.array([float(r["flux"]) for r in pts])
    y = y / np.median(y)  # normalize to median
    ax.scatter(t_hours, y, s=8, color="#1f77b4", alpha=0.6)
    ax.set_xlabel("Time from transit center (hours)")
    ax.set_ylabel("Relative flux")
    ax.set_title(
        "Exoplanets\nHD 189733 b transit (differential phot)",
        fontsize=12,
        fontweight="bold",
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


def thumb_variables(out: Path) -> None:
    rows = load_csv(LC_PATHS["variables"])
    if not rows:
        return
    pts = [
        r
        for r in rows
        if r.get("band", "").lower() == "v"
        and r.get("mag")
        and r["mag"].lower() != "nan"
        and float(r.get("snr") or 0) >= 5
    ]
    if not pts:
        print("[warn] no usable rows for variables thumbnail")
        return
    mjd = np.array([float(r["mjd"]) for r in pts])
    mag = np.array([float(r["mag"]) for r in pts])
    phase = ((mjd - mjd.min()) % P_CY_AQR_DAYS) / P_CY_AQR_DAYS

    fig, ax = plt.subplots(figsize=(5, 5))
    # Plot two periods for clarity
    ax.scatter(phase, mag, s=8, color="#2ca02c", alpha=0.6)
    ax.scatter(phase + 1, mag, s=8, color="#2ca02c", alpha=0.6)
    ax.invert_yaxis()
    ax.set_xlabel("Phase (P = 0.061 d)")
    ax.set_ylabel("V (AB mag)")
    ax.set_title("Variable stars\nCY Aqr period folded", fontsize=12, fontweight="bold")
    ax.set_xlim(0, 2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


def thumb_extended_objects(out: Path) -> None:
    """Stylized panel listing supported extended-object filters.

    Fallback for the extended-objects workflow thumbnail: the extended_objects
    butler repo only contains raw frames, no calibrated outputs to render as
    a deep image. We instead present the supported filter set as a card.
    """
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Title
    ax.text(
        5,
        9.0,
        "Extended objects",
        ha="center",
        va="center",
        fontsize=18,
        fontweight="bold",
        color="#1f2937",
    )
    ax.text(
        5,
        8.0,
        "Narrowband + Sloan workflows",
        ha="center",
        va="center",
        fontsize=11,
        color="#4b5563",
    )

    # Filter chips
    filters = [
        ("Hα", "#ef4444"),
        ("[O III]", "#06b6d4"),
        ("g′", "#22c55e"),
        ("r′", "#f59e0b"),
    ]
    chip_w, chip_h = 2.0, 1.2
    chip_y = 5.0
    total_w = len(filters) * chip_w + (len(filters) - 1) * 0.3
    start_x = (10 - total_w) / 2
    for i, (label, color) in enumerate(filters):
        x = start_x + i * (chip_w + 0.3)
        ax.add_patch(
            plt.Rectangle(
                (x, chip_y),
                chip_w,
                chip_h,
                facecolor=color,
                alpha=0.85,
                edgecolor="black",
                linewidth=1.2,
            )
        )
        ax.text(
            x + chip_w / 2,
            chip_y + chip_h / 2,
            label,
            ha="center",
            va="center",
            fontsize=14,
            fontweight="bold",
            color="white",
        )

    # Bottom caption
    ax.text(
        5,
        2.8,
        "Galaxies · H II regions · planetary nebulae",
        ha="center",
        va="center",
        fontsize=12,
        color="#4b5563",
        style="italic",
    )
    ax.text(
        5,
        1.6,
        "ISR → photometric calibration → multi-filter stacks",
        ha="center",
        va="center",
        fontsize=10,
        color="#6b7280",
    )

    fig.savefig(out, dpi=200, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    thumb_transients(OUT_DIR / "panel6_transients.png")
    thumb_exoplanets(OUT_DIR / "panel6_exoplanets.png")
    thumb_variables(OUT_DIR / "panel6_variables.png")
    thumb_extended_objects(OUT_DIR / "panel6_extended_objects.png")


if __name__ == "__main__":
    main()
