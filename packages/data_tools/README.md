# small-tel-tools

Python CLI and operational tools for small telescope data processing with LSST Science Pipelines.

Supports multiple telescopes via the **InstrumentPlugin** system:
- **Nickel** - Lick Observatory 1-meter telescope (default)
- **CTIO 0.9m** - Cerro Tololo 0.9-meter (SMARTS)

This package provides:
- **`nickel` CLI**: Unified command-line interface for all pipeline operations
- **InstrumentPlugin system**: Extensible multi-telescope support
- **Archive tools**: Download and query observatory archive data
- **EDA tools**: Explore archive and Butler repository contents
- **Pipeline tools**: DIA quality assessment, light curve extraction
- **Skymap utilities**: Skymap generation and configuration

## Installation

Install editable from the repo root:

```bash
uv sync  # Installs all workspace packages including data_tools
```

Or install directly:

```bash
python -m pip install -e packages/data_tools
```

## Multi-Instrument Support

The CLI supports multiple telescopes via the `-i/--instrument` flag:

```bash
# Default: Nickel telescope
nickel calibs 20230519

# Explicit instrument selection
nickel -i nickel calibs 20230519
nickel -i ctio0m9 calibs 20090527
```

### InstrumentPlugin Architecture

Each telescope is supported by an `InstrumentPlugin` subclass that provides:
- Observatory archive access (`fetch_data`)
- Bootstrap orchestration (`bootstrap`)
- Default pipeline configurations
- Instrument-specific parameters (collection prefix, skymap, day_obs offset)

```python
from small_tel_tools.instruments import get_plugin, list_plugins

# List available instruments
print(list_plugins())  # ['ctio0m9', 'nickel']

# Get a specific plugin
plugin = get_plugin("ctio0m9")
print(plugin.name)              # "ctio0m9"
print(plugin.collection_prefix) # "ctio0m9"
print(plugin.day_obs_offset)    # 1
```

### Adding a New Instrument

1. Create a plugin class in `small_tel_tools/instruments/<name>.py`:

```python
from small_tel_tools.instruments.base import InstrumentPlugin

class MyTelescopePlugin(InstrumentPlugin):
    name = "mytelescope"
    instrument_class = "lsst.obs.smalltel.mytelescope.MyTelescope"
    collection_prefix = "MyTelescope"
    skymap_name = "mytelescopeRings-v1"
    skymaps_chain = "skymaps/mytelescopeRings"
    day_obs_offset = 1  # Adjust for timezone

    def fetch_data(self, night: str, dest_dir: Path) -> None:
        # Implement archive download
        ...

    def bootstrap(self, repo: Path, config: dict) -> None:
        # Implement repo initialization
        ...
```

2. Register in `small_tel_tools/instruments/__init__.py`

3. Optionally register as an entry point in `pyproject.toml`

## The `nickel` CLI

The primary interface for processing Nickel telescope data. Uses profile-based configuration for multi-repository workflows.

### Basic Usage

```bash
# Show configuration and validate paths
nickel env

# Run nightly calibrations
nickel calibs 20240625

# Process science frames
nickel science 20240625

# Run difference imaging
nickel dia 20240625 --auto
```

### Profile-Based Configuration

Use profiles to work with different Butler repositories (e.g., different science campaigns):

```bash
# Uses .env.2023ixf for configuration
nickel -p 2023ixf env
nickel -p 2023ixf calibs 20230519
nickel -p 2023ixf dia 20230519 --band r --auto

# Uses .env.2020wnt for a different campaign
nickel -p 2020wnt calibs 20201207
```

Profiles look for `.env.{profile}` or `.env.{profile}.ps1` files in the current directory.

### Available Commands

| Command | Description |
|---------|-------------|
| `nickel env` | Show configuration and validate paths |
| `nickel bootstrap` | Initialize Butler repo, refcats, skymap |
| `nickel download NIGHT` | Fetch data from Lick archive |
| `nickel calibs NIGHT` | Run nightly calibrations (bias, flat) |
| `nickel science NIGHT` | Process science frames (ISR, WCS, photometry) |
| `nickel dia NIGHT` | Run difference imaging analysis |
| `nickel ps1-template` | Download and ingest PS1 template for DIA |
| `nickel fphot NIGHT` | Run forced photometry at RA/Dec |
| `nickel lightcurve` | Extract lightcurve from DIA/forced phot sources |
| `nickel run CONFIG.yaml` | Run full pipeline from YAML config |

### Command Details

#### `nickel bootstrap`

Initialize a new Butler repository:

```bash
nickel bootstrap
nickel -p 2023ixf bootstrap
```

