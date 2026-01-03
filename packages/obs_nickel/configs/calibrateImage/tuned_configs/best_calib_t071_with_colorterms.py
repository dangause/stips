# Wrapper config that loads both the tuned config and colorterms
# Used by experimental/DRP_recal.yaml pipeline

import os

# Load the base tuned config
config_dir = os.path.dirname(__file__)
# `config` is injected by the pipeline runner.
config.load(os.path.join(config_dir, "best_calib_t071.py"))  # noqa: F821

# Load colorterms on top
config.load(os.path.join(config_dir, "..", "..", "apply_colorterms.py"))  # noqa: F821
