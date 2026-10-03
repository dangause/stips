#!/usr/bin/env python
"""Re-measure SN 2023ixf flux on every R/I-band difference image by direct
asymptotic-aperture summation, bypassing PSF-fit forced photometry.

STIPS' PSF-fit on diff systematically under-reports the total flux (per CLAUDE.md
HD 189733b notes). A direct aperture sum at the target sky coordinates recovers
the missing flux. Output CSV mirrors the lightcurve_2023ixf.csv schema so the
poster plot can swap data sources by changing one path.
"""

from __future__ import annotations

import csv
import glob
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

REPO = Path("/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo")
OUT_CSV = Path(
    "/Users/dangause/Developer/lick/lsst/lsst_stack/stack/stips/"
    "analysis/lightcurve_2023ixf_aperture.csv"
)

RA, DEC = 210.910750, 54.311694
EXPLOSION_MJD = 60082.75

# Asymptotic source aperture (px). Inspecting visit 85480107 showed the diff
# flux plateaus at r=17 px ≈ 6.3″ — enough to capture the PSF wings but small
# enough to keep sky noise modest. Sky annulus at 30-45 px estimates residual
# background after DIA's host subtraction.
SRC_R, SKY_R_IN, SKY_R_OUT = 17.0, 30.0, 45.0

# AB zeropoint for nJy-scaled images: m = 31.4 - 2.5*log10(flux_nJy)
AB_NJY_ZP = 31.4


def measure(diff_path: Path) -> dict | None:
    """Aperture-flux + AB mag at (RA, DEC). Returns None on read failure."""
    try:
        hdul = fits.open(diff_path)
        img = hdul["IMAGE"].data.astype(np.float64)
        wcs = WCS(hdul["IMAGE"].header)
        var = hdul["VARIANCE"].data.astype(np.float64)
        prim = hdul[0].header
    except Exception as exc:
        print(f"[warn] {diff_path.name}: {exc}")
        return None

    h, w = img.shape
    xa, ya = wcs.world_to_pixel_values(RA, DEC)
    xi, yi = float(xa), float(ya)
    if not (10 < xi < w - 10 and 10 < yi < h - 10):
        hdul.close()
        return None

    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - xi) ** 2 + (yy - yi) ** 2

    src_mask = r2 <= SRC_R**2
    sky_mask = (r2 >= SKY_R_IN**2) & (r2 <= SKY_R_OUT**2)

    sky_pix = img[sky_mask]
    sky_pix = sky_pix[np.isfinite(sky_pix)]
    if sky_pix.size < 50:
        hdul.close()
        return None
    # Sigma-clipped median sky (robust to residual artifacts in annulus).
    med = float(np.median(sky_pix))
    mad = float(np.median(np.abs(sky_pix - med)))
    sigma = 1.4826 * mad
    keep = np.abs(sky_pix - med) < 3 * sigma
    sky_per_pix = float(np.median(sky_pix[keep]))

    n_src = int(np.sum(src_mask))
    src_sum_raw = float(np.nansum(img[src_mask]))
    flux = src_sum_raw - n_src * sky_per_pix
    flux_err = float(np.sqrt(np.nansum(var[src_mask])))

    # DATE-AVG is in TAI; convert to UTC, then MJD. See HD 189733b notes in
    # CLAUDE.md — Nickel diff/PVI FITS store DATE-AVG as TAI explicitly.
    date_avg = prim.get("DATE-AVG")
    mjd = None
    if date_avg:
        try:
            mjd = float(Time(date_avg, scale="tai").utc.mjd)
        except Exception:
            mjd = None

    if flux <= 0:
        hdul.close()
        return {
            "mjd": mjd,
            "band": prim.get("FILTNAM", "").lower(),
            "visit": int(diff_path.parent.name),
            "flux_nJy": flux,
            "flux_nJy_err": flux_err,
            "mag": float("nan"),
            "mag_err": float("nan"),
            "snr": flux / flux_err if flux_err > 0 else 0.0,
        }

    mag = AB_NJY_ZP - 2.5 * np.log10(flux)
    mag_err = 2.5 / np.log(10) * (flux_err / flux)
    snr = flux / flux_err if flux_err > 0 else 0.0
    hdul.close()
    return {
        "mjd": mjd,
        "band": prim.get("FILTNAM", "").lower(),
        "visit": int(diff_path.parent.name),
        "flux_nJy": flux,
        "flux_nJy_err": flux_err,
        "mag": mag,
        "mag_err": mag_err,
        "snr": snr,
    }


def main() -> None:
    pattern = str(
        REPO
        / "Nickel/runs/*/diff/*/run/difference_image/*/?/*/*/difference_image_*.fits"
    )
    diff_paths = sorted(Path(p) for p in glob.glob(pattern))
    print(f"found {len(diff_paths)} diff images")

    rows = []
    for i, p in enumerate(diff_paths):
        rec = measure(p)
        if rec is None:
            continue
        rec["days_since_explosion"] = (
            (rec["mjd"] - EXPLOSION_MJD) if rec["mjd"] is not None else None
        )
        rec["ra"] = RA
        rec["dec"] = DEC
        rows.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  measured {i+1}/{len(diff_paths)}")

    if not rows:
        raise SystemExit("no rows measured")
    fieldnames = [
        "mjd",
        "band",
        "visit",
        "ra",
        "dec",
        "flux_nJy",
        "flux_nJy_err",
        "mag",
        "mag_err",
        "snr",
        "days_since_explosion",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})
    print(f"wrote {OUT_CSV} with {len(rows)} rows")


if __name__ == "__main__":
    main()
