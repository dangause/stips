#!/usr/bin/env python
"""Plot sky background vs zero point, colored by target.

Photometric nights cluster at low skyBg / high zeroPoint; non-photometric
(clouds, moon, high airmass) drift toward higher skyBg and lower zeroPoint.
This is suggested plot #5 from docs/calibration_metrics_assessment.md.

Writes analysis/calib_metrics/sky_vs_zeropoint.png.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "analysis" / "calib_metrics" / "combined.csv"
OUT_PATH = REPO_ROOT / "analysis" / "calib_metrics" / "sky_vs_zeropoint.png"

TARGETS = ["2023ixf", "2020wnt", "hd189733", "ac_and", "extended_objects"]
TARGET_COLORS = {
    "2023ixf": "#e74c3c",
    "2020wnt": "#2ecc71",
    "hd189733": "#3498db",
    "ac_and": "#9b59b6",
    "extended_objects": "#f39c12",
}
TARGET_LABELS = {
    "2023ixf": "SN 2023ixf",
    "2020wnt": "SN 2020wnt",
    "hd189733": "HD 189733",
    "ac_and": "AC And",
    "extended_objects": "Extended objects",
}


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    rows = list(csv.DictReader(open(CSV_PATH)))
    fig, ax = plt.subplots(figsize=(9, 6))

    for target in TARGETS:
        sky = []
        zp = []
        for r in rows:
            if r["target"] != target:
                continue
            s = to_float(r["skyBg"])
            z = to_float(r["zeroPoint"])
            if s is None or z is None or s <= 0:
                continue
            sky.append(s)
            zp.append(z)
        ax.scatter(
            zp,
            sky,
            color=TARGET_COLORS[target],
            edgecolor="black",
            lw=0.3,
            s=22,
            alpha=0.65,
            label=f"{TARGET_LABELS[target]} (N={len(zp)})",
        )

    ax.set_yscale("log")
    ax.set_xlabel("Zero point (AB mag)")
    ax.set_ylabel("Sky background (nJy / pixel, log scale)")
    ax.set_title(
        "Sky background vs. photometric zero point\n"
        "Photometric nights: high ZP + low sky. Cloudy/bright nights: low ZP + high sky."
    )
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=9, loc="lower left", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=150)
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
