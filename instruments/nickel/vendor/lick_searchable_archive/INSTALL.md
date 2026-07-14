# Installation Instructions

This package can be installed using `uv`, a modern Python package manager.

## Prerequisites

Make sure you have `uv` installed. If not, install it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installation for Development or Local Use

### 1. Create a virtual environment

```bash
uv venv
```

This creates a `.venv` directory with a Python virtual environment.

### 2. Activate the virtual environment

```bash
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

### 3. Install the package in editable mode

To install the package with just the basic client dependencies:

```bash
uv pip install -e .
```

To install with optional coordinate query support:

```bash
uv pip install -e ".[coords]"
```

To install with all web application dependencies:

```bash
uv pip install -e ".[web]"
```

To install with development dependencies:

```bash
uv pip install -e ".[dev]"
```

## Installation in Another Project (e.g., obs_nickel)

From your `obs_nickel` project directory:

### Option 1: Install from local path

```bash
# Activate your obs_nickel virtual environment first
uv pip install -e /path/to/lick_searchable_archive
```

### Option 2: Install from Git repository (once published)

```bash
uv pip install git+https://github.com/lick-observatory/lick-searchable-archive.git
```

### Option 3: Add to your pyproject.toml

In your `obs_nickel` project's `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... other dependencies ...
    "lick-searchable-archive @ file:///path/to/lick_searchable_archive",
    # or once published to git:
    # "lick-searchable-archive @ git+https://github.com/lick-observatory/lick-searchable-archive.git",
]
```

Then run:

```bash
uv sync
```

## Usage After Installation

Once installed, you can import the client classes:

```python
from lick_archive import LickArchiveClient, QueryTerm, LickArchiveIngestClient

# Or import directly from the client module:
from lick_archive.client import LickArchiveClient, QueryTerm

# Create a client instance
client = LickArchiveClient("https://archive.ucolick.org/archive")

# Use the client...
```

## Verifying Installation

After installation, verify everything works:

```bash
python -c "from lick_archive import LickArchiveClient; print('Successfully imported LickArchiveClient')"
```
