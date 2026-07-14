"""Shared instrument-contract test harness.

A telescope added under ``instruments/<name>/`` gets shared test coverage by
convention: the auto-discovered contract module
(``packages/stips/tests/test_instrument_contracts.py``) discovers every
instrument dir and runs the assertions below against it. See
``docs/instrument-contract.md`` for what a fork must provide.

Design notes
------------
* **Importable, not a conftest.** This lives in the installed ``stips`` package
  so callers ``import`` it explicitly (``from stips.testing import
  instrument_contract``). It never relies on ambient ``conftest`` resolution,
  which previously collided across the two instrument test dirs.
* **Stack-free core.** The profile / exposure-id / fetch / translation contracts
  call the profile's declarative hooks directly and need only ``stips`` +
  ``astropy`` (imported lazily). Only :func:`active_instrument_dir` touches the
  LSST stack; callers that may run stack-free must ``pytest.importorskip`` a real
  ``lsst`` module (e.g. ``lsst.obs.base``) first -- never the ``lsst.obs.stips``
  namespace, which is importable from the editable install even without a stack.
* **Unique module names.** Every ``profile.py`` / ``fetch.py`` /
  ``contract_data.py`` loaded by path gets a unique synthetic module name keyed
  by the instrument, so loading several instruments in one process cannot shadow
  one another.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest import mock

# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InstrumentDirInfo:
    """A discovered ``instruments/<name>/`` directory and which assets it ships."""

    name: str
    path: Path

    @property
    def profile_path(self) -> Path:
        return self.path / "profile.py"

    @property
    def fetch_path(self) -> Path:
        return self.path / "fetch.py"

    @property
    def camera_dir(self) -> Path:
        return self.path / "camera"

    @property
    def testdata_dir(self) -> Path:
        return self.path / "testdata"

    @property
    def contract_data_path(self) -> Path:
        return self.path / "tests" / "contract_data.py"

    @property
    def has_profile(self) -> bool:
        return self.profile_path.is_file()

    @property
    def has_fetch(self) -> bool:
        return self.fetch_path.is_file()

    @property
    def has_camera(self) -> bool:
        return self.camera_dir.is_dir()

    @property
    def has_testdata(self) -> bool:
        return self.testdata_dir.is_dir()

    @property
    def has_contract_data(self) -> bool:
        return self.contract_data_path.is_file()


def find_repo_root(start: Optional[Path | str] = None) -> Path:
    """Walk upward from ``start`` (default: this file) to the repo root.

    The repo root is the first ancestor that contains both ``instruments/`` and
    ``packages/``.
    """
    p = Path(start).resolve() if start else Path(__file__).resolve()
    for cand in (p, *p.parents):
        if (cand / "instruments").is_dir() and (cand / "packages").is_dir():
            return cand
    raise RuntimeError(
        f"Could not locate repo root (instruments/ + packages/) from {p}"
    )


def discover_instruments(
    repo_root: Optional[Path | str] = None,
) -> list[InstrumentDirInfo]:
    """Return every ``instruments/<name>/`` dir that ships a ``profile.py``.

    Sorted by name for stable pytest parametrization ids.
    """
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    inst_root = root / "instruments"
    out: list[InstrumentDirInfo] = []
    if not inst_root.is_dir():
        return out
    for child in sorted(inst_root.iterdir()):
        if child.is_dir() and (child / "profile.py").is_file():
            out.append(InstrumentDirInfo(name=child.name, path=child))
    return out


# --------------------------------------------------------------------------- #
# Loading (by path, stack-free, collision-safe module names)
# --------------------------------------------------------------------------- #


def _load_module_by_path(path: Path, mod_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_profile(info: InstrumentDirInfo) -> Any:
    """Load the instrument's ``profile.py`` object by path, stack-free.

    ``profile.py`` does ``from fetch import fetch_data`` and ``from stips import
    ...``. We temporarily insert the instrument dir on ``sys.path`` and preload
    THIS instrument's ``fetch`` module under the bare name ``fetch`` so that
    import resolves to the right one even when several instruments are loaded in
    a single process; the environment is fully restored on exit.
    """
    inst_dir = str(info.path)
    saved_path = list(sys.path)
    saved_fetch = sys.modules.get("fetch")
    try:
        sys.path.insert(0, inst_dir)
        if info.has_fetch:
            sys.modules["fetch"] = _load_module_by_path(info.fetch_path, "fetch")
        prof_mod = _load_module_by_path(
            info.profile_path, f"_stips_contract_profile_{info.name}"
        )
        return prof_mod.profile
    finally:
        sys.path[:] = saved_path
        if saved_fetch is not None:
            sys.modules["fetch"] = saved_fetch
        else:
            sys.modules.pop("fetch", None)


def load_fetch(info: InstrumentDirInfo) -> Any:
    """Load the instrument's ``fetch.py`` module by path (stdlib-only at import)."""
    if not info.has_fetch:
        raise FileNotFoundError(f"{info.name} has no fetch.py")
    return _load_module_by_path(info.fetch_path, f"_stips_contract_fetch_{info.name}")


