#!/usr/bin/env python
"""Compare Nickel/STIPS DIA lightcurves to reference photometry.

For SN 2020wnt, overlays per-band Nickel photometry from Tinyanont et al. 2023
(ApJ 951:34) — same telescope, independent reduction pipeline.

For SN 2023ixf, overlays ZTF (ALeRCE) detections as a temporary reference until
the published photometry catalog is wired in.

Writes a two-panel figure to analysis/sn_vs_ztf_comparison.png.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "analysis" / "sn_vs_ztf_comparison.png"
OUT_POSTER_2020WNT = REPO_ROOT / "analysis" / "sn2020wnt_poster.png"
OUT_POSTER_2023IXF = REPO_ROOT / "analysis" / "sn2023ixf_poster.png"

# Dedicated path for the 2023ixf poster panel — points at the aperture-flux
# relookup CSV (analysis/aperture_relookup_2023ixf.py), which sums asymptotic
# aperture flux at the SN coords on every PS1-template diff image instead of
# using STIPS' PSF-fit forced photometry. PSF-fitting on diff systematically
# under-reports the bright-source flux by ~0.4 mag (same failure mode as the
# HD 189733b PSF run, per CLAUDE.md). Aperture sums recover that flux.
NICKEL_PATH_2023IXF_POSTER = (
    Path(__file__).resolve().parents[2] / "analysis" / "lightcurve_2023ixf_aperture.csv"
)

NICKEL_PATHS = {
    # 2023ixf: PS1 template — Nickel coadd template contains active-SN epochs
    # (days 70–206 post-explosion), contaminating early-epoch differences.
    "SN 2023ixf": Path(
        "/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv"
    ),
    # 2020wnt: Nickel-coadd template — built from SN-free epochs, gives much
    # broader band coverage (b/v/r/i, ~84 detections) than the PS1 r/i version (~14).
    "SN 2020wnt": Path(
        "/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_nickel_template_022226_repo/lightcurves/lightcurve_2020wnt.csv"
    ),
}

# Published BVRI photometry from Tinyanont et al. 2023 (ApJ 951:34) for
# 2020wnt. Per-band ASCII tables with (days_since_r_peak, mag, mag_err) — note
# that column 1 is days FROM PEAK r-band brightness, not from explosion.
PUB_DIR = {
    "SN 2020wnt": Path(__file__).resolve().parents[2]
    / "analysis"
    / "2020wnt_photometry_20220916",
}
PUB_BANDS = ("V", "r", "i")  # show R, V, I only (per-poster); B intentionally omitted
PUB_COLOR = {"V": "#2ca02c", "r": "#d62728", "i": "#8c564b"}
PUB_LABEL = {"V": "V", "r": "R", "i": "I"}
EXPLOSION_MJD = {"SN 2023ixf": 60082.75, "SN 2020wnt": 59180.0}

# Days between our reference epoch (EXPLOSION_MJD, ≈ discovery for 2020wnt) and
# Tinyanont's day 0 (r-band peak). Determined empirically: this offset minimises
# the STIPS R − Tinyanont R residual (mean ≈ −0.04, RMS ≈ 0.07 mag at delta=33).
PUB_PEAK_OFFSET_DAYS = {"SN 2020wnt": 33.0}

# Published Nickel BVRI catalog for SN 2023ixf (user-supplied; same telescope,
# independent reduction). Single ASCII file with whitespace-separated columns:
#   OBS:  MJD  filter  flux  flux_err  mag(AB)  mag_err  ...  status
# Filters are B/V/r/i; rows tagged "Bad" in the final column are excluded.
PUB_CAT_2023IXF = (
    Path(__file__).resolve().parents[2] / "analysis" / "2023ixf_nickel_phot.cat"
)
# The catalog spans MJD ~60084-60539 (days 1.5-457 post-explosion). The
# paper's published analysis only used data up to MJD ~60092 (≈day 9), but
# overlapping STIPS R coverage begins at day 3.6 so capping at the paper
# window leaves zero R-band overlap. Default = use the full catalog; set to a
# finite value to restrict to the paper window.
PUB_MJD_MAX_2023IXF: float = float("inf")

NICKEL_COLOR = {"r": "#d62728", "i": "#8c564b", "v": "#2ca02c"}

# ZTF (ALeRCE) reference photometry. Only SNe listed here get the ZTF overlay;
# used while published per-target photometry is being assembled.
ZTF_OIDS = {"SN 2023ixf": "ZTF23aaklqou"}
ZTF_BAND = {1: "g", 2: "r"}
ZTF_COLOR = {"g": "#2ca02c", "r": "#d62728"}
CACHE_DIR = Path("/tmp/alerce_cache")
CACHE_DIR.mkdir(exist_ok=True)


def fetch_ztf(oid: str) -> list[dict]:
    cache = CACHE_DIR / f"{oid}.json"
    if not cache.exists():
        url = f"https://api.alerce.online/ztf/v1/objects/{oid}/lightcurve"
        subprocess.run(["curl", "-sL", url, "-o", str(cache)], check=True)
    return json.loads(cache.read_text())["detections"]


def load_nickel(path: Path) -> list[dict]:
    return list(csv.DictReader(open(path)))


def load_published_2023ixf(band: str) -> list[tuple[float, float, float]]:
    """Load published Nickel photometry for SN 2023ixf.

    Returns (days_since_explosion, mag_AB, mag_err) tuples filtered to:
      - status != "Bad" (final column)
      - MJD <= PUB_MJD_MAX_2023IXF (paper window)
    Band match is case-insensitive (.cat uses "B V r i").
    """
    if not PUB_CAT_2023IXF.exists():
        return []
    explosion = EXPLOSION_MJD["SN 2023ixf"]
    band_lc = band.lower()
    out = []
    for line in PUB_CAT_2023IXF.read_text().splitlines():
        parts = line.split()
        if len(parts) < 11 or parts[0] != "OBS:":
            continue
        if parts[-1].lower() == "bad":
            continue
        mjd = float(parts[1])
        if mjd > PUB_MJD_MAX_2023IXF:
            continue
        if parts[2].lower() != band_lc:
            continue
        out.append((mjd - explosion, float(parts[5]), float(parts[6])))
    return out


def load_published(sn: str, band: str) -> list[tuple[float, float, float]]:
    """Load published per-band photometry: (days_since_explosion, mag, mag_err).

    Applies PUB_PEAK_OFFSET_DAYS to convert Tinyanont's days-from-peak reference
    onto our days-since-explosion reference so the x-coordinate matches STIPS.
    """
    pub_dir = PUB_DIR.get(sn)
    if pub_dir is None:
        return []
    suffix = "2020wnt" if "2020wnt" in sn else sn.replace("SN ", "")
    path = pub_dir / f"{suffix}_{band}.dat"
    if not path.exists():
        return []
    offset = PUB_PEAK_OFFSET_DAYS.get(sn, 0.0)
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        out.append((float(parts[0]) + offset, float(parts[1]), float(parts[2])))
    return out


def plot_one(ax, sn: str) -> None:
    # --- Load + filter Nickel/STIPS detections. ---
    nickel_all = load_nickel(NICKEL_PATHS[sn])
    nickel_valid = [
        r
        for r in nickel_all
        if r.get("mag")
        and r["mag"].lower() != "nan"
        and r.get("mag_err")
        and r["mag_err"].lower() != "nan"
        and float(r["mag_err"]) < 0.5
    ]
    n_upper_limits = len(nickel_all) - len(nickel_valid)
    nickel_days_all = [float(r["days_since_explosion"]) for r in nickel_valid]

    # Window = Nickel's campaign duration; the visible legend counts match the
    # data inside the window.
    if nickel_days_all:
        win_lo, win_hi = min(nickel_days_all), max(nickel_days_all)
    else:
        win_lo, win_hi = float("-inf"), float("inf")

    def in_window(t: float) -> bool:
        return win_lo <= t <= win_hi

    # --- Published Nickel photometry from Tinyanont+23 (2020wnt only) ---
    # Plotted as the bottom visual layer; small filled triangles so they read
    # as a reference trace beneath the Nickel/STIPS markers.
    if sn in PUB_DIR:
        for band in PUB_BANDS:
            pts = [(d, m, e) for (d, m, e) in load_published(sn, band) if in_window(d)]
            if not pts:
                continue
            x = np.array([p[0] for p in pts])
            y = np.array([p[1] for p in pts])
            e = np.array([p[2] for p in pts])
            ax.errorbar(
                x,
                y,
                yerr=e,
                fmt="^",
                markersize=4,
                color=PUB_COLOR[band],
                mec="black",
                mew=0.3,
                lw=0,
                elinewidth=0.5,
                ecolor=PUB_COLOR[band],
                alpha=0.55,
                zorder=1,
                label=f"Tinyanont+23 {PUB_LABEL[band]} (N={len(pts)})",
            )

    # --- Nickel/STIPS points (top visual layer) ---
    nickel_in = [r for r in nickel_valid if in_window(float(r["days_since_explosion"]))]
    bands_seen = sorted({r["band"] for r in nickel_in})
    for band in bands_seen:
        pts = [r for r in nickel_in if r["band"] == band]
        x = np.array([float(r["days_since_explosion"]) for r in pts])
        y = np.array([float(r["mag"]) for r in pts])
        e = np.array([float(r["mag_err"]) for r in pts])
        ax.errorbar(
            x,
            y,
            yerr=e,
            fmt="s",
            markersize=7,
            color=NICKEL_COLOR.get(band, "black"),
            mec="black",
            mew=0.6,
            lw=0,
            elinewidth=0.8,
            ecolor=NICKEL_COLOR.get(band, "black"),
            alpha=0.95,
            zorder=2,
            label=f"STIPS {band.upper()} (N={len(pts)})",
        )

    nickel_valid = nickel_in

    # --- ZTF (ALeRCE) overlay, used as a stand-in reference for SNe that
    # don't yet have published photometry wired in. Plotted on top of STIPS so
    # open circles are visible against same-color filled squares. ---
    if sn in ZTF_OIDS:
        explosion = EXPLOSION_MJD[sn]
        ztf_all = [
            d
            for d in fetch_ztf(ZTF_OIDS[sn])
            if d.get("rb") and d["rb"] > 0.5 and d.get("magpsf")
        ]
        for fid in (1, 2):
            band = ZTF_BAND[fid]
            pts = [
                d
                for d in ztf_all
                if d["fid"] == fid and in_window(d["mjd"] - explosion)
            ]
            if not pts:
                continue
            x = np.array([d["mjd"] - explosion for d in pts])
            y = np.array([d["magpsf"] for d in pts])
            e = np.array([d.get("sigmapsf") or 0 for d in pts])
            ax.errorbar(
                x,
                y,
                yerr=e,
                fmt="o",
                markersize=6,
                mfc="white",
                mew=1.2,
                color=ZTF_COLOR[band],
                lw=0,
                elinewidth=0.7,
                ecolor=ZTF_COLOR[band],
                alpha=0.95,
                zorder=3,
                label=f"ZTF {band} (N={len(pts)})",
            )

    # --- STIPS R vs Tinyanont+23 R agreement (≤3 d, both errors < 0.1 mag) ---
    nickel_r = [
        r for r in nickel_valid if r["band"] == "r" and float(r["mag_err"]) < 0.1
    ]
    pub_r = [p for p in load_published(sn, "r") if p[2] < 0.1]
    residuals = []
    for nr in nickel_r:
        nt = float(nr["days_since_explosion"])
        nm = float(nr["mag"])
        best = min(pub_r, key=lambda p: abs(p[0] - nt), default=None)
        if best is None or abs(best[0] - nt) > 3.0:
            continue
        residuals.append(nm - best[1])
    if residuals:
        arr = np.array(residuals)
        ax.text(
            0.98,
            0.97,
            f"STIPS R − Tinyanont+23 R (≤3 d):\n"
            f"N={len(arr)},  mean={arr.mean():+.3f},  RMS={float(np.sqrt((arr**2).mean())):.3f} mag",
            transform=ax.transAxes,
            fontsize=11,
            ha="right",
            va="top",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="black", alpha=0.9),
        )

    if n_upper_limits:
        ax.text(
            0.02,
            0.03,
            f"+{n_upper_limits} Nickel non-detections not shown",
            transform=ax.transAxes,
            fontsize=10,
            ha="left",
            va="bottom",
            color="gray",
            style="italic",
        )

    # Apply the overlap-window xlim computed at the top of this function.
    if win_hi > win_lo and win_hi != float("inf"):
        pad = 0.04 * (win_hi - win_lo)
        ax.set_xlim(win_lo - pad, win_hi + pad)

    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion", fontsize=12)
    ax.set_ylabel("AB magnitude", fontsize=12)
    ax.set_title(f"{sn}", fontsize=14, fontweight="bold")
    ax.tick_params(labelsize=11)
    ax.grid(True, alpha=0.3)
    # Place legend outside the right edge of the axes so it never overlaps data.
    ax.legend(
        fontsize=11,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        framealpha=0.95,
        ncol=1,
        borderaxespad=0,
    )


def plot_2020wnt_poster(out_path: Path) -> None:
    """Standalone SN 2020wnt panel sized for a poster.

    Single panel, large fonts and markers, minimum text. Shows Nickel/STIPS
    R/V/I detections (filled squares) overlaid on Tinyanont+23 R/V/I
    (filled triangles). The STIPS-vs-Tinyanont R-band residual box gives
    the headline cross-validation number.
    """
    sn = "SN 2020wnt"

    nickel_all = load_nickel(NICKEL_PATHS[sn])
    nickel_valid = [
        r
        for r in nickel_all
        if r.get("mag")
        and r["mag"].lower() != "nan"
        and r.get("mag_err")
        and r["mag_err"].lower() != "nan"
        and float(r["mag_err"]) < 0.5
    ]
    nickel_days_all = [float(r["days_since_explosion"]) for r in nickel_valid]
    win_lo, win_hi = (
        (min(nickel_days_all), max(nickel_days_all))
        if nickel_days_all
        else (float("-inf"), float("inf"))
    )

    def in_window(t: float) -> bool:
        return win_lo <= t <= win_hi

    fig, ax = plt.subplots(figsize=(16, 10))

    # Published Tinyanont+23 trace (background layer)
    for band in PUB_BANDS:
        pts = [(d, m, e) for (d, m, e) in load_published(sn, band) if in_window(d)]
        if not pts:
            continue
        x = np.array([p[0] for p in pts])
        y = np.array([p[1] for p in pts])
        e = np.array([p[2] for p in pts])
        ax.errorbar(
            x,
            y,
            yerr=e,
            fmt="^",
            markersize=10,
            color=PUB_COLOR[band],
            mec="black",
            mew=0.5,
            lw=0,
            elinewidth=1.0,
            ecolor=PUB_COLOR[band],
            alpha=0.55,
            zorder=1,
            label=f"Tinyanont+23 {PUB_LABEL[band]}",
        )

    # STIPS detections (foreground)
    nickel_in = [r for r in nickel_valid if in_window(float(r["days_since_explosion"]))]
    for band in sorted({r["band"] for r in nickel_in}):
        pts = [r for r in nickel_in if r["band"] == band]
        x = np.array([float(r["days_since_explosion"]) for r in pts])
        y = np.array([float(r["mag"]) for r in pts])
        e = np.array([float(r["mag_err"]) for r in pts])
        ax.errorbar(
            x,
            y,
            yerr=e,
            fmt="s",
            markersize=14,
            color=NICKEL_COLOR.get(band, "black"),
            mec="black",
            mew=0.9,
            lw=0,
            elinewidth=1.3,
            ecolor=NICKEL_COLOR.get(band, "black"),
            alpha=0.95,
            zorder=2,
            label=f"STIPS {band.upper()}",
        )

    if win_hi > win_lo and win_hi != float("inf"):
        pad = 0.04 * (win_hi - win_lo)
        ax.set_xlim(win_lo - pad, win_hi + pad)

    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion", fontsize=30)
    ax.set_ylabel("AB magnitude", fontsize=30)
    ax.set_title("SN 2020wnt", fontsize=38, fontweight="bold")
    ax.tick_params(labelsize=24)
    ax.grid(True, alpha=0.3)

    # Legend pinned to lower-left (data sparse in that corner: faintest mags
    # at the earliest days are empty space in the inverted-mag panel).
    ax.legend(
        fontsize=22,
        loc="lower left",
        framealpha=0.95,
        ncol=2,
        handletextpad=0.5,
        columnspacing=1.2,
        borderpad=0.8,
    )

    # R-band residual stats are quoted in the poster body text (copy.md
    # Panel 4) rather than overlaid on the figure, to keep the plot clean.
    # The residual is still printed to stdout for record-keeping.
    nickel_r = [r for r in nickel_in if r["band"] == "r" and float(r["mag_err"]) < 0.1]
    pub_r = [p for p in load_published(sn, "r") if p[2] < 0.1]
    residuals = []
    for nr in nickel_r:
        nt = float(nr["days_since_explosion"])
        best = min(pub_r, key=lambda p: abs(p[0] - nt), default=None)
        if best is None or abs(best[0] - nt) > 3.0:
            continue
        residuals.append(float(nr["mag"]) - best[1])
    if residuals:
        arr = np.array(residuals)
        print(
            f"  [SN 2020wnt R-band residual  STIPS − Tinyanont+23]  "
            f"N={len(arr)}  mean={arr.mean():+.3f}  RMS={float(np.sqrt((arr**2).mean())):.3f} mag"
        )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def plot_2023ixf_poster(out_path: Path) -> None:
    """Standalone SN 2023ixf panel sized for a poster.

    Pulls Nickel/STIPS detections from the nickel-template repo (cleaner R/I
    coverage than the PS1 repo) and overlays the user-supplied published
    Nickel BVRI catalog (R/V/I shown; B intentionally omitted) capped at
    MJD ~60092 (paper window). Mirrors plot_2020wnt_poster: STIPS as filled
    circles, published as triangles, R-band residual stats box above legend.
    """
    nickel_all = load_nickel(NICKEL_PATH_2023IXF_POSTER)
    nickel_valid = [
        r
        for r in nickel_all
        if r.get("mag")
        and r["mag"].lower() != "nan"
        and r.get("mag_err")
        and r["mag_err"].lower() != "nan"
        and float(r["mag_err"]) < 0.5
    ]
    nickel_days_all = [float(r["days_since_explosion"]) for r in nickel_valid]
    win_lo, win_hi = (
        (min(nickel_days_all), max(nickel_days_all))
        if nickel_days_all
        else (float("-inf"), float("inf"))
    )

    def in_window(t: float) -> bool:
        return win_lo <= t <= win_hi

    fig, ax = plt.subplots(figsize=(16, 10))

    # Published Nickel BVRI (background layer, triangles).
    for band in PUB_BANDS:  # ("V", "r", "i")
        pts = [(d, m, e) for (d, m, e) in load_published_2023ixf(band) if in_window(d)]
        if not pts:
            continue
        x = np.array([p[0] for p in pts])
        y = np.array([p[1] for p in pts])
        e = np.array([p[2] for p in pts])
        ax.errorbar(
            x,
            y,
            yerr=e,
            fmt="^",
            markersize=10,
            color=PUB_COLOR[band],
            mec="black",
            mew=0.5,
            lw=0,
            elinewidth=1.0,
            ecolor=PUB_COLOR[band],
            alpha=0.55,
            zorder=1,
            label=f"Published {PUB_LABEL[band]}",
        )

    # STIPS detections (foreground, filled circles).
    nickel_in = [r for r in nickel_valid if in_window(float(r["days_since_explosion"]))]
    for band in sorted({r["band"] for r in nickel_in}):
        pts = [r for r in nickel_in if r["band"] == band]
        x = np.array([float(r["days_since_explosion"]) for r in pts])
        y = np.array([float(r["mag"]) for r in pts])
        e = np.array([float(r["mag_err"]) for r in pts])
        ax.errorbar(
            x,
            y,
            yerr=e,
            fmt="o",
            markersize=14,
            color=NICKEL_COLOR.get(band, "black"),
            mec="black",
            mew=0.9,
            lw=0,
            elinewidth=1.3,
            ecolor=NICKEL_COLOR.get(band, "black"),
            alpha=0.95,
            zorder=2,
            label=f"STIPS {band.upper()}",
        )

    if win_hi > win_lo and win_hi != float("inf"):
        pad = 0.04 * (win_hi - win_lo)
        ax.set_xlim(win_lo - pad, win_hi + pad)

    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion", fontsize=30)
    ax.set_ylabel("AB magnitude", fontsize=30)
    ax.set_title("SN 2023ixf", fontsize=38, fontweight="bold")
    ax.tick_params(labelsize=24)
    ax.grid(True, alpha=0.3)

    # Single-column legend: STIPS bands first, Published reference at bottom.
    handles, labels = ax.get_legend_handles_labels()
    paired = list(zip(handles, labels))
    stips = [(h, lbl) for h, lbl in paired if lbl.startswith("STIPS")]
    pub = [(h, lbl) for h, lbl in paired if lbl.startswith("Published")]
    ordered = stips + pub
    legend = ax.legend(
        [h for h, _ in ordered],
        [lbl for _, lbl in ordered],
        fontsize=22,
        loc="lower left",
        framealpha=0.95,
        ncol=1,
        handletextpad=0.5,
        borderpad=0.8,
    )

    # STIPS R vs published r residual (≤3 d match, both errors < 0.1 mag).
    nickel_r = [r for r in nickel_in if r["band"] == "r" and float(r["mag_err"]) < 0.1]
    pub_r = [p for p in load_published_2023ixf("r") if p[2] < 0.1]
    residuals = []
    for nr in nickel_r:
        nt = float(nr["days_since_explosion"])
        best = min(pub_r, key=lambda p: abs(p[0] - nt), default=None)
        if best is None or abs(best[0] - nt) > 3.0:
            continue
        residuals.append(float(nr["mag"]) - best[1])
    if residuals:
        arr = np.array(residuals)
        fig.canvas.draw()
        leg_bbox = legend.get_window_extent().transformed(ax.transAxes.inverted())
        text = (
            "R-band residual  ·  STIPS − Published\n"
            f"N = {len(arr)}    mean = {arr.mean():+.3f} mag    "
            f"RMS = {float(np.sqrt((arr**2).mean())):.3f} mag"
        )
        ax.text(
            leg_bbox.x0,
            leg_bbox.y1 + 0.02,
            text,
            transform=ax.transAxes,
            fontsize=22,
            ha="left",
            va="bottom",
            fontweight="bold",
            bbox=dict(
                boxstyle="round,pad=0.5",
                fc="white",
                ec="black",
                linewidth=1.5,
                alpha=0.95,
            ),
        )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main() -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 11))
    plot_one(axes[0], "SN 2023ixf")
    plot_one(axes[1], "SN 2020wnt")
    fig.suptitle(
        "Nickel/STIPS lightcurves vs reference photometry\n"
        "squares = STIPS,  triangles = Tinyanont+23 (2020wnt),  circles = ZTF (2023ixf)",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PATH}")
    plot_2020wnt_poster(OUT_POSTER_2020WNT)
    plot_2023ixf_poster(OUT_POSTER_2023IXF)


if __name__ == "__main__":
    main()
