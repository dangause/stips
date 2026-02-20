"""YAML-driven pipeline orchestrator.

This module reads a YAML configuration file and orchestrates the full pipeline:
calibs → science → DIA → forced photometry → lightcurve → period analysis.

Example YAML format:
    # Environment configuration (choose one approach):
    #
    # Option 1: Reference a profile (loads .env.{profile})
    profile: "2023ixf"
    #
    # Option 2: Inline environment variables (self-contained config)
    env:
      REPO: "/path/to/butler/repo"
      STACK_DIR: "/path/to/lsst_stack"
      OBS_NICKEL: "/path/to/obs_nickel"
      RAW_PARENT_DIR: "/path/to/raw/data"

    object: "SN2023ixf"   # Must match target_name in FITS (case-insensitive partial match)
    ra: 210.910833
    dec: 54.316389
    bands: ["r", "i"]

    template:
      type: ps1           # or "coadd"
      degrade_seeing: 2.0  # optional
      nights:             # for coadd type: template nights (SN faded)
        - 20230625
        - 20230629

    science:
      nights:
        - 20230519
        - 20230521

    # Pipeline configuration files (paths relative to obs_nickel/configs/)
    configs:
      science:
        calibrate_image: calibrateImage/tuned_configs/2023ixf_relaxed.py
        calibrate_image_fallbacks:
          - calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py
        colorterms: apply_colorterms.py
      dia:
        subtract_images: dia/subtractImages.py
        detect_and_measure: dia/detectAndMeasure.py

    options:
      jobs: 8
      skip_calibs: false
      skip_science: false
      skip_dia: false
      forced_phot: true
      forced_phot_image_type: diffim  # visit, diffim, or both
      lightcurve: true
      lightcurve_dataset_type: dia_source_unfiltered  # or forced_phot_diffim_radec
      lightcurve_min_snr: 3.0
      use_fallbacks: true    # Try fallback configs on failure
      pipeline_type: supernova   # or "variable" for variable star campaigns
      period_search: false       # Enable Lomb-Scargle period search
      period_min: 0.1            # Minimum search period (days)
      period_max: 100.0          # Maximum search period (days)
      period_samples: 10000      # Frequency grid density
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config
    from obs_nickel_data_tools.core.science import ScienceConfig

log = logging.getLogger(__name__)


def _generate_run_id() -> str:
    """Generate a unique run ID for unified logging across Python and shell."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{os.getpid()}"


def _get_step_log_file(step: str, night: str = "", band: str = "") -> Path | None:
    """Get the log file path for a specific pipeline step.

    Uses RUN_LOG_DIR environment variable set by _setup_run_logging.
    Organizes logs into subdirectories by step type:
    - bootstrap/ for bootstrap logs
    - templates/ for PS1 and coadd template logs
    - calibs/ for calibration logs
    - science/ for science processing logs
    - dia/ for difference imaging logs
    - fphot/ for forced photometry logs
    - lightcurve/ for lightcurve extraction logs

    Args:
        step: Pipeline step name (e.g., "bootstrap", "calibs", "science", "dia")
        night: Optional night identifier for per-night steps
        band: Optional band identifier for per-band steps

    Returns:
        Path to log file if RUN_LOG_DIR is set, None otherwise
    """
    run_log_dir = os.environ.get("RUN_LOG_DIR")
    if not run_log_dir:
        return None

    base_dir = Path(run_log_dir)

    # Map step names to subdirectories
    # Template-related steps go into templates/{band}/
    # Matches the shell script (30_coadds.sh) directory structure
    if step in ("ps1_template", "coadd_template"):
        if band:
            step_dir = base_dir / "templates" / band
        else:
            step_dir = base_dir / "templates"
        log_name = f"{step}.log"
    # Template night processing goes into separate dirs
    elif step in ("calibs_template", "science_template"):
        base_step = step.replace("_template", "")
        step_dir = base_dir / f"{base_step}_template"
        log_name = f"{night}.log" if night else f"{step}.log"
    # Regular pipeline steps
    elif step == "bootstrap":
        step_dir = base_dir / "bootstrap"
        log_name = "bootstrap.log"
    elif step == "lightcurve":
        step_dir = base_dir / "lightcurve"
        # Support multiple lightcurve extractions (forced phot vs DIA sources)
        # The 'night' parameter is used to distinguish the type
        if night:
            log_name = f"{night}.log"  # e.g., "forced_phot.log" or "dia_sources.log"
        else:
            log_name = "lightcurve.log"
    else:
        # calibs, science, dia, fphot
        step_dir = base_dir / step
        # Build filename from night and band
        parts = []
        if night:
            parts.append(night)
        if band:
            parts.append(band)
        log_name = "_".join(parts) + ".log" if parts else f"{step}.log"

    # Create step directory
    step_dir.mkdir(parents=True, exist_ok=True)

    return step_dir / log_name


def _parse_log_data_id(line: str) -> dict[str, str] | None:
    """Extract dataId from LSST long-log format.

    LSST --long-log format includes dataId in parentheses:
        (cpBiasIsr:{instrument: 'Nickel', detector: 0, exposure: 86008005, ...})

    Returns:
        Dictionary with task_label and dataId fields, or None if not found.
    """
    match = re.search(r"\((\w+):\{([^}]+)\}\)", line)
    if not match:
        return None

    data_id: dict[str, str] = {"task_label": match.group(1)}
    for kv in re.finditer(r"(\w+):\s*('([^']*)'|(\d+)|(\w+))", match.group(2)):
        data_id[kv.group(1)] = kv.group(3) or kv.group(4) or kv.group(5)
    return data_id


