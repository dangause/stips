# Configuration Guide

This guide covers all configuration options for the Nickel Processing Suite.

## Configuration Methods

NPS supports three configuration methods (in order of precedence):

1. **Pipeline YAML with inline `env`** - Self-contained, portable
2. **Profile-based `.env` files** - Reusable across commands
3. **Shell environment variables** - Quick overrides

### Method 1: Inline YAML Environment (Recommended)

```yaml
# pipeline.yaml
env:
  REPO: "/path/to/repo"
  STACK_DIR: "/path/to/stack"
  OBS_NICKEL: "/path/to/obs_nickel"
  RAW_PARENT_DIR: "/path/to/raw"
  REFCAT_REPO: "/path/to/refcats"

object: "my_target"
# ... rest of config
```

Usage:
```bash
nickel run pipeline.yaml
nickel bootstrap pipeline.yaml
```

### Method 2: Profile-Based `.env` Files

Create `.env.{profile}` files in the repository root:

```bash
# .env.2023ixf
REPO=/data/nickel/2023ixf_repo
STACK_DIR=/opt/lsst/stack
OBS_NICKEL=/home/user/nps/packages/obs_nickel
RAW_PARENT_DIR=/data/nickel/raw
REFCAT_REPO=/data/refcats
```

Usage:
```bash
nickel -p 2023ixf calibs 20230519
nickel -p 2023ixf science 20230519
```

### Method 3: Shell Environment

```bash
export REPO=/data/nickel/repo
export STACK_DIR=/opt/lsst/stack
nickel calibs 20230519
```

---

## Environment Variables Reference

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `REPO` | Butler repository path | `/data/nickel/my_repo` |
| `STACK_DIR` | LSST stack installation | `/opt/lsst/stack` |
| `OBS_NICKEL` | obs_nickel package path | `/path/to/nps/packages/obs_nickel` |
| `RAW_PARENT_DIR` | Parent of raw data dirs | `/data/nickel/raw` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REFCAT_REPO` | Reference catalog repo | None |
| `CP_PIPE_DIR` | cp_pipe package path | Auto-discovered from stack |
| `LICK_ARCHIVE_DIR` | Lick archive client | None |
| `LICK_ARCHIVE_URL` | Archive API URL | `https://archive.ucolick.org/archive` |
| `LICK_ARCHIVE_INSTR` | Instrument code | `NICKEL_DIR` |

---

## Pipeline YAML Reference

### Complete Example

```yaml
# =============================================================================
# Environment Configuration
# =============================================================================
env:
  REPO: "/data/nickel/2023ixf_repo"
  STACK_DIR: "/opt/lsst/stack"
  OBS_NICKEL: "/home/user/nps/packages/obs_nickel"
  RAW_PARENT_DIR: "/data/nickel/raw"
  REFCAT_REPO: "/data/refcats"
  CP_PIPE_DIR: "${STACK_DIR}/cp_pipe"

# =============================================================================
# Target Information
# =============================================================================
object: "2023ixf"      # Object name for filtering (partial match, case-insensitive)
ra: 210.910833         # J2000 Right Ascension in degrees
dec: 54.316389         # J2000 Declination in degrees
bands: ["r", "i"]      # Bands to process: b, v, r, i

# =============================================================================
# Template Configuration
# =============================================================================
template:
  type: ps1            # "ps1" or "coadd"
  degrade_seeing: 2.0  # For PS1: convolve to this FWHM (arcsec)
  # For coadd templates, also specify:
  # nights:
  #   - "20231001"
  #   - "20231015"

# =============================================================================
# Observation Nights
# =============================================================================
nights:
  20230519:
    r: []              # Empty list = all visits for this band
    i: []

  20230521:
    r: [12345, 12346]  # Specific visit IDs only
    i: []

  20230523:
    r: []
    # i: not specified = skip i-band for this night

# =============================================================================
# Pipeline Configurations (Optional)
# =============================================================================
configs:
  science:
    # Primary config for calibrateImage
    calibrate_image: calibrateImage/tuned_configs/2023ixf_relaxed.py

    # Fallback configs tried in order if primary fails
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py

    # Color term application
    colorterms: apply_colorterms.py

  dia:
    subtract_images: dia/subtractImages.py
    detect_and_measure: dia/detectAndMeasure.py

# =============================================================================
# Processing Options
# =============================================================================
options:
  jobs: 8                  # Parallel processing jobs for pipetask
  skip_calibs: false       # Skip calibration building
  skip_science: false      # Skip science processing
  skip_dia: false          # Skip difference imaging
  forced_phot: true        # Run forced photometry at RA/Dec
  lightcurve: true         # Extract combined light curve
  continue_on_error: true  # Continue if one night fails
  use_fallbacks: true      # Try fallback configs on failure
```

