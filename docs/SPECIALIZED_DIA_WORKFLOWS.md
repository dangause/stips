Specialized DIA Workflows for obs_nickel

Quick reference for transient and variable star difference imaging analysis.

## Overview

obs_nickel provides three DIA workflow scripts:

1. **[run_full_dia.sh](../scripts/pipeline/run_full_dia.sh)** - General-purpose DIA pipeline
2. **[run_transient_dia.sh](../scripts/pipeline/run_transient_dia.sh)** - Optimized for supernovae/transients
3. **[run_variable_dia.sh](../scripts/pipeline/run_variable_dia.sh)** - Optimized for variable stars

All three use the same underlying [40_diff_imaging.sh](../scripts/pipeline/40_diff_imaging.sh) engine but with different defaults and workflows.

---

## Transient Workflow (Supernovae, Fast Transients)

### When to Use

- Supernova follow-up campaigns
- Fast transient monitoring (hours to days)
- Known point-source coordinates
- Single-object focus

### Key Features

- **Automatic tract discovery** from coordinates
- **Object filtering** by default (focus on your target)
- **Relaxed quality threshold** (0.35 vs 0.2) - transients often in poor seeing
- **Light curve extraction** built-in
- **Template date exclusion** support (avoid contamination)

### Quick Start

```bash
./scripts/pipeline/run_transient_dia.sh \
  --name "SN2020wnt" \
  --ra 56.658 --dec 43.229 \
  --band r \
  --template-nights template_nights.txt \
  --science-nights science_nights.txt \
  --jobs 4
```

### Required Inputs

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--name` | Transient name | `SN2020wnt` |
| `--ra` | RA in degrees | `56.658` |
| `--dec` | Dec in degrees | `43.229` |
| `--band` | Observation band | `r`, `i` |
| `--science-nights` | File with science nights | `science_nights.txt` |

### Template Options (pick one)

```bash
# Option 1: Build new template
--template-nights template_nights.txt

# Option 2: Use existing template
--template "templates/deep/tract1825/r/20251224T120000Z"

# Option 3: Auto-discover
--auto-template
```

### Advanced Options

```bash
# Avoid template contamination (exclude SN epoch)
--exclude-dates-start 20220101 \
--exclude-dates-end 20220301

# Adjust quality threshold for poor seeing
--bad-sub-threshold 0.5

# Skip light curve extraction (do it manually later)
--skip-lightcurve

# Preview commands without running
--dry-run
```

### Output Structure

```
transient_dia_results/SN2020wnt_20251224_120000/
├── workflow.log                  # Full processing log
├── SN2020wnt_lightcurve.ecsv     # Extracted light curve
└── (DIA products in butler repo)
```

### Complete Example

See [scripts/config/examples/sn2020wnt_example.sh](../scripts/config/examples/sn2020wnt_example.sh)

```bash
#!/bin/bash
# SN 2020wnt campaign

cat > template_nights.txt <<EOF
20201207
20201219
20210208
EOF

cat > science_nights.txt <<EOF
20220105
20220110
20220126
EOF

./scripts/pipeline/run_transient_dia.sh \
  --name "2020wnt" \
  --ra 56.658 --dec 43.229 \
  --band r \
  --template-nights template_nights.txt \
  --science-nights science_nights.txt \
  --exclude-dates-start 20220101 \
  --exclude-dates-end 20220301 \
  --bad-sub-threshold 0.35 \
  --jobs 4
```

---

## Variable Star Workflow (Cepheids, RR Lyrae, Eclipsing Binaries)

### When to Use

- Variable star monitoring campaigns
- Multi-epoch field observations
- Period-finding studies
- Full-field catalogs needed

### Key Features

- **Multi-band support** (process r,i,v simultaneously)
- **Strict quality threshold** (0.2) - variables need clean photometry
- **Field-based processing** (no object filter by default)
- **Template depth checking** (warns if < 5 nights)
- **Catalog extraction** for full-field analysis

### Quick Start

```bash
./scripts/pipeline/run_variable_dia.sh \
  --name "M33_field1" \
  --ra 23.462 --dec 30.660 \
  --bands r,i \
  --template-nights template_nights.txt \
  --observation-nights all_nights.txt \
  --jobs 4
