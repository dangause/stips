"""Nightly calibration processing (bias, flat, defects)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import (
    INSTRUMENT,
    CollectionNames,
    get_raw_dir,
    night_to_date_range,
    validate_night,
)
from obs_nickel_data_tools.core.stack import run_butler, run_pipetask

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config


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


def run(
    night: str,
    config: Config,
    *,
    jobs: int = 4,
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

    Returns:
        CalibsResult with collection names and status
    """
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
        run_butler(["register-instrument", repo, INSTRUMENT], config, check=False)

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
        )

        # Define visits
        run_butler(["define-visits", repo, "Nickel"], config)

        # Write curated calibrations
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
        )

        # Build bias
        qg_bias = config.repo / "qgraphs" / f"cp_bias_{night}_{cols.run_ts}.qg"
        qg_bias.parent.mkdir(parents=True, exist_ok=True)

        run_pipetask(
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
        )

        run_pipetask(
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
        )

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
            check=False,  # May already exist from previous run
        )

        # Build flat
        qg_flat = config.repo / "qgraphs" / f"cp_flat_{night}_{cols.run_ts}.qg"

        run_pipetask(
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
        )

        run_pipetask(
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
        )

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
            check=False,  # May already exist
        )

        # Update unified calib chain
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
