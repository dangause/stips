from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core.run import RunConfig  # noqa: E402


def _write(tmp_path, extra):
    cfg = {"object": "x", "ra": 1.0, "dec": 2.0, "bands": ["r"]}
    cfg.update(extra)
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_refcat_defaults_when_section_absent(tmp_path):
    # Staging default is "monster" (behavior-preserving) until validated.
    cfg = RunConfig.from_yaml(_write(tmp_path, {}))
    assert cfg.refcat_mode == "monster"
    assert cfg.refcat_radius_deg == 0.3
    assert cfg.refcat_gaia_quality is None


def test_refcat_gaia_ps1_opt_in(tmp_path):
    cfg = RunConfig.from_yaml(_write(tmp_path, {"refcat": {"mode": "gaia_ps1"}}))
    assert cfg.refcat_mode == "gaia_ps1"


def test_refcat_section_parsed(tmp_path):
    cfg = RunConfig.from_yaml(
        _write(tmp_path, {"refcat": {"mode": "monster", "radius_deg": 0.5}})
    )
    assert cfg.refcat_mode == "monster"
    assert cfg.refcat_radius_deg == 0.5


def test_refcat_invalid_mode_raises(tmp_path):
    with pytest.raises(ValueError, match="bogus"):
        RunConfig.from_yaml(_write(tmp_path, {"refcat": {"mode": "bogus"}}))


def test_run_refcat_step_calls_ensure(monkeypatch):
    from unittest import mock

    import stips.core.run as run
    from stips.core.refcat import RefcatResult

    seen = {}

    def fake_ensure(config, ra, dec, **k):
        seen.update(ra=ra, dec=dec, **k)
        return RefcatResult(mode=k.get("mode", "gaia_ps1"))

    monkeypatch.setattr(run, "ensure_refcats", fake_ensure)
    cfg = run.RunConfig(
        object_name="x",
        ra=210.9,
        dec=54.3,
        bands=["r"],
        refcat_mode="gaia_ps1",
        refcat_radius_deg=0.4,
    )
    run._run_refcat_step(cfg, config=mock.Mock(), result=mock.Mock(), dry_run=False)
    assert seen["ra"] == 210.9
    assert seen["mode"] == "gaia_ps1"
    assert seen["radius_deg"] == 0.4


def test_run_refcat_step_dry_run_skips(monkeypatch):
    from unittest import mock

    import stips.core.run as run

    called = []
    monkeypatch.setattr(run, "ensure_refcats", lambda *a, **k: called.append(1))
    cfg = run.RunConfig(object_name="x", ra=210.9, dec=54.3, bands=["r"])
    run._run_refcat_step(cfg, config=mock.Mock(), result=mock.Mock(), dry_run=True)
    assert called == []


def test_run_refcat_step_failure_is_early_exit(monkeypatch):
    """A failed ensure (e.g. missing astroquery) must abort the run loudly,
    not fall through to science and die with MissingDatasetTypeError."""
    from unittest import mock

    import stips.core.run as run
    from stips.core.refcat import RefcatResult

    def fake_ensure(config, ra, dec, **k):
        return RefcatResult(
            mode="gaia_ps1",
            gaia_status="failed",
            ps1_status="failed",
            error="gaia: No module named 'astroquery'",
        )

    monkeypatch.setattr(run, "ensure_refcats", fake_ensure)
    cfg = run.RunConfig(
        object_name="x", ra=210.9, dec=54.3, bands=["r"], refcat_mode="gaia_ps1"
    )
    result = mock.Mock()
    early_exit = run._run_refcat_step(
        cfg, config=mock.Mock(), result=result, dry_run=False
    )
    assert early_exit is result
    assert result.success is False
    assert "astroquery" in result.error
    assert "reference catalogs" in result.error


def test_run_refcat_step_success_returns_none(monkeypatch):
    from unittest import mock

    import stips.core.run as run
    from stips.core.refcat import RefcatResult

    monkeypatch.setattr(
        run,
        "ensure_refcats",
        lambda *a, **k: RefcatResult(
            mode="gaia_ps1", gaia_status="covered", ps1_status="covered"
        ),
    )
    cfg = run.RunConfig(
        object_name="x", ra=210.9, dec=54.3, bands=["r"], refcat_mode="gaia_ps1"
    )
    assert (
        run._run_refcat_step(cfg, config=mock.Mock(), result=mock.Mock(), dry_run=False)
        is None
    )


