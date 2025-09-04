from __future__ import annotations
from pathlib import Path
from typing import Dict
from .io_utils import ensure_parent

def write_overrides(workdir: Path, tag: str, params: Dict[str, float]) -> Path:
    """Create a per-trial calibrateImage overrides file with *top-level* assignments.

    NOTE:
      - `pipetask -C calibrateImage:<file.py>` executes the file with `config` bound.
      - Do NOT wrap in functions; assign directly to `config.*`.
    """
    trial_dir = workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    ov_path = trial_dir / f"calib_overrides_{tag}.py"

    txt = f"""# Auto-generated overrides for {tag}
# IMPORTANT: This file is executed by pipetask with `config` in scope.

# --- PSF detection ---
config.psf_detection.thresholdValue = {params["psf_det.threshold"]:.6g}
config.psf_detection.includeThresholdMultiplier = {params["psf_det.incMult"]:.6g}

# --- PSF star selector: objectSize ---
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = {params["psfsel.snmin"]:.6g}
cfg.doFluxLimit = False
cfg.widthMin = 0.8
cfg.widthMax = 8.0
cfg.widthStdAllowed = {params["psfsel.widthStdMax"]:.6g}
cfg.nSigmaClip = 3.0
config.psf_measure_psf.reserve.fraction = 0.0

# --- Astrometry matcher (pessimisticB) ---
m = config.astrometry.matcher
m.maxOffsetPix = {int(params["match.maxOffsetPix"])}
m.maxRotationDeg = {params["match.maxRotationDeg"]:.6g}
m.matcherIterations = {int(params["match.matcherIterations"])}
m.minMatchDistPixels = {params["match.minMatchDistPixels"]:.6g}
m.minMatchedPairs = {int(params["match.minMatchedPairs"])}
m.minFracMatchedPairs = {params["match.minFracMatchedPairs"]:.6g}
m.numBrightStars = {int(params["match.numBrightStars"])}
m.maxRefObjects = {int(params["match.maxRefObjects"])}
m.numPatternConsensus = {int(params["match.numPatternConsensus"])}

# --- Astrometry source selector ---
ss = config.astrometry.sourceSelector["science"]
ss.doSignalToNoise = True
ss.signalToNoise.minimum = {params["astro_src.snmin"]:.6g}

# --- Aperture correction selector ---
c = config.measure_aperture_correction
c.sourceSelector.name = "science"
css = c.sourceSelector["science"]
css.doSignalToNoise = True
css.signalToNoise.minimum = {params["apcorr.snmin"]:.6g}
css.signalToNoise.maximum = None
c.numSigmaClip = {params["apcorr.sigclip"]:.6g}
c.numIter = {int(params["apcorr.niter"])}

# --- PSF Normalized Calibration Flux selector ---
ncf = config.psf_normalized_calibration_flux.measure_ap_corr
ncf.sourceSelector.name = "science"
nss = ncf.sourceSelector["science"]
nss.doSignalToNoise = True
nss.signalToNoise.minimum = {params["ncf.snmin"]:.6g}
nss.doUnresolved = False
nss.doIsolated = False
"""
    ensure_parent(ov_path)
    ov_path.write_text(txt)
    return ov_path
