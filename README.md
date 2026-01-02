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
make bootstrap

# 4. Run pipelines
make archive-night NIGHT=20240625  # Download data
make calibs NIGHT=20240625          # Process calibrations
make science NIGHT=20240625         # Process science images
make coadds TRACT=1099 BAND=r       # Build templates
make dia NIGHT=20240625             # Run difference imaging
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
- **Calibration pipeline**: bias, flats, defect masks
- **Single-frame DRP**: ISR, source detection, WCS, photometry
- **Coadd generation**: deep template building
- **Difference imaging (DIA)**: transient/variable detection
- **Batch processing**: multi-night orchestration

### Data Access & Analysis Tools
- **Archive exploration & download** (`data_tools`)
- **EDA tools**: Query archive metadata, inspect Butler repositories
- **PS1 template ingest**
- **SkyMap generation**
- **Light curve extraction**
- **DIA quality assessment**
- Defect mask generation (`defects`)
- Color term fitting (`colorterms`)

---

## Monorepo Structure

```
obs_nickel/
├── packages/
│   ├── obs_nickel/           # LSST instrument package (camera, configs, pipelines)
│   ├── data_tools/           # Data access, EDA, archive download, PS1 templates, skymap, DIA tools
│   ├── defects/              # Defect mask tooling and generated masks
│   ├── refcats/              # Reference catalog scripts and helpers
│   ├── testdata/             # Test fixtures (small FITS files)
│   ├── tuning/               # Pipeline parameter optimization
│   ├── colorterms/           # Color term fitting utilities
│   └── lick_searchable_archive/  # Local mirror of Lick archive client
├── scripts/
│   ├── pipeline/             # Numbered workflow scripts (00-50)
│   ├── python/               # Helper scripts (deprecated, moved to packages)
│   └── utilities/            # Convenience wrappers
├── data-manifests/           # Versioned pointers to external data bundles
├── camera/                   # Symlink → packages/obs_nickel/camera
├── configs/                  # Symlink → packages/obs_nickel/configs
├── Makefile                  # Convenient automation targets
└── README.md                 # This file
```

**Backward compatibility**: Symlinks at repo root (`camera/`, `configs/`) point to `packages/obs_nickel/` for legacy compatibility.

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

# obs_nickel location (for EUPS)
OBS_NICKEL=/path/to/obs_nickel

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

The repository includes example configs:
- [.env.example](.env.example) - Template for creating your own configs
- [monorepo_repo.env](monorepo_repo.env) - Main testing repository
- [2020wnt_repo.env](2020wnt_repo.env) - SN 2020wnt transient campaign
- [2023ixf_repo.env](2023ixf_repo.env) - SN 2023ixf mini repository

**Note:** All `*.env` files (except `.env.example`) are gitignored for security.

---

## Running Pipelines

**No manual stack activation needed!** The Makefile handles it automatically.

### Basic Workflow

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

### Full Transient Pipeline

```bash
make transient-pipeline ARGS="--template-nights template_nights.txt --dia-nights campaign_nights.txt --band r --tract 1099"
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

| Target | Description |
|--------|-------------|
| `setup-dev` | Install packages + dev tools |
| `setup-dev-full` | Install all packages + notebooks + analysis |
| `bootstrap` | Initialize Butler repo + refcats + skymap |
| `archive-night` | Download night from archive (requires `NIGHT=YYYYMMDD`) |
| `calibs` | Run nightly calibrations (requires `NIGHT=YYYYMMDD`) |
| `science` | Run single-night science processing (requires `NIGHT=YYYYMMDD`) |
| `coadds` | Build coadds/templates (requires `TRACT=NUM BAND=X`) |
| `dia` | Run difference imaging (requires `NIGHT=YYYYMMDD`) |
| `batch` | Batch process nights file (requires `NIGHTS_FILE=path`) |
| `transient-pipeline` | Run full transient pipeline |
| `dia-multiband` | Run multi-band DIA helper |
| `stack-install` | Install LSST stack release (requires `TAG=version`) |
| `lint` | Run ruff linter |
| `format` | Run ruff formatter |
| `test` | Run pytest suite |
| `notebook` | Start Jupyter Lab with stack + venv |

---

## Pipeline Workflow

### Step 0: Bootstrap Repository (One-Time Setup)

Initialize the Butler repository, ingest reference catalogs, and register the skymap:

```bash
make bootstrap
# or manually:
./scripts/pipeline/00_bootstrap_repo.sh
```

This script:
- Creates Butler repository if needed
- Ingests Gaia DR3 and PS1 reference catalogs
- Ingests the_monster catalog (if available)
- Chains reference catalogs for automatic selection
- Registers the Nickel skymap

**Run this once** when setting up a new repository.

### Step 1: Download Archive Data (Optional)

```bash
make archive-night NIGHT=20210219
# or manually:
./scripts/pipeline/01_download_archive.sh --night 20210219
```

**Skip this step** if you already have raw data locally.

### Step 2: Process Calibrations (Per Night)

Build nightly calibration products (bias, flats, defects):

```bash
make calibs NIGHT=20210219
# or manually:
./scripts/pipeline/10_calibs.sh --night 20210219
```

This script:
- Ingests raw data for the night
- Writes curated calibrations (camera geometry)
- Constructs combined bias frames
- Constructs combined flat fields per filter
- Generates defect masks from flats
- Updates the `Nickel/calib/current` chain

**Run this for each new night** before science processing.

### Step 3: Process Science Data (Per Night)

Process science images through the DRP pipeline:

```bash
make science NIGHT=20210219
# or manually:
./scripts/pipeline/20_science.sh --night 20210219

# Process only specific object
./scripts/pipeline/20_science.sh --night 20210219 --object "2020wnt"

# Exclude bad exposures
./scripts/pipeline/20_science.sh --night 20210219 --bad 1032,1051,1052
```

This script:
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
make dia NIGHT=20210219
# or manually:
./scripts/pipeline/40_diff_imaging.sh --night 20210219 --auto-template

# Use specific template
./scripts/pipeline/40_diff_imaging.sh --night 20210219 --template templates/deep/r

# Process specific object in specific band
./scripts/pipeline/40_diff_imaging.sh \
  --night 20210219 \
  --auto-template \
  --object "2020wnt" \
  --band r
```

This script:
- Reprocesses visit images with full calibration metadata
- Warps template coadds to match science image geometry
- Performs PSF-matched image subtraction (Alard-Lupton)
- Detects and measures difference sources
- Injects sky sources for false positive estimation
- Generates quality metrics

**Run this after science processing** to search for transients/variables.

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