def _split_step_logs(run_log_dir: Path) -> None:
    """Split interleaved step log files by exposure for easier reading.

    After a pipeline run, walks all step log directories and splits any log
    file with multiple exposures into per-exposure files within a subdirectory.

    For example:
        calibs/20230519.log  →  calibs/20230519/
                                  _general.log        (ingest, defineVisits, qgraph, etc.)
                                  exp85950225.log     (all tasks for this exposure)
                                  exp85950236.log
                                  exp86203012.log
    """
    step_dirs = [
        "calibs",
        "science",
        "dia",
        "fphot",
        "calibs_template",
        "science_template",
        "templates",
    ]

    for step_name in step_dirs:
        step_dir = run_log_dir / step_name
        if not step_dir.is_dir():
            continue

        for log_file in step_dir.glob("*.log"):
            _split_single_log(log_file)


def _split_single_log(log_file: Path) -> None:
    """Split a single log file by exposure/visit into a subdirectory.

    Each exposure (or visit, for DIA/fphot steps) gets one file containing
    all log lines (across all tasks) for that identifier. Lines without a
    dataId go into _general.log.
    """
    with open(log_file) as f:
        lines = f.readlines()

    grouped: dict[str, list[str]] = defaultdict(list)
    current_exposure = "_general"

    for line in lines:
        data_id = _parse_log_data_id(line)
        if data_id:
            # Calibs use "exposure", DIA/fphot use "visit"
            current_exposure = (
                data_id.get("exposure") or data_id.get("visit") or "_general"
            )
        grouped[current_exposure].append(line)

    # Only split if there are multiple exposures
    real_exposures = [k for k in grouped if k != "_general"]
    if len(real_exposures) <= 1:
        return

    split_dir = log_file.with_suffix("")
    split_dir.mkdir(parents=True, exist_ok=True)

    for exposure, exp_lines in sorted(grouped.items()):
        if exposure == "_general":
            out_path = split_dir / "_general.log"
        else:
            out_path = split_dir / f"exp{exposure}.log"
        with open(out_path, "w") as f:
            f.writelines(exp_lines)

    log.debug(
        f"Split {log_file.name} → {split_dir.name}/ "
        f"({len(real_exposures)} exposures + general)"
    )


def _maybe_split_log(log_file: Path | None) -> None:
    """Split a log file by exposure if it exists and has multiple exposures."""
    if log_file and log_file.exists():
        _split_single_log(log_file)


def _setup_run_logging(run_id: str, config: Config) -> Path:
    """Set up unified logging directory for a pipeline run.

    Creates the run log directory and adds a FileHandler so all Python
    log output is captured alongside the shell script logs.

    Also sets RUN_ID in os.environ so child shell scripts (via
    run_with_stack) inherit it and write to the same directory.

    Args:
        run_id: Unique run identifier
        config: Pipeline configuration

    Returns:
        Path to the run log directory
    """
    # Use the same LOG_ROOT as logging.sh: {REPO_ROOT}/logs
    # REPO_ROOT is the monorepo root (obs_nickel.parent.parent)
    repo_root = config.obs_nickel.parent.parent
    log_root = repo_root / "logs"
    run_log_dir = log_root / run_id

    run_log_dir.mkdir(parents=True, exist_ok=True)

    # Set RUN_ID in environment so shell scripts (via run_with_stack)
    # inherit it and their logging.sh uses the same directory
    os.environ["RUN_ID"] = run_id

    # Set RUN_LOG_DIR in environment so child modules can access it
    os.environ["RUN_LOG_DIR"] = str(run_log_dir)

    # Add a file handler for Python-level logs
    pipeline_log = run_log_dir / "pipeline.log"
    file_handler = logging.FileHandler(pipeline_log)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    )

    # Add to root logger so all core modules' logs are captured
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Write run metadata
    run_info = run_log_dir / "run_info.txt"
    with open(run_info, "w") as f:
        f.write(f"Run ID: {run_id}\n")
        f.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Repository: {config.repo}\n")
        f.write(f"Pipeline log: {pipeline_log}\n")
        f.write(f"Log directory: {run_log_dir}\n")
        f.write("")

    return run_log_dir


@dataclass
class ScienceConfigs:
    """Science processing configuration paths."""

    calibrate_image: str | None = None
    calibrate_image_fallbacks: list[str] = field(default_factory=list)
    colorterms: str | None = None


@dataclass
class DIAConfigs:
    """DIA processing configuration paths."""

    subtract_images: str | None = None
    detect_and_measure: str | None = None


@dataclass
class CoaddConfigs:
    """Coadd template building configuration paths."""

    make_direct_warp: str | None = None


