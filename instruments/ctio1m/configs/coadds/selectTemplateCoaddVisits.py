# ruff: noqa: F821
# CTIO Y4KCam template-coadd visit selection (overrides the Nickel-tuned default).
#
# BestSeeingQuantileSelectVisitsTask. The framework default keeps the best 50%
# (qMax=0.5), tuned for Nickel's sparse visit counts. CTIO standard-field nights
# have even fewer visits, so dropping half can starve the template coadd. Keep
# all visits by seeing quantile but still require at least one. Retune once real
# per-night visit counts are known (validation task).
config.qMax = 0.99
config.nVisitsMin = 1