def test_cli_refcat_fetch_dispatches(monkeypatch):
    from unittest import mock

    import stips.cli as cli
    from click.testing import CliRunner
    from stips.core.refcat import RefcatResult

    captured = {}
    monkeypatch.setattr(cli, "_load_config", lambda ctx: mock.Mock())
    monkeypatch.setattr(
        "stips.core.refcat.ensure_refcats",
        lambda config, ra, dec, **k: captured.update(ra=ra, dec=dec, **k)
        or RefcatResult(mode=k.get("mode", "gaia_ps1")),
    )
    result = CliRunner().invoke(
        cli.cli,
        ["refcat", "fetch", "--ra", "210.91", "--dec", "54.31", "--radius", "0.4"],
    )
    assert result.exit_code == 0, result.output
    assert captured["ra"] == 210.91
    assert captured["radius_deg"] == 0.4
    assert captured["mode"] == "gaia_ps1"


def test_cli_refcat_fetch_exits_nonzero_when_a_catalog_fails(monkeypatch):
    """A failed PS1 (or Gaia) fetch must not exit 0: callers such as the paper
    rebuild driver retry on a non-zero exit, and a silent PS1 failure on the
    PG1323-086 Landolt field cost that night's standards (2026-10-07)."""
    from unittest import mock

    import stips.cli as cli
    from click.testing import CliRunner
    from stips.core.refcat import RefcatResult

    monkeypatch.setattr(cli, "_load_config", lambda ctx: mock.Mock())
    monkeypatch.setattr(
        "stips.core.refcat.ensure_refcats",
        lambda config, ra, dec, **k: RefcatResult(
            mode="gaia_ps1", gaia_status="fetched", ps1_status="failed",
            error="ps1: HTTP 503",
        ),  # fmt: skip
    )
    result = CliRunner().invoke(
        cli.cli, ["refcat", "fetch", "--ra", "201.41", "--dec", "-8.82"]
    )
    assert result.exit_code != 0
    assert "ps1" in result.output


def test_cli_refcat_status_computes_coverage_in_stack(monkeypatch):
    """``refcat status`` must not need ``lsst`` in the venv, same as ``fetch``.

    It called ``stips_refcats.cones_to_htm`` directly, which imports
    ``lsst.geom`` and so crashed in the plain venv with ModuleNotFoundError.
    It must use the venv-safe HTM path (in-stack snippet fallback) instead.
    """
    from unittest import mock

    import stips.cli as cli
    import stips.core.refcat as rc
    from click.testing import CliRunner

    def _no_lsst(cones, depth=7):
        raise ModuleNotFoundError("No module named 'lsst.geom'")

    scripts = []

    def _fake_stack_json(script, config):
        scripts.append(script)
        return [100, 101, 102]

    present = {"gaia_dr3": [100, 101, 102], "panstarrs1_dr2": [100]}
    monkeypatch.setattr(cli, "_load_config", lambda ctx: mock.Mock())
    monkeypatch.setattr(rc, "cones_to_htm", _no_lsst)
    monkeypatch.setattr(rc, "run_butler_python_json", _fake_stack_json)
    monkeypatch.setattr(
        rc.butler_query,
        "dataset_data_id_values",
        lambda config, dataset_type, collections, dimension: present[dataset_type],
    )
    result = CliRunner().invoke(
        cli.cli, ["refcat", "status", "--ra", "210.91", "--dec", "54.31"]
    )
    assert result.exit_code == 0, result.output
    # HTM coverage came from the in-stack snippet, for the requested cone.
    assert len(scripts) == 1 and "HtmIndexer" in scripts[0]
    assert "(210.91, 54.31, 0.3)" in scripts[0]
    assert "gaia_dr3: 3/3 trixels present" in result.output
    assert "panstarrs1_dr2: 1/3 trixels present" in result.output


def test_refcat_null_section_defaults_to_monster(tmp_path):
    cfg = RunConfig.from_yaml(_write(tmp_path, {"refcat": None}))
    assert cfg.refcat_mode == "monster"
    assert cfg.refcat_radius_deg == 0.3


@pytest.mark.parametrize("section", ["gaia_ps1", ["gaia"], 3])
def test_refcat_non_dict_section_is_rejected(tmp_path, section):
    with pytest.raises(ValueError, match="refcat: must be a mapping") as exc:
        RunConfig.from_yaml(_write(tmp_path, {"refcat": section}))
    assert repr(section) in str(exc.value)


