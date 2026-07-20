"""Curated calibration data for the CTIO 1.0m (Y4KCam) telescope.

This package provides curated calibrations (defects, etc.) that can be
ingested into a Butler repository using ``butler write-curated-calibrations``.
"""

from importlib.resources import files

__all__ = ["getPackageDir"]


def getPackageDir() -> str:
    """Return the root directory of the obs_ctio1m_data package.

    Returns
    -------
    path : `str`
        Path to the package root directory containing calibration data.
    """
    # Navigate from lsst/obs/ctio1m_data to package root
    return str(
        files("lsst.obs.ctio1m_data")
        .joinpath("..")
        .joinpath("..")
        .joinpath("..")
        .joinpath("..")
        .resolve()
    )