Creates the Butler repo, registers the instrument, ingests reference catalogs, and sets up the skymap.

#### `nickel calibs`

Run nightly calibrations:

```bash
nickel calibs 20240625
nickel calibs 20240625 --jobs 8
```

#### `nickel science`

Process science images:

```bash
nickel science 20240625
nickel science 20240625 --object 2020wnt --skip-coadds
nickel science 20240625 --bad 12345,12346
```

Options:
- `--object`: Filter by OBJECT header value
- `--bad`: Exclude specific exposure IDs
- `--skip-coadds`: Skip coadd generation
- `--jobs`: Parallel jobs (default: 8)

#### `nickel dia`

Run difference imaging:

```bash
nickel dia 20240625 --auto                          # Auto-discover template
nickel dia 20240625 --template templates/deep/r     # Use specific template
nickel dia 20240625 --auto --prefer-ps1 --band r    # Prefer PS1, single band
```

Options:
- `--auto`: Auto-discover template collection
- `--template`: Specify template collection
- `--prefer-ps1`: Prefer PS1 templates over internal (with --auto)
- `--band`: Filter by band (b/v/r/i)
- `--object`: Filter by OBJECT header

#### `nickel ps1-template`

Download and ingest PS1 template for difference imaging:

```bash
nickel ps1-template --ra 210.91 --dec 54.32 --band r
nickel ps1-template --ra 210.91 --dec 54.32 --band i --degrade-seeing 2.0
```

PS1 templates are only available for r and i bands.

Options:
- `--ra`, `--dec`: Target coordinates (required)
- `--band`: Nickel band, r or i (required)
- `--degrade-seeing`: Convolve to this FWHM in arcsec
- `--overwrite`: Replace existing template

#### `nickel fphot`

Run forced photometry at specified RA/Dec:

```bash
nickel fphot 20230519 --ra 210.91 --dec 54.32
nickel fphot 20230519 --ra 210.91 --dec 54.32 --band r --image-type both
```

Options:
- `--ra`, `--dec`: Target coordinates (required)
- `--band`: Filter by band
- `--image-type`: `visit`, `diffim`, or `both` (default: diffim)

#### `nickel lightcurve`

Extract lightcurve from DIA source catalogs or forced photometry:

```bash
# From DIA sources
nickel lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/20230519/diff/*/run" \
    --name "SN 2023ixf"

# From forced photometry
nickel lightcurve --ra 210.91 --dec 54.32 \
    --collections "Nickel/runs/20230519/forcedPhotRaDec/*/run" \
    --dataset-type forced_phot_diffim_radec \
    --name "SN 2023ixf"
```

Options:
- `--collections`: DIA/fphot collections to query (required)
- `--radius`: Match radius in arcsec (default: 1.0)
- `--min-snr`: Minimum S/N filter (default: 3.0)
- `--dataset-type`: Dataset type (default: dia_source_unfiltered)
- `--name`: Target name for plot title
- `--output`: Output CSV file path
- `--plot/--no-plot`: Generate plot (default: yes)

Output files are saved to `{repo}/lightcurves/` by default.

#### `nickel run`

Run a full pipeline from YAML configuration:

```bash
nickel run scripts/config/2023ixf/pipeline.yaml
nickel run pipeline.yaml --dry-run
```

Example YAML format:
```yaml
object: "2023ixf"
ra: 210.910750
dec: 54.311694
bands: ["r", "i"]

template:
  type: ps1
  degrade_seeing: 2.0

nights:
  20230519:
    r: []
    i: []

options:
  jobs: 8
  forced_phot: true
  lightcurve: true
```

## Standalone CLI Tools

In addition to the unified `nickel` CLI, individual tools are available for specific tasks:

### Archive Tools

Download and manage archive data:

```bash
# Download a night of data
obsn-archive-fetch-night --night 20210101 --raw-root /data/nickel/raw

# Generate list of nights in date range
obsn-archive-nights --start 20210101 --end 20210110 -o nights.txt

# Ingest PS1 template data
obsn-archive-ingest-ps1 --repo /path/to/repo --template-dir /path/to/ps1
```

### EDA Tools - Archive Queries

Explore what data is available in the Lick Observatory archive:

```bash
# Summary statistics for a date range
uv run obsn-eda-archive summary --start 20200101 --end 20201231

# Per-night file counts
uv run obsn-eda-archive nights --start 20200101 --end 20201231 --format table
uv run obsn-eda-archive nights --start 20200101 --end 20201231 --format csv --output nights.csv
```

