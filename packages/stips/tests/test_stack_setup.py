"""Stack-free test that the setup script exports STIPS_DEFAULTS."""

import types

from stips.core.config import Config
from stips.core.stack import _build_setup_script


def test_setup_script_exports_stips_defaults(tmp_path):
    # _build_setup_script needs a stack loader on disk AND a loaded profile.
    (tmp_path / "loadLSST.bash").write_text("")
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=tmp_path,
        raw_parent_dir=tmp_path,
    )
    # require_profile() raises if profile is None; _build_setup_script reads
    # prof.obs_data_package, so the stub must expose it (None = no data pkg).
    cfg.profile = types.SimpleNamespace(obs_data_package=None)
    script = _build_setup_script(cfg)
    assert "STIPS_DEFAULTS" in script
    assert "obs_stips/instrument_defaults" in script


def test_setup_script_exports_profile_skymap_identity(tmp_path):
    # The bootstrap script registers/chains the skymap under profile-driven names;
    # core/stack.py must export them (regression for the hardcoded-nickelRings bug).
    (tmp_path / "loadLSST.bash").write_text("")
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=tmp_path,
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(
        obs_data_package=None,
        skymap_name="ctio1mRings-v1",
        skymap_collection="skymaps/ctio1mRings",
    )
    script = _build_setup_script(cfg)
    assert 'export SKYMAP_NAME="ctio1mRings-v1"' in script
    assert 'export SKYMAP_COLLECTION="skymaps/ctio1mRings"' in script
    # SKYMAP_CFG is resolved instrument-dir-first; here it falls back to the
    # framework reference geometry (tmp_path has no configs/makeSkyMap.py).
    assert "export SKYMAP_CFG=" in script
    assert "configs/makeSkyMap.py" in script


def test_setup_script_omits_skymap_when_profile_has_none(tmp_path):
    # A profile without skymap fields (partial mock) must not crash and must not
    # emit SKYMAP_NAME/COLLECTION exports.
    (tmp_path / "loadLSST.bash").write_text("")
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=tmp_path,
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(obs_data_package=None)
    script = _build_setup_script(cfg)
    assert "SKYMAP_NAME" not in script
    assert "SKYMAP_COLLECTION" not in script
