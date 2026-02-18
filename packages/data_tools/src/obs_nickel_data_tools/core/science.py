"""Science processing (ISR, calibration, source detection)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import (
    INSTRUMENT,
    REFCATS_CHAIN,
    SKYMAP_NAME,
    SKYMAPS_CHAIN,
    CollectionNames,
    build_exclusion_expr,
    find_bad_coord_exposures,
    night_to_day_obs,
    parse_bad_exposures,
    parse_butler_query_output,
    parse_quanta_summary,
    read_log_delta,
    validate_night,
)
from obs_nickel_data_tools.core.stack import (
    run_butler,
    run_butler_query,
    run_pipetask,
)

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


def _count_matching_exposures(config: "Config", where: str) -> int | None:
    """Count exposure records matching a Butler WHERE expression.

    Returns None if the query fails.
    """
    from obs_nickel_data_tools.core.stack import run_butler_python

    script = f"""
from lsst.daf.butler import Butler

butler = Butler({str(config.repo)!r})
rows = butler.registry.queryDimensionRecords("exposure", where={where!r})
print(sum(1 for _ in rows))
"""
    output = run_butler_python(script, config)
    if not output:
        return None

    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.isdigit():
            return int(line)

    return None


@dataclass
class ScienceConfig:
    """Configuration for science processing."""

    # Config file paths (relative to obs_nickel or absolute)
    calibrate_image: Path | None = None
    colorterms: Path | None = None

    # Fallback configs to try if primary fails
    calibrate_image_fallbacks: list[Path] = field(default_factory=list)

    @classmethod
    def default(cls, obs_nickel: Path) -> "ScienceConfig":
        """Create default config with standard paths."""
        configs = obs_nickel / "configs"
        return cls(
            calibrate_image=configs / "calibrateImage/tuned_configs/2023ixf_relaxed.py",
            colorterms=configs / "apply_colorterms.py",
            calibrate_image_fallbacks=[
                configs
                / "calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py",
            ],
        )


@dataclass
class ScienceResult:
    """Result of science processing."""

    success: bool
    night: str
    science_run: str
    coadd_run: str | None
    error: str | None = None
    config_used: str | None = None  # Which config file succeeded
    fallback_used: bool = False  # Whether a fallback config was used
    quanta_succeeded: int = 0
    quanta_failed: int = 0


def resolve_object_filter(
    object_filter: str,
    config: "Config",
    night: str | None = None,
) -> str | None:
    """Resolve object filter to exact target_name using flexible matching.

    Performs case-insensitive substring matching against target_name values
    in the Butler repository.

    Args:
        object_filter: User-provided object name (can be partial, any case)
        config: Pipeline configuration
        night: Optional night to restrict search

    Returns:
        Exact target_name from FITS headers, or None if no match
    """
    from obs_nickel_data_tools.core.stack import run_butler_python_json

    # Query all unique target names from Butler directly.
    where = "instrument='Nickel' AND exposure.observation_type='science'"
    if night:
        from obs_nickel_data_tools.core.pipeline import night_to_day_obs

        day_obs = night_to_day_obs(night)
        where += f" AND day_obs={day_obs}"

    script = f"""
import json
from lsst.daf.butler import Butler

