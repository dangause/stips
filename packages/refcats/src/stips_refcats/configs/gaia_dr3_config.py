# Name of the output reference catalog dataset
config.dataset_config.ref_dataset_name = "gaia_dr3"

# Use the Gaia-specific conversion logic
from lsst.meas.algorithms import convertRefcatManager

config.manager.retarget(convertRefcatManager.ConvertGaiaManager)

# Tune parallelism as needed
config.n_processes = 4

# Gaia DR3 column mappings
config.id_name = "source_id"
config.ra_name = "ra"
config.dec_name = "dec"
config.ra_err_name = "ra_error"
config.dec_err_name = "dec_error"

config.parallax_name = "parallax"
config.parallax_err_name = "parallax_error"
config.coord_err_unit = "milliarcsecond"

config.pm_ra_name = "pmra"
config.pm_ra_err_name = "pmra_error"
config.pm_dec_name = "pmdec"
config.pm_dec_err_name = "pmdec_error"

config.epoch_name = "ref_epoch"
config.epoch_format = "jyear"  # Same as used in Gaia DR2
config.epoch_scale = "tcb"

# Emit epoch + proper motion + parallax + position covariances so the astrometry
# loader can propagate positions to the visit epoch. Requires the *_corr
# covariance columns in the input CSV (see COLS_SQL in stips_refcats.gaia) and
# all coord/pm/parallax error columns set above.
config.full_position_information = True

# List of Gaia DR3 photometric magnitude columns
config.mag_column_list = ["phot_g_mean", "phot_bp_mean", "phot_rp_mean"]

# Optional extra columns to carry along
config.extra_col_names = []
# ruff: noqa: F821,E402
