#!/usr/bin/env python
"""Fit Gaia DR3 -> Y4KCam B/V/R/I colour terms against Landolt standard stars.

For every star in the Landolt catalogue CSV, query Gaia DR3 (gaia_source) within
3 arcsec, take phot_g/bp/rp_mean_mag, and least-squares fit
    landolt = primary + c0 + c1 * (primary - secondary)
per band with 3-sigma clipping. Prints the block to paste into
instruments/ctio1m/configs/colorterms.py. The LSST Colorterm reads
"<primary>_flux", so the names are phot_g_mean, phot_bp_mean, phot_rp_mean.

Usage (needs astroquery, present in the LSST environment and the stips venv):
    python scripts/analysis/fit_gaia_colorterms_landolt.py \
        --catalog scripts/config/landolt_validation/landolt_catalog_ctio.csv \
        --catalog scripts/config/landolt_validation/landolt_catalog.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

# band -> (primary, secondary): the LSST Colorterm expresses only
# primary + c0 + c1 * (primary - secondary), so the colour is fixed by the pair.
BANDS = {
    "B": ("phot_bp_mean", "phot_rp_mean"),   # colour BP - RP
    "V": ("phot_g_mean", "phot_rp_mean"),    # colour G - RP
    "R": ("phot_rp_mean", "phot_g_mean"),    # colour RP - G
    "I": ("phot_rp_mean", "phot_g_mean"),    # colour RP - G
}


def fit_band(landolt_mag, primary, secondary, n_sigma: float = 3.0, n_iter: int = 5):
    y = np.asarray(landolt_mag, float) - np.asarray(primary, float)
    x = np.asarray(primary, float) - np.asarray(secondary, float)
    keep = np.isfinite(x) & np.isfinite(y)
    for _ in range(n_iter):
        c1, c0 = np.polyfit(x[keep], y[keep], 1)
        res = y - (c0 + c1 * x)
        s = 1.4826 * np.median(np.abs(res[keep] - np.median(res[keep])))
        new = keep & (np.abs(res) < n_sigma * max(s, 1e-4))
        if new.sum() == keep.sum():
            break
        keep = new
    rms = float(np.std(res[keep]))
    return float(c0), float(c1), rms


def gaia_match(ra: float, dec: float):
    from astroquery.gaia import Gaia

    q = f"""SELECT phot_g_mean_mag, phot_bp_mean_mag, phot_rp_mean_mag,
                   DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra}, {dec})) AS d
            FROM gaiadr3.gaia_source
            WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {3.0 / 3600.0}))
            ORDER BY d"""
    t = Gaia.launch_job(q).get_results()
    return None if len(t) == 0 else t[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", action="append", required=True)
    args = ap.parse_args()
    cat = pd.concat([pd.read_csv(p) for p in args.catalog], ignore_index=True)
    recs = []
    for _, s in cat.iterrows():
        m = gaia_match(s.ra_deg, s.dec_deg)
        if m is None:
            continue
        recs.append({"star": s.star_name, "B": s.B, "V": s.V, "R": s.R, "I": s.I,
                     "phot_g_mean": float(m["phot_g_mean_mag"]),
                     "phot_bp_mean": float(m["phot_bp_mean_mag"]),
                     "phot_rp_mean": float(m["phot_rp_mean_mag"])})
    d = pd.DataFrame(recs)
    print(f"{len(d)} stars matched of {len(cat)}")
    print('    "gaia*": ColortermDict(\n        data={')
    for band, (prim, sec) in BANDS.items():
        c0, c1, rms = fit_band(d[band], d[prim], d[sec])
        print(f'            "{band}": Colorterm(primary="{prim}", secondary="{sec}", c0={c0:.4f}, c1={c1:.4f}, c2=0.0),  # rms {rms:.3f} mag, n={len(d)}')
    print("        }\n    ),")


if __name__ == "__main__":
    main()
