#!/usr/bin/env python
"""Generate poster-size 3-panel figure for SN 2023ixf in M101.

Same Nickel R-band visit (85480145, 40 s, night 20230527 / UT 20230528) shown
at three pipeline stages, left to right:

  - raw                       — direct read of the science FITS off disk
                                (bias pedestal, overscan strip, dust donuts,
                                 vignetting, no WCS)
  - preliminary_visit_image   — ISR + flat + defect mask + WCS + nJy
                                photometric calibration
  - difference_image          — preliminary_visit_image minus the warped,
                                PSF-matched template (Nickel coadd in this
                                case) — what DIA looks for transients in
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from astropy.visualization import (
    AsymmetricPercentileInterval,
    ImageNormalize,
    LogStretch,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "analysis" / "2023ixf_raw_pvi_diff_poster.png"

DATA_REPO = Path(
    "/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_nickel_template_022226b_repo"
)

# Visit 85480145 — SN 2023ixf, R-band, 40 s, night 20230527 (UT 20230528).
RAW_FITS = (
    DATA_REPO
    / "Nickel/raw/20230527/20260223T162228Z/raw/20230528/20230528_145"
    / "raw_Nickel_R_20230528_145_CCD0_Nickel_raw_20230527_20260223T162228Z.fits"
)
PVI_FITS = (
    DATA_REPO
    / "Nickel/runs/20230527/processCcd/20260223T172313Z/run/preliminary_visit_image"
    / "20230528/r/R/85480145"
    / "preliminary_visit_image_Nickel_r_R_85480145_CCD0_Nickel_runs_20230527_processCcd_20260223T172313Z_run.fits"
)
DIFF_FITS = (
    DATA_REPO
    / "Nickel/runs/20230527/diff/20260223T221529Z/run/difference_image"
    / "20230528/r/R/85480145"
    / "difference_image_Nickel_r_R_85480145_CCD0_Nickel_runs_20230527_diff_20260223T221529Z_run.fits"
)
SCIENCE_LABEL = "SN 2023ixf in M101 · Nickel R · 40 s · visit 85480145"


def log_norm(
    arr: np.ndarray, lo_pct: float = 50.0, hi_pct: float = 99.7, a: float = 1000.0
):
    """Log stretch with tight percentile clipping for high contrast.

    Clipping the low end at the sky median crushes background to black; the
    high end at 99.7% lets bright stars saturate without compressing the
    mid-tones used to render the host galaxy and faint sources.
    """
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

    # DS9 "log + min max" appears to clip negatives to zero, so noise around
    # zero compresses to black instead of mid-grey. Replicate by floor-clipping
    # the difference image before display.
    dif_disp = np.where(np.isfinite(dif), np.maximum(dif, 0.0), np.nan)

    fig, axes = plt.subplots(1, 3, figsize=(22, 8.5))
    # raw / PVI use tight percentile clipping for high contrast.
    # DIA uses true min-max log (matches DS9 with negatives clamped above).
    panels = (
        (axes[0], raw, "raw", dict(lo_pct=50.0, hi_pct=99.7)),
        (axes[1], pvi, "reduced (PVI)", dict(lo_pct=50.0, hi_pct=99.7)),
        (axes[2], dif_disp, "difference (DIA)", dict(lo_pct=0.0, hi_pct=100.0)),
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
