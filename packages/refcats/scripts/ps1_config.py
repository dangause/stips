# Pan-STARRS1 DR2 reference catalog configuration for LSST ingest

from lsst.meas.algorithms import convertRefcatManager

# Output dataset name (used for Butler refcat collection name)
config.dataset_config.ref_dataset_name = "panstarrs1_dr2"

# Retarget to default conversion manager (no special flux conversion needed)
config.manager.retarget(convertRefcatManager.ConvertRefcatManager)

# Parallel processing
config.n_processes = 48

# RA/Dec columns (J2000, in degrees)
config.ra_name = "raMean"
config.dec_name = "decMean"

# RA/Dec uncertainty columns (in arcseconds, will be converted)
config.ra_err_name = "raMeanErr"
config.dec_err_name = "decMeanErr"
config.coord_err_unit = "arcsec"

# Unique object identifier
config.id_name = "objID"

# Astrometric epoch (converted from MJD)
config.epoch_name = "epochMean"
config.epoch_format = "mjd"
config.epoch_scale = "tcb"  # Technically unknown, but consistent use is fine

# Magnitude columns to ingest (PSF magnitudes)
config.mag_column_list = [
    "gMeanPSFMag",
    "rMeanPSFMag",
    "iMeanPSFMag",
    "zMeanPSFMag",
    "yMeanPSFMag",
]

# Associated magnitude error columns
config.mag_err_column_map = {
    "gMeanPSFMag": "gMeanPSFMagErr",
    "rMeanPSFMag": "rMeanPSFMagErr",
    "iMeanPSFMag": "iMeanPSFMagErr",
    "zMeanPSFMag": "zMeanPSFMagErr",
    "yMeanPSFMag": "yMeanPSFMagErr",
}

# Extra columns to retain in output (optional but useful)
config.extra_col_names = [
    "nDetections",
    "ng",
    "nr",
    "ni",
    "nz",
    "ny",
    "qualityFlag",
    "objInfoFlag",
]
# ruff: noqa: F821,E402
