#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute synthetic color terms for Nickel BVRI vs PS1 and Gaia DR3 and write obs_nickel/configs/colorterms.py

Dependencies: astroquery, numpy, scikit-learn
  pip install astroquery numpy scikit-learn
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from astroquery.svo_fps import SvoFps
from sklearn.linear_model import HuberRegressor

# ---------------------------
# CONFIG: output & mappings
# ---------------------------

# Where to write colorterms.py
OUTPUT_COLORTERMS = os.path.join(".", "configs", "colorterms.py")

# Reference-system color choices (primary minus secondary)
# PS1 I uses r-i here (more stable if z coverage is dicey)
SCHEME_PS1 = {
    "B": ("g", "r"),
    "V": ("g", "r"),
    "R": ("r", "i"),
    "I": ("i", "r"),  # change to ("i","z") if you prefer I vs (i−z)
}

SCHEME_GAIA = {
    "B": ("BP", "RP"),  # color BP−RP
    "V": ("G", "RP"),  # color G−RP (often more stable than G−BP)
    "R": ("RP", "BP"),  # color RP−BP
    "I": ("RP", "BP"),  # color RP−BP
}

# LSST refcat column bases (no _flux suffix)
PS1_COLBASE = dict(g="gMeanPSFMag", r="rMeanPSFMag", i="iMeanPSFMag", z="zMeanPSFMag")
GAIA_COLBASE = dict(G="phot_g_mean_mag", BP="phot_bp_mean_mag", RP="phot_rp_mean_mag")

# SED temperatures (K)
TEMP_GRID = [3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 8000, 9000]

# Minimum color leverage (5–95 percentile span) to accept a slope
MIN_COLOR_SPAN = 0.18  # mag

# ---------------------------
# SVO download
# ---------------------------


def get_band(idstr: str) -> Tuple[np.ndarray, np.ndarray]:
    """Fetch passband from SVO (wavelength in meters, transmission 0–1)."""
    tab = SvoFps.get_transmission_data(idstr)
    lam = np.array(tab["Wavelength"], float) * 1e-10  # Å -> m
    T = np.array(tab["Transmission"], float)
    # Clean & ensure monotonic lambda
    ok = np.isfinite(lam) & np.isfinite(T) & (T >= 0)
    lam, T = lam[ok], T[ok]
    o = np.argsort(lam)
    return lam[o], T[o]


# Nickel (SVO group = LICK)
NICKEL_IDS = dict(B="LICK/LICK.B", V="LICK/LICK.V", R="LICK/LICK.R", I="LICK/LICK.I")
# Pan-STARRS1 DR1/DR2 passbands (SVO has "PAN-STARRS/PS1.<band>")
PS1_IDS = dict(
    g="PAN-STARRS/PS1.g",
    r="PAN-STARRS/PS1.r",
    i="PAN-STARRS/PS1.i",
    z="PAN-STARRS/PS1.z",
)
# Gaia DR3
GAIA_IDS = dict(G="GAIA/GAIA3.G", BP="GAIA/GAIA3.Gbp", RP="GAIA/GAIA3.Grp")


def load_passbands() -> Dict[str, Dict[str, Tuple[np.ndarray, np.ndarray]]]:
    pb = dict(nickel={}, ps1={}, gaia={})
    for k, v in NICKEL_IDS.items():
        pb["nickel"][k] = get_band(v)
    for k, v in PS1_IDS.items():
        pb["ps1"][k] = get_band(v)
    for k, v in GAIA_IDS.items():
        pb["gaia"][k] = get_band(v)
    return pb


# ---------------------------
# Synthetic photometry
# ---------------------------


def planck_wlm(lam_m: np.ndarray, T: float) -> np.ndarray:
    """Planck function B_lambda (arbitrary normalization is fine for colors)."""
    h = 6.62607015e-34
    c = 2.99792458e8
    k = 1.380649e-23
    x = (h * c) / (lam_m * k * T)
    # Avoid overflow for tiny lam
    out = (2 * h * c**2) / (lam_m**5) / np.expm1(x)
    return out


def ab_mag_like(lam: np.ndarray, Tresp: np.ndarray, F_lam: np.ndarray) -> float:
    """AB-like mag up to additive constant; differences are what matter."""
    # photon-weighted integrals (lam factor); consistent choice across bands
    num = np.trapz(F_lam * Tresp * lam, lam)
    den = np.trapz(Tresp * lam, lam)
    if num <= 0 or den <= 0:
        return np.nan
    return -2.5 * np.log10(num / den)


@dataclass
class SED:
    name: str
    T: float


def synth_mag_on_grid(lam_band, T_band, Tsed) -> float:
    F = planck_wlm(lam_band, Tsed)
    return ab_mag_like(lam_band, T_band, F)


def make_sed_grid() -> List[SED]:
    return [SED(name=f"BB{T}", T=T) for T in TEMP_GRID]


def compute_mags_for_sed(sed: SED, pb) -> Dict[str, float]:
    """Return dict of mags for all bands used."""
    mags = {}
    # Nickel BVRI
    for k, (lam, Tresp) in pb["nickel"].items():
        mags[f"N_{k}"] = synth_mag_on_grid(lam, Tresp, sed.T)
    # PS1 griz
    for k, (lam, Tresp) in pb["ps1"].items():
        mags[f"P_{k}"] = synth_mag_on_grid(lam, Tresp, sed.T)
    # Gaia G/BP/RP
    for k, (lam, Tresp) in pb["gaia"].items():
        mags[f"G_{k}"] = synth_mag_on_grid(lam, Tresp, sed.T)
    return mags


