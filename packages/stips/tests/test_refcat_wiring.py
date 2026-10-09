from __future__ import annotations

import sys
from pathlib import Path

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
