"""Color term definitions for CTIO 0.9m telescope.

Defines transformations between CTIO 0.9m Johnson-Cousins filters
and reference catalog photometric systems (Gaia DR3, PS1).

Color term format:
    inst_mag = ref_mag + c0 + c1*(primary - secondary) + c2*(primary - secondary)^2

For Gaia DR3 with only G-band available in our refcat:
    We use identity transformations (c0=c1=c2=0) since we can't compute
    color-dependent corrections without BP-RP colors.
"""

from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict

# Gaia DR3 color terms
# Since our refcat only has g_flux (G-band), we use identity transformations.
# A proper implementation would use BP-RP colors for color-dependent corrections.
config.data = {  # noqa: F821 - config is injected by LSST config loader
    "gaia*": ColortermDict(
        data={
            # Johnson-Cousins broadband - identity transforms (G-band only)
            "u": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "b": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "v": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "r": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "i": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "y": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            # Uppercase physical filters map to same
            "U": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "B": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "V": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "R": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "I": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "Y": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            # Combination filters
            "DIA+U": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "DIA+V": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "DIA+R": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "DIA+I": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "DIA+Y": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
            "B+DIA": Colorterm(
                primary="g_flux", secondary="g_flux", c0=0.0, c1=0.0, c2=0.0
            ),
        }
    ),
}
