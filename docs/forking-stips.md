# Forking STIPS for a New Telescope

STIPS runs the LSST Science Pipelines on small (1-meter, single-CCD) telescopes.
The design splits cleanly into a **generic framework** and a per-telescope
**declarative instrument definition**. To adopt STIPS for your telescope you fork
the repo and add **one directory** — `instruments/<your_instrument>/` — that
describes your hardware and header conventions. **You write no LSST Python: no
instrument class, no translator/formatter bindings, no `pyproject.toml`, no EUPS
table.** The generic `obs_stips` package synthesizes all of that from your
profile at runtime.

This guide walks through that fork end to end, using the reference instrument
`instruments/nickel/` (Lick Observatory's Nickel 1-m) as the worked example.

---

## 1. Overview: framework vs. fork

**The framework — you do NOT touch these:**

| Package | Import root | What it provides |
|---------|-------------|------------------|
| `stips` | `stips` | The `stips` CLI + tooling. Exposes `stips.InstrumentProfile`, `stips.Site`, `stips.Field`, `stips.hook`. Loads the active instrument's `profile.py` **by path** from `INSTRUMENT_DIR`, and drives all collection names / Butler queries / skymap from the profile. |
| `obs_stips` | `lsst.obs.stips` | Generic LSST glue. The `lsst.obs.stips.active` submodule **synthesizes** a concrete, registerable instrument + translator + raw formatter from your profile (Butler registers `lsst.obs.stips.active.Instrument` — the same class for every fork). Also ships the shared/generic pipeline tasks (`StipsCalibCombineTask`, `lsst.obs.stips.tasks.*`). |

**The fork — you DO write this (data, not code):**

| Location | What it is |
|----------|-----------|
| `instruments/<x>/` | Your telescope definition: `profile.py` (one `InstrumentProfile(...)` + a few `@hook`s), a camera geometry YAML, and instrument-tuned pipelines/configs. **Loaded by path** — it is *not* an importable Python package. |

**Honest scope.** STIPS targets **1-meter, single-CCD** telescopes. The generic
translator handles the common FITS conventions; your telescope's header quirks
are absorbed by a handful of `@hook` functions in `profile.py`. Nickel needed
about seven hooks (filter fallback, observation typing, a coordinate-header bug,
an exposure-ID scheme, temperature units, and datetime/day_obs derivation). Plan
for a similar order of magnitude.

---

## 2. Step 1 — Fork & branch

```bash
# Fork the repo on your host (GitHub fork, or a clone you control), then:
git clone <your-fork-url> stips
cd stips
git checkout -b feature/instrument-<x>
```

---

## 3. Step 2 — Create your instrument directory

Copy `instruments/nickel/` as your template. There is no package to scaffold,
nothing to rename in Python, no metadata files to edit — it is pure data:

```bash
cp -r instruments/nickel instruments/<x>
rm -rf instruments/<x>/tests   # optional: keep & adapt, or start fresh
```

Resulting layout:

```
instruments/<x>/
├── profile.py                 # THE file you edit — your InstrumentProfile + @hooks
├── camera/
│   └── <x>.yaml               # LSST yamlCamera geometry (detectors, plate scale)
├── pipelines/                 # instrument-tuned pipeline YAMLs (copy & tune)
├── configs/                   # pipeline task config overrides (copy & tune)
├── fetch.py                   # OPTIONAL: a data-fetch hook (delete if you place raws by hand)
└── tests/                     # OPTIONAL: reference tests, adapt to your golden values
```

That's the whole fork. No `python/lsst/obs/<x>/`, no bindings, no
`pyproject.toml`, no `ups/` table — `obs_stips` builds the LSST instrument
machinery from `profile.py` at runtime.

---

## 4. Step 3 — Write `profile.py` (the heart)

`profile.py` builds one `stips.InstrumentProfile(...)` object plus a few
`@hook(profile)` functions, and assigns it to a module-level `profile`. The
framework loads this file **by path** (so the imports below resolve against the
installed `stips`). The real Nickel constructor call looks like this:

```python
from stips import Field, InstrumentProfile, Site, hook

profile = InstrumentProfile(
    name="Nickel",
    policy_name="Nickel",                 # defaults to name if omitted
    site=Site(
        latitude=37.3414,
        longitude=-121.6429,
        elevation=1283.0,
        name="Lick Observatory",          # if set, uses EarthLocation.of_site(name)
    ),
    # physical_filter -> band
    filters={
        "B": "b", "V": "v", "R": "r", "I": "i",
        "clear": None, "gp": "gp", "rp": "rp",
        "Halpha": "halpha", "OIII": "oiii",
    },
    # raw FITS filter value (upper-cased on lookup) -> physical_filter
    filter_aliases={
        "B": "B", "V": "V", "R": "R", "I": "I",
        "OPEN": "clear", "C": "clear", "CLEAR": "clear",
        "GP": "gp", "G'": "gp", "RP": "rp", "R'": "rp",
        "HALPHA": "Halpha", "H-ALPHA": "Halpha", "6563/100": "Halpha",
        "OIII": "OIII", "[OIII]": "OIII", "5000/100": "OIII",
    },
    filter_key="FILTNAM",                 # FITS keyword holding the raw filter name
    header_map={
        "exposure_time":      Field("EXPTIME", unit="s", default=0.0),
        "dark_time":          Field("EXPTIME", unit="s", default=0.0),
        "boresight_airmass":  Field("AIRMASS", default=float("nan")),
        "object":             Field("OBJECT", default="UNKNOWN"),
        "science_program":    Field("PROGRAM", default="unknown"),
        "relative_humidity":  Field("HUMIDITY", default=0.0),
        "telescope":          Field("TELESCOP", default="Nickel 1m"),
    },
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera="camera/nickel.yaml",
    instrument_class="lsst.obs.stips.active.Instrument",   # see note — same for every fork
    night_to_dayobs_offset_days=1,
    skymap_name="nickelRings-v1",
    skymap_collection="skymaps/nickelRings",
    obs_data_package="obs_nickel_data",
)
```

### Field-by-field

These are the real `InstrumentProfile` fields (from
`packages/stips/src/stips/profile.py`). Required fields have no default.

- **`name`** *(required)* — Instrument name, e.g. `"Nickel"`. Used for
  registration and as the default `collection_prefix`/`policy_name`.
- **`site`** *(required)* — A `stips.Site(latitude, longitude, elevation, name=None)`.
  If `name` is set, the translator resolves the location via
  `EarthLocation.of_site(name)` and the lat/lon/elev are informational
  fallbacks. If your observatory is not in astropy's site registry, leave
  `name=None` and the geodetic lat/lon/elev are used.
- **`filters`** *(required)* — `physical_filter -> band` map. This is the
  canonical filter registry that drives the LSST `FilterDefinitionCollection`.
  A band of `None` (Nickel's `"clear"`) means "no canonical band".
- **`filter_aliases`** — `raw FITS value -> physical_filter`. Lookup is
  case-insensitive. Map every spelling your headers actually emit (Nickel maps
  `OPEN`/`C`/`CLEAR` → `clear`, `G'` → `gp`, `6563/100` → `Halpha`, etc.).
- **`filter_key`** — FITS keyword holding the raw filter name. Default
  `"FILTNAM"`; Nickel uses the default.
- **`header_map`** *(required)* — `metadata field -> stips.Field(key, unit=None,
  default=None)`. Each `Field` maps an LSST metadata slot to a FITS keyword,
  with an astropy unit name (e.g. `"s"`) and a default for missing keys. Map the
  fields your telescope's headers provide directly; anything that needs logic
  goes in a `@hook` instead.
- **`const_map`** — Constants for metadata that your headers don't carry (Nickel
  has no rotator, so `boresight_rotation_angle: 0.0`).
- **`camera`** *(required)* — Path to your camera geometry YAML **relative to
  `instruments/<x>/`**, e.g. `"camera/<x>.yaml"`. Loaded from `INSTRUMENT_DIR`.
- **`instrument_class`** — The fully-qualified instrument class
  `butler register-instrument` uses. **Keep the Nickel value
  `"lsst.obs.stips.active.Instrument"` unchanged** — this is the generic class
  `obs_stips` synthesizes from your profile; it is the *same string for every
  instrument*. You do not write or name an instrument class.
- **`night_to_dayobs_offset_days`** — Offset between local observing night and
  UTC `day_obs` (Nickel: `1`, since Pacific-evening obs roll into the next UTC
  day).
- **`collection_prefix`** — Butler collection prefix. Defaults to `name` if
  omitted, so Nickel collections begin with `Nickel/...`.
- **`skymap_name` / `skymap_collection`** — Skymap registry name and its
  collection (`"nickelRings-v1"`, `"skymaps/nickelRings"`).
- **`obs_data_package`** — Optional companion EUPS data package with curated
  calibs / defects / crosstalk (`"obs_nickel_data"`). Left as a normal EUPS
  package; the stack activation sets it up by name. Omit if you have none.
- **`fetch_data`** — Optional callable hook: `fetch_data(night, config, *,
  overwrite=False) -> "ok" | "not_found" | "failed"`, used by `stips download`.
  Wire it from a co-located module (Nickel's `profile.py` does `from fetch import
  fetch_data` — the loader puts `instruments/<x>/` on `sys.path` so a co-located
  `fetch.py` is importable). Leave unset if you place raws by hand.
- **`policy_name`**, **`refcat_path`** — Optional; `policy_name` defaults to `name`.

### Quirk hooks (`@hook(profile)`)

Hooks override individual translation methods. Register one by decorating a
function whose name matches the method; the function takes `header` (and, for a
few, a `default`/`raw` argument). Write a hook only when a header field needs
logic beyond a flat `header_map` lookup. The hooks Nickel actually defines:

- **`observation_type(header)`** — Classify the frame (`science`, `flat`,
  `bias`, `dark`, `focus`) from your `OBSTYPE`/`OBJECT` strings.
- **`observation_reason(header)`** — `calibration` / `focus` / `test` /
  `pointing` / `science`.
- **`temperature(header)`** — Return an astropy `Quantity`. Nickel reads
  `TEMPDET` in Celsius and converts to Kelvin.
- **`exposure_id(header)` / `visit_id(header)`** — Build a unique ID that fits in
  31 bits. Nickel uses `days_since_2000 * 10000 + OBSNUM`.
- **`datetime_begin(header)` / `datetime_end(header)`** — Nickel prefers
  `DATE-BEG`/`DATE-END`, falls back to `DATE-OBS`, and synthesizes the end from
  `begin + EXPTIME` when `DATE-END` is missing or bad.
- **`day_obs(header)` / `observation_id(header)`** — Derive `YYYYMMDD` and a
  globally-unique string ID.
- **`unknown_filter(header, raw)`** — Fallback when `filter_aliases` has no
  match (Nickel logs a warning and returns `"clear"`).
- **`tracking_radec(header, default=None)`** — Coordinate read with quirk
  handling. Nickel's `CRVAL1/CRVAL2` (WCS) sometimes disagree with `RA`/`DEC`
  (telescope control); the hook calls `default()` for the generic CRVAL read,
  compares against the sexagesimal `RA`/`DEC`, and falls back to the control
  values when they diverge by more than 1°.

A short, realistic hook example:

```python
@hook(profile)
def observation_type(header):
    """Return one of: science | flat | bias | dark | focus."""
    obstype = header.get("OBSTYPE", "").strip().lower()
    obj = header.get("OBJECT", "").strip().lower()
    if obstype == "dark":
        return "bias" if "bias" in obj else "dark"
    if obstype == "flat" or "flat" in obj:
        return "flat"
    if any(w in obj for w in ("focus", "point", "test")):
        return "focus"
    return "science"


@hook(profile)
def temperature(header):
    import astropy.units as u
    return (header.get("TEMPDET", -999.0) + 273.15) * u.K
```

---

## 5. Step 4 — Camera geometry

There are two ways to give STIPS a camera.

**Simple path — `CameraSpec`.** For a single-CCD, geometry-only camera, set
`profile.camera` to a `CameraSpec` (imported from `stips`) instead of a YAML
path. You declare CCD size, pixel size, plate scale, and orientation, and STIPS
synthesizes a usable LSST camera in-memory with a default single-amp readout:

```python
from stips import CameraSpec

profile = InstrumentProfile(
    ...,
    camera=CameraSpec(
        nx=1024, ny=1024,
        pixel_size_um=30.0,
        plate_scale_arcsec_per_pixel=0.368,
        flip_x=False, flip_y=True,
    ),
)
```

`gain` / `read_noise` / `saturation` are optional (sensible defaults). This is
all most single-CCD telescopes need.

**Full-control escape hatch — `camera/<x>.yaml`.** A standard LSST
`yamlCamera`-format file describing detector layout, amps, gain, and read noise.
Set `profile.camera` to its path (loaded from `INSTRUMENT_DIR`, no EUPS lookup);
use `camera/nickel.yaml` as a template. Nickel deliberately uses the YAML to get
real multi-amp / gain / read-noise fidelity that the simple `CameraSpec` path
does not model.

---

## 6. Step 5 — Pipelines & configs

Copy `instruments/nickel/pipelines/` and `instruments/nickel/configs/` into your
instrument dir and tune them. The rules:

- **Generic tasks stay generic.** Pipeline steps that reference
  `lsst.obs.stips.tasks.*` or `lsst.obs.stips.calibCombine.StipsCalibCombineTask`
  are framework tasks — keep those references as-is. (The robust calib-combine
  that Nickel used to ship is now a generic obs_stips task.)
- **Use `$INSTRUMENT_DIR` for in-instrument includes.** Pipeline `location:` /
  `file:` includes that point inside your instrument dir use the
  `$INSTRUMENT_DIR/...` env var (exported by the stack activation), e.g.
  `$INSTRUMENT_DIR/pipelines/nickel-analysis-dia-detector.yaml`.
- **`instrument:` is the generic class.** Pipelines with an `instrument:` field
  use `lsst.obs.stips.active.Instrument` (same as `profile.instrument_class`).
- **Genuinely instrument-specific tasks (rare).** If your telescope needs a
  custom PipelineTask that no generic one covers, ship a Python module in your
  instrument dir (namespaced, e.g. `instruments/<x>/<x>_tasks.py`, so it can't
  shadow a stack module), declare its FQN, and reference it from your pipeline.
  Nickel ships none — both of its old quirk tasks generalized into `obs_stips`.

The Nickel pipelines (`DRP.yaml`, `DIA.yaml`, `ForcedPhotRaDec.yaml`,
`ProcessCcd.yaml`, the CpBias/CpFlat calib pipelines, etc.) and the `configs/`
overrides are good starting points — most tuning is relaxing thresholds for a
small-aperture, sparse-field instrument.

---

## 7. Step 6 — Point STIPS at your instrument

There is **nothing to install** — the instrument is loaded by path. Just tell
STIPS where your instrument dir is, via the `env:` block of the config YAML you
pass with `-c`:

```yaml
env:
  INSTRUMENT_DIR: /path/to/stips/instruments/<x>
  # ...plus REPO, STACK_DIR, RAW_PARENT_DIR (and optional REFCAT_REPO, CP_PIPE_DIR)
```

`stips` loads `INSTRUMENT_DIR/profile.py` by path; `obs_stips` synthesizes the
LSST instrument from it and Butler registers `lsst.obs.stips.active.Instrument`
(which reports your `profile.name`). Every collection name, Butler query, and
skymap reference is driven by your profile — collections become
`<your collection_prefix>/...`.

> If `INSTRUMENT_DIR` is unset (or has no `profile.py`), the framework fails loud
> with a clear message rather than guessing. There is no `INSTRUMENT_PACKAGE` and
> no obs-package import — the old package-based selection is gone.

---

## 8. Step 7 — Run

Same CLI, your instrument. Pass your config once with the group-level `-c`:

```bash
CFG=scripts/config/<target>/pipeline.yaml
stips -c $CFG bootstrap                 # create repo, register your instrument, ingest refcats, skymap
stips -c $CFG calibs <night>            # build bias/flat, certify
stips -c $CFG science <night> --ra <RA> --dec <DEC>
stips -c $CFG dia <night> --auto
stips -c $CFG fphot <night> --ra <RA> --dec <DEC>
stips -c $CFG lightcurve --ra <RA> --dec <DEC> --collections <...>
# or drive the whole thing from the same YAML config:
stips -c $CFG run
```

---

## 9. Verifying & common gotchas

**Translation parity — test first.** Before running pipelines, point
`astro_metadata_translator` at a real raw FITS header from your telescope and
confirm the translator resolves `physical_filter`, `observation_type`,
`exposure_id`, `datetime_begin/end`, `day_obs`, and `tracking_radec` to sane
values. Most fork bugs are header-mapping bugs, and they surface here cheaply.
(`instruments/nickel/tests/test_translation_golden.py` shows the pattern: set
`INSTRUMENT_DIR`, import `lsst.obs.stips.active`, and assert on its `Translator`.)

**Checklist:**

- [ ] `name`, `site`, `filters`, `header_map`, `camera` set (the required fields).
- [ ] `filter_aliases` covers every spelling your headers actually emit (check
      real files, not the manual).
- [ ] `filter_key` matches your FITS filter keyword.
- [ ] A `@hook` exists for every header quirk (observation typing, coordinate
      bugs, exposure-ID scheme, temperature units, datetime derivation).
- [ ] `camera/<x>.yaml` reflects your CCD dimensions, pixel scale, plate scale.
- [ ] `instrument_class` left as `"lsst.obs.stips.active.Instrument"` (the generic class).
- [ ] `INSTRUMENT_DIR: /path/to/instruments/<x>` set in the config YAML's `env:` block.
- [ ] Translator parity verified against a real header.

**Other gotchas:**

- **Single-CCD assumption.** STIPS targets single-detector cameras. A
  multi-detector mosaic needs more than a profile and is out of scope here.
- **Camera geometry matters.** A wrong plate scale or detector size silently
  corrupts WCS fitting and source matching. Get `camera/<x>.yaml` right early.
- **Don't name your in-instrument files after stdlib/stack modules.** The loader
  puts `instruments/<x>/` on `sys.path` (so `profile.py`'s co-located hooks like
  `fetch.py` import). The framework appends it (so stdlib/installed modules still
  win), but avoid generic names that could collide if another path entry is added.
- **`night_to_dayobs_offset_days`.** Local observing night vs. UTC `day_obs`
  trips up collection naming and Butler queries — set it correctly for your
  longitude (Nickel uses `1`).
- **`exposure_id` must fit 31 bits.** If your scheme can overflow, the hook
  should raise (Nickel's does) rather than silently wrap.
- **Hooks return the right types.** `temperature` returns an astropy
  `Quantity`; `datetime_*` return `astropy.time.Time`; `tracking_radec` returns
  a `SkyCoord`. Match the framework's expectations.
- **One instrument per repo.** A Butler repo holds one synthesized instrument
  (the fork-per-telescope model). Multi-instrument repos are unsupported.
