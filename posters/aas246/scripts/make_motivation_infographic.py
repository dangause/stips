#!/usr/bin/env python
"""Generate Panel 1 motivation infographic.

Two-row stat callout: large numbers + short captions framing the gap STIPS
addresses. No telescope photo. No decorative graphics. Read at poster scale.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = Path(__file__).resolve().parents[1] / "assets" / "panel1_motivation.png"


def main() -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Top callout
    ax.add_patch(Rectangle((0.5, 5.5), 9.0, 3.7, facecolor="#fef3c7",
                            edgecolor="#92400e", linewidth=1.5))
    ax.text(5.0, 8.0, "5+ decades", ha="center", va="center",
            fontsize=52, color="#92400e", fontweight="bold")
    ax.text(5.0, 6.4, "of archival 1-m imaging across professional observatories",
            ha="center", va="center", fontsize=14, color="#451a03")

    # Bottom callout
    ax.add_patch(Rectangle((0.5, 0.8), 9.0, 3.7, facecolor="#fee2e2",
                            edgecolor="#991b1b", linewidth=1.5))
    ax.text(5.0, 3.3, "0", ha="center", va="center",
            fontsize=80, color="#991b1b", fontweight="bold")
    ax.text(5.0, 1.7, "actively maintained, LSST-quality reduction pipelines",
            ha="center", va="center", fontsize=14, color="#450a0a")

    fig.savefig(OUT, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
