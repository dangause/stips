#!/usr/bin/env python
"""Fit PS1 -> Nickel B/V/R/I color terms against Landolt standard stars.

For each Landolt standard in landolt_catalog.csv, query PS1 DR2 mean PSF g/r/i,
and least-squares fit  target = primary + c0 + c1*(primary - secondary)  per band.
Prints old (synthetic) vs new (Landolt) coefficients and residual RMS.

The c0 (constant) is absorbed by calibrateImage's per-visit photometric zeropoint;
the c1 (color slope) is what removes color-dependent systematics in calibrated
photometry. Requires the LSST stack env (astroquery) — run under `make`/activated.

Usage:
    python scripts/analysis/fit_ps1_colorterms_landolt.py \\
        --catalog scripts/config/landolt_validation/landolt_catalog.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

# band -> (primary PS1 mag, (color_a, color_b), current synthetic c1)
BANDS = {
    "B": ("gMeanPSFMag", ("gMeanPSFMag", "rMeanPSFMag"), 0.617608),
    "V": ("gMeanPSFMag", ("gMeanPSFMag", "rMeanPSFMag"), -0.428548),
    "R": ("rMeanPSFMag", ("rMeanPSFMag", "iMeanPSFMag"), -0.129111),
    "I": ("iMeanPSFMag", ("iMeanPSFMag", "rMeanPSFMag"), 1.031936),
}


def _ps1_match(ra, dec):
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Catalogs

    t = Catalogs.query_region(
        SkyCoord(ra * u.deg, dec * u.deg),
        radius=5 * u.arcsec,
        catalog="Panstarrs",
        data_release="dr2",
        table="mean",
        columns=["raMean", "decMean", "gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag"],
    )
    if len(t) == 0:
        return None
    d = t.to_pandas()
    d = d[(d.gMeanPSFMag > 0) & (d.rMeanPSFMag > 0) & (d.iMeanPSFMag > 0)]
    if len(d) == 0:
        return None
    dd = (d.raMean - ra) ** 2 + (d.decMean - dec) ** 2
    return d.loc[dd.idxmin()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument(
        "--exclude", nargs="*", default=["SA 109-199"], help="star_name(s) to drop"
    )
    args = ap.parse_args()

    cat = pd.read_csv(args.catalog)
    recs = []
    for _, s in cat.iterrows():
        if s.star_name in args.exclude:
            continue
        m = _ps1_match(s.ra_deg, s.dec_deg)
        if m is None:
            continue
        recs.append(
            dict(
                gMeanPSFMag=m.gMeanPSFMag,
                rMeanPSFMag=m.rMeanPSFMag,
                iMeanPSFMag=m.iMeanPSFMag,
                B=s.B,
                V=s.V,
                R=s.R,
                I=s.I,
            )
        )
    df = pd.DataFrame(recs)
    print(f"fitting on {len(df)} Landolt stars\n")
    print(
        f"{'band':4} {'old_c1':>8} {'old_RMS':>8}   {'c0':>8} {'c1':>8} {'new_RMS':>8}"
    )
    for b, (prim, (ca, cb), c1old) in BANDS.items():
        primv = df[prim].values
        color = (df[ca] - df[cb]).values
        true = df[b].values
        old_rms = np.std(primv + c1old * color - true)
        A = np.vstack([np.ones_like(color), color]).T
        (c0, c1), *_ = np.linalg.lstsq(A, true - primv, rcond=None)
        new_rms = np.std(primv + c0 + c1 * color - true)
        print(f"{b:4} {c1old:8.3f} {old_rms:8.3f}   {c0:8.3f} {c1:8.3f} {new_rms:8.3f}")


if __name__ == "__main__":
    main()
