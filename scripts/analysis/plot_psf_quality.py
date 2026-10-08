#!/usr/bin/env python
"""Generate poster-size PSF-quality figure across science cases.

Two panels: PSF FWHM (arcsec) and PSF-model star count (nPsfStar). Same
target ordering and colours as the astrometric-precision poster, sized
for poster legibility.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_data  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = paper_data.data("calib_metrics", "combined.csv")
OUT_PATH = paper_data.figure("psf_quality_poster.png")

NICKEL_PIXEL_ARCSEC = 0.37
SIGMA_TO_FWHM = 2.355

TARGETS = [
    ("2020wnt", "SN 2020wnt", "#2ecc71"),
    ("2023ixf", "SN 2023ixf", "#e74c3c"),
    ("hd189733", "HD 189733", "#3498db"),
    ("ac_and", "AC And", "#9b59b6"),
    ("extended_objects", "Extended\nobjects", "#f39c12"),
]


def to_float(val: str) -> float | None:
    if val in (None, "", "nan", "NaN"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def collect(rows, target, column, transform=lambda v: v):
    out = []
    for r in rows:
        if r["target"] != target:
            continue
        v = to_float(r.get(column))
        if v is None:
            continue
        out.append(transform(v))
    return out


def style_boxes(bp, colors):
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
        patch.set_edgecolor("black")


def main() -> None:
    rows = list(csv.DictReader(open(CSV_PATH)))

    fwhm_data, npsf_data, labels, colors = [], [], [], []
    for target, label, color in TARGETS:
        # PSF FWHM in arcsec: sigma_px × pixel_scale × 2.355
        fwhms = collect(
            rows,
            target,
            "psfSigma",
            transform=lambda s: s * NICKEL_PIXEL_ARCSEC * SIGMA_TO_FWHM,
        )
        npsf = collect(rows, target, "nPsfStar")
        if not fwhms or not npsf:
            continue
        fwhm_data.append(fwhms)
        npsf_data.append(npsf)
        labels.append(f"{label}\nN={len(fwhms)}")
        colors.append(color)

    fig, axes = plt.subplots(1, 2, figsize=(22, 10))

    # ── Left: PSF FWHM (arcsec) ──────────────────────────────────────
    ax = axes[0]
    bp = ax.boxplot(
        fwhm_data,
        tick_labels=labels,
        patch_artist=True,
        widths=0.6,
        showfliers=False,
        medianprops=dict(color="black", lw=2.2),
        whiskerprops=dict(lw=1.8),
        capprops=dict(lw=1.8),
        boxprops=dict(lw=1.5),
    )
    style_boxes(bp, colors)
    ax.set_ylabel("PSF FWHM (arcsec)", fontsize=28)
    ax.set_title("Seeing", fontsize=30, fontweight="bold")
    ax.tick_params(axis="x", labelsize=20)
    ax.tick_params(axis="y", labelsize=22)
    ax.grid(True, axis="y", alpha=0.3)

    # ── Right: nPsfStar (PSF-model star count) ──────────────────────
    ax = axes[1]
    bp = ax.boxplot(
        npsf_data,
        tick_labels=labels,
        patch_artist=True,
        widths=0.6,
        showfliers=False,
        medianprops=dict(color="black", lw=2.2),
        whiskerprops=dict(lw=1.8),
        capprops=dict(lw=1.8),
        boxprops=dict(lw=1.5),
    )
    style_boxes(bp, colors)
    ax.set_ylabel("nPsfStar (model star count)", fontsize=28)
    ax.set_title("PSF Model Stars", fontsize=30, fontweight="bold")
    ax.tick_params(axis="x", labelsize=20)
    ax.tick_params(axis="y", labelsize=22)
    ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "PSF Quality Across Science Cases",
        fontsize=34,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
