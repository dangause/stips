# Quick Start Guide: Nickel Spline Color Terms

This guide will walk you through computing and implementing better color terms for your Nickel telescope.

## What You're Getting

A complete system to compute **spline-based color transformations** from Nickel BVRI to Monster catalog, using:
- Real filter throughput curves from SVO
- Stellar template SEDs (SDSS + Kurucz)
- Monster's proven spline-fitting methodology

## Files Included

1. **nickel_colorterm_fitter.py** - Main computation script
2. **convert_to_lsst_colorterms.py** - Converts results to LSST format
3. **example_run_nickel_colorterms.sh** - Example run script
4. **NICKEL_COLORTERMS_README.md** - Full documentation

## Step-by-Step Instructions

### Step 1: Install Dependencies

```bash
# Basic Python packages
pip install numpy scipy matplotlib astropy fitsio astroquery pyyaml scikit-learn

# For stellar templates
pip install fgcm
```

### Step 2: Locate Your Monster Throughputs

You need the Monster throughput directory. It should contain files like:
- `total_g.dat`, `total_r.dat`, `total_i.dat`, `total_z.dat`, `total_y.dat`
- OR: `total_comcam_g.ecsv`, `total_comcam_r.ecsv`, etc.

This is typically at:
```
the_monster/data/throughputs/
```

### Step 3: Run the Fitter

Edit `example_run_nickel_colorterms.sh` and set the path to your Monster throughputs:

```bash
MONSTER_THROUGHPUT_DIR="/path/to/the_monster/data/throughputs"
```

Then run:

```bash
./example_run_nickel_colorterms.sh
```

This will:
1. Download Nickel filter curves from SVO
2. Load stellar templates
3. Compute synthetic photometry
4. Fit spline color terms
5. Generate QA plots
6. Save results

### Step 4: Review the Results

Check the output directory (default: `./nickel_colorterms_output/`):

```bash
# View the QA plots
open nickel_colorterms_output/*.png

# Read the summary
cat nickel_colorterms_output/nickel_colorterms_summary.txt
```

**Look for:**
- Smooth curves in the plots (not oscillating wildly)
- Reasonable correction factors (near 1.0, varying smoothly with color)
- Good coverage across the color range

### Step 5: Convert to LSST Format

```bash
python convert_to_lsst_colorterms.py \
    --input-dir ./nickel_colorterms_output \
    --output colorterms_monster.py
```

This creates a file compatible with `obs_nickel/configs/colorterms.py`.

### Step 6: Integrate into obs_nickel

**Option A: Replace existing monster color terms**

```bash
# Backup your current file
cp obs_nickel/configs/colorterms.py obs_nickel/configs/colorterms.py.backup

# Copy in the new monster section
# Edit colorterms.py and replace the "*monster*" section with the new one
```

**Option B: Keep both for testing**

Add the new color terms with a different name pattern:

```python
config.data = {
    # ... existing entries ...

    "*monster_spline*": ColortermDict(
        data={
            # ... your new color terms ...
        }
    ),
}
```

Then in your pipeline config, switch between them:
```python
config.photometry.photoCatName = "the_monster_20250219_local"  # uses "*monster*"
# OR
config.photometry.photoCatName = "the_monster_spline"  # uses "*monster_spline*"
```

## Testing Your New Color Terms

### 1. Check on a Test Field

Run your pipeline on a small test field with known photometry:

```bash
pipetask run \
  -b "$REPO" \
  -i "Nickel/raw/all,Nickel/calib/current" \
  -o "Nickel/test_new_colorterms" \
  -p pipelines/DRP.yaml#processCcd \
  -d "visit=12345" \
  -j 1
```

### 2. Compare Photometry

Look at:
- Residuals vs. Monster catalog
- Any systematic trends with color
- RMS scatter

```python
# Example analysis
import matplotlib.pyplot as plt

# Load your calibrated photometry and Monster catalog
# Match sources
# Plot residuals

plt.scatter(color, mag_nickel - mag_monster, alpha=0.5)
plt.xlabel('Color')
plt.ylabel('Nickel - Monster (mag)')
plt.axhline(0, color='r', linestyle='--')
plt.show()
```

### 3. Expected Improvements

With spline color terms, you should see:
- **Smaller RMS** scatter vs. Monster
- **No systematic trends** with color (especially at blue/red extremes)
- **Better photometry** for M-dwarfs and hot white dwarfs

## Common Issues and Solutions

### Issue: "Could not find stellar templates"

**Solution:** Install fgcm
```bash
pip install fgcm
```

### Issue: "Could not find Monster throughput"

**Solution:** Check your throughput directory path and file names. The script looks for:
- `total_*.dat`
- `total_comcam_*.ecsv`

### Issue: "Not enough valid data points"

**Solution:** Reduce the number of nodes:
```bash
python nickel_colorterm_fitter.py \
    --monster-throughput-dir /path/to/throughputs \
    --n-nodes 3  # Instead of 4
```

### Issue: Spline oscillates wildly in QA plots

**Solution:** This is overfitting. Try:
1. Fewer nodes (`--n-nodes 3`)
2. Check your throughput files are correct
3. Make sure stellar templates loaded properly

### Issue: Poor match to real data

**Possible causes:**
1. Nickel throughputs from SVO don't match your actual telescope
2. CCD quantum efficiency not accounted for
3. Need site-specific corrections

**Solutions:**
1. Get measured Nickel throughputs (including CCD QE)
2. Measure empirical color terms from standard star fields
3. Combine synthetic + empirical approach

## Advanced: Using Custom Throughputs

If you have measured Nickel throughputs (better than SVO):

```python
# Modify nickel_colorterm_fitter.py

# Replace this line:
self.synth.load_nickel_throughputs_from_svo()

# With:
self.synth.load_nickel_throughputs_from_files({
    'B': '/path/to/nickel_B_throughput.dat',
    'V': '/path/to/nickel_V_throughput.dat',
    'R': '/path/to/nickel_R_throughput.dat',
    'I': '/path/to/nickel_I_throughput.dat',
})
```

File format: Two columns (wavelength in Angstroms, throughput 0-1)

## Advanced: Combining with Empirical Data

For the best results, combine synthetic color terms with empirical measurements:

1. Use synthetic color terms as starting point
2. Measure residuals on standard star fields
3. Add small empirical corrections

This gives you:
- Physical basis from synthetic approach
- Reality check from real data
- Best overall accuracy

## Next Steps

After you have good color terms:

1. **Test extensively** on multiple fields
2. **Document** your color term solution
3. **Share** with the community (if public data)
4. Consider **publishing** methodology paper

## Getting Help

If you run into issues:
1. Check `NICKEL_COLORTERMS_README.md` (full documentation)
2. Review QA plots carefully
3. Try different `--n-nodes` values
4. Check Monster throughputs are correct
5. Contact your local LSST stack expert

## Validation Checklist

Before deploying to production:

- [ ] QA plots look smooth and reasonable
- [ ] Tested on at least 3 different fields
- [ ] Compared to literature Nickel color terms (if available)
- [ ] RMS vs. Monster < 0.05 mag for most stars
- [ ] No systematic trends with color
- [ ] Works well for both blue and red stars
- [ ] Photometry matches standards within uncertainties

## References

- Monster catalog: https://github.com/lsst-dm/the_monster
- FGCM: Burke et al. 2018, AJ 155, 41
- Kelly templates: Kelly et al. 2014, MNRAS 439, 28
- SVO FPS: http://svo2.cab.inta-csic.es/theory/fps/

Good luck with your improved color terms! 🔭