### Section Reference

#### `env` Section

Environment variables for the pipeline. Supports variable expansion:

```yaml
env:
  STACK_DIR: "/opt/lsst/stack"
  CP_PIPE_DIR: "${STACK_DIR}/cp_pipe"  # Expands to /opt/lsst/stack/cp_pipe
```

#### `object` Field

Target name for filtering FITS headers. Matching is:
- Case-insensitive
- Partial match (substring)

Examples:
- `"2023ixf"` matches `"SN2023ixf"`, `"sn 2023ixf"`, `"SN2023IXF"`
- `"ngc1234"` matches `"NGC 1234"`, `"ngc1234-field1"`

#### `ra` and `dec` Fields

J2000 coordinates in decimal degrees. These are used for:
- **Forced photometry** (`fphot`) at the target position
- **Light curve extraction** (`lightcurve`) source matching
- **Coordinate validation** during science processing: exposures with `tracking_ra`/`tracking_dec` more than 5° from these coordinates are automatically excluded before qgraph construction (see [Stale DEC Headers](#stale-dec-headers))

```yaml
ra: 210.910833    # RA = 14h 03m 38.6s
dec: 54.316389    # Dec = +54° 18' 59"
```

#### `bands` Field

List of photometric bands to process:

| Band | Filter System |
|------|---------------|
| `b` | Johnson B |
| `v` | Johnson V |
| `r` | Cousins R |
| `i` | Cousins I |

**Note:** PS1 templates only support `r` and `i` bands.

#### `template` Section

##### PS1 Templates

```yaml
template:
  type: ps1
  degrade_seeing: 2.0  # Optional: convolve to match Nickel seeing
```

- Available for r and i bands only
- Good for quick start
- May have PSF mismatch issues

##### Nickel Coadd Templates

```yaml
template:
  type: coadd
  nights:
    - "20231001"
    - "20231015"
    - "20231101"
```

- Available for all bands (B, V, R, I)
- Better PSF matching
- Requires observations when transient has faded

#### `nights` Section

Specify observation nights and which visits to process:

```yaml
nights:
  # Process all visits for both bands
  20230519:
    r: []
    i: []

  # Process specific visits only
  20230521:
    r: [12345, 12346, 12347]
    i: [12350, 12351]

  # Skip a band for this night
  20230523:
    r: []
    # i: not listed = skipped
```

**Night format:** `YYYYMMDD` (local date at start of night)

#### `configs` Section

Override default pipeline configurations:

```yaml
configs:
  science:
    calibrate_image: path/to/config.py
    calibrate_image_fallbacks:
      - path/to/fallback1.py
      - path/to/fallback2.py
    colorterms: path/to/colorterms.py

  dia:
    subtract_images: path/to/subtract.py
    detect_and_measure: path/to/detect.py
```

Paths are relative to `obs_nickel/configs/`.

Available tuned configs:
- `calibrateImage/tuned_configs/2023ixf_relaxed.py` - Standard config
- `calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py` - For sparse fields

#### `options` Section

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `jobs` | int | 8 | Parallel jobs for pipetask |
| `skip_calibs` | bool | false | Skip calibration building |
| `skip_science` | bool | false | Skip science processing |
| `skip_dia` | bool | false | Skip difference imaging |
| `forced_phot` | bool | true | Run forced photometry |
| `lightcurve` | bool | true | Extract light curve |
| `continue_on_error` | bool | true | Continue if night fails |
| `use_fallbacks` | bool | true | Try fallback calibrateImage configs on partial failure. Each fallback writes to its own RUN collection (`/run_fb1`, etc.) and uses `--skip-existing-in` to only reprocess failed quanta. |

---

## Raw Data Directory Structure

NPS expects raw data organized as:

```
RAW_PARENT_DIR/
├── 20230519/
│   └── raw/
│       ├── d0519_0001.fits
│       ├── d0519_0002.fits
│       └── ...
├── 20230521/
│   └── raw/
│       └── ...
└── ...
```

The night directory (`20230519`) should be the local date at the start of the observing night.

---

## Reference Catalog Setup

Reference catalogs should be in a Butler repository with collections:

- `gaia_dr3` - Gaia DR3 astrometry
- `ps1_pv3_3pi_20170110` - PS1 photometry
- `the_monster` (optional) - Combined catalog

The bootstrap process chains these into `refcats` for automatic selection.

---

## Processing Logs

When `use_fallbacks: true`, NPS creates JSON logs in `{REPO}/processing_log/`:

```json
{
  "night": "20230519",
  "step": "science",
  "timestamp": "20240115T103045",
  "configs_tried": [
    {
      "config": "calibrateImage/tuned_configs/2023ixf_relaxed.py",
      "is_fallback": false,
      "quanta_attempted": 10,
      "quanta_succeeded": 8,
      "quanta_failed": 2,
      "failed_exposures": [
        {"exposure": 12345, "error": "Astrometry failed"}
      ]
    },
    {
      "config": "calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py",
      "is_fallback": true,
      "quanta_attempted": 2,
      "quanta_succeeded": 2,
      "quanta_failed": 0
    }
  ],
  "final_status": "success",
  "output_collection": "Nickel/runs/20230519/processCcd/20240115T103045Z/run"
  // Note: This records the primary RUN. Downstream steps use the CHAINED parent
  // (Nickel/runs/20230519/processCcd/20240115T103045Z) which includes fallback results.
}
```

---

## Docker Configuration

When running in Docker, paths map to container locations:

| Host Path | Container Path |
|-----------|----------------|
| `${REPO}` | `/data/repo` |
| `${RAW_PARENT_DIR}` | `/data/raw` |
| `${REFCAT_REPO}` | `/data/refcats` |

Example docker-compose override:

```yaml
services:
  nps:
    environment:
      - REPO=/data/repo
      - RAW_PARENT_DIR=/data/raw
      - REFCAT_REPO=/data/refcats
    volumes:
      - /host/path/to/repo:/data/repo
      - /host/path/to/raw:/data/raw
      - /host/path/to/refcats:/data/refcats:ro
```

---

## BPS Configuration

BPS site configs are in `bps/sites/`:

### Slurm Site

```yaml
# bps/sites/slurm.yaml
site:
  slurm:
    nodes: 1
    cores_per_node: 32
    mem_per_node: 128
    walltime: "04:00:00"
    scheduler_options: |
      #SBATCH --partition=normal
      #SBATCH --account={project}
```

### Task-Specific Resources

```yaml
pipetask:
  calibrateImage:
    requestMemory: 8192
    requestCpus: 2
    numberOfRetries: 3

  subtractImages:
    requestMemory: 16384
    memoryMultiplier: 1.5
```

---

## Known Issues

### Stale DEC Headers

The Nickel telescope has a known hardware issue where the `DEC` keyword in FITS headers can get "stuck" at a previous pointing's declination value. When this happens, both `CRVAL2` and `DEC` agree on the wrong coordinate, so the translator's CRVAL-vs-RA/DEC fallback (which requires a >1° disagreement) does not trigger.

These bad coordinates propagate into Butler exposure records and visit regions. During science processing, the qgraph builder tries to find reference catalog shards covering those visit regions. Since refcats are only ingested for the actual target field, visits with wrong coordinates land in uncovered HTM7 shards, causing a hard `FileNotFoundError` that crashes the entire qgraph build for all visits on that night.

**Mitigation:** NPS automatically performs pre-flight coordinate validation when target `ra`/`dec` are available. Before building the quantum graph, it queries Butler for each exposure's `tracking_ra`/`tracking_dec` and excludes any that are more than 5° from the expected target. This is automatic when using `nickel run` with a pipeline YAML. For standalone `nickel science` commands, pass `--ra` and `--dec` to enable this check.

---

## See Also

- [Getting Started](getting-started.md) - First-time setup
- [CLI Reference](cli-reference.md) - Command options
- [New Campaign Guide](new-campaign.md) - Campaign setup
