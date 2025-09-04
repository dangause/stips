from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

# CSV schemas used across modules
FAIL_LOG_HEADERS = [
    "time", "trial_tag", "exception", "message", "returncode",
    "cmd", "stdout_log", "stderr_log",
]
RUNS_CSV_HEADERS = [
    # trial identity
    "time", "trial_index", "trial_tag", "status", "out_coll",
    # where we read metrics from
    "read_from_collection", "postproc_out",
    # visits accounting
    "n_total", "n_success", "n_fail", "success_rate",
    # metrics
    "psfSigma_med", "astromOffsetStd_med", "skyNoise_med", "magLim_med",
    "score_base", "score",
    # parameters (flattened)
    "psf_det.threshold", "psf_det.incMult",
    "psfsel.snmin", "psfsel.widthStdMax",
    "match.maxOffsetPix", "match.maxRotationDeg", "match.matcherIterations",
    "match.minMatchDistPixels", "match.minMatchedPairs", "match.minFracMatchedPairs",
    "match.numBrightStars", "match.maxRefObjects", "match.numPatternConsensus",
    "astro_src.snmin",
    "apcorr.snmin", "apcorr.sigclip", "apcorr.niter",
    "ncf.snmin",
    # artifact paths
    "overrides_path", "trial_dir",
]

@dataclass
class Context:
    """Immutable runtime configuration shared across modules."""
    repo: Path
    obs_nickel: Path
    proc_pipe: Path
    post_pipe: Path
    workdir: Path
    visits: List[int]            # resolved visit list to process
    bad: List[int]               # visits explicitly excluded
    jobs: int
    inputs_postisr: str          # e.g. "Nickel/run/processCcd/<timestamp>"
    calib_chain: str             # e.g. "Nickel/calib/current"
    refcats: str                 # usually "refcats"
    fail_policy: str             # "hard" | "frac" | "linear"
    fail_weight: float
    echo_logs: bool
    tail: int
    run_postproc: bool
