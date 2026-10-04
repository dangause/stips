#!/usr/bin/env python
"""Generate poster-size 3-panel figure for SN 2023ixf — PS1-template DIA run.

Same layout as plot_2023ixf_raw_vs_reduced.py but on visit 85480107 (R-band,
20 s, night 20230527 / UT 20230528) processed with PS1 templates.

  raw → preliminary_visit_image → difference_image
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from astropy.visualization import (
    AsymmetricPercentileInterval,
    ImageNormalize,
    LogStretch,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_data  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "analysis" / "2023ixf_raw_pvi_diff_ps1_poster.png"

DATA_REPO = paper_data.repo("2023ixf")

# Visit 85480107 — SN 2023ixf, R-band, 20 s, night 20230527 (UT 20230528).
# The rebuild keeps this night unpruned (targets.yaml keep_nights).
RAW_FITS = paper_data.find_file(DATA_REPO, "raw_Nickel_R_20230528_107_*.fits")
PVI_FITS = paper_data.dataset_file(DATA_REPO, "preliminary_visit_image", 85480107)
DIFF_FITS = paper_data.dataset_file(DATA_REPO, "difference_image", 85480107)
SCIENCE_LABEL = "SN 2023ixf in M101 · Nickel R · 20 s · visit 85480107 · PS1 template"


def log_norm(
    arr: np.ndarray, lo_pct: float = 50.0, hi_pct: float = 99.7, a: float = 1000.0
):
    finite = arr[np.isfinite(arr)]
    vmin, vmax = AsymmetricPercentileInterval(lo_pct, hi_pct).get_limits(finite)
    return ImageNormalize(arr, vmin=vmin, vmax=vmax, stretch=LogStretch(a=a))


def main() -> None:
    for p in (RAW_FITS, PVI_FITS, DIFF_FITS):
        if not p.exists():
            raise SystemExit(f"missing FITS: {p}")

    raw = np.flipud(fits.getdata(RAW_FITS).astype(np.float32))
    pvi = fits.getdata(PVI_FITS, extname="IMAGE").astype(np.float32)
    dif = fits.getdata(DIFF_FITS, extname="IMAGE").astype(np.float32)

    # Clip diff negatives to zero so noise floor crushes to black (DS9-style).
    dif_disp = np.where(np.isfinite(dif), np.maximum(dif, 0.0), np.nan)

    fig, axes = plt.subplots(1, 3, figsize=(22, 8.5))
    panels = (
        (axes[0], raw, "raw", dict(lo_pct=50.0, hi_pct=99.7)),
        (axes[1], pvi, "reduced (PVI)", dict(lo_pct=50.0, hi_pct=99.7)),
        (axes[2], dif_disp, "difference (DIA)", dict(lo_pct=99.95, hi_pct=100.0)),
    )
    for ax, img, title, kwargs in panels:
        ax.imshow(
            img,
            origin="lower",
            cmap="gray",
            norm=log_norm(img, **kwargs),
            interpolation="nearest",
            aspect="equal",
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(title, fontsize=30, fontweight="bold")

    fig.suptitle(SCIENCE_LABEL, fontsize=34, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
