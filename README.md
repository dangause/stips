# Nickel Processing Suite

Gen3 LSST Science Pipelines integration for the **Nickel 1-meter telescope** at Lick Observatory.

A complete, production-ready monorepo providing telescope configuration, data pipelines, and analysis tools for automated astronomical survey processing.

> ✅ Tested with LSST Science Pipelines `v10.1.0+` and `v11.0.0`

---

## Quick Start

```bash
# 1. Install all packages
uv sync --group dev

# 2. Configure your environment
cp .env.example .env  # Edit .env and set your paths

# 3. Bootstrap your Butler repository (first time only)
nickel bootstrap

# 4. Run pipelines using the nickel CLI
nickel download 20240625              # Download data from archive
nickel calibs 20240625                # Process calibrations
nickel science 20240625               # Process science images
nickel dia 20240625 --auto            # Run difference imaging

# Or use Makefile targets (same functionality)
make calibs NIGHT=20240625
make science NIGHT=20240625
```

### Profile-Based Workflows

Work with multiple Butler repositories using profiles:

```bash
# Create profile-specific env files
cp .env.example .env.2023ixf
# Edit .env.2023ixf with campaign-specific paths

# Use profiles with the nickel CLI
nickel -p 2023ixf calibs 20230519
nickel -p 2023ixf dia 20230519 --band r --auto --prefer-ps1
nickel -p 2023ixf fphot 20230519 --ra 210.91 --dec 54.32
nickel -p 2023ixf lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/*/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec --name "SN 2023ixf"
```

See detailed workflows below.

---

## Features

### Core Instrument Package (`obs_nickel`)
- Single-detector camera model (1024×1024 CCD)
- FITS metadata translator (`NickelTranslator`)
- Raw data formatter (`NickelRawFormatter`)
- Filter definitions: Johnson/Bessell **B, V**; Cousins **R, I**
- Optimized pipeline configurations for Nickel data

### Complete Processing Pipelines
- **Calibration pipeline**: bias, flats, curated defect masks
- **Single-frame DRP**: ISR, source detection, WCS, photometry
- **Coadd generation**: deep template building
- **Difference imaging (DIA)**: transient/variable detection
- **Batch processing**: multi-night orchestration

### Curated Calibrations (`obs_nickel_data`)
- Pre-built defect masks in LSST `obs_*_data` format
- Automatically loaded via `butler write-curated-calibrations`
- Follows the same pattern as `obs_lsst_data` for consistency

### Unified CLI (`nickel`)
- **Profile-based configuration** for multi-repository workflows
- **Integrated commands**: bootstrap, calibs, science, dia, ps1-template, fphot, lightcurve
- **YAML-driven pipeline orchestration** for complete transient workflows
- **PS1 template ingestion** for difference imaging
- **Forced photometry** at arbitrary RA/Dec coordinates
- **Light curve extraction** from DIA sources or forced photometry

### Data Access & Analysis Tools (`data_tools`)
- **Archive exploration & download**
- **EDA tools**: Query archive metadata, inspect Butler repositories
- **Skymap generation**
- **DIA quality assessment**
- Defect mask generation (`defects`)
- Color term fitting (`colorterms`)

---

## Monorepo Structure

```
nickel_processing_suite/
├── packages/
│   ├── obs_nickel/           # LSST instrument package (camera, configs, pipelines)
│   ├── obs_nickel_data/      # Curated calibrations (defects, etc.) for obs_nickel
│   ├── data_tools/           # Data access, EDA, archive download, PS1 templates, skymap, DIA tools
│   ├── defects/              # Defect mask tooling and ECSV export utilities
│   ├── refcats/              # Reference catalog scripts and helpers
│   ├── testdata/             # Test fixtures (small FITS files)
│   ├── tuning/               # Pipeline parameter optimization
│   ├── colorterms/           # Color term fitting utilities
│   └── lick_searchable_archive/  # Local mirror of Lick archive client
├── scripts/
│   ├── config/               # Config helpers and generators
│   ├── pipeline/             # Numbered workflow scripts (00-50)
│   ├── python/               # Helper scripts (deprecated, moved to packages)
│   ├── test/                 # Ad hoc test runners
│   ├── utilities/            # Convenience wrappers
│   └── with-stack.sh         # LSST stack wrapper
├── pyproject.toml            # Workspace configuration
├── uv.lock                   # Locked dependencies
├── Makefile                  # Convenient automation targets
└── README.md                 # This file
```