**Note**: The archive index only provides filenames and dates. Detailed metadata (filter, exposure time, target name) requires downloading files and inspecting FITS headers.

### EDA Tools - Butler Repository Inspection

Explore and analyze Butler repository contents:

```bash
# List all collections, organized by type
obsn-eda-butler collections --repo /path/to/repo

# Filter collections by pattern
obsn-eda-butler collections --repo /path/to/repo --pattern "Nickel/runs/*/diff/*"

# Show dataset inventory for a collection
# Use the CHAINED parent to include primary + fallback results
obsn-eda-butler datasets --repo /path/to/repo --collection "Nickel/runs/20240625/processCcd/*"

# Check calibration coverage across nights
obsn-eda-butler calibs --repo /path/to/repo --nights 20240601,20240602,20240603

# Show template availability by tract and band
obsn-eda-butler templates --repo /path/to/repo
```

**Environment**: Set `$REPO` to avoid repeating `--repo` argument.

### DIA Tools

Quality assessment and light curve extraction:

```bash
# Assess DIA processing quality
obsn-dia-assess --repo /path/to/repo --collection "Nickel/runs/*/diff/*/run" --night 20240625

# Extract light curve for a source
obsn-dia-lightcurve --repo /path/to/repo --collection "Nickel/runs/*/diff/*/run" --ra 123.456 --dec 45.678
```

### Skymap Tools

```bash
# Build discrete skymap configuration
obsn-skymap-build-config --output nickel_skymap.py

# Create skymap from datasets
obsn-skymap-make --repo /path/to/repo --collection "Nickel/raw/*"
```

## Environment Variables

### Pipeline Configuration

The `nickel` CLI uses a `.env` file for configuration. Create one from the example:

```bash
cp .env.example .env
```

Required variables:
- `REPO` - Butler repository path
- `STACK_DIR` - LSST stack installation directory
- `OBS_NICKEL` - Path to obs_nickel package
- `RAW_PARENT_DIR` - Root directory for raw data

Optional variables:
- `REFCAT_REPO` - Reference catalog repository
- `CP_PIPE_DIR` - Calibration products directory
- `LICK_ARCHIVE_DIR` - Lick archive client path
- `LICK_ARCHIVE_URL` - Archive API URL (default: https://archive.ucolick.org/archive)

### Archive Tools (Standalone)

- `RAW_PARENT_DIR` - Root directory for raw data storage
- `LICK_ARCHIVE_URL` - Archive API base URL
- `LICK_ARCHIVE_DIR` - Path to lick_searchable_archive client library
- `LICK_ARCHIVE_INSTR` - Instrument filter (default: NICKEL_DIR)

## Dependencies

Core dependencies (automatically installed):
- `numpy`, `pandas` - Data manipulation
- `astropy` - Astronomy utilities
- `rich` - Terminal formatting and tables
- `matplotlib` - Plotting and visualization
- `click` - CLI framework
- `pyyaml` - YAML configuration parsing

LSST Stack dependencies (must be available in environment):
- `lsst.daf.butler` - Butler data repository access
- `lsst.pipe.base` - Pipeline infrastructure

## Development

The package uses a standard setuptools layout:

```
packages/data_tools/
├── src/
│   └── small_tel_tools/
│       ├── cli.py                # Main nickel CLI
│       ├── instruments/          # Multi-telescope plugin system
│       │   ├── base.py               # InstrumentPlugin ABC
│       │   ├── nickel.py             # Nickel 1-m plugin
│       │   └── ctio0m9.py            # CTIO 0.9m plugin
│       ├── core/                 # Core pipeline modules
│       │   ├── config.py             # Configuration loading
│       │   ├── stack.py              # LSST stack execution
│       │   ├── calibs.py             # Calibration pipeline
│       │   ├── science.py            # Science processing
│       │   ├── dia.py                # Difference imaging
│       │   ├── ps1_template.py       # PS1 template ingestion
│       │   ├── fphot.py              # Forced photometry
│       │   ├── lightcurve.py         # Lightcurve extraction
│       │   └── run.py                # YAML pipeline runner
│       ├── pipeline_tools/       # Archive download, PS1 ingest
│       ├── skymap/               # Skymap utilities
│       └── eda/                  # Exploratory data analysis
├── tests/
│   └── test_instrument_plugin.py # Plugin system tests
├── pyproject.toml
└── README.md
```

All CLI entry points are defined in `pyproject.toml` under `[project.scripts]`.

## Related Packages

- **obs_smalltel** - LSST instrument package with camera geometry, translators, pipelines
- **obs_nickel_data** / **obs_ctio0m9_data** - Curated calibrations (defects, etc.)
