# Tell MakeDiscreteSkyMap to use initial_pvi instead of calexp.
if hasattr(config, "inputDatasetTypes"):
    config.inputDatasetTypes = ["initial_pvi"]
elif hasattr(config, "inputDatasetType"):
    config.inputDatasetType = "initial_pvi"
else:
    raise RuntimeError("MakeDiscreteSkyMapConfig has no inputDatasetType(s) field")
