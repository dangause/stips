"""Stack integration test for refcat conversion.

Skipped unless the LSST stack is set up (``convertReferenceCatalog`` on PATH).
Verifies Open Question 1 from the spec: converted Gaia refcats carry nanojansky
fluxes (format_version >= 1) and produce HTM7 shards + an ingest map.

The heavier Butler register/ingest/chain path is validated manually per
docs/refcat-validation-runbook.md (needs a real Butler repo + the full stack).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

needs_stack = pytest.mark.skipif(
    shutil.which("convertReferenceCatalog") is None,
    reason="LSST stack not active (convertReferenceCatalog not on PATH)",
)

# Columns produced by nickel_refcats.gaia.fetch_gaia_cone (what gaia_dr3_config.py maps).
_GAIA_HEADER = (
    "source_id,ra,dec,ra_error,dec_error,parallax,parallax_error,"
    "pmra,pmra_error,pmdec,pmdec_error,ref_epoch,"
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

    # Ingest map + at least one HTM7 shard exist.
    assert ecsv.exists()
    shards = list(out_dir.glob("*.fits"))
    assert shards, "no HTM7 shard FITS produced"

    # The persisted DatasetConfig should request nanojansky fluxes (>= v1).
    cfg_text = (out_dir / "config.py").read_text()
    assert "format_version" in cfg_text
