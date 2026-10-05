#!/usr/bin/env python
"""Measure each Nickel filter's colour slope against PS1 (runs in the stack).

For every visit with calibrated sources, matches stars to the repo's PS1 DR2
reference catalogue and fits

    m_STIPS - m_PS1(band)  =  a + b * (r - i)_PS1

The zeropoint a absorbs calibration choices, but the slope b is a property of
the filter's bandpass: it does not depend on how the zeropoint was fitted.
Expected slopes (Tonry et al. 2012 and this repo's Landolt fit):
  Cousins R vs PS1 r:  b ~ -0.24      SDSS r' vs PS1 r:  b ~ 0
  Cousins I vs PS1 i:  b ~ -0.35      SDSS i' vs PS1 i:  b ~ 0
(I_C - i_P1 = -0.379 + 0.352 (i - r) is b = -0.352 on (r - i).)

Usage: filter_colour_slope.py REPO OUTPUT_CSV [PROCESSCCD_GLOB]
"""

from __future__ import annotations

import csv
import sys

import numpy as np
from astropy.io import fits
from lsst.daf.butler import Butler


def ps1_table(butler: Butler):
    ra, dec, r, i = [], [], [], []
    for ref in butler.query_datasets(
        "panstarrs1_dr2", collections="refcats*", find_first=False, explain=False
    ):
        cat = butler.get(ref)
        ra.append(np.degrees(cat["coord_ra"]))
        dec.append(np.degrees(cat["coord_dec"]))
        r.append(cat["rMeanPSFMag_flux"])
        i.append(cat["iMeanPSFMag_flux"])
    ra, dec = np.concatenate(ra), np.concatenate(dec)
    r_mag = 31.4 - 2.5 * np.log10(np.concatenate(r))
    i_mag = 31.4 - 2.5 * np.log10(np.concatenate(i))
    return ra, dec, r_mag, i_mag


def fit(color, delta):
    """Robust line fit: iterative 3-sigma clipping, then least squares."""
    keep = np.isfinite(color) & np.isfinite(delta)
    for _ in range(5):
        b, a = np.polyfit(color[keep], delta[keep], 1)
        resid = delta - (a + b * color)
        sigma = 1.4826 * np.median(np.abs(resid[keep] - np.median(resid[keep])))
        new = keep & (np.abs(resid) < 3 * sigma)
        if new.sum() == keep.sum():
            break
        keep = new
    n = keep.sum()
    cov = np.polyfit(color[keep], delta[keep], 1, cov=True)[1] if n > 4 else None
    b_err = float(np.sqrt(cov[0, 0])) if cov is not None else float("nan")
    return float(a), float(b), b_err, int(n), float(sigma)


def main() -> int:
    repo, output = sys.argv[1], sys.argv[2]
    glob = sys.argv[3] if len(sys.argv) > 3 else "*/runs/*/processCcd/*"
    butler = Butler.from_config(repo)
    ra, dec, r_ps1, i_ps1 = ps1_table(butler)
    rows = []
    refs = butler.query_datasets(
        "single_visit_star", collections=glob, find_first=False, explain=False
    )
    seen = set()
    for ref in refs:
        visit = ref.dataId["visit"]
        if visit in seen:
            continue
        seen.add(visit)
        rec = butler.query_dimension_records(
            "visit", data_id=ref.dataId, explain=False
        )[0]
        # The header label ("r'" vs "R") is what distinguishes the filter
        # eras; ingest maps both to physical_filter R, so read the raw file.
        raw = butler.query_datasets(
            "raw", collections="*/raw/*", find_first=False, explain=False,
            where=f"instrument='{rec.instrument}' AND exposure={visit}",
        )  # fmt: skip
        filtnam = (
            str(fits.getheader(butler.getURI(raw[0]).ospath).get("FILTNAM")).strip()
            if raw
            else "?"
        )
        df = butler.get(ref).to_pandas()
        good = (
            (df["psfFlux"] > 0)
            & (df["psfFlux"] / df["psfFluxErr"] > 50)
            & ~df["pixelFlags_saturatedCenter"].astype(bool)
            & (df.get("extendedness", 0) < 0.5)
        )
        df = df[good]
        if len(df) < 10:
            continue
        sra, sdec = df["coord_ra"].to_numpy(), df["coord_dec"].to_numpy()
        if np.nanmax(np.abs(sra)) < 7:  # radians -> degrees
            sra, sdec = np.degrees(sra), np.degrees(sdec)
        cosd = np.cos(np.radians(np.median(sdec)))
        near = (np.abs(dec - np.median(sdec)) < 0.2) & (
            np.abs((ra - np.median(sra)) * cosd) < 0.2
        )
        rra, rdec, rr, ri = ra[near], dec[near], r_ps1[near], i_ps1[near]
        if len(rra) == 0:
            continue
        dx = (sra[:, None] - rra[None, :]) * cosd * 3600
        dy = (sdec[:, None] - rdec[None, :]) * 3600
        d2 = dx**2 + dy**2
        j = np.argmin(d2, axis=1)
        ok = d2[np.arange(len(j)), j] < 1.0
        m = 31.4 - 2.5 * np.log10(df["psfFlux"].to_numpy()[ok])
        band = ref.dataId["band"]
        ps1 = (rr if band[0] == "r" else ri)[j[ok]]  # r, rp -> PS1 r; i, ip -> PS1 i
        color = (rr - ri)[j[ok]]
        sel = (ps1 > 13) & (ps1 < 19) & (color > -0.3) & (color < 1.5)
        if sel.sum() < 10:
            continue
        a, b, b_err, n, sigma = fit(color[sel], (m - ps1)[sel])
        rows.append(
            dict(visit=visit, band=band, physical_filter=rec.physical_filter, filtnam=filtnam,
                 target=rec.target_name, day_obs=rec.day_obs, n=n,
                 zeropoint_offset=round(a, 4), slope=round(b, 4),
                 slope_err=round(b_err, 4), scatter=round(sigma, 4))
        )  # fmt: skip
    with open(output, "w", newline="") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
