"""Unit tests for scripts/paper/nightly.py — the paper's nightly robust medians."""

from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "paper"))

import nightly  # noqa: E402

# MJD 60107 = UT 20230612; 60108 = UT 20230613.
NIGHT_A, NIGHT_B = 60107.2, 60108.2


def _row(mjd, band, mag, err=0.01, snr=100.0, system="AB"):
    return dict(mjd=str(mjd), band=band, mag=str(mag), mag_err=str(err),
                snr=str(snr), mag_system=system,
                days_since_explosion=str(mjd - 60082.75))  # fmt: skip


@pytest.fixture
def table():
    return [
        # Night A, rp: four good visits and one cloud-hit outlier (+0.6 mag).
        _row(NIGHT_A + 0.00, "rp", 13.00),
        _row(NIGHT_A + 0.01, "rp", 13.02),
        _row(NIGHT_A + 0.02, "rp", 12.98),
        _row(NIGHT_A + 0.03, "rp", 13.01),
        _row(NIGHT_A + 0.04, "rp", 13.60),
        # Night A, rp: below S/N 5 -> ignored entirely.
        _row(NIGHT_A + 0.05, "rp", 15.00, err=0.3, snr=3.0),
        # Night A, Cousins r (Vega): same night, must stay its own series.
        _row(NIGHT_A + 0.06, "r", 12.80, err=0.02, system="Vega"),
        _row(NIGHT_A + 0.07, "r", 12.84, err=0.02, system="Vega"),
        # Night B, ip: a single visit -> its own error.
        _row(NIGHT_B, "ip", 13.50, err=0.017),
        # Night B, rp: only a non-finite mag -> no point.
        _row(NIGHT_B, "rp", "nan", err="nan", snr=50.0),
        # Night B, ip: a blank (non-detection) row, as lightcurve.csv writes it.
        _row(NIGHT_B, "ip", "", err="", snr=1.2),
    ]


def test_one_point_per_night_and_band(table):
    out = nightly.nightly(table)
    assert [(r["band"], r["night"]) for r in out] == [
        ("ip", "20230613"),
        ("r", "20230612"),
        ("rp", "20230612"),
    ]
    assert {r["band"]: r["mag_system"] for r in out} == {
        "ip": "AB",
        "r": "Vega",
        "rp": "AB",
    }


def test_outlier_rejected_and_median_recomputed(table):
    rp = next(r for r in nightly.nightly(table) if r["band"] == "rp")
    assert rp["n_used"] == 4 and rp["n_rejected"] == 1
    kept = [13.00, 13.02, 12.98, 13.01]
    assert rp["mag"] == pytest.approx(statistics.median(kept))
    assert rp["mag_err"] == pytest.approx(1.2533 * statistics.pstdev(kept) / 2.0)
    assert rp["mjd"] == pytest.approx(NIGHT_A + 0.015)


def test_single_point_keeps_its_own_error(table):
    ip = next(r for r in nightly.nightly(table) if r["band"] == "ip")
    assert ip["n_used"] == 1 and ip["mag"] == 13.50 and ip["mag_err"] == 0.017


def test_clip_floor_protects_tight_nights():
    # MAD ~0.005 mag: 3 MAD would reject the 0.1 mag point; the 0.15 floor keeps it.
    rows = [
        _row(NIGHT_A + i / 100, "ip", m)
        for i, m in enumerate([14.0, 14.005, 13.995, 14.1])
    ]
    (out,) = nightly.nightly(rows)
    assert out["n_used"] == 4 and out["n_rejected"] == 0


@pytest.mark.parametrize("extra, n_rejected", [(13.40, 0), (13.50, 1)])
def test_mad_is_normal_scaled(extra, n_rejected):
    # Median 13.0, raw MAD 0.1 -> scaled 0.148, limit 0.445 mag: +0.40 stays
    # (a raw-MAD limit of 0.30 would reject it), +0.50 goes.
    mags = [13.0, 13.1, 12.9, 13.0, 13.1, 12.9, 13.0, extra]
    (out,) = nightly.nightly(
        [_row(NIGHT_A + i / 100, "rp", m) for i, m in enumerate(mags)]
    )
    assert out["n_rejected"] == n_rejected


def test_csv_round_trip(table, tmp_path):
    path = tmp_path / "lightcurve_nightly.csv"
    nightly.write_csv(nightly.nightly(table), path)
    rows = list(csv.DictReader(open(path)))
    assert list(rows[0]) == nightly.FIELDS
    assert len(rows) == 3
    assert all(math.isfinite(float(r["mag"])) for r in rows)
