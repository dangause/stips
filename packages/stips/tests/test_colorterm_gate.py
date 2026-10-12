"""Colour terms switch on only for a refcat the instrument's library covers.

The stack looks a colour-term block up by catalogue name (exact key, else exactly
one glob) and raises ColortermNotFoundError at run time when there is none. An
instrument that fits terms for one refcat only (CTIO: PS1) must therefore still
calibrate in its other refcat modes with colour terms OFF.

Execs the config snippets against a mock ``config`` (no LSST stack needed).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

_DEFAULTS = (
    Path(__file__).resolve().parents[3] / "packages/obs_stips/instrument_defaults"
)
APPLY = _DEFAULTS / "configs/apply_colorterms.py"
QA = _DEFAULTS / "configs/analysisToolsPhotometricCatalogMatchVisit.py"

NICKEL = {"ps1*": 1, "gaia*": 2, "*monster*": 3}
PS1_ONLY = {"ps1*": 1}


def _exec(path: Path, config: MagicMock) -> MagicMock:
    ns = {"config": config, "__file__": str(path)}
    exec(compile(path.read_text(), str(path), "exec"), ns)
    return config


@pytest.mark.parametrize(
    ("library", "refcat", "expected"),
    [
        (PS1_ONLY, "panstarrs1_dr2", True),
        (PS1_ONLY, "gaia_dr3", False),
        (PS1_ONLY, "the_monster_20250219_local", False),
        (NICKEL, "panstarrs1_dr2", True),
        (NICKEL, "gaia_dr3", True),
        (NICKEL, "the_monster_20250219_local", True),
        ({}, "panstarrs1_dr2", False),
    ],
)
def test_calibrate_image_gate(monkeypatch, tmp_path, library, refcat, expected):
    monkeypatch.setenv("INSTRUMENT_DIR", str(tmp_path))
    config = MagicMock()
    config.connections.photometry_ref_cat = refcat
    config.photometry.colorterms.data = library
    _exec(APPLY, config)
    assert config.photometry.applyColorTerms is expected


@pytest.mark.parametrize(
    ("library", "expected"), [(PS1_ONLY, False), (NICKEL, True), ({}, False)]
)
def test_qa_refmatch_gate(monkeypatch, tmp_path, library, expected):
    """The MONSTER QA ref-match task looks the block up by the refcat dataset name."""
    monkeypatch.setenv("INSTRUMENT_DIR", str(tmp_path))
    config = MagicMock()
    config.referenceCatalogLoader.colorterms.data = library
    _exec(QA, config)
    assert config.referenceCatalogLoader.doApplyColorTerms is expected