@dataclass
class RunConfig:
    """Configuration parsed from YAML."""

    object_name: str
    ra: float
    dec: float
    bands: list[str]
    nights: list[str] = field(default_factory=list)

    # Template configuration
    template_type: str = "ps1"  # "ps1" or "coadd"
    template_degrade_seeing: float | None = None
    template_size: float = 0.3  # PS1 cutout size in degrees (default: 0.3)
    template_nights: list[str] = field(default_factory=list)

    # Pipeline config files
    science_configs: ScienceConfigs = field(default_factory=ScienceConfigs)
    dia_configs: DIAConfigs = field(default_factory=DIAConfigs)
    coadd_configs: CoaddConfigs = field(default_factory=CoaddConfigs)

    # Processing options
    jobs: int = 8
    skip_calibs: bool = False
    skip_science: bool = False
    skip_dia: bool = False
    forced_phot: bool = True
    forced_phot_image_type: str = "diffim"  # visit, diffim, or both
    lightcurve: bool = True
    lightcurve_dataset_type: str = "dia_source_unfiltered"
    lightcurve_min_snr: float = 3.0
    rebuild_templates: bool = False
    continue_on_error: bool = True
    use_fallbacks: bool = True

    # Variable star options
    pipeline_type: str = "supernova"  # "supernova" or "variable"
    period_search: bool = False
    period_min: float = 0.1
    period_max: float = 100.0
    period_samples: int = 10_000

    # Environment profile (optional - embedded in YAML instead of -p flag)
    profile: str | None = None

    @classmethod
    def from_yaml(cls, path: Path) -> RunConfig:
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Extract template config
        template = data.get("template", {})
        template_type = template.get("type", "ps1")
        template_degrade_seeing = template.get("degrade_seeing")
        template_size = float(template.get("size", 0.3))
        # Convert template nights to strings (YAML parses 20230519 as int)
        template_nights = [str(n) for n in template.get("nights", [])]

        # Extract options
        options = data.get("options", {})

        # Parse science nights from science.nights (preferred) or legacy nights key.
        # Preferred:  science: { nights: [20230519, ...] }
        # Legacy:     nights: [20230519, ...]  or  nights: {20230519: {r: [], ...}, ...}
        science_section = data.get("science", {})
        raw_nights = science_section.get("nights") if science_section else None
        if raw_nights is None:
            raw_nights = data.get("nights", [])

        if isinstance(raw_nights, list):
            nights = [str(n) for n in raw_nights]
        elif isinstance(raw_nights, dict):
            # Legacy dict format: keys are nights
            nights = [str(k) for k in raw_nights.keys()]
            log.debug(
                "Using legacy dict format for nights (consider migrating to list)"
            )
        else:
            nights = []

        # Extract config file paths
        configs = data.get("configs", {})
        science_cfg_data = configs.get("science", {})
        dia_cfg_data = configs.get("dia", {})

        science_configs = ScienceConfigs(
            calibrate_image=science_cfg_data.get("calibrate_image"),
            calibrate_image_fallbacks=science_cfg_data.get(
                "calibrate_image_fallbacks", []
            ),
            colorterms=science_cfg_data.get("colorterms"),
        )

        dia_configs = DIAConfigs(
            subtract_images=dia_cfg_data.get("subtract_images"),
            detect_and_measure=dia_cfg_data.get("detect_and_measure"),
        )

        coadd_cfg_data = configs.get("coadd", {})
        coadd_configs = CoaddConfigs(
            make_direct_warp=coadd_cfg_data.get("make_direct_warp"),
        )

        # Apply pipeline_type defaults
        pipeline_type = options.get("pipeline_type", "supernova")

        # Variable star default: forced phot on both visit + diffim
        if pipeline_type == "variable" and "forced_phot_image_type" not in options:
            default_fphot_type = "both"
        else:
            default_fphot_type = "diffim"

        return cls(
            object_name=data.get("object", ""),
            ra=data["ra"],
            dec=data["dec"],
            bands=data.get("bands", ["r"]),
            nights=nights,
            template_type=template_type,
            template_degrade_seeing=template_degrade_seeing,
            template_size=template_size,
            template_nights=template_nights,
            science_configs=science_configs,
            dia_configs=dia_configs,
            coadd_configs=coadd_configs,
            jobs=options.get("jobs", 8),
            skip_calibs=options.get("skip_calibs", False),
            skip_science=options.get("skip_science", False),
            skip_dia=options.get("skip_dia", False),
            forced_phot=options.get("forced_phot", True),
            forced_phot_image_type=options.get(
                "forced_phot_image_type", default_fphot_type
            ),
            lightcurve=options.get("lightcurve", True),
            lightcurve_dataset_type=options.get(
                "lightcurve_dataset_type", "dia_source_unfiltered"
            ),
            lightcurve_min_snr=float(options.get("lightcurve_min_snr", 3.0)),
            rebuild_templates=options.get("rebuild_templates", False),
            continue_on_error=options.get("continue_on_error", True),
            use_fallbacks=options.get("use_fallbacks", True),
            pipeline_type=pipeline_type,
            period_search=options.get("period_search", False),
            period_min=float(options.get("period_min", 0.1)),
            period_max=float(options.get("period_max", 100.0)),
            period_samples=int(options.get("period_samples", 10_000)),
            profile=data.get("profile"),
        )


def get_profile_from_yaml(path: Path) -> str | None:
    """Extract just the profile field from a pipeline YAML file.

    This is a lightweight function to get the profile before loading
    the full environment configuration.

    Args:
        path: Path to pipeline YAML file

    Returns:
        Profile name if specified, None otherwise
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("profile")


def get_env_from_yaml(path: Path) -> dict[str, str] | None:
    """Extract inline environment variables from a pipeline YAML file.

    This allows pipeline configs to be self-contained by embedding
    environment variables directly in the YAML.

    Args:
        path: Path to pipeline YAML file

    Returns:
        Dict of environment variables if 'env' section exists, None otherwise
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    env_section = data.get("env")
    if env_section and isinstance(env_section, dict):
        # Convert all values to strings
        return {str(k): str(v) for k, v in env_section.items()}
    return None


