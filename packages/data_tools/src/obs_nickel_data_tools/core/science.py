"""Science processing (ISR, calibration, source detection)."""

from __future__ import annotations

import logging
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
    parse_bad_exposures,
    validate_night,
)
from obs_nickel_data_tools.core.stack import run_butler, run_pipetask

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


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
    repo = str(config.repo)

    # Query all unique target names
    where = "instrument='Nickel' AND exposure.observation_type='science'"
    if night:
        from obs_nickel_data_tools.core.pipeline import night_to_day_obs

        day_obs = night_to_day_obs(night)
        where += f" AND day_obs={day_obs}"

    try:
        result = run_butler(
            [
                "query-dimension-records",
                repo,
                "exposure",
                "--where",
                where,
            ],
            config,
            capture_output=True,
        )

        # Parse unique target names from output
        target_names: set[str] = set()
        for line in result.stdout.splitlines():
            # Skip header lines
            if "target_name" in line.lower() or line.startswith("-"):
                continue
            parts = line.split()
            # target_name is typically the 12th column, but parse more robustly
            # by looking for the column that matches known patterns
            for part in parts:
                # Skip obvious non-target fields
                if part in ("Nickel", "science", "NEWCAM", "None", "True", "False"):
                    continue
                if part.isdigit() or "." in part or part.startswith("["):
                    continue
                if len(part) >= 3:  # Reasonable target name length
                    target_names.add(part)

        # Find matches (case-insensitive substring)
        object_lower = object_filter.lower()
        matches = [t for t in target_names if object_lower in t.lower()]

        if len(matches) == 1:
            log.info(f"Resolved object filter '{object_filter}' -> '{matches[0]}'")
            return matches[0]
        elif len(matches) > 1:
            # Prefer exact match (case-insensitive) if available
            exact = [t for t in matches if t.lower() == object_lower]
            if exact:
                log.info(
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
                f"No target_name matches for '{object_filter}'. Available: {sorted(target_names)[:10]}"
            )
            return None

    except Exception as e:
        log.warning(f"Failed to resolve object filter: {e}")
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

    # Find the raw collection for this night
    try:
        result = run_butler(
            ["query-collections", repo],
            config,
            capture_output=True,
        )
        raw_run = None
        for line in result.stdout.splitlines():
            col = line.split()[0] if line.split() else ""
            if col.startswith(f"Nickel/raw/{night}/"):
                raw_run = col
        if not raw_run:
            return ScienceResult(
                success=False,
                night=night,
                science_run=cols.science_run,
                coadd_run=None,
                error=f"No raw collection found for night {night}",
            )
    except Exception as e:
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_run,
            coadd_run=None,
            error=f"Failed to query collections: {e}",
        )

    # Build exclusion expression
    bad_ids = parse_bad_exposures(bad_exposures, bad_file)
    exclusion_expr = build_exclusion_expr(bad_ids)

    # Resolve object filter with flexible matching
    object_expr = ""
    resolved_object = None
    if object_filter:
        resolved_object = resolve_object_filter(object_filter, config, night)
        if resolved_object:
            object_expr = f" AND exposure.target_name='{resolved_object}'"
        else:
            # No match found - warn but continue (will process all science exposures)
            log.warning(
                f"Could not resolve object '{object_filter}' to exact target_name. "
                "Processing all science exposures for this night."
            )

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
            science_run=cols.science_run,
            coadd_run=None,
            error=f"No valid config files found. Tried: {science_cfg.calibrate_image}",
        )

    # Register instrument
    try:
        run_butler(["register-instrument", repo, INSTRUMENT], config, check=False)
    except Exception:
        pass  # Already registered

    # Build quantum graph for single-visit processing
    qg_dir = config.repo / "qgraphs"
    qg_dir.mkdir(parents=True, exist_ok=True)

    data_query = (
        f"instrument='Nickel' AND exposure.observation_type='science'"
        f"{object_expr}{exclusion_expr}"
    )

    # Import processing log for tracking
    from obs_nickel_data_tools.core import processing_log

    # Create processing log for this night
    plog = processing_log.create_log(night, "science")

    # Single output run - all configs write here
    output_run = cols.science_run

    # Try each config in order, using --extend-run for fallbacks
    config_used: Path | None = None
    fallback_used = False
    any_success = False

    for i, tuned_config in enumerate(configs_to_try):
        is_fallback = i > 0
        config_label = "fallback" if is_fallback else "primary"
        log.info(f"Trying {config_label} config: {tuned_config.name}")

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

            # For fallback attempts, add --extend-run to skip already-completed quanta
            if is_fallback:
                qgraph_args.append("--extend-run")

            # Build quantum graph
            run_pipetask(qgraph_args, config)

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

            # For fallback attempts, add --clobber-outputs to replace failed quanta
            if is_fallback:
                run_args.extend(["--clobber-outputs", "--extend-run"])

            # Run science processing
            result = run_pipetask(
                run_args,
                config,
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                # Full success with this config
                attempt.quanta_succeeded = 1  # Placeholder - actual count from Butler
                any_success = True
                config_used = tuned_config
                fallback_used = is_fallback
                log.info(
                    f"Science processing succeeded with {config_label} config: {tuned_config.name}"
                )
                plog.add_attempt(attempt)
                break
            else:
                # Partial failure - some quanta may have succeeded
                attempt.error = (
                    result.stderr[:500] if result.stderr else "Unknown error"
                )
                attempt.failed_exposures = processing_log.parse_pipetask_failures(
                    result.stderr or "", result.stdout or ""
                )
                attempt.quanta_failed = len(attempt.failed_exposures) or 1
                plog.add_attempt(attempt)

                # Check if we should try fallback
                if not use_fallbacks or i == len(configs_to_try) - 1:
                    log.error(f"Config failed: {tuned_config.name}")
                    if i == len(configs_to_try) - 1:
                        log.error(
                            f"All {len(configs_to_try)} configs exhausted for {night}"
                        )
                else:
                    log.warning(
                        f"{config_label} config had failures, trying fallback..."
                    )

        except Exception as e:
            error_str = str(e)
            attempt.error = error_str[:500]
            attempt.quanta_failed = 1
            plog.add_attempt(attempt)
            log.warning(
                f"{config_label.capitalize()} config failed: {tuned_config.name}"
            )
            log.debug(f"Error: {error_str}")

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

            if not is_recoverable and use_fallbacks:
                log.info(
                    "Error doesn't appear to be config-related, skipping fallbacks"
                )
                break

    # Finalize and save processing log
    plog.output_collection = output_run
    plog.finalize()
    processing_log.save_log(plog, config)

    # Check if any config succeeded
    if not any_success:
        last_error = (
            plog.configs_tried[-1].error if plog.configs_tried else "No configs tried"
        )
        return ScienceResult(
            success=False,
            night=night,
            science_run=cols.science_run,
            coadd_run=None,
            error=last_error or "All configs failed",
        )

    try:
        # Update collection chain to point to the output run
        run_butler(
            [
                "collection-chain",
                repo,
                cols.science_parent,
                output_run,
                "--mode",
                "redefine",
            ],
            config,
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
            )
            coadd_run = cols.coadd_run

        return ScienceResult(
            success=True,
            night=night,
            science_run=output_run,
            coadd_run=coadd_run,
            config_used=str(config_used) if config_used else None,
            fallback_used=fallback_used,
        )

    except Exception as e:
        return ScienceResult(
            success=False,
            night=night,
            science_run=output_run,
            coadd_run=None,
            error=str(e),
            config_used=str(config_used) if config_used else None,
            fallback_used=fallback_used,
        )
