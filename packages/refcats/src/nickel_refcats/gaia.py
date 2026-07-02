"""Single-cone Gaia DR3 fetch for on-demand refcat building.

This is the importable, orchestrator-facing path: fetch exactly one cone around
a target and write a CSV with the columns ``gaia_dr3_config.py`` expects. The
``astroquery`` import is deferred into :func:`_launch_gaia_job` so importing this
module is cheap and does not hit the Gaia server (astroquery prints a server MOTD
on import of ``astroquery.gaia``).

The standalone batch tool (``scripts/gaia_fetch.py``) remains for bulk
pre-fetching many pointings at once.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

#: Columns required by convertReferenceCatalog ConvertGaiaManager (+ a few extras).
#: Must stay a superset of what ``gaia_dr3_config.py`` maps.
COLS_SQL = """
  g.source_id,
  g.ra, g.dec, g.ra_error, g.dec_error,
  g.parallax, g.parallax_error,
  g.pmra, g.pmra_error, g.pmdec, g.pmdec_error,
  g.ref_epoch,
  g.ra_dec_corr, g.ra_parallax_corr, g.ra_pmra_corr, g.ra_pmdec_corr,
  g.dec_parallax_corr, g.dec_pmra_corr, g.dec_pmdec_corr,
  g.parallax_pmra_corr, g.parallax_pmdec_corr, g.pmra_pmdec_corr,
  g.phot_g_mean_flux,  g.phot_bp_mean_flux,  g.phot_rp_mean_flux,
  g.phot_g_mean_flux_over_error, g.phot_bp_mean_flux_over_error, g.phot_rp_mean_flux_over_error,
  g.phot_g_mean_mag,   g.phot_bp_mean_mag,   g.phot_rp_mean_mag
""".strip()

_GAIA_TABLE = "gaiadr3.gaia_source"


def _build_cone_adql(
    ra: float,
    dec: float,
    radius_deg: float,
    ruwe_max: float | None,
    require_5param: bool,
) -> str:
    """Build the single-cone ADQL query, including optional quality cuts.

    Float literals are used for the radius so the server does not do integer
    division. ``ruwe`` / proper-motion / parallax conditions are applied in the
    WHERE clause (server-side) rather than selected into the output.
    """
    where = [
        "1 = CONTAINS(POINT('ICRS', g.ra, g.dec), "
        f"CIRCLE('ICRS', {float(ra):.8f}, {float(dec):.8f}, {float(radius_deg):.8f}))"
    ]
    if ruwe_max is not None:
        where.append(f"g.ruwe < {float(ruwe_max):.3f}")
    if require_5param:
        where.append(
            "g.pmra IS NOT NULL AND g.pmdec IS NOT NULL " "AND g.parallax IS NOT NULL"
        )
    where_clause = " AND ".join(where)
    return f"SELECT {COLS_SQL} FROM {_GAIA_TABLE} AS g WHERE {where_clause}"


def _launch_gaia_job(adql: str):
    """Launch an async Gaia TAP job. Isolated so tests can mock it.

    Lazily imports astroquery so module import stays offline/cheap.
    """
    from astroquery.gaia import Gaia

    Gaia.MAIN_GAIA_TABLE = _GAIA_TABLE
    Gaia.TIMEOUT = 600
    return Gaia.launch_job_async(
        query=adql, dump_to_file=False, output_format="votable"
    )


def _launch_gaia_job_sync(adql: str):
    """Synchronous Gaia TAP fallback for when the async result-storage is down.

    Gaia async TAP writes results to a job-storage volume that suffers periodic
    outages (HTTP 500 "result path does not exist"). A synchronous query returns
    results inline over HTTP, bypassing that volume, but is capped at 2000 rows
    server-side — so request the brightest 2000 by G, which is ample for
    astrometric/photometric calibration. Isolated so tests can mock it.
    """
    from astroquery.gaia import Gaia

    Gaia.MAIN_GAIA_TABLE = _GAIA_TABLE
    Gaia.TIMEOUT = 600
    sync_adql = (
        adql.replace("SELECT ", "SELECT TOP 2000 ", 1)
        + " ORDER BY g.phot_g_mean_mag"
    )
    return Gaia.launch_job(query=sync_adql, output_format="votable")


def fetch_gaia_cone(
    ra: float,
    dec: float,
    radius_deg: float,
    *,
    out_csv: Path,
    ruwe_max: float | None = 1.4,
    require_5param: bool = True,
) -> Path:
    """Fetch one Gaia DR3 cone and write it to ``out_csv``.

    Parameters
    ----------
    ra, dec
        Cone center in degrees (ICRS).
    radius_deg
        Cone radius in degrees.
    out_csv
        Output CSV path; written with lowercased column names matching
        ``gaia_dr3_config.py`` (``ra``, ``dec``, ``pmra``, ``pmdec``,
        ``ref_epoch``, fluxes, etc.).
    ruwe_max
        If set, keep only sources with ``ruwe < ruwe_max`` (astrometric
        quality). ``None`` disables the cut.
    require_5param
        If True, require a full 5-parameter solution (non-null pm + parallax)
        so positions can be proper-motion propagated.

    Returns
    -------
    Path
        ``out_csv``.
    """
    adql = _build_cone_adql(ra, dec, radius_deg, ruwe_max, require_5param)
    try:
        job = _launch_gaia_job(adql)
        res = job.get_results()
    except Exception as exc:  # noqa: BLE001 - async job-storage outages are common
        log.warning(
            "Gaia async TAP failed (%s); falling back to sync (brightest 2000)", exc
        )
        job = _launch_gaia_job_sync(adql)
        res = job.get_results()
    df = res if isinstance(res, pd.DataFrame) else res.to_pandas()
    df.columns = [c.lower() for c in df.columns]

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return out_csv
