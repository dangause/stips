"""Stack-free tests for the setup-script builder.

F-018: config paths and env-derived values must NOT be interpolated into the
bash script text; they are injected via the returned env mapping and referenced
as "$VAR". These tests assert both the (static) export lines and the env values.
"""

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
    script, env = _build_setup_script(cfg)
    # The export line is constant text; the value travels via env.
    assert 'export STIPS_DEFAULTS="$STIPS_DEFAULTS"' in script
    assert "obs_stips/instrument_defaults" in env["STIPS_DEFAULTS"]
    # The value itself is never baked into the script text.
    assert env["STIPS_DEFAULTS"] not in script


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
    script, env = _build_setup_script(cfg)
    assert 'export SKYMAP_NAME="$SKYMAP_NAME"' in script
    assert 'export SKYMAP_COLLECTION="$SKYMAP_COLLECTION"' in script
    assert env["SKYMAP_NAME"] == "ctio1mRings-v1"
    assert env["SKYMAP_COLLECTION"] == "skymaps/ctio1mRings"
    # SKYMAP_CFG is resolved instrument-dir-first; here it falls back to the
    # framework reference geometry (tmp_path has no configs/makeSkyMap.py).
    assert 'export SKYMAP_CFG="$SKYMAP_CFG"' in script
    assert "configs/makeSkyMap.py" in env["SKYMAP_CFG"]


def test_setup_script_sets_up_colocated_data_package(tmp_path):
    # F-020: a data package co-located under the instrument dir must be
    # eups-setup'd from that location (not the framework packages/ dir).
    (tmp_path / "loadLSST.bash").write_text("")
    instrument_dir = tmp_path / "instruments" / "x"
    data_dir = instrument_dir / "obs_x_data"
    data_dir.mkdir(parents=True)
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=instrument_dir,
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(obs_data_package="obs_x_data")
    script, env = _build_setup_script(cfg)
    # Path is referenced via $STIPS_DATA_DIR; the value lives in env.
    assert 'setup -r "$STIPS_DATA_DIR" obs_x_data' in script
    assert env["STIPS_DATA_DIR"] == str(data_dir)
    assert str(data_dir) not in script


def test_setup_script_skips_data_package_when_unresolved(tmp_path):
    # Named but present nowhere -> no data-package setup block emitted.
    (tmp_path / "loadLSST.bash").write_text("")
    instrument_dir = tmp_path / "instruments" / "x"
    instrument_dir.mkdir(parents=True)
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=instrument_dir,
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(obs_data_package="obs_missing_data")
    script, env = _build_setup_script(cfg)
    assert "obs_missing_data" not in script
    assert "STIPS_DATA_DIR" not in env


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
    script, env = _build_setup_script(cfg)
    assert "SKYMAP_NAME" not in script
    assert "SKYMAP_COLLECTION" not in script
    assert "SKYMAP_NAME" not in env
    assert "SKYMAP_COLLECTION" not in env


def test_setup_script_does_not_interpolate_shell_metacharacters(tmp_path):
    # F-018: a config path containing shell metacharacters ($VAR, backtick, ")
    # must NOT appear as raw text in the script (where bash would expand/execute
    # it). It must instead travel via the env mapping, verbatim, and the script
    # must reference only "$REPO".
    (tmp_path / "loadLSST.bash").write_text("")
    hostile = tmp_path / "data" / "$USER" / "`whoami`" / 'a"b'
    hostile.mkdir(parents=True)
    cfg = Config(
        repo=hostile,
        stack_dir=tmp_path,
        instrument_dir=tmp_path,
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(obs_data_package=None)
    script, env = _build_setup_script(cfg)
    # The dangerous substrings must not be present as literal script text.
    assert "$USER" not in script
    assert "`whoami`" not in script
    assert 'a"b' not in script
    # The value is preserved verbatim in the env mapping and referenced as $REPO.
    assert env["REPO"] == str(hostile)
    assert 'export REPO="$REPO"' in script
