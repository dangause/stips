# LSST Science Pipelines Parameter Reference Manual

**Complete catalog of configurable parameters for ISR and CalibrateImage pipeline tasks**

**Primary Documentation:** https://pipelines.lsst.io
**Version:** Current as of LSST Science Pipelines v28+

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Configuration System](#2-configuration-system)
3. [ISR Parameters](#3-isr-parameters)
4. [Detection Parameters](#4-detection-parameters)
5. [PSF Measurement Parameters](#5-psf-measurement-parameters)
6. [Astrometry Parameters](#6-astrometry-parameters)
7. [Photometry Parameters](#7-photometry-parameters)
8. [Measurement Parameters](#8-measurement-parameters)
9. [Additional Tasks](#9-additional-tasks)

---

## 1. Pipeline Overview

### Processing Chain

```
RAW IMAGE
    ↓
ISR (Instrument Signature Removal)
    ├─ Bias, dark, flat corrections
    ├─ Defect masking and interpolation
    └─ Variance plane construction
    ↓
CHARACTERIZE IMAGE
    ├─ Background estimation
    ├─ Source detection
    └─ PSF measurement
    ↓
CALIBRATE IMAGE
    ├─ Astrometric calibration (WCS)
    ├─ Photometric calibration (zero point)
    ├─ Final detection and measurement
    └─ Deblending
    ↓
CALIBRATED IMAGE + SOURCE CATALOG
```

### Task Documentation Links

- **IsrTask:** https://pipelines.lsst.io/v/daily/py-api/lsst.ip.isr.IsrTask.html
- **SourceDetectionTask:** https://pipelines.lsst.io/modules/lsst.meas.algorithms/tasks/lsst.meas.algorithms.SourceDetectionTask.html
- **MeasurePsfTask:** https://pipelines.lsst.io/modules/lsst.pipe.tasks/tasks/lsst.pipe.tasks.measurePsf.MeasurePsfTask.html
- **AstrometryTask:** https://pipelines.lsst.io/modules/lsst.meas.astrom/tasks/lsst.meas.astrom.AstrometryTask.html
- **PhotoCalTask:** https://pipelines.lsst.io/modules/lsst.pipe.tasks/tasks/lsst.pipe.tasks.photoCal.PhotoCalTask.html

---

## 2. Configuration System

### Access Patterns

```python
# Simple field
config.parameter = value

# Nested subtask
config.subtask.parameter = value

# Registry field (select variant)
config.selector.name = 'variant'

# Registry field (configure specific variant)
config.selector['variant'].parameter = value
```

### Command-Line Configuration

```bash
# Set parameter
pipetask run --config calibrate:astrometry.matcher.maxOffsetPix=500

# Load config file
pipetask run --config-file myconfig.py
```

---

## 3. ISR Parameters

**Task:** `lsst.ip.isr.IsrTask`
**Purpose:** Remove instrumental signatures from raw images

### 3.1 Core Processing Control

#### config.isr.doOverscan
- **Type:** bool
- **Default:** True
- **Description:** Subtract overscan region to remove bias pedestal
- **When to disable:** Overscan region corrupted or unreliable

#### config.isr.doBias
- **Type:** bool
- **Default:** True
- **Description:** Subtract master bias frame
- **When to disable:** Only when constructing master bias

#### config.isr.doDark
- **Type:** bool
- **Default:** True
- **Description:** Subtract dark current
- **Scales with:** Exposure time
- **When to disable:** Very short exposures where dark is negligible

#### config.isr.doFlat
- **Type:** bool
- **Default:** True
- **Description:** Apply flat field correction
- **When to disable:** Never for science images

#### config.isr.doLinearize
- **Type:** bool
- **Default:** True
- **Description:** Correct detector non-linearity
- **Impact:** Important for high signal levels (>50% full well)

#### config.isr.doFringe
- **Type:** bool
- **Default:** True
- **Description:** Remove fringe patterns (thin-film interference)
- **When to enable:** Red/IR filters (i, z, y bands)
- **When to disable:** Blue filters (u, g, r bands)

### 3.2 Advanced Corrections

#### config.isr.doCrosstalk
- **Type:** bool
- **Default:** False
- **Description:** Remove electronic crosstalk between amplifiers
- **Requires:** Crosstalk matrix calibration
- **When to enable:** Detector has known crosstalk >0.1%

#### config.isr.doBrighterFatter
- **Type:** bool
- **Default:** False
- **Description:** Correct for charge redistribution in deep wells
- **Physical effect:** Brighter sources appear larger
- **Requires:** BF correction kernel
- **When to enable:** Precision photometry/astrometry needed

**config.isr.brighterFatterLevel**
- **Type:** str (ChoiceField)
- **Default:** 'DETECTOR'
- **Valid values:** 'AMP', 'DETECTOR'
- **Description:** Spatial scale of BF correction application

**config.isr.brighterFatterMaxIter**
- **Type:** int
- **Default:** 10
- **Valid range:** [1, inf)
- **Description:** Maximum iterations for BF convergence

**config.isr.brighterFatterThreshold**
- **Type:** float
- **Default:** 1000.0
- **Valid range:** [0, inf)
- **Description:** Convergence threshold (sum of absolute differences)

#### config.isr.doDeferredCharge
- **Type:** bool
- **Default:** False
- **Description:** Correct charge transfer inefficiency (CTI)
- **Physical effect:** Charge trailing from traps
- **Requires:** CTI correction model

### 3.3 Masking and Interpolation

#### config.isr.doSaturation
- **Type:** bool
- **Default:** True
- **Description:** Identify and mask saturated pixels

**config.isr.saturation**
- **Type:** float
- **Default:** Detector-specific (from camera model)
- **Units:** ADU
- **Description:** Saturation threshold

**config.isr.growSaturationFootprintSize**
- **Type:** int
- **Default:** 1
- **Valid range:** [0, inf)
- **Units:** pixels
- **Description:** Grow saturation mask by N pixels in all directions
- **Purpose:** Mask charge bleed trails

#### config.isr.doDefect
- **Type:** bool
- **Default:** True
- **Description:** Mask known bad pixels/columns from defect lists

#### config.isr.doInterpolate
- **Type:** bool
- **Default:** True
- **Description:** Interpolate over masked pixels

**config.isr.maskListToInterpolate**
- **Type:** List of str
- **Default:** ['SAT', 'BAD']
- **Common values:** 'SAT', 'BAD', 'CR', 'INTRP', 'UNMASKEDNAN'
- **Description:** Mask planes that trigger interpolation

**config.isr.fwhm**
- **Type:** float
- **Default:** 1.0
- **Units:** arcseconds
- **Valid range:** [0.1, 10.0]
- **Description:** Expected PSF FWHM for interpolation kernel sizing

### 3.4 Variance Estimation

#### config.isr.doVariance
- **Type:** bool
- **Default:** True
- **Description:** Construct variance plane for noise model
- **Required for:** Optimal detection with pixel_stdev threshold type

**config.isr.gain**
- **Type:** float
- **Default:** nan (use detector model)
- **Units:** e-/ADU
- **Valid range:** [0, inf) or nan
- **Description:** Detector gain override

**config.isr.readNoise**
- **Type:** float
- **Default:** 0.0 (use detector model)
- **Units:** electrons
- **Valid range:** [0, inf)
- **Description:** Read noise override

### 3.5 Flat Field Configuration

**config.isr.flatScalingType**
- **Type:** str (ChoiceField)
- **Default:** 'USER'
- **Valid values:**
  - 'USER': Scale by flatUserScale
  - 'MEAN': Scale by inverse of mean
  - 'MEDIAN': Scale by inverse of median
- **Description:** Flat field normalization method

**config.isr.flatUserScale**
- **Type:** float
- **Default:** 1.0
- **Description:** User-specified flat field scaling factor

### 3.6 ISR Processing Order

1. Saturation/suspect pixel masking
2. Overscan subtraction
3. CCD assembly (combine amplifiers)
4. Bias subtraction
5. Variance plane construction
6. Linearization
7. Crosstalk correction
8. Brighter-fatter correction
9. Dark subtraction
10. Deferred charge correction
11. Flat fielding
12. Fringe correction
13. Defect masking and interpolation

---

## 4. Detection Parameters

**Task:** `lsst.meas.algorithms.detection.SourceDetectionTask`
**Purpose:** Identify contiguous regions (footprints) containing sources

### 4.1 Detection Threshold

#### config.detection.thresholdValue
- **Type:** float (RangeField)
- **Default:** 5.0
- **Valid range:** [0.0, inf)
- **Units:** Depends on thresholdType (typically sigma)
- **Description:** Detection significance threshold
- **Typical range:** [3.0, 10.0]

#### config.detection.thresholdType
- **Type:** str (ChoiceField)
- **Default:** 'pixel_stdev'
- **Valid values:**
  - **'pixel_stdev':** Per-pixel standard deviation (recommended)
  - **'stdev':** Global image standard deviation
  - **'variance':** Image variance
  - **'value':** Direct pixel value
- **Description:** Statistical method for threshold interpretation

#### config.detection.thresholdPolarity
- **Type:** str (ChoiceField)
- **Default:** 'positive'
- **Valid values:**
  - **'positive':** Detect sources brighter than background
  - **'negative':** Detect sources darker than background
  - **'both':** Detect both positive and negative
- **Description:** Source polarity to detect

### 4.2 Footprint Morphology

#### config.detection.minPixels
- **Type:** int (RangeField)
- **Default:** 1
- **Valid range:** [0, inf)
- **Description:** Minimum pixels in a footprint (reject smaller)
- **Purpose:** Filter noise spikes vs. real sources

#### config.detection.nSigmaToGrow
- **Type:** float
- **Default:** 2.4
- **Valid range:** [0, inf)
- **Units:** PSF sigma (RMS width)
- **Description:** Expand footprints by N × PSF_sigma
- **Purpose:** Capture full PSF extent including wings

#### config.detection.isotropicGrow
- **Type:** bool
- **Default:** False
- **Description:** Use isotropic (circular) vs. anisotropic (diamond) growing
- **False:** Manhattan metric (faster)
- **True:** Circular metric (more accurate)

### 4.3 Background Estimation

#### config.detection.reEstimateBackground
- **Type:** bool
- **Default:** False
- **Description:** Iteratively improve background by masking detected sources

#### config.detection.doTempLocalBackground
- **Type:** bool
- **Default:** False
- **Description:** Subtract temporary local background before detection

#### config.detection.background.binSize
- **Type:** int (RangeField)
- **Default:** 128
- **Valid range:** [1, inf)
- **Units:** pixels
- **Description:** Size of background estimation mesh

#### config.detection.background.algorithm
- **Type:** str (ChoiceField)
- **Default:** 'AKIMA_SPLINE'
- **Valid values:**
  - **'CONSTANT':** Single constant value
  - **'LINEAR':** Linear interpolation
  - **'NATURAL_SPLINE':** Cubic spline
  - **'AKIMA_SPLINE':** Robust nonlinear spline (recommended)
- **Description:** Background interpolation method

#### config.detection.background.statisticsProperty
- **Type:** str (ChoiceField)
- **Default:** 'MEANCLIP'
- **Valid values:**
  - **'MEANCLIP':** Iteratively clipped mean (recommended)
  - **'MEAN':** Arithmetic mean
  - **'MEDIAN':** Median (most robust)
- **Description:** Statistic computed per background grid cell

---

## 5. PSF Measurement Parameters

**Task:** `lsst.pipe.tasks.measurePsf.MeasurePsfTask`
**Purpose:** Determine Point Spread Function model from stellar sources

### 5.1 Star Selection

#### config.measurePsf.starSelector
- **Type:** RegistryField (single-selection)
- **Default:** 'objectSize'
- **Description:** Algorithm for selecting PSF candidate stars

### 5.2 ObjectSize Star Selector

**Active when:** `config.measurePsf.starSelector.name = 'objectSize'`

#### config.measurePsf.starSelector["objectSize"].sourceFluxField
- **Type:** str
- **Default:** 'base_GaussianFlux_instFlux'
- **Description:** Flux field for magnitude calculation
- **Common values:** 'base_GaussianFlux_instFlux', 'base_PsfFlux_instFlux'

#### config.measurePsf.starSelector["objectSize"].widthStdAllowed
- **Type:** float
- **Default:** 0.15
- **Valid range:** [0.0, 1.0]
- **Description:** Fractional width standard deviation allowed around stellar locus
- **Tighter (0.10):** Pure stellar sample, fewer stars
- **Looser (0.20):** More stars, possible galaxy contamination

#### config.measurePsf.starSelector["objectSize"].fluxMin
- **Type:** float
- **Default:** 12500.0
- **Units:** Counts
- **Valid range:** [0, inf)
- **Description:** Minimum flux for PSF candidate

#### config.measurePsf.starSelector["objectSize"].fluxMax
- **Type:** float
- **Default:** 0.0 (no maximum)
- **Units:** Counts
- **Description:** Maximum flux for PSF candidate; 0 = no limit

#### config.measurePsf.starSelector["objectSize"].doSignalToNoise
- **Type:** bool
- **Default:** True
- **Description:** Apply signal-to-noise cut

#### config.measurePsf.starSelector["objectSize"].signalToNoiseMin
- **Type:** float
- **Default:** 20.0
- **Valid range:** [0, inf)
- **Description:** Minimum S/N for PSF candidates
- **Typical range:** [10.0, 100.0]

### 5.3 Science Star Selector

**Active when:** `config.measurePsf.starSelector.name = 'science'` or used in astrometry

#### config.astrometry.sourceSelector["science"].doSignalToNoise
- **Type:** bool
- **Default:** True
- **Description:** Apply S/N cut

#### config.astrometry.sourceSelector["science"].signalToNoiseMin
- **Type:** float
- **Default:** 10.0
- **Valid range:** [0, inf)
- **Description:** Minimum signal-to-noise ratio

#### config.astrometry.sourceSelector["science"].doFlags
- **Type:** bool
- **Default:** True
- **Description:** Apply flag-based filtering (exclude bad sources)

#### config.astrometry.sourceSelector["science"].doUnresolved
- **Type:** bool
- **Default:** True
- **Description:** Select only unresolved (point-like) sources

### 5.4 PSF Determiner

#### config.measurePsf.psfDeterminer
- **Type:** RegistryField (single-selection)
- **Default:** 'psfex'
- **Description:** Algorithm for constructing PSF model

### 5.5 PSFEx PSF Determiner

**Active when:** `config.measurePsf.psfDeterminer.name = 'psfex'`
**Algorithm:** PSFEx (Bertin 2011) with spatially-varying basis functions

#### config.measurePsf.psfDeterminer['psfex'].spatialOrder
- **Type:** int
- **Default:** 2
- **Valid range:** [0, 6]
- **Description:** Polynomial order for spatial PSF variation
- **Values:**
  - **0:** Constant PSF across field
  - **1:** Linear variation
  - **2:** Quadratic variation (standard)
  - **3-4:** Higher-order for complex aberrations
  - **5-6:** Very high-order (risk of overfitting)
- **Typical range:** [0, 3]

#### config.measurePsf.psfDeterminer['psfex'].samplingSize
- **Type:** float
- **Default:** 0.5
- **Valid range:** [0.1, 1.0]
- **Description:** PSF model pixels per image pixel
- **0.5:** 2× oversampling (standard)
- **1.0:** Match image sampling

#### config.measurePsf.psfDeterminer['psfex'].sizeCellX
- **Type:** int
- **Default:** 256
- **Valid range:** [16, 1024]
- **Units:** pixels
- **Description:** Cell width for PSF spatial estimation

#### config.measurePsf.psfDeterminer['psfex'].sizeCellY
- **Type:** int
- **Default:** 256
- **Valid range:** [16, 1024]
- **Units:** pixels
- **Description:** Cell height for PSF spatial estimation

#### config.measurePsf.psfDeterminer['psfex'].maxCandidates
- **Type:** int
- **Default:** 300
- **Valid range:** [10, 10000]
- **Description:** Maximum PSF stars to use (downsamples if more available)
- **Typical range:** [50, 500]

#### config.measurePsf.psfDeterminer['psfex'].spatialReject
- **Type:** float
- **Default:** 3.0
- **Valid range:** [0, inf)
- **Units:** standard deviations
- **Description:** Outlier rejection threshold for PSF stars
- **Typical range:** [2.0, 5.0]

#### config.measurePsf.psfDeterminer['psfex'].tolerance
- **Type:** float
- **Default:** 0.01
- **Valid range:** [1e-6, 1.0]
- **Description:** Convergence tolerance for PSF fitting

#### config.measurePsf.psfDeterminer['psfex'].recentroid
- **Type:** bool
- **Default:** False
- **Description:** Allow PSFEx to recentroid star positions

#### config.measurePsf.psfDeterminer['psfex'].psfexBasis
- **Type:** str (ChoiceField)
- **Default:** 'PIXEL_AUTO'
- **Valid values:**
  - **'PIXEL':** Always use specified samplingSize
  - **'PIXEL_AUTO':** Adaptive based on FWHM
- **Description:** PSF basis function sampling control

#### config.measurePsf.psfDeterminer['psfex'].badMaskBits
- **Type:** List of str
- **Default:** ['INTRP', 'SAT']
- **Description:** Mask planes causing PSF candidate rejection
- **Common values:** 'INTRP', 'SAT', 'CR', 'BAD', 'EDGE'

#### config.measurePsf.psfDeterminer['psfex'].numPatternConsensus
- **Type:** int
- **Default:** 2
- **Valid range:** [1, 5]
- **Description:** Consensus patterns required (advanced)

---

## 6. Astrometry Parameters

**Task:** `lsst.meas.astrom.astrometry.AstrometryTask`
**Purpose:** Determine World Coordinate System by matching sources to reference catalog

### 6.1 Source Selection

#### config.astrometry.sourceSelector
- **Type:** RegistryField (single-selection)
- **Default:** 'science'
- **Description:** Source selector for astrometric matching

**Configuration:** See Section 5.3 for science selector parameters

### 6.2 Pattern Matcher Configuration

**Task:** `lsst.meas.astrom.matchPessimisticB.MatchPessimisticBTask`
**Algorithm:** Pessimistic Pattern Matcher B

#### config.astrometry.matcher.maxOffsetPix
- **Type:** int (RangeField)
- **Default:** 250
- **Valid range:** [50, 2000] (practical)
- **Units:** pixels
- **Description:** Maximum spatial offset between initial WCS and true positions
- **Performance:** Computation scales as O(maxOffsetPix²)
- **Critical:** Must also set `config.astromRefObjLoader.pixelMargin > maxOffsetPix`

#### config.astrometry.matcher.maxRotationDeg
- **Type:** float (RangeField)
- **Default:** 1.0
- **Valid range:** [0.1, 5.0] (practical)
- **Units:** degrees
- **Description:** Maximum rotation angle error in initial WCS
- **Typical values:**
  - Good tracking: 0.5-1.0°
  - Uncertain: 2.0-3.0°
  - Unknown: 5.0°

#### config.astrometry.matcher.numBrightStars
- **Type:** int
- **Default:** 200
- **Valid range:** [20, 500] (practical)
- **Description:** Number of brightest stars for pattern construction
- **Performance:** Computation scales as O(numBrightStars³)
- **Critical for:** Processing speed
- **Typical values:**
  - Fast: 100 (8× faster than 200)
  - Balanced: 200 (default)
  - Robust: 300-400 (slower but more reliable)

#### config.astrometry.matcher.minMatchDistPixels
- **Type:** float
- **Default:** 1.0
- **Valid range:** [0, inf)
- **Units:** pixels
- **Description:** Distance below which pairs always considered matches during fitting

#### config.astrometry.matcher.minMatchedPairs
- **Type:** int
- **Default:** 30
- **Valid range:** [10, 100] (practical)
- **Description:** Absolute minimum matched pairs required for WCS solution
- **Rule of thumb:** 3-5× number of WCS parameters

#### config.astrometry.matcher.minFracMatchedPairs
- **Type:** float
- **Default:** 0.3
- **Valid range:** [0, 1.0]
- **Description:** Minimum fraction of matches relative to min(N_sources, N_refs)
- **Formula:** Required = max(minMatchedPairs, minFracMatchedPairs × min(N_src, N_ref))

#### config.astrometry.matcher.matcherIterations
- **Type:** int (RangeField)
- **Default:** 5
- **Valid range:** [1, 10]
- **Description:** Number of softening iterations in pattern matcher
- **Typical range:** [3, 7]

#### config.astrometry.matcher.maxRefObjects
- **Type:** int (RangeField)
- **Default:** 65536
- **Absolute maximum:** 65536 (2¹⁶, implementation limit)
- **Description:** Maximum reference catalog objects to use

#### config.astrometry.matcher.numPatternConsensus
- **Type:** int
- **Default:** 3
- **Valid range:** [1, 5]
- **Description:** Independent patterns that must agree before accepting transformation
- **When used:** Only after first iteration fails with sufficient stars

### 6.3 WCS Fitter Configuration

**Task:** `lsst.meas.astrom.fitTanSipWcs.FitTanSipWcsTask`

#### config.astrometry.wcsFitter.order
- **Type:** int (RangeField)
- **Default:** 2
- **Valid range:** [0, 6] (practical: [0, 4])
- **Description:** SIP distortion polynomial order
- **Parameters by order:**
  - 0: 6 parameters (TAN only)
  - 1: 12 parameters
  - 2: 20 parameters
  - 3: 30 parameters
  - 4: 42 parameters
- **Typical range:** [2, 4]

#### config.astrometry.wcsFitter.numIter
- **Type:** int (RangeField)
- **Default:** 3
- **Valid range:** [1, inf)
- **Description:** Fitting iterations (X and Y fit separately)
- **Typical range:** [2, 5]

#### config.astrometry.wcsFitter.rejSigma
- **Type:** float (RangeField)
- **Default:** 3.0
- **Valid range:** [0.0, inf)
- **Units:** standard deviations
- **Description:** Outlier clipping threshold during WCS fitting
- **Typical range:** [2.0, 5.0]

#### config.astrometry.wcsFitter.maxScatterArcsec
- **Type:** float (RangeField)
- **Default:** 10.0
- **Valid range:** [0, inf)
- **Units:** arcseconds
- **Description:** Maximum median scatter; fit fails if exceeded

### 6.4 Astrometry Iteration Control

#### config.astrometry.maxIter
- **Type:** int (RangeField)
- **Default:** 3
- **Valid range:** [1, inf)
- **Description:** Maximum match-fit-rematch iterations

#### config.astrometry.matchDistanceSigma
- **Type:** float (RangeField)
- **Default:** 2.0
- **Valid range:** [0, inf)
- **Description:** Adaptive matching radius = mean + matchDistanceSigma × std

#### config.astrometry.maxMeanDistanceArcsec
- **Type:** float (RangeField)
- **Default:** 0.5
- **Valid range:** [0, inf)
- **Units:** arcseconds
- **Description:** Maximum mean on-sky distance; exceeding raises BadAstrometryFit

### 6.5 Reference Catalog Loader

#### config.astromRefObjLoader.pixelMargin
- **Type:** int
- **Default:** 300
- **Units:** pixels
- **Description:** Buffer pixels when loading reference catalog
- **Critical:** Must be > maxOffsetPix

---

## 7. Photometry Parameters

**Task:** `lsst.pipe.tasks.photoCal.PhotoCalTask`
**Purpose:** Determine magnitude zero point by matching to reference catalog

### 7.1 Core Configuration

#### config.photoCal.fluxField
- **Type:** str
- **Default:** 'slot_CalibFlux_instFlux'
- **Description:** Flux measurement field for calibration
- **Common values:**
  - 'slot_CalibFlux_instFlux' (typically aperture flux)
  - 'base_PsfFlux_instFlux'
  - 'base_CircularApertureFlux_X_X_instFlux'

#### config.photoCal.applyColorTerms
- **Type:** bool
- **Default:** True
- **Description:** Apply color term corrections to reference stars

#### config.photoCal.magErrFloor
- **Type:** float
- **Default:** 0.0
- **Valid range:** [0.0, inf)
- **Units:** magnitudes
- **Description:** Systematic magnitude uncertainty floor
- **Typical range:** [0.0, 0.02]

### 7.2 Iterative Fitting

#### config.photoCal.nIter
- **Type:** int
- **Default:** 3
- **Valid range:** [1, 10]
- **Description:** Sigma-clipping iterations for zero point fitting

#### config.photoCal.nSigma
- **Type:** float
- **Default:** 3.0
- **Valid range:** [1.0, 10.0]
- **Units:** standard deviations
- **Description:** Outlier rejection threshold

#### config.photoCal.useMedian
- **Type:** bool
- **Default:** True
- **Description:** Use median (vs. mean) for zero point
- **Recommended:** True (more robust to outliers)

### 7.3 Color Terms Configuration

**config.photoCal.colorterms**
- **Type:** ConfigDictField
- **Data type:** `lsst.pipe.tasks.colorterms.ColortermLibrary`
- **Description:** Library mapping reference catalogs to color term dictionaries

**Colorterm object parameters:**
- **primary:** Primary filter name (str)
- **secondary:** Secondary filter for color (str)
- **c0:** Zero-point offset (float)
- **c1:** Linear color term coefficient (float)
- **c2:** Quadratic color term coefficient (float)
- **Equation:** mag_obs = mag_ref + c0 + c1×(primary-secondary) + c2×(primary-secondary)²

---

## 8. Measurement Parameters

**Task:** `lsst.meas.base.sfm.SingleFrameMeasurementTask`
**Purpose:** Extract photometric and morphological properties from sources

### 8.1 Measurement Plugins

#### config.measurement.plugins
- **Type:** RegistryInstanceDict
- **Default plugins:** ['base_PixelFlags', 'base_SdssCentroid', 'base_SdssShape', 'base_GaussianFlux', 'base_PsfFlux', 'base_CircularApertureFlux', 'base_SkyCoord', 'base_Variance', 'base_Blendedness', 'base_LocalBackground']

### 8.2 Critical Plugins

#### base_PsfFlux (PSF Photometry)
**config.measurement.plugins['base_PsfFlux'].badMaskPlanes**
- **Type:** List of str
- **Default:** ['BAD', 'SAT', 'INTRP', 'NO_DATA']
- **Description:** Mask planes to exclude from PSF fit

#### base_CircularApertureFlux (Aperture Photometry)
**config.measurement.plugins['base_CircularApertureFlux'].radii**
- **Type:** List of float
- **Default:** [3.0, 4.5, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0]
- **Units:** pixels
- **Description:** Aperture radii for flux measurement

**config.measurement.plugins['base_CircularApertureFlux'].maxSincRadius**
- **Type:** float
- **Default:** 10.0
- **Units:** pixels
- **Description:** Maximum radius for sinc interpolation

#### base_SdssShape (Shape Measurement)
**config.measurement.plugins['base_SdssShape'].maxShift**
- **Type:** float
- **Default:** 0.0
- **Description:** Maximum centroid shift during shape fitting

### 8.3 Measurement Slots

**Purpose:** Map algorithm results to standard catalog fields

#### config.measurement.slots.calibFlux
- **Type:** str
- **Default:** 'base_CircularApertureFlux_12_0'
- **Description:** Flux for calibration

#### config.measurement.slots.psfFlux
- **Type:** str
- **Default:** 'base_PsfFlux'
- **Description:** PSF flux measurement

#### config.measurement.slots.centroid
- **Type:** str
- **Default:** 'base_SdssCentroid'
- **Description:** Centroid algorithm

#### config.measurement.slots.shape
- **Type:** str
- **Default:** 'base_SdssShape'
- **Description:** Shape measurement algorithm

### 8.4 Aperture Correction

**Task:** `lsst.meas.algorithms.measureApCorr.MeasureApCorrTask`

#### config.measureApCorr.sourceSelector
- **Type:** RegistryField
- **Default:** 'science'
- **Description:** Selector for aperture correction stars

#### config.measureApCorr.numIter
- **Type:** int
- **Default:** 4
- **Description:** Robust sigma-clipping iterations

#### config.measureApCorr.numSigmaClip
- **Type:** float
- **Default:** 3.0
- **Description:** Sigma threshold for clipping

#### config.measureApCorr.refFluxName
- **Type:** str
- **Default:** 'slot_CalibFlux'
- **Description:** Reference flux for aperture correction

---

## 9. Additional Tasks

### 9.1 Cosmic Ray Rejection

**Task:** `lsst.pipe.tasks.repair.RepairTask`

#### config.repair.doCosmicRay
- **Type:** bool
- **Default:** True
- **Description:** Find and mask cosmic rays

#### config.repair.cosmicray.minSigma
- **Type:** float
- **Default:** 6.0
- **Valid range:** [3.0, 10.0]
- **Units:** sigma
- **Description:** Detection threshold for cosmic rays

#### config.repair.cosmicray.minNumPixels
- **Type:** int
- **Default:** 1
- **Description:** Minimum pixels in cosmic ray

#### config.repair.cosmicray.niteration
- **Type:** int
- **Default:** 3
- **Valid range:** [1, 5]
- **Description:** CR detection iterations

### 9.2 Deblending

**Task:** `lsst.meas.deblender.sourceDeblendTask.SourceDeblendTask`

#### config.doDeblend
- **Type:** bool
- **Default:** True
- **Description:** Separate blended sources

### 9.3 Top-Level Control

#### config.doAstrometry
- **Type:** bool
- **Default:** True
- **Description:** Perform astrometric calibration

#### config.doPhotoCal
- **Type:** bool
- **Default:** True
- **Description:** Perform photometric calibration

#### config.requireAstrometry
- **Type:** bool
- **Default:** True
- **Description:** Raise exception if astrometry fails

#### config.requirePhotoCal
- **Type:** bool
- **Default:** True
- **Description:** Raise exception if photometry fails

---

## Quick Reference: Key Parameters by Priority

### Critical (Must Tune)
1. `config.detection.thresholdValue` - Controls catalog completeness
2. `config.astrometry.matcher.maxOffsetPix` - Critical for matching success
3. `config.astrometry.matcher.numBrightStars` - Balances speed/robustness
4. `config.measurePsf.psfDeterminer['psfex'].spatialOrder` - PSF quality

### High Priority
5. `config.detection.background.binSize` - Background model scale
6. `config.measurePsf.starSelector["objectSize"].signalToNoiseMin` - PSF star quality
7. `config.astrometry.matcher.minMatchedPairs` - Solution robustness
8. `config.astrometry.wcsFitter.order` - Distortion accuracy

### Medium Priority
9. `config.detection.nSigmaToGrow` - Detection completeness
10. `config.measurePsf.psfDeterminer['psfex'].maxCandidates` - PSF sampling
11. `config.astrometry.matcher.matcherIterations` - Matching robustness
12. `config.isr.fwhm` - Interpolation quality

### Lower Priority (Fine-Tuning)
13. `config.detection.minPixels` - Noise filtering
14. `config.astrometry.wcsFitter.rejSigma` - Outlier rejection
15. `config.photoCal.nSigma` - Photometric outliers
16. `config.measurePsf.psfDeterminer['psfex'].spatialReject` - PSF outliers

---

## Documentation Resources

**Primary References:**
- LSST Science Pipelines: https://pipelines.lsst.io
- Configuration System: https://pipelines.lsst.io/modules/lsst.pex.config/
- Task Framework: https://pipelines.lsst.io/modules/lsst.pipe.base/

**GitHub Repositories:**
- ISR: https://github.com/lsst/ip_isr
- Detection: https://github.com/lsst/meas_algorithms
- PSF: https://github.com/lsst/meas_extensions_psfex
- Astrometry: https://github.com/lsst/meas_astrom
- Photometry: https://github.com/lsst/pipe_tasks

**Community:**
- LSST Community Forum: https://community.lsst.org
- Configuration Examples: https://github.com/lsst/obs_lsst/tree/main/config
