"""NickelPlugin — operational adapter for the Nickel 1-meter telescope."""

from __future__ import annotations

import logging
from pathlib import Path

from obs_nickel_data_tools.instruments.base import InstrumentPlugin

__all__ = ("NickelPlugin",)

log = logging.getLogger(__name__)


class NickelPlugin(InstrumentPlugin):
    """Operational adapter for the Nickel 1-m at Lick Observatory."""

    name = "Nickel"
    instrument_class = "lsst.obs.smalltel.nickel.Nickel"
    collection_prefix = "Nickel"
    skymap_name = "nickelRings-v1"
    skymaps_chain = "skymaps/nickelRings"
    day_obs_offset = 1  # Lick is UTC-8; observing night rolls into next UT day

    # Lick Observatory archive connection details
    archive_url: str = "https://archive.ucolick.org/archive"
    archive_instrument: str = "NICKEL_DIR"

    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw Nickel data for *night* from the Lick Observatory archive.

        Parameters
        ----------
        night
            Observing night in YYYYMMDD format (local Lick date).
        dest_dir
            Destination directory; files are written into ``dest_dir/raw/``.
        """
        import os
        import sys

        # Push lick_searchable_archive onto sys.path if configured
        archive_dir = os.environ.get("LICK_ARCHIVE_DIR")
        if archive_dir:
            sys.path.insert(0, archive_dir)

        # Import the module and delegate to its download machinery
        from obs_nickel_data_tools.pipeline_tools import fetch_archive_night as _mod

        raw_dir = dest_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Use sys.argv injection so _mod.main() sees our arguments.
        # This is a deliberate short-term bridge until fetch_archive_night exposes
        # a proper library API (tracked as future refactor).
        original_argv = sys.argv
        sys.argv = [
            "fetch_archive_night",
            "--night",
            night,
            "--raw-root",
            str(dest_dir.parent),
            "--archive-url",
            self.archive_url,
            "--instrument",
            self.archive_instrument,
        ]
        try:
            rc = _mod.main()
        finally:
            sys.argv = original_argv

        if rc not in (0, 2):  # 0=ok, 2=no data (acceptable for some nights)
            raise RuntimeError(
                f"fetch_archive_night returned exit code {rc} for night {night}"
            )

    def bootstrap(self, repo: Path, config: dict) -> None:
        """Bootstrap a Butler repo for Nickel: register instrument, ingest
        refcats, create skymap.

        This currently delegates to the existing shell-script bootstrap path
        and will be refactored to use the plugin system fully in Task 16.
        """
        # Intentional pass: full implementation deferred to Task 16.
        pass

    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config paths relative to obs_smalltel/configs/nickel/.

        Returns a mapping of config role → relative Path so callers can
        locate the right override file without hard-coding telescope names.
        """
        return {
            "calibrate_image": Path(
                "nickel/calibrateImage/tuned_configs/dense_strict.py"
            ),
            "colorterms": Path("nickel/apply_colorterms.py"),
        }

    def curated_calibrations_path(self) -> Path | None:
        """Return the obs_nickel_data package directory if the LSST stack is active.

        obs_nickel_data contains defect maps and crosstalk coefficients for the
        Nickel detector. Returns ``None`` when the LSST stack is not available
        (e.g., during pure-Python unit tests).
        """
        try:
            from lsst.utils import getPackageDir  # type: ignore

            return Path(getPackageDir("obs_nickel_data"))
        except (ImportError, LookupError):
            return None

    def refcat_path(self) -> Path | None:
        """Return the MONSTER reference catalog root if it is configured.

        Reads ``REFCAT_REPO`` from the environment. Returns ``None`` when the
        variable is unset or points to a non-existent directory.
        """
        import os

        path = os.environ.get("REFCAT_REPO")
        if path:
            p = Path(path)
            if p.exists():
                return p
        return None