All configuration and code lives in the `packages/` directory. Scripts reference package paths directly (e.g., `packages/obs_nickel/configs/`).

---

## The `nickel` CLI

The unified command-line interface for all pipeline operations, provided by the `data_tools` package.

### Commands Overview

```bash
nickel --help              # Show all commands
nickel env                 # Show configuration and validate paths
nickel bootstrap           # Initialize Butler repository
nickel download NIGHT      # Fetch data from Lick archive
nickel calibs NIGHT        # Run nightly calibrations
nickel science NIGHT       # Process science frames
nickel dia NIGHT           # Run difference imaging
nickel ps1-template        # Download and ingest PS1 template
nickel fphot NIGHT         # Run forced photometry at RA/Dec
nickel lightcurve          # Extract lightcurve from sources
nickel run CONFIG.yaml     # Run full pipeline from YAML config
```

### Profile-Based Configuration

Use profiles to work with multiple Butler repositories:

```bash
# Create profile-specific env files
cp .env.example .env.2023ixf  # For SN 2023ixf campaign
cp .env.example .env.2020wnt  # For SN 2020wnt campaign

# Use profiles with any command
nickel -p 2023ixf calibs 20230519
nickel -p 2020wnt dia 20201207 --auto

# Profiles look for .env.{profile} or .env.{profile}.ps1
```

See [packages/data_tools/README.md](packages/data_tools/README.md) for complete CLI documentation.

---

## Installation

### Prerequisites

- **Python 3.12+**
- **LSST Science Pipelines** installed (for running pipelines)
- **UV** package manager: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Installation Options

#### Minimal Development Setup (Code Quality Tools Only)

```bash
uv sync --group dev
# or
make setup-dev
```

Installs all workspace packages in editable mode plus code quality tools: `ruff`, `pyright`, `pre-commit`.

**Use this if**: You're developing core packages and don't need notebooks/analysis.

#### Full Development Setup (Everything)

```bash
uv sync --all-groups
# or
make setup-dev-full
```

Installs everything:
- All packages (editable)
- Code quality tools
- Jupyter notebooks
- Analysis libraries (pandas, pyarrow, fastparquet, pyvo)
- RSP integration

**Use this if**: You're doing data analysis, running notebooks, or need full capabilities.

#### Custom Setup (Pick What You Need)

```bash
# Core packages + notebooks
uv sync --group dev --group notebooks

# Core packages + analysis tools
uv sync --group dev --group analysis

# Core packages + RSP
uv sync --group dev --group rsp
```

**Available dependency groups**:
| Group | Contains | Use Case |
|-------|----------|----------|
| `dev` | ruff, pyright, pre-commit | Code quality and development |
| `notebooks` | jupyterlab, notebook | Interactive analysis |
| `analysis` | pandas, pyarrow, fastparquet, pyvo | Data analysis |
| `rsp` | lsst-rsp | Rubin Science Platform integration |

### Working with LSST Stack

UV creates an isolated virtual environment, but `obs_nickel` needs the LSST stack. The **Makefile handles this automatically** for you:

```bash
# Makefile automatically activates LSST stack + runs commands
make test      # Activates stack, runs tests
make notebook  # Activates stack + UV venv, starts Jupyter
```

**Manual activation** (if you prefer):

```bash
# 1. Activate LSST stack
source /path/to/lsst_stack/loadLSST.zsh
setup lsst_distrib

# 2. Activate UV venv
source .venv/bin/activate

# 3. Now both are active - you can use obs_nickel + dev tools
python -c "from lsst.obs.nickel import Nickel"
jupyter lab
```

### Installing another LSST stack (weekly/daily/release)

Use the helper wrapper around `lsstinstall`:

```bash
# Installs to the same location as .env:STACK_DIR by default (fallback: ~/lsst_stacks)
make stack-install TAG=w_latest
```

- To install somewhere else: `STACK_PREFIX=/path/to/stacks make stack-install TAG=w_latest`
- To pin Python: `./scripts/utilities/install_stack_version.sh --release w_latest --python 3.12`
- After install, update `.env:STACK_DIR` to the new path, and the Makefile targets will load that stack automatically.

### Verification

```bash
# Run test suite (automatically activates stack)
make test

# Test CLI tools (no LSST stack required)
uv run obsn-archive-fetch-night --help
uv run obsn-defects-from-flats --help
uv run obsn-defects-to-ecsv --help
```

