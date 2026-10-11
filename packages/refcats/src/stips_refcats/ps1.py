"""Single-cone Pan-STARRS1 DR2 fetch for on-demand refcat building.

Importable, orchestrator-facing path: fetch one PS1 DR2 "mean" cone around a
target and write a CSV with the columns ``ps1_config.py`` expects. The
``astroquery`` import is deferred into :func:`_query_ps1_mean` so importing this
module is cheap and offline.

PS1 only covers Dec > -30 deg; :func:`fetch_ps1_cone` raises
:class:`PS1FootprintError` outside that footprint so callers can fall back to
Gaia-only astrometry. STScI uses ``-999.0`` to mean "no measurement"; those are
masked to NaN before writing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: PS1 southern footprint limit (degrees). Nothing reliable below this.
PS1_DEC_MIN = -30.0

#: Columns needed by ps1_config.py (+ useful extras). Superset of the mapping.
PS1_COLUMNS = [
    "objID",
    "raMean",
    "decMean",
    "raMeanErr",
    "decMeanErr",
    "epochMean",
    "gMeanPSFMag",
    "rMeanPSFMag",
    "iMeanPSFMag",
    "zMeanPSFMag",
    "yMeanPSFMag",
    "gMeanPSFMagErr",
    "rMeanPSFMagErr",
    "iMeanPSFMagErr",
    "zMeanPSFMagErr",
    "yMeanPSFMagErr",
    "nDetections",
    "ng",
    "nr",
    "ni",
    "nz",
    "ny",
    "qualityFlag",
    "objInfoFlag",
]

#: Magnitude / error columns where -999.0 means "no measurement".
_SENTINEL_COLUMNS = [
    c for c in PS1_COLUMNS if c.endswith("Mag") or c.endswith("MagErr")
]

#: PSF-mag bands a usable photometric reference MUST have. These are the bands
#: the Nickel photometry + color terms consume (g for B/V, r/i for R/I). Most
#: PS1 mean-catalog objects (galaxies/faint) lack a clean PSF magnitude; keeping
#: them makes convertReferenceCatalog read the empty CSV field as 0.0 -> mag-0
#: (hugely bright) garbage references that wreck the photometric zeropoint fit.
REQUIRED_PSF_MAG_BANDS = ["gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag"]


class PS1FootprintError(Exception):
    """Raised when a target is outside the PS1 (Dec > -30) footprint."""


#: Rows per MAST request. MAST never returns more than one page per request,
#: so a cone with more objects than this must be read page by page.
PS1_PAGESIZE = 50000

#: Safety cap on pages per cone (50000 * 40 = 2M objects, far beyond any
#: cone STIPS fetches). Stops a runaway loop if MAST ever misreports a page.
PS1_MAX_PAGES = 40


def query_ps1_mean_pages(
    ra: float,
    dec: float,
    radius_deg: float,
    *,
    columns: list[str] = PS1_COLUMNS,
    pagesize: int = PS1_PAGESIZE,
) -> pd.DataFrame:
    """Read the whole PS1 DR2 mean-object cone from MAST, page by page.

    MAST serves at most ``pagesize`` rows per request and, without a sort
    key, each request returns an arbitrary slice of the cone, so a single
    request on a cone larger than one page silently returns a different
    random subset each time (observed: 50000 of 111595 objects for a 0.3 deg
    cone at Dec +54). Sorting by ``objID`` makes the pages disjoint and the
    result repeatable; the loop stops at the first short page.

    Lazily imports astroquery/astropy so module import stays offline.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Catalogs

    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    pages: list[pd.DataFrame] = []
    for page in range(1, PS1_MAX_PAGES + 1):
        tab = Catalogs.query_region(
            coordinates=coord,
            radius=radius_deg * u.deg,
            catalog="Panstarrs",
            data_release="dr2",
            table="mean",
            columns=columns,
            pagesize=pagesize,
            page=page,
            sort_by=[("asc", "objID")],
        )
        df = tab.to_pandas()
        pages.append(df)
        if len(df) < pagesize:
            break
    else:
        raise RuntimeError(
            f"PS1 cone at ({ra:.5f}, {dec:.5f}) r={radius_deg} deg exceeded "
            f"{PS1_MAX_PAGES} pages of {pagesize} rows; shrink the cone"
        )
    return pd.concat(pages, ignore_index=True) if len(pages) > 1 else pages[0]


def _query_ps1_mean(ra: float, dec: float, radius_deg: float) -> pd.DataFrame:
    """Query the PS1 DR2 mean-object table for one cone. Mockable seam."""
    return query_ps1_mean_pages(ra, dec, radius_deg)


def fetch_ps1_cone(
    ra: float,
    dec: float,
    radius_deg: float,
    *,
    out_csv: Path,
) -> Path:
    """Fetch one PS1 DR2 cone and write it to ``out_csv``.

    Raises
    ------
    PS1FootprintError
        If ``dec < -30`` (outside the PS1 footprint).
    """
    if dec < PS1_DEC_MIN:
        raise PS1FootprintError(
            f"Dec {dec:.4f} is south of the PS1 footprint (Dec > {PS1_DEC_MIN})"
        )

    df = _query_ps1_mean(ra, dec, radius_deg)

    # -999.0 sentinel -> NaN so it is never treated as a real magnitude.
    present = [c for c in _SENTINEL_COLUMNS if c in df.columns]
    if present:
        df[present] = df[present].replace(-999.0, np.nan)

    # Keep only objects with a valid PSF magnitude in every band photometry uses.
    # Drops galaxies/faint objects lacking PSF mags whose empty fields would
    # otherwise be read back as mag-0 garbage references by convertReferenceCatalog.
    req = [c for c in REQUIRED_PSF_MAG_BANDS if c in df.columns]
    if req:
        df = df.dropna(subset=req)

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return out_csv
