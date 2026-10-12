"""Stack-free tests for the setup-script builder.

F-018: config paths and env-derived values must NOT be interpolated into the
bash script text; they are injected via the returned env mapping and referenced
as "$VAR". These tests assert both the (static) export lines and the env values.
"""

import types

from stips.core.config import Config
from stips.core.stack import _build_setup_script


def _instrument_dir(tmp_path, name="x"):
    """A minimal instruments/<name>/ dir: the setup script derives the
    PYTHONPATH root and Butler class path from this layout."""
    d = tmp_path / "instruments" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.py").write_text("")
    return d


def test_setup_script_exports_stips_defaults(tmp_path):
    # _build_setup_script needs a stack loader on disk AND a loaded profile.
    (tmp_path / "loadLSST.bash").write_text("")
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=_instrument_dir(tmp_path),
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


def test_setup_script_no_longer_exports_bootstrap_script_values(tmp_path, monkeypatch):
    # Only the removed bootstrap shell script read the skymap identity/config,
    # the instrument class and RUN_ID from the environment; stips.core.bootstrap
    # takes them from the profile and Config directly.
    monkeypatch.setenv("RUN_ID", "20261011_000000_1")
    (tmp_path / "loadLSST.bash").write_text("")
    cfg = Config(
        repo=tmp_path,
        stack_dir=tmp_path,
        instrument_dir=_instrument_dir(tmp_path),
        raw_parent_dir=tmp_path,
    )
    cfg.profile = types.SimpleNamespace(
        obs_data_package=None,
        skymap_name="ctio1mRings-v1",
        skymap_collection="skymaps/ctio1mRings",
    )
    script, env = _build_setup_script(cfg)
    for name in (
        "SKYMAP_NAME",
        "SKYMAP_COLLECTION",
        "SKYMAP_CFG",
        "STIPS_INSTRUMENT_CLASS",
        "RUN_ID",
    ):
        assert name not in script and name not in env, name


def test_setup_script_sets_up_colocated_data_package(tmp_path):
    # F-020: a data package co-located under the instrument dir must be
    # eups-setup'd from that location (not the framework packages/ dir).
    (tmp_path / "loadLSST.bash").write_text("")
    instrument_dir = _instrument_dir(tmp_path)
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
    instrument_dir = _instrument_dir(tmp_path)
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
        instrument_dir=_instrument_dir(tmp_path),
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
