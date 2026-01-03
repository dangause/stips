# DRP Recalibration Setup - Complete

## ✅ Setup Complete

Your DRP with recalibration environment is now fully set up and ready to use!

## 📁 Files Created

### Configuration Files
- ✅ `.env.recal` - Environment configuration for recalibration testing
- ✅ `packages/obs_nickel/pipelines/experimental/DRP_recal.yaml` - Pipeline definition (already existed)

### Scripts Created

#### Core Pipeline Scripts
- ✅ `scripts/pipeline/00_bootstrap_repo_recal.sh` - Bootstrap repository
- ✅ `scripts/pipeline/10_calibs_recal.sh` - Process calibrations
- ✅ `scripts/pipeline/20_science_recal.sh` - Stage 1 science (single-visit)
- ✅ `scripts/pipeline/21_recalibrate.sh` - **Stage 2 recalibration (NEW!)**
- ✅ `scripts/pipeline/30_coadds_recal.sh` - Build coadds with recalibrated data

#### Orchestration Scripts
- ✅ `scripts/pipeline/run_drp_recal.sh` - **Master script to run everything**

### Documentation
- ✅ `README_RECAL.md` - Complete documentation
- ✅ `QUICKSTART_RECAL.md` - Quick start guide
- ✅ `RECAL_SETUP_SUMMARY.md` - This file

## 🎯 What You Can Do Now

### Option 1: Run Everything at Once (Recommended)

```bash
# 1. Create a nights list
cat > nights.txt <<EOF
20240624
20240625
20240626
EOF

# 2. Run the full pipeline
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file nights.txt \
  --tract 1825 \
  --jobs 4
```

This runs the complete pipeline:
- Bootstrap (if needed)
- Download raw data (optional)
- Process calibrations
- Run Stage 1 (single-visit processing)
- Run Stage 2 (FGCM + GBDES + PSF refit)
- Build coadds

### Option 2: Step-by-Step

See [QUICKSTART_RECAL.md](QUICKSTART_RECAL.md) for step-by-step instructions.

## 🔄 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    DRP with Recalibration                    │
└─────────────────────────────────────────────────────────────┘

Stage 0: Bootstrap (once)
  └─> Repository creation, refcat ingestion, skymap

Stage 1: Single-Visit Processing (per night)
  └─> ISR → calibrateImage → PSF → astrometry → photometry
      ├─> preliminary_visit_image
      ├─> preliminary_visit_summary
      └─> single_visit_star

Stage 1: Isolated Star Association (per tract)
  └─> Match stars across visits
      └─> isolated_star_association

Stage 2: Recalibration (all nights together)
  ├─> Step 2a: FGCM (global photometric calibration)
  │   └─> fgcmPhotoCalibCatalog
  ├─> Step 2b: GBDES tract-level (joint astrometric fit)
  │   └─> gbdesAstrometricFitSkyWcsCatalog
  ├─> Step 2c: GBDES healpix-level (optional)
  ├─> Step 2d: Refit PSFs + update visit_summary
  │   └─> visit_summary (with FGCM + GBDES applied)
  └─> Step 2f: Final tables and stellar motion

Stage 3: Coadds (per band)
  └─> Use recalibrated visit_summary
      └─> template_coadd

Stage 4: Difference Imaging (optional)
  └─> Use recalibrated templates
```

## 📊 Collection Organization

Your data will be organized in isolated collections:

```
Nickel/
├── raw/                    # Raw data (shared)
├── calib/current/         # Calibration products (shared)
└── recal/                 # RECALIBRATION OUTPUTS (isolated)
    ├── runs/
    │   └── {NIGHT}/
    │       └── stage1/
    │           └── {TIMESTAMP}/   ← Stage 1 outputs
    ├── stage2/
    │   └── {TIMESTAMP}/           ← Stage 2 recalibration outputs
    └── coadds/
        └── tract{TRACT}/{BAND}/
            └── {TIMESTAMP}/       ← Recalibrated coadds
```

**All outputs go to `Nickel/recal/*` - completely isolated from your existing data!**

## 🔍 Key Differences from Standard DRP

| Aspect | Standard DRP | Recal DRP |
|--------|--------------|-----------|
| **Environment** | `.env` | `.env.recal` |
| **Repository** | Main repo | Isolated recal repo |
| **Pipeline YAML** | `DRP.yaml` | `DRP_recal.yaml` |
| **Scripts** | `*_script.sh` | `*_recal.sh` |
| **Collections** | `Nickel/runs/*` | `Nickel/recal/*` |
| **Stages** | Stage 1 + coadds | Stage 1 + Stage 2 + coadds |
| **Calibrations** | Initial only | Initial + multi-epoch |
| **Coadds** | Use `preliminary_visit_summary` | Use `visit_summary` (recalibrated) |

## ⚙️ Environment Configuration

Your `.env.recal` file is configured with:

```bash
# Isolated repository
REPO=/Users/dangause/Developer/lick/lsst/data/nickel/recal_20240624_repo

# LSST stack paths
STACK_DIR=/Users/dangause/Developer/lick/lsst/lsst_stack
OBS_NICKEL=/Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Pipeline configuration
DRP_PIPE_DIR=${STACK_DIR}/drp_pipe
PIPE_TASKS_DIR=${STACK_DIR}/pipe_tasks

# Reference catalogs
REFCAT_REPO=/Users/dangause/Developer/lick/lsst/lsst_stack/stack/refcats

# Defaults
JOBS=4
SKYMAP_NAME=nickelRings-v1
```

You can modify these as needed.

## 📖 Documentation

- **[QUICKSTART_RECAL.md](QUICKSTART_RECAL.md)** - Quick start guide with common commands
- **[README_RECAL.md](README_RECAL.md)** - Complete documentation with all details
- **This file** - Setup summary

## 🚀 Next Steps

1. **Review configuration**: Check `.env.recal` and adjust paths if needed

2. **Prepare data**: Create a `nights.txt` file with the nights you want to process

3. **Test run**: Start with a small dataset (1-2 nights) to verify everything works

4. **Full run**: Process your complete dataset

5. **Compare results**: Compare photometry/astrometry with standard DRP

## ⚠️ Important Notes

### Isolation
- **Everything is isolated**: The recal pipeline uses a completely separate repository
- **No conflicts**: You can run this alongside your regular DRP without any issues
- **Safe testing**: Experiment freely without affecting your production data

### Data Requirements
- **FGCM**: Needs multiple nights (ideally 5+) and multiple bands
- **GBDES**: Needs sufficient overlap between visits
- **Healpix**: Optional, may not work with small datasets

### Performance
- **Stage 1**: Parallelizes by visit/detector (set `--jobs`)
- **Stage 2**: Some steps are global (no parallelization)
- **Coadds**: Parallelizes by patch (set `--jobs`)

## 🐛 Troubleshooting

See [QUICKSTART_RECAL.md](QUICKSTART_RECAL.md#troubleshooting) for common issues and solutions.

## ✨ Summary

You now have a complete, isolated setup for testing DRP with Stage 2 recalibration:

✅ Separate environment (`.env.recal`)
✅ Separate scripts (`*_recal.sh`)
✅ Separate pipeline (`DRP_recal.yaml`)
✅ Separate collections (`Nickel/recal/*`)
✅ Complete documentation
✅ Master orchestration script

**Ready to run!** 🎉

Start with the quick start guide:
```bash
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh --help
```

Or dive into [QUICKSTART_RECAL.md](QUICKSTART_RECAL.md) for examples.