---

## Environment Configuration

### Single Repository Setup

Create a `.env` file in the repo root with your paths:

```bash
# Copy the example file
cp .env.example .env
# Edit with your paths
```

Example `.env`:
```bash
# Butler repository
REPO=/path/to/butler/repo

# LSST stack installation
STACK_DIR=/path/to/lsst_stack

# Nickel Processing Suite repo (or packages/obs_nickel for EUPS)
OBS_NICKEL=/path/to/nickel_processing_suite

# Raw data parent directory
RAW_PARENT_DIR=/path/to/raw/data

# Reference catalogs
REFCAT_REPO=/path/to/refcat/repo

# Calibration products directory (from LSST stack)
CP_PIPE_DIR=${STACK_DIR}/cp_pipe

# Optional: Lick Archive client
LICK_ARCHIVE_DIR=/path/to/lick_searchable_archive
LICK_ARCHIVE_URL=https://archive.ucolick.org/archive
LICK_ARCHIVE_INSTR=NICKEL_DIR
```

The Makefile automatically sources this file and activates the LSST stack for all pipeline targets.

### Multiple Repository Setup

To work with multiple Butler repositories simultaneously (e.g., different science campaigns, test repos), you have three options:

#### Option 1: Separate Config Files (Recommended)

Create repo-specific config files:

```bash
# Create configs for different repositories
cat > monorepo_repo.env <<EOF
REPO=/path/to/monorepo_repo
STACK_DIR=/path/to/lsst_stack
# ... other common settings
EOF

cat > 2020wnt_repo.env <<EOF
REPO=/path/to/2020wnt_repo
STACK_DIR=/path/to/lsst_stack
# ... other common settings
EOF
```

**Usage:**
```bash
# Terminal 1: Work on monorepo
ENV_FILE=monorepo_repo.env make calibs NIGHT=20240625
ENV_FILE=monorepo_repo.env make science NIGHT=20240625

# Terminal 2: Simultaneously work on SN 2020wnt repo
ENV_FILE=2020wnt_repo.env make dia NIGHT=20210219
ENV_FILE=2020wnt_repo.env make science NIGHT=20210220
```

#### Option 2: Environment Variable Override

Override `REPO` on the command line:

```bash
# Quick one-off for different repo
REPO=/path/to/test_repo make calibs NIGHT=20240625

# Multiple commands with same override
REPO=/path/to/test_repo make calibs NIGHT=20240625
REPO=/path/to/test_repo make science NIGHT=20240625
```

#### Option 3: Hybrid Approach

Use repo-specific configs as base, with one-off overrides:

```bash
# Use 2020wnt config but override to experimental repo
ENV_FILE=2020wnt_repo.env REPO=/path/to/2020wnt_test make science NIGHT=20210219
```

### Example Multi-Repo Configs

The repository includes example configs at the repo root:
- [.env.example](.env.example) - Template for creating your own configs
- `.env.2020wnt`, `.env.2023ixf`, `.env.recalib` - Campaign-specific examples
- `.env.*.ps1` - PS1 template variants

**Note:** `.env` and `.env.*` are gitignored by default (see `.gitignore`). The shipped examples are already tracked; keep your own overrides local or point `ENV_FILE` at a file outside the repo.

---

## Running Pipelines

### Using the `nickel` CLI (Recommended)

The `nickel` CLI provides a unified interface for all pipeline operations:

```bash
# Check configuration
nickel env

# Download data from archive
nickel download 20240625

# Process calibrations
nickel calibs 20240625

# Process science images
nickel science 20240625

# Run difference imaging (auto-discover template)
nickel dia 20240625 --auto

# With profile for specific campaign
nickel -p 2023ixf dia 20230519 --band r --auto --prefer-ps1
```

#### Transient Analysis Workflow

```bash
# 1. Ingest PS1 template for r-band
nickel ps1-template --ra 210.91 --dec 54.32 --band r

# 2. Run forced photometry on difference images
nickel fphot 20230519 --ra 210.91 --dec 54.32

# 3. Extract lightcurve
nickel lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/20230519/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"
```

#### YAML-Driven Pipeline

Run complete workflows from a configuration file:

```bash
nickel run scripts/config/2023ixf/pipeline.yaml
nickel run pipeline.yaml --dry-run  # Preview without executing
```

### Using Make Targets

The Makefile provides equivalent functionality (automatically activates LSST stack):

