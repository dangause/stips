# ruff: noqa: F821
# Colour terms for the CTIO 1.0m / Y4KCam, from the literature (not a STIPS fit).
#
# Y4KCam's BVRI set is a standard Kitt Peak BVRcIc (Kron-Cousins) set
# (https://www.astronomy.ohio-state.edu/Y4KCam/filters.html). Clem & Landolt
# 2013, AJ 146, 88, calibrated it against Landolt standards on 139 photometric
# nights (Feb 2006 - mid 2012, bracketing the STIPS data) and found terms to
# the standard system of B +0.174, V -0.019, R -0.012, I -0.020 mag/mag: V, R
# and I realise the Cousins system to within 0.02 mag/mag, which is neglected
# here. The transformations below therefore take the PS1 DR2 reference
# photometry (AB) to Johnson-Cousins (Vega) with the PS1 -> BVRcIc relations of
# Tonry et al. 2012, ApJ 750, 99, Table 6 (x = g_P1 - r_P1):
#
#   B  - g = 0.212 + 0.556 x + 0.034 x^2   (scatter 0.032)
#   V  - g = 0.005 - 0.536 x + 0.011 x^2   (0.012)
#   Rc - r = -0.137 - 0.108 x - 0.029 x^2  (0.015)
#   Ic - i = -0.366 - 0.136 x - 0.018 x^2  (0.017)
#
# LSST Colorterm form: m = primary + c0 + c1 (primary - secondary)
#                        + c2 (primary - secondary)^2.
# Keys are PHYSICAL filter names (profile ``filters``: "R" -> band r, ...).
# Only R and I are reachable in ``refcat.mode: gaia_ps1`` today: the profile's
# ``ps1_band_map`` maps r/i to PS1 r/i and nothing else, so B and V are kept
# for completeness and take effect only once b/v are mapped to PS1 g.
# Bands calibrated through this block are on the Vega system; the profile's
# ``vega_bands`` says so for the lightcurve and Landolt tools.
from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict

config.data = {
    "ps1*": ColortermDict(
        data={
            # colour (g - r) = x: coefficients verbatim.
            "B": Colorterm(
                primary="gMeanPSFMag",
                secondary="rMeanPSFMag",
                c0=0.212,
                c1=0.556,
                c2=0.034,
            ),
            "V": Colorterm(
                primary="gMeanPSFMag",
                secondary="rMeanPSFMag",
                c0=0.005,
                c1=-0.536,
                c2=0.011,
            ),
            # colour (r - g) = -x: the odd-power coefficient flips sign.
            "R": Colorterm(
                primary="rMeanPSFMag",
                secondary="gMeanPSFMag",
                c0=-0.137,
                c1=0.108,
                c2=-0.029,
            ),
            # Tonry's I relation is in g - r, which a Colorterm with primary i
            # cannot express. On the stellar locus x ~ 1.7 (r - i), so the
            # linear term becomes -0.136 * 1.7 * (r - i) = +0.23 (i - r); the
            # quadratic term is dropped. Measured on SN 2009Y field stars:
            # I slope -0.25 +/- 0.06 on (r - i), consistent.
            "I": Colorterm(
                primary="iMeanPSFMag",
                secondary="rMeanPSFMag",
                c0=-0.366,
                c1=0.23,
                c2=0.0,
            ),
            # SOAR Bessell I (October 2009 only): no standards were observed
            # through it, so it takes the I terms. Stated as an assumption in
            # the paper for the three 2009 WASP-18 nights.
            "I_SOAR": Colorterm(
                primary="iMeanPSFMag",
                secondary="rMeanPSFMag",
                c0=-0.366,
                c1=0.23,
                c2=0.0,
            ),
        }
    ),
    # Gaia DR3 -> Y4KCam BVRI, a STIPS fit (unlike the PS1 block above): fit
    # 2026-11-03 by scripts/analysis/fit_gaia_colorterms_landolt.py against
    # Landolt standards in scripts/config/landolt_validation/
    # landolt_catalog_ctio.csv (90 southern/equatorial stars) and
    # landolt_catalog.csv (11 northern stars), matched 1:1 to Gaia DR3
    # gaia_source within 3 arcsec (101 of 101 stars matched), least squares
    # with 3-sigma clipping per band. B: rms 0.104 mag on 99/101 stars kept;
    # V: rms 0.030 mag on 75/101; R: rms 0.028 mag on 80/101; I: rms 0.011 mag
    # on 82/101. V/R/I clip out a sizeable minority: most of what gets
    # dropped are the LSE/WD white-dwarf and hot-subdwarf standards in the
    # catalogue (e.g. WD 0830-535, LSE 259*, SA 98-6xx), whose Gaia G/BP/RP
    # colours do not sit on the same linear locus as the normal G-K-type
    # Landolt stars the fit is otherwise tight on; a few genuinely noisy
    # entries (e.g. [L92b] SA 98 L5 at V_err=0.16) are clipped in every band
    # too. B's rms is worse than V/R/I because Gaia BP is a very wide,
    # non-standard bandpass against Johnson B; this is the well-known
    # behaviour of the Gaia-to-Johnson transformation, not a clipping
    # failure. The LSST Colorterm reads "<primary>_flux", and the Gaia
    # refcat converted by stips_refcats has phot_g_mean_flux,
    # phot_bp_mean_flux, phot_rp_mean_flux, hence these primary/secondary
    # names. c0 is absorbed by the per-visit zero point but is kept anyway so
    # validate-landolt residuals centre on zero.
    "gaia*": ColortermDict(
        data={
            "B": Colorterm(
                primary="phot_bp_mean",
                secondary="phot_rp_mean",
                c0=-0.0016,
                c1=0.6532,
                c2=0.0,
            ),
            "V": Colorterm(
                primary="phot_g_mean",
                secondary="phot_rp_mean",
                c0=-0.2186,
                c1=0.8007,
                c2=0.0,
            ),
            "R": Colorterm(
                primary="phot_rp_mean",
                secondary="phot_g_mean",
                c0=-0.0510,
                c1=-0.7236,
                c2=0.0,
            ),
            "I": Colorterm(
                primary="phot_rp_mean",
                secondary="phot_g_mean",
                c0=0.0103,
                c1=0.1387,
                c2=0.0,
            ),
            # No standards were observed through the SOAR Bessell I filter
            # (October 2009 only), so it takes the Y4KCam I terms, as in the
            # ps1* block above.
            "I_SOAR": Colorterm(
                primary="phot_rp_mean",
                secondary="phot_g_mean",
                c0=0.0103,
                c1=0.1387,
                c2=0.0,
            ),
        }
    ),
}
