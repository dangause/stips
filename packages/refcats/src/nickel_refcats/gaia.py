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

from pathlib import Path

import pandas as pd

#: Columns required by convertReferenceCatalog ConvertGaiaManager (+ a few extras).
#: Must stay a superset of what ``gaia_dr3_config.py`` maps.
COLS_SQL = """
  g.source_id,
  g.ra, g.dec, g.ra_error, g.dec_error,
  g.parallax, g.parallax_error,
  g.pmra, g.pmra_error, g.pmdec, g.pmdec_error,
  g.ref_epoch,
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
    job = _launch_gaia_job(adql)
    res = job.get_results()
    df = res if isinstance(res, pd.DataFrame) else res.to_pandas()
    df.columns = [c.lower() for c in df.columns]

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return out_csv
