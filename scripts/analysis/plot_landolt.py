#!/usr/bin/env python
"""Generate Landolt validation plots from analysis/landolt_validation_4nights.csv.

Produces three single-panel figures used in the AAS poster + assessment doc:

    analysis/landolt_residuals.png    — per-band photometric residual scatter
                                        (one point per measurement, per-night
                                        marker shape, per-point error bars)
    analysis/landolt_astrometry.png   — per-band match-distance scatter with
                                        per-band seeing (FWHM) annotation
    analysis/landolt_color_terms.png  — residual vs B−V with linear fits

Per-point error bars use the propagated photometric uncertainty
sqrt(pipeline_mag_err² + landolt_mag_err²); mean ± SEM is annotated at the top
of each band column. Seeing is computed per band from preliminary_visit_summary
psfSigma × pixel_scale × 2.355 (FWHM in arcsec).

Drops a single |residual| >= 2 mag outlier (a known V-band source-match
failure on SA 110-340 visit 90151051).
"""

from __future__ import annotations

import csv
import glob
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "analysis" / "landolt_validation_4nights.csv"
# Rigorous per-measurement PM-corrected vector residual CSV produced by
# scripts/analysis/landolt_pm_corrected_residuals.py — Gaia DR3 positions
# propagated to each visit's UTC-MJD, re-matched against the
# single_visit_star_unstandardized source catalog, with cos(dec) handled on RA.
PM_CSV_PATH = REPO_ROOT / "analysis" / "landolt_pm_corrected.csv"
OUT_DIR = REPO_ROOT / "analysis"

# Per-night psfSigma lookup is glob-based off the landolt_validation Butler repo.
LANDOLT_REPO = Path(
    "/Users/dangause/Developer/lick/lsst/data/nickel/landolt_validation_repo"
)

NICKEL_PIXEL_ARCSEC = 0.37
SIGMA_TO_FWHM = 2.355

BANDS = ["b", "v", "r", "i"]
BAND_COLORS = {"b": "#1f77b4", "v": "#2ca02c", "r": "#d62728", "i": "#8c564b"}
BAND_LABELS = {"b": "B", "v": "V", "r": "R", "i": "I"}

# Landolt-standard proper motions from Gaia DR3 (mas/yr). The Landolt catalog
# positions in scripts/config/landolt_validation/landolt_catalog.csv are at
# J2000.0 with no proper-motion correction, while LSST's astrometric refcat
# (descended from Gaia DR3 epoch 2016.0) carries Gaia PM. The raw Landolt
# match distances therefore mostly reflect PM drift (450 mas for a 20 mas/yr
# star over 22 years), not pipeline astrometric error. Subtracting the
# predicted PM displacement recovers the true astrometric noise floor.
LANDOLT_PM = {
    "PG 1323-086": (-0.76, -2.64),
    "PG 1530+057": (-19.51, -12.37),
    "PG 1633+099": (-19.10, -9.83),
    "SA 107-458": (-1.98, +7.85),
    "SA 109-199": (+1.70, -3.58),
    "SA 109-231": (+1.00, -15.53),
    "SA 110-340": (+1.68, -7.18),
    "SA 113-342": (+20.25, -1.20),
    "SA 114-670": (-7.95, -10.83),
    "SA 92-311": (-0.19, -3.32),
}
LANDOLT_EPOCH = 2000.0


def obs_epoch_from_night(night: str) -> float:
    """Decimal-year obs epoch from 'YYYYMMDD' night string."""
    y = int(night[:4])
    m = int(night[4:6])
    d = int(night[6:8])
    return y + (m - 1) / 12.0 + d / 365.0


def pm_displacement_mas(star: str, night: str) -> float:
    """Predicted Landolt → observation-epoch displacement magnitude in mas.

    Returns NaN if the star has no Gaia PM lookup; callers should skip.
    """
    pm = LANDOLT_PM.get(star)
    if pm is None:
        return float("nan")
    pmra, pmdec = pm
    dt = obs_epoch_from_night(night) - LANDOLT_EPOCH
    return float(np.hypot(pmra * dt, pmdec * dt))


# Distinct markers per observing night so multi-night structure is visible.
NIGHT_MARKERS = {
    "20210208": "o",
    "20240625": "s",
    "20240906": "^",
    "20240907": "D",
}

OUTLIER_THRESHOLD = 2.0
ASTROM_OUTLIER_CUT_MAS = 1000.0


def load_rows():
    with open(CSV_PATH) as fh:
        return list(csv.DictReader(fh))


def filter_outliers(rows):
    return [r for r in rows if abs(float(r["residual"])) < OUTLIER_THRESHOLD]


def total_err(r) -> float:
    """Quadrature sum of pipeline + Landolt-catalog photometric uncertainty."""
    pe = float(r.get("pipeline_mag_err") or 0)
    le = float(r.get("landolt_mag_err") or 0)
    return float(np.sqrt(pe**2 + le**2))


