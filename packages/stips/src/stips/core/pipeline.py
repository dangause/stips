"""Shared pipeline utilities."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

# Re-exported for backwards compatibility; canonical home is stips.collections.
from stips.collections import CollectionNames as CollectionNames
from stips.collections import generate_run_timestamp as generate_run_timestamp
from stips.core import butler_query

if TYPE_CHECKING:
    from stips.core.config import Config

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


def night_to_day_obs(night: str, offset_days: int = 1) -> str:
    """Convert observing night (local) to UT day_obs.

    For an instrument whose local night YYYYMMDD maps to a UT date that is
    ``offset_days`` ahead, this shifts the date accordingly. The default of 1
    preserves Nickel/Lick behavior, where observations starting on local night
    YYYYMMDD have UT dates of YYYYMMDD+1 in FITS headers. The offset is
    instrument-configurable via the profile's
    ``night_to_dayobs_offset_days``.

    Args:
        night: Local observing night (YYYYMMDD)
        offset_days: Days to add to convert local night to UT day_obs
            (default: 1, Nickel-correct)

    Returns:
        UT day_obs (YYYYMMDD)
    """
    from datetime import timedelta

    dt = datetime.strptime(night, "%Y%m%d")
    return (dt + timedelta(days=offset_days)).strftime("%Y%m%d")


def ps1_band_map(config: "Config") -> dict[str, str]:
    """Return the active profile's LOCAL-band -> PS1-band map (empty if no profile).

    This is the single source of truth for the band->template policy (F-011):
    the KEYS are the local science bands eligible for external PS1 templates, and
    each value is the PS1 band to download for it. An empty map (no profile, or a
    fork that declares none) means "no PS1 templates" — every band then falls
    back to a coadd template in "auto" mode.
    """
    prof = getattr(config, "profile", None)
    if prof is None:
        return {}
    return dict(getattr(prof, "ps1_band_map", None) or {})


def ps1_eligible_bands(config: "Config") -> list[str]:
    """Local science bands eligible for PS1 templates (``ps1_band_map`` keys)."""
    return list(ps1_band_map(config).keys())


def night_day_obs_values(
    night: str,
    profile=None,
    *,
    offset_days: int | None = None,
) -> tuple[int, ...]:
    """Return the distinct UT ``day_obs`` values an observing night can span.

    A single local observing night can straddle UT midnight: exposures taken
    before midnight (Pacific evening) have ``day_obs == night``, while
    post-midnight exposures have ``day_obs == night + offset_days`` (what
    :func:`night_to_day_obs` returns). Butler queries must include *both* days
    or pre-midnight exposures are silently dropped.

    Args:
        night: Local observing night (YYYYMMDD)
        profile: Active instrument profile; its
            ``night_to_dayobs_offset_days`` is used when ``offset_days`` is not
            given explicitly. Defaults to 1 (Nickel-correct) when both are None.
        offset_days: Explicit local->UT offset, overriding the profile value.

    Returns:
        Tuple of distinct integer ``day_obs`` values (one value when the offset
        collapses both days onto the same date, e.g. ``offset_days=0``).
    """
    if offset_days is None:
        offset_days = profile.night_to_dayobs_offset_days if profile is not None else 1
    first = int(night)
    second = int(night_to_day_obs(night, offset_days=offset_days))
    if second == first:
        return (first,)
    return (first, second)


def night_day_obs_expr(
    night: str,
    profile=None,
    *,
    column: str = "day_obs",
    offset_days: int | None = None,
) -> str:
    """Build a Butler WHERE fragment selecting a night's UT ``day_obs`` value(s).

    Emits ``{column} IN (a, b)`` for the two UT days an observing night spans,
    or ``{column}=a`` when the offset collapses them onto a single date. See
    :func:`night_day_obs_values` for the two-UT-day rationale.

    Args:
        night: Local observing night (YYYYMMDD)
        profile: Active instrument profile (supplies the offset).
        column: Column name to constrain (e.g. ``"day_obs"`` or
            ``"exposure.day_obs"``).
        offset_days: Explicit local->UT offset, overriding the profile value.

    Returns:
        A WHERE clause fragment (no leading ``AND``).
    """
    values = night_day_obs_values(night, profile, offset_days=offset_days)
    if len(values) == 1:
        return f"{column}={values[0]}"
    joined = ", ".join(str(v) for v in values)
    return f"{column} IN ({joined})"


def isr_config_args(
    profile, label: str = "isr", *, include_crosstalk: bool = True
) -> list[str]:
    """Build ``pipetask --config`` args from the profile's ``isr_overrides``.

    The same overrides are applied to every ISR invocation — calib build
    (``cpBiasIsr``/``cpFlatIsr``) and science (``isr``) — by passing the task
    label, so e.g. parallel-overscan settings stay consistent between the master
    bias/flat and the science frames they correct.

    When the profile declares ``crosstalk``, ``doCrosstalk=True`` is injected for
    every ISR invocation (so the certified crosstalk calib corrects the master
    bias/flat and the science frames alike). An explicit ``doCrosstalk`` in
    ``isr_overrides`` wins and is not duplicated. Pass ``include_crosstalk=False``
    for the crosstalk *measurement* ISR (``cpCrosstalkIsr``), which must not apply
    crosstalk while measuring it.
    """
    overrides = dict(getattr(profile, "isr_overrides", None) or {})
    if include_crosstalk and getattr(profile, "crosstalk", None) is not None:
        overrides.setdefault("doCrosstalk", True)
    args: list[str] = []
    for key, value in overrides.items():
        args.extend(["--config", f"{label}:{key}={value}"])
    return args


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
    instrument_name: str,
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
        instrument_name: Butler instrument name for the query
            (the active profile's name)

    Returns:
        Sorted list of exposure IDs with bad coordinates
    """
    from stips.core.stack import run_butler_python_json

    # A Lick observing night can span two UT days (Pacific evening = night,
    # post-midnight = night+1). Query both. The local->UT offset is
    # instrument-configurable via the active profile.
    day_obs_expr = night_day_obs_expr(night, config.profile, column="exposure.day_obs")

    # Build WHERE clause
    where = (
        f"instrument='{instrument_name}' AND exposure.observation_type='science'"
        f" AND {day_obs_expr}"
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
    if exposures is None:
        # The in-stack query crashed (None), which is NOT the same as "no
        # exposures matched" ([]). Silently returning [] here would disable
        # the stuck-DEC coordinate-validation safety net without anyone
        # noticing. Do not raise (degraded/offline runs must proceed), but the
        # operator must see that the check did not run.
        log.error(
            "Coordinate validation could not run (in-stack exposure query "
            "returned no result) — proceeding WITHOUT bad-coordinate exclusion."
        )
        return []
    if not exposures:
        # Genuinely no exposures matched the query; nothing to validate.
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


# Standard chains
REFCATS_CHAIN = "refcats"


def _is_processccd_parent(collection: str) -> bool:
    """True for a CHAINED processCcd parent (not a bare ``/run`` or ``/run_fb*``).

    Science processing writes RUN collections ``.../processCcd/{ts}/run`` plus
    ``.../run_fb1..3`` for fallback ``calibrateImage`` configs, all chained under
    the CHAINED parent ``.../processCcd/{ts}``. The parent is what downstream
    consumers (DIA, coadd, fphot) must use, since it aggregates the primary and
    every successful fallback RUN.
    """
    return not collection.endswith("/run") and "/run_fb" not in collection


def latest_raw_run(config: Config, night: str) -> str | None:
    """Return the newest raw-ingest collection for ``night`` (or ``None``).

    ``list_collections`` returns names sorted ascending, so the timestamped raw
    ingest collections sort oldest-first; the newest (``[-1]``) is the correct
    one to use, since a re-ingest (e.g. after a header fix) appends a newer
    timestamp that supersedes the stale earlier one.
    """
    prof = config.require_profile()
    raw_collections = (
        butler_query.list_collections(
            config,
            f"{prof.collection_prefix}/raw/{night}/*",
            prefix=f"{prof.collection_prefix}/",
        )
        or []
    )
    return raw_collections[-1] if raw_collections else None


def resolve_processccd_collections(
    config: Config,
    night: str,
    *,
    all_parents: bool = False,
    verify_datasets: bool = False,
    dataset_type: str | None = None,
    where: str = "",
) -> list[str]:
    """Resolve the processCcd science collection(s) to feed downstream steps.

    Encapsulates the "prefer the CHAINED parent over individual ``/run`` and
    ``/run_fb*`` RUNs" policy shared by DIA, coadd, and forced photometry, with a
    single, consistent tie-break: CHAINED parents are returned **newest-first**.

    Args:
        config: Pipeline configuration.
        night: Observing night (YYYYMMDD).
        all_parents: When True, return every CHAINED parent (DIA needs the union
            across disjoint band groups). When False (default), return only the
            single newest parent (fphot / coadd).
        verify_datasets: When True, keep only collections that actually contain
            ``dataset_type`` (coadd's per-band verification). Requires
            ``dataset_type``.
        dataset_type: Dataset type checked when ``verify_datasets`` is True.
        where: Optional Butler WHERE clause for the verification query
            (e.g. ``"band='r'"``).

    Returns:
        Matching collection names, newest-first. Empty list when none is found
        (or none survive verification).

    Notes:
        If **no** CHAINED parent exists for the night, this falls back to a bare
        RUN collection, preferring ``/run`` over any ``/run_fb*`` (a lone
        fallback RUN is only a partial result), and logs a WARNING — downstream
        steps normally expect the CHAINED parent.
    """
    if verify_datasets and dataset_type is None:
        raise ValueError("verify_datasets=True requires a dataset_type to check.")

    prof = config.require_profile()
    colls = (
        butler_query.list_collections(
            config,
            f"{prof.collection_prefix}/runs/{night}/processCcd/*",
            prefix=f"{prof.collection_prefix}/",
        )
        or []
    )
    if not colls:
        return []

    # Newest-first CHAINED parents.
    parents = sorted((c for c in colls if _is_processccd_parent(c)), reverse=True)

    if not parents:
        # No CHAINED parent: fall back to a bare RUN, preferring /run over a lone
        # /run_fb* (which only holds partial, fallback-config results).
        runs = sorted((c for c in colls if c.endswith("/run")), reverse=True)
        fallback_runs = sorted((c for c in colls if "/run_fb" in c), reverse=True)
        candidates = runs or fallback_runs
        if not candidates:
            return []
        chosen = candidates[0]
        log.warning(
            "No CHAINED processCcd parent for night %s; falling back to bare RUN "
            "collection %s (partial results — downstream steps normally expect "
            "the CHAINED parent).",
            night,
            chosen,
        )
        parents = [chosen]

    if verify_datasets:
        parents = [
            c
            for c in parents
            if butler_query.has_datasets(config, dataset_type, c, where=where)
        ]

    if not parents:
        return []

    return parents if all_parents else parents[:1]


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
            (e.g. (Nickel) "Nickel/", or "templates/")

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