@dataclass
class RunResult:
    """Result of pipeline run."""

    success: bool
    failed_calibs: list[str] = field(default_factory=list)
    failed_science: list[str] = field(default_factory=list)
    failed_dia: list[str] = field(default_factory=list)
    failed_fphot: list[str] = field(default_factory=list)
    template_collections: dict[str, str] = field(default_factory=dict)
    forced_phot_collections: dict[str, list[str]] = field(default_factory=dict)
    lightcurve_path: str | None = None
    period_result_path: str | None = None
    log_dir: str | None = None
    error: str | None = None


def _get_bands_for_night(
    night: str,
    run_cfg: RunConfig,
) -> list[str]:
    """Get the bands to process for a specific night.

    Returns all top-level bands. Per-band availability is handled
    gracefully by the pipeline (empty quantum graphs, no matching
    exposures, etc.).
    """
    return list(run_cfg.bands)


def _run_ps1_templates(
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> None:
    """Ingest PS1 templates for each band."""
    from obs_nickel_data_tools.core import ps1_template

    for band in run_cfg.bands:
        if band not in ("r", "i"):
            log.warning(f"PS1 templates not available for band {band}, skipping")
            continue

        log.info(f"Ingesting PS1 template for {band}-band...")

        if not dry_run:
            ps1_log = _get_step_log_file("ps1_template", band=band)
            ps1_result = ps1_template.run(
                ra=run_cfg.ra,
                dec=run_cfg.dec,
                band=band,
                config=config,
                size=run_cfg.template_size,
                degrade_seeing=run_cfg.template_degrade_seeing,
                overwrite=run_cfg.rebuild_templates,
                log_file=ps1_log,
            )
            if ps1_result.success:
                result.template_collections[band] = ps1_result.collection
            else:
                log.warning(f"PS1 template failed for {band}: {ps1_result.error}")
        else:
            log.info(
                f"  [DRY RUN] ps1_template.run(ra={run_cfg.ra}, dec={run_cfg.dec}, band={band})"
            )
            result.template_collections[band] = f"templates/ps1/{band}"


def _run_coadd_templates(
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    science_cfg: "ScienceConfig",
    dry_run: bool,
) -> RunResult | None:
    """Build coadd templates: process template nights, then coadd per band.

    Returns a RunResult early-exit if continue_on_error is False and a step fails,
    or None to continue normally.
    """
    from obs_nickel_data_tools.core import calibs, coadd, science

    if not run_cfg.template_nights:
        log.error("Coadd template type requires template.nights in YAML")
        return RunResult(
            success=False,
            error="Coadd template type requires template.nights configuration",
        )

    # Process template nights through calibs
    if not run_cfg.skip_calibs:
        for night in run_cfg.template_nights:
            log.info(f"Running calibrations for template night {night}...")
            if not dry_run:
                calib_log = _get_step_log_file("calibs_template", night=night)
                calib_result = calibs.run(
                    night, config, jobs=run_cfg.jobs, log_file=calib_log
                )
                _maybe_split_log(calib_log)
                if not calib_result.success:
                    result.failed_calibs.append(f"template:{night}")
                    log.warning(
                        f"Calibrations failed for template night {night}: {calib_result.error}"
                    )
                    if not run_cfg.continue_on_error:
                        return RunResult(
                            success=False,
                            error=f"Template night calibrations failed for {night}",
                        )
            else:
                log.info(f"  [DRY RUN] calibs.run({night})")

    # Process template nights through science
    template_science_ran = False
    if not run_cfg.skip_science:
        for night in run_cfg.template_nights:
            bands_for_night = _get_bands_for_night(night, run_cfg)
            if not bands_for_night:
                log.info(
                    f"Skipping template-night science for {night} "
                    "(no bands configured)"
                )
                continue

            log.info(f"Running science for template night {night}...")
            if not dry_run:
                sci_log = _get_step_log_file("science_template", night=night)
                sci_result = science.run(
                    night,
                    config,
                    jobs=run_cfg.jobs,
                    object_filter=run_cfg.object_name,
                    skip_coadds=True,
                    science_cfg=science_cfg,
                    use_fallbacks=run_cfg.use_fallbacks,
                    bands=bands_for_night,
                    target_ra=run_cfg.ra,
                    target_dec=run_cfg.dec,
                    log_file=sci_log,
                )
                _maybe_split_log(sci_log)
                template_science_ran = True
                if not sci_result.success:
                    result.failed_science.append(f"template:{night}")
                    log.warning(
                        f"Science failed for template night {night}: {sci_result.error}"
                    )
                    if not run_cfg.continue_on_error:
                        return RunResult(
                            success=False,
                            error=f"Template night science failed for {night}",
                        )
            else:
                template_science_ran = True
                log.info(f"  [DRY RUN] science.run({night}, bands={bands_for_night})")

    # Build coadd templates per band
    force_rebuild_templates = template_science_ran or run_cfg.rebuild_templates
    if force_rebuild_templates and template_science_ran:
        log.info("Science was (re-)processed — forcing template rebuild")
    elif force_rebuild_templates:
        log.info("rebuild_templates=true — forcing template rebuild")

    for band in run_cfg.bands:
        log.info(f"Building coadd template for {band}-band...")

        if not dry_run:
            coadd_config_files = []
            if run_cfg.coadd_configs.make_direct_warp:
                cfg_path = (
                    config.obs_nickel
                    / "configs"
                    / run_cfg.coadd_configs.make_direct_warp
                )
                coadd_config_files.append(f"makeDirectWarp:{cfg_path}")

            coadd_log = _get_step_log_file("coadd_template", band=band)
            coadd_result = coadd.run(
                nights=run_cfg.template_nights,
                band=band,
                config=config,
                ra=run_cfg.ra,
                dec=run_cfg.dec,
                jobs=run_cfg.jobs,
                overwrite=force_rebuild_templates,
                config_files=coadd_config_files or None,
                log_file=coadd_log,
            )
            _maybe_split_log(coadd_log)
            if coadd_result.success:
                result.template_collections[band] = coadd_result.collection
                log.info(f"  Coadd template for {band}: {coadd_result.collection}")
            else:
                log.warning(f"Coadd template failed for {band}: {coadd_result.error}")
        else:
            log.info(
                f"  [DRY RUN] coadd.run(nights={run_cfg.template_nights}, band={band})"
            )
            result.template_collections[band] = f"templates/deep/tract0/{band}"

    return None


def _log_template_summary(run_cfg: RunConfig, result: RunResult) -> None:
    """Log which bands have templates and which don't."""
    built = [b for b in run_cfg.bands if b in result.template_collections]
    failed = [b for b in run_cfg.bands if b not in result.template_collections]
    if built:
        log.info(f"Templates built for bands: {', '.join(built)}")
    if failed:
        log.warning(
            f"No templates for bands: {', '.join(failed)} (DIA will be skipped for these)"
        )


def _run_calibs_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> RunResult | None:
    """Run calibrations for each science night.

    Returns a RunResult for early exit if continue_on_error is False, else None.
    """
    from obs_nickel_data_tools.core import calibs

    for night in all_nights:
        log.info(f"Running calibrations for {night}...")

        if not dry_run:
            calib_log = _get_step_log_file("calibs", night=night)
            calib_result = calibs.run(
                night, config, jobs=run_cfg.jobs, log_file=calib_log
            )
            _maybe_split_log(calib_log)
            if not calib_result.success:
                result.failed_calibs.append(night)
                log.warning(f"Calibrations failed for {night}: {calib_result.error}")
                if not run_cfg.continue_on_error:
                    result.success = False
                    result.error = f"Calibrations failed for {night}"
                    return result
        else:
            log.info(f"  [DRY RUN] calibs.run({night})")

    return None


def _run_science_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    science_cfg: "ScienceConfig",
    dry_run: bool,
) -> RunResult | None:
    """Run science processing for each night.

    Returns a RunResult for early exit if continue_on_error is False, else None.
    """
    from obs_nickel_data_tools.core import science

    for night in all_nights:
        if night in result.failed_calibs:
            log.info(f"Skipping science for {night} (calibrations failed)")
            result.failed_science.append(night)
            continue

        bands_for_night = _get_bands_for_night(night, run_cfg)
        if not bands_for_night:
            log.info(f"Skipping science for {night} (no bands configured)")
            continue

        log.info(f"Running science for {night}...")

        if not dry_run:
            sci_log = _get_step_log_file("science", night=night)
            sci_result = science.run(
                night,
                config,
                jobs=run_cfg.jobs,
                object_filter=run_cfg.object_name,
                skip_coadds=True,
                science_cfg=science_cfg,
                use_fallbacks=run_cfg.use_fallbacks,
                bands=bands_for_night,
                target_ra=run_cfg.ra,
                target_dec=run_cfg.dec,
                log_file=sci_log,
            )
            _maybe_split_log(sci_log)
            if not sci_result.success:
                result.failed_science.append(night)
                log.warning(f"Science failed for {night}: {sci_result.error}")
                if not run_cfg.continue_on_error:
                    result.success = False
                    result.error = f"Science failed for {night}"
                    return result
            elif sci_result.fallback_used:
                log.info(
                    f"  Note: {night} used fallback config: {sci_result.config_used}"
                )
        else:
            log.info(f"  [DRY RUN] science.run({night}, bands={bands_for_night})")

    return None