# ---------------------------------------------------------------------------
# psfSigma → per-band seeing FWHM
# ---------------------------------------------------------------------------


def load_psf_sigma_table() -> dict[tuple[str, str], float]:
    """Read psfSigma (px) from every preliminary_visit_summary FITS in the
    Landolt validation repo. Keyed by (str(visit), str(band)).
    """
    pat = f"{LANDOLT_REPO}/Nickel/runs/*/processCcd/*/run/preliminary_visit_summary/"
    fits_paths: list[str] = []
    for d in glob.glob(pat + "*"):
        for root, _, fs in os.walk(d):
            for f in fs:
                if f.endswith(".fits"):
                    fits_paths.append(os.path.join(root, f))

    table: dict[tuple[str, str], float] = {}
    for p in fits_paths:
        try:
            with fits.open(p) as hdul:
                for hd in hdul:
                    if hd.data is None or not hasattr(hd, "columns"):
                        continue
                    if "psfSigma" not in hd.columns.names:
                        continue
                    for row in hd.data:
                        table[(str(row["visit"]), str(row["band"]))] = float(
                            row["psfSigma"]
                        )
                    break
        except Exception:
            continue
    return table


def seeing_per_band(rows, psf_table) -> dict[str, tuple[float, int]]:
    """For each band, return (median FWHM in arcsec, N visits used)."""
    out: dict[str, tuple[float, int]] = {}
    for band in BANDS:
        sigmas = []
        for r in rows:
            if r["band"] != band:
                continue
            sigma = psf_table.get((r["visit"], r["band"]))
            if sigma is not None and np.isfinite(sigma):
                sigmas.append(sigma)
        if sigmas:
            fwhm = float(np.median(sigmas)) * NICKEL_PIXEL_ARCSEC * SIGMA_TO_FWHM
            out[band] = (fwhm, len(sigmas))
        else:
            out[band] = (float("nan"), 0)
    return out


# ---------------------------------------------------------------------------
# Scatter helpers
# ---------------------------------------------------------------------------


def _band_xpos(band: str) -> float:
    return BANDS.index(band)


def _jitter(n: int, scale: float = 0.18) -> np.ndarray:
    """Deterministic horizontal jitter so points in a band don't fully overlap."""
    if n <= 1:
        return np.zeros(n)
    return np.linspace(-0.5, 0.5, n) * scale


# ---------------------------------------------------------------------------
# Photometric residual scatter plot
# ---------------------------------------------------------------------------


