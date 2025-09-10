README.md

# obs_nickel

Gen3 **obs** package for the **Nickel 1-m telescope (Lick Observatory)**.

This package provides:
- a single-detector camera model (`camera/nickel.yaml`),
- a FITS metadata translator (`NickelTranslator`),
- a raw formatter (`NickelRawFormatter`),
- filter definitions (Johnson/Bessell **B, V**; Cousins **R, I**),
- ingest and translator tests, and
- example pipeline runner(s).

> ✅ Tested locally with `lsst-scipipe-10.1.0`. Other recent LSST releases should work too.

---

## Quick start

### 0) Load the LSST stack and this package

    cd /path/to/your/stack               # STACK_DIR
    source loadLSST.zsh
    setup lsst_distrib
    # If developing locally:
    eups declare -r /path/to/obs_nickel obs_nickel -t current
    setup obs_nickel
    # optional (tests/ingest examples use it)
    setup testdata_nickel

### 1) Create a Gen3 repo & register the instrument

    REPO=/path/to/repo
    INSTRUMENT=lsst.obs.nickel.Nickel

    butler create "$REPO"
    butler register-instrument "$REPO" "$INSTRUMENT"

### 2) Ingest raws & define visits

    RAWDIR=/path/to/raws  # directory with Nickel FITS
    RUN="Nickel/raw/all"

    butler ingest-raws "$REPO" "$RAWDIR" --transfer symlink --output-run "$RUN"
    butler define-visits "$REPO" Nickel

### 3) (Optional) Minimal curated calibrations

This writes the **camera** dataset (and any other built-ins) to a timestamped collection.

    CURATED="Nickel/run/curated/$(date -u +%Y%m%dT%H%M%SZ)"
    butler write-curated-calibrations "$REPO" Nickel "$RUN" --collection "$CURATED"

    # form a small calib chain
    CALIB_CHAIN="Nickel/calib/current"
    butler collection-chain "$REPO" "$CALIB_CHAIN" "$CURATED" --mode redefine

### 4) Run a simple science pipeline (ProcessCcd)

    PIPE=/path/to/obs_nickel/pipelines/ProcessCcd.yaml
    OUT="Nickel/run/processCcd/$(date +%Y%m%d%H%M%S)"

    pipetask run \
      -b "$REPO" \
      -i "$RUN","$CALIB_CHAIN" \
      -o "$OUT" \
      -p "$PIPE#processCcd" \
      -d "instrument='Nickel' AND exposure.observation_type='science'" \
      -j 8 \
      --register-dataset-types

---

## Camera overview

- **Detector**: single CCD (`CCD0`), **imaging area 1024×1024**, right-side serial overscan **32 columns**
  (raw amp frame = 1056×1024).
- **Amplifiers**: 1 (`A00`).
- **Pixel size**: 15 μm.
- **Gain / read noise**: defaults set from on-telescope measurements (see YAML).
- **Saturation/linearity**: filled conservatively for initial release.

See `camera/nickel.yaml` for the authoritative configuration.

---

## Filters

Defined in `python/lsst/obs/nickel/nickelFilters.py`:

- `B` (band `b`) — Johnson/Bessell B
- `V` (band `v`) — Johnson/Bessell V
- `R` (band `r`) — Cousins R
- `I` (band `i`) — Cousins I

The **translator** reads `FILTNAM` and maps directly to the **physical filter** string.

---

## Metadata translator (`NickelTranslator`)

Key behavior (matches tests):

- **Instrument**: "Nickel"
- **Times**:
  - `to_datetime_begin`: `DATE-BEG` if present, else `DATE-OBS`
  - `to_datetime_end`: `DATE-END`, else `begin + EXPTIME`
- **Airmass**: from `AIRMASS` if present
- **Filter**: `FILTNAM` (stripped)
- **Location**: `EarthLocation.of_site("Lick Observatory")`
- **Tracking RA/Dec**: uses **primary WCS center** (`CRVAL1/CRVAL2`) and frame from `RADECSYS`/`RADESYS`
- **AltAz/pressure**: not provided in v1 (`None`)
- **Observation typing**: simple rules on `OBSTYPE` and `OBJECT`
  (`science`, `flat`, `dark`, `bias`, `focus`)

---

## Running tests

> Requires the `testdata_nickel` package.

    # after stack + obs_nickel + testdata_nickel are setup
    pytest -q

- `tests/test_translator.py` validates translator behavior.
- `tests/test_instrument.py` exercises camera & filter registration.
- `tests/test_ingest.py` performs a real ingest and **define-visits** check, and reads the raw back.
- Curated calibrations test is **intentionally skipped** for v1 (you can enable later).

---

## Example pipeline runner

A portable runner is provided in `scripts/run_nickel.sh` that:
- loads the stack,
- creates/updates a repo,
- ingests raws and defines visits,
- (optionally) writes curated calibs, builds CP bias/flats, defects, a calib chain,
- runs ProcessCcd and post-processing.

Run `scripts/run_nickel.sh -h` for usage.
If you have your own script, ensure it **doesn’t** hard-code personal paths; prefer flags/env.

---

## Contributing / dev hygiene

- Run formatting & linting pre-commit hooks:

      pre-commit install
      pre-commit run -a

- Please include tests for new translator/camera behavior.

---

## License

This package is intended to be distributed under **GPL-3.0** (or the license your org prefers).
