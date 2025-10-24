# LSST Science Pipelines Configuration Reference: ISR and CalibrateImage Parameters

This comprehensive reference catalogs all tunable configuration parameters for the LSST Science Pipelines Instrument Signature Removal (ISR) and calibrateImage pipeline tasks, optimized for building parameter grids for telescope data processing optimization.

**Primary Documentation:** https://pipelines.lsst.io
**GitHub Repository:** https://github.com/lsst/pipe_tasks

## Table of Contents

1. [Configuration System Overview](#1-configuration-system-overview)
2. [ISR Task Parameters](#2-isr-instrument-signature-removal-task-parameters)
3. [Detection Parameters](#3-detection-parameters)
4. [PSF Measurement Parameters](#4-psf-measurement-parameters)
5. [Astrometry Parameters](#5-astrometry-parameters)
6. [Photometry Parameters](#6-photometry-parameters)
7. [Measurement Algorithms](#7-measurement-algorithms)
8. [Other CalibrateImage Components](#8-other-calibrateimage-components)
9. [Parameter Grid Examples](#9-parameter-grid-examples)

---

## 1. Configuration System Overview

### Understanding the Configuration Hierarchy

The LSST configuration system follows a **Task → Config → ConfigField** hierarchy where each processing task has an associated Config class containing Field attributes that define individual parameters.

**Configuration Access Patterns:**
- **Simple fields:** `config.parameter = value`
- **Nested subtasks:** `config.subtask.parameter = value`
- **Registry fields:** `config.selector.name = 'variant'` or `config.selector['variant'].parameter = value`

**Registry Pattern Explained:** The bracket notation `config.selector["name"]` accesses configuration for a specific registered implementation variant. The `.active` attribute refers to the currently selected variant. This allows configuring multiple implementations before selecting which to use.

**Command-Line Configuration:**
```bash
# Simple values
pipetask run -p pipeline.yaml --config taskLabel:parameter=value

# Nested parameters
pipetask run --config calibrate.astrometry.matcher.maxOffsetPix=500

# Configuration files (for complex changes)
pipetask run --config-file myconfig.py
```

**Key Documentation Links:**
- Configuration System: https://pipelines.lsst.io/modules/lsst.pex.config/
- Task Framework: https://pipelines.lsst.io/modules/lsst.pipe.base/
- Configuring Tasks: https://pipelines.lsst.io/modules/lsst.ctrl.mpexec/configuring-pipetask-tasks.html

---

## 2. ISR (Instrument Signature Removal) Task Parameters

**Task:** `lsst.ip.isr.IsrTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.ip.isr/index.html
**API Reference:** https://pipelines.lsst.io/v/daily/py-api/lsst.ip.isr.IsrTask.html

ISR removes instrumental signatures from raw CCD images through a series of calibration corrections applied in a specific order.

### 2.1 Core Processing Control

#### config.doOverscan
- **Type:** bool
- **Default:** True
- **Description:** Enable overscan subtraction to remove bias pedestal from amplifier readout regions
- **Valid Values:** True, False
- **Impact:** Fundamental correction; typically always enabled unless overscan regions are unreliable

#### config.doBias
- **Type:** bool
- **Default:** True
- **Description:** Apply master bias frame correction to remove systematic electronic offset
- **Valid Values:** True, False
- **Impact:** Essential for most processing; disable only for bias frame construction

#### config.doDark
- **Type:** bool
- **Default:** True
- **Description:** Apply master dark frame correction to remove thermal signal accumulation
- **Valid Values:** True, False
- **Impact:** Critical for long exposures or warm detectors

#### config.doFlat
- **Type:** bool
- **Default:** True
- **Description:** Apply flat field correction to normalize pixel-to-pixel response variations
- **Valid Values:** True, False
- **Impact:** Essential for photometric accuracy

#### config.doLinearize
- **Type:** bool
- **Default:** True
- **Description:** Correct for detector non-linearity (deviation from linear response to photon flux)
- **Valid Values:** True, False
- **Impact:** Important for high-accuracy photometry, especially near saturation

#### config.doFringe
- **Type:** bool
- **Default:** True
- **Description:** Apply fringe correction (removes interference patterns common in red/infrared filters)
- **Valid Values:** True, False
- **Impact:** Essential for red filters (i, z, y bands); minimal effect for blue filters

### 2.2 Advanced Corrections

#### config.doCrosstalk
- **Type:** bool
- **Default:** False
- **Description:** Apply intra-CCD crosstalk correction (removes ghost signals between amplifiers)
- **Valid Values:** True, False
- **Impact:** Improves photometry near bright sources; requires camera-specific crosstalk matrix

#### config.doBrighterFatter
- **Type:** bool
- **Default:** False
- **Description:** Apply brighter-fatter correction (corrects charge redistribution in deep potential wells)
- **Valid Values:** True, False
- **Impact:** Critical for high-precision photometry and astrometry of bright sources

**Related Parameters:**

**config.brighterFatterLevel**
- **Type:** str (ChoiceField)
- **Default:** 'DETECTOR'
- **Valid Values:** 'AMP' (per-amplifier), 'DETECTOR' (per-detector)
- **Description:** Spatial scale at which to apply brighter-fatter correction

**config.brighterFatterMaxIter**
- **Type:** int
- **Default:** 10
- **Valid Range:** [1, inf)
- **Description:** Maximum iterations for brighter-fatter correction convergence

**config.brighterFatterThreshold**
- **Type:** float
- **Default:** 1000.0
- **Valid Range:** [0, inf)
- **Description:** Convergence threshold (absolute difference sum over all pixels)

#### config.doDeferredCharge
- **Type:** bool
- **Default:** False
- **Description:** Apply deferred charge (CTI) correction for charge transfer inefficiency
- **Valid Values:** True, False
- **Impact:** Important for CCDs with significant charge traps

### 2.3 Masking and Interpolation

#### config.doSaturation
- **Type:** bool
- **Default:** True
- **Description:** Mask saturated pixels (sets mask bits; independent of interpolation)
- **Valid Values:** True, False

**config.saturatedMaskName**
- **Type:** str
- **Default:** 'SAT'
- **Description:** Name of mask plane for saturated pixels

**config.growSaturationFootprintSize**
- **Type:** int
- **Default:** 1
- **Valid Range:** [0, inf)
- **Description:** Number of pixels to grow saturation footprints (accounts for charge bleeding)

#### config.doDefect
- **Type:** bool
- **Default:** True
- **Description:** Mask known CCD defects (hot pixels, bad columns, etc.)
- **Valid Values:** True, False

#### config.doInterpolate
- **Type:** bool
- **Default:** True
- **Description:** Interpolate over masked pixels using surrounding good pixels
- **Valid Values:** True, False

**config.maskListToInterpolate**
- **Type:** List of str
- **Default:** ['SAT', 'BAD']
- **Description:** Mask planes that should be interpolated over
- **Common Values:** 'SAT', 'BAD', 'CR', 'INTRP', 'UNMASKEDNAN'

### 2.4 Variance and Quality Assessment

#### config.doVariance
- **Type:** bool
- **Default:** True
- **Description:** Calculate variance plane (propagates noise through processing)
- **Valid Values:** True, False
- **Impact:** Required for weighted fitting and error propagation

**config.gain**
- **Type:** float
- **Default:** nan (use detector model value)
- **Description:** Detector gain (e-/ADU) if not available from detector model
- **Valid Range:** [0, inf) or nan

**config.readNoise**
- **Type:** float
- **Default:** 0.0
- **Description:** Read noise (electrons) if not available from detector model
- **Valid Range:** [0, inf)

#### config.doStandardStatistics
- **Type:** bool
- **Default:** True
- **Description:** Calculate standard image quality statistics (mean, median, RMS)
- **Valid Values:** True, False

### 2.5 Flat Field Configuration

**config.flatScalingType**
- **Type:** str (ChoiceField)
- **Default:** 'USER'
- **Valid Values:**
  - 'USER': Scale by flatUserScale parameter
  - 'MEAN': Scale by inverse of mean
  - 'MEDIAN': Scale by inverse of median
- **Description:** Method for normalizing flat field on-the-fly

**config.flatUserScale**
- **Type:** float
- **Default:** 1.0
- **Description:** Scaling factor when flatScalingType='USER'

### 2.6 FWHM Parameter

**config.fwhm**
- **Type:** float
- **Default:** 1.0
- **Units:** arcseconds
- **Valid Range:** [0.1, 10.0] (typical)
- **Description:** Expected FWHM of PSF used for interpolation kernel sizing
- **Impact:** Affects interpolation over defects and cosmic rays; should match typical seeing

### 2.7 ISR Processing Order

ISR corrections are applied in this order (critical for reproducibility):
1. Saturation and suspect pixel masking
2. Overscan subtraction
3. CCD assembly (combining amplifiers)
4. Bias subtraction
5. Variance plane construction
6. Linearization
7. Crosstalk correction
8. Brighter-fatter correction
9. Dark subtraction
10. Deferred charge (CTI) correction
11. Flat fielding
12. Fringe correction
13. Defect masking and interpolation

---

## 3. Detection Parameters

**Task:** `lsst.meas.algorithms.detection.SourceDetectionTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.meas.algorithms/tasks/lsst.meas.algorithms.SourceDetectionTask.html

Detection identifies regions of the image containing astronomical sources by finding pixels above a threshold.

### 3.1 Core Detection Thresholds

#### config.detection.thresholdValue
- **Full Path:** `config.detection.thresholdValue`
- **Type:** float (RangeField)
- **Default:** 5.0
- **Valid Range:** [0.0, inf)
- **Units:** Depends on thresholdType (typically sigma)
- **Description:** Detection threshold for identifying footprints; exact meaning determined by thresholdType
- **Impact:** Higher values reduce false detections but miss faint sources; lower values increase completeness but add noise detections
- **Typical Range for Optimization:** [3.0, 10.0] sigma

#### config.detection.thresholdType
- **Full Path:** `config.detection.thresholdType`
- **Type:** str (ChoiceField)
- **Default:** 'pixel_stdev'
- **Valid Values:**
  - **'pixel_stdev'**: Threshold per-pixel standard deviation (most common, robust to variable noise)
  - **'stdev'**: Threshold applied to global image standard deviation
  - **'variance'**: Threshold applied to image variance
  - **'value'**: Threshold applied directly to pixel values
- **Description:** Specifies statistical method for threshold interpretation
- **Recommended:** 'pixel_stdev' for modern processing with variance planes

#### config.detection.thresholdPolarity
- **Full Path:** `config.detection.thresholdPolarity`
- **Type:** str (ChoiceField)
- **Default:** 'positive'
- **Valid Values:**
  - **'positive'**: Detect only positive sources (most common)
  - **'negative'**: Detect only negative sources (for difference imaging)
  - **'both'**: Detect positive and negative sources
- **Description:** Polarity of sources to detect

### 3.2 Footprint Morphology

#### config.detection.minPixels
- **Full Path:** `config.detection.minPixels`
- **Type:** int (RangeField)
- **Default:** 1
- **Valid Range:** [0, inf)
- **Description:** Minimum number of pixels in a detection; sources smaller than this are rejected
- **Impact:** Filters single hot pixels vs. real sources
- **Typical Range:** [1, 10]

#### config.detection.nSigmaToGrow
- **Full Path:** `config.detection.nSigmaToGrow`
- **Type:** float
- **Default:** 2.4
- **Valid Range:** [0, inf)
- **Units:** PSF RMS widths (sigma)
- **Description:** Grow detection footprints by this many PSF sigma; if 0, no growing
- **Impact:** Captures extended wings of PSF; too large merges nearby sources
- **Typical Range:** [0.0, 5.0]

#### config.detection.isotropicGrow
- **Full Path:** `config.detection.isotropicGrow`
- **Type:** bool
- **Default:** False
- **Valid Values:** True (circular growth), False (Manhattan/diamond metric)
- **Description:** Footprint growth pattern - isotropic (circular) or anisotropic (diamond)
- **Impact:** True is more computationally expensive but more physically motivated

### 3.3 Background Estimation

#### config.detection.reEstimateBackground
- **Full Path:** `config.detection.reEstimateBackground`
- **Type:** bool
- **Default:** False
- **Description:** Re-estimate background after initial detection (iterative approach)
- **Impact:** Can improve background model by masking detected sources

#### config.detection.doTempLocalBackground
- **Full Path:** `config.detection.doTempLocalBackground`
- **Type:** bool
- **Default:** False
- **Description:** Subtract temporary local background before detection to suppress wings of bright sources
- **Impact:** Helps avoid spurious detections in extended wings

#### config.detection.background.binSize
- **Full Path:** `config.detection.background.binSize`
- **Type:** int (RangeField)
- **Default:** 128
- **Valid Range:** [1, inf)
- **Units:** pixels
- **Description:** Size of background estimation mesh (larger = smoother background model)
- **Typical Range:** [64, 512]

#### config.detection.background.algorithm
- **Full Path:** `config.detection.background.algorithm`
- **Type:** str (ChoiceField)
- **Default:** 'AKIMA_SPLINE'
- **Valid Values:**
  - **'CONSTANT'**: Single constant value
  - **'LINEAR'**: Linear interpolation
  - **'NATURAL_SPLINE'**: Cubic spline with zero second derivative at endpoints
  - **'AKIMA_SPLINE'**: Robust nonlinear spline (recommended)
- **Description:** Background interpolation method

#### config.detection.background.statisticsProperty
- **Full Path:** `config.detection.background.statisticsProperty`
- **Type:** str (ChoiceField)
- **Default:** 'MEANCLIP'
- **Valid Values:**
  - **'MEANCLIP'**: Clipped mean (robust, recommended)
  - **'MEAN'**: Unclipped mean
  - **'MEDIAN'**: Median (most robust to outliers)
- **Description:** Statistic used for background grid points

---

## 4. PSF Measurement Parameters

**Task:** `lsst.pipe.tasks.measurePsf.MeasurePsfTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.pipe.tasks/

PSF measurement determines the point spread function model from stellar sources in the image, critical for accurate photometry and deblending.

### 4.1 Star Selection Configuration

#### config.measurePsf.starSelector (Registry)
- **Full Path:** `config.measurePsf.starSelector`
- **Type:** RegistryField (single-selection)
- **Default:** 'objectSize'
- **Description:** Controls algorithm for selecting stars (vs. galaxies) for PSF measurement

**Available Star Selectors:**

**A. 'objectSize' - ObjectSizeStarSelectorTask** (RECOMMENDED DEFAULT)
- **Class:** `lsst.meas.algorithms.objectSizeStarSelector.ObjectSizeStarSelectorTask`
- **Method:** Identifies stellar locus in size-magnitude space using clustering
- **Best For:** General-purpose PSF measurement with mixed star/galaxy fields

**Configuration Parameters:**

**config.measurePsf.starSelector["objectSize"].sourceFluxField**
- **Type:** str
- **Default:** 'base_GaussianFlux_instFlux'
- **Description:** Flux measurement field for magnitude calculation
- **Common Values:** 'base_GaussianFlux_instFlux', 'base_PsfFlux_instFlux', 'base_CircularApertureFlux_X_X_instFlux'

**config.measurePsf.starSelector["objectSize"].widthStdAllowed**
- **Type:** float
- **Default:** 0.15
- **Valid Range:** [0.0, 1.0]
- **Description:** Standard deviation in width (size) allowed for stellar locus
- **Impact:** Tighter values = stricter star/galaxy separation; looser values = more candidates

**config.measurePsf.starSelector["objectSize"].fluxMin**
- **Type:** float
- **Default:** 12500.0
- **Units:** Counts (flux units)
- **Description:** Minimum flux for PSF candidate consideration
- **Impact:** Avoid faint sources with poor S/N

**config.measurePsf.starSelector["objectSize"].fluxMax**
- **Type:** float
- **Default:** 0.0 (no maximum)
- **Description:** Maximum flux for PSF candidate; 0 = no limit
- **Impact:** Can exclude saturated sources if needed

**config.measurePsf.starSelector["objectSize"].doSignalToNoise**
- **Type:** bool
- **Default:** True
- **Description:** Apply signal-to-noise ratio cut

**config.measurePsf.starSelector["objectSize"].signalToNoiseMin**
- **Type:** float
- **Default:** 20.0
- **Valid Range:** [0, inf)
- **Description:** Minimum S/N for PSF star candidates
- **Typical Range:** [10.0, 100.0]

**B. 'science' - ScienceSourceSelectorTask**
- **Class:** `lsst.meas.algorithms.sourceSelector.ScienceSourceSelectorTask`
- **Method:** Flag-based and quality-based source selection
- **Best For:** When explicit quality criteria are more important than size clustering

**Key Parameters:**

**config.astrometry.sourceSelector["science"].doSignalToNoise**
- **Type:** bool
- **Default:** True
- **Description:** Apply S/N selection cut

**config.astrometry.sourceSelector["science"].signalToNoiseMin**
- **Type:** float
- **Default:** 10.0 (typical for astrometry; 20+ for PSF measurement)
- **Description:** Minimum signal-to-noise ratio

**config.astrometry.sourceSelector["science"].doFlags**
- **Type:** bool
- **Default:** True
- **Description:** Apply flag-based filtering (exclude sources with bad flags)

**config.astrometry.sourceSelector["science"].doUnresolved**
- **Type:** bool
- **Default:** True
- **Description:** Select only unresolved (point-like) sources

**C. 'matcher' - MatcherSourceSelectorTask**
- **Class:** `lsst.meas.algorithms.matcherSourceSelector.MatcherSourceSelectorTask`
- **Method:** Optimized for pattern matching in astrometry
- **Best For:** Astrometry source selection (not typically used for PSF measurement)

**D. 'astrometry' - AstrometrySourceSelectorTask**
- **Class:** `lsst.meas.algorithms.astrometrySourceSelector.AstrometrySourceSelectorTask`
- **Method:** Specialized for astrometric calibration
- **Best For:** Astrometry tasks

### 4.2 PSF Determiner Configuration

#### config.measurePsf.psfDeterminer (Registry)
- **Full Path:** `config.measurePsf.psfDeterminer`
- **Type:** RegistryField (single-selection)
- **Default:** 'psfex' (recent versions) or 'pca' (older versions)
- **Description:** Algorithm for constructing PSF model from selected stars

**Available PSF Determiners:**

**A. 'psfex' - PSFEx PSF Determiner** (RECOMMENDED)
- **Class:** `lsst.meas.extensions.psfex.psfexPsfDeterminer.PsfexPsfDeterminerTask`
- **Method:** Uses PSFEx algorithm (Bertin 2011) with spatially-varying basis functions
- **Best For:** Most applications; handles spatial variations well

**Configuration Parameters:**

**config.measurePsf.psfDeterminer['psfex'].spatialOrder**
- **Type:** int
- **Default:** 2
- **Valid Range:** [0, 6] (typical)
- **Description:** Polynomial order for spatial PSF variation model
- **Impact:**
  - 0 = constant PSF across field
  - 1 = linear variation
  - 2 = quadratic (standard, handles most optical distortions)
  - 3+ = higher-order (for complex aberrations)
- **Typical Range for Optimization:** [0, 3]

**config.measurePsf.psfDeterminer['psfex'].samplingSize**
- **Type:** float
- **Default:** 0.5
- **Valid Range:** [0.1, 1.0]
- **Description:** PSF model resolution relative to pixel size (0.5 = 2× oversampling)
- **Impact:** Higher resolution (smaller values) = more accurate but slower

**config.measurePsf.psfDeterminer['psfex'].sizeCellX**
- **Type:** int
- **Default:** 256
- **Valid Range:** [16, 1024]
- **Units:** pixels
- **Description:** Size of cells for PSF estimation (column direction)
- **Impact:** Smaller = more spatial variation captured; larger = fewer stars per cell

**config.measurePsf.psfDeterminer['psfex'].sizeCellY**
- **Type:** int
- **Default:** 256
- **Valid Range:** [16, 1024]
- **Units:** pixels
- **Description:** Size of cells for PSF estimation (row direction)

**config.measurePsf.psfDeterminer['psfex'].maxCandidates**
- **Type:** int
- **Default:** 300
- **Valid Range:** [10, 10000]
- **Description:** Maximum PSF stars to use; downsamples if more available
- **Impact:** More stars = better model but slower; fewer = faster but potentially less accurate
- **Typical Range:** [50, 500]

**config.measurePsf.psfDeterminer['psfex'].spatialReject**
- **Type:** float
- **Default:** 3.0
- **Valid Range:** [0, inf)
- **Units:** standard deviations
- **Description:** Rejection threshold for outlier stars based on spatial fit residuals
- **Impact:** Lower = more aggressive rejection of bad stars

**config.measurePsf.psfDeterminer['psfex'].tolerance**
- **Type:** float
- **Default:** 0.01
- **Valid Range:** [1e-6, 1.0]
- **Description:** Convergence tolerance for PSF fitting
- **Impact:** Smaller = more iterations, higher accuracy

**config.measurePsf.psfDeterminer['psfex'].recentroid**
- **Type:** bool
- **Default:** False
- **Description:** Allow PSFEx to recentroid star positions during fitting
- **Impact:** Can improve PSF quality if initial centroids are poor

**config.measurePsf.psfDeterminer['psfex'].psfexBasis**
- **Type:** str (ChoiceField)
- **Default:** 'PIXEL_AUTO'
- **Valid Values:**
  - **'PIXEL'**: Always use samplingSize as specified
  - **'PIXEL_AUTO'**: Use samplingSize only for FWHM < 3 pixels; otherwise samplingSize=1
- **Description:** Controls PSF basis function sampling

**config.measurePsf.psfDeterminer['psfex'].badMaskBits**
- **Type:** List of str
- **Default:** ['INTRP', 'SAT']
- **Description:** Mask bits causing source rejection as PSF candidate
- **Common Values:** 'INTRP', 'SAT', 'CR', 'BAD', 'EDGE'

**B. 'pca' - PCA PSF Determiner**
- **Class:** `lsst.meas.algorithms.psfDeterminer.PcaPsfDeterminer`
- **Method:** Principal Component Analysis decomposition
- **Best For:** Simple PSF models; legacy compatibility

---

## 5. Astrometry Parameters

**Task:** `lsst.meas.astrom.astrometry.AstrometryTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.meas.astrom/tasks/lsst.meas.astrom.AstrometryTask.html

Astrometry determines the World Coordinate System (WCS) by matching detected sources to a reference catalog.

### 5.1 Source Selector for Astrometry

#### config.astrometry.sourceSelector
- **Full Path:** `config.astrometry.sourceSelector`
- **Type:** RegistryField (single-selection)
- **Default:** 'science'
- **Description:** Selects which detected sources to use for astrometric matching

**What "science" means:** The 'science' selector (`ScienceSourceSelectorTask`) applies general quality cuts appropriate for science analysis - S/N thresholds, flag filtering, and unresolved source selection. It's the default because it provides a balanced set of high-quality sources suitable for most astrometric solutions.

**Configuration for 'science' selector:**

**config.astrometry.sourceSelector["science"].doSignalToNoise**
- **Type:** bool
- **Default:** True
- **Description:** Apply signal-to-noise cut

**config.astrometry.sourceSelector["science"].signalToNoiseMin**
- **Type:** float
- **Default:** 10.0
- **Valid Range:** [0, inf)
- **Description:** Minimum S/N for astrometric source selection
- **Typical Range:** [5.0, 50.0]

**config.astrometry.sourceSelector["science"].doFlags**
- **Type:** bool
- **Default:** True
- **Description:** Exclude sources with bad flags

**config.astrometry.sourceSelector["science"].doUnresolved**
- **Type:** bool
- **Default:** True
- **Description:** Select only unresolved (point-like) sources for astrometry

### 5.2 Matcher Configuration (Critical for Parameter Optimization)

**Hierarchy Explanation:**
- **config.astrometry**: The AstrometryTask subtask within CalibrateTask
- **config.astrometry.matcher**: The MatchPessimisticBTask subtask that performs pattern matching
- **Matcher purpose**: Finds geometric patterns in source and reference catalogs to determine initial WCS transformation

**Default Matcher:** `lsst.meas.astrom.matchPessimisticB.MatchPessimisticBTask`
**Algorithm:** Pessimistic Pattern Matcher B - constructs geometric patterns from bright sources and references
**Documentation:** https://pipelines.lsst.io/py-api/lsst.meas.astrom.MatchPessimisticBConfig.html

#### config.astrometry.matcher.maxOffsetPix
- **Full Path:** `config.astrometry.matcher.maxOffsetPix`
- **Type:** int (RangeField)
- **Default:** 250
- **Valid Range:** [-inf, 4000) (practical range: [50, 2000])
- **Units:** pixels
- **Description:** Maximum allowed spatial offset between initial WCS and true sky positions; defines search radius for pattern matching
- **Impact:**
  - **Too small**: Fails when initial WCS is poor (>maxOffsetPix error)
  - **Too large**: Increased computation time and false match probability
  - **Performance scaling**: O(N²) with offset
- **Typical Values:**
  - Good initial WCS: 50-100 pixels
  - Poor/approximate WCS: 250-500 pixels
  - No WCS: 1000+ pixels (very slow)
- **IMPORTANT:** When changing this, also update `config.astromRefObjLoader.pixelMargin` to ensure sufficient reference objects are loaded

#### config.astrometry.matcher.maxRotationDeg
- **Full Path:** `config.astrometry.matcher.maxRotationDeg`
- **Type:** float (RangeField)
- **Default:** 1.0
- **Valid Range:** [-inf, 6.0) degrees (practical: [0.1, 5.0])
- **Units:** degrees
- **Description:** Maximum rotation angle error allowed in initial WCS
- **Impact:**
  - **Too small**: Fails if WCS rotation is off by >maxRotationDeg
  - **Too large**: More false pattern matches considered
- **Typical Values:**
  - Known orientation: 0.5-1.0 degrees
  - Uncertain orientation: 2.0-5.0 degrees

#### config.astrometry.matcher.matcherIterations
- **Full Path:** `config.astrometry.matcher.matcherIterations`
- **Type:** int (RangeField)
- **Default:** 5
- **Valid Range:** [1, inf) (practical: [1, 10])
- **Description:** Number of softening iterations in pattern matcher; iteratively relaxes matching constraints to find robust solution
- **Impact:**
  - **More iterations**: Better recovery from difficult initial conditions; longer processing
  - **Fewer iterations**: Faster but may fail on challenging fields
- **Typical Range:** [3, 7]

#### config.astrometry.matcher.minMatchDistPixels
- **Full Path:** `config.astrometry.matcher.minMatchDistPixels`
- **Type:** float
- **Default:** 1.0
- **Valid Range:** [0, inf) (practical: [0.5, 5.0])
- **Units:** pixels
- **Description:** Distance below which source-reference pairs are always considered a match during WCS fitting iterations
- **Impact:** Allows including new matches as WCS improves during fitting; prevents overfitting
- **Typical Range:** [1.0, 3.0]

#### config.astrometry.matcher.minMatchedPairs
- **Full Path:** `config.astrometry.matcher.minMatchedPairs`
- **Type:** int
- **Default:** 30
- **Valid Range:** [1, inf) (practical: [10, 100])
- **Description:** Absolute minimum number of matched source-reference pairs required for acceptable astrometric solution
- **Impact:**
  - **Higher values**: More robust solutions but may fail in sparse fields
  - **Lower values**: More permissive but potentially unreliable solutions
- **Used with:** Works in conjunction with minFracMatchedPairs; minimum is max(minMatchedPairs, minFracMatchedPairs × N)
- **Typical Range:** [15, 50]

#### config.astrometry.matcher.minFracMatchedPairs
- **Full Path:** `config.astrometry.matcher.minFracMatchedPairs`
- **Type:** float
- **Default:** 0.3
- **Valid Range:** [0, 1.0]
- **Description:** Minimum fraction of matches relative to min(number of reference stars, number of good sources)
- **Impact:** Provides adaptive threshold based on field density
- **Formula:** Actual minimum = max(minMatchedPairs, minFracMatchedPairs × min(N_ref, N_src))
- **Typical Range:** [0.2, 0.5]

#### config.astrometry.matcher.numBrightStars
- **Full Path:** `config.astrometry.matcher.numBrightStars`
- **Type:** int
- **Default:** 200
- **Valid Range:** [1, inf) (practical: [20, 500])
- **Description:** Number of brightest stars used for pattern construction; determines maximum patterns tested
- **Impact:**
  - **More stars**: Better matching in crowded fields; computation scales as O(N³)
  - **Fewer stars**: Much faster but may fail in complex fields
- **Performance Note:** Most critical parameter for computation time
- **Typical Values:**
  - Sparse fields: 50-100
  - Dense fields: 200-300
  - Crowded/complex: 300-500

#### config.astrometry.matcher.maxRefObjects
- **Full Path:** `config.astrometry.matcher.maxRefObjects`
- **Type:** int (RangeField)
- **Default:** 65536
- **Valid Range:** [0, 65537)
- **Absolute Maximum:** 65536 (2¹⁶; memory constraint in matcher implementation)
- **Description:** Maximum number of reference catalog objects to use for matching
- **Impact:** Limits memory usage; critical for very dense reference catalogs (e.g., Gaia in galactic plane)
- **Note:** If reference catalog has more objects in field, they are randomly sampled

#### config.astrometry.matcher.numPatternConsensus
- **Full Path:** `config.astrometry.matcher.numPatternConsensus`
- **Type:** int
- **Default:** 3
- **Valid Range:** [1, inf) (practical: [2, 5])
- **Description:** Number of implied shift/rotation patterns that must agree before accepting a transformation
- **When Used:** Only activated after first softening iteration fails AND both reference and source counts > numBrightStars
- **Impact:** Increases robustness against false matches in challenging cases
- **Typical Range:** [2, 4]

**Additional Matcher Parameters:**

**config.astrometry.matcher.numPointsForShape**
- **Full Path:** `config.astrometry.matcher.numPointsForShape`
- **Type:** int
- **Default:** 6
- **Valid Range:** [3, inf)
- **Description:** Number of points defining geometric pattern for matching (e.g., 6-point asterism)
- **Impact:** More points = more distinctive patterns but fewer matches in sparse fields

### 5.3 WCS Fitter Configuration

**config.astrometry.wcsFitter**
- **Full Path:** `config.astrometry.wcsFitter`
- **Default Class:** `lsst.meas.astrom.fitTanSipWcs.FitTanSipWcsTask`
- **Purpose:** Fits World Coordinate System with distortion model after initial matching
- **Documentation:** https://pipelines.lsst.io/modules/lsst.meas.astrom/tasks/lsst.meas.astrom.FitTanSipWcsTask.html

**config.astrometry.wcsFitter.order**
- **Type:** int (RangeField)
- **Default:** 2
- **Valid Range:** [0, inf) (practical: [0, 6])
- **Description:** Order of SIP (Simple Imaging Polynomial) distortion polynomial
- **Impact:**
  - **0**: No distortion correction (simple tangent projection)
  - **1-2**: Low-order distortion (most optical systems)
  - **3-4**: Higher-order distortion (wide-field or complex optics)
  - **5+**: Very high-order (rarely needed; may overfit)
- **Typical Range:** [2, 4]

**config.astrometry.wcsFitter.numIter**
- **Type:** int (RangeField)
- **Default:** 3
- **Valid Range:** [1, inf)
- **Description:** Number of fitting iterations (fits X and Y separately, benefits from iteration)
- **Typical Range:** [2, 5]

**config.astrometry.wcsFitter.rejSigma**
- **Type:** float (RangeField)
- **Default:** 3.0
- **Valid Range:** [0.0, inf)
- **Units:** standard deviations
- **Description:** Sigma threshold for clipping outlier matches during WCS fitting
- **Impact:** Lower = more aggressive outlier rejection
- **Typical Range:** [2.0, 5.0]

**config.astrometry.wcsFitter.maxScatterArcsec**
- **Type:** float (RangeField)
- **Default:** 10.0
- **Valid Range:** [0, inf)
- **Units:** arcseconds
- **Description:** Maximum median on-sky scatter; fit fails catastrophically if exceeded
- **Purpose:** Catches complete failures (not for quality control)

### 5.4 Astrometry Iteration Control

**config.astrometry.maxIter**
- **Full Path:** `config.astrometry.maxIter`
- **Type:** int (RangeField)
- **Default:** 3
- **Valid Range:** [1, inf)
- **Description:** Maximum iterations of match-sources-fit-WCS cycle
- **Impact:** More iterations allow convergence from worse initial WCS

**config.astrometry.matchDistanceSigma**
- **Full Path:** `config.astrometry.matchDistanceSigma`
- **Type:** float (RangeField)
- **Default:** 2.0
- **Valid Range:** [0, inf)
- **Description:** Maximum match distance = mean + matchDistanceSigma × std_dev
- **Impact:** Controls adaptive matching radius during iterations

**config.astrometry.maxMeanDistanceArcsec**
- **Full Path:** `config.astrometry.maxMeanDistanceArcsec`
- **Type:** float (RangeField)
- **Default:** 0.5
- **Valid Range:** [0, inf)
- **Units:** arcseconds
- **Description:** Maximum acceptable mean on-sky distance post-fit; exceeding raises BadAstrometryFit
- **Note:** Value is workflow-dependent; 0.5 arcsec suitable for external calibration

---

## 6. Photometry Parameters

**Task:** `lsst.pipe.tasks.photoCal.PhotoCalTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.pipe.tasks/tasks/lsst.pipe.tasks.photoCal.PhotoCalTask.html

Photometric calibration determines the magnitude zero point by matching source fluxes to reference catalog magnitudes.

### 6.1 Core Photometric Calibration

#### config.photoCal.fluxField
- **Full Path:** `config.photoCal.fluxField`
- **Type:** str
- **Default:** 'slot_CalibFlux_instFlux'
- **Description:** Flux measurement field to use for photometric calibration; associated flag field is implicitly included
- **Common Values:**
  - 'slot_CalibFlux_instFlux' (default; typically CircularApertureFlux)
  - 'base_PsfFlux_instFlux'
  - 'base_CircularApertureFlux_X_X_instFlux'

#### config.photoCal.applyColorTerms
- **Type:** bool
- **Default:** True
- **Description:** Apply photometric color terms to reference stars for multi-band corrections
- **Impact:** True = apply color corrections (fails if unavailable); False = ignore color terms
- **Note:** Critical for accurate cross-band photometry

#### config.photoCal.magErrFloor
- **Type:** float
- **Default:** 0.0
- **Valid Range:** [0.0, inf)
- **Units:** magnitudes
- **Description:** Systematic magnitude uncertainty added in quadrature with measurement errors
- **Purpose:** Provides error floor for photometric calibration
- **Typical Range:** [0.0, 0.02] mag

### 6.2 Iterative Fitting Parameters

#### config.photoCal.nIter
- **Full Path:** `config.photoCal.nIter`
- **Type:** int
- **Default:** 3
- **Valid Range:** [1, 10]
- **Description:** Number of iterative sigma-clipping cycles for zero point fitting
- **Typical Range:** [2, 5]

#### config.photoCal.nSigma
- **Full Path:** `config.photoCal.nSigma`
- **Type:** float
- **Default:** 3.0
- **Valid Range:** [1.0, 10.0]
- **Units:** standard deviations
- **Description:** Outlier rejection threshold during iterative fitting
- **Typical Range:** [2.5, 4.0]

#### config.photoCal.useMedian
- **Full Path:** `config.photoCal.useMedian`
- **Type:** bool
- **Default:** True
- **Description:** Use median (vs. mean) for zero point calculation
- **Impact:** Median is more robust to outliers (recommended)

### 6.3 Color Terms Configuration

**config.photoCal.colorterms**
- **Full Path:** `config.photoCal.colorterms`
- **Type:** ConfigDictField
- **Data Type:** `lsst.pipe.tasks.colorterms.ColortermLibrary`
- **Description:** Library mapping reference catalog names to color term dictionaries
- **Purpose:** Transforms reference catalog magnitudes to instrument system

**Colorterm Object Parameters:**

**primary**
- **Type:** str
- **Description:** Primary filter name in color term equation
- **Example:** 'g'

**secondary**
- **Type:** str
- **Description:** Secondary filter for color computation
- **Example:** 'r' (for g-r color)

**c0, c1, c2**
- **Type:** float
- **Default:** 0.0
- **Description:** Color term equation coefficients
- **Equation:** mag_obs = mag_ref + c0 + c1×(primary-secondary) + c2×(primary-secondary)²
- **Purpose:** c0 = zero-point offset, c1 = linear color dependence, c2 = quadratic term

**Example Configuration:**
```python
from lsst.pipe.tasks.colorterms import Colorterm
config.photoCal.colorterms.data = {
    'ps1*': Colorterm(primary='g', secondary='r', c0=-0.00816, c1=-0.08367)
}
```

---

## 7. Measurement Algorithms

**Task:** `lsst.meas.base.sfm.SingleFrameMeasurementTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.meas.base/tasks/lsst.meas.base.sfm.SingleFrameMeasurementTask.html

Measurement algorithms extract photometric and morphological properties from detected sources.

### 7.1 Plugin Configuration

**config.measurement.plugins**
- **Full Path:** `config.measurement.plugins`
- **Type:** RegistryInstanceDict
- **Default Plugins:** ['base_PixelFlags', 'base_SdssCentroid', 'base_SdssShape', 'base_GaussianFlux', 'base_PsfFlux', 'base_CircularApertureFlux', 'base_SkyCoord', 'base_Variance', 'base_Blendedness', 'base_LocalBackground']
- **Description:** Measurement algorithms to run and their configurations

### 7.2 Critical Measurement Plugins

#### base_PsfFlux (PSF Photometry)
- **Algorithm:** Linear least-squares fit of PSF model to source
- **Purpose:** Most accurate flux for point sources
- **Config:** `config.measurement.plugins['base_PsfFlux']`

**config.measurement.plugins['base_PsfFlux'].badMaskPlanes**
- **Type:** List of str
- **Default:** ['BAD', 'SAT', 'INTRP', 'NO_DATA']
- **Description:** Mask planes to exclude from PSF fit

#### base_CircularApertureFlux (Aperture Photometry)
- **Algorithm:** Sum flux within circular apertures
- **Purpose:** Standard photometry for extended sources
- **Config:** `config.measurement.plugins['base_CircularApertureFlux']`

**config.measurement.plugins['base_CircularApertureFlux'].radii**
- **Type:** List of float
- **Default:** [3.0, 4.5, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0] (typical)
- **Units:** pixels
- **Description:** Aperture radii for flux measurement
- **Impact:** Should span range from PSF core to extended wings

**config.measurement.plugins['base_CircularApertureFlux'].maxSincRadius**
- **Type:** float
- **Default:** 10.0
- **Units:** pixels
- **Description:** Maximum radius for sinc interpolation (vs. bilinear)
- **Impact:** Sinc is more accurate but slower

#### base_SdssShape (Shape Measurement)
- **Algorithm:** SDSS-style adaptive moments
- **Purpose:** Measures second moments for size and ellipticity
- **Config:** `config.measurement.plugins['base_SdssShape']`

**config.measurement.plugins['base_SdssShape'].maxShift**
- **Type:** float
- **Default:** 0.0 (no shift allowed from initial centroid)
- **Description:** Maximum centroid shift during shape fitting

### 7.3 Slot Configuration

**Slots** map measurement algorithm results to standard fields in the catalog.

**config.measurement.slots.calibFlux**
- **Type:** str
- **Default:** 'base_CircularApertureFlux_12_0' (12-pixel aperture)
- **Description:** Flux measurement used for calibration

**config.measurement.slots.psfFlux**
- **Type:** str
- **Default:** 'base_PsfFlux'
- **Description:** PSF flux measurement

**config.measurement.slots.centroid**
- **Type:** str
- **Default:** 'base_SdssCentroid'
- **Description:** Centroid algorithm

**config.measurement.slots.shape**
- **Type:** str
- **Default:** 'base_SdssShape'
- **Description:** Shape measurement algorithm

### 7.4 Aperture Correction

**Task:** `lsst.meas.algorithms.measureApCorr.MeasureApCorrTask`

**Purpose:** Aperture corrections adjust finite-aperture fluxes to total fluxes by measuring the ratio of PSF flux to aperture flux for stars and modeling spatial variations.

**config.measureApCorr.sourceSelector**
- **Type:** RegistryField
- **Default:** 'science'
- **Description:** Selector for stars used in aperture correction measurement

**config.measureApCorr.numIter**
- **Type:** int
- **Default:** 4
- **Description:** Number of robust sigma-clipping iterations

**config.measureApCorr.numSigmaClip**
- **Type:** float
- **Default:** 3.0
- **Description:** Sigma threshold for outlier clipping

**config.measureApCorr.refFluxName**
- **Type:** str
- **Default:** 'slot_CalibFlux'
- **Description:** Reference flux field (typically PSF flux) to which other measurements are corrected

---

## 8. Other CalibrateImage Components

### 8.1 Cosmic Ray Rejection

**Task:** `lsst.pipe.tasks.repair.RepairTask` (in CharacterizeImageTask)
**Purpose:** Identifies and masks/interpolates cosmic ray hits

**config.repair.doCosmicRay**
- **Type:** bool
- **Default:** True
- **Description:** Find and mask cosmic rays

**config.repair.cosmicray.minSigma**
- **Type:** float
- **Default:** 6.0
- **Valid Range:** [3.0, 10.0]
- **Units:** sigma
- **Description:** Detection threshold for cosmic rays
- **Impact:** Lower = more sensitive but more false positives

**config.repair.cosmicray.minNumPixels**
- **Type:** int
- **Default:** 1
- **Description:** Minimum pixels in a cosmic ray
- **Purpose:** Distinguishes CRs from hot pixels

**config.repair.cosmicray.niteration**
- **Type:** int
- **Default:** 3
- **Valid Range:** [1, 5]
- **Description:** Number of CR detection iterations

### 8.2 Deblending

**Task:** `lsst.meas.deblender.sourceDeblendTask.SourceDeblendTask`
**Purpose:** Separates blended sources into individual components

**config.doDeblend**
- **Type:** bool
- **Default:** True
- **Description:** Run deblender on detected sources

### 8.3 Top-Level Task Control

**config.doAstrometry**
- **Type:** bool
- **Default:** True
- **Description:** Perform astrometric calibration

**config.doPhotoCal**
- **Type:** bool
- **Default:** True
- **Description:** Perform photometric calibration

**config.requireAstrometry**
- **Type:** bool
- **Default:** True
- **Description:** Raise exception if astrometry fails (vs. continue with poor WCS)

**config.requirePhotoCal**
- **Type:** bool
- **Default:** True
- **Description:** Raise exception if photometry fails (vs. continue without photometric calibration)

---

## 9. Parameter Grid Examples

### 9.1 Astrometry Optimization Grid (Nickel Telescope)

**Scenario:** Small telescope with approximate initial WCS, need robust astrometric solutions

```python
parameter_grid = {
    # Matcher configuration
    'astrometry.matcher.maxOffsetPix': [250, 500, 750],
    'astrometry.matcher.maxRotationDeg': [1.0, 2.0, 3.0],
    'astrometry.matcher.numBrightStars': [100, 150, 200, 250],
    'astrometry.matcher.minMatchedPairs': [20, 30, 40],
    'astrometry.matcher.matcherIterations': [3, 5, 7],

    # WCS fitting
    'astrometry.wcsFitter.order': [2, 3, 4],
    'astrometry.wcsFitter.rejSigma': [2.5, 3.0, 3.5],

    # Source selection
    'astrometry.sourceSelector["science"].signalToNoiseMin': [10.0, 20.0, 30.0],
}
```

**Recommended Optimization Strategy:**
1. Start with `maxOffsetPix` and `maxRotationDeg` to establish reliable matching
2. Tune `numBrightStars` to balance accuracy and speed
3. Adjust `minMatchedPairs` based on field density
4. Fine-tune WCS fitter `order` and `rejSigma` for optimal residuals

### 9.2 PSF Measurement Optimization Grid

```python
parameter_grid = {
    # Star selection
    'measurePsf.starSelector.name': ['objectSize'],
    'measurePsf.starSelector["objectSize"].signalToNoiseMin': [20.0, 30.0, 50.0],
    'measurePsf.starSelector["objectSize"].widthStdAllowed': [0.10, 0.15, 0.20],

    # PSF determiner
    'measurePsf.psfDeterminer.name': ['psfex'],
    'measurePsf.psfDeterminer["psfex"].spatialOrder': [0, 1, 2, 3],
    'measurePsf.psfDeterminer["psfex"].samplingSize': [0.5, 1.0],
    'measurePsf.psfDeterminer["psfex"].maxCandidates': [150, 200, 300],
    'measurePsf.psfDeterminer["psfex"].sizeCellX': [128, 256, 512],
    'measurePsf.psfDeterminer["psfex"].sizeCellY': [128, 256, 512],
}
```

**Optimization Metrics:**
- PSF model χ² residuals
- PSF FWHM consistency across field
- Star/galaxy separation performance
- Processing time

### 9.3 Detection Optimization Grid

```python
parameter_grid = {
    # Detection thresholds
    'detection.thresholdValue': [3.0, 4.0, 5.0, 7.0],
    'detection.thresholdType': ['pixel_stdev'],
    'detection.minPixels': [1, 3, 5],
    'detection.nSigmaToGrow': [0.0, 2.0, 2.4, 3.0],

    # Background estimation
    'detection.background.binSize': [64, 128, 256],
    'detection.background.algorithm': ['AKIMA_SPLINE', 'NATURAL_SPLINE'],
    'detection.background.statisticsProperty': ['MEANCLIP', 'MEDIAN'],
}
```

**Optimization Metrics:**
- Completeness (detection rate vs. known sources)
- Purity (real sources / total detections)
- False positive rate
- Faint magnitude limit

### 9.4 ISR Configuration for Optimization

```python
parameter_grid = {
    # Core corrections (mostly binary on/off)
    'isr.doFlat': [True],
    'isr.doBias': [True],
    'isr.doDark': [True],
    'isr.doFringe': [True, False],  # Test if fringe correction helps

    # Interpolation
    'isr.fwhm': [0.8, 1.0, 1.2, 1.5],  # FWHM in arcsec
    'isr.maskListToInterpolate': [
        ['SAT', 'BAD'],
        ['SAT', 'BAD', 'CR'],
    ],

    # Saturation handling
    'isr.growSaturationFootprintSize': [0, 1, 2, 3],
}
```

### 9.5 Full Pipeline Optimization Priority

**High Priority (Most Impact):**
1. `astrometry.matcher.maxOffsetPix` - Critical for matching success
2. `astrometry.matcher.numBrightStars` - Balances accuracy and speed
3. `detection.thresholdValue` - Controls completeness/purity tradeoff
4. `measurePsf.psfDeterminer["psfex"].spatialOrder` - PSF quality
5. `astrometry.wcsFitter.order` - Distortion correction accuracy

**Medium Priority:**
6. `astrometry.matcher.minMatchedPairs` - Solution robustness
7. `measurePsf.starSelector["objectSize"].signalToNoiseMin` - PSF star quality
8. `detection.nSigmaToGrow` - Detection completeness
9. `astrometry.matcher.maxRotationDeg` - Orientation tolerance
10. `detection.background.binSize` - Background model scale

**Lower Priority (Fine-Tuning):**
11. `astrometry.wcsFitter.rejSigma` - Outlier rejection
12. `measurePsf.psfDeterminer["psfex"].maxCandidates` - PSF sample size
13. `photoCal.nSigma` - Photometric outlier rejection
14. `detection.minPixels` - Spurious detection filtering

### 9.6 Nickel Telescope-Specific Considerations

For Nickel telescope optimization, prioritize:
1. **Astrometry robustness**: Likely has approximate WCS from mount
2. **PSF spatial variation**: Small telescope may have significant field-dependent aberrations
3. **Background estimation**: Detector characteristics and sky conditions
4. **Detection threshold**: Balance between faint source recovery and false positives

**Recommended Starting Point:**
```python
# Conservative starting configuration
config.astrometry.matcher.maxOffsetPix = 500  # Allow for poor initial WCS
config.astrometry.matcher.numBrightStars = 200  # Good balance
config.astrometry.wcsFitter.order = 3  # Capture field distortion
config.detection.thresholdValue = 5.0  # Standard detection
config.measurePsf.psfDeterminer["psfex"].spatialOrder = 2  # Model PSF variation
```

**Validation Metrics:**
- Astrometric RMS residuals (target: <0.3 arcsec)
- Number of successful astrometric matches
- PSF FWHM consistency
- Photometric zero point scatter
- Processing time per exposure

---

## Additional Documentation Resources

**Primary References:**
- LSST Science Pipelines: https://pipelines.lsst.io
- GitHub Repositories:
  - ISR: https://github.com/lsst/ip_isr
  - Astrometry: https://github.com/lsst/meas_astrom
  - Photometry: https://github.com/lsst/pipe_tasks
  - Detection: https://github.com/lsst/meas_algorithms

**Community Support:**
- LSST Community Forum: https://community.lsst.org
- Configuration Examples: https://github.com/lsst/obs_lsst/tree/main/config

**Technical Notes:**
- ISR Technical Paper: https://arxiv.org/html/2404.14516v1
- PSFEx Algorithm: Bertin (2011) - Automated morphometry with PSFEx

This comprehensive reference provides all tunable parameters needed to establish an optimization grid for the Nickel telescope's LSST Science Pipelines processing. The hierarchical organization, detailed parameter descriptions, and optimization examples enable systematic parameter tuning for achieving optimal data reduction quality.
