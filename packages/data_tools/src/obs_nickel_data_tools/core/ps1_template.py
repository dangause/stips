"""PS1 template ingestion for difference imaging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.stack import run_with_stack

if TYPE_CHECKING:
    from pathlib import Path

    from obs_nickel_data_tools.core.config import Config


@dataclass
class PS1TemplateResult:
    """Result of PS1 template ingestion."""

    success: bool
    band: str
    collection: str
    tract: int | None = None
    patch: int | None = None
    fits_path: str | None = None
    error: str | None = None


def run(
    ra: float,
    dec: float,
    band: str,
    config: Config,
    *,
    collection: str | None = None,
    tract: int | None = None,
    size: float = 0.2,
    output_dir: Path | None = None,
    degrade_seeing: float | None = None,
    overwrite: bool = False,
    log_file: Path | None = None,
) -> PS1TemplateResult:
    """Download and ingest PS1 template for DIA.

    Downloads a PS1 stacked image cutout centered on the given coordinates,
    converts it to LSST format, and ingests it as a template_coadd.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        band: Nickel band (r or i only - PS1 doesn't cover b/v)
        config: Pipeline configuration
        collection: Output collection (default: templates/ps1/{band})
        tract: Tract number (auto-determined if None)
        size: Cutout size in degrees (default: 0.2)
        output_dir: Directory for downloaded FITS files
        degrade_seeing: Convolve to this FWHM in arcsec (e.g., 2.0)
        overwrite: Replace existing template if present
        log_file: Optional path to write LSST pipeline logs

    Returns:
        PS1TemplateResult with collection and status
    """
    if band not in ("r", "i"):
        return PS1TemplateResult(
            success=False,
            band=band,
            collection=collection or f"templates/ps1/{band}",
            error=f"PS1 templates only available for r/i bands, not {band}",
        )

    if collection is None:
        collection = f"templates/ps1/{band}"

    if output_dir is None:
        output_dir = config.repo / "ps1_templates"

    # Build arguments for the ingest script
    args = [
        "python",
        "-m",
        "obs_nickel_data_tools.pipeline_tools.ingest_ps1_template",
        "--repo",
        str(config.repo),
        "--ra",
        str(ra),
        "--dec",
        str(dec),
        "--band",
        band,
        "--collection",
        collection,
        "--size",
        str(size),
        "--output-dir",
        str(output_dir),
    ]

    if tract is not None:
        args.extend(["--tract", str(tract)])

    if degrade_seeing is not None:
        args.extend(["--degrade-seeing", str(degrade_seeing)])

    if overwrite:
        args.append("--overwrite")

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)

        if result.returncode == 0:
            # Parse output to extract tract/patch if available
            tract_val = None
            patch_val = None
            fits_path = None

            for line in result.stdout.split("\n"):
                if "tract=" in line and "patch=" in line:
                    # Parse "Data ID: {'skymap': ..., 'tract': 1825, 'patch': 0, ...}"
                    import re

                    tract_match = re.search(r"'tract':\s*(\d+)", line)
                    patch_match = re.search(r"'patch':\s*(\d+)", line)
                    if tract_match:
                        tract_val = int(tract_match.group(1))
                    if patch_match:
                        patch_val = int(patch_match.group(1))
                if "FITS file:" in line:
                    fits_path = line.split("FITS file:")[-1].strip()

            return PS1TemplateResult(
                success=True,
                band=band,
                collection=collection,
                tract=tract_val,
                patch=patch_val,
                fits_path=fits_path,
            )
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return PS1TemplateResult(
                success=False,
                band=band,
                collection=collection,
                error=error_msg,
            )

    except Exception as e:
        return PS1TemplateResult(
            success=False,
            band=band,
            collection=collection,
            error=str(e),
        )


def check_exists(
    band: str,
    config: Config,
    collection: str | None = None,
) -> bool:
    """Check if PS1 template already exists in Butler.

    Args:
        band: Nickel band (r or i)
        config: Pipeline configuration
        collection: Collection to check (default: templates/ps1/{band})

    Returns:
        True if template exists
    """
    if collection is None:
        collection = f"templates/ps1/{band}"

    args = [
        "butler",
        "query-datasets",
        str(config.repo),
        "template_coadd",
        "--collections",
        collection,
    ]

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)
        # If there's output beyond the header, templates exist
        lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
        return len(lines) > 2  # Header is 2 lines
    except Exception:
        return False
