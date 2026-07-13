"""Science processing (ISR, calibration, source detection)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core import butler_query, quanta_report
from stips.core.pipeline import (
    REFCATS_CHAIN,
    CollectionNames,
    build_exclusion_expr,
    find_bad_coord_exposures,
    isr_config_args,
    latest_raw_run,
    night_day_obs_expr,
    parse_bad_exposures,
    parse_quanta_summary,
    read_log_delta,
    validate_night,
)
from stips.core.query import butler_str_literal
from stips.core.refcat import refcat_overlay_config
from stips.core.stack import (
    run_butler,
)

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)


def _count_matching_exposures(config: "Config", where: str) -> int | None:
    """Count exposure records matching a Butler WHERE expression.

    Returns None if the query fails.
    """
    from stips.core.stack import run_butler_python

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

    # Config file paths (resolved instrument-dir-first, else framework defaults;
    # callers may still pass relative or absolute Path values)
    calibrate_image: Path | None = None
    colorterms: Path | None = None

    # Fallback configs to try if primary fails
    calibrate_image_fallbacks: list[Path] = field(default_factory=list)

    # Reference-catalog mode; "gaia_ps1" applies the Gaia/PS1 overlay on top of
    # the tuned calibrateImage config. "monster" uses the DRP.yaml default.
    refcat_mode: str = "monster"

    @classmethod
    def default(cls, config: "Config") -> "ScienceConfig":
        """Create default config with standard paths (resolver-aware)."""
        return cls(
            calibrate_image=config.resolve_config(
                "calibrateImage/tuned_configs/2023ixf_relaxed.py"
            ),
            colorterms=config.resolve_config("apply_colorterms.py"),
            calibrate_image_fallbacks=[
                config.resolve_config(
                    "calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py"
                ),
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


def _read_landolt_target_names() -> list[str]:
    """Read fits_object names from scripts/config/landolt_validation/landolt_catalog.csv.

    Used by run() when object='landolt_validation' to filter the science qgraph
    to just Landolt-field exposures.
    """
    import csv

    # science.py → core/ → stips/ → src/ → stips/ → packages/ → repo root
    #   (parents[0]=core, [1]=stips, [2]=src, [3]=stips, [4]=packages, [5]=root)
    repo_root = Path(__file__).resolve().parents[5]
    catalog = (
        repo_root / "scripts" / "config" / "landolt_validation" / "landolt_catalog.csv"
    )
    if not catalog.exists():
        return []
    names: list[str] = []
    with open(catalog, newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("fits_object") or "").strip()
            if name:
                names.append(name)
    return names


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
    from stips.core.stack import run_butler_python_json

    prof = config.require_profile()

    # Query all unique target names from Butler directly.
    where = f"instrument='{prof.name}' AND exposure.observation_type='science'"
    if night:
        # See run() — a Lick observing night spans two UT days.
        where += f" AND {night_day_obs_expr(night, prof)}"

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
    executor=None,
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
    from stips.core.executor import LocalExecutor

    if executor is None:
        executor = LocalExecutor()

    prof = config.require_profile()
    night = validate_night(night)
    cols = CollectionNames(night, prefix=prof.collection_prefix)
    repo = str(config.repo)

    # Build config chain: explicit > legacy > default
    if science_cfg is None:
        science_cfg = ScienceConfig.default(config)
    if science_config is not None:
        science_cfg.calibrate_image = science_config

    # Find the raw collection for this night (targeted query).
    # Use the newest raw ingest — a re-ingest (e.g. after a header fix) appends
    # a newer timestamp that supersedes the stale earlier one.
    try:
        raw_run = latest_raw_run(config, night)
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
        # Special case: "landolt_validation" resolves to the list of fits_object
        # names from the Landolt reference catalog, so the science qgraph only
        # includes Landolt-field visits (not other science targets observed the
        # same night).
        if object_filter.lower() == "landolt_validation":
            names = _read_landolt_target_names()
            if names:
                quoted = ", ".join(butler_str_literal(n) for n in names)
                object_expr = f" AND exposure.target_name IN ({quoted})"
            else:
                log.warning(
                    "object='landolt_validation' but landolt_catalog.csv could not "
                    "be read. Processing all science exposures for this night."
                )
        else:
            resolved_object = resolve_object_filter(object_filter, config, night)
            if resolved_object:
                object_expr = (
                    f" AND exposure.target_name={butler_str_literal(resolved_object)}"
                )
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
            instrument_name=prof.name,
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
    pipeline = config.resolve_pipeline("DRP.yaml")
    colorterms_config = science_cfg.colorterms or config.resolve_config(
        "apply_colorterms.py"
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

    # A single Lick observing night can span two UT days: exposures taken
    # before Pacific midnight have day_obs=night, and post-midnight exposures
    # have day_obs=night+1 (what night_to_day_obs returns). Query both.
    data_query = (
        f"instrument='{prof.name}' AND exposure.observation_type='science'"
        f" AND {night_day_obs_expr(night, prof)}"
        f"{object_expr}{band_expr}{exclusion_expr}"
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

    # Register instrument. check=False already tolerates the common
    # "already registered" non-zero exit, matching dia/calibs/coadd. No
    # try/except here on purpose: the only remaining raise path is a
    # stack-activation/spawn failure, which must surface rather than be
    # silently swallowed.
    run_butler(
        ["register-instrument", repo, prof.instrument_class],
        config,
        check=False,
        log_file=log_file,
    )

    # Build quantum graph for single-visit processing
    qg_dir = config.repo / "qgraphs"
    qg_dir.mkdir(parents=True, exist_ok=True)

    # Import processing log for tracking
    from stips.core import processing_log

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
            # calibrateImage config-file chain: tuned config, then (optionally)
            # the Gaia/PS1 refcat overlay, then color terms. Order keeps color
            # terms last so they see the final photometry_ref_cat.
            config_file_args = ["--config-file", f"calibrateImage:{tuned_config}"]
            overlay_name = refcat_overlay_config(science_cfg.refcat_mode)
            if overlay_name:
                overlay_path = config.resolve_config(overlay_name)
                config_file_args += [
                    "--config-file",
                    f"calibrateImage:{overlay_path}",
                ]
            config_file_args += ["--config-file", f"calibrateImage:{colorterms_config}"]

            # Build qgraph arguments
            qgraph_args = [
                "qgraph",
                "-b",
                repo,
                "-p",
                f"{pipeline}#stage1-single-visit",
                "-i",
                f"{raw_run},{cols.calib_chain},{REFCATS_CHAIN},{prof.skymap_collection}",
                "-o",
                cols.science_parent,
                "--output-run",
                output_run,
                "--save-qgraph",
                str(qg_science),
                *config_file_args,
                "-d",
                data_query,
            ]

            # Profile-declared ISR overrides (e.g. doDefect=False for an
            # instrument without curated defect maps, or parallel overscan).
            # Applied as inline config so instruments need not fork the shared DRP
            # pipeline; the same overrides feed the calib-build ISR (calibs.py).
            qgraph_args.extend(isr_config_args(prof))

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
            executor.run_pipetask(qgraph_args, config, log_file=log_file)

            # Build run arguments
            summary_file = qg_science.with_suffix(".summary.json")
            run_args = [
                "run",
                "-b",
                repo,
                "-g",
                str(qg_science),
                "--output-run",
                output_run,
                "-j",
                str(jobs),
                "--register-dataset-types",
                *quanta_report.summary_run_args(summary_file),
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
            result = executor.run_pipetask(
                run_args,
                config,
                capture_output=True,
                check=False,
                log_file=log_file,
                output_run=output_run,
            )

            # Parse actual quanta counts. Prefer the structured --summary JSON;
            # fall back to the stdout/log regex when it is absent (e.g. the BPS
            # executor path, which does not run `pipetask run`).
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            if not combined_output.strip():
                combined_output = read_log_delta(
                    log_file, log_start_pos=log_start_pos, max_chars=8000
                )
            counts = quanta_report.parse_summary_file(summary_file)
            if counts is not None:
                quanta_ok, quanta_fail = counts
            else:
                quanta_ok, quanta_fail = parse_quanta_summary(
                    combined_output,
                    log_file,
                    log_start_pos=log_start_pos,
                )

            if result.returncode == 0:
                # Full success with this config (rc==0 => pipetask ran the
                # planned quanta). Record the true parsed count. If quanta_ok
                # is 0 here, the quanta summary could not be parsed — record
                # the honest 0 plus an explicit parse-failure marker rather
                # than fabricating a count. Success is still driven by rc==0.
                if quanta_ok == 0:
                    attempt.quanta_parse_failed = True
                    log.warning(
                        "Quanta summary could not be parsed (returncode=0); "
                        "recording 0 succeeded with quanta_parse_failed=True. "
                        "Reported counts may understate the work actually done."
                    )
                attempt.quanta_succeeded = quanta_ok
                cumulative_succeeded += quanta_ok
                successful_runs.append(output_run)
                any_success = True
                config_used = tuned_config
                fallback_used = is_fallback
                if is_fallback:
                    log.info(
                        f"Fallback config {tuned_config.name} rescued all "
                        f"{quanta_ok} remaining quanta"
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
                    # Fallback qgraphs only contain quanta that previously
                    # failed, so every success here is a new win. (quanta_ok
                    # is > 0 in this branch, so there is no "rescued nothing"
                    # case to guard — that path lands in the total-failure
                    # branch below.)
                    new_wins = quanta_ok
                    cumulative_succeeded += new_wins
                    log.warning(
                        f"Fallback config {tuned_config.name}: "
                        f"{new_wins} new quanta rescued, {quanta_fail} still failing "
                        f"(cumulative: {cumulative_succeeded} succeeded)"
                    )
                else:
                    cumulative_succeeded += quanta_ok
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
                # Record the honest parsed count. If the summary could not be
                # parsed (quanta_fail == 0 despite the non-zero returncode),
                # mark the parse failure instead of fabricating a count of 1.
                attempt.quanta_failed = quanta_fail
                if quanta_fail == 0:
                    attempt.quanta_parse_failed = True
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
            # The attempt raised before any quanta could be counted, so the
            # failure count is unknown, not 1. Leave quanta_failed at 0 and
            # mark the parse failure; the populated ``error`` field (and the
            # any_success flag) carry the failure downstream.
            attempt.quanta_parse_failed = True
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
    from stips.core import provenance

    provenance.upsert_from_log(plog, config)  # non-fatal; logs on failure

    # Use cumulative counts — cumulative_succeeded tracks unique successes
    # across all configs. Failures are NOT summed: because each fallback's
    # qgraph is reduced (via --skip-existing-in) to only the quanta that
    # previously failed, the LAST attempt's failure count is precisely the set
    # of still-unresolved quanta. Summing would double-count. Name it honestly
    # so callers know it is the last attempt's remaining failures, not a total.
    total_succeeded = cumulative_succeeded
    last_attempt_failed = (
        plog.configs_tried[-1].quanta_failed if plog.configs_tried else 0
    )

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
            quanta_failed=last_attempt_failed,
        )

    try:
        # Chain all successful RUN collections under the parent CHAINED
        # collection so downstream consumers (DIA, fphot) see a unified view.
        # Order matters: later runs (fallbacks) should be searched first so
        # their outputs take precedence over partial/failed primary outputs.
        #
        # Verify each RUN collection actually exists in the Butler before
        # chaining. BPS may report success even when all quanta failed
        # (no outputs written = no RUN collection created).
        verified_runs: list[str] = []
        for run_name in successful_runs:
            if butler_query.collection_exists(config, run_name):
                verified_runs.append(run_name)
            else:
                log.warning(
                    f"RUN collection {run_name} does not exist in Butler "
                    "(all quanta may have failed) — skipping"
                )

        if not verified_runs:
            return ScienceResult(
                success=False,
                night=night,
                science_run=cols.science_parent,
                coadd_run=None,
                error="No RUN collections were created (all quanta failed)",
                quanta_succeeded=0,
                quanta_failed=last_attempt_failed,
            )

        chain_members = list(reversed(verified_runs))
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

            executor.run_pipetask(
                [
                    "qgraph",
                    "-b",
                    repo,
                    "-p",
                    f"{pipeline}#coadds-only",
                    "-i",
                    f"{cols.science_parent},{cols.calib_chain},{REFCATS_CHAIN},{prof.skymap_collection}",
                    "-o",
                    cols.coadd_parent,
                    "--output-run",
                    cols.coadd_run,
                    "--save-qgraph",
                    str(qg_coadd),
                    "-d",
                    f"instrument='{prof.name}' AND skymap='{prof.skymap_name}'",
                ],
                config,
                log_file=log_file,
            )

            executor.run_pipetask(
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
                output_run=cols.coadd_run,
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
            quanta_failed=last_attempt_failed,
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
            quanta_failed=last_attempt_failed,
        )
