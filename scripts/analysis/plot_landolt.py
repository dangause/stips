#!/usr/bin/env python
"""Generate Landolt validation plots from analysis/landolt_validation_4nights.csv.

Produces two figures used in the AAS poster + assessment doc:

    analysis/landolt_residuals.png    — per-band residual bar chart
    analysis/landolt_color_terms.png  — residual vs B-V with linear fits

Drops a single |residual| >= 2 mag outlier (a known V-band source-match
failure on SA 110-340 visit 90151051).
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "analysis" / "landolt_validation_4nights.csv"
OUT_DIR = REPO_ROOT / "analysis"

BANDS = ["b", "v", "r", "i"]
BAND_COLORS = {"b": "#1f77b4", "v": "#2ca02c", "r": "#d62728", "i": "#8c564b"}
BAND_LABELS = {"b": "B", "v": "V", "r": "R", "i": "I"}
OUTLIER_THRESHOLD = 2.0


def load_rows():
    with open(CSV_PATH) as fh:
        return list(csv.DictReader(fh))


def filter_outliers(rows):
    return [r for r in rows if abs(float(r["residual"])) < OUTLIER_THRESHOLD]


def plot_residuals(rows, out_path: Path) -> None:
    """Two-panel figure: per-band mean bar chart + individual measurements scatter.

    Matches the style of cell 15 in analysis/calibration_assessment.ipynb.
    Shows bar means with stat labels (left) and the individual residuals for
    every measurement colored by band (right), so the per-band spread is
    visible alongside the summary.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: per-band mean bar chart
    ax = axes[0]
    means, stds, ns = [], [], []
    for band in BANDS:
        brows = [r for r in rows if r["band"] == band]
        resids = [float(r["residual"]) for r in brows]
        means.append(float(np.mean(resids)) if resids else 0.0)
        stds.append(float(np.std(resids, ddof=1)) if len(resids) > 1 else 0.0)
        ns.append(len(resids))

    bars = ax.bar(
        [BAND_LABELS[b] for b in BANDS],
        means,
        yerr=stds,
        capsize=5,
        color=[BAND_COLORS[b] for b in BANDS],
        alpha=0.85,
        edgecolor="black",
    )
    ax.axhline(0, color="black", lw=1)
    ax.set_ylabel("Residual (pipeline − Landolt) [mag]")
    ax.set_xlabel("Band")
    ax.set_title("Per-Band Photometric Offset")

    # Annotate bars with the mean residual just outside the error bar
    for bar, m, s in zip(bars, means, stds):
        y = m + (s + 0.04) * (1 if m >= 0 else -1)
        va = "bottom" if m >= 0 else "top"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            f"{m:+.3f}",
            ha="center",
            va=va,
            fontsize=11,
            fontweight="bold",
        )

    # Right: individual measurements as a per-band scatter (jittered)
    ax = axes[1]
    rng = np.random.default_rng(seed=42)
    for band in BANDS:
        brows = [r for r in rows if r["band"] == band]
        resids = [float(r["residual"]) for r in brows]
        x = BANDS.index(band) + rng.uniform(-0.15, 0.15, size=len(resids))
        ax.scatter(
            x,
            resids,
            color=BAND_COLORS[band],
            s=55,
            alpha=0.8,
            edgecolor="black",
            lw=0.5,
            label=f"{BAND_LABELS[band]} (N={len(resids)})",
        )
    ax.set_xticks(range(len(BANDS)))
    ax.set_xticklabels([BAND_LABELS[b] for b in BANDS])
    ax.axhline(0, color="black", lw=1)
    ax.set_ylabel("Residual (mag)")
    ax.set_xlabel("Band")
    ax.set_title("Individual Measurements")
    ax.legend(fontsize=10, loc="best", framealpha=0.85)

    fig.suptitle(
        "Landolt Photometric Validation: Pipeline vs. Published Magnitudes",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def linfit(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float]:
    """Linear least-squares fit returning (slope, intercept, rms)."""
    if len(xs) < 2:
        return float("nan"), float("nan"), float("nan")
    slope, intercept = np.polyfit(xs, ys, 1)
    rms = float(np.sqrt(np.mean((ys - (slope * xs + intercept)) ** 2)))
    return float(slope), float(intercept), rms


def plot_color_terms(rows, out_path: Path) -> None:
    """4-panel residual vs B-V with per-band linear fit and star labels.

    Matches the style of cell 17 in analysis/calibration_assessment.ipynb.
    Adds a short star label next to each point (e.g. "1530+057") so the
    reader can see which specific Landolt standard drives each fit's outliers.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    bv_range = np.linspace(-0.3, 1.85, 100)

    for idx, band in enumerate(BANDS):
        ax = axes[idx // 2][idx % 2]
        brows = [r for r in rows if r["band"] == band]
        bv = np.array([float(r["color_BV"]) for r in brows], float)
        resids = np.array([float(r["residual"]) for r in brows], float)

        ax.axhline(0, color="black", linestyle="--", alpha=0.5, lw=0.5)
        ax.scatter(
            bv,
            resids,
            color=BAND_COLORS[band],
            s=55,
            edgecolor="black",
            lw=0.5,
            alpha=0.85,
            zorder=3,
        )

        if len(bv) >= 2:
            slope, intercept, fit_rms = linfit(bv, resids)
            ax.plot(
                bv_range,
                slope * bv_range + intercept,
                color=BAND_COLORS[band],
                lw=1.5,
                linestyle="--",
                alpha=0.7,
                label=f"slope = {slope:+.3f} mag/mag",
            )
            ax.legend(fontsize=10, loc="best")

        # Annotate every point with a short star label
        for r in brows:
            star_short = r["star"].split()[-1]  # "PG 1530+057" -> "1530+057"
            ax.annotate(
                star_short,
                (float(r["color_BV"]), float(r["residual"])),
                fontsize=7,
                alpha=0.7,
                xytext=(5, 5),
                textcoords="offset points",
            )

        ax.set_ylabel("Residual (mag)")
        ax.set_title(f"{BAND_LABELS[band]} band", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.3)

        if band in ("b", "v"):
            yspan = max(0.5, float(np.abs(resids).max()) * 1.2)
            ax.set_ylim(-yspan, yspan)

    axes[1][0].set_xlabel("B−V (Landolt)")
    axes[1][1].set_xlabel("B−V (Landolt)")

    fig.suptitle(
        "Residual vs. B−V Color: Nickel-to-Landolt Color Terms",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main() -> None:
    rows = filter_outliers(load_rows())
    print(f"Loaded {len(rows)} measurements (after outlier filter)")
    plot_residuals(rows, OUT_DIR / "landolt_residuals.png")
    plot_color_terms(rows, OUT_DIR / "landolt_color_terms.png")


if __name__ == "__main__":
    main()