```bash
# Download data from archive
make archive-night NIGHT=20240625

# Process calibrations
make calibs NIGHT=20240625

# Process science images
make science NIGHT=20240625

# Build templates/coadds
make coadds TRACT=1099 BAND=r

# Run difference imaging
make dia NIGHT=20240625
```

### Batch Processing Multiple Nights

```bash
# Create nights list
cat > nights.txt <<EOF
20240625
20240626
20240627
EOF

# Process all nights
make batch NIGHTS_FILE=nights.txt
```

### Available Make Targets

```bash
make help  # Show all available targets
```

| Target | CLI Equivalent | Description |
|--------|----------------|-------------|
| `setup-dev` | - | Install packages + dev tools |
| `setup-dev-full` | - | Install all packages + notebooks + analysis |
| `bootstrap` | `nickel bootstrap` | Initialize Butler repo + refcats + skymap |
| `archive-night` | `nickel download` | Download night from archive |
| `calibs` | `nickel calibs` | Run nightly calibrations |
| `science` | `nickel science` | Run single-night science processing |
| `coadds` | - | Build coadds/templates |
| `dia` | `nickel dia` | Run difference imaging |
| `batch` | - | Batch process nights file |
| `transient-pipeline` | `nickel run` | Run full transient pipeline |
| `dia-multiband` | - | Run multi-band DIA helper |
| `stack-install` | - | Install LSST stack release |
| `lint` | - | Run ruff linter |
| `format` | - | Run ruff formatter |
| `test` | - | Run pytest suite |
| `notebook` | - | Start Jupyter Lab with stack + venv |

Additional `nickel` CLI commands (no Make equivalent):
- `nickel ps1-template` - Download and ingest PS1 template
- `nickel fphot` - Run forced photometry at RA/Dec
- `nickel lightcurve` - Extract lightcurve from sources
- `nickel env` - Show/validate configuration

---

## Pipeline Workflow

### Step 0: Bootstrap Repository (One-Time Setup)

Initialize the Butler repository, ingest reference catalogs, and register the skymap:

```bash
nickel bootstrap
# or with profile:
nickel -p 2023ixf bootstrap
# or via Make:
make bootstrap
```

This step:
- Creates Butler repository if needed
- Registers the Nickel instrument
- Ingests Gaia DR3 and PS1 reference catalogs
- Ingests the_monster catalog (if available)
- Chains reference catalogs for automatic selection
- Registers the Nickel skymap

**Run this once** when setting up a new repository.

### Step 1: Download Archive Data (Optional)

```bash
nickel download 20210219
# or via Make:
make archive-night NIGHT=20210219
```

**Skip this step** if you already have raw data locally.

### Step 2: Process Calibrations (Per Night)

Build nightly calibration products (bias, flats, defects):

```bash
nickel calibs 20210219
nickel calibs 20210219 --jobs 8  # More parallel jobs
# or via Make:
make calibs NIGHT=20210219
```

This step:
- Ingests raw data for the night
- Writes curated calibrations (camera geometry + defects from `obs_nickel_data`)
- Constructs combined bias frames
- Constructs combined flat fields per filter
- Updates the `Nickel/calib/current` chain

**Run this for each new night** before science processing.

### Step 3: Process Science Data (Per Night)

Process science images through the DRP pipeline:

```bash
nickel science 20210219
nickel science 20210219 --object "2020wnt"         # Filter by target
nickel science 20210219 --bad 1032,1051,1052       # Exclude bad exposures
nickel science 20210219 --skip-coadds              # Skip coadd generation
# or via Make:
make science NIGHT=20210219
```

This step:
- Runs ISR (Instrument Signature Removal)
- Performs source detection and measurement
- Computes astrometric solution (WCS)
- Performs photometric calibration
- Consolidates visit-level catalogs
- Generates quality metrics

**Run this for each night** after calibrations are built.

### Step 4: Build Templates (For Difference Imaging)

Build deep coadd templates:

```bash
make coadds TRACT=1099 BAND=r
# or manually:
./scripts/pipeline/30_coadds.sh --tract 1099 --band r
```

**Run this step** if you plan to do difference imaging.

### Step 5: Difference Imaging (DIA)

Run difference imaging to detect transients and variable sources:

