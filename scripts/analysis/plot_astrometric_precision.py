#!/usr/bin/env python
"""Generate poster-size astrometric-precision box plot across science cases.

Reads per-visit calibration metrics from analysis/calib_metrics/combined.csv
and renders one box per target showing astromOffsetMean (mas) — the matching
RMS residual reported by calibrateImage.
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
OUT_PATH = REPO_ROOT / "analysis" / "astrometric_precision_poster.png"

# Display order + colour per target (matches the notebook's field_comparison
# panel — green = sparse SN, red = dense SN host, blue = exoplanet, etc.).
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


def main() -> None:
    rows = list(csv.DictReader(open(CSV_PATH)))
    data, labels, colors = [], [], []
    for target, label, color in TARGETS:
        # Drop degenerate-WCS rows (astromOffsetMean ~0 from zero-DOF fits).
        # Convert arcsec → mas.
        vals = [
            v * 1000.0
            for v in (
                to_float(r["astromOffsetMean"]) for r in rows if r["target"] == target
            )
            if v is not None and v >= 1e-6
        ]
        if not vals:
            continue
        data.append(vals)
        labels.append(f"{label}\nN={len(vals)}")
        colors.append(color)

    fig, ax = plt.subplots(figsize=(16, 10))

    bp = ax.boxplot(
        data,
        tick_labels=labels,
        patch_artist=True,
        widths=0.6,
        showfliers=False,
        medianprops=dict(color="black", lw=2.2),
        whiskerprops=dict(lw=1.8),
        capprops=dict(lw=1.8),
        boxprops=dict(lw=1.5),
    )
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
        patch.set_edgecolor("black")

    ax.set_ylabel("astromOffsetMean (mas)", fontsize=30)
    ax.set_title(
        "Astrometric Precision Across Science Cases", fontsize=34, fontweight="bold"
    )
    ax.tick_params(axis="x", labelsize=22)
    ax.tick_params(axis="y", labelsize=24)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
