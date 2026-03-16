"""Shared pipeline utilities."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


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
    Uses a 30-day window (±15 days) so Butler can find calibrations
    from nearby nights when a specific band's flat is missing on a
    given night.  When multiple certified calibrations overlap a
    science exposure's date, Butler picks the most-recently-prepended
    entry in the calib chain, so the same-night calibration is still
    preferred.

    Args:
        night: Observing night (YYYYMMDD)

    Returns:
        Tuple of (begin_date, end_date) in ISO format
    """
    from datetime import timedelta

    dt = datetime.strptime(night, "%Y%m%d").replace(tzinfo=timezone.utc)
    begin_dt = dt - timedelta(days=15)
    end_dt = dt + timedelta(days=15)
    return (
        begin_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def night_to_day_obs(night: str, day_obs_offset: int = 1) -> str:
    """Convert observing night (local) to UT day_obs.

    Lick observations starting on local night YYYYMMDD have
    UT dates of YYYYMMDD+1 in FITS headers.

    Args:
        night: Local observing night (YYYYMMDD)
        day_obs_offset: Days to add to the observing night to get the UT
            day_obs (default 1, for western-hemisphere observatories like
            Lick where observations cross midnight UT)

    Returns:
        UT day_obs (YYYYMMDD)
    """
    from datetime import timedelta

    dt = datetime.strptime(night, "%Y%m%d")
    return (dt + timedelta(days=day_obs_offset)).strftime("%Y%m%d")


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


def find_bad_coord_exposures(
    config: Config,
    night: str,
    target_ra: float,
    target_dec: float,
    *,
    object_filter: str | None = None,
    tolerance_deg: float = 5.0,
    instrument_name: str = "Nickel",
    day_obs_offset: int = 1,
) -> list[int]:
    """Find exposures with coordinates far from the expected target.

    Queries Butler for exposure records and compares tracking_ra/tracking_dec
    against the expected target coordinates. Exposures outside the tolerance
    are returned for exclusion from the data query.

    This catches the Nickel telescope's known issue where the DEC keyword
    gets "stuck" at a previous pointing's value, causing both CRVAL2 and DEC
    to agree on a wrong coordinate (defeating the translator's fallback).

    Args:
        config: Pipeline configuration
        night: Observing night (YYYYMMDD)
        target_ra: Expected target RA in degrees
        target_dec: Expected target Dec in degrees
        object_filter: Optional object name to restrict query
        tolerance_deg: Max offset in degrees before flagging (default: 5.0)
        instrument_name: Butler instrument name to use in WHERE clause
            (default: "Nickel")
        day_obs_offset: Days to add to the observing night to get UT day_obs
            (default: 1, for western-hemisphere observatories like Lick)

    Returns:
        Sorted list of exposure IDs with bad coordinates
    """
    from obs_nickel_data_tools.core.stack import run_butler_python_json

    day_obs = night_to_day_obs(night, day_obs_offset=day_obs_offset)

    # Build WHERE clause
    where = (
        f"instrument='{instrument_name}' AND exposure.observation_type='science'"
        f" AND exposure.day_obs={day_obs}"
    )
    if object_filter:
        where += f" AND exposure.target_name='{object_filter}'"

    script = f"""
import json
from lsst.daf.butler import Butler

butler = Butler("{config.repo}")
records = list(butler.registry.queryDimensionRecords(
    "exposure",
    where="{where}",
))

results = []
for exp in records:
    results.append({{
        "id": exp.id,
        "tracking_ra": exp.tracking_ra,
        "tracking_dec": exp.tracking_dec,
        "target_name": exp.target_name,
        "physical_filter": exp.physical_filter,
    }})

print(json.dumps(results))
"""

    exposures = run_butler_python_json(script, config)
    if not exposures:
        return []

    bad_ids: list[int] = []
    for exp in exposures:
        ra = exp.get("tracking_ra")
        dec = exp.get("tracking_dec")
        if ra is None or dec is None:
            log.warning(f"Exposure {exp['id']} has no tracking coordinates, excluding")
            bad_ids.append(exp["id"])
            continue

        ra_diff = abs(ra - target_ra)
        dec_diff = abs(dec - target_dec)

        # Handle RA wrap-around
        if ra_diff > 180:
            ra_diff = 360 - ra_diff

        if ra_diff > tolerance_deg or dec_diff > tolerance_deg:
            log.warning(
                f"Exposure {exp['id']} ({exp.get('physical_filter', '?')}) has bad coordinates: "
                f"RA={ra:.4f}, Dec={dec:.4f} "
                f"(expected RA={target_ra:.4f}, Dec={target_dec:.4f}, "
                f"offset: dRA={ra_diff:.2f}, dDec={dec_diff:.2f})"
            )
            bad_ids.append(exp["id"])

    if bad_ids:
        log.info(
            f"Found {len(bad_ids)}/{len(exposures)} exposures with bad coordinates "
            f"on night {night}"
        )

    return sorted(bad_ids)


class CollectionNames:
    """Generate standard collection names for a pipeline run."""

    def __init__(
        self, night: str, run_ts: str | None = None, *, prefix: str = "Nickel"
    ):
        self.night = night
        self.run_ts = run_ts or generate_run_timestamp()
        self._prefix = prefix

    # Raw data
    @property
    def raw_run(self) -> str:
        return f"{self._prefix}/raw/{self.night}/{self.run_ts}"

    # Calibration products
    @property
    def cp_bias(self) -> str:
        return f"{self._prefix}/cp/{self.night}/bias/{self.run_ts}"

    @property
    def cp_bias_run(self) -> str:
        return f"{self.cp_bias}/run"

    @property
    def cp_flat(self) -> str:
        return f"{self._prefix}/cp/{self.night}/flat/{self.run_ts}"

    @property
    def cp_flat_run(self) -> str:
        return f"{self.cp_flat}/run"

    @property
    def curated_run(self) -> str:
        return f"{self._prefix}/calib/curated/{self.run_ts}"

    @property
    def curated_chain(self) -> str:
        return f"{self._prefix}/calib/curated"

    @property
    def calib_out(self) -> str:
        return f"{self._prefix}/calib/{self.night}"

    @property
    def calib_chain(self) -> str:
        return f"{self._prefix}/calib/current"

    # Science processing
    @property
    def science_parent(self) -> str:
        return f"{self._prefix}/runs/{self.night}/processCcd/{self.run_ts}"

    @property
    def science_run(self) -> str:
        return f"{self.science_parent}/run"

    @property
    def coadd_parent(self) -> str:
        return f"{self._prefix}/runs/{self.night}/coadd/{self.run_ts}"

    @property
    def coadd_run(self) -> str:
        return f"{self.coadd_parent}/run"

    # Difference imaging
    @property
    def diff_parent(self) -> str:
        return f"{self._prefix}/runs/{self.night}/diff/{self.run_ts}"

    @property
    def diff_run(self) -> str:
        return f"{self.diff_parent}/run"


# Standard chains
REFCATS_CHAIN = "refcats"
SKYMAPS_CHAIN = "skymaps/nickelRings"
SKYMAP_NAME = "nickelRings-v1"
INSTRUMENT = "lsst.obs.nickel.Nickel"


def parse_butler_query_output(
    output: str,
    *,
    prefix_filter: str | None = None,
) -> list[str]:
    """Parse butler query-collections or query-datasets tabular output.

    Extracts the first column (collection/dataset name) from butler CLI
    tabular output, skipping headers and separator lines.

    Args:
        output: Raw stdout from butler query-collections/query-datasets
        prefix_filter: Only return names starting with this prefix
            (e.g., "Nickel/", "templates/")

    Returns:
        List of collection/dataset names
    """
    names = []
    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip header/separator lines
        if line.startswith(("-", "=")):
            continue
        # Skip column header lines (case-insensitive)
        first_word = line.split()[0].lower() if line.split() else ""
        if first_word in ("type", "name", "collection", "dataset"):
            continue
        # Extract first column
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if prefix_filter and not name.startswith(prefix_filter):
            continue
        names.append(name)
    return names


def butler_query_has_results(output: str) -> bool:
    """Check if butler tabular output contains at least one data row.

    Useful for checking if query-datasets or query-data-ids returned results.
    """
    return len(parse_butler_query_output(output)) > 0


def parse_quanta_summary(
    output: str,
    log_file: Path | None = None,
    log_start_pos: int | None = None,
) -> tuple[int, int]:
    """Parse pipetask output for quanta success/failure counts.

    Looks for the final "Executed N quanta successfully, M failed and 0 remain"
    line in the pipetask output or log file.

    Args:
        output: Captured stdout/stderr from pipetask
        log_file: Optional path to LSST log file (checked when --no-log-tty is used)
        log_start_pos: Optional byte offset in log_file to start reading from.
            If provided, only new log lines written after this position are parsed.

    Returns:
        Tuple of (succeeded, failed) counts. Returns (0, 0) if not found.
    """
    succeeded = 0
    failed = 0
    pattern = re.compile(
        r"Executed (\d+) quanta successfully, (\d+) failed and (\d+) remain"
    )

    # Check captured output first
    for line in output.splitlines():
        m = pattern.search(line)
        if m:
            succeeded = int(m.group(1))
            failed = int(m.group(2))

    # If not found in captured output, check log file (LSST logs go there with --no-log-tty)
    if succeeded == 0 and failed == 0 and log_file and log_file.exists():
        try:
            with open(log_file) as f:
                if log_start_pos is not None:
                    f.seek(log_start_pos)
                for line in f:
                    m = pattern.search(line)
                    if m:
                        succeeded = int(m.group(1))
                        failed = int(m.group(2))
        except OSError:
            pass

    return succeeded, failed


def read_log_delta(
    log_file: Path | None,
    *,
    log_start_pos: int | None,
    max_chars: int = 8000,
) -> str:
    """Read newly appended log content after a starting byte position."""
    if not log_file or not log_file.exists():
        return ""

    try:
        with open(log_file) as f:
            if log_start_pos is not None:
                f.seek(log_start_pos)
            data = f.read()
    except OSError:
        return ""

    return data[-max_chars:] if len(data) > max_chars else data


def is_empty_qgraph(output: str) -> bool:
    """Check if pipetask output indicates an empty quantum graph."""
    return "QuantumGraph contains no quanta" in output
