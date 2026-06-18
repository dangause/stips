"""Core pipeline functionality for obs_nickel.

This module provides Python APIs for running LSST pipelines on Nickel data.
All functions can be used programmatically or via the `nickel` CLI.

Example:
    from stips.core import config, calibs, science, dia

    cfg = config.load()
    calibs.run(night="20240625", jobs=4, config=cfg)
    science.run(night="20240625", jobs=8, config=cfg)
    dia.run(night="20240625", config=cfg, auto_template=True)

    # PS1 templates
    from stips.core import ps1_template
    ps1_template.run(ra=210.91, dec=54.32, band="r", config=cfg)

    # Forced photometry
    from stips.core import fphot
    fphot.run(night="20240625", ra=210.91, dec=54.32, config=cfg)

    # Lightcurve extraction
    from stips.core import lightcurve
    lightcurve.run(ra=210.91, dec=54.32, collections="<prefix>/runs/*/diff/*/run", config=cfg)

    # Full pipeline from YAML config
    from stips.core import run
    run.run(config_file=Path("pipeline.yaml"), config=cfg)
"""

from stips.core import (
    calibs,
    dia,
    fphot,
    lightcurve,
    ps1_template,
    run,
    science,
)
from stips.core.config import Config, load

__all__ = [
    "Config",
    "load",
    "calibs",
    "science",
    "dia",
    "ps1_template",
    "fphot",
    "lightcurve",
    "run",
]
