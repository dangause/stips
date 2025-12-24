# SN 2020wnt with PS1 Template - Super Simple

Just 4 commands to go from fresh repo to light curve!

## Step 1: Create repo + Ingest PS1 template (2 min)

```bash
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
source .env

# Create new repo
export NEW_REPO="/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_ps1_repo"
butler create "$NEW_REPO"
butler register-instrument "$NEW_REPO" lsst.obs.nickel.Nickel

# Install astroquery (one-time)
pip install astroquery

# Ingest PS1 template
REPO="$NEW_REPO" ./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 83.8145 --dec 3.0847 --band r
```

**Output**: PS1 template in `templates/ps1/r`

## Step 2: Run pipeline through processCcd (~3-4 hrs)

```bash
REPO="$NEW_REPO" ./scripts/pipeline/run_full_transient_pipeline.sh \
    --template-nights scripts/config/2020wnt/template_nights.txt \
    --dia-nights scripts/config/2020wnt/sn_nights.txt \
    --band r \
    --transient-name "SN2020wnt" \
    --ra 83.8145 --dec 3.0847 \
    --skip-download \
    --skip-template \
    --skip-dia \
    --jobs 8
```

**This does**: Bootstrap + Calibrations + Science processing for all 9 nights

## Step 3: Run DIA with PS1 template (1 hr)

```bash
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do
    REPO="$NEW_REPO" ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" \
        --template "templates/ps1/r" \
        --band r \
        --object "2020wnt" \
        -j 8
done
```

## Step 4: Extract light curve (30 sec)

```bash
mkdir -p ./sn2020wnt_ps1_results

python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo "$NEW_REPO" \
    --collection "Nickel/runs/*/diff/*/run" \
    --ra 83.8145 --dec 3.0847 \
    --radius 1.0 --band r --min-snr 3.0 \
    --output ./sn2020wnt_ps1_results/lightcurve.ecsv
```

**Done!** Light curve at `./sn2020wnt_ps1_results/lightcurve.ecsv`

---

## One-Liner (if you're feeling brave)

After Step 1, run this:

```bash
# Steps 2-4 combined
REPO="$NEW_REPO" ./scripts/pipeline/run_full_transient_pipeline.sh \
    --template-nights scripts/config/2020wnt/template_nights.txt \
    --dia-nights scripts/config/2020wnt/sn_nights.txt \
    --band r --transient-name "SN2020wnt" \
    --ra 83.8145 --dec 3.0847 \
    --skip-download --skip-template --skip-dia --jobs 8 && \
for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do \
    REPO="$NEW_REPO" ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" --template "templates/ps1/r" \
        --band r --object "2020wnt" -j 8; \
done && \
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo "$NEW_REPO" --collection "Nickel/runs/*/diff/*/run" \
    --ra 83.8145 --dec 3.0847 --radius 1.0 --band r --min-snr 3.0 \
    --output ./sn2020wnt_ps1_results/lightcurve.ecsv
```

---

## What Each Step Does

| Step | What Happens | Time |
|------|--------------|------|
| 1 | Create repo, download PS1 template | 2 min |
| 2 | Bootstrap, calibs (9 nights), science (9 nights) | 3-4 hrs |
| 3 | Difference imaging with PS1 template | 1 hr |
| 4 | Extract photometry | 30 sec |

**Total**: ~4-5 hours (mostly automated, can run overnight)

---

## Verification

```bash
# Check everything worked
butler query-datasets "$NEW_REPO" template_coadd --collections "templates/ps1/r"
butler query-datasets "$NEW_REPO" difference_image --collections "Nickel/runs/*/diff/*/run"

# View light curve
cat ./sn2020wnt_ps1_results/lightcurve.ecsv
```