```bash
nickel dia 20210219 --auto                    # Auto-discover template
nickel dia 20210219 --template templates/deep/r  # Use specific template
nickel dia 20210219 --auto --prefer-ps1 --band r  # Prefer PS1 template
nickel dia 20210219 --auto --object "2020wnt" --band r  # Filter by target
# or via Make:
make dia NIGHT=20210219
```

This step:
- Reprocesses visit images with full calibration metadata
- Warps template coadds to match science image geometry
- Performs PSF-matched image subtraction (Alard-Lupton)
- Detects and measures difference sources
- Injects sky sources for false positive estimation
- Generates quality metrics

**Run this after science processing** to search for transients/variables.

### Step 6: Forced Photometry (Optional)

Run forced photometry at specific coordinates on difference images:

```bash
nickel fphot 20210219 --ra 123.456 --dec 45.678
nickel fphot 20210219 --ra 123.456 --dec 45.678 --band r --image-type diffim
```

### Step 7: Light Curve Extraction (Optional)

Extract light curves from DIA sources or forced photometry:

```bash
# From DIA sources
nickel lightcurve --ra 123.456 --dec 45.678 \
    --collections "Nickel/runs/20210219/diff/*/run" \
    --name "Target Name"

# From forced photometry (more reliable for known targets)
nickel lightcurve --ra 123.456 --dec 45.678 \
    --collections "Nickel/runs/20210219/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "Target Name"
```

Output files are saved to `{repo}/lightcurves/` by default.

---

## Camera Specification

- **Detector**: Single CCD (detector ID: 0)
- **Format**: 1024×1024 imaging area + 32 column overscan
- **Raw frame size**: 1056×1024 pixels
- **Amplifier**: Single readout (A00)
- **Pixel scale**: 0.37"/pixel
- **Field of view**: ~6.3' × 6.3'
- **Gain**: ~1.8 e-/ADU
- **Read noise**: ~7 e-

See [packages/obs_nickel/camera/nickel.yaml](packages/obs_nickel/camera/nickel.yaml) for complete specifications.

---

## Filters

Defined in [packages/obs_nickel/python/lsst/obs/nickel/nickelFilters.py](packages/obs_nickel/python/lsst/obs/nickel/nickelFilters.py):

| Physical Filter | Band | System         | Central λ |
|----------------|------|----------------|-----------|
| B              | b    | Johnson/Bessell| ~440 nm   |
| V              | v    | Johnson/Bessell| ~550 nm   |
| R              | r    | Cousins        | ~640 nm   |
| I              | i    | Cousins        | ~790 nm   |
| clear          | -    | -              | -         |

---

## Curated Calibrations

### Overview

The `obs_nickel_data` package provides pre-built curated calibrations (currently defect masks) that are automatically loaded during pipeline processing. This follows the same pattern as `obs_lsst_data` for the Rubin Observatory.

### How It Works

1. **Automatic discovery**: The `Nickel` instrument class has `obsDataPackage = "obs_nickel_data"` configured
2. **Butler integration**: When you run `butler write-curated-calibrations`, it automatically finds and ingests calibrations from `obs_nickel_data`
3. **No on-the-fly generation**: Defects are pre-computed and stored, reducing pipeline runtime

### Directory Structure

```
obs_nickel_data/
├── Nickel/
│   └── defects/
│       └── ccd0/
│           └── 19700101T000000.ecsv  # Defects valid from epoch (all-time)
├── python/
│   └── lsst/obs/nickel_data/
│       └── __init__.py
├── ups/
│   └── obs_nickel_data.table
└── pyproject.toml
```

### ECSV Format

Defect files use ECSV 0.9 format with FITS-compatible metadata:

```
# %ECSV 0.9
# ---
# datatype:
# - name: x0
#   unit: pix
#   datatype: int32
# - name: y0
#   ...
# meta: !!omap
# - OBSTYPE: defects
# - INSTRUME: Nickel
# - DETECTOR: 0
# - CALIBDATE: '1970-01-01T00:00:00'
# - DEFECTS_SCHEMA: Simple
# - DEFECTS_SCHEMA_VERSION: 1
# schema: astropy-2.0
x0 y0 width height
255 1 2 1024
...
```

### Generating New Defects

Use the defects package tools to generate and export defects:

