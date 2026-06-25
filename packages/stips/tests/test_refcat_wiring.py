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