```

### Required Inputs

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--name` | Field name | `M33_field1` |
| `--ra` | Field center RA | `23.462` |
| `--dec` | Field center Dec | `30.660` |
| `--bands` | Comma-separated bands | `r,i` or `b,v,r,i` |
| `--observation-nights` | All observation nights | `all_nights.txt` |

### Template Options (pick one)

```bash
# Option 1: Build new template
--template-nights template_nights.txt

# Option 2: Use existing template (will append /{band})
--template "templates/deep/tract1825"

# Option 3: Auto-discover per band
--auto-template
```

### Advanced Options

```bash
# Filter by specific object (for targeted variable)
--object "V1"

# Relax quality if needed
--bad-sub-threshold 0.3

# Require deeper template
--min-template-nights 10

# Extract full DIA catalogs for analysis
--extract-catalog

# Skip automatic light curve extraction
--skip-lightcurve
```

### Output Structure

```
variable_dia_results/M33_field1_20251224_120000/
├── workflow.log                          # Full processing log
├── M33_field1_r_dia_collections.txt      # R-band DIA collections
├── M33_field1_i_dia_collections.txt      # I-band DIA collections
└── (DIA products in butler repo)
```

### Extract Light Curves

After DIA completes, extract light curves for individual variables:

```bash
# Get DIA collections
DIA_COLL=$(cat variable_dia_results/M33_field1_*/M33_field1_r_dia_collections.txt)

# Extract light curve for variable at RA=23.470, Dec=30.665
python scripts/python/pipeline_tools/extract_lightcurve.py \
  --repo $REPO \
  --collection "$DIA_COLL" \
  --ra 23.470 --dec 30.665 \
  --radius 1.0 --band r \
  --output M33_var1_r_lc.ecsv
```

### Complete Example

See [scripts/config/examples/m33_variables_example.sh](../scripts/config/examples/m33_variables_example.sh)

```bash
#!/bin/bash
# M33 variable star monitoring

cat > template_nights.txt <<EOF
20240601
20240602
20240605
20240610
20240615
EOF

cat > all_nights.txt <<EOF
# Includes template nights + monitoring nights
20240601
20240602
20240605
20240610
20240615
20240701
20240715
20240801
EOF

./scripts/pipeline/run_variable_dia.sh \
  --name "M33_field1" \
  --ra 23.462 --dec 30.660 \
  --bands r,i \
  --template-nights template_nights.txt \
  --observation-nights all_nights.txt \
  --min-template-nights 5 \
  --extract-catalog \
  --jobs 4
```

---

## Comparison: Transient vs Variable Workflows

| Feature | Transient | Variable |
|---------|-----------|----------|
| **Focus** | Single object | Full field |
| **Bands** | Single | Multi-band |
| **Quality threshold** | Relaxed (0.35) | Strict (0.2) |
| **Object filter** | Yes (default) | Optional |
| **Light curve** | Auto-extracted | Manual |
| **Template** | Date-aware | Deep baseline |
| **Use case** | Known transient coords | Variable search/monitoring |

---

## Common Workflows

### 1. Supernova Follow-up with Local Template

```bash
# Step 1: Build template from pre-SN nights
cat > template_nights.txt <<EOF
20201207
20201219
20210208
EOF

# Step 2: Run transient DIA
./scripts/pipeline/run_transient_dia.sh \
  --name "SN2023xyz" \
  --ra 56.658 --dec 43.229 \
  --band r \
  --template-nights template_nights.txt \
  --science-nights sn_nights.txt \
  --exclude-dates-start 20230201 \
  --exclude-dates-end 20230430
```

### 2. Supernova with PS1 Template

