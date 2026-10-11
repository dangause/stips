"""Unit tests for the contract assertions in ``stips.testing.instrument_contract``.

The auto-discovered suite (``test_instrument_contracts.py``) only exercises the
assertions against the real instrument dirs, which all pass; these tests pin
that each assertion actually *fails* on the violations it exists to catch.
"""

from __future__ import annotations

import pytest
from stips.testing import instrument_contract as ic


def _demo_instrument(tmp_path, profile_src: str, siblings=("helpers",)):
    inst = tmp_path / "instruments" / "demo_x"
    inst.mkdir(parents=True)
    (inst / "profile.py").write_text(profile_src)
    (inst / "instrument.py").write_text("bind(__name__)\n")
    for stem in siblings:
        (inst / f"{stem}.py").write_text("x = 1\ny = 2\n")
    return ic.InstrumentDirInfo(name="demo_x", path=inst)


# --------------------------------------------------------------------------- #
# assert_profile_imports_relatively
# --------------------------------------------------------------------------- #


def test_relative_sibling_import_passes(tmp_path):
    info = _demo_instrument(tmp_path, "from .helpers import x\n")
    ic.assert_profile_imports_relatively(info)


@pytest.mark.parametrize(
    "line",
    [
        "from helpers import x",
        "    from helpers import x",
        "from helpers.sub import x",
        "import helpers",
        "import helpers as h",
        "import helpers, os",
    ],
)
def test_absolute_sibling_import_fails(tmp_path, line):
    info = _demo_instrument(tmp_path, f"{line}\n")
    with pytest.raises(AssertionError, match=r"from \.helpers import"):
        ic.assert_profile_imports_relatively(info)


def test_absolute_fetch_import_still_fails(tmp_path):
    info = _demo_instrument(tmp_path, "from fetch import fetch_data\n", ("fetch",))
    with pytest.raises(AssertionError, match=r"from \.fetch import"):
        ic.assert_profile_imports_relatively(info)


@pytest.mark.parametrize(
    "src",
    [
        # Package-qualified framework module of the same stem: not a sibling.
        "from stips.fetch import make_fetch_data\n",
        "import stips.fetch\n",
        # A different module whose name merely starts with the stem.
        "from fetch_extra import y\n",
        "import fetchers\n",
        # The stem only inside a string.
        'NOTE = "from fetch import fetch_data"\n',
    ],
)
def test_non_sibling_imports_pass(tmp_path, src):
    info = _demo_instrument(tmp_path, src, ("fetch",))
    ic.assert_profile_imports_relatively(info)


def test_nameplate_and_profile_stems_are_not_siblings(tmp_path):
    # profile.py / instrument.py are excluded from the sibling set: a profile
    # importing e.g. ``instrument`` from elsewhere is not this contract's job.
    info = _demo_instrument(tmp_path, "import instrument\nimport profile\n", ())
    ic.assert_profile_imports_relatively(info)


# --------------------------------------------------------------------------- #
# assert_fetch_hook_is_framework_wrapper
# --------------------------------------------------------------------------- #


class _ProfileStub:
    def __init__(self, fetch_data):
        self.fetch_data = fetch_data


def _backend(night, raw_root, *, overwrite=False, **kwargs):  # pragma: no cover
    return 0


def test_no_fetch_hook_passes():
    ic.assert_fetch_hook_is_framework_wrapper(_ProfileStub(None))


def test_framework_wrapper_fetch_hook_passes():
    from stips.fetch import make_fetch_data

    hook = make_fetch_data(_backend, lambda env: {})
    ic.assert_fetch_hook_is_framework_wrapper(_ProfileStub(hook))


def test_hand_rolled_fetch_hook_fails():
    def fetch_data(night, config, *, overwrite=False):  # pragma: no cover
        return "ok"

    with pytest.raises(AssertionError, match="make_fetch_data"):
        ic.assert_fetch_hook_is_framework_wrapper(_ProfileStub(fetch_data))