def _run_dia_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> RunResult | None:
    """Run DIA per night per band.

    Returns a RunResult for early exit if continue_on_error is False, else None.
    """
    from obs_nickel_data_tools.core import dia

    for night in all_nights:
        if night in result.failed_science:
            log.info(f"Skipping DIA for {night} (science processing failed)")
            bands_for_night = _get_bands_for_night(night, run_cfg)
            for band in bands_for_night:
                result.failed_dia.append(f"{night}/{band}")
            continue

        bands_for_night = _get_bands_for_night(night, run_cfg)
        if not bands_for_night:
            log.info(f"Skipping DIA for {night} (no bands configured)")
            continue

        for band in bands_for_night:
            template_coll = result.template_collections.get(band)
            if template_coll is None:
                log.warning(f"Skipping DIA for {night}/{band} (no template available)")
                result.failed_dia.append(f"{night}/{band}")
                continue

            log.info(f"Running DIA for {night}/{band}...")

            if not dry_run:
                dia_log = _get_step_log_file("dia", night=night, band=band)

                # Resolve DIA config file paths from YAML
                configs_dir = config.obs_nickel / "configs"
                subtract_cfg = None
                if run_cfg.dia_configs.subtract_images:
                    subtract_cfg = configs_dir / run_cfg.dia_configs.subtract_images
                detect_cfg = None
                if run_cfg.dia_configs.detect_and_measure:
                    detect_cfg = configs_dir / run_cfg.dia_configs.detect_and_measure

                dia_result = dia.run(
                    night,
                    config,
                    jobs=run_cfg.jobs,
                    template=template_coll,
                    auto_template=False,
                    prefer_ps1=run_cfg.template_type == "ps1",
                    band=band,
                    object_filter=run_cfg.object_name,
                    subtract_config_file=subtract_cfg,
                    detect_config_file=detect_cfg,
                    log_file=dia_log,
                )
                _maybe_split_log(dia_log)
                if not dia_result.success:
                    result.failed_dia.append(f"{night}/{band}")
                    log.warning(f"DIA failed for {night}/{band}: {dia_result.error}")
                    if not run_cfg.continue_on_error:
                        result.success = False
                        result.error = f"DIA failed for {night}/{band}"
                        return result
            else:
                log.info(f"  [DRY RUN] dia.run({night}, band={band})")

    return None


