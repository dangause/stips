import pytest
import yaml

from stips.core import refcat


def test_modes_and_default():
    assert refcat.REFCAT_MODES == ("monster", "gaia_ps1", "gaia")
    assert refcat.DEFAULT_REFCAT_MODE == "monster"


@pytest.mark.parametrize("value", [None, "monster", "gaia_ps1", "gaia"])
def test_parse_accepts_valid_and_default(value):
    assert refcat.parse_refcat_mode(value) == (value or "monster")


@pytest.mark.parametrize("value", ["", "MONSTER", "gaia-ps1", 3, "ps1"])
def test_parse_rejects_unknown(value):
    with pytest.raises(ValueError) as exc:
        refcat.parse_refcat_mode(value)
    msg = str(exc.value)
    assert repr(value) in msg and "monster" in msg and "gaia_ps1" in msg and "gaia" in msg


def _yaml(tmp_path, data):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_mode_from_yaml_absent_present_invalid(tmp_path):
    assert refcat.refcat_mode_from_yaml(_yaml(tmp_path, {"env": {}})) == "monster"
    assert refcat.refcat_mode_from_yaml(_yaml(tmp_path, {"refcat": {"mode": "gaia"}})) == "gaia"
    assert refcat.refcat_mode_from_yaml(_yaml(tmp_path, {"refcat": None})) == "monster"
    with pytest.raises(ValueError, match="refcat.mode"):
        refcat.refcat_mode_from_yaml(_yaml(tmp_path, {"refcat": {"mode": "nope"}}))


def test_run_default_is_reexported():
    from stips.core.run import DEFAULT_REFCAT_MODE

    assert DEFAULT_REFCAT_MODE is refcat.DEFAULT_REFCAT_MODE
