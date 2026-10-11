"""CTIO 1.0m Y4KCam, 2x2 on-chip binned.

A binned readout is the same camera but a different pixel grid, and Butler
stores one camera geometry per instrument NAME — so binned data is its own
instrument. This profile is the unbinned CTIO1m profile with a new name and
``ccd_binning=2``; ``camera/`` and ``configs/`` are symlinks to the base dir.
Replace a symlink with a real directory if the binned data ever needs its own
geometry source or config overrides.

Curated defects (obs_ctio1m_data) are in UNBINNED pixels, so they are not
loaded here (``doDefect=False``); the crosstalk matrix is per-amplifier ratios
and carries over unchanged.
"""

from dataclasses import replace

from instruments.ctio1m.profile import profile as _base

profile = replace(
    _base,
    name="CTIO1m_bin2",
    policy_name="CTIO1m_bin2",
    collection_prefix="CTIO1m_bin2",
    ccd_binning=2,
    obs_data_package=None,
    isr_overrides={**_base.isr_overrides, "doDefect": False},
    # replace() copies the hooks dict by reference; copy it so a hook added
    # here can never mutate the base profile.
    hooks=dict(_base.hooks),
)
