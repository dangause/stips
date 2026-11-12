#!/usr/bin/env python
"""Fit Gaia DR3 -> Y4KCam B/V/R/I colour terms against Landolt standard stars.

For every star in the Landolt catalogue CSV, query Gaia DR3 (gaia_source) within
3 arcsec, take phot_g/bp/rp_mean_flux (e-/s), convert them to AB magnitudes and
least-squares fit
    landolt = primary_AB + c0 + c1 * (primary_AB - secondary_AB)
per band with 3-sigma clipping. Prints the block to paste into
instruments/ctio1m/configs/colorterms.py. The LSST Colorterm reads
"<primary>_flux", so the names are phot_g_mean, phot_bp_mean, phot_rp_mean.

The Gaia side is on the AB system because the LSST reference catalogue is:
ConvertGaiaManager (meas_algorithms convertRefcatManager.py, gaiaFluxToFlux)
stores phot_{g,bp,rp}_mean_flux in nJy as m_AB = ZP - 2.5 log10(flux_e/s) with
the zero points in GAIA_AB_ZEROPOINTS, and the Colorterm is applied to those
fluxes. Fitting against the Gaia archive's Vega magnitudes (phot_*_mean_mag)
instead would change c0 by exactly -(delta_primary) - c1 * delta_colour,
where delta is AB minus Vega for the relevant Gaia band(s); c1 is exactly
unchanged, because those offsets are constants per band, not functions of
colour.

Usage (needs astroquery, present in the LSST environment and the stips venv):
    python scripts/analysis/fit_gaia_colorterms_landolt.py \
        --catalog scripts/config/landolt_validation/landolt_catalog_ctio.csv \
        --catalog scripts/config/landolt_validation/landolt_catalog.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

# Gaia DR3 e-/s flux -> AB magnitude zero points, verbatim from the LSST
# converter (ConvertGaiaManager._getFluxes; Gaia DR2 documentation Table 5.3),
# keyed by the refcat column stem. These are the DR2 Table 5.3 zero points
# that the LSST converter applies to DR3 fluxes; they must match the
# converter, not be "upgraded" to the DR3 values (25.8010 / 25.3540 /
# 25.1040) -- using the DR3 zero points here would fit against magnitudes
# the refcat never actually produces.
GAIA_AB_ZEROPOINTS = {
    "phot_g_mean": 25.7934,
    "phot_bp_mean": 25.3806,
    "phot_rp_mean": 25.1161,
}

# band -> (primary, secondary): the LSST Colorterm expresses only
# primary + c0 + c1 * (primary - secondary), so the colour is fixed by the pair.
BANDS = {
    "B": ("phot_bp_mean", "phot_rp_mean"),  # colour BP - RP
    "V": ("phot_g_mean", "phot_rp_mean"),  # colour G - RP
    "R": ("phot_rp_mean", "phot_g_mean"),  # colour RP - G
    "I": ("phot_rp_mean", "phot_g_mean"),  # colour RP - G
}


def gaia_ab_mag(flux, zp: float):
    """AB magnitude of a Gaia e-/s flux, as the LSST refcat converter computes it.

    m_AB = zp - 2.5 log10(flux); non-positive or missing fluxes give NaN.
    """
    f = np.asarray(flux, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = zp - 2.5 * np.log10(f)
    return np.where(f > 0, m, np.nan)


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

    q = f"""SELECT phot_g_mean_flux, phot_bp_mean_flux, phot_rp_mean_flux,
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
        rec = {"star": s.star_name, "B": s.B, "V": s.V, "R": s.R, "I": s.I}
        for col, zp in GAIA_AB_ZEROPOINTS.items():
            flux = m[f"{col}_flux"]
            flux = np.nan if np.ma.is_masked(flux) else float(flux)
            rec[col] = float(gaia_ab_mag(flux, zp))
        recs.append(rec)
    d = pd.DataFrame(recs)
    print(f"{len(d)} stars matched of {len(cat)}")
    print('    "gaia*": ColortermDict(\n        data={')
    for band, (prim, sec) in BANDS.items():
        c0, c1, rms = fit_band(d[band], d[prim], d[sec])
        print(
            f'            "{band}": Colorterm(primary="{prim}", secondary="{sec}", c0={c0:.4f}, c1={c1:.4f}, c2=0.0),  # rms {rms:.3f} mag, n={len(d)}'
        )
    print("        }\n    ),")


if __name__ == "__main__":
    main()
