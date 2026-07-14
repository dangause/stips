from pathlib import Path
from unittest import mock

import pytest
from stips_refcats.convert import convert_catalog


def test_convert_skips_when_map_exists(tmp_path: Path):
    out = tmp_path / "gaia-refcat-X"
    out.mkdir()
    (out / "filename_to_htm.ecsv").write_text("# map\n")
    src = tmp_path / "in.csv"
    src.write_text("ra,dec\n1,2\n")
    cfg = tmp_path / "cfg.py"
    cfg.write_text("")
    with mock.patch("stips_refcats.convert.subprocess.run") as run:
        result = convert_catalog("GAIA", src, cfg, out, force=False)
    run.assert_not_called()
    assert result == out / "filename_to_htm.ecsv"


def test_convert_runs_cli_and_returns_map(tmp_path: Path):
    out = tmp_path / "ps1-refcat-X"
    src = tmp_path / "in.csv"
    src.write_text("raMean,decMean\n1,2\n")
    cfg = tmp_path / "cfg.py"
    cfg.write_text("")

    def fake_run(cmd, check):
        out.mkdir(parents=True, exist_ok=True)
        (out / "filename_to_htm.ecsv").write_text("# map\n")
        return mock.Mock(returncode=0)

    with mock.patch(
        "stips_refcats.convert.subprocess.run", side_effect=fake_run
    ) as run:
        result = convert_catalog("PS1", src, cfg, out, force=False)
    run.assert_called_once()
    assert "convertReferenceCatalog" in run.call_args.args[0][0]
    assert result.exists()


def test_convert_raises_on_missing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        convert_catalog(
            "GAIA",
            tmp_path / "nope.csv",
            tmp_path / "c.py",
            tmp_path / "o",
            force=False,
        )
