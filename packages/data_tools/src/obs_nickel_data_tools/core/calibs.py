"""Nightly calibration processing (bias, flat, defects)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import (
    INSTRUMENT,
    CollectionNames,
    get_raw_dir,
    night_to_date_range,
    validate_night,
)
from obs_nickel_data_tools.core.stack import run_butler

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class CalibsResult:
    """Result of calibration processing."""

    success: bool
    night: str
    raw_run: str
    calib_chain: str
    cp_bias: str
    cp_flat: str
    error: str | None = None


def write_curated_calibrations(
    night: str,
    config: Config,
    *,
    log_file: Path | None = None,
) -> None:
    """Write curated calibrations (defects, crosstalk) for a night.

    This is safe to call once before concurrent calibs. The curated
    calibrations are instrument-level data that only need to be written
    once per run.

    Args:
        night: Any observing night (used for raw_run collection reference)
        config: Pipeline configuration
        log_file: Optional log file path
    """
    night = validate_night(night)
    cols = CollectionNames(night)
    repo = str(config.repo)

    # Ingest raws for this night first (needed for write-curated-calibrations)
    raw_dir = get_raw_dir(config, night)
    if raw_dir.exists():
        run_butler(
            ["register-instrument", repo, INSTRUMENT],
            config,
            check=False,
            log_file=log_file,
        )
        run_butler(
            [
                "ingest-raws",
                repo,
                str(raw_dir),
                "--transfer",
                "copy",
                "--output-run",
                cols.raw_run,
            ],
            config,
            check=False,
            log_file=log_file,
        )
        run_butler(["define-visits", repo, "Nickel"], config, log_file=log_file)

    run_butler(
        [
            "write-curated-calibrations",
            repo,
            "Nickel",
            cols.raw_run,
            "--collection",
            cols.curated_run,
        ],
        config,
        log_file=log_file,
    )
    run_butler(
        [
            "collection-chain",
            repo,
            cols.curated_chain,
            cols.curated_run,
            "--mode",
            "redefine",
        ],
        config,
        log_file=log_file,
    )


def run(
    night: str,
    config: Config,
    *,
    jobs: int = 4,
    log_file: Path | None = None,
    executor=None,
    skip_curated: bool = False,
) -> CalibsResult:
    """Run nightly calibration processing.

    This performs:
    1. Ingest raw data
    2. Write curated calibrations (defects from obs_nickel_data)
    3. Build and certify bias frames
    4. Build and certify flat frames
    5. Update the unified calibration chain

    Args:
        night: Observing night (YYYYMMDD)
        config: Pipeline configuration
        jobs: Number of parallel jobs
        log_file: Optional path to write LSST pipeline logs
        skip_curated: Skip curated calibrations write (already done externally)

    Returns:
        CalibsResult with collection names and status
    """
    from obs_nickel_data_tools.core.executor import LocalExecutor

    if executor is None:
        executor = LocalExecutor()

    night = validate_night(night)
    cols = CollectionNames(night)

    raw_dir = get_raw_dir(config, night)
    if not raw_dir.exists():
        return CalibsResult(
            success=False,
            night=night,
            raw_run=cols.raw_run,
            calib_chain=cols.calib_chain,
            cp_bias=cols.cp_bias,
            cp_flat=cols.cp_flat,
            error=f"Raw directory not found: {raw_dir}",
        )

    repo = str(config.repo)

    # Ensure cp_pipe is configured
    if not config.cp_pipe_dir:
        return CalibsResult(
            success=False,
            night=night,
            raw_run=cols.raw_run,
            calib_chain=cols.calib_chain,
            cp_bias=cols.cp_bias,
            cp_flat=cols.cp_flat,
            error="CP_PIPE_DIR not configured",
        )

    try:
        # Register instrument (idempotent)
        run_butler(
            ["register-instrument", repo, INSTRUMENT],
            config,
            check=False,
            log_file=log_file,
        )

        # Ingest raws
        run_butler(
            [
                "ingest-raws",
                repo,
                str(raw_dir),
                "--transfer",
                "copy",
                "--output-run",
                cols.raw_run,
            ],
            config,
            check=False,  # May fail if already ingested
            log_file=log_file,
        )

        # Define visits
        run_butler(["define-visits", repo, "Nickel"], config, log_file=log_file)

        # Write curated calibrations (skip if already done by orchestrator)
        if not skip_curated:
            run_butler(
                [
                    "write-curated-calibrations",
                    repo,
                    "Nickel",
                    cols.raw_run,
                    "--collection",
                    cols.curated_run,
                ],
                config,
                log_file=log_file,
            )
            run_butler(
                [
                    "collection-chain",
                    repo,
                    cols.curated_chain,
                    cols.curated_run,
                    "--mode",
                    "redefine",
                ],
                config,
                log_file=log_file,
            )

        # Build bias
        qg_bias = config.repo / "qgraphs" / f"cp_bias_{night}_{cols.run_ts}.qg"
        qg_bias.parent.mkdir(parents=True, exist_ok=True)
        bias_ok = False

        try:
            executor.run_pipetask(
                [
                    "qgraph",
                    "-b",
                    repo,
                    "-p",
                    str(config.cp_pipe_dir / "pipelines/_ingredients/cpBias.yaml"),
                    "-i",
                    f"{cols.curated_chain},{cols.raw_run}",
                    "-o",
                    cols.cp_bias,
                    "--output-run",
                    cols.cp_bias_run,
                    "--save-qgraph",
                    str(qg_bias),
                    "-d",
                    "instrument='Nickel' AND exposure.observation_type='bias'",
                ],
                config,
                log_file=log_file,
            )

            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    repo,
                    "-g",
                    str(qg_bias),
                    "-j",
                    str(jobs),
                    "--register-dataset-types",
                ],
                config,
                check=False,
                log_file=log_file,
            )
            if result.returncode != 0:
                log.warning(
                    f"Bias pipeline had partial failures for {night} "
                    f"(exit code {result.returncode}). "
                    "Certifying successfully-built products."
                )
            bias_ok = True
        except Exception as e:
            log.warning(f"Bias qgraph/setup failed for {night}: {e}")

        if bias_ok:
            run_butler(
                [
                    "collection-chain",
                    repo,
                    cols.cp_bias,
                    cols.cp_bias_run,
                    "--mode",
                    "redefine",
                ],
                config,
                log_file=log_file,
            )

            # Certify bias (check=False to handle already-certified case)
            begin_iso, end_iso = night_to_date_range(night)
            run_butler(
                [
                    "certify-calibrations",
                    repo,
                    cols.cp_bias,
                    cols.calib_out,
                    "bias",
                    "--begin-date",
                    begin_iso,
                    "--end-date",
                    end_iso,
                ],
                config,
                check=False,
                log_file=log_file,
            )
        else:
            begin_iso, end_iso = night_to_date_range(night)

        # Build flat (continue even if bias had issues — certify what succeeds)
        qg_flat = config.repo / "qgraphs" / f"cp_flat_{night}_{cols.run_ts}.qg"
        flat_ok = False

        try:
            executor.run_pipetask(
                [
                    "qgraph",
                    "-b",
                    repo,
                    "-p",
                    str(config.cp_pipe_dir / "pipelines/_ingredients/cpFlat.yaml"),
                    "-i",
                    f"{cols.curated_chain},{cols.raw_run},{cols.calib_out},{cols.cp_bias_run}",
                    "-o",
                    cols.cp_flat,
                    "--output-run",
                    cols.cp_flat_run,
                    "--save-qgraph",
                    str(qg_flat),
                    "-d",
                    "instrument='Nickel' AND exposure.observation_type='flat'",
                    "-c",
                    "cpFlatIsr:doDark=False",
                    "-c",
                    "cpFlatIsr:doOverscan=True",
                ],
                config,
                log_file=log_file,
            )

            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    repo,
                    "-g",
                    str(qg_flat),
                    "-j",
                    str(jobs),
                    "--register-dataset-types",
                ],
                config,
                check=False,
                log_file=log_file,
            )
            if result.returncode != 0:
                log.warning(
                    f"Flat pipeline had partial failures for {night} "
                    f"(exit code {result.returncode}). "
                    "Certifying successfully-built products."
                )
            flat_ok = True
        except Exception as e:
            log.warning(f"Flat qgraph/setup failed for {night}: {e}")

        if flat_ok:
            run_butler(
                [
                    "collection-chain",
                    repo,
                    cols.cp_flat,
                    cols.cp_flat_run,
                    "--mode",
                    "redefine",
                ],
                config,
                log_file=log_file,
            )

            # Certify flat
            run_butler(
                [
                    "certify-calibrations",
                    repo,
                    cols.cp_flat,
                    cols.calib_out,
                    "flat",
                    "--begin-date",
                    begin_iso,
                    "--end-date",
                    end_iso,
                ],
                config,
                check=False,
                log_file=log_file,
            )

        # Always update unified calib chain (certify what we have)
        run_butler(
            [
                "collection-chain",
                repo,
                cols.calib_chain,
                cols.calib_out,
                cols.curated_chain,
                "--mode",
                "prepend",
            ],
            config,
            check=False,
            log_file=log_file,
        )

        if not bias_ok and not flat_ok:
            return CalibsResult(
                success=False,
                night=night,
                raw_run=cols.raw_run,
                calib_chain=cols.calib_chain,
                cp_bias=cols.cp_bias,
                cp_flat=cols.cp_flat,
                error=f"Both bias and flat pipelines failed for {night}",
            )

        return CalibsResult(
            success=True,
            night=night,
            raw_run=cols.raw_run,
            calib_chain=cols.calib_chain,
            cp_bias=cols.cp_bias,
            cp_flat=cols.cp_flat,
        )

    except Exception as e:
        return CalibsResult(
            success=False,
            night=night,
            raw_run=cols.raw_run,
            calib_chain=cols.calib_chain,
            cp_bias=cols.cp_bias,
            cp_flat=cols.cp_flat,
            error=str(e),
        )