def load_contract_data(info: InstrumentDirInfo) -> Any:
    """Load the instrument's ``tests/contract_data.py`` fixtures module by path."""
    if not info.has_contract_data:
        raise FileNotFoundError(f"{info.name} has no tests/contract_data.py")
    return _load_module_by_path(
        info.contract_data_path, f"_stips_contract_data_{info.name}"
    )


@contextmanager
def active_instrument_dir(instrument_dir: Path | str) -> Iterator[Any]:
    """Bind ``INSTRUMENT_DIR`` to ``instrument_dir``, (re)load
    ``lsst.obs.stips.active``, and yield the freshly synthesized module.

    STACK-DEPENDENT: ``lsst.obs.stips.active`` imports the LSST stack. Callers
    that may run in a plain venv must ``pytest.importorskip`` a real ``lsst``
    module (e.g. ``lsst.obs.base``) BEFORE calling this. Restores the prior
    ``INSTRUMENT_DIR`` on exit.
    """
    prev = os.environ.get("INSTRUMENT_DIR")
    os.environ["INSTRUMENT_DIR"] = str(instrument_dir)
    try:
        import lsst.obs.stips.active as active

        yield importlib.reload(active)
    finally:
        if prev is None:
            os.environ.pop("INSTRUMENT_DIR", None)
        else:
            os.environ["INSTRUMENT_DIR"] = prev


# --------------------------------------------------------------------------- #
# Contract assertions (stack-free; each raises AssertionError on violation)
# --------------------------------------------------------------------------- #


def assert_profile_valid(profile: Any) -> None:
    """The profile loads and its required fields are populated and sane."""
    assert (
        isinstance(profile.name, str) and profile.name.strip()
    ), "profile.name must be a non-empty string"
    assert profile.collection_prefix, f"{profile.name}: collection_prefix must be set"
    assert profile.policy_name, f"{profile.name}: policy_name must be set"
    assert profile.instrument_class, f"{profile.name}: instrument_class must be set"
    assert profile.filter_key, f"{profile.name}: filter_key must be set"
    assert (
        profile.filters
    ), f"{profile.name}: filters (physical->band) must be non-empty"
    assert profile.header_map, f"{profile.name}: header_map must be non-empty"

    site = profile.site
    assert (
        -90.0 <= site.latitude <= 90.0
    ), f"{profile.name}: latitude {site.latitude} out of range"
    assert (
        -180.0 <= site.longitude <= 360.0
    ), f"{profile.name}: longitude {site.longitude} out of range"
    assert (
        -500.0 < site.elevation < 10000.0
    ), f"{profile.name}: implausible elevation {site.elevation}"


def assert_exposure_id_scheme(profile: Any, contract_data: Any) -> None:
    """exposure_id fits in 31 bits, encodes the seq number, is monotonic in seq,
    and visit_id mirrors it."""
    hooks = profile.hooks
    header = contract_data.SAMPLE_HEADER
    exp = hooks["exposure_id"](header)
    assert isinstance(exp, int), "exposure_id must be an int"
    assert 0 < exp < 2**31, f"exposure_id {exp} must be positive and fit in 31 bits"
    assert hooks["visit_id"](header) == exp, "visit_id must equal exposure_id"

    seq = contract_data.EXPECTED_SEQ
    assert (
        exp % 10000 == seq
    ), f"exposure_id low digits {exp % 10000} do not encode seq {seq}"

    plus_one = hooks["exposure_id"](contract_data.SAMPLE_HEADER_SEQ_PLUS_ONE)
    assert (
        plus_one == exp + 1
    ), f"exposure_id not monotonic in seq: seq+1 gave {plus_one}, expected {exp + 1}"


