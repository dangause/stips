"""stack._build_setup_script exports what the stack needs to import the
instrument by name, and nothing the profile now carries."""

from pathlib import Path

from stips.core import config as cfg
from stips.core.stack import _build_setup_script

REPO_ROOT = Path(__file__).resolve().parents[3]


def _config(tmp_path):
    stack = tmp_path / "stack"
    stack.mkdir()
    (stack / "loadLSST.bash").write_text("# fake loader\n")
    return cfg.load(
        env={
            "REPO": str(tmp_path / "repo"),
            "STACK_DIR": str(stack),
            "INSTRUMENT_DIR": str(REPO_ROOT / "instruments" / "nickel"),
            "RAW_PARENT_DIR": str(tmp_path / "raw"),
        }
    )


def test_setup_script_exports_instruments_root_and_class(tmp_path):
    script, env = _build_setup_script(_config(tmp_path))
    assert env["STIPS_INSTRUMENTS_ROOT"] == str(REPO_ROOT)
    assert env["STIPS_INSTRUMENT_CLASS"] == "instruments.nickel.instrument.Instrument"
    assert 'export PYTHONPATH="${STIPS_INSTRUMENTS_ROOT}:${PYTHONPATH:-}"' in script
    assert 'export STIPS_INSTRUMENT_CLASS="$STIPS_INSTRUMENT_CLASS"' in script


def test_setup_script_no_longer_smuggles_profile_values(tmp_path):
    script, env = _build_setup_script(_config(tmp_path))
    assert "CCD_BINNING" not in env and "CCD_BINNING" not in script
    assert "STIPS_PS1_BAND_MAP" not in env and "STIPS_PS1_BAND_MAP" not in script
