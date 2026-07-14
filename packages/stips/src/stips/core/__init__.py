"""Core pipeline functionality for the active instrument.

This module provides Python APIs for running LSST pipelines on small-telescope
data. All functions can be used programmatically or via the `stips` CLI.

Example:
    from stips.core import config, calibs, science, dia

    cfg = config.load("config.yaml")
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

import importlib
from typing import TYPE_CHECKING

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

# Submodules re-exported lazily via PEP 562 ``__getattr__``. Importing them
# eagerly here would pull in heavy/optional dependencies (e.g. the LSST stack)
# at package import time, breaking commands that never need them -- including
# ``stips --help``. The CLI already imports each core module lazily inside its
# command handlers; keeping this list lazy preserves that isolation.
_SUBMODULES = frozenset(
    {
        "calibs",
        "science",
        "dia",
        "ps1_template",
        "fphot",
        "lightcurve",
        "run",
    }
)

# Names re-exported from ``stips.core.config``.
_CONFIG_ATTRS = frozenset({"Config", "load"})

if TYPE_CHECKING:  # Help static analysers see the re-exported names.
    from stips.core import (  # noqa: F401
        calibs,
        dia,
        fphot,
        lightcurve,
        ps1_template,
        run,
        science,
    )
    from stips.core.config import Config, load  # noqa: F401


def __getattr__(name: str):
    if name in _SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    if name in _CONFIG_ATTRS:
        config = importlib.import_module(f"{__name__}.config")
        value = getattr(config, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
