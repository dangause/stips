# obs_smalltel

LSST Science Pipelines instrument package for small telescopes. Currently supports:

- **Nickel** - Lick Observatory 1-meter telescope
- **CTIO 0.9m** - Cerro Tololo Inter-American Observatory 0.9-meter (SMARTS)

## Architecture

The package uses a data-driven configuration approach where each instrument's specifics are defined in YAML files rather than hardcoded Python:

```
obs_smalltel/
├── instruments/
│   ├── nickel/           # Nickel 1-m YAML configurations
│   │   ├── camera.yaml       # Detector geometry (2048x2048 CCD)
│   │   ├── filters.yaml      # Filter definitions (B, V, R, I)
│   │   └── header_map.yaml   # FITS keyword mappings
│   └── ctio0m9/          # CTIO 0.9m YAML configurations
│       ├── camera.yaml       # Detector geometry (SITE2K 2048x2046)
│       ├── filters.yaml      # Filter definitions (B, V, R, I)
│       └── header_map.yaml   # FITS keyword mappings
├── pipelines/            # Pipeline definitions
│   ├── DRP.yaml              # Full data release (shared)
│   ├── DIA.yaml              # Difference imaging (shared)
│   ├── NickelCpBias.yaml     # Nickel bias calibration
│   ├── NickelCpFlat.yaml     # Nickel flat calibration
│   ├── Ctio0m9CpBias.yaml    # CTIO bias calibration
│   ├── Ctio0m9CpFlat.yaml    # CTIO flat calibration
│   └── ...
├── configs/              # Python pipeline config overrides
│   ├── nickel/               # Nickel-specific configs
│   └── ctio0m9/              # CTIO-specific configs
└── python/
    └── lsst/obs/smalltel/
        ├── nickel/           # Nickel instrument class + translator
        └── ctio0m9/          # CTIO instrument class + translator
```

## Instrument Classes

Both instruments inherit from `GenericSmallTelInstrument`, which provides:
- YAML-based camera geometry loading
- YAML-based filter definitions
- Configurable FITS header translation via `ConfigurableTranslator`

```python
from lsst.obs.smalltel import Nickel, Ctio0m9

# Each instrument is a fully LSST-compatible Instrument
nickel = Nickel()
ctio = Ctio0m9()
```

## Adding a New Instrument

1. Create YAML configurations in `instruments/<name>/`:
   - `camera.yaml` - detector geometry
   - `filters.yaml` - filter definitions
   - `header_map.yaml` - FITS keyword mappings

2. Create instrument class in `python/lsst/obs/smalltel/<name>/`:
   - `instrument.py` - inherit from `GenericSmallTelInstrument`
   - `translator.py` - inherit from `ConfigurableTranslator`
   - `formatter.py` - raw data formatter (optional, can inherit)

3. Add pipeline definitions in `pipelines/<Name>*.yaml`

4. Register translator entry point in `pyproject.toml`

5. Export from `__init__.py`

## Installation

```bash
# From the monorepo root
pip install -e packages/obs_smalltel

# Or with the LSST stack
setup -r packages/obs_smalltel obs_smalltel
```

## Usage with Butler

```bash
# Register instrument with a Butler repository
butler register-instrument /path/to/repo lsst.obs.smalltel.Nickel
butler register-instrument /path/to/repo lsst.obs.smalltel.Ctio0m9

# Run pipelines
pipetask run -b /path/to/repo \
    -p $OBS_SMALLTEL_DIR/pipelines/NickelCpBias.yaml \
    -i Nickel/raw/20230519 \
    -o Nickel/calib/20230519/bias
```

## Related Packages

- **data_tools** - CLI and operational tools with `InstrumentPlugin` system
- **obs_nickel_data** / **obs_ctio0m9_data** - Curated calibrations (defects, etc.)
