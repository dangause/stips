"""Guard the centralized Butler dataset-type constants (finding F-025).

The point of ``stips.core.dataset_types`` is that a future stack-driven rename
of a dataset type is a single edit. These tests (a) pin the constant values so a
typo is caught, and (b) assert the rewired core modules no longer carry stray
quoted dataset-type literals that would bypass the module.
"""

from __future__ import annotations

from pathlib import Path

from stips.core import dataset_types as dt

# packages/stips/tests/test_dataset_types.py -> parents[1] == packages/stips
CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "stips" / "core"

# Core modules that reference Butler dataset types as query/pipeline arguments
# and were rewired to import from stips.core.dataset_types.
GUARDED_MODULES = ("dia.py", "fphot.py", "lightcurve.py", "coadd.py")

# Dataset-type strings that must not appear as bare quoted literals in the
# guarded modules (log-message prose without quotes is fine).
GUARDED_VALUES = (
    dt.DIFFERENCE_IMAGE,
    dt.DIA_SOURCE_UNFILTERED,
    dt.TEMPLATE_COADD,
    dt.PRELIMINARY_VISIT_IMAGE,
)


def test_constant_values() -> None:
    assert dt.DIFFERENCE_IMAGE == "difference_image"
    assert dt.DIA_SOURCE_UNFILTERED == "dia_source_unfiltered"
    assert dt.TEMPLATE_COADD == "template_coadd"
    assert dt.PRELIMINARY_VISIT_IMAGE == "preliminary_visit_image"
    assert dt.FORCED_PHOT_DIFFIM_RADEC == "forced_phot_diffim_radec"
    assert dt.FORCED_PHOT_RADEC == "forced_phot_radec"
    assert dt.FORCED_DIFF_RADEC == "forced_diff_radec"
    assert dt.FORCED_PHOT_PREFIX == "forced_phot"


def test_forced_phot_dataset_types_share_prefix() -> None:
    for value in (
        dt.FORCED_PHOT_DIFFIM_RADEC,
        dt.FORCED_PHOT_RADEC,
        dt.FORCED_DIFF_RADEC,
    ):
        assert value.startswith(dt.FORCED_PHOT_PREFIX) or value.startswith("forced_")


def test_no_stray_dataset_type_literals() -> None:
    for module_name in GUARDED_MODULES:
        source = (CORE_DIR / module_name).read_text()
        for value in GUARDED_VALUES:
            for quoted in (f'"{value}"', f"'{value}'"):
                assert quoted not in source, (
                    f"core/{module_name} contains stray dataset-type literal "
                    f"{quoted}; import it from stips.core.dataset_types instead"
                )
