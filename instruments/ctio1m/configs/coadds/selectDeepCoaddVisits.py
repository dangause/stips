# ruff: noqa: F821
# CTIO Y4KCam deep-coadd visit selection (overrides the Nickel-tuned default).
#
# BestSeeingSelectVisitsTask. Nickel default maxPsfFwhm=3.0 arcsec; Y4KCam at
# Cerro Tololo typically delivers better seeing but on a 1m the PSF FWHM in
# arcsec can still vary — keep a generous cap so good CTIO visits are not
# rejected, and accept all (nVisitsMax=-1). Retune at validation.
config.maxPsfFwhm = 4.0
config.nVisitsMax = -1
