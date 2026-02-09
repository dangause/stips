"""Nickel Processing Suite CLI.

Unified command-line interface for processing Nickel telescope data
with the LSST Science Pipelines.

Usage:
    nickel calibs 20240625
    nickel science 20240625
    nickel dia 20240625 --auto-template
    nickel env

Profiles:
    nickel -p 2023ixf dia 20230519 --auto   # Uses .env.2023ixf
    nickel -p 2020wnt calibs 20201207       # Uses .env.2020wnt
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from obs_nickel_data_tools.core import config as cfg_module


def _print_error(msg: str) -> None:
    """Print error message in red."""
    click.secho(f"Error: {msg}", fg="red", err=True)


def _print_success(msg: str) -> None:
    """Print success message in green."""
    click.secho(msg, fg="green")


def _print_info(msg: str) -> None:
    """Print info message."""
    click.echo(msg)


def _resolve_env_file(env_file: Path | None, profile: str | None) -> Path | None:
    """Resolve environment file from --env-file or --profile."""
    if env_file:
        return env_file

    if profile:
        # Try common patterns for profile env files
        candidates = [
            Path(f".env.{profile}"),
            Path(f".env.{profile}.ps1"),
            Path(f"envs/{profile}.env"),
            Path(f".env-{profile}"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # If no match found, default to .env.{profile}
        default = Path(f".env.{profile}")
        if not default.exists():
            _print_error(
                f"Profile '{profile}' not found. Tried: {', '.join(str(c) for c in candidates)}"
            )
            sys.exit(1)
        return default

    return None


@click.group()
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    help="Environment file to load (default: .env)",
)
@click.option(
    "-p",
    "--profile",
    help="Profile name (loads .env.{profile})",
)
@click.pass_context
def cli(ctx: click.Context, env_file: Path | None, profile: str | None) -> None:
    """Nickel Processing Suite - LSST pipeline tools for Nickel telescope data.

    Process Nickel 1-meter telescope observations using LSST Science Pipelines.
    Configure your environment with a .env file or environment variables.

    \b
    Quick start:
        nickel env                    # Check configuration
        nickel calibs 20240625        # Run calibrations
        nickel science 20240625       # Process science frames
        nickel dia 20240625 --auto    # Difference imaging

    \b
    Using profiles (shorthand for --env-file):
        nickel -p 2023ixf env         # Uses .env.2023ixf
        nickel -p 2020wnt calibs ...  # Uses .env.2020wnt
    """
    ctx.ensure_object(dict)

    if env_file and profile:
        _print_error("Cannot use both --env-file and --profile")
        sys.exit(1)

    resolved = _resolve_env_file(env_file, profile)
    ctx.obj["env_file"] = resolved
    ctx.obj["profile"] = profile


def _load_config(ctx: click.Context) -> cfg_module.Config:
    """Load configuration from context."""
    env_file = ctx.obj.get("env_file")
    try:
        return cfg_module.load(env_file=env_file)
    except ValueError as e:
        _print_error(str(e))
        sys.exit(1)


# =============================================================================
# env - Show configuration
# =============================================================================


@cli.command()
@click.pass_context
def env(ctx: click.Context) -> None:
    """Show current configuration and validate paths."""
    try:
        config = _load_config(ctx)
    except SystemExit:
        return

    click.echo("\nNickel Processing Suite Configuration")
    click.echo("=" * 40)

    # Show profile/env file if set
    profile = ctx.obj.get("profile")
    env_file = ctx.obj.get("env_file")
    if profile:
        click.echo(f"\n{'Profile:':<20} {profile}")
    if env_file:
        click.echo(f"{'Env file:':<20} {env_file}")

    click.echo(f"\n{'REPO:':<20} {config.repo}")
    click.echo(f"{'STACK_DIR:':<20} {config.stack_dir}")
    click.echo(f"{'OBS_NICKEL:':<20} {config.obs_nickel}")
    click.echo(f"{'RAW_PARENT_DIR:':<20} {config.raw_parent_dir}")

    if config.cp_pipe_dir:
        click.echo(f"{'CP_PIPE_DIR:':<20} {config.cp_pipe_dir}")
    if config.refcat_repo:
        click.echo(f"{'REFCAT_REPO:':<20} {config.refcat_repo}")
    if config.lick_archive_dir:
        click.echo(f"{'LICK_ARCHIVE_DIR:':<20} {config.lick_archive_dir}")

    # Validate paths
    errors = config.validate()
    if errors:
        click.echo("\n" + click.style("Validation errors:", fg="red"))
        for err in errors:
            click.echo(f"  - {err}")
        sys.exit(1)
    else:
        click.echo("\n" + click.style("✓ All paths valid", fg="green"))

    # Check stack
    click.echo("\nChecking LSST stack...", nl=False)
    from obs_nickel_data_tools.core.stack import check_stack

    if check_stack(config):
        click.echo(click.style(" ✓ available", fg="green"))
    else:
        click.echo(click.style(" ✗ not accessible", fg="red"))
        click.echo("  Make sure LSST stack is installed at STACK_DIR")


# =============================================================================
# calibs - Nightly calibrations
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=4, help="Parallel jobs (default: 4)")
@click.pass_context
def calibs(ctx: click.Context, night: str, jobs: int) -> None:
    """Run nightly calibrations (bias, flat, defects).

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel calibs 20240625
        nickel calibs 20240625 --jobs 8
    """
    config = _load_config(ctx)

    _print_info(f"Running calibrations for {night}...")

    from obs_nickel_data_tools.core import calibs as calibs_module

    result = calibs_module.run(night, config, jobs=jobs)

    if result.success:
        _print_success(f"\n✓ Calibrations complete for {night}")
        click.echo(f"  Raw collection: {result.raw_run}")
        click.echo(f"  Bias: {result.cp_bias}")
        click.echo(f"  Flat: {result.cp_flat}")
        click.echo(f"  Calib chain: {result.calib_chain}")
    else:
        _print_error(f"Calibrations failed: {result.error}")
        sys.exit(1)


# =============================================================================
# science - Science processing
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=8, help="Parallel jobs (default: 8)")
@click.option("--bad", help="Comma-separated exposure IDs to exclude")
@click.option(
    "--bad-file",
    type=click.Path(exists=True, path_type=Path),
    help="File with bad exposure IDs",
)
@click.option("--object", "object_filter", help="Filter by OBJECT header value")
@click.option("--skip-coadds", is_flag=True, help="Skip coadd generation")
@click.option(
    "--config",
    "science_config",
    type=click.Path(exists=True, path_type=Path),
    help="Override calibrateImage config",
)
@click.pass_context
def science(
    ctx: click.Context,
    night: str,
    jobs: int,
    bad: str | None,
    bad_file: Path | None,
    object_filter: str | None,
    skip_coadds: bool,
    science_config: Path | None,
) -> None:
    """Run science processing (ISR, WCS, photometry).

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel science 20240625
        nickel science 20240625 --object 2020wnt --skip-coadds
        nickel science 20240625 --bad 12345,12346
    """
    config = _load_config(ctx)

    _print_info(f"Running science processing for {night}...")

    from obs_nickel_data_tools.core import science as science_module

    result = science_module.run(
        night,
        config,
        jobs=jobs,
        bad_exposures=bad,
        bad_file=bad_file,
        object_filter=object_filter,
        skip_coadds=skip_coadds,
        science_config=science_config,
    )

    if result.success:
        _print_success(f"\n✓ Science processing complete for {night}")
        click.echo(f"  Science run: {result.science_run}")
        if result.coadd_run:
            click.echo(f"  Coadd run: {result.coadd_run}")
    else:
        _print_error(f"Science processing failed: {result.error}")
        sys.exit(1)


# =============================================================================
# dia - Difference imaging
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=8, help="Parallel jobs (default: 8)")
@click.option("-t", "--template", help="Template collection to use")
@click.option("--auto", "auto_template", is_flag=True, help="Auto-discover template")
@click.option("--prefer-ps1", is_flag=True, help="Prefer PS1 templates (with --auto)")
@click.option("-b", "--band", help="Filter by band (b/v/r/i)")
@click.option("--object", "object_filter", help="Filter by OBJECT header value")
@click.option("--bad", help="Comma-separated exposure IDs to exclude")
@click.option(
    "--bad-file",
    type=click.Path(exists=True, path_type=Path),
    help="File with bad exposure IDs",
)
@click.pass_context
def dia(
    ctx: click.Context,
    night: str,
    jobs: int,
    template: str | None,
    auto_template: bool,
    prefer_ps1: bool,
    band: str | None,
    object_filter: str | None,
    bad: str | None,
    bad_file: Path | None,
) -> None:
    """Run difference imaging analysis.

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel dia 20240625 --auto
        nickel dia 20240625 --template templates/deep/r
        nickel dia 20240625 --auto --band r --object 2020wnt
    """
    if not template and not auto_template:
        _print_error("Specify --template or --auto")
        sys.exit(1)

    config = _load_config(ctx)

    _print_info(f"Running difference imaging for {night}...")

    from obs_nickel_data_tools.core import dia as dia_module

    result = dia_module.run(
        night,
        config,
        jobs=jobs,
        template=template,
        auto_template=auto_template,
        prefer_ps1=prefer_ps1,
        band=band,
        object_filter=object_filter,
        bad_exposures=bad,
        bad_file=bad_file,
    )

    if result.success:
        _print_success(f"\n✓ Difference imaging complete for {night}")
        click.echo(f"  Template: {result.template_collection}")
        click.echo(f"  DIA run: {result.diff_run}")
        click.echo(f"  Difference images: {result.diff_image_count}")
        click.echo(f"  DIA sources: {result.dia_source_count}")
    else:
        _print_error(f"Difference imaging failed: {result.error}")
        sys.exit(1)


# =============================================================================
# download - Fetch data from archive
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("--overwrite", is_flag=True, help="Re-download existing files")
@click.pass_context
def download(ctx: click.Context, night: str, overwrite: bool) -> None:
    """Download a night from the Lick archive.

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel download 20240625
    """
    config = _load_config(ctx)

    _print_info(f"Downloading {night} from Lick archive...")

    # Use existing fetch_archive_night module
    # Build args for the existing main()
    import sys

    from obs_nickel_data_tools.pipeline_tools import fetch_archive_night

    old_argv = sys.argv
    sys.argv = [
        "obsn-archive-fetch-night",
        "--night",
        night,
        "--raw-root",
        str(config.raw_parent_dir),
    ]
    if config.lick_archive_dir:
        sys.argv.extend(["--client-path", str(config.lick_archive_dir)])
    if overwrite:
        sys.argv.append("--overwrite")

    try:
        result = fetch_archive_night.main()
        sys.argv = old_argv
        if result == 0:
            _print_success(f"✓ Downloaded {night}")
        else:
            sys.exit(result)
    except SystemExit as e:
        sys.argv = old_argv
        if e.code != 0:
            sys.exit(e.code)


# =============================================================================
# bootstrap - Initialize a new Butler repository
# =============================================================================


@cli.command()
@click.pass_context
def bootstrap(ctx: click.Context) -> None:
    """Initialize a new Butler repository.

    Creates the Butler repo, registers the instrument, ingests reference
    catalogs, and sets up the skymap. Run this once before processing data.

    \b
    Example:
        nickel -p 2023ixf bootstrap
    """
    config = _load_config(ctx)

    _print_info("Bootstrapping Butler repository...")
    _print_info(f"  Repo: {config.repo}")

    # Find the bootstrap script
    # obs_nickel could be the package dir or the monorepo root
    script_candidates = [
        config.obs_nickel.parent.parent / "scripts/pipeline/00_bootstrap_repo.sh",
        config.obs_nickel / "../../scripts/pipeline/00_bootstrap_repo.sh",
    ]

    # Also check if we're in the monorepo
    cwd = Path.cwd()
    script_candidates.insert(0, cwd / "scripts/pipeline/00_bootstrap_repo.sh")

    bootstrap_script = None
    for candidate in script_candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            bootstrap_script = resolved
            break

    if not bootstrap_script:
        _print_error(
            "Bootstrap script not found. Run from the nickel_processing_suite directory."
        )
        sys.exit(1)

    from obs_nickel_data_tools.core.stack import run_with_stack

    try:
        # Run the bootstrap script through the stack
        result = run_with_stack(
            [str(bootstrap_script)],
            config,
            check=False,
        )

        if result.returncode == 0:
            _print_success("✓ Bootstrap complete")
            click.echo(f"  Repository ready: {config.repo}")
        else:
            _print_error(f"Bootstrap failed with exit code {result.returncode}")
            sys.exit(result.returncode)

    except Exception as e:
        _print_error(f"Bootstrap failed: {e}")
        sys.exit(1)


# =============================================================================
# ps1-template - Ingest PS1 template for DIA
# =============================================================================


@cli.command("ps1-template")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option(
    "-b",
    "--band",
    required=True,
    type=click.Choice(["r", "i"]),
    help="Nickel band (r or i)",
)
@click.option(
    "-c", "--collection", help="Output collection (default: templates/ps1/{band})"
)
@click.option("--tract", type=int, help="Tract number (auto-determined if not set)")
@click.option(
    "--size", type=float, default=0.2, help="Cutout size in degrees (default: 0.2)"
)
@click.option("--degrade-seeing", type=float, help="Convolve to this FWHM in arcsec")
@click.option("--overwrite", is_flag=True, help="Replace existing template")
@click.pass_context
def ps1_template(
    ctx: click.Context,
    ra: float,
    dec: float,
    band: str,
    collection: str | None,
    tract: int | None,
    size: float,
    degrade_seeing: float | None,
    overwrite: bool,
) -> None:
    """Download and ingest PS1 template for difference imaging.

    PS1 templates are available for r and i bands only.

    \b
    Example:
        nickel ps1-template --ra 210.91 --dec 54.32 --band r
        nickel ps1-template --ra 210.91 --dec 54.32 --band i --degrade-seeing 2.0
    """
    config = _load_config(ctx)

    _print_info(f"Ingesting PS1 {band}-band template at RA={ra:.4f}, Dec={dec:.4f}...")

    from obs_nickel_data_tools.core import ps1_template as ps1_module

    # Check if already exists
    target_collection = collection or f"templates/ps1/{band}"
    if not overwrite and ps1_module.check_exists(band, config, target_collection):
        _print_info(f"PS1 template already exists in {target_collection}")
        _print_info("Use --overwrite to replace")
        return

    result = ps1_module.run(
        ra=ra,
        dec=dec,
        band=band,
        config=config,
        collection=collection,
        tract=tract,
        size=size,
        degrade_seeing=degrade_seeing,
        overwrite=overwrite,
    )

    if result.success:
        _print_success("\n✓ PS1 template ingested")
        click.echo(f"  Collection: {result.collection}")
        if result.tract is not None:
            click.echo(f"  Tract: {result.tract}, Patch: {result.patch}")
        if result.fits_path:
            click.echo(f"  FITS file: {result.fits_path}")
    else:
        _print_error(f"PS1 template ingestion failed: {result.error}")
        sys.exit(1)


# =============================================================================
# fphot - Forced photometry at RA/Dec
# =============================================================================


@cli.command("fphot")
@click.argument("night")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option("-b", "--band", help="Filter by band (default: all bands)")
@click.option(
    "--image-type",
    type=click.Choice(["visit", "diffim", "both"]),
    default="diffim",
    help="Image type for photometry (default: diffim)",
)
@click.pass_context
def fphot(
    ctx: click.Context,
    night: str,
    ra: float,
    dec: float,
    band: str | None,
    image_type: str,
) -> None:
    """Run forced photometry at specified RA/Dec coordinates.

    Performs forced photometry on calibrated visit images and/or difference images.

    \b
    Example:
        nickel fphot 20230519 --ra 210.91 --dec 54.32
        nickel fphot 20230519 --ra 210.91 --dec 54.32 --band r --image-type both
    """
    config = _load_config(ctx)

    _print_info(
        f"Running forced photometry for {night} at RA={ra:.4f}, Dec={dec:.4f}..."
    )

    from obs_nickel_data_tools.core import fphot as fphot_module

    result = fphot_module.run(
        night=night,
        ra=ra,
        dec=dec,
        config=config,
        band=band,
        image_type=image_type,
    )

    if result.success:
        _print_success(f"\n✓ Forced photometry complete for {night}")
        for coll in result.output_collections:
            click.echo(f"  Collection: {coll}")
    else:
        _print_error(f"Forced photometry failed: {result.error}")
        sys.exit(1)


# =============================================================================
# lightcurve - Extract lightcurve from DIA sources
# =============================================================================


@cli.command("lightcurve")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option(
    "--collections", required=True, help="Comma-separated DIA collections to query"
)
@click.option(
    "--radius", type=float, default=1.0, help="Match radius in arcsec (default: 1.0)"
)
@click.option(
    "--min-snr", type=float, default=3.0, help="Minimum S/N filter (default: 3.0)"
)
@click.option("-b", "--band", help="Restrict to single band")
@click.option("--name", help="Target name for plot title")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output CSV file")
@click.option("--plot/--no-plot", default=True, help="Generate plot (default: yes)")
@click.option(
    "--dataset-type",
    default="dia_source_unfiltered",
    help="Dataset type to query (default: dia_source_unfiltered). Use 'forced_phot_diffim_radec' for forced phot.",
)
@click.pass_context
def lightcurve(
    ctx: click.Context,
    ra: float,
    dec: float,
    collections: str,
    radius: float,
    min_snr: float,
    band: str | None,
    name: str | None,
    output: Path | None,
    plot: bool,
    dataset_type: str,
) -> None:
    """Extract lightcurve from DIA source catalogs or forced photometry.

    Queries source catalogs for detections near the specified coordinates
    and generates a lightcurve CSV and optional plot.

    \b
    Example (DIA sources):
        nickel lightcurve --ra 210.91 --dec 54.32 \\
            --collections "Nickel/runs/20230519/diff/*/run" --name "SN 2023ixf"

    Example (forced photometry):
        nickel lightcurve --ra 210.91 --dec 54.32 \\
            --collections "Nickel/runs/20230519/forcedPhotRaDec/*/run" \\
            --dataset-type forced_phot_diffim_radec --name "SN 2023ixf"
    """
    config = _load_config(ctx)

    _print_info(f"Extracting lightcurve at RA={ra:.4f}, Dec={dec:.4f}...")

    from obs_nickel_data_tools.core import lightcurve as lc_module

    result = lc_module.run(
        ra=ra,
        dec=dec,
        collections=collections,
        config=config,
        radius=radius,
        min_snr=min_snr,
        band=band,
        name=name,
        output=output,
        plot=plot,
        dataset_type=dataset_type,
    )

    if result.success:
        _print_success("\n✓ Lightcurve extracted")
        click.echo(f"  Detections: {result.n_detections}")
        if result.csv_path:
            click.echo(f"  CSV: {result.csv_path}")
        if result.plot_path:
            click.echo(f"  Plot: {result.plot_path}")
    else:
        _print_error(f"Lightcurve extraction failed: {result.error}")
        sys.exit(1)


# =============================================================================
# run - YAML-driven pipeline orchestrator
# =============================================================================


@cli.command("run")
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Print commands without executing")
@click.pass_context
def run_pipeline(
    ctx: click.Context,
    config_file: Path,
    dry_run: bool,
) -> None:
    """Run full pipeline from YAML configuration file.

    CONFIG_FILE is a YAML file specifying target, nights, bands, and options.

    \b
    Example YAML format:
        object: "2023ixf"
        ra: 210.910833
        dec: 54.316389
        bands: ["r", "i"]

        template:
          type: ps1
          degrade_seeing: 2.0

        nights:
          20230519:
            r: []
            i: []

        options:
          jobs: 8
          forced_phot: true
          lightcurve: true

    \b
    Example:
        nickel run scripts/config/2023ixf/pipeline.yaml
        nickel run pipeline.yaml --dry-run
    """
    config = _load_config(ctx)

    _print_info(f"Running pipeline from {config_file}...")

    if dry_run:
        _print_info("[DRY RUN] Commands will be printed but not executed")

    from obs_nickel_data_tools.core import run as run_module

    result = run_module.run(
        config_file=config_file,
        config=config,
        dry_run=dry_run,
    )

    if result.success:
        _print_success("\n✓ Pipeline complete")
        if result.template_collections:
            click.echo("  Templates:")
            for band, coll in result.template_collections.items():
                click.echo(f"    {band}: {coll}")
        if result.lightcurve_path:
            click.echo(f"  Lightcurve: {result.lightcurve_path}")
    else:
        _print_error(f"Pipeline failed: {result.error}")
        if result.failed_calibs:
            click.echo(f"  Failed calibs: {result.failed_calibs}")
        if result.failed_science:
            click.echo(f"  Failed science: {result.failed_science}")
        if result.failed_dia:
            click.echo(f"  Failed DIA: {result.failed_dia}")
        sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