def plot_residuals(rows, out_path: Path) -> None:
    """Per-band photometric residual scatter.

    One point per measurement, error bar = sqrt(pipeline² + landolt²) propagated
    photometric uncertainty. Marker shape encodes observing night so multi-
    night structure is visible. Mean ± SEM (N) annotated at the top of each
    band column inside the axes.
    """
    fig, ax = plt.subplots(figsize=(9.5, 6.0))

    # Pre-compute data extents so axis and labels can be set up first.
    all_resids = [float(r["residual"]) for r in rows]
    y_lo = min(all_resids) - 0.10
    y_hi = max(all_resids) + 0.35  # headroom for per-band labels at the top
    ax.set_ylim(y_lo, y_hi)
    label_y = y_hi - 0.08

    for band in BANDS:
        brows = [r for r in rows if r["band"] == band]
        if not brows:
            continue
        nights_here = sorted({r["night"] for r in brows})
        per_night = {n: [r for r in brows if r["night"] == n] for n in nights_here}
        sub_offsets = _jitter(len(nights_here), scale=0.32)
        for sub_offset, night in zip(sub_offsets, nights_here):
            nrows = per_night[night]
            xs = _band_xpos(band) + sub_offset + _jitter(len(nrows), scale=0.10)
            ys = np.array([float(r["residual"]) for r in nrows])
            es = np.array([total_err(r) for r in nrows])
            ax.errorbar(
                xs,
                ys,
                yerr=es,
                fmt=NIGHT_MARKERS.get(night, "o"),
                markersize=6.5,
                color=BAND_COLORS[band],
                mec="black",
                mew=0.5,
                lw=0,
                elinewidth=1.0,
                ecolor="black",
                alpha=0.85,
                zorder=2,
            )

        resids = np.array([float(r["residual"]) for r in brows])
        mean = float(resids.mean())
        sem = (
            float(resids.std(ddof=1) / np.sqrt(len(resids))) if len(resids) > 1 else 0.0
        )
        ax.text(
            _band_xpos(band),
            label_y,
            f"{mean:+.3f} ± {sem:.3f}\nN={len(resids)}",
            ha="center",
            va="top",
            fontsize=10,
            fontweight="bold",
        )

    # Per-night marker legend.
    night_handles = [
        plt.Line2D(
            [0],
            [0],
            marker=NIGHT_MARKERS[n],
            color="black",
            linestyle="",
            markersize=7,
            mfc="white",
            mec="black",
            label=n,
        )
        for n in sorted({r["night"] for r in rows})
    ]

    ax.axhline(0, color="black", lw=1)
    ax.set_xticks(range(len(BANDS)))
    ax.set_xticklabels([BAND_LABELS[b] for b in BANDS])
    ax.set_xlim(-0.5, len(BANDS) - 0.5)
    ax.set_xlabel("Band")
    ax.set_ylabel("Residual (pipeline − Landolt) [mag]")
    ax.set_title(
        "Landolt Photometric Residual by Band",
        fontsize=13,
        fontweight="bold",
    )
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(
        handles=night_handles,
        title="Night",
        loc="lower right",
        fontsize=9,
        framealpha=0.9,
        ncol=2,
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


# ---------------------------------------------------------------------------
# Astrometric precision scatter plot
# ---------------------------------------------------------------------------


def plot_astrometry(rows, out_path: Path) -> None:
    """Per-band match-distance scatter with seeing FWHM annotation.

    One point per measurement (mas), marker shape encodes night. Seeing
    (median FWHM in arcsec) and N are annotated below each band's data
    cluster. A horizontal dotted line marks the Nickel pixel scale (370 mas)
    so the eye can compare the astrometric residual to the pixel size.
    """
    psf_table = load_psf_sigma_table()
    seeing = seeing_per_band(rows, psf_table)

    fig, ax = plt.subplots(figsize=(9.5, 6.5))

    # PM-corrected residuals. Prefer the rigorous per-measurement vector CSV
    # (Gaia DR3 → obs MJD propagation → re-match against single_visit_star),
    # falling back to a scalar approximation only if that CSV is missing.
    NICKEL_PIXEL_MAS = NICKEL_PIXEL_ARCSEC * 1000.0
    methodology_tag = "rigorous (Gaia DR3 PM + re-match)"
    if PM_CSV_PATH.exists():
        pm_csv = list(csv.DictReader(open(PM_CSV_PATH)))
        pm_rows = [{**r, "_pm_corrected_mas": float(r["residual_mas"])} for r in pm_csv]
    else:
        methodology_tag = "scalar PM-displacement approximation"
        pm_rows = []
        for r in rows:
            if r["star"] not in LANDOLT_PM:
                continue
            obs = float(r["match_dist_arcsec"]) * 1000.0
            if obs >= ASTROM_OUTLIER_CUT_MAS:
                continue
            pm = pm_displacement_mas(r["star"], r["night"])
            if not np.isfinite(pm):
                continue
            pm_rows.append({**r, "_pm_corrected_mas": obs - pm})

    all_resids = np.array([r["_pm_corrected_mas"] for r in pm_rows])
    # Tighten the axis so sub-pixel precision is the visual message. For the
    # rigorous |Δ| residuals the data are positive-only; for the legacy scalar
    # approximation they can be signed.
    is_unsigned = bool(np.all(all_resids >= 0))
    data_hi = float(np.max(all_resids))
    if is_unsigned:
        y_max = data_hi + 50
        y_min = -55
    else:
        data_lo = float(np.min(all_resids))
        span = max(abs(data_hi), abs(data_lo), 50)
        y_max = span + 70
        y_min = -span - 50
    ax.set_ylim(y_min, y_max)
    label_y = y_max - 6
    # Place seeing FWHM annotation just above the lower-right Night legend.
    seeing_y = -15

    for band in BANDS:
        brows = [r for r in pm_rows if r["band"] == band]
        if not brows:
            continue
        nights_here = sorted({r["night"] for r in brows})
        per_night = {n: [r for r in brows if r["night"] == n] for n in nights_here}
        sub_offsets = _jitter(len(nights_here), scale=0.32)
        for sub_offset, night in zip(sub_offsets, nights_here):
            nrows = per_night[night]
            xs = _band_xpos(band) + sub_offset + _jitter(len(nrows), scale=0.10)
            ys = np.array([r["_pm_corrected_mas"] for r in nrows])
            ax.scatter(
                xs,
                ys,
                marker=NIGHT_MARKERS.get(night, "o"),
                s=55,
                facecolor=BAND_COLORS[band],
                edgecolor="black",
                linewidth=0.5,
                alpha=0.85,
                zorder=2,
            )

        dists = np.array([r["_pm_corrected_mas"] for r in brows])
        abs_med = float(np.median(np.abs(dists)))
        sem = float(dists.std(ddof=1) / np.sqrt(len(dists))) if len(dists) > 1 else 0.0
        ax.text(
            _band_xpos(band),
            label_y,
            f"|med| = {abs_med:.0f} ± {sem:.0f} mas\nN = {len(dists)}",
            ha="center",
            va="top",
            fontsize=10,
            fontweight="bold",
        )

        # Per-band seeing under each column.
        fwhm, nfwhm = seeing.get(band, (float("nan"), 0))
        if np.isfinite(fwhm):
            ax.text(
                _band_xpos(band),
                seeing_y,
                f"seeing FWHM ≈ {fwhm:.2f}″   (N={nfwhm})",
                ha="center",
                va="center",
                fontsize=9,
                color="#333",
            )

    ax.axhline(0, color="black", lw=0.8)

    ax.set_xticks(range(len(BANDS)))
    ax.set_xticklabels([BAND_LABELS[b] for b in BANDS])
    ax.set_xlim(-0.5, len(BANDS) - 0.5)
    ax.set_xlabel("Band")
    ax.set_ylabel(
        "PM-corrected residual |Δ| (mas)"
        if "rigorous" in methodology_tag
        else "PM-corrected match residual (mas)"
    )
    ax.set_title(
        f"Landolt Astrometric Precision by Band  "
        f"({methodology_tag}, 1 pixel = {NICKEL_PIXEL_MAS:.0f} mas)",
        fontsize=12,
        fontweight="bold",
    )
    ax.grid(True, axis="y", alpha=0.3)
    night_handles = [
        plt.Line2D(
            [0],
            [0],
            marker=NIGHT_MARKERS[n],
            color="black",
            linestyle="",
            markersize=7,
            mfc="white",
            mec="black",
            label=n,
        )
        for n in sorted({r["night"] for r in rows})
    ]
    ax.legend(
        handles=night_handles,
        title="Night",
        loc="lower right",
        fontsize=9,
        framealpha=0.9,
        ncol=2,
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


# ---------------------------------------------------------------------------
# Color terms (unchanged)
# ---------------------------------------------------------------------------


def linfit(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float]:
    if len(xs) < 2:
        return float("nan"), float("nan"), float("nan")
    slope, intercept = np.polyfit(xs, ys, 1)
    rms = float(np.sqrt(np.mean((ys - (slope * xs + intercept)) ** 2)))
    return float(slope), float(intercept), rms


def plot_color_terms(rows, out_path: Path) -> None:
    # Two-tier y-scaling: B band gets its own (wider) axis because its
    # residuals run to ≈ -1 mag for the red-giant outliers; V/R/I share a
    # tighter common axis so their per-star scatter (~ ±0.05 mag) is
    # visible. The y-axis label and a small annotation note the split.
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    bv_range = np.linspace(-0.3, 1.85, 100)

    Y_LIM_B = (-1.05, 0.20)
    Y_LIM_VRI = (-0.25, 0.45)

    for idx, band in enumerate(BANDS):
        ax = axes[idx // 2][idx % 2]
        brows = [r for r in rows if r["band"] == band]
        bv = np.array([float(r["color_BV"]) for r in brows], float)
        resids = np.array([float(r["residual"]) for r in brows], float)

        ax.axhline(0, color="black", linestyle="--", alpha=0.5, lw=0.5)
        ax.scatter(
            bv,
            resids,
            color=BAND_COLORS[band],
            s=55,
            edgecolor="black",
            lw=0.5,
            alpha=0.85,
            zorder=3,
        )

        if len(bv) >= 2:
            slope, intercept, _ = linfit(bv, resids)
            ax.plot(
                bv_range,
                slope * bv_range + intercept,
                color=BAND_COLORS[band],
                lw=1.5,
                linestyle="--",
                alpha=0.7,
                label=f"slope = {slope:+.3f} mag/mag",
            )
            ax.legend(fontsize=10, loc="best")

        for r in brows:
            star_short = r["star"].split()[-1]
            ax.annotate(
                star_short,
                (float(r["color_BV"]), float(r["residual"])),
                fontsize=7,
                alpha=0.7,
                xytext=(5, 5),
                textcoords="offset points",
            )

        ax.set_ylabel("Residual (mag)")
        ax.set_title(f"{BAND_LABELS[band]} band", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(*(Y_LIM_B if band == "b" else Y_LIM_VRI))

    axes[1][0].set_xlabel("B−V (Landolt)")
    axes[1][1].set_xlabel("B−V (Landolt)")

    fig.suptitle(
        "Residual vs. B−V Color: Nickel-to-Landolt Color Terms",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main() -> None:
    rows = filter_outliers(load_rows())
    print(f"Loaded {len(rows)} measurements (after outlier filter)")
    plot_residuals(rows, OUT_DIR / "landolt_residuals.png")
    plot_astrometry(rows, OUT_DIR / "landolt_astrometry.png")
    plot_color_terms(rows, OUT_DIR / "landolt_color_terms.png")


if __name__ == "__main__":
    main()
