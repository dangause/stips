#!/usr/bin/env python
"""Generate Panel 2 STIPS architecture diagram.

A horizontal layered block diagram suitable for the iPoster centerpiece:
  [Raw FITS] -> [Instrument plugins] -> [STIPS core] -> [LSST Science Pipelines] -> [Outputs]
plus callout strips below for supported instruments and execution environments.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parents[1] / "assets" / "panel2_architecture.png"


def block(ax, x, y, w, h, title, body, fc, ec):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=fc,
        edgecolor=ec,
        linewidth=1.5,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2,
        y + h * 0.72,
        title,
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color=ec,
    )
    ax.text(
        x + w / 2,
        y + h * 0.32,
        body,
        ha="center",
        va="center",
        fontsize=9.5,
        color="#1f2937",
    )


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=18,
            color="#374151",
            linewidth=1.5,
        )
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")

    # Main flow row (y centered around 4.5)
    block(
        ax,
        0.2,
        3.8,
        1.5,
        1.4,
        "Raw FITS",
        "per-night\nNickel /\nCTIO 0.9m",
        "#e5e7eb",
        "#374151",
    )
    block(
        ax,
        2.2,
        3.5,
        2.6,
        2.0,
        "Instrument plugins",
        "InstrumentPlugin\nformatter, translator,\nfilter map",
        "#fde68a",
        "#92400e",
    )
    block(
        ax,
        5.3,
        3.5,
        3.0,
        2.0,
        "STIPS core",
        "CLI · YAML configs ·\nButler ingest ·\nmulti-instrument abstraction",
        "#e0e7ff",
        "#3730a3",
    )
    block(
        ax,
        8.8,
        3.5,
        2.9,
        2.0,
        "LSST Science Pipelines",
        "calibrateImage · DIA ·\nforced photometry ·\nlightcurve extraction",
        "#dbeafe",
        "#1e3a8a",
    )
    block(
        ax,
        12.0,
        3.8,
        1.0,
        1.4,
        "Outputs",
        "calibrated\nimages, DIA,\nlightcurves",
        "#e5e7eb",
        "#374151",
    )

    # Arrows between blocks
    arrow(ax, 1.7, 4.5, 2.2, 4.5)
    arrow(ax, 4.8, 4.5, 5.3, 4.5)
    arrow(ax, 8.3, 4.5, 8.8, 4.5)
    arrow(ax, 11.7, 4.5, 12.0, 4.5)

    # Top callout — supported instruments
    block(
        ax,
        2.2,
        6.0,
        9.5,
        0.7,
        "Supported instruments",
        "Nickel (Lick)   ·   CTIO 0.9m   (new instruments: add an InstrumentPlugin)",
        "#fff7ed",
        "#9a3412",
    )

    # Bottom callout — execution environments
    block(
        ax,
        2.2,
        0.5,
        9.5,
        0.7,
        "Execution environments",
        "local   ·   Docker   ·   Slurm cluster via BPS / Parsl",
        "#ecfdf5",
        "#065f46",
    )

    # Title above the diagram
    ax.text(
        6.5,
        6.85,
        "STIPS — small-telescope abstraction over the LSST Science Pipelines",
        ha="center",
        va="bottom",
        fontsize=13.5,
        fontweight="bold",
        color="#111827",
    )

    fig.savefig(OUT, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
