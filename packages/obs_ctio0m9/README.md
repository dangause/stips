# obs_ctio0m9

LSST Science Pipelines instrument package for the CTIO/SMARTS 0.9m telescope.

## Features

- Single-amplifier readout mode (Tek2K CCD)
- Johnson-Cousins UBVRI filter support
- Dual filter wheel handling

## Installation

```bash
pip install -e .
```

Or with EUPS:

```bash
setup -r . obs_ctio0m9
```

## Usage

```python
from lsst.obs.ctio0m9 import Ctio0m9

# Register instrument with Butler
butler.registry.registerInstrument(Ctio0m9())
```
