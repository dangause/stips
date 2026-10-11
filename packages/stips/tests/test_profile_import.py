"""stips.profile: importing an instrument directory by name."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from stips import InstrumentProfile, Site
from stips.profile import (
    import_instrument_submodule,
    import_profile,
    instrument_class_for,
    instrument_dir_name,
    instruments_root,
)

_PROFILE_SRC = textwrap.dedent(
    """
    from stips import Field, InstrumentProfile, Site

    profile = InstrumentProfile(
        name="{name}",
        site=Site(10.0, 20.0, 100.0),
        filters={{"B": "b"}},
        header_map={{"exposure_time": Field("EXPTIME", unit="s", default=0.0)}},
        camera="camera/demo.yaml",
    )
    """
)


@pytest.fixture
def root(tmp_path):
    """A <root>/instruments/ layout; removed from sys.path/sys.modules on exit."""
    r = tmp_path / "root"
    (r / "instruments").mkdir(parents=True)
    yield r
    for mod_name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if mod_name.startswith("instruments.") and f and str(r) in f:
            del sys.modules[mod_name]
    while str(r) in sys.path:
        sys.path.remove(str(r))


def _make(root: Path, dirname: str, name: str) -> Path:
    d = root / "instruments" / dirname
    d.mkdir()
    (d / "profile.py").write_text(_PROFILE_SRC.format(name=name))
    return d


def test_import_profile_by_name(root):
    d = _make(root, "demo_a", "DemoA")
    prof = import_profile(d)
    assert prof.name == "DemoA"
    assert "instruments.demo_a.profile" in sys.modules
    assert str(root) in sys.path


def test_two_instruments_are_distinct_modules(root):
    a = _make(root, "demo_b", "DemoB")
    b = _make(root, "demo_c", "DemoC")
    assert import_profile(a).name == "DemoB"
    assert import_profile(b).name == "DemoC"
    assert (
        sys.modules["instruments.demo_b.profile"]
        is not sys.modules["instruments.demo_c.profile"]
    )


def test_submodule_import(root):
    d = _make(root, "demo_d", "DemoD")
    (d / "fetch.py").write_text("MARK = 'demo_d'\n")
    assert import_instrument_submodule(d, "fetch").MARK == "demo_d"


def test_instrument_class_for(root):
    d = _make(root, "demo_e", "DemoE")
    assert instrument_class_for(d) == "instruments.demo_e.instrument.Instrument"
    assert instruments_root(d) == root.resolve()
    assert instrument_dir_name(d) == "demo_e"


def test_missing_profile_raises_file_not_found(root):
    d = root / "instruments" / "demo_f"
    d.mkdir()
    with pytest.raises(FileNotFoundError):
        import_profile(d)
    with pytest.raises(FileNotFoundError):
        import_profile("/tmp/does_not_exist_instrument_dir")


def test_rejects_dir_not_under_instruments(tmp_path):
    d = tmp_path / "elsewhere" / "demo_g"
    d.mkdir(parents=True)
    (d / "profile.py").write_text(_PROFILE_SRC.format(name="DemoG"))
    with pytest.raises(ValueError, match="instruments/<name>/"):
        instrument_dir_name(d)


@pytest.mark.parametrize("bad", ["demo-h", "_demo_h", "class", "1demo"])
def test_rejects_non_identifier_names(root, bad):
    d = root / "instruments" / bad
    d.mkdir()
    (d / "profile.py").write_text(_PROFILE_SRC.format(name="Bad"))
    with pytest.raises(ValueError, match="identifier"):
        instrument_dir_name(d)


def test_profile_binning_fields_default_and_validate():
    kw = dict(
        site=Site(0.0, 0.0, 0.0),
        filters={"B": "b"},
        header_map={},
        camera="camera/x.yaml",
    )
    p = InstrumentProfile(name="X", **kw)
    assert p.ccd_binning == 1
    assert p.binning_header is None
    p2 = InstrumentProfile(name="X2", ccd_binning=2, binning_header="CCDSUM", **kw)
    assert p2.ccd_binning == 2
    with pytest.raises(ValueError, match="ccd_binning"):
        InstrumentProfile(name="X3", ccd_binning=0, **kw)


@pytest.fixture
def two_roots(tmp_path):
    """Two <root>/instruments/ layouts; cleaned from sys.path/sys.modules on exit."""
    roots = [tmp_path / "root_a", tmp_path / "root_b"]
    for r in roots:
        (r / "instruments").mkdir(parents=True)
    yield roots
    for mod_name in list(sys.modules):
        if mod_name == "instruments.demo_s" or mod_name.startswith(
            "instruments.demo_s."
        ):
            del sys.modules[mod_name]
    for r in roots:
        while str(r) in sys.path:
            sys.path.remove(str(r))


def test_shadowed_instrument_dir_raises(two_roots):
    root_a, root_b = two_roots
    _make(root_a, "demo_s", "A")
    b = _make(root_b, "demo_s", "B")
    sys.path.insert(0, str(root_a))
    with pytest.raises(RuntimeError) as excinfo:
        import_profile(b)
    msg = str(excinfo.value)
    assert str((root_a / "instruments" / "demo_s").resolve()) in msg
    assert str((root_b / "instruments" / "demo_s").resolve()) in msg
