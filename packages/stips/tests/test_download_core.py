"""Tests for stips.core.download (extracted download orchestration, F-041).

Covers YAML night detection, on-disk missing-night detection, and the
per-night fetch loop's ok/not_found/failed accounting with a mocked
``fetch_data`` hook — plus the CLI handler's missing-config error.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from click.testing import CliRunner
from stips import cli as cli_module
from stips.core import download


def _config(raw_parent_dir: Path | None = None, fetch_data=None):
    profile = SimpleNamespace(name="TestCam", fetch_data=fetch_data)
    return SimpleNamespace(
        raw_parent_dir=raw_parent_dir,
        require_profile=lambda: profile,
    )


# ---------------------------------------------------------------------------
# nights_from_config
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "pipeline.yaml"
    p.write_text(text)
    return p


def test_nights_from_config_merges_science_and_coadd_template(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
science:
  nights: [20230519, 20230521]
template:
  type: coadd
  nights: [20231211, 20230519]
""",
    )
    # De-duplicated (20230519 appears in both), stringified, sorted.
    assert download.nights_from_config(p) == ["20230519", "20230521", "20231211"]


def test_nights_from_config_ignores_ps1_template_nights(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
science:
  nights: [20230519]
template:
  type: ps1
  nights: [20231211]
""",
    )
    assert download.nights_from_config(p) == ["20230519"]


def test_nights_from_config_empty_or_missing_sections(tmp_path):
    assert download.nights_from_config(_write_yaml(tmp_path, "")) == []
    assert download.nights_from_config(_write_yaml(tmp_path, "object: x\n")) == []


# ---------------------------------------------------------------------------
# has_raw_data / missing_nights
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fname", ["a.fits", "a.fits.gz"])
def test_has_raw_data_true_with_fits(tmp_path, fname):
    (tmp_path / "20230519" / "raw").mkdir(parents=True)
    (tmp_path / "20230519" / "raw" / fname).touch()
    assert download.has_raw_data("20230519", _config(tmp_path)) is True


def test_has_raw_data_false_for_missing_or_empty_dir(tmp_path):
    cfg = _config(tmp_path)
    assert download.has_raw_data("20230519", cfg) is False  # no dir at all
    (tmp_path / "20230521" / "raw").mkdir(parents=True)
    assert download.has_raw_data("20230521", cfg) is False  # dir but no FITS


def test_missing_nights_filters_and_preserves_order(tmp_path):
    (tmp_path / "20230521" / "raw").mkdir(parents=True)
    (tmp_path / "20230521" / "raw" / "x.fits").touch()
    cfg = _config(tmp_path)
    got = download.missing_nights(["20230523", "20230521", "20230519"], cfg)
    assert got == ["20230523", "20230519"]


# ---------------------------------------------------------------------------
# fetch_nights accounting
# ---------------------------------------------------------------------------


def test_fetch_nights_accounting_with_mocked_hook():
    def hook(night, config, *, overwrite=False):
        if night == "n_ok":
            return "ok"
        if night == "n_missing":
            return "not_found"
        if night == "n_raises":
            raise RuntimeError("archive down")
        return "error"  # any other status counts as failed

    cfg = _config(fetch_data=hook)
    result = download.fetch_nights(["n_ok", "n_missing", "n_raises", "n_bad"], cfg)

    assert result.succeeded == ["n_ok"]
    assert result.not_in_archive == ["n_missing"]
    assert result.failed == ["n_raises", "n_bad"]
    assert result.success is False


def test_fetch_nights_success_when_nothing_failed():
    hook = mock.Mock(return_value="ok")
    cfg = _config(fetch_data=hook)
    result = download.fetch_nights(["a", "b"], cfg, overwrite=True)
    assert result.succeeded == ["a", "b"]
    assert result.success is True
    # overwrite is forwarded to the hook
    hook.assert_called_with("b", cfg, overwrite=True)


def test_fetch_nights_not_found_only_is_not_a_failure():
    cfg = _config(fetch_data=mock.Mock(return_value="not_found"))
    result = download.fetch_nights(["a"], cfg)
    assert result.not_in_archive == ["a"]
    assert result.success is True  # missing-from-archive is not an outright failure


def test_fetch_nights_emits_progress_events():
    def hook(night, config, *, overwrite=False):
        if night == "bad":
            raise RuntimeError("boom")
        return "ok"

    events = []
    cfg = _config(fetch_data=hook)
    download.fetch_nights(
        ["good", "bad"], cfg, on_event=lambda n, s, e: events.append((n, s, e))
    )
    assert events == [
        ("good", "start", None),
        ("good", "ok", None),
        ("bad", "start", None),
        ("bad", "failed", "boom"),
    ]


# ---------------------------------------------------------------------------
# CLI handler: missing-config error (no nights and no -c)
# ---------------------------------------------------------------------------


def test_download_cli_no_nights_and_no_config_errors():
    cfg = _config(Path("/tmp/raw"), fetch_data=mock.Mock(return_value="ok"))
    with mock.patch.object(cli_module, "_load_config", return_value=cfg):
        res = CliRunner().invoke(cli_module.cli, ["download"])
    assert res.exit_code != 0
    assert "No nights given and no -c config" in res.output