# ---------------------------------------------------------------------------
# _run_bootstrap_step: refcat.mode -> require_monster (issue #75)
# ---------------------------------------------------------------------------


def _patch_bootstrap(monkeypatch, *, needs=True, result=None, monster_run=True):
    from stips.core import bootstrap, butler_query

    calls = []
    monkeypatch.setattr(
        butler_query,
        "collection_exists",
        lambda config, name: monster_run if name == bootstrap.MONSTER_RUN else True,
    )

    def fake_run(config, **kw):
        calls.append(kw)
        return result or bootstrap.BootstrapResult(True, None)

    monkeypatch.setattr(bootstrap, "needs_bootstrap", lambda config: needs)
    monkeypatch.setattr(bootstrap, "run", fake_run)
    import stips.core.run as run

    monkeypatch.setattr(run, "_get_step_log_file", lambda step: None)
    return calls


@pytest.mark.parametrize(
    "mode, required",
    [("monster", True), ("gaia_ps1", False), ("gaia", False)],
)
def test_run_bootstrap_step_passes_require_monster(
    monkeypatch, tmp_path, mode, required
):
    from types import SimpleNamespace

    import stips.core.run as run

    calls = _patch_bootstrap(monkeypatch)
    out = run._run_bootstrap_step(
        SimpleNamespace(repo=tmp_path / "repo"),
        SimpleNamespace(refcat_mode=mode),
        dry_run=False,
        run_log_dir=tmp_path,
    )
    assert out is None
    assert len(calls) == 1
    assert calls[0]["require_monster"] is required


def test_run_bootstrap_step_failure_is_early_exit(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import stips.core.run as run
    from stips.core.bootstrap import BootstrapResult

    _patch_bootstrap(
        monkeypatch, result=BootstrapResult(False, "No MONSTER refcat shards")
    )
    out = run._run_bootstrap_step(
        SimpleNamespace(repo=tmp_path / "repo"),
        SimpleNamespace(refcat_mode="monster"),
        dry_run=False,
        run_log_dir=tmp_path,
    )
    assert out is not None
    assert out.success is False
    assert "No MONSTER refcat shards" in out.error
    assert out.log_dir == str(tmp_path)


@pytest.mark.parametrize("needs, dry_run", [(False, False), (True, True)])
def test_run_bootstrap_step_skips(monkeypatch, tmp_path, needs, dry_run):
    from types import SimpleNamespace

    import stips.core.run as run

    calls = _patch_bootstrap(monkeypatch, needs=needs)
    out = run._run_bootstrap_step(
        SimpleNamespace(repo=tmp_path / "repo"),
        SimpleNamespace(refcat_mode="monster"),
        dry_run=dry_run,
        run_log_dir=tmp_path,
    )
    assert out is None
    assert calls == []


@pytest.mark.parametrize(
    "mode, monster_run, called",
    [
        # initialized repo without the MONSTER run, now in monster mode:
        # bootstrap again so shards are ingested or the clear error surfaces
        ("monster", False, True),
        ("gaia_ps1", False, False),
        ("monster", True, False),
    ],
)
def test_run_bootstrap_step_monster_mode_needs_monster_run(
    monkeypatch, tmp_path, mode, monster_run, called
):
    from types import SimpleNamespace

    import stips.core.run as run

    calls = _patch_bootstrap(monkeypatch, needs=False, monster_run=monster_run)
    out = run._run_bootstrap_step(
        SimpleNamespace(repo=tmp_path / "repo"),
        SimpleNamespace(refcat_mode=mode),
        dry_run=False,
        run_log_dir=tmp_path,
    )
    assert out is None
    if called:
        assert len(calls) == 1
        assert calls[0]["require_monster"] is True
    else:
        assert calls == []


def test_run_invalid_refcat_mode_returns_failure(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import stips.core.run as run
    from stips.core import bootstrap

    monkeypatch.setattr(run, "_setup_run_logging", lambda run_id, config: tmp_path)

    def boom(*a, **k):
        raise AssertionError("no bootstrap")

    monkeypatch.setattr(bootstrap, "needs_bootstrap", boom)
    p = _write(tmp_path, {"refcat": {"mode": "bogus"}})
    out = run.run(p, SimpleNamespace(repo=tmp_path / "repo"))
    assert out.success is False
    assert "bogus" in out.error
    assert out.log_dir == str(tmp_path)
