# CLI Reference

Complete reference for the `nickel` command-line interface.

## Global Options

These options can be used with any command:

| Option | Description |
|--------|-------------|
| `-p, --profile PROFILE` | Load environment from `.env.{PROFILE}` |
| `--env-file PATH` | Load environment from specific file |
| `--help` | Show help message |

**Examples:**

```bash
# Use a profile
nickel -p 2023ixf calibs 20230519

# Use explicit env file
nickel --env-file /path/to/.env.custom science 20230519
```

---

## Configuration Commands

### `nickel env`

Show current configuration and validate paths.

```bash
nickel env
nickel -p 2023ixf env
```

**Output:**
- Lists all environment variables
- Validates that paths exist
- Checks LSST stack accessibility

---

### `nickel bootstrap`

Initialize a new Butler repository.

```bash
nickel bootstrap [CONFIG_FILE]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `CONFIG_FILE` | Optional. Pipeline YAML with `env` section |

**What it does:**
1. Creates Butler repository directory
2. Registers Nickel instrument
3. Ingests reference catalogs (Gaia DR3, PS1, the_monster)
4. Registers the Nickel skymap

**Examples:**

```bash
# Bootstrap using YAML config (recommended)
nickel bootstrap scripts/config/2023ixf/pipeline_ps1_template.yaml

# Bootstrap using profile
nickel -p 2023ixf bootstrap

