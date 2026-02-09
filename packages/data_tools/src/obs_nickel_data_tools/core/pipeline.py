"""Shared pipeline utilities."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config


def validate_night(night: str) -> str:
    """Validate and normalize a night string (YYYYMMDD).

    Args:
        night: Night string to validate

    Returns:
        Normalized night string

    Raises:
        ValueError: If night is not valid YYYYMMDD format
    """
    if not re.match(r"^\d{8}$", night):
        raise ValueError(f"Night must be YYYYMMDD format, got: {night}")

    # Validate it's a real date
    try:
        datetime.strptime(night, "%Y%m%d")
    except ValueError as e:
        raise ValueError(f"Invalid date: {night}") from e

    return night


def generate_run_timestamp() -> str:
    """Generate a UTC timestamp for collection naming."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def night_to_date_range(night: str) -> tuple[str, str]:
    """Convert observing night to certification date range.

    Returns ISO format dates for butler certify-calibrations.

    Args:
        night: Observing night (YYYYMMDD)

    Returns:
        Tuple of (begin_date, end_date) in ISO format
    """
    dt = datetime.strptime(night, "%Y%m%d").replace(tzinfo=timezone.utc)
    from datetime import timedelta

    end_dt = dt + timedelta(days=2)
    return (
        dt.strftime("%Y-%m-%dT%H:%M:%S"),
        end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def night_to_day_obs(night: str) -> str:
    """Convert observing night (local) to UT day_obs.

    Lick observations starting on local night YYYYMMDD have
    UT dates of YYYYMMDD+1 in FITS headers.

    Args:
        night: Local observing night (YYYYMMDD)

    Returns:
        UT day_obs (YYYYMMDD)
    """
    from datetime import timedelta

    dt = datetime.strptime(night, "%Y%m%d")
    return (dt + timedelta(days=1)).strftime("%Y%m%d")


def get_raw_dir(config: Config, night: str) -> Path:
    """Get the raw data directory for a night."""
    return config.raw_parent_dir / night / "raw"


def parse_bad_exposures(
    bad_list: str | None = None,
    bad_file: Path | None = None,
) -> list[int]:
    """Parse bad exposure IDs from string and/or file.

    Args:
        bad_list: Comma or space separated exposure IDs
        bad_file: File with exposure IDs (comments allowed)

    Returns:
        Sorted list of unique exposure IDs
    """
    ids: set[int] = set()

    if bad_list:
        # Extract all numbers from the string
        for match in re.finditer(r"\d+", bad_list):
            ids.add(int(match.group()))

    if bad_file and bad_file.exists():
        with open(bad_file) as f:
            for line in f:
                # Remove comments
                line = line.split("#")[0].strip()
                for match in re.finditer(r"\d+", line):
                    ids.add(int(match.group()))

    return sorted(ids)


def build_exclusion_expr(bad_ids: list[int]) -> str:
    """Build Butler WHERE clause for excluding exposures.

    Args:
        bad_ids: List of exposure/visit IDs to exclude

    Returns:
        WHERE clause fragment (empty string if no exclusions)
    """
    if not bad_ids:
        return ""
    csv = ",".join(str(i) for i in bad_ids)
    return f" AND NOT (exposure IN ({csv}) OR visit IN ({csv}))"


class CollectionNames:
    """Generate standard collection names for a pipeline run."""

    def __init__(self, night: str, run_ts: str | None = None):
        self.night = night
        self.run_ts = run_ts or generate_run_timestamp()

    # Raw data
    @property
    def raw_run(self) -> str:
        return f"Nickel/raw/{self.night}/{self.run_ts}"

    # Calibration products
    @property
    def cp_bias(self) -> str:
        return f"Nickel/cp/{self.night}/bias/{self.run_ts}"

    @property
    def cp_bias_run(self) -> str:
        return f"{self.cp_bias}/run"

    @property
    def cp_flat(self) -> str:
        return f"Nickel/cp/{self.night}/flat/{self.run_ts}"

    @property
    def cp_flat_run(self) -> str:
        return f"{self.cp_flat}/run"

    @property
    def curated_run(self) -> str:
        return f"Nickel/calib/curated/{self.run_ts}"

    @property
    def curated_chain(self) -> str:
        return "Nickel/calib/curated"

    @property
    def calib_out(self) -> str:
        return f"Nickel/calib/{self.night}"

    @property
    def calib_chain(self) -> str:
        return "Nickel/calib/current"

    # Science processing
    @property
    def science_parent(self) -> str:
        return f"Nickel/runs/{self.night}/processCcd/{self.run_ts}"

    @property
    def science_run(self) -> str:
        return f"{self.science_parent}/run"

    @property
    def coadd_parent(self) -> str:
        return f"Nickel/runs/{self.night}/coadd/{self.run_ts}"

    @property
    def coadd_run(self) -> str:
        return f"{self.coadd_parent}/run"

    # Difference imaging
    @property
    def diff_parent(self) -> str:
        return f"Nickel/runs/{self.night}/diff/{self.run_ts}"

    @property
    def diff_run(self) -> str:
        return f"{self.diff_parent}/run"


# Standard chains
REFCATS_CHAIN = "refcats"
SKYMAPS_CHAIN = "skymaps/nickelRings"
SKYMAP_NAME = "nickelRings-v1"
INSTRUMENT = "lsst.obs.nickel.Nickel"