def _run_fphot_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> None:
    """Run forced photometry per night per successful DIA band."""
    from obs_nickel_data_tools.core import fphot

    failed_dia_set = set(result.failed_dia)

    for night in all_nights:
        bands_for_night = _get_bands_for_night(night, run_cfg)
        successful_bands = [
            b for b in bands_for_night if f"{night}/{b}" not in failed_dia_set
        ]

        if not successful_bands:
            log.info(f"Skipping forced photometry for {night} (all DIA bands failed)")
            result.failed_fphot.append(night)
            continue

        night_fphot_colls: list[str] = []
        night_had_failure = False

        for band in successful_bands:
            log.info(f"Running forced photometry for {night}/{band}...")

            if not dry_run:
                fphot_log = _get_step_log_file("fphot", night=night, band=band)
                fphot_result = fphot.run(
                    night=night,
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    config=config,
                    band=band,
                    image_type=run_cfg.forced_phot_image_type,
                    jobs=run_cfg.jobs,
                    log_file=fphot_log,
                )
                _maybe_split_log(fphot_log)
                if not fphot_result.success:
                    night_had_failure = True
                    log.warning(
                        f"Forced phot failed for {night}/{band}: {fphot_result.error}"
                    )
                else:
                    night_fphot_colls.extend(fphot_result.output_collections)
            else:
                log.info(
                    f"  [DRY RUN] fphot.run({night}, band={band}, "
                    f"image_type={run_cfg.forced_phot_image_type})"
                )

        if night_fphot_colls:
            result.forced_phot_collections[night] = night_fphot_colls
        if night_had_failure:
            result.failed_fphot.append(night)