# Bootstrap using default .env
nickel bootstrap
```

**Note:** `nickel run` automatically calls bootstrap if the repository doesn't exist.

---

## Data Access Commands

### `nickel download`

Fetch observation data from the Lick Observatory archive.

```bash
nickel download NIGHT [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NIGHT` | Observing night in YYYYMMDD format |

**Options:**

| Option | Description |
|--------|-------------|
| `--overwrite` | Re-download existing files |

**Examples:**

```bash
nickel download 20230519
nickel download 20230519 --overwrite
```

---

### `nickel ps1-template`

Download and ingest a PS1 template image for difference imaging.

```bash
nickel ps1-template --ra RA --dec DEC --band BAND [OPTIONS]
```

**Required Options:**

| Option | Description |
|--------|-------------|
| `--ra FLOAT` | Right ascension in degrees |
| `--dec FLOAT` | Declination in degrees |
| `-b, --band {r,i}` | Nickel band (r or i) |

**Optional:**

| Option | Description |
|--------|-------------|
| `-c, --collection TEXT` | Output collection (default: `templates/ps1/{band}`) |
| `--tract INT` | Tract number (auto-determined if not set) |
| `--size FLOAT` | Cutout size in degrees (default: 0.2) |
| `--degrade-seeing FLOAT` | Convolve to this FWHM in arcsec |
| `--overwrite` | Replace existing template |

**Examples:**

```bash
# Basic usage
nickel ps1-template --ra 210.91 --dec 54.32 --band r

# With seeing degradation
nickel ps1-template --ra 210.91 --dec 54.32 --band r --degrade-seeing 2.0

# Custom collection
nickel ps1-template --ra 210.91 --dec 54.32 --band i \
    --collection templates/ps1/2023ixf/i
```

---

## Processing Commands

### `nickel calibs`

Run nightly calibrations (bias, flat, defects).

```bash
nickel calibs NIGHT [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NIGHT` | Observing night in YYYYMMDD format |

**Options:**

| Option | Description |
|--------|-------------|
| `-j, --jobs INT` | Parallel jobs (default: 4) |

**What it does:**
1. Ingests raw data for the night
2. Writes curated calibrations (defects from obs_nickel_data)
3. Builds combined bias
4. Builds combined flats per filter
5. Certifies calibrations to `Nickel/calib/{night}`

**Examples:**

```bash
nickel calibs 20230519
nickel calibs 20230519 --jobs 8
nickel -p 2023ixf calibs 20230519
```

---

### `nickel science`

Run science processing (ISR, WCS, photometry).

```bash
nickel science NIGHT [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NIGHT` | Observing night in YYYYMMDD format |

**Options:**

| Option | Description |
|--------|-------------|
| `-j, --jobs INT` | Parallel jobs (default: 8) |
| `--object TEXT` | Filter by OBJECT header value |
| `--bad TEXT` | Comma-separated exposure IDs to exclude |
| `--bad-file PATH` | File with bad exposure IDs (one per line) |
| `--skip-coadds` | Skip coadd generation |
| `--config PATH` | Override calibrateImage config |
| `--ra FLOAT` | Target RA in degrees (enables coordinate validation) |
| `--dec FLOAT` | Target Dec in degrees (enables coordinate validation) |

**What it does:**
1. *(If `--ra`/`--dec` provided)* Pre-flight coordinate validation: queries Butler for exposure coordinates, excludes any that are far from the target
2. Runs ISR (Instrument Signature Removal)
3. Characterizes images (PSF, background)
4. Calibrates images (WCS, photometry)
5. Consolidates catalogs
6. Creates processing log

**Coordinate Validation:**

When `--ra` and `--dec` are provided, science processing queries the Butler for each exposure's `tracking_ra`/`tracking_dec` and compares them to the expected target coordinates. Exposures more than 5° away are automatically excluded from the data query. This prevents qgraph build failures caused by the Nickel telescope's known issue where the DEC header can get "stuck" at a previous pointing's value.

This validation is **automatic** when using `nickel run` with a pipeline YAML (which always has `ra`/`dec` fields).

**Examples:**

```bash
# Basic usage
nickel science 20230519

# Filter by target
nickel science 20230519 --object 2023ixf

# With coordinate validation (recommended for Nickel data)
nickel science 20230519 --object 2023ixf --ra 210.91 --dec 54.32

# Exclude bad exposures
nickel science 20230519 --bad 12345,12346,12347

# Use bad exposure file
nickel science 20230519 --bad-file bad_exposures.txt

# Skip coadd step
nickel science 20230519 --object 2023ixf --skip-coadds
```

---

### `nickel dia`

Run difference imaging analysis.

```bash
nickel dia NIGHT [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NIGHT` | Observing night in YYYYMMDD format |

**Options (Template - one required):**

| Option | Description |
|--------|-------------|
| `-t, --template TEXT` | Template collection to use |
| `--auto` | Auto-discover template |

**Options (Filtering):**

| Option | Description |
|--------|-------------|
| `-b, --band TEXT` | Filter by band (b/v/r/i) |
| `--object TEXT` | Filter by OBJECT header |
| `--prefer-ps1` | Prefer PS1 templates (with --auto) |
| `--bad TEXT` | Comma-separated exposure IDs to exclude |
| `--bad-file PATH` | File with bad exposure IDs |

**Options (Processing):**

| Option | Description |
|--------|-------------|
| `-j, --jobs INT` | Parallel jobs (default: 8) |

**What it does:**
1. Warps template to match science image geometry
2. Performs PSF-matched image subtraction
3. Detects and measures difference sources
4. Injects sky sources for validation

**Examples:**

```bash
# Auto-discover template
nickel dia 20230519 --auto

# Specify template explicitly
nickel dia 20230519 --template templates/ps1/r

# Auto with PS1 preference
nickel dia 20230519 --auto --prefer-ps1 --band r

# Filter by target
nickel dia 20230519 --auto --object 2023ixf --band r
```

---

### `nickel fphot`

Run forced photometry at specified coordinates.

```bash
nickel fphot NIGHT --ra RA --dec DEC [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `NIGHT` | Observing night in YYYYMMDD format |

**Required Options:**

| Option | Description |
|--------|-------------|
| `--ra FLOAT` | Right ascension in degrees |
| `--dec FLOAT` | Declination in degrees |

**Optional:**

| Option | Description |
|--------|-------------|
| `-b, --band TEXT` | Filter by band (default: all) |
| `--image-type {visit,diffim,both}` | Image type (default: diffim) |

**What it does:**
- Performs forced photometry at exact RA/Dec on difference images
- Measures flux even when source is not detected

**Examples:**

```bash
# Basic forced photometry on difference images
nickel fphot 20230519 --ra 210.91 --dec 54.32

# On both visit and difference images
nickel fphot 20230519 --ra 210.91 --dec 54.32 --image-type both

# Single band only
nickel fphot 20230519 --ra 210.91 --dec 54.32 --band r
```

---

### `nickel lightcurve`

Extract light curve from DIA sources or forced photometry.

```bash
nickel lightcurve --ra RA --dec DEC --collections COLLECTIONS [OPTIONS]
```

**Required Options:**

| Option | Description |
|--------|-------------|
| `--ra FLOAT` | Right ascension in degrees |
| `--dec FLOAT` | Declination in degrees |
| `--collections TEXT` | Comma-separated collection patterns |

**Optional:**

| Option | Description |
|--------|-------------|
| `--repo PATH` | Butler repository path (overrides profile/env) |
| `--radius FLOAT` | Match radius in arcsec (default: 1.0) |
| `--min-snr FLOAT` | Minimum S/N filter (default: 3.0) |
| `--max-mag-err FLOAT` | Maximum magnitude error for plot filtering |
| `-b, --band TEXT` | Restrict to single band |
| `--name TEXT` | Target name for plot title |
| `-o, --output PATH` | Output CSV file |
| `--plot/--no-plot` | Generate plot (default: yes) |
| `--dataset-type TEXT` | Dataset type to query (default: dia_source_unfiltered) |
| `--y-axis CHOICE` | Y-axis display: `apparent_mag`, `absolute_mag`, `flux_nJy`, `flux_adu` (default: apparent_mag) |
| `--x-axis CHOICE` | X-axis display: `mjd`, `days_since_explosion` (default: mjd) |
| `--explosion-mjd FLOAT` | Explosion MJD (required with `--x-axis=days_since_explosion`) |
| `--distance-modulus FLOAT` | Distance modulus (required with `--y-axis=absolute_mag`) |

**Examples:**

```bash
# Using --repo to specify Butler repository directly
nickel -p 2023ixf lightcurve \
    --repo /path/to/butler_repo \
    --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/diff/*/run" \
    --dataset-type dia_source_unfiltered \
    --name "SN 2023ixf"

# From DIA sources (using profile for repo)
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/diff/*/run" \
    --name "SN 2023ixf"

# From forced photometry (recommended for faint/variable sources)
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"

# Days since explosion with error filtering
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf" \
    --x-axis days_since_explosion --explosion-mjd 60082.75 \
    --min-snr 2 --max-mag-err 1.0

# Absolute magnitude (requires distance modulus)
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --y-axis absolute_mag --distance-modulus 29.05

# Flux mode (linear scale, no axis inversion)
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --y-axis flux_nJy
```

---

## Orchestration Commands

### `nickel run`

Run complete pipeline from YAML configuration.

```bash
nickel run CONFIG_FILE [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `CONFIG_FILE` | Path to pipeline YAML configuration |

**Options:**

| Option | Description |
|--------|-------------|
| `--dry-run` | Print commands without executing |

**What it does:**
1. Loads configuration from YAML
2. Bootstraps repository if needed
3. Ingests templates
4. For each night: runs calibs → science → DIA → fphot
5. Extracts combined light curve

**Examples:**

```bash
# Run full pipeline
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml

# Dry run to preview
nickel run pipeline.yaml --dry-run
```

---

## BPS Commands (HPC)

### `nickel bps submit`

Submit pipeline to HPC cluster via BPS.

```bash
nickel bps submit PIPELINE NIGHT [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PIPELINE` | Pipeline type: calibs, science, dia, fphot |
| `NIGHT` | Observing night in YYYYMMDD format |

**Options:**

| Option | Description |
|--------|-------------|
| `--site {slurm,htcondor,local}` | Compute site (default: slurm) |
| `-b, --band TEXT` | Band for DIA pipeline |
| `-t, --template TEXT` | Template collection for DIA |
| `--object TEXT` | Filter by OBJECT header |
| `--coords TEXT` | Coordinate collection for fphot |
| `--project TEXT` | HPC project/account (default: nickel) |
| `--dry-run` | Show what would be submitted |

**Examples:**

```bash
# Submit calibrations to Slurm
nickel bps submit calibs 20230519 --site slurm

# Submit science processing
nickel bps submit science 20230519 --site slurm --project myallocation

# Submit DIA (requires band)
nickel bps submit dia 20230519 --site slurm --band r

# Dry run
nickel bps submit calibs 20230519 --site local --dry-run
```

---

### `nickel bps status`

Check status of a BPS run.

```bash
nickel bps status RUN_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `RUN_ID` | Run identifier from submit command |

---

### `nickel bps cancel`

Cancel a running BPS workflow.

```bash
nickel bps cancel RUN_ID [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `RUN_ID` | Run identifier |

**Options:**

| Option | Description |
|--------|-------------|
| `--force` | Cancel without confirmation |

---

### `nickel bps list`

List recent BPS runs.

```bash
nickel bps list
```

---

## Environment Variables

These can be set in `.env` files or the shell:

| Variable | Required | Description |
|----------|----------|-------------|
| `REPO` | Yes | Path to Butler repository |
| `STACK_DIR` | Yes | Path to LSST stack installation |
| `OBS_NICKEL` | Yes | Path to obs_nickel package |
| `RAW_PARENT_DIR` | Yes | Parent directory for raw data |
| `REFCAT_REPO` | No | Path to reference catalogs |
| `CP_PIPE_DIR` | No | Path to cp_pipe (auto-discovered) |
| `LICK_ARCHIVE_DIR` | No | Path to Lick archive client |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (see stderr for details) |

---

## See Also

- [Getting Started](getting-started.md) - First-time setup
- [Configuration Guide](configuration.md) - YAML config reference
- [New Campaign Guide](new-campaign.md) - Setting up new targets
