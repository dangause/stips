# LSST Science Pipelines Configuration Reference: ISR and CalibrateImage Parameters

This comprehensive reference catalogs all tunable configuration parameters for the LSST Science Pipelines Instrument Signature Removal (ISR) and calibrateImage pipeline tasks, with detailed explanations of pipeline architecture, parameter interactions, and optimization strategies for telescope data processing.

**Primary Documentation:** https://pipelines.lsst.io
**GitHub Repository:** https://github.com/lsst/pipe_tasks

## Table of Contents

1. [Pipeline Architecture and Flow](#1-pipeline-architecture-and-flow)
2. [Configuration System Overview](#2-configuration-system-overview)
3. [ISR Task Parameters](#3-isr-instrument-signature-removal-task-parameters)
4. [Detection Parameters](#4-detection-parameters)
5. [PSF Measurement Parameters](#5-psf-measurement-parameters)
6. [Astrometry Parameters](#6-astrometry-parameters)
7. [Photometry Parameters](#7-photometry-parameters)
8. [Measurement Algorithms](#8-measurement-algorithms)
9. [Other CalibrateImage Components](#9-other-calibrateimage-components)
10. [Parameter Interaction Guide](#10-parameter-interaction-guide)
11. [Parameter Grid Examples](#11-parameter-grid-examples)

---

## 1. Pipeline Architecture and Flow

### 1.1 The Complete Processing Chain

The LSST Science Pipelines process raw CCD images through a sequence of interconnected tasks, each building upon the results of previous steps. Understanding this flow is critical for effective parameter optimization.

**Processing Sequence:**

```
RAW IMAGE
    ↓
[1] ISR (Instrument Signature Removal)
    ├─ Removes instrumental artifacts
    ├─ Applies calibration frames (bias, dark, flat)
    └─ Produces: Calibrated image + variance plane + mask plane
    ↓
[2] CHARACTERIZE IMAGE (Detection + PSF)
    ├─ Background subtraction
    ├─ Source detection (initial)
    ├─ PSF measurement from stars
    └─ Produces: Initial source catalog + PSF model + background model
    ↓
[3] CALIBRATE IMAGE (Astrometry + Photometry + Final Measurement)
    ├─ Astrometry: Match sources to reference catalog → WCS
    ├─ Photometry: Calibrate fluxes to reference magnitudes → Zero point
    ├─ Detection: Re-detect with better background model
    ├─ Measurement: Measure all source properties
    ├─ Deblending: Separate overlapping sources
    └─ Produces: Final calibrated catalog with positions, fluxes, shapes
    ↓
CALIBRATED IMAGE + SOURCE CATALOG
```

### 1.2 Task Dependencies and Data Flow

**Critical Understanding:** Each stage depends on the quality of previous stages. A failure or poor performance in an early stage cascades through the entire pipeline.

**Key Dependencies:**

1. **ISR → Everything Else**
   - Poor ISR (bad flat fielding, unmasked defects) → False detections → Poor PSF measurement → Failed astrometry
   - Good ISR is the foundation of all downstream processing

2. **Detection → PSF → Astrometry → Photometry**
   - Detection finds sources → PSF uses clean stars → Astrometry matches sources → Photometry calibrates fluxes
   - Each step refines the results of the previous step

3. **PSF Model → Measurement Quality**
   - PSF is used for: star/galaxy separation, deblending, PSF photometry, shape measurement
   - A poor PSF model degrades ALL measurements, not just PSF photometry

4. **Astrometry → Photometry**
   - Astrometry provides source positions → Used to match photometric reference stars
   - Failed astrometry = no photometric calibration possible

### 1.3 Feedback Loops and Iterations

The pipeline includes several **iterative refinement loops**:

**Detection → Background → Detection Loop:**
- Initial detection with approximate background
- Mask detected sources, re-estimate background
- Re-detect with improved background model
- *Why:* Sources contaminate background estimation; iteration improves both

**PSF Measurement Iteration:**
- Select candidate stars
- Measure preliminary PSF
- Reject outliers (non-stars, bad pixels)
- Re-measure PSF with cleaned star sample
- *Why:* Initial star selection may include galaxies or artifacts

**Astrometry Matching Iteration:**
- Initial pattern match with large tolerances
- Fit WCS, identify outliers
- Re-match with tighter constraints using improved WCS
- Repeat until convergence
- *Why:* Better WCS enables identifying more matches and excluding false matches

**Understanding these iterations is crucial:** Parameters control how aggressive each iteration is. Too strict → fails to converge; too loose → accepts bad data.

### 1.4 Critical Decision Points

Throughout the pipeline, there are **critical decision points** where parameter choices have outsized impact:

**1. Detection Threshold (config.detection.thresholdValue)**
   - **Impact:** Sets the catalog completeness/purity tradeoff for ALL downstream processing
   - **Cascading Effect:**
     - Too low → Excess false detections contaminate PSF star selection
     - Too high → Miss faint stars needed for PSF spatial sampling

**2. PSF Spatial Order (config.measurePsf.psfDeterminer["psfex"].spatialOrder)**
   - **Impact:** Determines if PSF variations across the field are modeled
   - **Cascading Effect:**
     - Too low → PSF mismatch at field edges → poor photometry and star/galaxy separation
     - Too high → Overfitting → PSF noise → unstable measurements

**3. Astrometry Match Tolerance (config.astrometry.matcher.maxOffsetPix)**
   - **Impact:** Determines whether initial pattern matching succeeds
   - **Cascading Effect:**
     - Too small → Complete astrometry failure → no photometry → unusable data
     - Too large → Slow processing + false matches → poor WCS

**4. Number of Bright Stars (config.astrometry.matcher.numBrightStars)**
   - **Impact:** Computation time scales as O(N³)
   - **Cascading Effect:**
     - Too few → Matching fails in complex fields
     - Too many → Processing time explodes (minutes → hours per image)

### 1.5 Parameter Adjustment Philosophy

**General Principles:**

**Start Conservative, Then Optimize:**
1. Begin with permissive parameters that ensure processing completes
2. Measure performance (astrometric RMS, photometric scatter, processing time)
3. Systematically tighten parameters to improve quality
4. Stop when quality plateaus or failure rate increases

**Early-Stage Parameters Are Critical:**
- ISR and detection parameters affect everything downstream
- Optimize these FIRST before tuning later stages
- Example: No amount of astrometry tuning fixes poor detection

**Processing Speed vs. Quality Tradeoffs:**
- Many parameters trade computation time for accuracy
- Identify your bottleneck: Is processing time or data quality limiting?
- For Nickel telescope: Processing 1000s of images → speed matters
- For precise science: Processing 10s of images → maximize quality

**Field Diversity Considerations:**
- Parameters optimized for one field type (sparse, crowded, galaxy-rich) may fail elsewhere
- Test parameter sets across diverse fields (low/high Galactic latitude, different crowding)
- Consider field-dependent configuration if necessary

---

## 2. Configuration System Overview

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

## 3. ISR (Instrument Signature Removal) Task Parameters

**Task:** `lsst.ip.isr.IsrTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.ip.isr/index.html
**API Reference:** https://pipelines.lsst.io/v/daily/py-api/lsst.ip.isr.IsrTask.html

### 3.1 What ISR Does and Why It Matters

**Purpose:** ISR removes instrumental signatures from raw CCD images to produce calibrated science-grade images. It's the **foundation** of all subsequent processing.

**What ISR Corrects:**
1. **Electronic signatures:** Bias pedestal, dark current, read noise
2. **Optical signatures:** Pixel-to-pixel sensitivity variations (flat field)
3. **Physical defects:** Bad pixels, cosmic rays, saturation
4. **Detector artifacts:** Non-linearity, crosstalk, charge persistence

**Why ISR Parameter Tuning Matters:**
- **Incomplete corrections** → Systematic photometric errors, false detections
- **Over-aggressive masking** → Loss of science data in wings of bright sources
- **Poor interpolation** → Artifacts mistaken for sources
- **Incorrect variance estimation** → Wrong source detection thresholds

**Downstream Impact:**
- Bad ISR → Background estimation fails → Detection finds artifacts as sources
- Bad ISR → PSF measurement uses contaminated stars → Poor PSF model
- Bad ISR → Astrometry uses false sources → Failed WCS solution

### 3.2 ISR Processing Order (Critical!)

ISR corrections are applied in a **specific order** to maintain reproducibility and correctness:

```
1. Saturation and suspect pixel masking    [Identify problems]
2. Overscan subtraction                     [Remove bias level]
3. CCD assembly (combining amplifiers)      [Build full detector image]
4. Bias subtraction                         [Remove systematic offset]
5. Variance plane construction              [Build noise model]
6. Linearization                            [Correct response curve]
7. Crosstalk correction                     [Remove inter-amp ghosts]
8. Brighter-fatter correction               [Correct charge distribution]
9. Dark subtraction                         [Remove thermal signal]
10. Deferred charge (CTI) correction        [Correct charge traps]
11. Flat fielding                           [Normalize pixel response]
12. Fringe correction                       [Remove interference patterns]
13. Defect masking and interpolation        [Fix known bad regions]
```

**Why Order Matters:**
- Bias must be subtracted before measuring dark current
- Flat field applied to fully calibrated electrons (after linearization, dark)
- Defect interpolation done last to use fully corrected surrounding pixels

### 3.3 Core Processing Control

#### config.doOverscan
- **Type:** bool
- **Default:** True
- **What it does:** Subtracts the bias pedestal measured from the overscan region (non-illuminated pixels read out after each row)
- **When to disable:** Only if overscan region is corrupted or unreliable
- **Impact on downstream:** Failure to subtract overscan → constant offset in all pixels → biased photometry
- **Adjustment strategy:** Almost always True unless detector-specific issues

#### config.doBias
- **Type:** bool
- **Default:** True
- **What it does:** Subtracts master bias frame to remove pixel-to-pixel bias structure remaining after overscan
- **When to disable:** Only when constructing the master bias itself
- **Impact on downstream:** No bias correction → structure in "empty" pixels → false detections
- **Interaction:** Works with doOverscan (overscan removes mean, bias removes structure)

#### config.doDark
- **Type:** bool
- **Default:** True
- **What it does:** Subtracts dark current (thermal electrons accumulated during exposure)
- **When to adjust:**
  - **Enable:** For long exposures (>10s) or warm CCDs
  - **Disable:** For very short exposures where dark current is negligible
- **Impact on downstream:** No dark correction → excess "flux" in all pixels → photometric bias, especially for faint sources
- **Scaling consideration:** Dark scales with exposure time; ISR automatically scales dark frame

#### config.doFlat
- **Type:** bool
- **Default:** True
- **What it does:** Divides by flat field to correct pixel-to-pixel response variations
- **When to disable:** Never for science images (only when constructing flats)
- **Impact on downstream:**
  - No flat → 10-30% pixel-to-pixel variations → photometric errors
  - No flat → Dust shadows appear as sources
- **Critical for:** Photometry, aperture corrections, background estimation
- **Quality check:** Poor flat fielding is often the dominant photometric systematic

#### config.doLinearize
- **Type:** bool
- **Default:** True
- **What it does:** Corrects for detector non-linearity (deviation from linear photon count ↔ ADU relationship)
- **When matters most:** High signal levels (>50% full well)
- **Impact on downstream:**
  - No linearization → Photometry of bright sources systematically low
  - → Poor PSF measurement if using bright stars
  - → Incorrect aperture corrections
- **Typical non-linearity:** 1-10% at high counts depending on detector

#### config.doFringe
- **Type:** bool
- **Default:** True
- **What it does:** Removes fringe patterns from thin-film interference in red/IR filters
- **When to adjust:**
  - **Enable:** For i, z, y bands (fringe amplitudes ~1-5%)
  - **Disable:** For u, g, r bands (negligible fringing)
- **Impact on downstream:**
  - No fringe correction → Periodic pattern across image → False extended source detections
  - Over-aggressive fringe correction → Remove real large-scale structure
- **Quality indicator:** Residual fringing visible as ripple pattern in background-subtracted images

### 3.4 How to Adjust ISR Parameters

**Diagnostic Approach:**

**1. Check ISR Quality:**
```python
# After ISR, examine:
- Background level should be near zero (±few counts)
- Sky variance should match expected Poisson + read noise
- No obvious structured residuals in background-subtracted image
- Bright stars should have smooth profiles
```

**2. Identify Problems:**
- **High background in specific regions:** Check flat field quality
- **Ripple patterns:** Enable/tune fringe correction
- **False detections near bright stars:** Adjust saturation growing or bright-fatter
- **Bad columns appearing as sources:** Enable defect masking

**3. Parameter Adjustment Strategy:**

**For Saturation Issues:**
```python
# If missing saturated regions:
config.isr.growSaturationFootprintSize = 2  # Grow by 2 pixels
# Too aggressive saturation masking:
config.isr.saturation = 50000  # Increase threshold (if detector spec allows)
```

**For Interpolation Quality:**
```python
# Interpolation kernel size based on PSF:
config.isr.fwhm = 1.2  # Match actual seeing FWHM in arcsec
# If seeing varies greatly, use conservative (larger) value
```

**For Fringe Correction:**
```python
# Red/IR bands with fringing:
config.isr.doFringe = True
# Blue bands without fringing:
config.isr.doFringe = False  # Saves processing time
```

### 3.5 Advanced Corrections

#### config.doCrosstalk
- **Type:** bool
- **Default:** False
- **What it does:** Removes electronic crosstalk (ghost images from bright sources appearing in other amplifiers)
- **How it works:** Applies crosstalk matrix measured during detector characterization
- **When to enable:**
  - Detector has known crosstalk >0.1%
  - Have accurate crosstalk matrix
  - Processing images with very bright sources
- **Impact on downstream:**
  - Without correction: Ghost sources near bright stars → contaminate PSF measurement
  - With correction: Cleaner photometry near bright sources
- **Computational cost:** Moderate (one matrix multiply per amplifier pair)

#### config.doBrighterFatter
- **Type:** bool
- **Default:** False
- **What it does:** Corrects charge redistribution in deep potential wells (brighter sources appear larger/"fatter")
- **Physical mechanism:** Charge repulsion flattens potential wells → lateral charge spreading
- **When to enable:**
  - Precision photometry or astrometry required
  - Working with bright sources (>10,000 e-)
  - Have BF correction kernel
- **Impact on downstream:**
  - Without correction: Systematic PSF size increase with brightness → biased star/galaxy separation
  - With correction: More accurate PSF model → better measurements
- **Computational cost:** High (iterative correction)

**Related Parameters:**

**config.brighterFatterLevel**
- **Default:** 'DETECTOR'
- **What it controls:** Spatial scale of correction application
- **Values:**
  - **'AMP':** Apply per-amplifier (if amplifiers have different behavior)
  - **'DETECTOR':** Apply per-detector (standard)
- **When to adjust:** Only if characterization shows per-amp differences

**config.brighterFatterMaxIter** / **config.brighterFatterThreshold**
- **What they control:** Convergence criteria for iterative BF correction
- **Adjustment:**
  - Faster convergence: Increase threshold or decrease maxIter
  - More accuracy: Decrease threshold or increase maxIter
- **Typical:** 10 iterations with threshold 1000 is good balance

#### config.doDeferredCharge
- **Type:** bool
- **Default:** False
- **What it does:** Corrects charge transfer inefficiency (CTI) from traps in CCD
- **Physical mechanism:** Traps capture and release charges → trailing
- **When to enable:**
  - Detector shows significant charge trailing
  - Have CTI correction model
  - Precision photometry needed
- **Impact:** Corrects systematic trailing behind sources

### 3.6 Masking and Interpolation Strategy

**Purpose:** Identify bad regions and replace with interpolated values to prevent contaminating measurements.

#### config.doSaturation
- **Default:** True
- **What it does:** Identifies pixels above saturation threshold and sets SAT mask bit
- **Why it's critical:** Saturated pixels have non-linear response → unreliable flux measurements
- **Downstream impact:**
  - Saturated pixels excluded from PSF measurement
  - Saturated sources flagged in catalog
  - Enables growing saturation regions to mask charge bleed

**config.growSaturationFootprintSize**
- **Default:** 1
- **What it does:** Expands saturation mask by N pixels in all directions
- **Why needed:** Saturation causes charge bleeding → contaminate adjacent pixels
- **Adjustment strategy:**
  ```
  # Conservative (avoid false detections near bright stars):
  growSaturationFootprintSize = 3

  # Aggressive (maximize useful area, risk contamination):
  growSaturationFootprintSize = 0

  # Standard balanced:
  growSaturationFootprintSize = 1
  ```
- **Tradeoff:** Larger values = more reliable but lose more science area

#### config.doDefect
- **Default:** True
- **What it does:** Masks known bad pixels, columns, regions from defect lists
- **Sources:** Hot pixels, dead pixels, bad columns identified during detector characterization
- **Why critical:** Defects appear as sources or systematic photometric errors
- **Maintenance:** Defect lists should be updated regularly as detector ages

#### config.doInterpolate
- **Default:** True
- **What it does:** Replaces masked pixels with interpolated values from surrounding good pixels
- **Method:** Uses PSF-shaped kernel for interpolation
- **When to enable:** Almost always for science processing
- **Impact:**
  - Prevents masked regions from appearing as holes in images
  - Allows measurements near masked pixels
  - Enables background estimation across masked regions

**config.maskListToInterpolate**
- **Default:** ['SAT', 'BAD']
- **What it controls:** Which mask planes trigger interpolation
- **Common values:**
  - **'SAT':** Saturated pixels (almost always interpolate)
  - **'BAD':** Known bad pixels (almost always interpolate)
  - **'CR':** Cosmic rays (usually interpolate)
  - **'INTRP':** Previously interpolated (usually DON'T interpolate again)
- **Adjustment strategy:**
  ```python
  # Minimal (only worst defects):
  config.isr.maskListToInterpolate = ['SAT', 'BAD']

  # Include cosmic rays:
  config.isr.maskListToInterpolate = ['SAT', 'BAD', 'CR']

  # Aggressive (may over-interpolate):
  config.isr.maskListToInterpolate = ['SAT', 'BAD', 'CR', 'UNMASKEDNAN']
  ```

**config.fwhm**
- **Default:** 1.0
- **Units:** arcseconds
- **What it does:** Sets interpolation kernel size (should match expected PSF FWHM)
- **Why it matters:**
  - Too small: Interpolation doesn't capture PSF wings → sharp edges
  - Too large: Over-smoothing → blend nearby sources
- **Adjustment strategy:**
  ```python
  # Good seeing (0.8" FWHM):
  config.isr.fwhm = 0.8

  # Average seeing (1.2" FWHM):
  config.isr.fwhm = 1.2

  # Poor seeing (2.0" FWHM):
  config.isr.fwhm = 2.0

  # Conservative (when unsure):
  config.isr.fwhm = 1.5  # Use larger value to avoid under-smoothing
  ```

### 3.7 ISR Parameter Interaction Summary

**Correction Chain Interactions:**

1. **Bias + Overscan:**
   - Applied sequentially (overscan first, then bias)
   - Both must be enabled for clean zero-point

2. **Linearization + Flat:**
   - Linearization MUST come before flat field
   - Flat field expects linear detector response

3. **Dark + Flat + Fringe:**
   - Dark subtracted before flat (flat field applied to calibrated electrons)
   - Fringe after flat (fringe pattern in calibrated units)

4. **Interpolation + Detection:**
   - Interpolation fills gaps → enables detection near masked regions
   - But interpolated regions have unreliable variance → can cause false detections
   - Solution: Grow masked regions slightly before detection

**Critical ISR Tuning for Nickel Telescope:**

```python
# Starting point for Nickel telescope ISR:

# Core corrections (enable all unless specific issues):
config.isr.doBias = True
config.isr.doDark = True
config.isr.doFlat = True
config.isr.doLinearize = True  # If characterized

# Fringe correction (test per filter):
config.isr.doFringe = True  # For red bands
# Measure: Is background RMS reduced with fringe correction?

# Saturation handling (conservative):
config.isr.growSaturationFootprintSize = 2  # Protect against bleed

# Interpolation (match seeing):
config.isr.fwhm = 1.2  # Typical Nickel seeing
config.isr.maskListToInterpolate = ['SAT', 'BAD', 'CR']

# Advanced corrections (enable if characterized):
config.isr.doCrosstalk = False  # Enable if crosstalk measured
config.isr.doBrighterFatter = False  # Enable for precision work

# Variance estimation (for detection thresholds):
config.isr.doVariance = True  # Essential
```

---

## 4. Detection Parameters

**Task:** `lsst.meas.algorithms.detection.SourceDetectionTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.meas.algorithms/tasks/lsst.meas.algorithms.SourceDetectionTask.html

### 4.1 What Detection Does and Its Critical Role

**Purpose:** Detection identifies contiguous regions (footprints) containing astronomical sources by finding pixels above a threshold relative to the background noise.

**Why Detection is Critical:**
- **Determines catalog completeness:** Sources below detection threshold are lost forever
- **Controls downstream processing load:** More detections = more sources to measure = longer processing
- **Affects ALL subsequent steps:** PSF uses detected sources, astrometry matches detected sources, photometry measures detected sources
- **Sets purity-completeness tradeoff:** Lower threshold = more real sources + more artifacts

**What Detection Produces:**
1. **Footprints:** Contiguous groups of above-threshold pixels
2. **Peaks:** Local maxima within footprints (handles blended sources)
3. **Background model:** Iteratively improved sky background
4. **Metadata:** Detection statistics for quality assessment

**Downstream Dependencies:**
- PSF measurement selects from detected sources
- Astrometry matches detected sources to reference catalog
- Photometry measures fluxes of detected sources
- Deblending separates detected blends

### 4.2 Detection Algorithm Explained

**Step-by-Step Process:**

```
1. BACKGROUND ESTIMATION
   ├─ Divide image into grid (binSize × binSize pixels)
   ├─ Compute statistic (mean/median) per grid cell
   ├─ Interpolate grid → smooth background model
   └─ Subtract background from image

2. THRESHOLD CALCULATION
   ├─ For thresholdType='pixel_stdev':
   │  └─ Calculate per-pixel noise from variance plane
   ├─ threshold_image = thresholdValue × noise_image
   └─ Or use global threshold (older method)

3. FOOTPRINT IDENTIFICATION
   ├─ Find pixels > threshold
   ├─ Group connected pixels into footprints
   ├─ Reject footprints with < minPixels
   └─ Grow footprints by nSigmaToGrow

4. PEAK FINDING
   ├─ Within each footprint, find local maxima
   ├─ Each peak = potential source (for deblending)
   └─ Multiple peaks = blended sources

5. ITERATION (if reEstimateBackground=True)
   ├─ Mask detected footprints
   ├─ Re-estimate background excluding sources
   ├─ Re-detect with improved background
   └─ Repeat until convergence
```

### 4.3 Core Detection Thresholds

#### config.detection.thresholdValue
- **Full Path:** `config.detection.thresholdValue`
- **Type:** float (RangeField)
- **Default:** 5.0
- **Valid Range:** [0.0, inf)
- **Units:** Depends on thresholdType (typically sigma)

**What it does:** Sets the detection significance threshold. With default settings, sources must be 5σ above background to be detected.

**How it works with thresholdType:**
```python
# For thresholdType='pixel_stdev' (recommended):
threshold_at_pixel = thresholdValue × sqrt(variance_at_pixel)
detected = (pixel_value > threshold_at_pixel)

# For thresholdType='stdev' (global):
threshold_everywhere = thresholdValue × image_stdev
detected = (pixel_value > threshold_everywhere)
```

**Impact on Pipeline:**

**Lowering threshold (e.g., 3.0σ):**
- ✅ Detect fainter sources → better completeness
- ✅ More stars for PSF measurement → better spatial sampling
- ⚠️ More false detections from noise → contaminate PSF star selection
- ⚠️ Longer processing time (more sources to measure)
- ⚠️ More blended sources → deblending challenges

**Raising threshold (e.g., 7.0σ):**
- ✅ Fewer false detections → cleaner catalogs
- ✅ Faster processing
- ⚠️ Miss faint sources → incomplete catalogs
- ⚠️ Fewer PSF stars → may fail in sparse fields
- ⚠️ Bias toward bright sources

**Adjustment Strategy:**

```python
# For crowded fields (many stars):
config.detection.thresholdValue = 5.0  # Standard, good S/N
# Reason: Plenty of bright sources, don't need faint ones for PSF

# For sparse fields (few stars):
config.detection.thresholdValue = 3.0  # Lower to get enough sources
# Reason: Need faint sources to have sufficient PSF stars

# For very deep images (low noise):
config.detection.thresholdValue = 7.0  # Higher to manage catalog size
# Reason: So many detections that processing becomes slow

# For shallow images (high noise):
config.detection.thresholdValue = 4.0  # Moderate threshold
# Reason: Balance completeness vs. noise false positives
```

**Quality Checks:**
1. **Visual:** Overlay detections on image - missing obvious sources?
2. **Quantitative:** Compare to known source lists - what's completeness?
3. **False positive rate:** How many detections have PSF = galaxy shape?

#### config.detection.thresholdType
- **Full Path:** `config.detection.thresholdType`
- **Type:** str (ChoiceField)
- **Default:** 'pixel_stdev'

**What it does:** Determines HOW the threshold value is interpreted.

**Options Explained:**

**'pixel_stdev' (RECOMMENDED for modern processing):**
- Uses per-pixel standard deviation from variance plane
- Adapts to spatially varying noise (edges, bright sources, gaps)
- **When to use:** Almost always (requires variance plane from ISR)
- **Advantage:** Optimal detection in variable noise background
- **Example:** Noise is higher near bright stars → threshold automatically raised there

**'stdev' (legacy, global threshold):**
- Uses single threshold = thresholdValue × image_standard_deviation
- Same threshold everywhere in image
- **When to use:** Legacy compatibility, or no variance plane available
- **Disadvantage:** Sub-optimal in regions with unusual noise

**'variance' (direct variance threshold):**
- Threshold = thresholdValue × variance_plane
- Rarely used
- **When to use:** Special cases with unusual variance models

**'value' (direct pixel value threshold):**
- Threshold = thresholdValue (in image units)
- **When to use:** When you know exact count threshold needed

**Recommendation for Nickel Telescope:**
```python
config.detection.thresholdType = 'pixel_stdev'
# Reason: Enables optimal detection with spatially varying noise
# Requires: ISR must produce variance plane (config.isr.doVariance = True)
```

#### config.detection.thresholdPolarity
- **Full Path:** `config.detection.thresholdPolarity`
- **Default:** 'positive'

**What it does:** Determines which sources to detect based on sign.

**Options:**
- **'positive':** Detect sources brighter than background (standard astronomy)
- **'negative':** Detect sources darker than background (difference imaging, artifacts)
- **'both':** Detect both positive and negative sources

**When to adjust:**
```python
# Standard imaging:
config.detection.thresholdPolarity = 'positive'

# Difference imaging (transient detection):
config.detection.thresholdPolarity = 'both'
# Reason: New transients (positive) and disappeared sources (negative)

# Checking for artifacts:
config.detection.thresholdPolarity = 'negative'
# Reason: Over-subtracted regions or processing errors
```

### 4.4 Footprint Morphology Control

#### config.detection.minPixels
- **Default:** 1
- **What it does:** Rejects footprints smaller than this pixel count
- **Purpose:** Filter single-pixel noise spikes vs. real PSF-sized sources

**Adjustment Strategy:**

**For Nickel telescope with ~1.0" seeing, ~0.4"/pixel:**
```python
# PSF FWHM = 1.0" = 2.5 pixels
# PSF area ≈ π × (FWHM/2.35)² ≈ 2.2 pixels

# Conservative (accept marginal sources):
config.detection.minPixels = 1  # Any detection
# Risk: Single hot pixels detected as sources

# Moderate (PSF-sized sources):
config.detection.minPixels = 2  # ~PSF core
# Balanced: Rejects single pixels, accepts PSF sources

# Aggressive (only well-sampled sources):
config.detection.minPixels = 5  # Require extended detection
# Risk: Miss faint sources detected in only few pixels
```

**Impact on Pipeline:**
- Higher minPixels → fewer false detections from hot pixels
- But: May reject real faint sources detected in few pixels
- **Recommended:** minPixels = 1 (let measurement flags identify bad sources)

#### config.detection.nSigmaToGrow
- **Default:** 2.4
- **Units:** PSF sigma (RMS width)
- **What it does:** Expands footprints outward by this many PSF widths

**Why footprints need growing:**
- Initial detection finds only core above threshold
- PSF has extended wings below threshold
- Growing captures full PSF extent for accurate measurement
- Merges nearby sources (helps identify blends)

**How it works:**
```python
# If PSF FWHM = 1.0" and nSigmaToGrow = 2.4:
# PSF sigma = FWHM / 2.35 = 0.43"
# Grow distance = 2.4 × 0.43" = 1.03"
# In pixels (0.4"/pix): ~2.6 pixels in all directions
```

**Impact on Pipeline:**

**Larger nSigmaToGrow (e.g., 4.0):**
- ✅ Captures more PSF wings → accurate photometry
- ✅ Identifies more blends (footprints merge)
- ⚠️ Over-merges distinct sources → excessive deblending load
- ⚠️ Footprints too large → slower measurement

**Smaller nSigmaToGrow (e.g., 1.0):**
- ✅ Faster measurement (smaller footprints)
- ✅ Fewer blends identified
- ⚠️ Miss PSF wings → underestimate flux
- ⚠️ Miss nearby faint companions

**Adjustment Strategy:**
```python
# Standard balanced setting:
config.detection.nSigmaToGrow = 2.4
# Captures ~98% of PSF flux

# For crowded fields (avoid over-merging):
config.detection.nSigmaToGrow = 1.5
# Smaller footprints → less merging → faster but risk missing wings

# For sparse fields (ensure completeness):
config.detection.nSigmaToGrow = 3.0
# Larger footprints → capture all wings

# For no growing (fastest, for testing):
config.detection.nSigmaToGrow = 0.0
# No growing → only above-threshold core
```

#### config.detection.isotropicGrow
- **Default:** False
- **What it does:** Controls footprint growing pattern

**Growing Patterns:**

**False (default - "Manhattan" or "diamond" metric):**
```
Grows in 4 directions (N, S, E, W):
    *
  * X *
    *
Faster, slightly anisotropic
```

**True (isotropic - circular metric):**
```
Grows circularly:
  * * *
  * X *
  * * *
Slower, more physically motivated
```

**When to adjust:**
```python
# Default (faster):
config.detection.isotropicGrow = False

# For publication-quality or precision work:
config.detection.isotropicGrow = True
# Reason: More accurately represents circular PSF
# Cost: ~20% slower processing
```

### 4.5 Background Estimation Strategy

**Why background estimation matters:**
- Sources appear as deviations from background
- Accurate background → accurate threshold → clean detection
- Poor background → false detections or missed sources

**Background Estimation Process:**
1. Divide image into grid
2. Compute statistic (mean/median) per cell, excluding bright sources
3. Interpolate grid to create smooth background model
4. Subtract from image

#### config.detection.background.binSize
- **Default:** 128
- **Units:** pixels
- **What it does:** Sets size of background estimation mesh

**Physical meaning:**
```python
# For Nickel telescope with 0.4"/pixel:
binSize = 128 pixels = 51.2 arcsec

# Background model has resolution of ~50"
# Can't resolve background variations smaller than this
```

**Impact on Detection:**

**Smaller binSize (e.g., 64):**
- ✅ Better tracking of local background variations
- ✅ Important in crowded fields or near bright sources
- ⚠️ May over-subtract real large-scale structure
- ⚠️ More sensitive to noise in background estimation

**Larger binSize (e.g., 256):**
- ✅ Smoother background model, less noise
- ✅ Preserves large-scale structure (galaxies, nebulosity)
- ⚠️ Misses local background variations
- ⚠️ Poor performance near bright stars (halos not removed)

**Adjustment Strategy:**
```python
# For fields with large galaxies:
config.detection.background.binSize = 256
# Reason: Avoid subtracting galaxy light as "background"

# For crowded stellar fields:
config.detection.background.binSize = 64
# Reason: Need local background between stars

# For standard stellar fields:
config.detection.background.binSize = 128  # Default, balanced

# Rule of thumb: binSize should be several times larger than
# largest sources you want to detect
```

#### config.detection.reEstimateBackground
- **Default:** False
- **What it does:** Iteratively improves background model

**Iterative Background Refinement:**
```
1. Estimate background (sources contaminate)
2. Detect sources with preliminary background
3. Mask detected sources
4. Re-estimate background (excluding masked sources)
5. Re-detect with improved background
```

**When to enable:**
```python
# For crowded fields:
config.detection.reEstimateBackground = True
# Reason: Initial background contaminated by many sources

# For sparse fields:
config.detection.reEstimateBackground = False  # Default
# Reason: Few sources, initial background is good

# Cost: Adds ~30% processing time
# Benefit: Better background model → cleaner detection
```

#### config.detection.background.algorithm
- **Default:** 'AKIMA_SPLINE'
- **What it does:** Method for interpolating background grid to full image

**Options Explained:**

**'AKIMA_SPLINE' (recommended):**
- Nonlinear spline interpolation
- Robust to outliers
- Smooth but captures local variations
- **Best for:** Most applications

**'NATURAL_SPLINE':**
- Cubic spline with natural boundary conditions
- Very smooth
- Can oscillate near edges
- **Best for:** When background is known to be very smooth

**'LINEAR':**
- Simple linear interpolation
- Fast but creates artifacts
- **Best for:** Testing/debugging only

**'CONSTANT':**
- Single value across image
- **Best for:** Heavily processed images with uniform background

**Recommendation:**
```python
config.detection.background.algorithm = 'AKIMA_SPLINE'
# Reason: Best balance of smoothness and local adaptation
# Use unless specific reason to change
```

#### config.detection.background.statisticsProperty
- **Default:** 'MEANCLIP'
- **What it does:** Statistic computed for each background grid cell

**Options:**

**'MEANCLIP' (recommended):**
- Iteratively sigma-clips outliers, then takes mean
- Robust to sources within grid cell
- **Best for:** Most applications
- **Process:** Compute mean, reject >3σ points, recompute

**'MEAN':**
- Simple arithmetic mean
- Fast but sensitive to sources
- **Best for:** Clean backgrounds with no sources

**'MEDIAN':**
- Most robust to outliers
- Slower to compute
- **Best for:** Very crowded fields or when many artifacts expected

**Recommendation:**
```python
config.detection.background.statisticsProperty = 'MEANCLIP'
# Reason: Good robustness without median's computational cost
```

### 4.6 Detection Parameter Interactions

**Critical Interaction #1: Threshold × Background**
- Lower threshold + aggressive background subtraction = many false detections
- Higher threshold + conservative background = miss real sources
- **Balance:** Moderate threshold (5σ) with binSize matched to source sizes

**Critical Interaction #2: Growing × Deblending**
- Large nSigmaToGrow → many merged footprints → heavy deblending load
- Small nSigmaToGrow → few merges → miss blends → poor photometry
- **Balance:** nSigmaToGrow = 2-3 captures PSF, identifies obvious blends

**Critical Interaction #3: Detection → PSF Measurement**
- Detection creates the source list for PSF star selection
- Too few detections → PSF fails (not enough stars)
- Too many false detections → PSF contaminated by non-stars
- **Downstream effect:** PSF quality depends critically on detection

**Critical Interaction #4: Detection → Astrometry**
- Astrometry matches detected sources to reference catalog
- Need ~50-200 good detections for reliable WCS
- Too few → matching fails; too many → slow but no harm
- **Balance:** Threshold that gives ~100-500 detections per image

### 4.7 How to Tune Detection for Nickel Telescope

**Step 1: Establish baseline**
```python
# Start with standard settings:
config.detection.thresholdValue = 5.0
config.detection.thresholdType = 'pixel_stdev'
config.detection.minPixels = 1
config.detection.nSigmaToGrow = 2.4
config.detection.background.binSize = 128
config.detection.background.algorithm = 'AKIMA_SPLINE'
config.detection.background.statisticsProperty = 'MEANCLIP'
```

**Step 2: Assess initial results**
```python
# Count detections per image
# Target: 100-1000 for good astrometry/PSF
# If < 50: Lower threshold or check ISR quality
# If > 5000: Raise threshold or check for artifacts
```

**Step 3: Visual inspection**
```python
# Create diagnostic plots:
# - Overlay detections on image
# - Check: Missing obvious sources?
# - Check: Detecting artifacts (diffraction spikes, ghosts)?
# - Check: Background over/under-subtracted?
```

**Step 4: Adjust based on findings**

**If missing faint sources:**
```python
config.detection.thresholdValue = 4.0  # Lower threshold
```

**If too many artifacts:**
```python
config.detection.thresholdValue = 6.0  # Raise threshold
config.detection.minPixels = 3  # Reject single-pixel detections
```

**If background poorly subtracted:**
```python
config.detection.background.binSize = 64  # Finer resolution
config.detection.reEstimateBackground = True  # Iterate
```

**If over-merging sources:**
```python
config.detection.nSigmaToGrow = 1.5  # Smaller footprints
```

**Step 5: Verify downstream effects**
```python
# After adjusting detection, check:
# - Does PSF measurement still work? (need enough stars)
# - Does astrometry still work? (need enough matches)
# - Is catalog size reasonable? (not 10,000s of sources)
# - Is processing time acceptable?
```

---

## 5. PSF Measurement Parameters

**Task:** `lsst.pipe.tasks.measurePsf.MeasurePsfTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.pipe.tasks/

### 5.1 What PSF Measurement Does and Why It's Critical

**Purpose:** PSF measurement determines the Point Spread Function - the instrument's response to a point source - by modeling stellar images across the field.

**Why PSF is Critical (Affects Everything!):**

**Direct Uses of PSF Model:**
1. **PSF Photometry:** Optimal flux measurement for point sources
2. **Star/Galaxy Separation:** Resolved sources deviate from PSF
3. **Deblending:** Separate overlapping sources using PSF shape
4. **Aperture Corrections:** Extrapolate aperture flux to total flux
5. **Shape Measurement:** Compare source shapes to PSF shape

**Indirect Downstream Effects:**
- Poor PSF → PSF photometry wrong → photometric zero point wrong
- Poor PSF → Star/galaxy separation wrong → wrong sources for astrometry
- Poor PSF → Aperture corrections wrong → systematic photometry errors
- Poor PSF → Deblending fails → crowded field photometry breaks

**PSF Spatial Variation:**
- Real telescopes have PSF that varies across field
- Optical aberrations, atmospheric refraction, tracking errors
- PSF measurement must MODEL this spatial variation
- Critical parameter: spatialOrder (controls variation model)

### 5.2 PSF Measurement Process Overview

**Step-by-Step Process:**

```
1. SELECT PSF STAR CANDIDATES
   ├─ Use starSelector to identify likely stars
   ├─ Apply cuts: magnitude, S/N, shape, flags
   └─ Produces: List of ~100-300 candidate stars

2. MEASURE PSF FROM CANDIDATES
   ├─ Extract postage stamps around each candidate
   ├─ Fit PSF model (basis functions + spatial variation)
   ├─ Identify outliers (galaxies, artifacts, bad pixels)
   └─ Produces: PSF model + list of good PSF stars

3. VALIDATE PSF MODEL
   ├─ Check: Spatial pattern makes sense?
   ├─ Check: Residuals (star - PSF) are random noise?
   ├─ Check: PSF FWHM reasonable for seeing?
   └─ Flag issues for quality assessment

4. APPLY PSF MODEL
   ├─ Used immediately for catalog measurement
   ├─ Used for deblending
   └─ Saved for later use (forced photometry, etc.)
```

**Iterative Refinement:**
- Initial star selection may include galaxies, bad pixels
- PSF measurement identifies outliers
- Re-measure PSF excluding outliers
- Repeat until stable

### 5.3 Star Selection Configuration

#### config.measurePsf.starSelector (Registry)
- **Full Path:** `config.measurePsf.starSelector`
- **Type:** RegistryField (single-selection)
- **Default:** 'objectSize'

**What star selection does:**
- Distinguishes stars (PSF-shaped) from galaxies (resolved)
- Applies quality cuts (S/N, flags, magnitude range)
- Produces list of candidate sources for PSF measurement

**Why it matters:**
- Galaxies contaminating PSF stars → spatially-varying errors in PSF model
- Too few stars → poor spatial sampling → PSF varies across field without measurement
- Too many stars → slower PSF measurement (but usually fine)

**Available Star Selectors (Detailed):**

#### A. 'objectSize' - ObjectSizeStarSelectorTask (RECOMMENDED)

**Method:** Identifies stellar locus in size-magnitude space using clustering algorithm.

**How it works:**
1. Measure size (e.g., base_SdssShape moments) of all sources
2. Plot size vs. magnitude
3. Identify tight stellar sequence (stars have consistent size)
4. Select sources near this sequence

**Advantages:**
- Robust to different fields (adapts to local star/galaxy mix)
- Handles varying seeing (uses relative sizes)
- Good performance in most conditions

**Disadvantages:**
- Requires sufficient sources to identify stellar locus
- Can fail in extremely sparse or extremely crowded fields

**Key Configuration Parameters:**

**config.measurePsf.starSelector["objectSize"].sourceFluxField**
- **Default:** 'base_GaussianFlux_instFlux'
- **What it does:** Flux measurement used for magnitude axis in size-magnitude plot
- **Options:**
  - **'base_GaussianFlux_instFlux':** Fast Gaussian aperture (default)
  - **'base_PsfFlux_instFlux':** PSF flux (circular - needs initial PSF guess)
  - **'base_CircularApertureFlux_X_X_instFlux':** Specific aperture size

**When to adjust:**
```python
# Default (fast, robust):
config.measurePsf.starSelector["objectSize"].sourceFluxField = 'base_GaussianFlux_instFlux'

# If Gaussian flux unreliable:
config.measurePsf.starSelector["objectSize"].sourceFluxField = 'base_CircularApertureFlux_9_0_instFlux'
# Use specific aperture radius (in pixels, here 9.0 pixels)
```

**config.measurePsf.starSelector["objectSize"].widthStdAllowed**
- **Default:** 0.15
- **Units:** Fractional width
- **What it does:** Standard deviation in size allowed around stellar locus

**Physical meaning:**
```python
# If stellar locus has typical size = 3.0 pixels
# widthStdAllowed = 0.15
# Accept stars with size in range:
# [3.0 × (1-0.15), 3.0 × (1+0.15)] = [2.55, 3.45] pixels
```

**Impact on PSF:**

**Tighter selection (widthStdAllowed = 0.10):**
- ✅ Pure stellar sample, minimal galaxy contamination
- ✅ Better PSF model quality
- ⚠️ May reject real stars with unusual PSF (edge effects, distorted)
- ⚠️ Fewer PSF stars → poorer spatial sampling

**Looser selection (widthStdAllowed = 0.20):**
- ✅ More PSF stars → better spatial coverage
- ⚠️ May include marginally resolved galaxies
- ⚠️ PSF model biased toward slightly larger size

**Adjustment strategy:**
```python
# Standard fields:
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.15

# Crowded fields (many stars, can afford to be picky):
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.10

# Sparse fields (need every star):
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.20

# Diagnostic: Plot size vs. magnitude
# Check: Is stellar locus well-separated from galaxies?
# If yes → can use tight cut; if no → need looser cut
```

**config.measurePsf.starSelector["objectSize"].fluxMin**
- **Default:** 12500.0
- **Units:** Counts (flux units)
- **What it does:** Minimum flux for PSF candidate consideration

**Why flux limits matter:**
- Faint sources have poor S/N → noisy PSF measurement
- Bright sources have better S/N but may be saturated
- Sweet spot: bright enough for good S/N, faint enough to avoid saturation

**Adjustment strategy:**
```python
# For deep images (good S/N):
config.measurePsf.starSelector["objectSize"].fluxMin = 5000.0
# Can use fainter stars

# For shallow images (poor S/N):
config.measurePsf.starSelector["objectSize"].fluxMin = 20000.0
# Need brighter stars for reliable PSF

# For Nickel telescope typical exposure:
config.measurePsf.starSelector["objectSize"].fluxMin = 10000.0
# Adjust based on typical stellar flux in your images
```

**config.measurePsf.starSelector["objectSize"].fluxMax**
- **Default:** 0.0 (no maximum)
- **What it does:** Maximum flux for PSF candidate; 0 = no limit

**When to set:**
```python
# Exclude saturated sources:
config.measurePsf.starSelector["objectSize"].fluxMax = 50000.0
# Use if saturation level is ~60,000 counts

# Default (no upper limit):
config.measurePsf.starSelector["objectSize"].fluxMax = 0.0
# Usually fine; saturated sources flagged and rejected anyway
```

**config.measurePsf.starSelector["objectSize"].doSignalToNoise**
- **Default:** True
- **What it does:** Apply S/N ratio cut in addition to flux cut

**config.measurePsf.starSelector["objectSize"].signalToNoiseMin**
- **Default:** 20.0
- **What it does:** Minimum S/N for PSF star candidates

**Why S/N matters:**
- Low S/N stars → noisy PSF shape measurement
- PSF measurement averages many stars → individual star S/N critical
- Rule of thumb: S/N = 20 gives ~5% PSF shape uncertainty

**Impact on PSF:**

**Higher S/N cut (e.g., 50.0):**
- ✅ Very clean PSF measurements
- ✅ Minimal noise in PSF model
- ⚠️ Fewer PSF stars → worse spatial sampling
- ⚠️ May have no stars in sparse fields

**Lower S/N cut (e.g., 10.0):**
- ✅ More PSF stars → better spatial coverage
- ⚠️ Noisier PSF model
- ⚠️ May not converge if too noisy

**Adjustment strategy:**
```python
# Standard (good balance):
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0

# Sparse fields (need more stars):
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0

# Dense fields (can be picky):
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 30.0

# Very deep images (excellent S/N available):
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 50.0
```

#### B. 'science' - ScienceSourceSelectorTask

**Method:** Flag-based and quality-based source selection using explicit criteria.

**When to use:** When you want explicit control over selection criteria rather than automatic clustering.

**Key difference from objectSize:**
- objectSize: Adapts to field using clustering
- science: Uses fixed criteria you specify

**Use case:** When objectSize fails (no clear stellar locus) or when you need reproducible selection criteria.

### 5.4 PSF Determiner Configuration

#### config.measurePsf.psfDeterminer (Registry)
- **Full Path:** `config.measurePsf.psfDeterminer`
- **Default:** 'psfex'

**What PSF determiner does:**
- Takes list of PSF star candidates
- Fits spatial PSF model across field
- Produces PSF model that can be evaluated at any position

#### A. 'psfex' - PSFEx PSF Determiner (RECOMMENDED)

**Algorithm:** PSFEx (Bertin 2011) - industry-standard PSF modeling.

**How PSFEx works:**
1. **Basis function decomposition:** Represent PSF as weighted sum of basis functions (Karhunen-Loève decomposition)
2. **Spatial variation:** Model how weights vary across field using polynomials
3. **Iterative fitting:** Fit basis, identify outliers, refit
4. **Validation:** Check residuals, convergence

**Why PSFEx is recommended:**
- Handles spatially-varying PSF naturally
- Robust outlier rejection
- Proven performance across many surveys
- Good defaults that work for most cases

**Critical Configuration Parameters:**

#### config.measurePsf.psfDeterminer['psfex'].spatialOrder
- **Type:** int
- **Default:** 2
- **Valid Range:** [0, 6]

**What it does:** Polynomial order for modeling PSF spatial variation.

**Physical meaning:**
```
spatialOrder = 0: PSF constant across field
  PSF(x,y) = PSF₀

spatialOrder = 1: PSF varies linearly
  PSF(x,y) = PSF₀ + a₁·x + a₂·y

spatialOrder = 2: PSF varies quadratically (DEFAULT)
  PSF(x,y) = PSF₀ + a₁·x + a₂·y + a₃·x² + a₄·xy + a₅·y²

spatialOrder = 3+: Higher-order variation
```

**Impact on PSF Quality (CRITICAL PARAMETER):**

**spatialOrder = 0 (constant PSF):**
- ✅ Fastest computation
- ✅ Most robust (can't overfit spatial variation)
- ✅ Best for small fields or good optical quality
- ⚠️ Averages PSF across field → poor quality at edges
- ⚠️ Misses real spatial variations → systematic errors
- **When to use:** Small field (<10 arcmin), excellent optics, testing

**spatialOrder = 1 (linear variation):**
- ✅ Fast, robust
- ✅ Captures typical tilt/coma patterns
- ⚠️ May miss complex optical aberrations
- **When to use:** Moderate field, good optics

**spatialOrder = 2 (quadratic variation - DEFAULT):**
- ✅ Captures most optical aberrations (spherical, astigmatism, coma)
- ✅ Good balance: flexible but not overfit
- ✅ Works for most telescopes/fields
- **When to use:** Standard choice for most applications

**spatialOrder = 3-4 (high-order variation):**
- ✅ Captures complex aberration patterns
- ✅ Important for wide-field systems
- ⚠️ Risk of overfitting if insufficient PSF stars
- ⚠️ Slower computation
- **When to use:** Wide field (>1 degree), complex optics

**spatialOrder = 5-6 (very high-order):**
- ⚠️ High risk of overfitting
- ⚠️ Requires many PSF stars well-distributed
- ⚠️ Can produce unphysical PSF variations
- **When to use:** Rarely; only for extremely complex systems with excellent spatial sampling

**Adjustment strategy for Nickel telescope:**

```python
# Start with default:
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2

# Diagnostic: Examine PSF residuals across field
# Plot: PSF FWHM vs. position
# Check: Is there systematic spatial pattern in residuals?

# If PSF constant across field (residuals random):
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 0
# Benefit: More robust, faster

# If PSF shows strong spatial variation:
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 3
# Captures more complex patterns

# If PSF measurement fails (overfitting):
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
# Reduce complexity to avoid overfitting

# Quantitative check:
# Compare PSF model residuals for different spatialOrder
# spatialOrder too low: Systematic residuals with spatial pattern
# spatialOrder too high: Noisy PSF model, unphysical variations
```

#### config.measurePsf.psfDeterminer['psfex'].samplingSize
- **Default:** 0.5
- **Units:** PSF model pixels per image pixel
- **What it does:** Resolution of PSF model relative to image pixels

**Physical meaning:**
```python
samplingSize = 0.5  # PSF model has 2× finer sampling than image
# Image: 1 pixel = 0.4 arcsec
# PSF model: 1 pixel = 0.2 arcsec (2× oversampling)

samplingSize = 1.0  # PSF model matches image sampling
# Both have same pixel scale
```

**Why oversampling matters:**
- PSF core may be undersampled in image
- Finer PSF model captures true PSF shape
- Enables sub-pixel centroiding
- Improves PSF photometry accuracy

**Impact:**

**Higher resolution (samplingSize = 0.33):**
- ✅ Very accurate PSF shape
- ✅ Better sub-pixel PSF evaluation
- ⚠️ Much slower computation (~3× slower)
- ⚠️ May amplify noise in PSF measurement

**Lower resolution (samplingSize = 1.0):**
- ✅ Fastest computation
- ⚠️ May miss fine PSF structure
- ⚠️ PSF core undersampled

**Adjustment strategy:**
```python
# Standard (recommended):
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.5
# Good balance: captures PSF detail without excessive computation

# For well-sampled PSFs (FWHM > 3 pixels):
config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0
# Image sampling sufficient, no oversampling needed

# For undersampled PSFs (FWHM < 2 pixels):
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.33
# Need finer PSF model to capture core

# For Nickel telescope:
# Typical: 1.0" seeing / 0.4"/pixel = 2.5 pixels FWHM
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.5
# Slightly undersampled → benefit from 2× oversampling
```

#### config.measurePsf.psfDeterminer['psfex'].sizeCellX, sizeCellY
- **Default:** 256
- **Units:** pixels
- **What they do:** Size of cells used for PSF spatial variation estimation

**How PSFEx uses cells:**
1. Divide image into sizeCellX × sizeCellY pixel cells
2. Find PSF stars in each cell
3. Measure PSF variation across cells
4. Interpolate between cells for full-field PSF model

**Impact:**

**Smaller cells (e.g., 128):**
- ✅ Finer spatial resolution of PSF variation
- ✅ Can track rapid PSF changes
- ⚠️ Need more PSF stars (require stars in each cell)
- ⚠️ More susceptible to noise

**Larger cells (e.g., 512):**
- ✅ More robust (more stars per cell)
- ✅ Better for sparse fields
- ⚠️ May miss rapid PSF variations
- ⚠️ Poor at field edges (fewer cells)

**Adjustment strategy:**
```python
# Rule of thumb: cellSize should contain ~10-20 PSF stars

# For dense stellar fields:
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 128
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 128

# For sparse fields:
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 512
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 512

# For typical fields:
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 256  # Default
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 256

# For rectangular detectors, can use different X and Y:
# E.g., if detector is 2048×4096:
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 256
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 512
```

#### config.measurePsf.psfDeterminer['psfex'].maxCandidates
- **Default:** 300
- **Valid Range:** [10, 10000]
- **What it does:** Maximum number of PSF stars to use; downsamples if more available

**Why limit stars:**
- PSF measurement computation scales with number of stars
- Beyond ~300 stars, accuracy improvement minimal
- Downsampling from many stars still gives good spatial coverage

**Impact:**

**More stars (e.g., 500):**
- ✅ Better PSF model (if spatialOrder high)
- ✅ Better spatial sampling in dense fields
- ⚠️ Slower PSF measurement (~linear scaling)
- **When beneficial:** High spatialOrder (3-4), wide fields

**Fewer stars (e.g., 100):**
- ✅ Faster PSF measurement
- ⚠️ Worse spatial sampling
- ⚠️ May miss field-dependent PSF variations
- **When acceptable:** spatialOrder 0-1, small fields

**Adjustment strategy:**
```python
# Balanced (recommended):
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 300

# For fast processing (spatialOrder=0 or 1):
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 100

# For high-quality PSF (spatialOrder=3-4):
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 500

# Rule of thumb:
# maxCandidates should provide ~10× stars as polynomial terms
# spatialOrder=2 → 6 terms → need ~60 stars minimum
# maxCandidates=300 provides good margin
```

#### config.measurePsf.psfDeterminer['psfex'].spatialReject
- **Default:** 3.0
- **Units:** standard deviations
- **What it does:** Rejection threshold for outlier stars based on spatial fit residuals

**How outlier rejection works:**
1. Fit PSF model to all candidate stars
2. Compute residuals (star - model) for each star
3. Identify stars with residuals > spatialReject × σ
4. Exclude outliers, refit PSF
5. Iterate until convergence

**Why outlier rejection matters:**
- Galaxies contaminating PSF stars → biased PSF shape
- Bad pixels in stars → noisy PSF measurement
- Cosmic rays on stars → outliers
- Need to automatically identify and reject these

**Impact:**

**Lower threshold (e.g., 2.0):**
- ✅ Aggressive outlier rejection
- ✅ Cleaner PSF model
- ⚠️ May reject real stars with unusual PSF (distorted at edges)
- ⚠️ Risk of having too few stars

**Higher threshold (e.g., 5.0):**
- ✅ Keeps more stars → better spatial sampling
- ⚠️ May include some outliers → PSF model bias

**Adjustment strategy:**
```python
# Standard (recommended):
config.measurePsf.psfDeterminer['psfex'].spatialReject = 3.0

# For clean fields (few artifacts):
config.measurePsf.psfDeterminer['psfex'].spatialReject = 4.0
# Keep more stars

# For problematic fields (many artifacts):
config.measurePsf.psfDeterminer['psfex'].spatialReject = 2.5
# More aggressive rejection

# Diagnostic: Check fraction of stars rejected
# If >50% rejected: Problem with star selection or field
# If <5% rejected: Could be more aggressive
```

### 5.5 PSF Parameter Interaction Summary

**Critical Interactions:**

**1. spatialOrder × Cell Size × Number of Stars:**
```python
# High spatialOrder requires:
# - Many PSF stars (to constrain polynomial)
# - Good spatial distribution
# - Small cells for local fitting

# spatialOrder=3, 6 polynomial terms per basis
# Need ~60 stars minimum, ~200 recommended
# Cell size determines spatial resolution

# Example balanced configuration:
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 256
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 300
```

**2. Star Selection → PSF Quality:**
```python
# Too few stars:
starSelector.signalToNoiseMin = 50  # Too strict
→ Few PSF stars → spatialOrder must be low → poor PSF at edges

# Too many stars (including galaxies):
starSelector.widthStdAllowed = 0.30  # Too loose
→ Galaxy contamination → PSF too large → photometry bias

# Balanced:
starSelector.signalToNoiseMin = 20
starSelector.widthStdAllowed = 0.15
→ ~100-300 clean stars → spatialOrder=2 works well
```

**3. PSF Quality → Downstream Processing:**
```python
# Poor PSF (spatialOrder too low for actual variation):
→ PSF mismatch at field edges
→ PSF photometry biased
→ Star/galaxy separation fails at edges
→ Aperture corrections spatially varying
→ Deblending uses wrong PSF shape

# Over-fit PSF (spatialOrder too high):
→ Noisy PSF model
→ Unstable PSF photometry
→ Unphysical PSF shape variations
→ Processing failures
```

### 5.6 How to Tune PSF for Nickel Telescope

**Step-by-step tuning process:**

**Step 1: Start with defaults and assess**
```python
config.measurePsf.starSelector.name = 'objectSize'
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.15

config.measurePsf.psfDeterminer.name = 'psfex'
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 300
```

**Step 2: Check PSF star selection**
```python
# Examine PSF star list:
# - How many stars selected? Target: 100-300
# - Spatial distribution uniform?
# - S/N of stars reasonable?

# If <50 stars:
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0
# Or lower detection threshold

# If >1000 stars:
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 30.0
# Can be more selective
```

**Step 3: Assess PSF spatial variation**
```python
# Create diagnostic plots:
# - PSF FWHM vs. X position
# - PSF FWHM vs. Y position
# - PSF ellipticity across field

# Check: Smooth variation or random scatter?
# Smooth → real PSF variation → need spatialOrder ≥ 1
# Random → PSF constant → spatialOrder=0 sufficient

# Check: Simple pattern (linear/quadratic) or complex?
# Simple → spatialOrder=1 or 2
# Complex → spatialOrder=3 or 4
```

**Step 4: Tune spatialOrder**
```python
# Try different values:
for order in [0, 1, 2, 3]:
    config.measurePsf.psfDeterminer['psfex'].spatialOrder = order
    # Run PSF measurement
    # Measure PSF model residuals
    # Check: RMS residuals, spatial patterns

# Select order that:
# - Minimizes residuals
# - Shows no systematic spatial patterns
# - Doesn't overfit (order N+1 same as order N)
```

**Step 5: Validate with diagnostics**
```python
# Final checks:
# 1. PSF FWHM reasonable? (Should match seeing)
# 2. PSF shape reasonable? (Gaussian-like)
# 3. Spatial variation smooth? (No discontinuities)
# 4. Residuals small? (RMS < 5% of peak)
# 5. Enough PSF stars used? (>50)
```

**Step 6: Test downstream effects**
```python
# Check impact on measurements:
# - PSF photometry residuals vs. aperture photometry
# - Star/galaxy separation effectiveness
# - Astrometry success rate (needs good stars)
# - Processing time (higher spatialOrder slower)
```

---

## 6. Astrometry Parameters

**Task:** `lsst.meas.astrom.astrometry.AstrometryTask`
**Documentation:** https://pipelines.lsst.io/modules/lsst.meas.astrom/tasks/lsst.meas.astrom.AstrometryTask.html

### 6.1 What Astrometry Does and Why It's Critical

**Purpose:** Astrometry determines the World Coordinate System (WCS) - the mathematical transformation from pixel coordinates to sky coordinates (RA, Dec) - by matching detected sources to a reference catalog.

**Why Astrometry is Critical:**

**Fundamental for astronomy:**
- Enables cross-matching with other catalogs (identify same objects)
- Required for multi-epoch studies (moving objects, variable sources)
- Needed for photometric calibration (match to reference stars)
- Essential for mosaicking (combine multiple images)

**Downstream dependencies:**
- **Photometry:** Can't calibrate without WCS (need to match reference stars)
- **Source identification:** Can't identify sources without positions
- **Science analysis:** Most analyses require accurate positions

**Astrometry failure is catastrophic:**
- No WCS → No photometric calibration possible
- → Image unusable for most science
- → Must re-process from scratch with better parameters

**Astrometry challenge:**
- Must solve "pattern matching" problem
- Given: 100s of detected source positions (x, y)
- Given: 1000s of reference catalog positions (RA, Dec)
- Find: Which detections correspond to which reference sources?
- Problem: Without WCS, don't know where to look!

### 6.2 Astrometry Process Overview

**Step-by-step process:**

```
1. INITIAL WCS APPROXIMATION
   ├─ From telescope pointing (RA, Dec of field center)
   ├─ From header keywords (CRVAL, CRPIX, CD matrix)
   ├─ Uncertainty: Could be arcminutes to degrees off!
   └─ Produces: Approximate WCS with ~arcmin accuracy

2. SOURCE SELECTION
   ├─ Select high-quality detected sources
   ├─ Apply cuts: S/N, shape, flags
   ├─ Target: ~100-500 sources for matching
   └─ Produces: List of "good" sources for matching

3. REFERENCE CATALOG LOADING
   ├─ Load reference stars from catalog (Gaia, etc.)
   ├─ Search region: Initial WCS ± maxOffsetPix safety margin
   ├─ Apply magnitude cuts, proper motion corrections
   └─ Produces: List of reference stars in search region

4. PATTERN MATCHING (CRITICAL STEP)
   ├─ Construct geometric patterns from brightest sources
   ├─ Construct patterns from brightest references
   ├─ Find matching patterns despite WCS error
   ├─ Infer shift/rotation from matches
   └─ Produces: Initial set of source-reference pairs

5. WCS FITTING
   ├─ Fit WCS transformation to initial pairs
   ├─ Find additional matches using improved WCS
   ├─ Reject outliers
   ├─ Refit with expanded match list
   └─ Produces: Refined WCS with distortion model

6. ITERATION
   ├─ Use improved WCS to find more matches
   ├─ Tighten matching tolerance
   ├─ Refit WCS with all matches
   ├─ Repeat until convergence
   └─ Produces: Final WCS solution

7. VALIDATION
   ├─ Check: Enough matches? (>minMatchedPairs)
   ├─ Check: RMS residuals reasonable? (<maxMeanDistanceArcsec)
   ├─ Check: Spatial distribution of matches uniform?
   └─ Accept or reject WCS solution
```

**Why pattern matching is hard:**
- Initial WCS could be wrong by degrees
- Don't know which source corresponds to which reference
- False matches look plausible
- Must be efficient (can't try all combinations)

**Key insight: Use geometric patterns**
- Stars form distinctive geometric patterns (triangles, quadrilaterals)
- These patterns are the same in detected sources and references
- Just need to find the pattern match despite shift/rotation/scale

### 6.3 Matcher Configuration (Most Critical for Success)

The **matcher** (pattern matching algorithm) is the heart of astrometry. Its parameters control whether matching succeeds or fails.

#### config.astrometry.matcher.maxOffsetPix

- **Full Path:** `config.astrometry.matcher.maxOffsetPix`
- **Type:** int (RangeField)
- **Default:** 250
- **Valid Range:** [50, 2000] (practical)
- **Units:** pixels

**What it does:** Defines the maximum allowed spatial offset between initial WCS prediction and true source positions. This sets the search radius for pattern matching.

**Physical meaning:**
```python
# For Nickel telescope with 0.4"/pixel:
maxOffsetPix = 250 pixels = 100 arcsec = 1.7 arcmin

# If initial WCS says source is at pixel (1000, 1000)
# But actual source is at pixel (1200, 1050)
# Offset = sqrt((200)² + (50)²) = 206 pixels
# Will find match if maxOffsetPix >= 206
```

**Why it's critical:**
- Too small: Matching fails if initial WCS error > maxOffsetPix
- Too large: Search vast region → slow + false matches

**Impact on processing:**

**Large maxOffsetPix (e.g., 1000):**
- ✅ Works even with very poor initial WCS
- ✅ Robust to telescope pointing errors
- ⚠️ Much slower (search area scales as maxOffsetPix²)
- ⚠️ More false pattern matches → may find wrong solution
- **Processing time:** Can be 10-100× slower

**Small maxOffsetPix (e.g., 100):**
- ✅ Fast matching
- ✅ Few false matches
- ⚠️ Fails if WCS error > maxOffsetPix
- ⚠️ Requires good initial WCS

**Adjustment strategy:**

```python
# Step 1: Assess initial WCS quality
# Check: Plot sources overlaid on sky coordinates
# Measure: Typical offset between sources and expected positions

# If WCS error < 50 pixels (good telescope pointing):
config.astrometry.matcher.maxOffsetPix = 100
# Fast, reliable

# If WCS error ~100-200 pixels (typical):
config.astrometry.matcher.maxOffsetPix = 250  # Default
# Balanced

# If WCS error ~500 pixels (poor pointing):
config.astrometry.matcher.maxOffsetPix = 600
# Slower but necessary

# If no reliable initial WCS:
config.astrometry.matcher.maxOffsetPix = 1500
# Very slow but comprehensive search
# Consider using separate blind astrometry solver

# Diagnostic approach:
# 1. Start with 250 (default)
# 2. If matching fails, check if it's WCS error:
#    - Try 500, then 1000
#    - If works → initial WCS was poor
#    - If still fails → different problem (see troubleshooting)
```

**Critical interaction with pixelMargin:**
```python
# MUST ENSURE: astromRefObjLoader.pixelMargin > maxOffsetPix
# Otherwise: May not load reference stars in search region!

config.astrometry.matcher.maxOffsetPix = 500
config.astromRefObjLoader.pixelMargin = 600  # Must be larger

# pixelMargin adds buffer when loading reference catalog:
# Search region = image area + maxOffsetPix + pixelMargin
```

#### config.astrometry.matcher.maxRotationDeg

- **Full Path:** `config.astrometry.matcher.maxRotationDeg`
- **Type:** float (RangeField)
- **Default:** 1.0
- **Valid Range:** [0.1, 5.0] (practical)
- **Units:** degrees

**What it does:** Maximum allowed rotation angle error between initial WCS and true orientation.

**Physical meaning:**
```python
# If initial WCS says North is "up" (PA=0°)
# But image is actually rotated (PA=2°)
# Will match if maxRotationDeg >= 2.0°
```

**Why it matters:**
- Geometric patterns depend on orientation
- Wrong orientation → patterns don't match
- Larger tolerance → searches more orientations → slower

**Impact on processing:**

**Large maxRotationDeg (e.g., 5.0):**
- ✅ Works with very uncertain orientation
- ✅ Robust to tracking errors, rotator problems
- ⚠️ Slower matching
- ⚠️ More false pattern matches possible

**Small maxRotationDeg (e.g., 0.5):**
- ✅ Faster matching
- ⚠️ Fails if rotation error exceeds tolerance

**Adjustment strategy:**

```python
# If telescope tracking is good:
config.astrometry.matcher.maxRotationDeg = 1.0  # Default
# Typical for well-aligned telescopes

# If uncertain orientation (alt-az, poor calibration):
config.astrometry.matcher.maxRotationDeg = 3.0
# Allows for larger rotator errors

# If orientation completely unknown:
config.astrometry.matcher.maxRotationDeg = 5.0
# Comprehensive search, slower

# For Nickel telescope:
# Check: Is rotator reliably calibrated?
# If yes → 1.0°; if uncertain → 2.0°
config.astrometry.matcher.maxRotationDeg = 1.5
# Conservative for typical systematic errors
```

#### config.astrometry.matcher.numBrightStars

- **Full Path:** `config.astrometry.matcher.numBrightStars`
- **Type:** int
- **Default:** 200
- **Valid Range:** [20, 500] (practical)

**What it does:** Number of brightest stars used for constructing geometric patterns.

**How pattern matching uses this:**
1. Sort detected sources by brightness
2. Take brightest numBrightStars sources
3. Construct all possible geometric patterns from these
4. Do same for reference catalog
5. Find matching patterns

**Why it's critical:**
- Computation scales approximately as O(N³) with N = numBrightStars
- Most critical parameter for processing speed!

**Computational scaling:**
```python
numBrightStars = 50  → Processing time = 1× (reference)
numBrightStars = 100 → Processing time = 8×
numBrightStars = 200 → Processing time = 64×
numBrightStars = 400 → Processing time = 512×

# This is WHY numBrightStars = 200 is default!
# Balance between success rate and speed
```

**Impact on matching:**

**More stars (e.g., 400):**
- ✅ Better matching in crowded, complex fields
- ✅ More geometric patterns → higher success rate
- ✅ Better spatial coverage across field
- ⚠️ Much slower (minutes → tens of minutes per image)
- **When needed:** Very crowded fields, complex geometry

**Fewer stars (e.g., 100):**
- ✅ Much faster (seconds vs. minutes)
- ⚠️ May fail in crowded fields (patterns not unique)
- ⚠️ May fail in sparse fields (too few patterns)
- **When acceptable:** Simple fields, good initial WCS

**Adjustment strategy:**

```python
# Quick test/initial processing:
config.astrometry.matcher.numBrightStars = 100
# 8× faster than default
# Try first, see if matching succeeds

# Standard processing:
config.astrometry.matcher.numBrightStars = 200  # Default
# Good balance for most fields

# Challenging fields:
config.astrometry.matcher.numBrightStars = 300
# More robust, ~3-4× slower

# Very crowded or very sparse fields:
config.astrometry.matcher.numBrightStars = 400
# Maximum robustness, very slow

# Diagnostic approach:
# 1. Start with 100 (fast)
# 2. If matching fails → try 200
# 3. If still fails → try 300
# 4. Check if time vs. quality tradeoff is acceptable
```

**Interaction with field properties:**
```python
# Sparse fields (few stars):
# Need fewer brightStars
config.astrometry.matcher.numBrightStars = 100
# Reason: Not enough stars anyway

# Crowded fields (many stars):
# Benefit from more brightStars
config.astrometry.matcher.numBrightStars = 300
# Reason: More patterns needed for unique matching

# For Nickel telescope:
# Typical stellar fields have ~1000-5000 sources
config.astrometry.matcher.numBrightStars = 200
# Standard default works well
```

#### config.astrometry.matcher.minMatchedPairs

- **Full Path:** `config.astrometry.matcher.minMatchedPairs`
- **Type:** int
- **Default:** 30
- **Valid Range:** [10, 100] (practical)

**What it does:** Absolute minimum number of source-reference pairs required for accepting WCS solution.

**Why it matters:**
- Too few matches → WCS fit underconstrained → unreliable solution
- WCS has ~6-12 free parameters (depending on distortion order)
- Need many more matches than parameters for robust fit

**Rule of thumb:**
```python
# Minimum matches for different WCS models:
# Simple TAN (6 parameters): Need ≥ 20 matches
# TAN + SIP order 2 (12 parameters): Need ≥ 40 matches
# TAN + SIP order 3 (20 parameters): Need ≥ 60 matches

# General: minMatchedPairs should be 3-5× number of parameters
```

**Impact on robustness:**

**Higher minMatchedPairs (e.g., 50):**
- ✅ More robust WCS solution
- ✅ Better rejection of false matches
- ✅ More reliable validation
- ⚠️ May fail in sparse fields (not enough sources)
- ⚠️ May fail with high rejection rate

**Lower minMatchedPairs (e.g., 15):**
- ✅ Works in sparse fields
- ✅ More permissive (fewer failures)
- ⚠️ WCS may be unreliable (underconstrained)
- ⚠️ Risk of accepting poor solution

**Adjustment strategy:**

```python
# Standard fields:
config.astrometry.matcher.minMatchedPairs = 30  # Default

# Dense fields (many sources):
config.astrometry.matcher.minMatchedPairs = 50
# Can afford to be picky

# Sparse fields (few sources):
config.astrometry.matcher.minMatchedPairs = 20
# Lower requirement to avoid failures

# High-order distortion (SIP order 3-4):
config.astrometry.matcher.minMatchedPairs = 60
# Need more matches to constrain parameters

# Interaction with field density:
# Count typical detections per image
# If <100 detections total:
config.astrometry.matcher.minMatchedPairs = 15
# Very permissive for sparse fields

# Diagnostic:
# Check: How many matches typically found?
# If consistently >100 matches:
config.astrometry.matcher.minMatchedPairs = 50
# Can raise threshold for robustness
```

#### config.astrometry.matcher.minFracMatchedPairs

- **Full Path:** `config.astrometry.matcher.minFracMatchedPairs`
- **Type:** float
- **Default:** 0.3
- **Valid Range:** [0.1, 0.9]

**What it does:** Minimum fraction of possible matches that must be found, relative to min(N_sources, N_references).

**How it works with minMatchedPairs:**
```python
# Actual minimum = max(
#     minMatchedPairs,
#     minFracMatchedPairs × min(N_sources, N_references)
# )

# Example:
# N_sources = 200, N_references = 500
# minMatchedPairs = 30
# minFracMatchedPairs = 0.3
# Required matches = max(30, 0.3 × 200) = max(30, 60) = 60
```

**Why fractional threshold:**
- Adapts to field density automatically
- Crowded fields have more sources → require more matches
- Sparse fields have fewer sources → require fewer matches

**Impact:**

**Higher fraction (e.g., 0.5):**
- ✅ Requires matching most visible sources
- ✅ More robust against false matches
- ⚠️ May fail if some sources are actually galaxies
- ⚠️ May fail with partial detector coverage

**Lower fraction (e.g., 0.2):**
- ✅ More permissive
- ✅ Works with mixed star/galaxy fields
- ⚠️ May accept poor solutions

**Adjustment strategy:**

```python
# Standard:
config.astrometry.matcher.minFracMatchedPairs = 0.3  # Default

# Pure stellar fields:
config.astrometry.matcher.minFracMatchedPairs = 0.4
# Can expect high match fraction

# Mixed star/galaxy fields:
config.astrometry.matcher.minFracMatchedPairs = 0.2
# Many sources won't match (galaxies not in ref catalog)

# For Nickel telescope:
# Typical stellar field → most sources are stars
config.astrometry.matcher.minFracMatchedPairs = 0.3
# Default is appropriate
```

#### config.astrometry.matcher.matcherIterations

- **Full Path:** `config.astrometry.matcher.matcherIterations`
- **Type:** int (RangeField)
- **Default:** 5
- **Valid Range:** [1, 10] (practical)

**What it does:** Number of "softening" iterations in pattern matcher.

**How iterations work:**
1. **Iteration 1:** Strict matching (exact pattern correspondence)
2. **Iteration 2:** Slightly relax tolerances
3. **Iteration 3:** Further relax tolerances
4. **Iterations 4-5:** Continue softening until solution found

**Why iterations help:**
- First iteration may fail due to:
  - Pattern distortions from WCS errors
  - Missing stars (detection incompleteness)
  - False stars (artifacts, galaxies)
- Later iterations more permissive → eventually find solution
- But: More iterations = slower

**Impact:**

**More iterations (e.g., 7):**
- ✅ Better recovery from difficult initial conditions
- ✅ More robust to poor initial WCS
- ⚠️ Slower matching
- ⚠️ May accept false matches

**Fewer iterations (e.g., 3):**
- ✅ Faster
- ⚠️ May fail on challenging fields

**Adjustment strategy:**

```python
# For good initial WCS:
config.astrometry.matcher.matcherIterations = 3
# Fast, likely succeeds on first iteration

# Standard (balanced):
config.astrometry.matcher.matcherIterations = 5  # Default

# For poor initial WCS:
config.astrometry.matcher.matcherIterations = 7
# More attempts to find solution

# Diagnostic: Check logs
# If matching succeeds on iteration 1 → can reduce
# If often fails → increase iterations
```

#### config.astrometry.matcher.minMatchDistPixels

- **Full Path:** `config.astrometry.matcher.minMatchDistPixels`
- **Type:** float
- **Default:** 1.0
- **Units:** pixels

**What it does:** Distance below which source-reference pairs are ALWAYS considered matches during WCS fitting iterations.

**How it works:**
```python
# During WCS fitting:
# After each fit, compute residuals for all source-reference pairs
# If residual < minMatchDistPixels:
#     Consider it a match (even if not in original match list)
#     Include in next WCS fit
# This allows finding additional matches as WCS improves
```

**Why it matters:**
- Initial pattern matching may miss some valid pairs
- As WCS improves, can identify additional matches
- Allows gradual expansion of match list
- Prevents overfitting (only includes nearby pairs)

**Adjustment strategy:**

```python
# Standard:
config.astrometry.matcher.minMatchDistPixels = 1.0  # Default
# Sub-pixel accuracy after good WCS fit

# For coarse astrometry:
config.astrometry.matcher.minMatchDistPixels = 2.0
# Accept matches within 2 pixels

# For precision astrometry:
config.astrometry.matcher.minMatchDistPixels = 0.5
# Strict sub-pixel matching
```

#### config.astrometry.matcher.maxRefObjects

- **Full Path:** `config.astrometry.matcher.maxRefObjects`
- **Type:** int (RangeField)
- **Default:** 65536
- **Absolute Maximum:** 65536 (2¹⁶)

**What it does:** Maximum number of reference catalog objects to use.

**Why the limit:**
- Memory constraint in matcher implementation
- In very dense reference catalogs (e.g., Gaia in Galactic plane), may have >100,000 stars
- Must downsample to stay within memory limits
- 65536 is hard-coded maximum in matcher

**When it matters:**
```python
# Typical fields: 1000-10,000 reference stars → no problem
# Dense fields (Galactic plane): 50,000-500,000 reference stars
# If >65536 reference stars → randomly sampled down

# Check: How many reference stars in your fields?
# If consistently <10,000 → never an issue
# If >50,000 → matcher will downsample
```

**Adjustment strategy:**

```python
# Standard (usually leave at default):
config.astrometry.matcher.maxRefObjects = 65536

# If matching fails in dense fields, try lowering:
config.astrometry.matcher.maxRefObjects = 30000
# Speeds up matching, still plenty of patterns

# Note: Can't exceed 65536 due to implementation limit
```

#### config.astrometry.matcher.numPatternConsensus

- **Full Path:** `config.astrometry.matcher.numPatternConsensus`
- **Type:** int
- **Default:** 3
- **Valid Range:** [1, 5] (practical)

**What it does:** Number of independent shift/rotation patterns that must agree before accepting transformation.

**When activated:**
- Only used after first softening iteration fails
- Only if both N_sources > numBrightStars AND N_references > numBrightStars
- Provides additional validation in challenging cases

**How consensus works:**
```python
# Multiple geometric patterns suggest same shift/rotation
# Count how many patterns agree
# If ≥ numPatternConsensus patterns agree:
#     Accept transformation
# Else:
#     Continue searching
```

**Impact:**

**Higher consensus (e.g., 5):**
- ✅ More robust against false matches
- ⚠️ May fail to find valid solution

**Lower consensus (e.g., 2):**
- ✅ More permissive
- ⚠️ May accept wrong transformation

**Adjustment strategy:**

```python
# Standard (leave at default unless problems):
config.astrometry.matcher.numPatternConsensus = 3

# For extremely challenging fields:
config.astrometry.matcher.numPatternConsensus = 2
# More permissive, higher success rate
```

### 6.4 WCS Fitter Configuration

After pattern matching succeeds, the WCS fitter refines the transformation using all matched pairs.

#### config.astrometry.wcsFitter.order

- **Full Path:** `config.astrometry.wcsFitter.order`
- **Type:** int (RangeField)
- **Default:** 2
- **Valid Range:** [0, 6] (practical: [0, 4])

**What it does:** Order of SIP (Simple Imaging Polynomial) distortion correction.

**Physical meaning:**
```python
# order = 0: TAN projection only (no distortion)
#   x_sky = f(x_detector)  [linear transformation]

# order = 1: TAN + linear distortion
#   x_sky = f(x_detector) + a₁·x + a₂·y

# order = 2: TAN + quadratic distortion
#   x_sky = f(x_detector) + a₁·x + a₂·y + a₃·x² + a₄·xy + a₅·y²

# order = 3: TAN + cubic distortion (and so on)
```

**Number of free parameters:**
```python
# order 0: 6 parameters (TAN only)
# order 1: 12 parameters
# order 2: 20 parameters
# order 3: 30 parameters
# order 4: 42 parameters
```

**Impact on WCS quality:**

**Higher order (e.g., 4):**
- ✅ Captures complex optical distortions
- ✅ Better residuals across full field
- ✅ Important for wide-field systems
- ⚠️ Requires many matches (>100 for order 4)
- ⚠️ Risk of overfitting if insufficient matches
- ⚠️ May produce unphysical distortions at field edges

**Lower order (e.g., 1):**
- ✅ Robust (few parameters to fit)
- ✅ Works with sparse matches
- ⚠️ Systematic residuals if real distortion is higher-order

**Adjustment strategy:**

```python
# For small fields or good optics:
config.astrometry.wcsFitter.order = 2  # Default

# For wide-field systems:
config.astrometry.wcsFitter.order = 3
# Captures field distortion

# For very wide field (>1 degree):
config.astrometry.wcsFitter.order = 4
# But requires excellent match distribution

# For sparse matches (<50):
config.astrometry.wcsFitter.order = 1
# Avoid overfitting

# For Nickel telescope (~12 arcmin field):
config.astrometry.wcsFitter.order = 2
# Sufficient for moderate field size

# Diagnostic: Plot residuals vs. position
# If systematic spatial pattern → increase order
# If random scatter → current order sufficient
```

**Interaction with number of matches:**
```python
# Rule: Need ≥ 3× parameters in matches
# order 2 (20 params) → need ≥60 matches
# order 3 (30 params) → need ≥90 matches

# If typical matches < 60:
config.astrometry.wcsFitter.order = 1
# Or:
config.astrometry.matcher.minMatchedPairs = 60
```

### 6.5 Astrometry Parameter Interaction Summary

**Critical interaction: Matcher speed vs. robustness:**
```python
# FAST configuration (seconds per image):
config.astrometry.matcher.numBrightStars = 100
config.astrometry.matcher.maxOffsetPix = 150
config.astrometry.matcher.matcherIterations = 3
# Works if: Good initial WCS, simple fields

# ROBUST configuration (minutes per image):
config.astrometry.matcher.numBrightStars = 300
config.astrometry.matcher.maxOffsetPix = 500
config.astrometry.matcher.matcherIterations = 7
# Works if: Poor initial WCS, challenging fields

# BALANCED configuration:
config.astrometry.matcher.numBrightStars = 200
config.astrometry.matcher.maxOffsetPix = 250
config.astrometry.matcher.matcherIterations = 5
# Default settings
```

**Critical interaction: Match requirements vs. field density:**
```python
# Dense stellar fields (>500 sources):
config.astrometry.matcher.minMatchedPairs = 50
config.astrometry.matcher.minFracMatchedPairs = 0.3
config.astrometry.wcsFitter.order = 3
# Plenty of matches → can use high-order fit

# Sparse fields (<100 sources):
config.astrometry.matcher.minMatchedPairs = 20
config.astrometry.matcher.minFracMatchedPairs = 0.2
config.astrometry.wcsFitter.order = 1
# Few matches → use simpler model
```

**Critical interaction: Source selection → Matching:**
```python
# If detection threshold too high:
config.detection.thresholdValue = 7.0
→ Few sources detected
→ Matching may fail (not enough patterns)
→ Solution: Lower detection threshold or use fainter references

# If detection threshold too low:
config.detection.thresholdValue = 3.0
→ Many false detections
→ Confuses pattern matching
→ Solution: Raise threshold or improve source selection
```

### 6.6 How to Tune Astrometry for Nickel Telescope

**Tuning workflow:**

**Step 1: Characterize initial WCS error**
```python
# Take test image with known pointing
# Measure: Offset between predicted and actual source positions
# Typical Nickel: ~100-300 pixels (~40-120 arcsec)

# Set maxOffsetPix accordingly:
measured_offset = 200  # pixels
config.astrometry.matcher.maxOffsetPix = measured_offset + 100  # Add safety margin
```

**Step 2: Choose speed vs. robustness**
```python
# For routine processing (1000s of images):
# PRIORITY: Speed
config.astrometry.matcher.numBrightStars = 150
config.astrometry.matcher.matcherIterations = 4
# Should complete in 10-30 seconds per image

# For difficult fields or science-critical:
# PRIORITY: Success rate
config.astrometry.matcher.numBrightStars = 250
config.astrometry.matcher.matcherIterations = 6
# May take 1-2 minutes per image but higher success rate
```

**Step 3: Test and measure success rate**
```python
# Process sample of ~50 images across different fields
# Measure:
# - Success rate: What fraction solves?
# - Time per image: Is it acceptable?
# - Residuals: Typical RMS in arcsec?

# Target metrics:
# Success rate > 95%
# RMS residuals < 0.3 arcsec (for Nickel ~0.4"/pixel)
# Time per image < 1 minute
```

**Step 4: Adjust based on failures**
```python
# If matching fails:
# Check logs: Which stage failed?

# "No pattern matches found":
→ Increase maxOffsetPix or numBrightStars
→ Check if initial WCS is completely wrong

# "Insufficient matches (got X, need Y)":
→ Lower minMatchedPairs or minFracMatchedPairs
→ Or improve detection (more sources)

# "WCS fit failed to converge":
→ Lower wcsFitter.order
→ Or improve match quality (better source selection)

# "Maximum iterations exceeded":
→ Increase matcherIterations
→ Or improve initial WCS
```

**Step 5: Validate final WCS**
```python
# Quantitative checks:
# 1. RMS residuals: Should be < pixel scale (0.4")
# 2. Number of matches: Should be > 100
# 3. Spatial distribution: Matches across full field, not clustered
# 4. Comparison with external catalog: Match independent sources

# Visual checks:
# 1. Overlay sources on reference catalog
# 2. Check field edges (worst distortion)
# 3. Verify no systematic offsets
```

---

## 10. Parameter Interaction Guide

### 10.1 Cross-Task Parameter Dependencies

**Fundamental understanding:** Parameters don't operate in isolation. Changes ripple through the pipeline.

**Major interaction pathways:**

```
ISR Parameters
    ↓ (affects image quality)
Detection Parameters
    ↓ (affects source list)
PSF Measurement Parameters
    ↓ (affects PSF model)
[Simultaneously affects:] → Astrometry Parameters (uses sources for matching)
    ↓ (provides WCS)
Photometry Parameters (needs WCS to match references)
    ↓
Final Catalog Quality
```

### 10.2 Common Adjustment Scenarios

#### Scenario 1: Pipeline Fails at Detection

**Symptom:** No sources detected, or only a few obvious bright stars.

**Possible causes & solutions:**

**Cause A: ISR failure**
```python
# Check: Does image look reasonable after ISR?
# If not (weird structure, very high background):
→ Problem in ISR (bad flat, wrong calibrations)
→ Solution: Fix ISR, don't adjust detection

# If ISR looks good:
→ Problem is detection threshold
```

**Cause B: Detection threshold too high**
```python
# Symptom: Missing obvious faint sources
# Solution:
config.detection.thresholdValue = 3.5  # Lower from 5.0

# But check downstream:
# Will PSF measurement still work with more noise detections?
# Adjust star selection to compensate:
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 25
# Higher S/N for PSF stars filters noise detections
```

**Cause C: Background over-subtracted**
```python
# Symptom: Negative "holes" where sources should be
# Solution:
config.detection.background.binSize = 256  # Increase from 128
# Larger bins → smoother background → less over-subtraction
```

#### Scenario 2: PSF Measurement Fails

**Symptom:** "Unable to measure PSF" error or very poor PSF model.

**Diagnosis cascade:**

**Check 1: Enough PSF stars?**
```python
# Look at logs: How many PSF stars selected?
# If <30:
→ Lower PSF star selection requirements
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0
→ Or lower detection threshold to find more sources
config.detection.thresholdValue = 4.0
```

**Check 2: PSF stars contaminated?**
```python
# If many "stars" but PSF fitting fails:
→ Galaxies contaminating stellar sample
→ Solution: Tighten star selection
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.10
```

**Check 3: Spatial overfitting?**
```python
# If PSF fits but produces weird spatial patterns:
→ spatialOrder too high for number of stars
→ Solution: Reduce spatial complexity
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
# Or increase star count:
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 10.0
```

**Cascading solution:**
```python
# Complete adjustment to fix PSF failure:

# 1. Get more sources
config.detection.thresholdValue = 4.0  # From 5.0

# 2. But filter them well for PSF
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.12

# 3. Use simpler PSF model
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1

# 4. Allow more PSF stars
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 200
```

#### Scenario 3: Astrometry Fails

**Symptom:** "No astrometric solution found" error.

**Diagnosis cascade:**

**Check 1: Initial WCS completely wrong?**
```python
# Try much larger search radius:
config.astrometry.matcher.maxOffsetPix = 1000  # From 250

# If this works → initial WCS was very poor
# Permanent solution: Fix WCS in headers or use blind solver
```

**Check 2: Not enough sources?**
```python
# Check: How many sources detected?
# If <50:
→ Lower detection threshold
config.detection.thresholdValue = 4.0

# Or lower match requirements:
config.astrometry.matcher.minMatchedPairs = 20
```

**Check 3: Sources wrong type?**
```python
# If detecting mostly galaxies (not point sources):
→ Reference catalog (Gaia) only has stars
→ Won't match galaxies
→ Solution: Improve source selection
config.astrometry.sourceSelector["science"].doUnresolved = True
config.astrometry.sourceSelector["science"].signalToNoiseMin = 15.0
```

**Check 4: Reference catalog problem?**
```python
# Check: Is reference catalog loaded?
# Verify pixelMargin is large enough:
config.astromRefObjLoader.pixelMargin = 600
# Must be > maxOffsetPix

# Check reference catalog availability at field position
# If at very low Galactic latitude or high declination:
→ May have no reference stars
→ Solution: Use different reference catalog or different field
```

**Cascading solution:**
```python
# Complete adjustment to fix astrometry failure:

# 1. Ensure enough good sources
config.detection.thresholdValue = 4.5
config.astrometry.sourceSelector["science"].signalToNoiseMin = 12.0

# 2. Allow larger search if WCS uncertain
config.astrometry.matcher.maxOffsetPix = 400

# 3. Use more stars for matching (slower but more robust)
config.astrometry.matcher.numBrightStars = 250

# 4. Be more permissive with matches
config.astrometry.matcher.minMatchedPairs = 25
config.astrometry.matcher.minFracMatchedPairs = 0.25

# 5. More iterations
config.astrometry.matcher.matcherIterations = 6
```

#### Scenario 4: Processing Too Slow

**Symptom:** Each image takes 10+ minutes to process.

**Bottleneck identification:**

**If astrometry is slow:**
```python
# Fastest speedup: Reduce numBrightStars
config.astrometry.matcher.numBrightStars = 100  # From 200
# 8× faster!

# Second speedup: Reduce search area
config.astrometry.matcher.maxOffsetPix = 150  # From 250
# ~2× faster

# Combined: ~16× speedup
# Trade-off: May fail more often
# Solution: Test on sample, verify success rate acceptable
```

**If PSF measurement is slow:**
```python
# Speedup: Reduce PSF star count
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 150
# ~2× faster

# Speedup: Reduce spatial complexity
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
# Faster fitting

# Speedup: Coarser PSF sampling
config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0
# ~2× faster
```

**If detection/measurement is slow:**
```python
# Speedup: Raise detection threshold
config.detection.thresholdValue = 6.0
# Fewer sources → faster measurement

# But check: Do you still get enough sources for astrometry/PSF?
# May need to adjust those too
```

### 10.3 Optimization Strategy Matrix

**Goal: High Quality, Speed Not Critical**
```python
config.detection.thresholdValue = 3.5  # Completeness priority
config.detection.nSigmaToGrow = 3.0  # Capture full PSF
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 30.0
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 3
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 400
config.astrometry.matcher.numBrightStars = 300
config.astrometry.wcsFitter.order = 3
```

**Goal: Fast Processing, Acceptable Quality**
```python
config.detection.thresholdValue = 6.0  # Fewer sources
config.detection.nSigmaToGrow = 2.0
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 150
config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0
config.astrometry.matcher.numBrightStars = 100
config.astrometry.wcsFitter.order = 2
```

**Goal: Robust (High Success Rate)**
```python
config.detection.thresholdValue = 4.5  # Balanced
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0  # Permissive
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.astrometry.matcher.maxOffsetPix = 500  # Large search
config.astrometry.matcher.numBrightStars = 250
config.astrometry.matcher.matcherIterations = 7
config.astrometry.matcher.minMatchedPairs = 25  # Lower requirement
```

---

## 11. Parameter Grid Examples

### 11.1 Systematic Parameter Exploration for Nickel Telescope

**Recommended optimization workflow:**

**Phase 1: ISR Validation (one-time)**
```python
# Goal: Verify ISR produces good images
# Don't grid search ISR - just validate it works

# Test these cases:
isr_validation = {
    'baseline': 'all corrections enabled',
    'no_fringe': 'doFringe=False (compare background RMS)',
    'no_crosstalk': 'doCrosstalk=False (if applicable)',
}

# Metrics:
# - Background RMS (should match theoretical Poisson + read noise)
# - Flat field quality (sky flat RMS ~1%)
# - No obvious artifacts
```

**Phase 2: Detection Threshold Optimization**
```python
# Goal: Find optimal detection threshold
# Most critical single parameter!

detection_grid = {
    'threshold': [3.0, 4.0, 5.0, 6.0, 7.0],
    'grow': [1.5, 2.4, 3.0],  # Secondary
}

# Metrics:
# - Catalog completeness vs. known sources
# - False positive rate (visual inspection)
# - Number of detections (target: 200-1000 per image)
# - PSF measurement success rate (needs enough stars)
# - Astrometry success rate (needs enough sources)

# Expected result:
# threshold=5.0, grow=2.4 for most fields
# threshold=4.0, grow=2.4 for sparse fields
# threshold=6.0, grow=2.0 for very deep/crowded
```

**Phase 3: PSF Measurement Optimization**
```python
# Goal: Optimize PSF model quality

psf_grid = {
    'spatialOrder': [0, 1, 2, 3],
    'signalToNoiseMin': [15.0, 20.0, 30.0],
    'widthStdAllowed': [0.10, 0.15, 0.20],
}

# Strategy: Grid search in order
# 1. Fix S/N=20, width=0.15, vary spatialOrder
# 2. Find best spatialOrder (by residuals)
# 3. Fix spatialOrder, vary S/N and width

# Metrics:
# - PSF model RMS residuals (goal: <5% of peak)
# - PSF FWHM vs. position (should be smooth)
# - Number of PSF stars used (goal: 50-300)
# - PSF measurement success rate (goal: >98%)
# - Star/galaxy separation quality

# Expected result:
# spatialOrder=2 (or 1 if field small)
# signalToNoiseMin=20.0
# widthStdAllowed=0.15
```

**Phase 4: Astrometry Matcher Optimization**
```python
# Goal: Balance speed vs. success rate

astrometry_grid = {
    # PRIMARY:
    'numBrightStars': [100, 150, 200, 250, 300],
    'maxOffsetPix': [150, 250, 400, 600],

    # SECONDARY (if primary optimized):
    'minMatchedPairs': [20, 30, 40],
    'matcherIterations': [3, 5, 7],
}

# Strategy:
# 1. Characterize initial WCS error:
#    - Measure typical offset on test images
#    - Set maxOffsetPix = measured_offset + 100 pixels
#    - This is now FIXED for remaining optimization
#
# 2. Grid search numBrightStars:
#    - Try [100, 150, 200, 250, 300]
#    - Measure time per image and success rate
#    - Choose lowest numBrightStars with >95% success

# Metrics:
# - Matching success rate (goal: >95%)
# - Time per image (goal: <1 minute)
# - RMS astrometric residuals (goal: <0.3 arcsec)
# - Number of matches found (goal: >50)

# Expected result:
# maxOffsetPix = 300 (depends on WCS quality)
# numBrightStars = 200 (balanced)
# matcherIterations = 5 (standard)
# minMatchedPairs = 30 (standard)
```

**Phase 5: WCS Distortion Model Optimization**
```python
# Goal: Optimal distortion correction

distortion_grid = {
    'wcsFitter.order': [1, 2, 3, 4],
}

# Test on subset with excellent astrometry

# Metrics:
# - Astrometric RMS across full field
# - Residuals vs. position (should be random, not systematic)
# - Residuals at field edges (worst case)

# Expected result:
# order=2 for moderate field size (Nickel ~12 arcmin)
# order=3 if significant field distortion evident
```

**Phase 6: Fine-Tuning and Edge Cases**
```python
# Test optimized configuration on diverse fields:

field_types = [
    'dense_galactic',  # Many stars, crowded
    'sparse_high_lat',  # Few stars
    'mixed_starsgals',  # Mixture
    'very_faint',  # Deep integration
    'bright_stars',  # Saturation challenges
]

# For each field type:
# - Verify pipeline succeeds
# - Measure quality metrics
# - Identify failure modes
# - Adjust parameters for problematic cases

# May need field-dependent configs:
# - Lower threshold for sparse fields
# - Higher threshold for crowded fields
# - More matcher stars for complex fields
```

### 11.2 Example: Complete Nickel Telescope Starting Configuration

```python
"""
LSST Science Pipelines Configuration for Nickel Telescope
Optimized for: 1-m telescope, ~12 arcmin field, 0.4"/pixel, 1.0" typical seeing
"""

# ============================================================================
# ISR CONFIGURATION
# ============================================================================

# Core corrections (validate these work with your calibrations)
config.isr.doBias = True
config.isr.doDark = True
config.isr.doFlat = True
config.isr.doLinearize = True  # If characterized
config.isr.doFringe = True  # Test per filter

# Saturation handling
config.isr.doSaturation = True
config.isr.growSaturationFootprintSize = 2  # Conservative

# Defect handling
config.isr.doDefect = True
config.isr.doInterpolate = True
config.isr.fwhm = 1.2  # Match typical seeing
config.isr.maskListToInterpolate = ['SAT', 'BAD', 'CR']

# Variance plane (essential for detection)
config.isr.doVariance = True

# Advanced corrections (enable if characterized)
config.isr.doCrosstalk = False  # Enable if measured
config.isr.doBrighterFatter = False  # Enable for precision work

# ============================================================================
# DETECTION CONFIGURATION
# ============================================================================

# Detection threshold (MOST CRITICAL PARAMETER)
config.detection.thresholdValue = 5.0  # Standard 5-sigma
config.detection.thresholdType = 'pixel_stdev'
config.detection.thresholdPolarity = 'positive'

# Footprint morphology
config.detection.minPixels = 1  # Accept single-pixel cores
config.detection.nSigmaToGrow = 2.4  # Capture PSF wings
config.detection.isotropicGrow = False  # Faster

# Background estimation
config.detection.background.binSize = 128  # Balanced
config.detection.background.algorithm = 'AKIMA_SPLINE'
config.detection.background.statisticsProperty = 'MEANCLIP'
config.detection.reEstimateBackground = False  # Save time

# ============================================================================
# PSF MEASUREMENT CONFIGURATION
# ============================================================================

# Star selector
config.measurePsf.starSelector.name = 'objectSize'
config.measurePsf.starSelector["objectSize"].sourceFluxField = 'base_GaussianFlux_instFlux'
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.15
config.measurePsf.starSelector["objectSize"].fluxMin = 10000.0  # Adjust for your images

# PSF determiner
config.measurePsf.psfDeterminer.name = 'psfex'
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2  # Quadratic variation
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.5  # 2× oversampling
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 256
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 256
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 300  # Good spatial sampling
config.measurePsf.psfDeterminer['psfex'].spatialReject = 3.0  # Outlier rejection

# ============================================================================
# ASTROMETRY CONFIGURATION
# ============================================================================

# Source selector
config.astrometry.sourceSelector.name = 'science'
config.astrometry.sourceSelector["science"].signalToNoiseMin = 10.0
config.astrometry.sourceSelector["science"].doFlags = True
config.astrometry.sourceSelector["science"].doUnresolved = True

# Pattern matcher (CRITICAL FOR SUCCESS)
config.astrometry.matcher.maxOffsetPix = 300  # Adjust based on your WCS error
config.astrometry.matcher.maxRotationDeg = 1.5  # Conservative
config.astrometry.matcher.numBrightStars = 200  # Balanced speed/robustness
config.astrometry.matcher.minMatchedPairs = 30  # Standard requirement
config.astrometry.matcher.minFracMatchedPairs = 0.3
config.astrometry.matcher.matcherIterations = 5  # Standard
config.astrometry.matcher.minMatchDistPixels = 1.0

# Reference catalog loader
config.astromRefObjLoader.pixelMargin = 400  # Must be > maxOffsetPix

# WCS fitter
config.astrometry.wcsFitter.order = 2  # Quadratic distortion
config.astrometry.wcsFitter.numIter = 3
config.astrometry.wcsFitter.rejSigma = 3.0

# Iteration control
config.astrometry.maxIter = 3
config.astrometry.matchDistanceSigma = 2.0

# ============================================================================
# PHOTOMETRY CONFIGURATION
# ============================================================================

config.photoCal.fluxField = 'slot_CalibFlux_instFlux'
config.photoCal.applyColorTerms = True
config.photoCal.nIter = 3
config.photoCal.nSigma = 3.0
config.photoCal.useMedian = True

# ============================================================================
# MEASUREMENT CONFIGURATION
# ============================================================================

# Aperture photometry radii (in pixels)
config.measurement.plugins['base_CircularApertureFlux'].radii = [3.0, 4.5, 6.0, 9.0, 12.0, 17.0, 25.0]

# Slots (what measurements to use)
config.measurement.slots.calibFlux = 'base_CircularApertureFlux_12_0'
config.measurement.slots.psfFlux = 'base_PsfFlux'
config.measurement.slots.shape = 'base_SdssShape'

# ============================================================================
# NOTES ON EXPECTED PERFORMANCE
# ============================================================================

"""
Expected metrics with this configuration:

Processing time:
- ~30-60 seconds per image (on modern hardware)
- Dominated by astrometry matcher (numBrightStars=200)

Success rates:
- Detection: >99% (will always succeed)
- PSF measurement: >98% (may fail in very sparse fields)
- Astrometry: >95% (depends on WCS quality)
- Photometry: >95% (depends on astrometry)

Quality metrics:
- Detection completeness: ~80% at S/N=5
- Astrometric RMS: <0.3 arcsec (0.75 pixels)
- Photometric scatter: ~0.03 mag (with good calibration)

Common failure modes:
1. Astrometry fails due to poor initial WCS
   → Solution: Increase maxOffsetPix to 500
2. PSF measurement fails in sparse fields
   → Solution: Lower signalToNoiseMin to 15.0
3. Too many/few detections
   → Solution: Adjust thresholdValue

Optimization priorities:
1. Verify ISR works well (check background, flat field quality)
2. Optimize detection threshold (completeness vs. purity)
3. Tune astrometry matcher (maxOffsetPix, numBrightStars)
4. Fine-tune PSF spatial order based on field tests
"""
```

### 11.3 Advanced: Multi-Objective Optimization

For systematic optimization across multiple objectives:

```python
from scipy.optimize import differential_evolution

def pipeline_objective(params):
    """
    Multi-objective function for pipeline optimization.

    Params:
        [0]: detection.thresholdValue
        [1]: psf.spatialOrder (discrete)
        [2]: astrometry.numBrightStars

    Returns: Combined score (lower is better)
    """

    # Set parameters
    config.detection.thresholdValue = params[0]
    config.measurePsf.psfDeterminer['psfex'].spatialOrder = int(params[1])
    config.astrometry.matcher.numBrightStars = int(params[2])

    # Run pipeline on test set
    results = run_pipeline_on_testset(config)

    # Compute objective components
    success_rate = results['fraction_successful']
    astrometric_rms = results['mean_rms_arcsec']
    processing_time = results['mean_time_seconds']

    # Multi-objective scoring (adjust weights as needed)
    score = (
        1000 * (1 - success_rate)  # Heavy penalty for failures
        + 10 * astrometric_rms      # Penalize poor accuracy
        + 0.1 * processing_time     # Small penalty for slow processing
    )

    return score

# Parameter bounds
bounds = [
    (3.0, 7.0),   # thresholdValue
    (0, 3),       # spatialOrder
    (100, 300),   # numBrightStars
]

# Optimize
result = differential_evolution(
    pipeline_objective,
    bounds,
    maxiter=50,
    popsize=10,
)

print(f"Optimal parameters: {result.x}")
print(f"Final score: {result.fun}")
```

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

---

This comprehensive reference provides complete understanding of the LSST Science Pipelines processing chain, with detailed explanations of what each component does, how they interact, and strategic guidance for parameter optimization specifically for the Nickel telescope.
