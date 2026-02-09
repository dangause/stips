"""YAML-driven pipeline orchestrator.

This module reads a YAML configuration file and orchestrates the full pipeline:
calibs → science → DIA → forced photometry → lightcurve.

Example YAML format:
    object: "SN2023ixf"   # Must match target_name in FITS (case-insensitive partial match)
    ra: 210.910833
    dec: 54.316389
    bands: ["r", "i"]

    template:
      type: ps1           # or "coadd"
      degrade_seeing: 2.0  # optional

    nights:
      20230519:
        r: [76482094, 76482095]
        i: [76482096]
      20230521:
        r: []
        i: []

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
      lightcurve: true
      use_fallbacks: true    # Try fallback configs on failure
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


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
class RunConfig:
    """Configuration parsed from YAML."""

    object_name: str
    ra: float
    dec: float
    bands: list[str]
    nights: dict[str, dict[str, list[int]]]

    # Template configuration
    template_type: str = "ps1"  # "ps1" or "coadd"
    template_degrade_seeing: float | None = None
    template_nights: list[str] = field(default_factory=list)

    # Pipeline config files
    science_configs: ScienceConfigs = field(default_factory=ScienceConfigs)
    dia_configs: DIAConfigs = field(default_factory=DIAConfigs)

    # Processing options
    jobs: int = 8
    skip_calibs: bool = False
    skip_science: bool = False
    skip_dia: bool = False
    forced_phot: bool = True
    lightcurve: bool = True
    continue_on_error: bool = True
    use_fallbacks: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> RunConfig:
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Extract template config
        template = data.get("template", {})
        template_type = template.get("type", "ps1")
        template_degrade_seeing = template.get("degrade_seeing")
        # Convert template nights to strings (YAML parses 20230519 as int)
        template_nights = [str(n) for n in template.get("nights", [])]

        # Extract options
        options = data.get("options", {})

        # Convert night keys to strings (YAML parses 20230519 as int)
        raw_nights = data.get("nights", {})
        nights = {str(k): v for k, v in raw_nights.items()}

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

        return cls(
            object_name=data.get("object", ""),
            ra=data["ra"],
            dec=data["dec"],
            bands=data.get("bands", ["r"]),
            nights=nights,
            template_type=template_type,
            template_degrade_seeing=template_degrade_seeing,
            template_nights=template_nights,
            science_configs=science_configs,
            dia_configs=dia_configs,
            jobs=options.get("jobs", 8),
            skip_calibs=options.get("skip_calibs", False),
            skip_science=options.get("skip_science", False),
            skip_dia=options.get("skip_dia", False),
            forced_phot=options.get("forced_phot", True),
            lightcurve=options.get("lightcurve", True),
            continue_on_error=options.get("continue_on_error", True),
            use_fallbacks=options.get("use_fallbacks", True),
        )


@dataclass
class RunResult:
    """Result of pipeline run."""

    success: bool
    failed_calibs: list[str] = field(default_factory=list)
    failed_science: list[str] = field(default_factory=list)
    failed_dia: list[str] = field(default_factory=list)
    failed_fphot: list[str] = field(default_factory=list)
    template_collections: dict[str, str] = field(default_factory=dict)
    lightcurve_path: str | None = None
    error: str | None = None


def run(
    config_file: Path,
    config: Config,
    *,
    dry_run: bool = False,
) -> RunResult:
    """Run full pipeline from YAML configuration.

    This orchestrates:
    1. PS1 template ingestion (or coadd building) per band
    2. Calibrations per night
    3. Science processing per night
    4. DIA per night per band
    5. Forced photometry per night
    6. Lightcurve extraction

    Args:
        config_file: Path to YAML configuration file
        config: Pipeline configuration
        dry_run: Print commands without executing

    Returns:
        RunResult with status and any failures
    """
    from obs_nickel_data_tools.core import (
        calibs,
        dia,
        fphot,
        lightcurve,
        ps1_template,
        science,
    )
    from obs_nickel_data_tools.core.science import ScienceConfig

    # Load run configuration
    run_cfg = RunConfig.from_yaml(config_file)

    # Build ScienceConfig from YAML paths
    configs_dir = config.obs_nickel / "configs"
    science_cfg = ScienceConfig.default(config.obs_nickel)

    # Override with YAML-specified configs if present
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

    result = RunResult(success=True)
    all_nights = list(run_cfg.nights.keys())

    log.info(f"Pipeline run for {run_cfg.object_name}")
    log.info(f"  Target: RA={run_cfg.ra:.4f}, Dec={run_cfg.dec:.4f}")
    log.info(f"  Bands: {run_cfg.bands}")
    log.info(f"  Nights: {len(all_nights)}")

    if dry_run:
        log.info("[DRY RUN] Commands would be executed:")

    # Step 1: Templates per band
    for band in run_cfg.bands:
        if run_cfg.template_type == "ps1":
            if band not in ("r", "i"):
                log.warning(f"PS1 templates not available for band {band}, skipping")
                continue

            log.info(f"Ingesting PS1 template for {band}-band...")

            if not dry_run:
                ps1_result = ps1_template.run(
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    band=band,
                    config=config,
                    degrade_seeing=run_cfg.template_degrade_seeing,
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

    # Step 2: Calibrations per night
    if not run_cfg.skip_calibs:
        for night in all_nights:
            log.info(f"Running calibrations for {night}...")

            if not dry_run:
                calib_result = calibs.run(night, config, jobs=run_cfg.jobs)
                if not calib_result.success:
                    result.failed_calibs.append(night)
                    log.warning(
                        f"Calibrations failed for {night}: {calib_result.error}"
                    )
                    if not run_cfg.continue_on_error:
                        result.success = False
                        result.error = f"Calibrations failed for {night}"
                        return result
            else:
                log.info(f"  [DRY RUN] calibs.run({night})")

    # Step 3: Science per night
    if not run_cfg.skip_science:
        for night in all_nights:
            log.info(f"Running science for {night}...")

            if not dry_run:
                sci_result = science.run(
                    night,
                    config,
                    jobs=run_cfg.jobs,
                    object_filter=run_cfg.object_name,
                    skip_coadds=True,
                    science_cfg=science_cfg,
                    use_fallbacks=run_cfg.use_fallbacks,
                )
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
                log.info(f"  [DRY RUN] science.run({night})")

    # Step 4: DIA per night per band
    if not run_cfg.skip_dia:
        for night in all_nights:
            night_bands = run_cfg.nights.get(night, {})
            for band in run_cfg.bands:
                # Skip if no data for this band on this night
                if band in night_bands and not night_bands[band]:
                    log.info(f"Skipping DIA for {night}/{band} (no visit IDs)")
                    continue

                template_coll = result.template_collections.get(band)
                log.info(f"Running DIA for {night}/{band}...")

                if not dry_run:
                    dia_result = dia.run(
                        night,
                        config,
                        jobs=run_cfg.jobs,
                        template=template_coll,
                        auto_template=template_coll is None,
                        prefer_ps1=run_cfg.template_type == "ps1",
                        band=band,
                        object_filter=run_cfg.object_name,
                    )
                    if not dia_result.success:
                        result.failed_dia.append(f"{night}/{band}")
                        log.warning(
                            f"DIA failed for {night}/{band}: {dia_result.error}"
                        )
                        if not run_cfg.continue_on_error:
                            result.success = False
                            result.error = f"DIA failed for {night}/{band}"
                            return result
                else:
                    log.info(f"  [DRY RUN] dia.run({night}, band={band})")

    # Step 5: Forced photometry per night
    if run_cfg.forced_phot:
        for night in all_nights:
            log.info(f"Running forced photometry for {night}...")

            if not dry_run:
                fphot_result = fphot.run(
                    night=night,
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    config=config,
                )
                if not fphot_result.success:
                    result.failed_fphot.append(night)
                    log.warning(f"Forced phot failed for {night}: {fphot_result.error}")
            else:
                log.info(f"  [DRY RUN] fphot.run({night})")

    # Step 6: Lightcurve extraction
    if run_cfg.lightcurve:
        log.info("Extracting lightcurve...")

        # Build collection pattern for all nights
        collections = ",".join([f"Nickel/runs/{n}/diff/*/run" for n in all_nights])

        if not dry_run:
            lc_result = lightcurve.run(
                ra=run_cfg.ra,
                dec=run_cfg.dec,
                collections=collections,
                config=config,
                name=run_cfg.object_name,
                plot=True,
            )
            if lc_result.success:
                result.lightcurve_path = lc_result.csv_path
            else:
                log.warning(f"Lightcurve extraction failed: {lc_result.error}")
        else:
            log.info("  [DRY RUN] lightcurve.run()")

    # Determine overall success
    if result.failed_calibs or result.failed_science or result.failed_dia:
        result.success = False
        failures = []
        if result.failed_calibs:
            failures.append(f"calibs: {result.failed_calibs}")
        if result.failed_science:
            failures.append(f"science: {result.failed_science}")
        if result.failed_dia:
            failures.append(f"dia: {result.failed_dia}")
        result.error = "; ".join(failures)

    return result
