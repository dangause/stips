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
    by_band = {b: [] for b in BANDS}
    for r in rows:
        by_band[r["band"]].append(float(r["residual"]))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    xs = np.arange(len(BANDS))
    means = [np.mean(by_band[b]) if by_band[b] else 0 for b in BANDS]
    stds = [np.std(by_band[b], ddof=1) if len(by_band[b]) > 1 else 0 for b in BANDS]
    counts = [len(by_band[b]) for b in BANDS]

    bars = ax.bar(
        xs,
        means,
        yerr=stds,
        color=[BAND_COLORS[b] for b in BANDS],
        edgecolor="black",
        capsize=6,
        alpha=0.85,
    )

    ax.axhline(0.0, color="black", linewidth=0.6, linestyle="--", alpha=0.5)

    # Pad y-limits to leave room for annotations above/below the error bars
    upper = max((m + s for m, s in zip(means, stds)), default=0)
    lower = min((m - s for m, s in zip(means, stds)), default=0)
    span = upper - lower if upper != lower else 1.0
    ax.set_ylim(lower - 0.3 * span, upper + 0.25 * span)

    for x, m, s, n in zip(xs, means, stds, counts):
        if m >= 0:
            label_y = m + s + 0.04 * span
            va = "bottom"
        else:
            label_y = m - s - 0.04 * span
            va = "top"
        ax.annotate(
            f"N={n}\n{m:+.3f}±{s:.3f}",
            (x, label_y),
            ha="center",
            va=va,
            fontsize=9,
        )

    ax.set_xticks(xs)
    ax.set_xticklabels([BAND_LABELS[b] for b in BANDS])
    ax.set_xlabel("Band")
    ax.set_ylabel("Pipeline − Landolt residual (mag)")
    ax.set_title(
        "Landolt photometric validation — per-band residuals\n"
        f"4 nights × 10 stars (B-V −0.19 to +1.74), 1 V-band outlier excluded"
    )
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
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
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    axes = axes.flatten()

    bv_range = np.linspace(-0.3, 1.85, 100)

    for ax, band in zip(axes, BANDS):
        xs = np.array(
            [float(r["color_BV"]) for r in rows if r["band"] == band], float
        )
        ys = np.array(
            [float(r["residual"]) for r in rows if r["band"] == band], float
        )

        ax.axhline(0.0, color="black", linewidth=0.5, linestyle="--", alpha=0.5)
        ax.scatter(
            xs,
            ys,
            color=BAND_COLORS[band],
            edgecolor="black",
            s=45,
            alpha=0.8,
            zorder=3,
        )

        slope, intercept, fit_rms = linfit(xs, ys)
        ax.plot(
            bv_range,
            slope * bv_range + intercept,
            color="black",
            linewidth=1.5,
            linestyle="-",
            alpha=0.7,
        )

        ax.set_title(
            f"{BAND_LABELS[band]} band  "
            f"(N={len(xs)},  slope={slope:+.3f},  intercept={intercept:+.3f},  "
            f"fit RMS={fit_rms:.3f})",
            fontsize=10,
        )
        ax.set_ylabel("Residual (mag)")
        ax.grid(True, alpha=0.3)

        if band in ("b", "v"):
            yspan = max(0.5, abs(ys).max() * 1.2)
            ax.set_ylim(-yspan, yspan)

    axes[2].set_xlabel("Landolt B − V color (mag)")
    axes[3].set_xlabel("Landolt B − V color (mag)")
    fig.suptitle(
        "Nickel-to-Landolt color terms — pipeline residual vs B−V\n"
        "Linear fit per band across full Landolt color range",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def main() -> None:
    rows = filter_outliers(load_rows())
    print(f"Loaded {len(rows)} measurements (after outlier filter)")
    plot_residuals(rows, OUT_DIR / "landolt_residuals.png")
    plot_color_terms(rows, OUT_DIR / "landolt_color_terms.png")


if __name__ == "__main__":
    main()