```bash
# Use external PS1 template (already ingested)
./scripts/pipeline/run_transient_dia.sh \
  --name "SN2023xyz" \
  --ra 56.658 --dec 43.229 \
  --band r \
  --template "templates/ps1/r/sn2023xyz" \
  --science-nights sn_nights.txt \
  --bad-sub-threshold 0.4
```

### 3. Multi-Band Variable Monitoring

```bash
# Process all bands for period-finding
./scripts/pipeline/run_variable_dia.sh \
  --name "NGC2419" \
  --ra 114.535 --dec 38.883 \
  --bands b,v,r,i \
  --template-nights baseline_nights.txt \
  --observation-nights all_nights.txt \
  --extract-catalog
```

### 4. Eclipsing Binary Light Curve

```bash
# Targeted extraction for known eclipsing binary
./scripts/pipeline/run_variable_dia.sh \
  --name "NGC2419" \
  --ra 114.535 --dec 38.883 \
  --bands v,r \
  --template-nights baseline_nights.txt \
  --observation-nights all_nights.txt \
  --object "EB_V47"  # Filter by object name
```

---

## Troubleshooting

### BadSubtractionError

**Symptom:** Some visits fail with "ratio exceeds maximum threshold"

**Cause:** Poor PSF matching (seeing mismatch, poor astrometry)

**Solutions:**
```bash
# Option 1: Relax threshold
--bad-sub-threshold 0.5

# Option 2: Exclude bad visits
--bad-file bad_visits.txt

# Option 3: Build template from better seeing nights
```

### No Template Coverage

**Symptom:** "Template doesn't cover tract/patch"

**Cause:** Template and science observations in different fields

**Solutions:**
```bash
# Verify coordinates match
# Check tract assignment

# Or use PS1 template (full sky)
--template "templates/ps1/r/yourfield"
```

### Refcat Coverage Issues

**Symptom:** "Not enough datasets found for astrometry_ref_cat"

**Cause:** Multiple targets in night, some outside refcat coverage

**Solutions:**
```bash
# Filter by object name
--object "YourTarget"

# This excludes other targets outside refcat cone
```

### Multi-Target Nights

**Symptom:** Processing fails for some exposures

**Cause:** Observing night includes multiple targets, some outside refcat

**Solution:**
```bash
# ALWAYS use object filter for multi-target nights
--object "YourTarget"
```

---

## Best Practices

### Transient Campaigns

1. ✅ **Use object filter** to focus on your target
2. ✅ **Build template from pre-discovery** nights when possible
3. ✅ **Exclude SN epoch dates** from template
4. ✅ **Relax quality threshold** (0.35-0.5) for rapid cadence
5. ✅ **Monitor logs** for PSF mismatch warnings

### Variable Campaigns

1. ✅ **Build deep template** (5+ nights minimum)
2. ✅ **Process all bands** together for color info
3. ✅ **Keep strict threshold** (0.2) for photometry quality
4. ✅ **Extract full catalogs** for variable search
5. ✅ **Cross-match epochs** for period finding

### General

1. ✅ **Always specify tract** explicitly (faster, more reliable)
2. ✅ **Check seeing** in template vs science (PSF matching critical)
3. ✅ **Use --dry-run** to preview workflow first
4. ✅ **Monitor disk space** (DIA generates many products)
5. ✅ **Keep logs** for debugging and QA

---

## Reference

- **Full DIA guide:** [NICKEL_TEMPLATE_DIA_GUIDE.md](NICKEL_TEMPLATE_DIA_GUIDE.md)
- **Quick start:** [DIA_QUICKSTART.md](DIA_QUICKSTART.md)
- **Pipeline scripts:** [scripts/pipeline/](../scripts/pipeline/)
- **Examples:** [scripts/config/examples/](../scripts/config/examples/)

---

## Support

For issues or questions:
1. Check [NICKEL_TEMPLATE_DIA_GUIDE.md](NICKEL_TEMPLATE_DIA_GUIDE.md) troubleshooting
2. Review workflow logs in output directories
3. Test with example scripts first
4. Check GitHub issues
