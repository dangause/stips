"""Generic instrument base class for single-CCD small telescopes."""

from __future__ import annotations

__all__ = ("GenericSmallTelInstrument",)

from pathlib import Path

import yaml


class GenericSmallTelInstrument:
    """Base instrument for single-CCD small telescopes.

    Subclasses set ``instrument_name`` and ``config_dir``.
    Everything else loads from YAML in instruments/{config_dir}/.

    This is a mixin/base that will inherit from lsst.obs.base.Instrument
    when the full class is assembled (Task 7). The YAML loading helpers
    are defined here for testability without the LSST stack.
    """

    instrument_name: str  # e.g., "Nickel"
    config_dir: str  # subdirectory under instruments/

    @classmethod
    def _package_root(cls) -> Path:
        """Resolve the obs_smalltel package root directory.

        Uses LSST's getPackageDir (EUPS) as primary resolution method,
        falling back to Path(__file__) traversal for editable pip installs.
        """
        try:
            from lsst.utils import getPackageDir

            return Path(getPackageDir("obs_smalltel"))
        except (ImportError, LookupError):
            return Path(__file__).parent.parent.parent.parent.parent

    def _config_path(self, filename: str) -> Path:
        """Resolve path to a YAML config file in instruments/{config_dir}/."""
        return self._package_root() / "instruments" / self.config_dir / filename

    def _load_yaml(self, filename: str) -> dict:
        """Load and parse a YAML config file."""
        with open(self._config_path(filename)) as f:
            return yaml.safe_load(f)
