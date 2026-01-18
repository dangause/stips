# obs-nickel-data-tools

Python CLIs for data access, exploration, and pipeline support for Nickel telescope workflows.

This package provides:
- **Archive tools**: Download and query Lick Observatory archive data
- **EDA tools**: Explore archive and Butler repository contents
- **Pipeline tools**: DIA quality assessment, light curve extraction
- **Skymap utilities**: Skymap generation and configuration

These tools were formerly in `obs-nickel-archive-tools` and scripts under `scripts/python/`. Legacy wrapper scripts remain for compatibility.

## Installation

Install editable from the repo root:

```bash
uv sync  # Installs all workspace packages including data_tools
```

Or install directly:

```bash
python -m pip install -e packages/data_tools
```

## CLI Tools

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

**Note**: The archive index only provides filenames and dates. Detailed metadata (filter, exposure time, target name) requires downloading files and inspecting FITS headers. Use `obsn-archive-fetch-night` to download data for detailed analysis.

**Output formats**: `table` (rich terminal), `json`, `csv`, `tsv`

**Example output** (summary):
```
Archive Summary Statistics
  Total exposures: 1,331
  Observing nights: 14
  Night range: 20201201 to 20201230

Note
  Archive metadata (filter, exptime, object, etc.) is not indexed.
  For detailed analysis, download files and inspect FITS headers.
  Use 'nights' command to see per-night file counts.
```

**Example output** (nights):
```
┏━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Night    ┃ File_Count ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 20201201 │ 182        │
│ 20201202 │ 44         │
│ 20201204 │ 129        │
└──────────┴────────────┘
```

### EDA Tools - Butler Repository Inspection

Explore and analyze Butler repository contents:

```bash
# List all collections, organized by type
obsn-eda-butler collections --repo /path/to/repo

# Filter collections by pattern
obsn-eda-butler collections --repo /path/to/repo --pattern "Nickel/runs/*/diff/*"

# Show dataset inventory for a collection
obsn-eda-butler datasets --repo /path/to/repo --collection "Nickel/runs/20240625/processCcd/*/run"

# Check calibration coverage across nights
obsn-eda-butler calibs --repo /path/to/repo --nights 20240601,20240602,20240603

# Show template availability by tract and band
obsn-eda-butler templates --repo /path/to/repo
obsn-eda-butler templates --repo /path/to/repo --band r --format csv
```

**Environment**: Set `$REPO` to avoid repeating `--repo` argument

**Example output** (collections):
```
Butler Collections
  Repository: /data/nickel/butler

Raw Collections (12)
  [RUN] Nickel/raw/20240625/20240626T123456Z
  [RUN] Nickel/raw/20240626/20240627T123456Z
  ...

Calibrations Collections (8)
  [CHAIN] Nickel/calib/current
  [RUN] Nickel/calib/20240625
  [RUN] Nickel/cp/20240625/bias/20240626T123456Z/run
  ...

Templates Collections (4)
  [RUN] templates/deep/tract071/r/20240701T123456Z
  ...
```

**Example output** (calibs):
```
Calibration Coverage by Night
┏━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━┓
┃ Night    ┃ Bias  ┃ Flat  ┃ Dark  ┃ Defects ┃
┡━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━┩
│ 20240625 │ 10    │ 15    │ ✗     │ ✓       │
│ 20240626 │ 12    │ 18    │ ✗     │ ✓       │
└──────────┴───────┴───────┴───────┴─────────┘
```

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

### Archive Tools

- `RAW_PARENT_DIR` - Root directory for raw data storage
- `LICK_ARCHIVE_URL` - Archive API base URL (default: https://archive.ucolick.org/archive)
- `LICK_ARCHIVE_DIR` - Path to lick_searchable_archive client library
- `LICK_ARCHIVE_INSTR` - Instrument filter (default: NICKEL_DIR)

### Butler Tools

- `REPO` - Butler repository path (used by EDA butler commands)

## Dependencies

Core dependencies (automatically installed):
- `numpy`, `pandas` - Data manipulation
- `astropy` - Astronomy utilities
- `rich` - Terminal formatting and tables
- `matplotlib` - Plotting and visualization

LSST Stack dependencies (must be available in environment):
- `lsst.daf.butler` - Butler data repository access
- `lsst.pipe.base` - Pipeline infrastructure

## Development

The package uses a standard setuptools layout:

```
packages/data_tools/
├── src/
│   └── obs_nickel_data_tools/
│       ├── pipeline_tools/      # Archive download, PS1 ingest
│       ├── skymap/              # Skymap utilities
│       └── eda/                 # Exploratory data analysis
│           ├── archive_query.py # Archive exploration
│           ├── butler_inspect.py # Butler repo inspection
│           └── formatters.py    # Output formatting utilities
├── pyproject.toml
└── README.md
```

All CLI entry points are defined in `pyproject.toml` under `[project.scripts]`.

## Legacy Notes

The original scripts under `scripts/python/pipeline_tools/` and `scripts/python/skymap/` have been removed. Use the `obsn-*` CLI entrypoints (or `python -m obs_nickel_data_tools...`) instead; the pipeline scripts in this repo now call the entrypoints directly.