# ---------------------------
# Fit c1 (slope) with Huber, no intercept (c0 handled by nightly ZP)
# ---------------------------


def fit_c1(y: np.ndarray, c: np.ndarray) -> Tuple[float, float]:
    X = c.reshape(-1, 1)
    mdl = HuberRegressor(fit_intercept=False).fit(X, y)
    pred = mdl.predict(X)
    rms = float(np.nanstd(y - pred))
    return float(mdl.coef_[0]), rms


def assemble_and_fit(
    rows: List[Dict[str, float]], target: str, prim: str, sec: str, label: str
) -> Dict[str, float]:
    """
    y = m(Nickel,target) - m(ref,primary)
    c = m(ref,primary)   - m(ref,secondary)
    """
    y = np.array([r[f"N_{target}"] - r[prim] for r in rows], float)
    c = np.array([r[prim] - r[sec] for r in rows], float)

    # leverage check
    lo, hi = np.nanpercentile(c, 5), np.nanpercentile(c, 95)
    span = hi - lo

    if not np.isfinite(span) or span < MIN_COLOR_SPAN:
        return dict(
            ok=False,
            reason=f"low_color_span({span:.3f})",
            span=float(span),
            c1=np.nan,
            rms=np.nan,
        )

    c1, rms = fit_c1(y, c)
    return dict(ok=True, c1=c1, rms=rms, span=span)


# ---------------------------
# Main
# ---------------------------


def main():
    print("Downloading passbands from SVO…")
    pb = load_passbands()
    print("Building SED grid…")
    seds = make_sed_grid()
    print(f"SEDs: {[s.name for s in seds]}")

    print("Computing synthetic mags…")
    rows = []
    for sed in seds:
        mags = compute_mags_for_sed(sed, pb)
        # rename keys for clarity: P_* and G_* stay, N_* are Nickel
        rows.append(mags)

    # PS1 fits
    print("\n=== PS1 color terms (Nickel vs PS1) ===")
    ps1_results = {}
    for band, (p, s) in SCHEME_PS1.items():
        prim = f"P_{p}"
        sec = f"P_{s}"
        res = assemble_and_fit(
            rows, target=band, prim=prim, sec=sec, label=f"PS1 {band}"
        )
        ps1_results[band] = res
        print(
            f"PS1 {band}: primary={p}, secondary={s}, span={res['span']:.3f}, c1={res['c1']:+.4f}, rms={res['rms']:.4f}, ok={res['ok']}"
        )

    # Gaia fits
    print("\n=== Gaia DR3 color terms (Nickel vs Gaia) ===")
    gaia_results = {}
    for band, (p, s) in SCHEME_GAIA.items():
        prim = f"G_{p}"
        sec = f"G_{s}"
        res = assemble_and_fit(
            rows, target=band, prim=prim, sec=sec, label=f"Gaia {band}"
        )
        gaia_results[band] = res
        print(
            f"GAIA {band}: primary={p}, secondary={s}, span={res['span']:.3f}, c1={res['c1']:+.4f}, rms={res['rms']:.4f}, ok={res['ok']}"
        )

    # Build colorterms.py contents (only include terms that passed leverage)
    def fmt(val):
        return f"{val:.6f}"

    ps1_block = []
    for band, res in ps1_results.items():
        if not res["ok"]:
            continue
        primary, secondary = SCHEME_PS1[band]
        colbase_p = PS1_COLBASE[primary]
        colbase_s = PS1_COLBASE[secondary]
        ps1_block.append(
            f'        "{band}": Colorterm(primary="{colbase_p}", secondary="{colbase_s}", c0=0.0, c1={fmt(res["c1"])}, c2=0.0),'
        )

    gaia_block = []
    for band, res in gaia_results.items():
        if not res["ok"]:
            continue
        primary, secondary = SCHEME_GAIA[band]
        colbase_p = GAIA_COLBASE[primary]
        colbase_s = GAIA_COLBASE[secondary]
        gaia_block.append(
            f'        "{band}": Colorterm(primary="{colbase_p}", secondary="{colbase_s}", c0=0.0, c1={fmt(res["c1"])}, c2=0.0),'
        )

    content = [
        "# Auto-generated by make_synthetic_colorterms.py",
        "from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict",
        "",
        "config.data = {",
    ]
    if ps1_block:
        content.append('    "panstarrs1*": ColortermDict(data={')
        content.extend(ps1_block)
        content.append("    }),")
    if gaia_block:
        content.append('    "gaia*": ColortermDict(data={')
        content.extend(gaia_block)
        content.append("    }),")
    content.append("}")
    text = "\n".join(content)

    os.makedirs(os.path.dirname(OUTPUT_COLORTERMS), exist_ok=True)
    with open(OUTPUT_COLORTERMS, "w") as f:
        f.write(text)
    print(f"\nWrote {OUTPUT_COLORTERMS}\n")
    print("Preview:\n" + "\n".join(text.splitlines()[:30]) + ("\n..."))


if __name__ == "__main__":
    main()