```bash
# Step 1: Detect defects from flat fields
obsn-defects-from-flats \
  --repo $REPO \
  --collection "Nickel/cp/flat/..." \
  --csv-out defects.csv \
  --plot

# Step 2: Export to ECSV for obs_nickel_data
obsn-defects-to-ecsv \
  --csv defects.csv \
  --output packages/obs_nickel_data/Nickel/defects/ccd0/

# Or directly from Butler flats:
obsn-defects-to-ecsv \
  --repo $REPO \
  --collection "Nickel/cp/flat/..." \
  --output packages/obs_nickel_data/Nickel/defects/ccd0/
```

### Updating Curated Calibrations

After adding new ECSV files to `obs_nickel_data`:

```bash
# Re-run curated calibration ingest for your Butler repo
butler write-curated-calibrations $REPO Nickel $RAW_RUN --collection $CURATED_RUN
```

---

## Development Workflow

### For Interactive Analysis (Jupyter)

```bash
# Easy way: Let Make handle everything
make notebook

# Manual way (if you prefer)
source ~/lsst_stacks/loadLSST.zsh
setup lsst_distrib
source .venv/bin/activate
jupyter lab
```

### For Code Development

```bash
# No stack needed for linting/formatting
make lint
make format

# Tests need the stack (automatically activated)
make test
```

### Code Quality

Pre-commit hooks are configured for linting and formatting:

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## Testing

### Unit Tests

Run the full test suite:

```bash
make test
# or manually with stack activated:
pytest -v
```

Individual test modules:
- `packages/obs_nickel/tests/test_translator.py` - FITS header translation
- `packages/obs_nickel/tests/test_instrument.py` - Camera and filter registration
- `packages/obs_nickel/tests/test_ingest.py` - Raw data ingest and visit definition

---

## Butler Collections

The pipeline uses a hierarchical collection structure:

```
Nickel/
├── raw/
│   └── YYYYMMDD/            # Raw data by night
│       └── TIMESTAMP/
├── calib/
│   ├── current              # CHAIN: Latest calibrations
│   ├── curated              # CHAIN: Camera geometry
│   ├── defects/             # Defect masks
│   ├── YYYYMMDD/            # Nightly calibrations
│   └── cp/                  # Calibration products
│       └── YYYYMMDD/
│           ├── bias/
│           └── flat/
├── runs/
│   └── YYYYMMDD/            # Science processing
│       ├── processCcd/
│       ├── coadd/
│       └── diff/
└── refcats                   # CHAIN: Reference catalogs
```

---

## For LSST Upstream Submission

The `obs_nickel` package is intentionally kept minimal and LSST-ready:

```bash
# Just install obs_nickel standalone
pip install -e packages/obs_nickel

# Verify it works without monorepo dependencies
cd /tmp
python -c "from lsst.obs.nickel import Nickel; print('✅ obs_nickel OK')"
```

**Minimal dependencies** (only 2):
- `astro_metadata_translator>=0.11.0`
- `astropy`

No development tools, no tuning code, no notebooks - just the core instrument package.

---

## UV Benefits

- **Fast**: 10-100x faster than pip
- **Reliable**: True dependency resolution
- **Reproducible**: Lock files ensure consistent installs
- **Workspace-aware**: Handles monorepo structure automatically
- **Compatible**: Works with existing `pyproject.toml`

---

## Troubleshooting

### "LSST stack not found"

Make sure `STACK_DIR` in your `.env` points to the correct location:

```bash
# .env
STACK_DIR=/Users/dangause/Developer/lick/lsst/lsst_stack
```

### "Command not found: obsn-*"

Run `uv sync --group dev` to install the CLI tools.

### Pipeline fails with import errors

The Makefile should handle this, but if you run scripts directly without Make, ensure you've activated the stack:

```bash
source $STACK_DIR/loadLSST.zsh
setup lsst_distrib
```

### Module not found errors

Make sure you've activated the UV environment:

```bash
source .venv/bin/activate
# or run commands via:
uv run python script.py
```

---

## Contributing

Contributions are welcome! Please:
1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Submit pull requests against `main`

---

## References

- **LSST Science Pipelines**: https://pipelines.lsst.io
- **Butler Gen3**: https://pipelines.lsst.io/modules/lsst.daf.butler
- **Obs Base**: https://github.com/lsst/obs_base
- **UV Package Manager**: https://docs.astral.sh/uv/

---

## License

This package is distributed under **GPL-3.0** license.

---

## Contact

For questions or issues:
- Create an issue on GitHub
- Contact the maintainer: Dan Gause

---

## Acknowledgments

Built on the LSST Science Pipelines framework. Thanks to the LSST Data Management team for the excellent infrastructure and documentation.
