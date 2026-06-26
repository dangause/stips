from unittest import mock

import stips.core.dia as dia


def test_find_template_auto_prefers_ps1_for_ri(monkeypatch):
    monkeypatch.setattr(
        dia, "_collection_exists", lambda config, name: name == "templates/ps1/r"
    )
    got = dia.find_template(config=mock.Mock(), band="r", strategy="auto")
    assert got == "templates/ps1/r"


def test_find_template_auto_uses_coadd_for_bv(monkeypatch):
    monkeypatch.setattr(dia, "_collection_exists", lambda config, name: True)
    monkeypatch.setattr(
        dia, "_find_coadd_template", lambda config, band: "templates/deep/tract1/v"
    )
    got = dia.find_template(config=mock.Mock(), band="v", strategy="auto")
    assert got == "templates/deep/tract1/v"


def test_find_template_auto_ri_falls_back_to_coadd_without_ps1(monkeypatch):
    monkeypatch.setattr(dia, "_collection_exists", lambda config, name: False)
    monkeypatch.setattr(
        dia, "_find_coadd_template", lambda config, band: "templates/deep/tract1/r"
    )
    got = dia.find_template(config=mock.Mock(), band="r", strategy="auto")
    assert got == "templates/deep/tract1/r"


def test_auto_template_builds_ps1_for_ri_and_coadd_for_bv(monkeypatch):
    import stips.core.run as run

    built = []
    monkeypatch.setattr(
        run,
        "_run_ps1_templates",
        lambda run_cfg, config, result, dry_run, bands=None: built.append(
            ("ps1", tuple(bands))
        ),
    )
    monkeypatch.setattr(
        run,
        "_run_coadd_templates",
        lambda run_cfg, config, result, science_cfg, dry_run, bands=None: built.append(
            ("coadd", tuple(bands))
        ),
    )
    cfg = run.RunConfig(
        object_name="x",
        ra=1.0,
        dec=2.0,
        bands=["r", "i", "b", "v"],
        template_type="auto",
        template_nights=["20230728"],
    )
    out = run._run_auto_templates(
        cfg,
        config=mock.Mock(),
        result=mock.Mock(),
        science_cfg=mock.Mock(),
        dry_run=True,
    )
    assert out is None
    assert ("ps1", ("r", "i")) in built
    assert ("coadd", ("b", "v")) in built


def test_auto_template_skips_coadd_without_template_nights(monkeypatch):
    import stips.core.run as run

    built = []
    monkeypatch.setattr(
        run,
        "_run_ps1_templates",
        lambda run_cfg, config, result, dry_run, bands=None: built.append("ps1"),
    )
    monkeypatch.setattr(
        run,
        "_run_coadd_templates",
        lambda *a, **k: built.append("coadd"),
    )
    cfg = run.RunConfig(
        object_name="x",
        ra=1.0,
        dec=2.0,
        bands=["r", "b"],
        template_type="auto",
        template_nights=[],
    )
    run._run_auto_templates(
        cfg,
        config=mock.Mock(),
        result=mock.Mock(),
        science_cfg=mock.Mock(),
        dry_run=True,
    )
    # PS1 runs for r; coadd skipped because no template_nights for b.
    assert "ps1" in built
    assert "coadd" not in built
