"""Pre-ingest screen for raw frames that cannot be processed (``screen_raw_frames``).

Observatory raw directories carry the occasional frame that is a real FITS file
but not a usable exposure: Nickel nights include 82x50 and 57x25 "bias"/"flat"
readouts (test subframes) beside the 1056x1024 science geometry, and a transfer
can leave a file shorter than its header declares. ``butler ingest-raws`` takes
the whole directory and accepts both. The subframe then reaches ISR, whose
overscan list comes back empty for the mismatched geometry, and the stack raises
``UnboundLocalError: noiseProvenanceString`` -- failing that ONE quantum, which
fails the bias combine, which fails the whole night (real: 2023ixf 20230817).

The screen runs before ingest and drops those frames, naming each with a reason,
so the night proceeds on its good frames.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import calibs, pipeline  # noqa: E402
from stips.core.pipeline import (  # noqa: E402
    raw_ingest_locations,
    screen_raw_frames,
)

fits = pytest.importorskip("astropy.io.fits")
np = pytest.importorskip("numpy")

FULL = (1024, 1056)  # numpy (ny, nx) for a 1056x1024 Nickel frame


def _write(raw_dir: Path, name: str, shape=FULL, compressed=False) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    data = np.zeros(shape, dtype=np.int16)
    path = raw_dir / name
    if compressed:
        fits.HDUList([fits.PrimaryHDU(), fits.CompImageHDU(data)]).writeto(path)
    else:
        fits.PrimaryHDU(data).writeto(path)
    return path


def _names(paths):
    return sorted(p.name for p in paths)


def test_clean_night_accepts_everything(tmp_path):
    for i in range(5):
        _write(tmp_path, f"d{i}.fits")
    screen = screen_raw_frames(tmp_path)
    assert _names(screen.accepted) == [f"d{i}.fits" for i in range(5)]
    assert screen.rejected == []


def test_subframe_is_rejected_with_its_shape(tmp_path):
    for i in range(4):
        _write(tmp_path, f"d{i}.fits")
    _write(tmp_path, "d250001.fits", shape=(50, 82))

    screen = screen_raw_frames(tmp_path)

    assert "d250001.fits" not in _names(screen.accepted)
    ((name, reason),) = screen.rejected
    assert name == "d250001.fits"
    assert "82x50" in reason and "1056x1024" in reason


def test_truncated_file_is_rejected(tmp_path):
    for i in range(3):
        _write(tmp_path, f"d{i}.fits")
    bad = _write(tmp_path, "d311.fits")
    bad.write_bytes(bad.read_bytes()[: 2880 * 50])  # header intact, data cut short

    screen = screen_raw_frames(tmp_path)

    assert "d311.fits" not in _names(screen.accepted)
    assert [n for n, _ in screen.rejected] == ["d311.fits"]
    assert "truncated" in screen.rejected[0][1]


def test_unreadable_file_is_rejected(tmp_path):
    _write(tmp_path, "d0.fits")
    (tmp_path / "junk.fits").write_bytes(b"not a fits file")
    screen = screen_raw_frames(tmp_path)
    assert _names(screen.accepted) == ["d0.fits"]
    assert [n for n, _ in screen.rejected] == ["junk.fits"]


def test_compressed_frames_use_their_image_shape(tmp_path):
    """A .fits.fz tile-compressed frame is judged by ZNAXISn, not the table."""
    for i in range(3):
        _write(tmp_path, f"d{i}.fits.fz", compressed=True)
    _write(tmp_path, "sub.fits.fz", shape=(25, 57), compressed=True)
    screen = screen_raw_frames(tmp_path)
    assert _names(screen.accepted) == [f"d{i}.fits.fz" for i in range(3)]
    assert [n for n, _ in screen.rejected] == ["sub.fits.fz"]


def test_larger_minority_shape_is_left_to_ingest(tmp_path):
    """Only SMALLER frames are screened; anything else is ingest's call."""
    for i in range(3):
        _write(tmp_path, f"d{i}.fits")
    _write(tmp_path, "big.fits", shape=(2048, 2112))
    screen = screen_raw_frames(tmp_path)
    assert "big.fits" in _names(screen.accepted)
    assert screen.rejected == []


def test_missing_dir_is_empty(tmp_path):
    screen = screen_raw_frames(tmp_path / "nope")
    assert screen.accepted == [] and screen.rejected == []


def test_ingest_locations_pass_the_dir_when_clean(tmp_path):
    """No change to the ingest call for a clean night."""
    _write(tmp_path, "d0.fits")
    assert raw_ingest_locations(tmp_path) == [str(tmp_path)]


def test_ingest_locations_list_accepted_files_when_some_rejected(tmp_path):
    for i in range(2):
        _write(tmp_path, f"d{i}.fits")
    _write(tmp_path, "sub.fits", shape=(50, 82))
    locs = raw_ingest_locations(tmp_path)
    assert sorted(Path(p).name for p in locs) == ["d0.fits", "d1.fits"]


# --------------------------------------------------------------------------- #
# Wired in: `stips calibs` ingests only the screened frames.
# --------------------------------------------------------------------------- #


def test_calibs_ingests_only_accepted_frames(tmp_path):
    raw_dir = tmp_path / "raw"
    for i in range(3):
        _write(raw_dir, f"d{i}.fits")
    _write(raw_dir, "d250001.fits", shape=(50, 82))

    config = MagicMock()
    config.repo = tmp_path
    config.cp_pipe_dir = "/cp"
    prof = MagicMock()
    prof.collection_prefix = "Nickel"
    prof.name = "Nickel"
    config.require_profile.return_value = prof

    run_butler = MagicMock(name="run_butler")
    run_butler.return_value = SimpleNamespace(returncode=0, stderr="")
    with (
        patch.object(calibs, "run_butler", run_butler),
        patch.object(pipeline, "run_butler", run_butler),
        patch.object(calibs, "butler_query", MagicMock()),
        patch.object(pipeline.butler_query, "list_instruments", lambda config: {}),
        patch.object(calibs, "get_raw_dir", return_value=raw_dir),
        patch.object(calibs, "find_aliasing_exposure_ids", return_value={}),
    ):
        calibs.run("20230817", config, jobs=1, executor=MagicMock(), skip_curated=True)

    ingest = next(
        c.args[0] for c in run_butler.call_args_list if c.args[0][0] == "ingest-raws"
    )
    locations = ingest[2 : ingest.index("--transfer")]
    assert sorted(Path(p).name for p in locations) == ["d0.fits", "d1.fits", "d2.fits"]
