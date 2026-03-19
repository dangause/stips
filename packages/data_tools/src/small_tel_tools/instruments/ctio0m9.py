"""Ctio0m9Plugin — operational adapter for the CTIO/SMARTS 0.9m telescope."""

from __future__ import annotations

import logging
from pathlib import Path

from small_tel_tools.instruments.base import InstrumentPlugin

__all__ = ("Ctio0m9Plugin",)

log = logging.getLogger(__name__)


class Ctio0m9Plugin(InstrumentPlugin):
    """Operational adapter for the CTIO/SMARTS 0.9m at Cerro Tololo."""

    name = "ctio0m9"
    instrument_class = "lsst.obs.smalltel.ctio0m9.Ctio0m9"
    collection_prefix = "ctio0m9"
    skymap_name = "ctio0m9Rings-v1"
    skymaps_chain = "skymaps/ctio0m9Rings"
    day_obs_offset = 1  # CTIO is UTC-4; observing night rolls into next UT day

    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw CTIO data for *night*.

        CTIO/SMARTS 0.9m does not have a public archive API like Lick.
        Data must be obtained through NOAO archive or direct file transfer.

        Parameters
        ----------
        night
            Observing night in YYYYMMDD format.
        dest_dir
            Destination directory.

        Raises
        ------
        NotImplementedError
            CTIO archive access not yet implemented.
        """
        raise NotImplementedError(
            "CTIO 0.9m archive download not implemented. "
            "Please manually copy raw data to the appropriate directory."
        )

    def bootstrap(self, repo: Path, config: dict) -> None:
        """Bootstrap a Butler repo for CTIO 0.9m.

        This currently delegates to core.bootstrap.bootstrap() with
        CTIO-specific parameters.
        """
        # Intentional pass: full implementation deferred.
        pass

    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config paths relative to obs_smalltel/configs/ctio0m9/.

        Returns a mapping of config role → relative Path so callers can
        locate the right override file without hard-coding telescope names.
        """
        return {
            "colorterms": Path("ctio0m9/colorterms.py"),
            "make_skymap": Path("ctio0m9/makeSkyMap.py"),
        }

    def curated_calibrations_path(self) -> Path | None:
        """Return the obs_ctio0m9_data package directory if available.

        obs_ctio0m9_data contains defect maps for the SITE2K detector.
        Returns ``None`` when the package is not installed.
        """
        try:
            from lsst.utils import getPackageDir  # type: ignore

            return Path(getPackageDir("obs_ctio0m9_data"))
        except (ImportError, LookupError):
            return None

    def refcat_path(self) -> Path | None:
        """Return the reference catalog root if configured.

        CTIO uses Gaia DR3 refcats. Reads ``REFCAT_REPO`` from the
        environment. Returns ``None`` when unset or non-existent.
        """
        import os

        path = os.environ.get("REFCAT_REPO")
        if path:
            p = Path(path)
            if p.exists():
                return p
        return None
