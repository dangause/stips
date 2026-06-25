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
