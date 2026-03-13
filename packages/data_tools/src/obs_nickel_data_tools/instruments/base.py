"""InstrumentPlugin ABC — operational adapter for a telescope."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

__all__ = ("InstrumentPlugin",)


class InstrumentPlugin(ABC):
    """Operational adapter for a telescope.

    NOT the LSST Instrument class (that lives in obs_smalltel).
    This handles archive access, bootstrap orchestration,
    and default pipeline config paths.

    Subclasses MUST set these class attributes:
      - name: str                  e.g. "Nickel"
      - instrument_class: str      e.g. "lsst.obs.smalltel.nickel.Nickel"
      - collection_prefix: str     e.g. "Nickel"
      - skymap_name: str           e.g. "nickelRings-v1"
      - skymaps_chain: str         e.g. "skymaps/nickelRings"
      - day_obs_offset: int        1 for Lick (UTC-8), 0 for eastern observatories
    """

    name: str
    instrument_class: str
    collection_prefix: str
    skymap_name: str
    skymaps_chain: str
    day_obs_offset: int

    @abstractmethod
    def fetch_data(self, night: str, dest_dir: Path) -> None:
        """Download raw data for a given observing night."""
        ...

    @abstractmethod
    def bootstrap(self, repo: Path, config: dict) -> None:
        """Initialize Butler repository for this instrument."""
        ...

    def default_pipeline_configs(self) -> dict[str, Path]:
        """Default pipeline config overrides for this telescope."""
        return {}

    def curated_calibrations_path(self) -> Path | None:
        """Path to curated calibration data (defects, crosstalk)."""
        return None

    def refcat_path(self) -> Path | None:
        """Path to reference catalog repository."""
        return None