def assert_translation_contract(profile: Any, contract_data: Any) -> None:
    """The declarative hooks reproduce the pinned ``EXPECTED_TRANSLATION``."""
    import astropy.units as u
    from astropy.time import Time

    hooks = profile.hooks
    header = contract_data.SAMPLE_HEADER
    expected = contract_data.EXPECTED_TRANSLATION

    for key in (
        "observation_type",
        "day_obs",
        "observation_id",
        "exposure_id",
        "visit_id",
    ):
        if key in expected:
            got = hooks[key](header)
            assert got == expected[key], f"{key}: {got!r} != expected {expected[key]!r}"

    if "tracking_radec" in expected:
        coord = hooks["tracking_radec"](header)
        want_ra, want_dec = expected["tracking_radec"]
        assert (
            abs(coord.ra.to_value(u.deg) - want_ra) < 0.01
        ), f"tracking RA {coord.ra.to_value(u.deg)} != {want_ra}"
        assert (
            abs(coord.dec.to_value(u.deg) - want_dec) < 0.01
        ), f"tracking Dec {coord.dec.to_value(u.deg)} != {want_dec}"

    if "datetime_begin_mjd" in expected:
        t0 = hooks["datetime_begin"](header)
        assert isinstance(t0, Time), "datetime_begin must return an astropy Time"
        assert (
            abs(t0.mjd - expected["datetime_begin_mjd"]) < 1e-6
        ), f"datetime_begin mjd {t0.mjd} != {expected['datetime_begin_mjd']}"

    if "datetime_end_mjd" in expected:
        t1 = hooks["datetime_end"](header)
        assert isinstance(t1, Time), "datetime_end must return an astropy Time"
        assert (
            abs(t1.mjd - expected["datetime_end_mjd"]) < 1e-6
        ), f"datetime_end mjd {t1.mjd} != {expected['datetime_end_mjd']}"


def assert_observation_type_cases(profile: Any, contract_data: Any) -> None:
    """Optional: ``OBSERVATION_TYPE_CASES = [(header, expected), ...]`` all map."""
    cases = getattr(contract_data, "OBSERVATION_TYPE_CASES", None)
    if not cases:
        return
    hook_fn = profile.hooks["observation_type"]
    for header, expected in cases:
        got = hook_fn(header)
        assert got == expected, f"observation_type {got!r} != expected {expected!r}"


def assert_unknown_filter_contract(profile: Any, contract_data: Any) -> None:
    """Optional: ``UNKNOWN_FILTER`` pins the unknown-filter fallback/raise policy.

    ``UNKNOWN_FILTER = {"raw": "ZZZ", "raises": True}`` (hard error) or
    ``{"raw": "ZZZ", "raises": False, "result": "clear"}`` (fallback value).
    """
    spec = getattr(contract_data, "UNKNOWN_FILTER", None)
    if spec is None:
        return
    hook_fn = profile.hooks["unknown_filter"]
    raw = spec["raw"]
    if spec.get("raises"):
        raised = False
        try:
            hook_fn({}, raw)
        except ValueError:
            raised = True
        assert raised, f"unknown_filter({raw!r}) should raise ValueError"
    else:
        got = hook_fn({}, raw)
        assert (
            got == spec["result"]
        ), f"unknown_filter({raw!r}) -> {got!r}, expected {spec['result']!r}"


class FetchConfigStub:
    """Minimal stand-in for ``stips.core.config.Config`` as seen by fetch hooks:
    just ``raw_parent_dir`` plus the generic ``env`` block."""

    def __init__(self, env: dict, raw_parent_dir: Path | str = "/tmp/raw") -> None:
        self.raw_parent_dir = Path(raw_parent_dir)
        self.env = dict(env)


def assert_fetch_status_contract(fetch_module: Any, contract_data: Any) -> None:
    """``fetch_data`` maps the backend return code to ok / not_found / failed.

    Parameterized by the instrument's env schema: ``FETCH_NIGHT`` (a valid night
    string) and ``FETCH_ENV`` (the ``env`` block the hook reads). The backend
    ``_fetch_night`` is mocked, so this is network-free.

    Because the status mapping and env/night plumbing are hoisted into
    :func:`stips.fetch.make_fetch_data`, we assert the instrument actually wires
    the shared wrapper (its ``fetch_data`` closure is defined in ``stips.fetch``)
    rather than copy-pasting one -- that is what keeps the mapping single-source.
    """
    from stips import fetch as framework_fetch

    assert fetch_module.fetch_data.__module__ == framework_fetch.__name__, (
        f"{fetch_module.__name__}.fetch_data must be built via "
        "stips.fetch.make_fetch_data (shared wrapper), not a per-instrument copy"
    )

    night = contract_data.FETCH_NIGHT
    cfg = FetchConfigStub(contract_data.FETCH_ENV)
    for code, expected in ((0, "ok"), (2, "not_found"), (1, "failed")):
        with mock.patch.object(fetch_module, "_fetch_night", return_value=code):
            status = fetch_module.fetch_data(night, cfg, overwrite=True)
        assert (
            status == expected
        ), f"backend code {code} -> {status!r}, expected {expected!r}"
