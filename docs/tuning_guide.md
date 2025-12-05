# LSST Science Pipelines Tuning and Optimization Guide

**Strategic guide for parameter optimization, troubleshooting, and understanding pipeline interactions**

**Companion to:** LSST Pipeline Parameter Reference Manual
**Focus:** How parameters interact, adjustment strategies, and optimization workflows

---

## Table of Contents

1. [Understanding Pipeline Dependencies](#1-understanding-pipeline-dependencies)
2. [Critical Parameter Interactions](#2-critical-parameter-interactions)
3. [Adjustment Strategies by Goal](#3-adjustment-strategies-by-goal)
4. [Common Failure Modes and Solutions](#4-common-failure-modes-and-solutions)
5. [Field-Specific Optimization](#5-field-specific-optimization)
6. [Performance vs. Quality Tradeoffs](#6-performance-vs-quality-tradeoffs)
7. [Systematic Optimization Workflows](#7-systematic-optimization-workflows)
8. [Troubleshooting Decision Trees](#8-troubleshooting-decision-trees)

---

## 1. Understanding Pipeline Dependencies

### 1.1 The Cascading Effect

**Fundamental principle:** Every stage depends on the quality of previous stages. Poor performance early in the pipeline cascades through all downstream processing.

```
ISR Quality
    ↓ (affects everything)
Detection Results
    ↓ (affects source list)
PSF Model Quality
    ↓ (affects measurements AND matching)
    ├──→ Astrometry Success
    │    ↓
    │    Photometry Success
    └──→ All Measurements
         ↓
    Final Catalog Quality
```

### 1.2 Critical Dependency Chains

**Chain 1: ISR → Detection → Everything**
- Bad flat fielding → False detections from dust shadows
- Unmasked saturated pixels → PSF contaminated by saturated stars
- Poor variance plane → Wrong detection thresholds
- **Impact:** Fix ISR FIRST before tuning anything else

**Chain 2: Detection → PSF → Measurements**
- Low detection threshold → Many noise detections → PSF contaminated
- High detection threshold → Few stars → PSF poorly sampled spatially
- Wrong background subtraction → Both false detections AND missed sources
- **Impact:** Detection threshold is the single most critical parameter

**Chain 3: Detection → Astrometry**
- Too few detections → Pattern matching fails (need ~50-200 sources)
- Too many artifacts → Confuses pattern matching
- Wrong source types (galaxies) → Don't match reference stars
- **Impact:** Astrometry needs the right NUMBER and TYPE of sources

**Chain 4: PSF → Everything**
- PSF used for: star/galaxy separation, deblending, PSF photometry, shape measurement
- Poor PSF model → ALL measurements degraded
- Spatially-varying PSF errors → Field-dependent systematic errors
- **Impact:** PSF quality affects every single measurement

**Chain 5: Astrometry → Photometry**
- No WCS → Can't match photometric reference stars
- Poor WCS → Wrong stars matched → Wrong zero point
- **Impact:** Photometry completely depends on astrometry success

### 1.3 Feedback Loops

**Loop 1: Detection → Background → Detection**
- Sources contaminate background → Poor background model
- Poor background → Wrong detection threshold → False detections
- **Solution:** Enable `reEstimateBackground` to iterate

**Loop 2: PSF Measurement Iteration**
- Initial star sample includes galaxies/artifacts
- Preliminary PSF fit identifies outliers
- Re-fit PSF excluding outliers → Better PSF
- **Built-in:** PSF measurement already iterates internally

**Loop 3: Astrometry Matching Iteration**
- Initial pattern match with loose tolerances
- Fit WCS, find outliers
- Re-match with tighter tolerances using improved WCS
- **Controlled by:** `maxIter` and `matchDistanceSigma`

### 1.4 Where Parameters Have Outsized Impact

**Critical Decision Point 1: Detection Threshold**
- Sets completeness/purity tradeoff for ENTIRE pipeline
- Affects: PSF star count, astrometry source count, catalog size
- **Most important single parameter to tune**

**Critical Decision Point 2: Astrometry numBrightStars**
- Computation scales as O(N³)
- Changing 100 → 200 → 400 increases time 8× → 64×
- **Most important for processing speed**

**Critical Decision Point 3: PSF spatialOrder**
- Controls whether field-dependent PSF captured
- Wrong choice → systematic errors across field
- **Most important for measurement quality**

**Critical Decision Point 4: Astrometry maxOffsetPix**
- Determines whether matching succeeds or fails completely
- Too small → total astrometry failure
- **Most critical for success rate**

---

## 2. Critical Parameter Interactions

### 2.1 Detection ↔ PSF Interaction

**The Problem:**
- Detection threshold too LOW → excess false detections → contaminate PSF stars
- Detection threshold too HIGH → miss faint stars → PSF poorly sampled

**The Balance:**
```python
# Scenario: Lower detection threshold to get more sources
config.detection.thresholdValue = 3.5  # From 5.0

# CONSEQUENCE: More noise detections contaminate PSF sample

# SOLUTION: Compensate by tightening PSF star selection
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 30.0  # From 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.12  # From 0.15

# RESULT: More sources detected, but only high-quality ones used for PSF
```

**Strategic Adjustment:**
1. Start with detection threshold that gives ~200-1000 sources
2. Check PSF measurement success rate
3. If PSF fails (contaminated): Tighten star selection OR raise detection threshold
4. If PSF fails (too few stars): Lower detection threshold OR loosen star selection

### 2.2 PSF ↔ Everything Interaction

**The Cascade:**
```
Poor PSF Model
    ├──→ PSF Photometry wrong
    │    └──→ Aperture corrections wrong
    │         └──→ ALL photometry systematically wrong
    │
    ├──→ Star/galaxy separation wrong
    │    └──→ Wrong sources for astrometry
    │         └──→ Astrometry fails
    │
    └──→ Deblending uses wrong PSF
         └──→ Crowded field photometry fails
```

**How to Diagnose PSF Problems:**
```python
# Symptom: Astrometry intermittently fails
# Check: Is PSF measurement succeeding?
# If PSF spatial pattern shows artifacts:
→ spatialOrder too high (overfitting)
→ Solution: Reduce spatialOrder

# Symptom: Photometry shows field-dependent systematics
# Check: Does PSF FWHM vary smoothly across field?
# If PSF constant but shouldn't be:
→ spatialOrder too low
→ Solution: Increase spatialOrder

# Symptom: Star/galaxy separation poor
# Check: Are PSF stars actually stars?
# If contaminated:
→ Tighten widthStdAllowed
→ Raise signalToNoiseMin
```

### 2.3 Astrometry Matcher Speed Interaction

**The Brutal Reality:**
```python
# Processing time scales as O(numBrightStars³)

numBrightStars = 50   → Time = 1×    (baseline)
numBrightStars = 100  → Time = 8×    (2³)
numBrightStars = 200  → Time = 64×   (4³)
numBrightStars = 400  → Time = 512×  (8³)

# Real-world example:
# numBrightStars=100: 5 seconds per image
# numBrightStars=200: 40 seconds per image
# numBrightStars=400: 5 minutes per image
```

**Multi-Parameter Speed Optimization:**
```python
# FAST configuration (5-10 seconds per image):
config.astrometry.matcher.numBrightStars = 100
config.astrometry.matcher.maxOffsetPix = 150  # If WCS good
config.astrometry.matcher.matcherIterations = 3
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 150
config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0

# CONSEQUENCE: May fail ~5% of time
# USE WHEN: Processing thousands of images, can tolerate some failures

# ROBUST configuration (1-2 minutes per image):
config.astrometry.matcher.numBrightStars = 300
config.astrometry.matcher.maxOffsetPix = 500
config.astrometry.matcher.matcherIterations = 7
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 3
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 400
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.5

# CONSEQUENCE: Much slower but >99% success rate
# USE WHEN: Critical data, can't afford failures
```

### 2.4 Background ↔ Detection Interaction

**The Problem:**
```
Large binSize → Smooth background → Subtracts real structure
Small binSize → Detailed background → Sensitive to noise
```

**Field-Dependent Optimization:**
```python
# Fields WITH extended sources (galaxies, nebulae):
config.detection.background.binSize = 256  # Large
# Reason: Avoid subtracting galaxy light as "background"
# Consequence: May have false detections in galaxy halos
# Compensate: Raise detection threshold slightly
config.detection.thresholdValue = 5.5

# Fields WITHOUT extended sources (stellar fields):
config.detection.background.binSize = 128  # Medium
config.detection.thresholdValue = 5.0  # Standard

# Very crowded stellar fields:
config.detection.background.binSize = 64  # Small
# Reason: Need local background between stars
# Consequence: More computational time
# Benefit: Better detection in crowded regions
```

### 2.5 Matcher Tolerance ↔ Match Requirements

**The Tension:**
```python
# Loose matching tolerances:
config.astrometry.matcher.maxOffsetPix = 600  # Large search
config.astrometry.matcher.maxRotationDeg = 3.0  # Large rotation

# PROBLEM: More false pattern matches possible
# SOLUTION: Require more matches for confidence
config.astrometry.matcher.minMatchedPairs = 50  # From 30
config.astrometry.matcher.minFracMatchedPairs = 0.4  # From 0.3

# Tight matching tolerances:
config.astrometry.matcher.maxOffsetPix = 150  # Small search
config.astrometry.matcher.maxRotationDeg = 0.5  # Small rotation

# BENEFIT: Fewer false matches
# CONSEQUENCE: May fail if WCS worse than expected
# SOLUTION: Can lower match requirements
config.astrometry.matcher.minMatchedPairs = 20  # More permissive
```

### 2.6 WCS Fitter Order ↔ Number of Matches

**The Constraint:**
```python
# WCS parameters by order:
# order 0: 6 parameters
# order 1: 12 parameters
# order 2: 20 parameters
# order 3: 30 parameters
# order 4: 42 parameters

# Rule: Need ≥ 3× parameters in matches for stable fit

# Scenario: Sparse field with ~40 typical matches
config.astrometry.wcsFitter.order = 2  # 20 parameters
# 40 matches ÷ 20 parameters = 2× → BORDERLINE

# Options:

# Option A: Use simpler model
config.astrometry.wcsFitter.order = 1  # 12 parameters
# 40 matches ÷ 12 parameters = 3.3× → SAFE

# Option B: Get more matches
config.astrometry.matcher.minMatchedPairs = 20  # From 30, more permissive
config.detection.thresholdValue = 4.0  # From 5.0, more sources
# May get 60 matches → 60 ÷ 20 = 3× → SAFE
```

---

## 3. Adjustment Strategies by Goal

### 3.1 Goal: Maximize Completeness (Faint Source Detection)

**Strategy: Aggressive detection, careful filtering**

```python
# Step 1: Lower detection threshold
config.detection.thresholdValue = 3.5  # From 5.0
config.detection.minPixels = 1  # Accept small detections

# Step 2: Capture full PSF
config.detection.nSigmaToGrow = 3.0  # From 2.4

# Step 3: BUT filter PSF stars carefully
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 25.0  # Stricter
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.12  # Tighter

# Step 4: Accept that astrometry has more sources
# May need to allow more matcher stars
config.astrometry.matcher.numBrightStars = 250  # From 200

# Expected outcome:
# - Catalog 20-30% more sources
# - False positive rate increases 2-3×
# - PSF measurement still robust (filtered)
# - Processing time +30%
```

### 3.2 Goal: Maximize Processing Speed

**Strategy: Reduce computation without breaking pipeline**

```python
# Step 1: Aggressive astrometry speedup (biggest impact)
config.astrometry.matcher.numBrightStars = 100  # From 200
# 8× speedup on astrometry

# Step 2: Simplify PSF model
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1  # From 2
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 150  # From 300
config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0  # From 0.5

# Step 3: Reduce source count (if acceptable)
config.detection.thresholdValue = 6.0  # From 5.0
# Fewer sources → faster measurement

# Step 4: Simplify WCS (if field small)
config.astrometry.wcsFitter.order = 1  # From 2

# Expected outcome:
# - Total processing time reduced 5-10×
# - Success rate may drop 2-5%
# - Catalog completeness reduced 10-20%
# - Acceptable for: bulk processing, QA checks
```

### 3.3 Goal: Maximize Success Rate (Robustness)

**Strategy: Permissive parameters, multiple attempts**

```python
# Step 1: Permissive detection
config.detection.thresholdValue = 4.5  # Moderate, not too low

# Step 2: Permissive PSF star selection
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0  # Lower
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.18  # Looser

# Step 3: Robust astrometry (slower but more reliable)
config.astrometry.matcher.maxOffsetPix = 500  # Large search
config.astrometry.matcher.numBrightStars = 250  # Many patterns
config.astrometry.matcher.matcherIterations = 7  # More attempts
config.astrometry.matcher.minMatchedPairs = 25  # Lower requirement
config.astrometry.matcher.minFracMatchedPairs = 0.25  # Lower fraction

# Step 4: Simple, robust WCS
config.astrometry.wcsFitter.order = 2  # Standard, not too complex

# Expected outcome:
# - Success rate >98% (vs. ~95% with defaults)
# - Processing time +50-100%
# - Quality still good (not optimal)
# - Use for: production pipelines, heterogeneous data
```

### 3.4 Goal: Maximize Precision (Science-Grade)

**Strategy: Strict requirements, iterative refinement**

```python
# Step 1: Moderate detection for clean sources
config.detection.thresholdValue = 5.0  # Standard
config.detection.reEstimateBackground = True  # Iterate background

# Step 2: High-quality PSF stars only
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 30.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.10
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 3  # Capture variation
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 400  # Many stars
config.measurePsf.psfDeterminer['psfex'].samplingSize = 0.5  # High resolution

# Step 3: High-order astrometry
config.astrometry.wcsFitter.order = 3  # Capture distortion
config.astrometry.wcsFitter.rejSigma = 2.5  # Aggressive outlier rejection

# Step 4: High-quality photometry
config.photoCal.nSigma = 2.5  # Aggressive outlier rejection
config.photoCal.useMedian = True  # Robust

# Expected outcome:
# - Best possible astrometry and photometry
# - May fail 5-10% of time (strict requirements)
# - Processing time 2-3× longer
# - Use for: key science data, publications
```

---

## 4. Common Failure Modes and Solutions

### 4.1 Complete Astrometry Failure

**Symptom:** "No astrometric solution found" or "Pattern matching failed"

**Diagnosis Cascade:**

```
Astrometry Failed
    ↓
Check 1: Is initial WCS completely wrong?
    Test: Increase maxOffsetPix to 1000
    If works → Problem is initial WCS
    Solution: Fix WCS headers or use blind solver
    ↓
Check 2: Are there enough detected sources?
    Test: Lower detection.thresholdValue to 4.0
    If works → Problem is too few sources
    Solution: Adjust detection threshold permanently
    ↓
Check 3: Are sources the wrong type?
    Test: Check if detecting mostly galaxies
    If yes → Problem is source selection
    Solution: Enable doUnresolved in source selector
    ↓
Check 4: Is reference catalog missing?
    Test: Check logs for "loaded N reference objects"
    If N=0 → Problem is reference catalog or pixelMargin
    Solution: Increase pixelMargin or check field position
    ↓
Check 5: Is matcher too strict?
    Test: Increase numBrightStars to 300, iterations to 7
    If works → Problem is matcher configuration
    Solution: Use more robust matcher settings
```

**Complete Solution Example:**
```python
# Comprehensive fix for problematic astrometry:

# 1. Ensure sufficient sources
config.detection.thresholdValue = 4.5
config.astrometry.sourceSelector["science"].signalToNoiseMin = 10.0

# 2. Allow large search (if WCS uncertain)
config.astrometry.matcher.maxOffsetPix = 500
config.astromRefObjLoader.pixelMargin = 600  # Must be larger!

# 3. Use more stars for robustness
config.astrometry.matcher.numBrightStars = 250

# 4. More permissive matching
config.astrometry.matcher.minMatchedPairs = 25
config.astrometry.matcher.minFracMatchedPairs = 0.25
config.astrometry.matcher.matcherIterations = 7

# 5. Allow uncertain orientation
config.astrometry.matcher.maxRotationDeg = 2.0
```

### 4.2 PSF Measurement Failure

**Symptom:** "Unable to determine PSF" or very poor PSF model

**Diagnosis Cascade:**

```
PSF Failed
    ↓
Check 1: Are there enough PSF candidates?
    Look in logs: "Selected N PSF stars"
    If N < 30 → Not enough stars
    Solutions:
        - Lower signalToNoiseMin to 15.0
        - Lower detection.thresholdValue
    ↓
Check 2: Are PSF candidates contaminated?
    Test: Inspect PSF star images visually
    If many galaxies → Star selection too loose
    Solutions:
        - Tighten widthStdAllowed to 0.10
        - Raise signalToNoiseMin to 25.0
    ↓
Check 3: Is spatial order too high?
    Test: Reduce spatialOrder to 1
    If works → Overfitting with too few stars
    Solution: Either lower spatialOrder OR get more stars
    ↓
Check 4: Are there bad regions in images?
    Test: Check if PSF stars near detector edges/defects
    If yes → Bad pixel regions contaminating PSF
    Solution: Improve ISR (better masking)
```

**Complete Solution Example:**
```python
# Fix for challenging PSF measurement:

# 1. Get enough stars (but not too many)
config.detection.thresholdValue = 4.5
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.15

# 2. Use appropriate spatial complexity
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
# Or 1 if fewer than 50 stars typically available

# 3. Allow sufficient PSF stars
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 200

# 4. Reasonable outlier rejection
config.measurePsf.psfDeterminer['psfex'].spatialReject = 3.0
```

### 4.3 Excessive False Detections

**Symptom:** Catalog has thousands of obvious artifacts

**Causes and Solutions:**

```
Too Many False Detections
    ↓
Cause 1: Detection threshold too low
    Check: Overlay detections on image
    If detecting obvious noise → Threshold too low
    Solution:
        config.detection.thresholdValue = 6.0  # Raise

Cause 2: Background over-subtracted
    Check: Look for "holes" where sources should be
    If yes → Background subtraction too aggressive
    Solution:
        config.detection.background.binSize = 256  # Larger

Cause 3: Bad ISR (artifacts appearing as sources)
    Check: Look for patterns (satellite trails, diffraction spikes)
    If yes → ISR problem
    Solution:
        Improve ISR masking
        config.isr.growSaturationFootprintSize = 3  # Larger

Cause 4: PSF interpolation creating artifacts
    Check: Look near masked regions
    If yes → Interpolated regions detected as sources
    Solution:
        config.detection.background.binSize = 256
        OR grow masked regions before detection
```

### 4.4 Processing Extremely Slow

**Symptom:** Each image takes >5 minutes

**Diagnosis:**

```
Slow Processing
    ↓
Check 1: Is astrometry slow?
    Time just the astrometry step
    If >80% of time → numBrightStars too high
    Solution:
        config.astrometry.matcher.numBrightStars = 100
        # 8× speedup
    ↓
Check 2: Is PSF measurement slow?
    Time the PSF step
    If >20% of time → PSF configuration
    Solutions:
        config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
        config.measurePsf.psfDeterminer['psfex'].maxCandidates = 150
        config.measurePsf.psfDeterminer['psfex'].samplingSize = 1.0
    ↓
Check 3: Is measurement slow?
    Count number of detected sources
    If >10,000 sources → Detection threshold too low
    Solution:
        config.detection.thresholdValue = 6.0  # Raise
    ↓
Check 4: Is background subtraction slow?
    Check if reEstimateBackground enabled
    If yes → Disable for speed
    Solution:
        config.detection.reEstimateBackground = False
```

---

## 5. Field-Specific Optimization

### 5.1 Dense Stellar Fields (Galactic Plane)

**Challenges:**
- Very crowded (>1000 sources per image)
- Many blended sources
- High stellar density confuses background estimation

**Optimized Configuration:**
```python
# Detection: Higher threshold to manage catalog size
config.detection.thresholdValue = 6.0  # Higher than standard
config.detection.background.binSize = 64  # Smaller for local background
config.detection.nSigmaToGrow = 2.0  # Smaller to reduce blending

# PSF: Can be picky (plenty of stars)
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 25.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.12  # Tight
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 300

# Astrometry: Many sources available
config.astrometry.matcher.numBrightStars = 200  # Standard
config.astrometry.matcher.minMatchedPairs = 40  # Can require more

# Expected: 500-2000 sources, good PSF, slow measurement
```

### 5.2 Sparse Fields (High Galactic Latitude)

**Challenges:**
- Few sources (<100 per image)
- May not have enough PSF stars
- Astrometry may struggle with few patterns

**Optimized Configuration:**
```python
# Detection: Lower threshold to find more sources
config.detection.thresholdValue = 4.0  # Lower than standard
config.detection.background.binSize = 256  # Larger (smoother)
config.detection.nSigmaToGrow = 2.4  # Standard

# PSF: Must be permissive (few stars available)
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0  # Lower
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.18  # Looser
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1  # Simple
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 100
config.measurePsf.psfDeterminer['psfex'].sizeCellX = 512  # Larger cells
config.measurePsf.psfDeterminer['psfex'].sizeCellY = 512

# Astrometry: Need every source
config.astrometry.matcher.numBrightStars = 150  # Fewer (limited sources)
config.astrometry.matcher.minMatchedPairs = 20  # Lower requirement
config.astrometry.matcher.minFracMatchedPairs = 0.25

# Expected: 50-200 sources, simple PSF, fast processing
```

### 5.3 Mixed Star/Galaxy Fields

**Challenges:**
- Galaxies contaminate star selection
- Reference catalog (Gaia) only has stars
- Star/galaxy separation critical

**Optimized Configuration:**
```python
# Detection: Moderate threshold
config.detection.thresholdValue = 5.0  # Standard
config.detection.background.binSize = 256  # Avoid subtracting galaxies

# PSF: Strict star selection (filter galaxies)
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.12  # Tight
# ObjectSize selector uses clustering → should separate stars/galaxies

# Astrometry: Use only unresolved sources
config.astrometry.sourceSelector["science"].doUnresolved = True
config.astrometry.sourceSelector["science"].signalToNoiseMin = 12.0

# PSF spatial variation important (galaxies skew local PSF if not filtered)
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2

# Expected: Mixed catalog, but clean PSF and astrometry
```

### 5.4 Deep Images (Long Exposures)

**Challenges:**
- Can detect very faint sources (S/N ~ 3)
- Many detections → slow processing
- Cosmic rays and artifacts more problematic

**Optimized Configuration:**
```python
# Detection: Can use lower threshold (high S/N available)
config.detection.thresholdValue = 4.0  # Lower (good S/N)
config.detection.background.binSize = 128  # Standard

# BUT: Will get many detections → manage catalog size
# Option: Raise threshold for speed, or accept longer processing

# PSF: Can be very selective (many high-S/N stars)
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 50.0  # Very high
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.10  # Very tight
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 400  # Many available

# Cosmic rays: More aggressive
config.repair.cosmicray.minSigma = 5.0  # Lower (more sensitive)
config.repair.cosmicray.niteration = 5  # More iterations

# Expected: Large catalog (1000-5000 sources), excellent PSF, slow
```

### 5.5 Shallow Images (Short Exposures)

**Challenges:**
- High noise (limited S/N)
- Few faint sources detectable
- May struggle to get enough PSF stars

**Optimized Configuration:**
```python
# Detection: Moderate threshold (balance noise vs. completeness)
config.detection.thresholdValue = 5.5  # Slightly higher
config.detection.minPixels = 2  # Require multi-pixel (filter noise)

# PSF: Must use available stars (can't be too picky)
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 15.0  # Lower
config.measurePsf.starSelector["objectSize"].widthStdAllowed = 0.15  # Standard
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1  # Simple (few stars)

# Astrometry: May need to be permissive
config.astrometry.matcher.minMatchedPairs = 25  # Lower requirement

# Expected: Smaller catalog (100-500 sources), simpler PSF, fast
```

---

## 6. Performance vs. Quality Tradeoffs

### 6.1 The Pareto Frontier

**Understanding the tradeoff space:**

```
Quality Axis (Astrometric RMS):
    │
0.1"│                                    ● (Slow, Best)
    │                               ●
0.2"│                          ●
    │                     ●
0.3"│                ●
    │           ●
0.4"│      ● (Fast, Acceptable)
    │  ●
0.5"│●
    └────────────────────────────────────────→
      10s  30s  1m   2m   5m  10m  30m        Processing Time

Key insight: Diminishing returns after ~1 minute processing
```

### 6.2 Configuration Profiles

**Profile 1: Fast & Acceptable (10-20 seconds)**
```python
config.astrometry.matcher.numBrightStars = 100
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 1
config.detection.thresholdValue = 5.5
# Success rate: ~93%
# Astrometric RMS: ~0.35"
# Use case: Bulk processing, initial QA
```

**Profile 2: Balanced (30-60 seconds)**
```python
config.astrometry.matcher.numBrightStars = 200
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.detection.thresholdValue = 5.0
# Success rate: ~96%
# Astrometric RMS: ~0.25"
# Use case: Standard production pipeline (RECOMMENDED)
```

**Profile 3: Robust (1-2 minutes)**
```python
config.astrometry.matcher.numBrightStars = 250
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.astrometry.matcher.matcherIterations = 7
config.detection.thresholdValue = 4.5
# Success rate: ~98%
# Astrometric RMS: ~0.23"
# Use case: Heterogeneous data, maximize success
```

**Profile 4: Best Quality (2-5 minutes)**
```python
config.astrometry.matcher.numBrightStars = 300
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 3
config.measurePsf.psfDeterminer['psfex'].maxCandidates = 400
config.astrometry.wcsFitter.order = 3
config.detection.reEstimateBackground = True
# Success rate: ~96% (strict requirements)
# Astrometric RMS: ~0.18"
# Use case: Science-grade final reductions
```

### 6.3 Speed Optimization Checklist

**Fastest speedups (do these first):**
1. **numBrightStars: 200 → 100** → 8× faster astrometry
2. **spatialOrder: 2 → 1** → 2× faster PSF
3. **thresholdValue: 5.0 → 6.0** → 2× fewer sources → 2× faster measurement

**Moderate speedups:**
4. **maxCandidates: 300 → 150** → 1.5× faster PSF
5. **samplingSize: 0.5 → 1.0** → 2× faster PSF
6. **reEstimateBackground: True → False** → 1.3× faster detection

**Minimal speedups (not worth it unless desperate):**
7. **wcsFitter.order: 2 → 1** → 1.1× faster
8. **matcherIterations: 5 → 3** → 1.2× faster

### 6.4 Quality Optimization Checklist

**Biggest quality improvements:**
1. **spatialOrder: 1 → 2** → Capture field-dependent PSF
2. **detection.thresholdValue: 6.0 → 4.5** → Better completeness
3. **wcsFitter.order: 2 → 3** → Better distortion correction
4. **maxCandidates: 150 → 400** → Better PSF spatial sampling

**Moderate improvements:**
5. **reEstimateBackground: False → True** → Better background model
6. **signalToNoiseMin: 15 → 25** → Cleaner PSF stars
7. **samplingSize: 1.0 → 0.5** → Higher PSF resolution

---

## 7. Systematic Optimization Workflows

### 7.1 The Five-Phase Optimization

**Phase 1: Validate ISR (One-Time)**
```
Goal: Ensure ISR produces good images before tuning anything else

1. Process ~10 images with standard ISR configuration
2. Check metrics:
   - Background mean ≈ 0 (within ±10 counts)
   - Background RMS matches expected Poisson + read noise
   - No obvious artifacts (ripples, gradients, patterns)
   - Bright stars have smooth profiles
3. If ISR looks bad → Fix ISR first (flats, bias, calibrations)
4. If ISR looks good → Proceed to Phase 2
```

**Phase 2: Optimize Detection Threshold**
```
Goal: Find optimal detection threshold (single most critical parameter)

1. Try thresholdValue = [3.0, 4.0, 5.0, 6.0, 7.0]
2. For each, measure:
   - Number of detections (target: 200-1000)
   - Visual: Missing obvious sources?
   - Visual: Detecting noise?
   - PSF measurement success rate
   - Astrometry success rate
3. Select threshold where:
   - PSF measurement succeeds
   - Astrometry succeeds
   - Not detecting obvious noise
   - Not missing obvious sources
4. Typical result: thresholdValue ≈ 4.5-5.5
```

**Phase 3: Tune PSF Measurement**
```
Goal: Optimize PSF quality

1. Fix detection threshold from Phase 2
2. Vary spatialOrder = [0, 1, 2, 3]
3. For each, measure:
   - PSF FWHM vs. position (should vary smoothly)
   - PSF model residuals (RMS < 5% of peak)
   - Number of PSF stars used (target: 50-300)
4. Select spatialOrder where:
   - Residuals minimized
   - No systematic spatial patterns in residuals
   - Doesn't overfit (order N+1 ≈ order N)
5. Typical result: spatialOrder = 1-2

6. Fine-tune star selection:
   - If PSF uses <50 stars: Lower signalToNoiseMin
   - If PSF contaminated: Tighten widthStdAllowed
```

**Phase 4: Optimize Astrometry Matcher**
```
Goal: Balance speed vs. success rate

1. Characterize initial WCS error:
   - Plot sources overlaid on predicted positions
   - Measure typical offset
   - Set maxOffsetPix = measured_offset + 100
2. Try numBrightStars = [100, 150, 200, 250, 300]
3. For each, measure:
   - Success rate (target: >95%)
   - Processing time per image
   - Astrometric RMS residuals
4. Select lowest numBrightStars with >95% success
5. Typical result: numBrightStars = 150-250

6. If success rate still low (<95%):
   - Increase matcherIterations to 7
   - Lower minMatchedPairs to 25
   - Increase maxOffsetPix
```

**Phase 5: Validate on Diverse Fields**
```
Goal: Ensure configuration works across field types

1. Test on representative sample:
   - Dense stellar fields
   - Sparse fields
   - Mixed star/galaxy fields
   - Different exposure times
2. Measure failure rate by field type
3. If specific field type problematic:
   - Create field-specific config override
   - Or adjust global config for worst case
4. Final validation metrics:
   - Overall success rate >95%
   - Astrometric RMS <0.3" (for ~0.4"/pixel)
   - Processing time acceptable for throughput
```

### 7.2 Iterative Refinement Loop

**For ongoing optimization:**

```
MEASURE → ANALYZE → ADJUST → REPEAT

1. MEASURE:
   Process batch of images
   Log: Success/failure for each stage
   Record: Metrics (RMS, time, counts)

2. ANALYZE:
   Which stage fails most often?
   What are typical failure modes?
   Where is time spent?

3. ADJUST:
   If astrometry fails: Adjust matcher
   If PSF fails: Adjust star selection
   If too slow: Reduce numBrightStars
   If quality poor: Increase complexity

4. REPEAT:
   Process same batch with new config
   Compare metrics
   Did it improve?

Continue until metrics meet requirements
```

### 7.3 Multi-Objective Optimization

**When you need to balance multiple goals:**

```python
def score_configuration(config_params):
    """
    Score configuration balancing success, quality, speed
    """

    # Run pipeline on test set
    results = process_testset(config_params)

    # Component scores (lower is better)
    failure_penalty = 1000 * (1 - results.success_rate)
    quality_score = 10 * results.astrometric_rms
    speed_penalty = 0.1 * results.mean_time_seconds

    # Combined score with weights
    total_score = failure_penalty + quality_score + speed_penalty

    return total_score

# Grid search or optimization
best_config = optimize(score_configuration, parameter_bounds)
```

---

## 8. Troubleshooting Decision Trees

### 8.1 Pipeline Completely Fails

```
Pipeline Failed
    ↓
Which stage failed?
    ↓
┌──────┬────────────┬──────────────┬─────────────┐
│      │            │              │             │
ISR   Detection   PSF          Astrometry    Measurement
│      │            │              │             │
↓      ↓            ↓              ↓             ↓
See    See          See            See           See
8.2    8.3          8.4            8.5           8.6
```

### 8.2 ISR Failures

```
ISR Failed
    ↓
Check error message
    ↓
┌─────────────┬──────────────┬────────────────┐
│             │              │                │
"No bias"   "No flat"   "Variance NaN"    Other
│             │              │                │
↓             ↓              ↓                ↓
Calibration Missing calibs  Bad pixels    Check logs
files       Set do*=False   Check ISR     Contact
missing     for testing     masking       experts
```

### 8.3 Detection Failures (Rare)

```
Detection "Failed"
(Usually just gives unexpected results, doesn't error)
    ↓
What's the symptom?
    ↓
┌─────────────┬──────────────┬────────────────┐
│             │              │                │
No sources  Too many      Wrong          Pattern
detected    sources       background     in results
│             │              │                │
↓             ↓              ↓                ↓
Lower      Raise         Adjust          Check for
threshold  threshold     binSize         artifacts
          or check       reEstimate      in ISR
          threshType     Background
```

### 8.4 PSF Measurement Failures

```
PSF Failed
    ↓
Error: "Too few stars"?
    ↓
Yes → Lower signalToNoiseMin
      Or lower detection threshold
      Or loosen widthStdAllowed
    ↓
No → Error: "Cannot determine PSF"?
    ↓
    Yes → Check: spatialOrder too high?
          Try: spatialOrder = 1
          Or: Increase maxCandidates
    ↓
    No → Error: "PSF fit diverged"?
        ↓
        Yes → spatialReject too low
              Or stars contaminated
              Tighten star selection
```

### 8.5 Astrometry Failures

```
Astrometry Failed
    ↓
Stage 1: Pattern matching or WCS fitting?
Check error message
    ↓
┌────────────────────┬─────────────────────┐
│                    │                     │
"No pattern       "Insufficient        "WCS fit
matches"           matches"             failed"
│                    │                     │
↓                    ↓                     ↓
Increase:          Lower:                Lower:
maxOffsetPix       minMatchedPairs       wcsFitter.order
numBrightStars     minFracMatched        Or check if
matcherIterations  Or lower              matches are
                   detection             actually wrong
                   threshold             (false matches)
```

### 8.6 Measurement Failures

```
Measurement Stage Issues
(Rarely fails completely, but may have poor results)
    ↓
Symptom?
    ↓
┌─────────────┬──────────────┬────────────────┐
│             │              │                │
Slow        Wrong fluxes   Wrong shapes   Flags set
│             │              │                │
↓             ↓              ↓                ↓
Too many    Check PSF      Check PSF      Check which
sources     model          model          flags
Raise       quality        quality        Often normal
threshold   Re-tune PSF    Re-tune PSF    (sources near
                                          bad regions)
```

---

## Summary: The Strategic Framework

### Golden Rules of Pipeline Optimization

1. **Fix ISR first** - Everything downstream depends on clean images
2. **Detection threshold is king** - Affects everything else
3. **Speed comes from numBrightStars** - 8× difference for 2× change
4. **Quality comes from PSF spatialOrder** - But can overfit
5. **Always validate on diverse fields** - One config rarely fits all

### The Essential Parameters (Top 5)

If you can only tune 5 parameters, tune these:

1. **config.detection.thresholdValue** - Completeness/purity tradeoff
2. **config.astrometry.matcher.maxOffsetPix** - Success vs. failure
3. **config.astrometry.matcher.numBrightStars** - Speed vs. robustness
4. **config.measurePsf.psfDeterminer['psfex'].spatialOrder** - PSF quality
5. **config.measurePsf.starSelector["objectSize"].signalToNoiseMin** - PSF star quality

### Quick Start for Nickel Telescope

```python
# Phase 1: Validate ISR works
# Phase 2: Start with these and measure performance:

config.detection.thresholdValue = 5.0
config.astrometry.matcher.maxOffsetPix = 300  # Adjust based on your WCS
config.astrometry.matcher.numBrightStars = 200
config.measurePsf.psfDeterminer['psfex'].spatialOrder = 2
config.measurePsf.starSelector["objectSize"].signalToNoiseMin = 20.0

# Phase 3: Adjust based on:
# - Success rate >95%? If no → more robust settings
# - Too slow? → Reduce numBrightStars to 150
# - Poor PSF? → Check star selection and spatialOrder
# - Astrometry fails? → Increase maxOffsetPix

# Phase 4: Fine-tune remaining parameters
# Phase 5: Validate across field types
```

### When to Stop Optimizing

You've reached optimal configuration when:
- Success rate >95% across diverse fields
- Processing time acceptable for your throughput
- Astrometric RMS <0.5 × pixel scale
- Further parameter changes don't improve metrics
- You understand failure modes (know what breaks and why)

**Remember:** Perfect is the enemy of good. A robust 95% success config is better than a fragile 98% config that breaks on edge cases.
