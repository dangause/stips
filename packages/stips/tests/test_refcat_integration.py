"""Stack integration test for refcat conversion.

Skipped unless the LSST stack is set up (``convertReferenceCatalog`` on PATH).
Verifies Open Question 1 from the spec: converted Gaia refcats carry nanojansky
fluxes (format_version >= 1) and produce HTM7 shards + an ingest map.

The heavier Butler register/ingest/chain path is validated manually per
docs/refcat-validation-runbook.md (needs a real Butler repo + the full stack).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

needs_stack = pytest.mark.skipif(
    shutil.which("convertReferenceCatalog") is None,
    reason="LSST stack not active (convertReferenceCatalog not on PATH)",
)

# Columns produced by nickel_refcats.gaia.fetch_gaia_cone (what gaia_dr3_config.py
# maps). Must mirror COLS_SQL in nickel_refcats.gaia, including the 10 off-diagonal
# ``*_corr`` covariance columns: gaia_dr3_config sets full_position_information=True,
# so ConvertGaiaManager._setCoordinateCovariance reads every
# ``{a}_{b}_corr`` pair over (ra, dec, parallax, pmra, pmdec). Omitting them makes
# convertReferenceCatalog raise "ValueError: no field of name ra_dec_corr".
_GAIA_HEADER = (
    "source_id,ra,dec,ra_error,dec_error,parallax,parallax_error,"
    "pmra,pmra_error,pmdec,pmdec_error,ref_epoch,"
    "ra_dec_corr,ra_parallax_corr,ra_pmra_corr,ra_pmdec_corr,"
    "dec_parallax_corr,dec_pmra_corr,dec_pmdec_corr,"
    "parallax_pmra_corr,parallax_pmdec_corr,pmra_pmdec_corr,"
    "phot_g_mean_flux,phot_bp_mean_flux,phot_rp_mean_flux,"
    "phot_g_mean_flux_over_error,phot_bp_mean_flux_over_error,"
    "phot_rp_mean_flux_over_error,"
    "phot_g_mean_mag,phot_bp_mean_mag,phot_rp_mean_mag"
)


def _canned_gaia_csv(path: Path) -> Path:
    rows = [_GAIA_HEADER]
    # A few stars near a northern field; values are plausible, not physical.
    for i in range(5):
        ra = 210.90 + i * 0.001
        dec = 54.31 + i * 0.001
        rows.append(
            f"{1000 + i},{ra},{dec},0.1,0.1,0.5,0.05,"
            f"1.0,0.1,-1.0,0.1,2016.0,"
            # 10 off-diagonal correlation coefficients in [-1, 1], same order as
            # COLS_SQL: ra_dec, ra_parallax, ra_pmra, ra_pmdec, dec_parallax,
            # dec_pmra, dec_pmdec, parallax_pmra, parallax_pmdec, pmra_pmdec.
            f"0.10,0.05,-0.02,0.03,-0.15,0.08,-0.06,0.12,-0.09,0.04,"
            f"1.0e6,5.0e5,8.0e5,100,80,90,18.0,18.5,17.5"
        )
    path.write_text("\n".join(rows) + "\n")
    return path


@needs_stack
def test_convert_gaia_emits_njy_shards(tmp_path):
    from nickel_refcats.convert import convert_catalog
    from stips.core.refcat import _convert_config_path

    src = _canned_gaia_csv(tmp_path / "gaia.csv")
    out_dir = tmp_path / "gaia-refcat"
    ecsv = convert_catalog(
        "gaia_dr3", src, _convert_config_path("gaia_dr3_config.py"), out_dir
    )

    # Ingest map + at least one HTM7 shard exist. convertReferenceCatalog writes
    # the sharded catalog into an ``out_dir/<ref_dataset_name>/`` subdirectory,
    # with the ingest map (filename_to_htm.ecsv) at the top level.
    assert ecsv.exists()
    dataset_dir = out_dir / "gaia_dr3"
    # HTM7 shards are named by trixel id (e.g. 218515.fits); master_schema.fits is
    # the schema template, not a data shard, so require a numerically-named shard.
    shards = [p for p in dataset_dir.glob("*.fits") if p.stem.isdigit()]
    assert shards, "no HTM7 shard FITS produced"

    # The persisted DatasetConfig should request nanojansky fluxes (format_version
    # >= 1; the installed v30-class stack emits v2). Asserting >= 1 rather than an
    # exact value keeps the check meaningful across stack versions.
    cfg_text = (dataset_dir / "config.py").read_text()
    match = re.search(r"format_version\s*=\s*(\d+)", cfg_text)
    assert match, f"format_version not found in DatasetConfig:\n{cfg_text}"
    assert int(match.group(1)) >= 1, "refcat is pre-nanojansky (format_version < 1)"
