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
        }
    ),
}