def _run_lightcurve_step(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> None:
    """Extract lightcurve from forced photometry or DIA sources."""
    from obs_nickel_data_tools.core import lightcurve

    use_forced_phot = run_cfg.lightcurve_dataset_type.startswith("forced_phot")

    if use_forced_phot:
        collections_list = _discover_fphot_collections(
            all_nights, run_cfg, config, result, dry_run
        )
    else:
        collections_list = _discover_dia_collections(
            all_nights, run_cfg, config, result, dry_run
        )

    if not collections_list:
        source_type = "forced photometry" if use_forced_phot else "DIA"
        log.warning(
            f"No {source_type} collections found, skipping lightcurve extraction"
        )
        return

    collections = ",".join(collections_list)
    source_label = "forced phot" if use_forced_phot else "diff"
    log.info(f"Lightcurve using {len(collections_list)} {source_label} collections")

    if not dry_run:
        lc_type = "forced_phot" if use_forced_phot else "dia_sources"
        lc_log = _get_step_log_file("lightcurve", night=lc_type)
        lc_result = lightcurve.run(
            ra=run_cfg.ra,
            dec=run_cfg.dec,
            collections=collections,
            config=config,
            name=run_cfg.object_name,
            plot=True,
            min_snr=run_cfg.lightcurve_min_snr,
            dataset_type=run_cfg.lightcurve_dataset_type,
            log_file=lc_log,
        )
        if lc_result.success:
            result.lightcurve_path = lc_result.csv_path
        else:
            log.warning(f"Lightcurve extraction failed: {lc_result.error}")
    else:
        log.info("  [DRY RUN] lightcurve.run()")


def _run_period_step(
    run_cfg: RunConfig,
    result: RunResult,
    dry_run: bool,
) -> None:
    """Run period analysis on extracted lightcurve."""
    if not result.lightcurve_path:
        log.warning("No lightcurve available, skipping period search")
        return

    if not dry_run:
        from obs_nickel_data_tools.core import period

        period_log = _get_step_log_file("period")
        period_result = period.run(
            csv_path=Path(result.lightcurve_path),
            period_min=run_cfg.period_min,
            period_max=run_cfg.period_max,
            n_samples=run_cfg.period_samples,
            output_dir=Path(result.lightcurve_path).parent / "period_analysis",
            log_file=period_log,
        )
        result.period_result_path = str(period_result.output_dir)
        log.info(
            f"  Best period: {period_result.best_period:.6f} d "
            f"(FAP={period_result.fap:.2e})"
        )
    else:
        log.info("  [DRY RUN] period.run()")


def _discover_fphot_collections(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> list[str]:
    """Gather forced photometry collections for lightcurve extraction."""
    from obs_nickel_data_tools.core.pipeline import parse_butler_query_output
    from obs_nickel_data_tools.core.stack import run_butler_query

    fphot_colls: list[str] = []
    for night in all_nights:
        colls = result.forced_phot_collections.get(night, [])
        if colls:
            fphot_colls.extend(colls)

    # If no forced phot ran this session, discover from Butler
    if not fphot_colls and not dry_run:
        log.info("No forced phot from this run, discovering from Butler...")
        # When image_type is "both", search for both visit and diffim patterns
        if run_cfg.forced_phot_image_type == "both":
            fphot_suffixes = ["visit", "diffim"]
        else:
            fphot_suffixes = [run_cfg.forced_phot_image_type]
        for night in all_nights:
            for fphot_suffix in fphot_suffixes:
                try:
                    check_result = run_butler_query(
                        [
                            "query-collections",
                            str(config.repo),
                            f"Nickel/runs/{night}/forcedPhotRaDec/*/{fphot_suffix}*",
                        ],
                        config,
                        check=False,
                    )
                    if check_result.returncode == 0:
                        fphot_colls.extend(
                            parse_butler_query_output(
                                check_result.stdout,
                                prefix_filter="Nickel/runs/",
                            )
                        )
                except Exception as e:
                    log.debug(
                        f"Failed to discover fphot collections for {night}/{fphot_suffix}: {e}"
                    )
    elif not fphot_colls and dry_run:
        for night in all_nights:
            fphot_colls.append(f"Nickel/runs/{night}/forcedPhotRaDec/*/run")

    return sorted(set(fphot_colls))


def _discover_dia_collections(
    all_nights: list[str],
    run_cfg: RunConfig,
    config: Config,
    result: RunResult,
    dry_run: bool,
) -> list[str]:
    """Gather DIA diff collections for lightcurve extraction."""
    from obs_nickel_data_tools.core.pipeline import parse_butler_query_output
    from obs_nickel_data_tools.core.stack import run_butler_query

    verified: list[str] = []
    failed_night_bands = set(result.failed_dia)

    for night in all_nights:
        bands_for_night = _get_bands_for_night(night, run_cfg)
        has_success = any(
            f"{night}/{b}" not in failed_night_bands for b in bands_for_night
        )
        if not has_success:
            continue

        if not dry_run:
            try:
                check_result = run_butler_query(
                    [
                        "query-collections",
                        str(config.repo),
                        f"Nickel/runs/{night}/diff/*/run",
                    ],
                    config,
                    check=False,
                )
                if check_result.returncode == 0:
                    verified.extend(
                        parse_butler_query_output(
                            check_result.stdout,
                            prefix_filter="Nickel/runs/",
                        )
                    )
            except Exception:
                log.debug(f"Could not verify diff collection for {night}")
        else:
            verified.append(f"Nickel/runs/{night}/diff/*/run")

    return verified


def run(
    config_file: Path,
    config: Config,
    *,
    dry_run: bool = False,
) -> RunResult:
    """Run full pipeline from YAML configuration.

    This orchestrates:
    0. Bootstrap repository if needed (auto-detected)
    1. PS1 template ingestion (or coadd building) per band
    2. Calibrations per night
    3. Science processing per night
    4. DIA per night per band
    5. Forced photometry per night
    6. Lightcurve extraction
    7. Period analysis (variable stars, if period_search=true)

    Args:
        config_file: Path to YAML configuration file
        config: Pipeline configuration
        dry_run: Print commands without executing

    Returns:
        RunResult with status and any failures
    """
    from obs_nickel_data_tools.core import bootstrap
    from obs_nickel_data_tools.core.science import ScienceConfig

    # Set up unified logging directory for this pipeline run
    run_id = _generate_run_id()
    run_log_dir = _setup_run_logging(run_id, config)
    log.info(f"Logs: {run_log_dir}")

    # Step 0: Check if bootstrap is needed
    if bootstrap.needs_bootstrap(config):
        log.info(f"Repository not initialized, running bootstrap: {config.repo}")
        if not dry_run:
            bootstrap_log = _get_step_log_file("bootstrap")
            bootstrap_result = bootstrap.run(config, log_file=bootstrap_log)
            if not bootstrap_result.success:
                return RunResult(
                    success=False,
                    error=f"Bootstrap failed: {bootstrap_result.error}",
                    log_dir=str(run_log_dir),
                )
            log.info("Bootstrap complete")
        else:
            log.info("[DRY RUN] Would run bootstrap")

    # Load run configuration
    run_cfg = RunConfig.from_yaml(config_file)

    # Build ScienceConfig from YAML paths
    configs_dir = config.obs_nickel / "configs"
    science_cfg = ScienceConfig.default(config.obs_nickel)

    if run_cfg.science_configs.calibrate_image:
        science_cfg.calibrate_image = (
            configs_dir / run_cfg.science_configs.calibrate_image
        )
    if run_cfg.science_configs.colorterms:
        science_cfg.colorterms = configs_dir / run_cfg.science_configs.colorterms
    if run_cfg.science_configs.calibrate_image_fallbacks:
        science_cfg.calibrate_image_fallbacks = [
            configs_dir / fb for fb in run_cfg.science_configs.calibrate_image_fallbacks
        ]

    result = RunResult(success=True, log_dir=str(run_log_dir))
    all_nights = list(run_cfg.nights)

    log.info(f"Pipeline run for {run_cfg.object_name}")
    log.info(f"  Target: RA={run_cfg.ra:.4f}, Dec={run_cfg.dec:.4f}")
    log.info(f"  Bands: {run_cfg.bands}")
    log.info(f"  Template type: {run_cfg.template_type}")
    log.info(f"  Nights: {len(all_nights)}")
    if run_cfg.template_type == "coadd" and run_cfg.template_nights:
        log.info(f"  Template nights: {run_cfg.template_nights}")

    if dry_run:
        log.info("[DRY RUN] Commands would be executed:")

    # Step 1: Templates per band
    if run_cfg.template_type == "ps1":
        _run_ps1_templates(run_cfg, config, result, dry_run)
        _log_template_summary(run_cfg, result)
    elif run_cfg.template_type == "coadd":
        early_exit = _run_coadd_templates(run_cfg, config, result, science_cfg, dry_run)
        if early_exit is not None:
            log.error(f"Coadd template build failed: {early_exit.error}")
            return early_exit
        _log_template_summary(run_cfg, result)

    # Step 2: Calibrations per night
    if not run_cfg.skip_calibs:
        early_exit = _run_calibs_step(all_nights, run_cfg, config, result, dry_run)
        if early_exit is not None:
            return early_exit

    # Step 3: Science per night
    if not run_cfg.skip_science:
        early_exit = _run_science_step(
            all_nights, run_cfg, config, result, science_cfg, dry_run
        )
        if early_exit is not None:
            return early_exit

    # Step 4: DIA per night per band
    if not run_cfg.skip_dia:
        early_exit = _run_dia_step(all_nights, run_cfg, config, result, dry_run)
        if early_exit is not None:
            return early_exit

    # Step 5: Forced photometry per night per successful DIA band
    if run_cfg.forced_phot:
        _run_fphot_step(all_nights, run_cfg, config, result, dry_run)

    # Step 6: Lightcurve extraction
    if run_cfg.lightcurve:
        log.info("Extracting lightcurve...")
        _run_lightcurve_step(all_nights, run_cfg, config, result, dry_run)

    # Step 7: Period analysis (variable stars only)
    if run_cfg.period_search:
        log.info("Running period analysis...")
        _run_period_step(run_cfg, result, dry_run)

    # Determine overall success
    # Use a three-tier status: SUCCESS (no failures), PARTIAL (some failures but
    # usable results like lightcurves or successful nights), FAILED (nothing worked)
    has_failures = bool(
        result.failed_calibs
        or result.failed_science
        or result.failed_dia
        or result.failed_fphot
    )
    has_successes = False

    if has_failures:
        # Check if we got any usable results despite failures
        total_nights = len(all_nights)
        successful_science = total_nights - len(result.failed_science)
        successful_dia_pairs = sum(
            1
            for night in all_nights
            for b in _get_bands_for_night(night, run_cfg)
            if f"{night}/{b}" not in set(result.failed_dia)
        )
        successful_fphot = total_nights - len(result.failed_fphot)

        has_successes = (
            successful_science > 0
            or successful_dia_pairs > 0
            or successful_fphot > 0
            or result.lightcurve_path is not None
            or result.period_result_path is not None
        )

        if has_successes:
            result.success = True  # Partial success is still success
        else:
            result.success = False

        failures = []
        if result.failed_calibs:
            failures.append(f"calibs: {result.failed_calibs}")
        if result.failed_science:
            failures.append(f"science: {result.failed_science}")
        if result.failed_dia:
            failures.append(f"dia: {result.failed_dia}")
        if result.failed_fphot:
            failures.append(f"fphot: {result.failed_fphot}")
        result.error = "; ".join(failures)

    # Post-process: split any remaining unsplit logs by exposure
    if not dry_run:
        _split_step_logs(run_log_dir)

    # Write summary and log final location
    if not has_failures:
        status = "SUCCESS"
    elif has_successes:
        status = "PARTIAL SUCCESS"
    else:
        status = "FAILED"
    log.info(f"Pipeline {status}")
    log.info(f"All logs: {run_log_dir}")

    # Log success/failure counts
    total_nights = len(all_nights)
    n_calibs_ok = total_nights - len(result.failed_calibs)
    n_science_ok = total_nights - len(result.failed_science)
    n_fphot_ok = total_nights - len(result.failed_fphot)
    total_dia_pairs = sum(
        len(_get_bands_for_night(night, run_cfg)) for night in all_nights
    )
    n_dia_ok = total_dia_pairs - len(result.failed_dia)
    log.info(
        f"  Calibs: {n_calibs_ok}/{total_nights}, Science: {n_science_ok}/{total_nights}, "
        f"DIA: {n_dia_ok}/{total_dia_pairs}, Fphot: {n_fphot_ok}/{total_nights}"
    )
    if result.lightcurve_path:
        log.info(f"  Lightcurve: {result.lightcurve_path}")
    if result.period_result_path:
        log.info(f"  Period analysis: {result.period_result_path}")

    summary_file = run_log_dir / "summary.txt"
    with open(summary_file, "w") as f:
        f.write(f"Status: {status}\n")
        f.write(f"Object: {run_cfg.object_name}\n")
        f.write(f"Bands: {run_cfg.bands}\n")
        f.write(f"Nights: {total_nights}\n")
        f.write(f"Calibs OK: {n_calibs_ok}/{total_nights}\n")
        f.write(f"Science OK: {n_science_ok}/{total_nights}\n")
        f.write(f"DIA OK: {n_dia_ok}/{total_dia_pairs}\n")
        f.write(f"Fphot OK: {n_fphot_ok}/{total_nights}\n")
        if result.failed_calibs:
            f.write(f"Failed calibs: {result.failed_calibs}\n")
        if result.failed_science:
            f.write(f"Failed science: {result.failed_science}\n")
        if result.failed_dia:
            f.write(f"Failed DIA: {result.failed_dia}\n")
        if result.failed_fphot:
            f.write(f"Failed fphot: {result.failed_fphot}\n")
        if result.template_collections:
            f.write(f"Templates: {result.template_collections}\n")
        if result.lightcurve_path:
            f.write(f"Lightcurve: {result.lightcurve_path}\n")
        if result.period_result_path:
            f.write(f"Period analysis: {result.period_result_path}\n")

    return result