butler = Butler({str(config.repo)!r})
records = butler.registry.queryDimensionRecords("exposure", where={where!r})
target_names = sorted(
    {{
        str(rec.target_name).strip()
        for rec in records
        if getattr(rec, "target_name", None) not in (None, "")
    }}
)
print(json.dumps(target_names))
"""
    target_names = run_butler_python_json(script, config)
    if not target_names:
        target_names = []

    # Find matches (case-insensitive substring)
    object_lower = object_filter.lower()
    matches = [t for t in target_names if object_lower in t.lower()]

    if len(matches) == 1:
        log.debug(f"Resolved object filter '{object_filter}' -> '{matches[0]}'")
        return matches[0]
    elif len(matches) > 1:
        # Prefer exact match (case-insensitive) if available
        exact = [t for t in matches if t.lower() == object_lower]
        if exact:
            log.debug(
                f"Resolved object filter '{object_filter}' -> '{exact[0]}' (exact)"
            )
            return exact[0]
        # Otherwise use the first match but warn
        log.warning(
            f"Multiple matches for '{object_filter}': {matches}. Using '{matches[0]}'"
        )
        return matches[0]
    else:
        log.warning(
            f"No target_name matches for '{object_filter}'. Available: {target_names[:10]}"
        )
        return None


def run(
    night: str,
    config: Config,
    *,
    jobs: int = 8,
    bad_exposures: str | None = None,
    bad_file: Path | None = None,
    object_filter: str | None = None,
    skip_coadds: bool = False,
    science_config: Path | None = None,
    science_cfg: ScienceConfig | None = None,
    use_fallbacks: bool = True,
    bands: list[str] | None = None,
    target_ra: float | None = None,
    target_dec: float | None = None,
    log_file: Path | None = None,
) -> ScienceResult:
    """Run science processing for a night.

    This performs:
    1. Single-visit processing (ISR, source detection, WCS, photometry)
    2. Optionally build coadds from the night's data

    Args:
        night: Observing night (YYYYMMDD)
        config: Pipeline configuration
        jobs: Number of parallel jobs
        bad_exposures: Comma-separated exposure IDs to exclude
        bad_file: File with exposure IDs to exclude
        object_filter: Filter by OBJECT header value (case-insensitive, partial match)
        skip_coadds: Skip coadd generation
        science_config: Override calibrateImage config file (legacy, prefer science_cfg)
        science_cfg: Full science configuration with fallbacks
        use_fallbacks: Try fallback configs on failure
        bands: Optional list of bands to process (e.g. ["r", "i"])
        target_ra: Expected target RA in degrees (enables coordinate validation)
        target_dec: Expected target Dec in degrees (enables coordinate validation)
        log_file: Optional path to write LSST pipeline logs

    Returns:
        ScienceResult with collection names and status
    """
    night = validate_night(night)
    cols = CollectionNames(night)
    repo = str(config.repo)

    # Build config chain: explicit > legacy > default
    if science_cfg is None:
        science_cfg = ScienceConfig.default(config.obs_nickel)
    if science_config is not None:
        science_cfg.calibrate_image = science_config

    # Find the raw collection for this night (targeted query)
    try:
        result = run_butler_query(
            ["query-collections", repo, f"Nickel/raw/{night}/*"],
            config,
            check=False,
        )
        raw_collections = parse_butler_query_output(
            result.stdout, prefix_filter="Nickel/"
        )
        raw_run = raw_collections[0] if raw_collections else None
        if not raw_run:
            return ScienceResult(
                success=False,
                night=night,
                science_run=cols.science_parent,
                coadd_run=None,
                error=f"No raw collection found for night {night}",
            )
    except Exception as e:
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_parent,
            coadd_run=None,
            error=f"Failed to query collections: {e}",
        )

    # Build exclusion expression
    bad_ids = parse_bad_exposures(bad_exposures, bad_file)

    # Resolve object filter with flexible matching
    object_expr = ""
    resolved_object = None
    if object_filter:
        resolved_object = resolve_object_filter(object_filter, config, night)
        if resolved_object:
            object_expr = f" AND exposure.target_name='{resolved_object}'"
        else:
            # No match found - coordinate filtering (below) can still prune by target position.
            log.warning(
                f"Could not resolve object '{object_filter}' to exact target_name. "
                "Processing all science exposures for this night."
            )

    # Pre-flight coordinate validation: find exposures with bad coordinates.
    # If object resolution failed, validate against all science exposures for the
    # night and keep only those near the requested target coordinates.
    if target_ra is not None and target_dec is not None:
        coord_filter = resolved_object if resolved_object else None
        coord_bad_ids = find_bad_coord_exposures(
            config,
            night,
            target_ra,
            target_dec,
            object_filter=coord_filter,
        )
        if coord_bad_ids:
            log.warning(
                f"Excluding {len(coord_bad_ids)} exposures with bad coordinates: "
                f"{coord_bad_ids}"
            )
            bad_ids.extend(coord_bad_ids)
            bad_ids = sorted(set(bad_ids))

    # Optional band filter (LSST dimension key: "band")
    band_expr = ""
    if bands:
        normalized_bands: list[str] = []
        for band in bands:
            b = str(band).strip().lower()
            if not b:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", b):
                raise ValueError(
                    f"Invalid band value in science bands filter: {band!r}"
                )
            normalized_bands.append(b)

        if normalized_bands:
            # Keep deterministic order while dropping duplicates.
            unique_bands = list(dict.fromkeys(normalized_bands))
            band_csv = ",".join(f"'{b}'" for b in unique_bands)
            band_expr = f" AND band IN ({band_csv})"
            log.info(f"Filtering science processing to bands: {unique_bands}")

    exclusion_expr = build_exclusion_expr(bad_ids)

    # Pipeline and config paths
    pipeline = config.obs_nickel / "pipelines" / "DRP.yaml"
    colorterms_config = (
        science_cfg.colorterms or config.obs_nickel / "configs/apply_colorterms.py"
    )

    # Build list of configs to try (primary + fallbacks)
    configs_to_try: list[Path] = []
    if science_cfg.calibrate_image and science_cfg.calibrate_image.exists():
        configs_to_try.append(science_cfg.calibrate_image)
    if use_fallbacks:
        for fb in science_cfg.calibrate_image_fallbacks:
            if fb.exists() and fb not in configs_to_try:
                configs_to_try.append(fb)

    if not configs_to_try:
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_parent,
            coadd_run=None,
            error=f"No valid config files found. Tried: {science_cfg.calibrate_image}",
        )

    day_obs = night_to_day_obs(night)
    data_query = (
        f"instrument='Nickel' AND exposure.observation_type='science'"
        f" AND day_obs={day_obs}{object_expr}{band_expr}{exclusion_expr}"
    )

    # Fail fast if this night has no matching exposures after filtering.
    match_count = _count_matching_exposures(config, data_query)
    if match_count == 0:
        reason = (
            f"No science exposures matched selection for night {night} "
            "(after object/coordinate/bad-exposure filtering)"
        )
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_parent,
            coadd_run=None,
            error=reason,
        )
    if match_count is not None:
        log.info(f"Found {match_count} matching science exposures for {night}")

    # Register instrument
    try:
        run_butler(
            ["register-instrument", repo, INSTRUMENT],
            config,
            check=False,
            log_file=log_file,
        )
    except Exception:
        pass  # Already registered

    # Build quantum graph for single-visit processing
    qg_dir = config.repo / "qgraphs"
    qg_dir.mkdir(parents=True, exist_ok=True)

    # Import processing log for tracking
    from obs_nickel_data_tools.core import processing_log

    # Create processing log for this night
    plog = processing_log.create_log(night, "science")

    # Primary output run — fallbacks get separate RUNs to avoid
    # ConflictingDefinitionError (LSST enforces config consistency per RUN).
    primary_run = cols.science_run
    successful_runs: list[str] = []  # RUNs that produced at least one quantum

    # Try each config in order, using --skip-existing-in for fallbacks
    config_used: Path | None = None
    fallback_used = False
    any_success = False
    cumulative_succeeded = 0  # Track total successes across all configs

    for i, tuned_config in enumerate(configs_to_try):
        is_fallback = i > 0
        config_label = "fallback" if is_fallback else "primary"
        log.info(f"Trying {config_label} config: {tuned_config.name}")

        # Each config attempt gets its own RUN collection.
        # Primary: .../run
        # Fallbacks: .../run_fb1, .../run_fb2, .../run_fb3
        if is_fallback:
            output_run = f"{cols.science_parent}/run_fb{i}"
        else:
            output_run = primary_run

        # Each attempt gets its own qgraph (different config = different plan)
        qg_science = qg_dir / f"processCcd_{night}_{cols.run_ts}_cfg{i}.qg"

        # Track this attempt
        attempt = processing_log.ConfigAttempt(
            config=tuned_config.name,
            is_fallback=is_fallback,
        )

        try:
            # Build qgraph arguments
            qgraph_args = [
                "qgraph",
                "-b",
                repo,
                "-p",
                f"{pipeline}#stage1-single-visit",
                "-i",
                f"{raw_run},{cols.calib_chain},{REFCATS_CHAIN},{SKYMAPS_CHAIN}",
                "-o",
                cols.science_parent,
                "--output-run",
                output_run,
                "--save-qgraph",
                str(qg_science),
                "--config-file",
                f"calibrateImage:{tuned_config}",
                "--config-file",
                f"calibrateImage:{colorterms_config}",
                "-d",
                data_query,
            ]

            # For fallback attempts, build a qgraph that excludes quanta
            # whose outputs already exist in any prior successful RUN.
            # --skip-existing-in filters at graph-build time based on _metadata
            # datasets, so the qgraph only contains the failed quanta that
            # need retrying with a different config.
            #
            # Each fallback writes to its own RUN to avoid
            # ConflictingDefinitionError (LSST enforces config consistency
            # per task label within a single RUN collection).
            if is_fallback and successful_runs:
                for prior_run in successful_runs:
                    qgraph_args.extend(["--skip-existing-in", prior_run])
                qgraph_args.append("--clobber-outputs")

            # Build quantum graph
            run_pipetask(qgraph_args, config, log_file=log_file)

            # Build run arguments
            run_args = [
                "run",
                "-b",
                repo,
                "-g",
                str(qg_science),
                "-j",
                str(jobs),
                "--register-dataset-types",
            ]

            # Fallback qgraphs are already reduced to unresolved quanta via
            # --skip-existing-in at qgraph build time; execute directly.
            log_start_pos = None
            if log_file and log_file.exists():
                try:
                    log_start_pos = log_file.stat().st_size
                except OSError:
                    pass

            # Run science processing
            result = run_pipetask(
                run_args,
                config,
                capture_output=True,
                check=False,
                log_file=log_file,
            )

            # Parse actual quanta counts from output (or log file if --no-log-tty)
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            if not combined_output.strip():
                combined_output = read_log_delta(
                    log_file, log_start_pos=log_start_pos, max_chars=8000
                )
            quanta_ok, quanta_fail = parse_quanta_summary(
                combined_output,
                log_file,
                log_start_pos=log_start_pos,
            )

            if result.returncode == 0:
                # Full success with this config
                attempt.quanta_succeeded = quanta_ok or 1
                cumulative_succeeded += quanta_ok or 1
                successful_runs.append(output_run)
                any_success = True
                config_used = tuned_config
                fallback_used = is_fallback
                if is_fallback:
                    new_wins = quanta_ok
                    log.info(
                        f"Fallback config {tuned_config.name} rescued all "
                        f"{new_wins} remaining quanta"
                    )
                else:
                    log.info(
                        f"Science processing fully succeeded with {config_label} "
                        f"config: {tuned_config.name} ({quanta_ok} quanta)"
                    )
                plog.add_attempt(attempt)
                break
            elif quanta_ok > 0:
                # Partial success - some quanta succeeded, some failed
                attempt.quanta_succeeded = quanta_ok
                attempt.quanta_failed = quanta_fail
                attempt.failed_exposures = processing_log.parse_pipetask_failures(
                    result.stderr or "", result.stdout or ""
                )
                successful_runs.append(output_run)
                any_success = True
                config_used = tuned_config
                fallback_used = is_fallback

                # Determine how many NEW successes this config produced
                if is_fallback:
                    new_wins = quanta_ok  # Fallback qgraph only has failed quanta
                    cumulative_succeeded += new_wins
                    log.warning(
                        f"Fallback config {tuned_config.name}: "
                        f"{new_wins} new quanta rescued, {quanta_fail} still failing "
                        f"(cumulative: {cumulative_succeeded} succeeded)"
                    )
                    # If this fallback rescued zero new quanta, stop trying
                    if new_wins == 0:
                        log.info(
                            "Fallback produced no new successes — remaining "
                            f"{quanta_fail} failures appear to be data-quality "
                            "issues, not config-related. Stopping fallback attempts."
                        )
                        plog.add_attempt(attempt)
                        break
                else:
                    cumulative_succeeded = quanta_ok
                    log.warning(
                        f"Partial success with primary config: {tuned_config.name} "
                        f"({quanta_ok} quanta succeeded, {quanta_fail} failed)"
                    )

                plog.add_attempt(attempt)
                # Don't break - try fallback for the remaining failures
                if not use_fallbacks or i == len(configs_to_try) - 1:
                    log.info(
                        f"Accepting partial result with {cumulative_succeeded} "
                        "successful quanta"
                    )
                    break
                else:
                    log.info(
                        f"Trying fallback config for {quanta_fail} remaining "
                        "failures..."
                    )
            else:
                # Total failure - no quanta succeeded
                attempt.error = (
                    combined_output.strip()[-500:]
                    if combined_output.strip()
                    else "Unknown error"
                )
                attempt.failed_exposures = processing_log.parse_pipetask_failures(
                    result.stderr or "", result.stdout or ""
                )
                attempt.quanta_failed = quanta_fail or 1
                plog.add_attempt(attempt)

                log.error(
                    f"No quanta succeeded with {config_label} config: "
                    f"{tuned_config.name}"
                )
                if not use_fallbacks or i == len(configs_to_try) - 1:
                    if i == len(configs_to_try) - 1:
                        log.error(
                            f"All {len(configs_to_try)} configs exhausted for "
                            f"{night}"
                        )
                else:
                    log.warning(
                        f"{config_label} config had total failure, trying "
                        "fallback..."
                    )

        except Exception as e:
            error_str = str(e)
            attempt.error = error_str[:500]
            attempt.quanta_failed = 1
            plog.add_attempt(attempt)

            # Log detailed error information
            log.warning(
                f"{config_label.capitalize()} config failed: {tuned_config.name}"
            )

            # Surface key parts of the error for diagnostics
            if "FileNotFoundError" in error_str and "astrometry_ref_cat" in error_str:
                log.error(
                    "Reference catalog not found for this field - no refcat shard available"
                )
                log.error("This usually means the field is outside the refcat coverage")
            elif "FileNotFoundError" in error_str:
                # Extract the specific file/dataset that's missing
                match = re.search(r"connection (\S+)", error_str)
                if match:
                    log.error(f"Missing required dataset: {match.group(1)}")
                log.error(f"Full error: {error_str[:200]}")
            else:
                log.error(f"Error: {error_str[:200]}")

            # Check if this is a recoverable error that fallback might help with
            recoverable_patterns = [
                "astrometry",
                "refcat",
                "WCS",
                "matches",
                "Too few",
                "not enough",
                "PSF",
                "converge",
                "FAILED",  # pipetask quantum failures
            ]
            is_recoverable = any(
                p.lower() in error_str.lower() for p in recoverable_patterns
            )

            # Don't try fallback if the issue is missing refcat
            if "FileNotFoundError" in error_str and "astrometry_ref_cat" in error_str:
                log.info("Refcat missing - skipping fallback (won't help)")
                break

            if not is_recoverable and use_fallbacks:
                log.info(
                    "Error doesn't appear to be config-related, skipping fallbacks"
                )
                break

    # Finalize and save processing log
    plog.output_collection = primary_run
    plog.finalize()
    processing_log.save_log(plog, config)

    # Use cumulative counts — cumulative_succeeded tracks unique successes
    # across all configs, and the last attempt's failure count represents
    # the remaining unresolved failures.
    total_succeeded = cumulative_succeeded
    total_failed = plog.configs_tried[-1].quanta_failed if plog.configs_tried else 0

    # Check if any config succeeded
    if not any_success:
        last_error = (
            plog.configs_tried[-1].error if plog.configs_tried else "No configs tried"
        )
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_parent,
            coadd_run=None,
            error=last_error or "All configs failed",
            quanta_succeeded=total_succeeded,
            quanta_failed=total_failed,
        )

    try:
        # Chain all successful RUN collections under the parent CHAINED
        # collection so downstream consumers (DIA, fphot) see a unified view.
        # Order matters: later runs (fallbacks) should be searched first so
        # their outputs take precedence over partial/failed primary outputs.
        chain_members = list(reversed(successful_runs))
        run_butler(
            [
                "collection-chain",
                repo,
                cols.science_parent,
                *chain_members,
                "--mode",
                "redefine",
            ],
            config,
            log_file=log_file,
        )

        coadd_run = None
        if not skip_coadds:
            # Build coadds
            qg_coadd = qg_dir / f"coadds_{night}_{cols.run_ts}.qg"

            run_pipetask(
                [
                    "qgraph",
                    "-b",
                    repo,
                    "-p",
                    f"{pipeline}#coadds-only",
                    "-i",
                    f"{cols.science_parent},{cols.calib_chain},{REFCATS_CHAIN},{SKYMAPS_CHAIN}",
                    "-o",
                    cols.coadd_parent,
                    "--output-run",
                    cols.coadd_run,
                    "--save-qgraph",
                    str(qg_coadd),
                    "-d",
                    f"instrument='Nickel' AND skymap='{SKYMAP_NAME}'",
                ],
                config,
                log_file=log_file,
            )

            run_pipetask(
                [
                    "run",
                    "-b",
                    repo,
                    "-g",
                    str(qg_coadd),
                    "-j",
                    str(jobs),
                    "--register-dataset-types",
                ],
                config,
                log_file=log_file,
            )

            run_butler(
                [
                    "collection-chain",
                    repo,
                    cols.coadd_parent,
                    cols.coadd_run,
                    "--mode",
                    "redefine",
                ],
                config,
                log_file=log_file,
            )
            coadd_run = cols.coadd_run

        return ScienceResult(
            success=True,
            night=night,
            science_run=cols.science_parent,
            coadd_run=coadd_run,
            config_used=str(config_used) if config_used else None,
            fallback_used=fallback_used,
            quanta_succeeded=total_succeeded,
            quanta_failed=total_failed,
        )

    except Exception as e:
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_parent,
            coadd_run=None,
            error=str(e),
            config_used=str(config_used) if config_used else None,
            fallback_used=fallback_used,
            quanta_succeeded=total_succeeded,
            quanta_failed=total_failed,
        )
