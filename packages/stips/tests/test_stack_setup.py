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
