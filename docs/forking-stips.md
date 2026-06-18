# Forking STIPS for a New Telescope

STIPS runs the LSST Science Pipelines on small (1-meter, single-CCD) telescopes.
The design splits cleanly into a **generic framework** and a per-telescope
**instrument profile**. To adopt STIPS for your telescope you fork the repo and
add **one** instrument package (`obs_<your_instrument>`) that describes your
hardware and header conventions. You do not modify the framework.

This guide walks through that fork end to end, using the reference instrument
`obs_nickel` (Lick Observatory's Nickel 1-m) as the worked example.

---

## 1. Overview: framework vs. fork

**The framework — you do NOT touch these:**

| Package | Import root | What it provides |
|---------|-------------|------------------|
| `stips` | `stips` | The `stips` CLI + tooling. Exposes `stips.InstrumentProfile`, `stips.Site`, `stips.Field`, `stips.hook`. Selects the active instrument via the `INSTRUMENT_PACKAGE` env var (default `lsst.obs.nickel`), imports `<pkg>.profile`, and drives all collection names / Butler queries / skymap from the profile. |
| `obs_stips` | `lsst.obs.stips` | Generic LSST glue: `StipsInstrument`, `StipsTranslator`, `StipsRawFormatter`, and shared pipeline tasks under `lsst.obs.stips.tasks.*`. |

**The fork — you DO write this:**

| Package | Import root | What it is |
|---------|-------------|-----------|
| `obs_<x>` | `lsst.obs.<x>` | Your instrument package. The heart is `profile.py` (one `InstrumentProfile(...)`). Everything else is thin bindings, a camera geometry file, and instrument-tuned pipelines/configs. |

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
git checkout -b feature/obs-<x>
```

---

## 3. Step 2 — Create your instrument package

Copy `obs_nickel` as your template, then rename. This is faster and safer than
starting from scratch — it gives you a working file layout, bindings, and a real
example for every field.

```bash
cp -r packages/obs_nickel packages/obs_<x>
```

Resulting layout (rename the `nickel` python dir to `<x>` and remove
`__pycache__`):

```
packages/obs_<x>/
├── pyproject.toml                       # package metadata + translator entry point
├── camera/
│   └── <x>.yaml                         # LSST yamlCamera geometry (detectors, plate scale)
├── pipelines/                           # instrument-tuned pipeline YAMLs (copy & tune)
├── configs/                             # pipeline task config overrides (copy & tune)
└── python/lsst/obs/<x>/
    ├── __init__.py                      # imports profile + bindings (copy as-is, rename symbols)
    ├── profile.py                       # THE file you edit — your InstrumentProfile
    ├── translator.py                    # binding: class <X>Translator(StipsTranslator)
    ├── _instrument.py                   # binding: class <X>(StipsInstrument)
    ├── rawFormatter.py                  # binding: class <X>RawFormatter(StipsRawFormatter)
    ├── calibCombine.py                  # instrument quirk task — keep only if needed
    └── visitInfo.py                     # instrument quirk task — keep only if needed
```

Rename the python package directory:

```bash
git -C packages/obs_<x> mv python/lsst/obs/nickel python/lsst/obs/<x>
rm -rf packages/obs_<x>/python/lsst/obs/<x>/__pycache__
```

---

## 4. Step 3 — Write `profile.py` (the heart)

`profile.py` builds one `stips.InstrumentProfile(...)` object plus a few
`@hook(profile)` functions. The real Nickel constructor call looks like this
(values are the actual Nickel values):

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
    eups_package="obs_nickel",
    instrument_class="lsst.obs.nickel.Nickel",
    night_to_dayobs_offset_days=1,
    skymap_name="nickelRings-v1",
    skymap_collection="skymaps/nickelRings",
    obs_data_package="obs_nickel_data",
    package_dir="lsst.obs.nickel",
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
- **`camera`** *(required)* — Relative path to your camera geometry YAML, e.g.
  `"camera/<x>.yaml"`.
- **`eups_package`** — EUPS package name (`"obs_nickel"`).
- **`instrument_class`** — Fully-qualified instrument class path used by
  `butler register-instrument`, e.g. `"lsst.obs.<x>.<X>"`.
- **`night_to_dayobs_offset_days`** — Offset between local observing night and
  UTC `day_obs` (Nickel: `1`, since Pacific-evening obs roll into the next UTC
  day).
- **`collection_prefix`** — Butler collection prefix. Defaults to `name` if
  omitted, so Nickel collections begin with `Nickel/...`.
- **`skymap_name` / `skymap_collection`** — Skymap registry name and its
  collection (`"nickelRings-v1"`, `"skymaps/nickelRings"`).
- **`obs_data_package`** — Optional companion data package with curated calibs
  (`"obs_nickel_data"`).
- **`policy_name`**, **`package_dir`**, **`refcat_path`**, **`fetch_data`** —
  Optional. `policy_name` defaults to `name`; the rest are advanced/optional.

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

## 5. Step 4 — Bindings, camera, pyproject

### Bindings (3 thin classes)

The bindings just attach your `profile` to the generic framework classes. Copy
Nickel's and rename. These are complete files, not snippets:

```python
# python/lsst/obs/<x>/translator.py
from lsst.obs.stips.translator import StipsTranslator
from .profile import profile

class <X>Translator(StipsTranslator):
    profile = profile
```

```python
# python/lsst/obs/<x>/_instrument.py
from lsst.obs.stips.instrument import StipsInstrument
from .profile import profile
from .translator import <X>Translator

class <X>(StipsInstrument):
    profile = profile
    translatorClass = <X>Translator

    def getRawFormatter(self, dataId):
        from .rawFormatter import <X>RawFormatter   # local import breaks the cycle
        return <X>RawFormatter
```

```python
# python/lsst/obs/<x>/rawFormatter.py
from lsst.obs.stips.formatter import StipsRawFormatter
from ._instrument import <X>
from .translator import <X>Translator

class <X>RawFormatter(StipsRawFormatter):
    instrumentClass = <X>
    translatorClass = <X>Translator
    filterDefinitions = <X>.filterDefinitions
```

`__init__.py` wires these together (exports `profile`, the translator, and —
guarded by `try/except ImportError` so the translator works even without the
full LSST stack — the instrument, raw formatter, and any quirk tasks like
`calibCombine`/`visitInfo`). Copy Nickel's verbatim and rename the symbols.

### Camera geometry

`camera/<x>.yaml` is a standard LSST `yamlCamera`-format file describing detector
layout, pixel size, and plate scale. For a single-CCD telescope this is one
detector. Use `camera/nickel.yaml` as your template and edit the dimensions,
pixel scale, and detector name/serial to match your CCD.

### pyproject.toml

Copy `obs_nickel/pyproject.toml` and change the package name, the
`astro_metadata_translator` entry point, and the workspace sources:

```toml
[project]
name = "obs-<x>"
# ...
dependencies = ["obs-stips", "stips", "astro_metadata_translator>=0.11.0", "astropy"]

[project.entry-points."astro_metadata_translator.translators"]
<X> = "lsst.obs.<x>.translator:<X>Translator"

[tool.uv.sources]
obs-stips = { workspace = true }
stips = { workspace = true }

[tool.setuptools.packages.find]
where = ["python"]
```

The entry point is what makes `astro_metadata_translator` discover your
translator when reading raw FITS.

---

## 6. Step 5 — Pipelines & configs

Copy `obs_nickel/pipelines/` and `obs_nickel/configs/` into your package and tune
them for your instrument. Two rules:

- **Generic tasks stay generic.** Pipeline steps that reference
  `lsst.obs.stips.tasks.*` are framework tasks — keep those references as-is.
- **Instrument quirk tasks stay in your package.** If your telescope needs a
  custom step (Nickel keeps `calibCombine.py` and `visitInfo.py`), reference it
  as `lsst.obs.<x>.<module>.<Task>` and ship the module in your package. Only
  write a quirk task if a generic one doesn't fit.

The Nickel pipelines (`DRP.yaml`, `DIA.yaml`, `ForcedPhotRaDec.yaml`,
`ProcessCcd.yaml`, the CpBias/CpFlat calib pipelines, etc.) and the `configs/`
overrides (`calibrateImage/`, `dia/`, `coadds/`, `makeSkyMap.py`, ...) are good
starting points — most tuning is relaxing thresholds for a small-aperture,
sparse-field instrument.

---

## 7. Step 6 — Install & point STIPS at your instrument

Install your package into the dev environment so it is importable in the venv
(the framework imports `lsst.obs.<x>.profile` at runtime — it must be on the
Python path):

```bash
# either install editable directly...
uv pip install -e packages/obs_<x>

# ...or add it to the uv workspace (packages/* is already a member) and sync
uv sync
```

Then tell STIPS which instrument is active:

```bash
export INSTRUMENT_PACKAGE=lsst.obs.<x>
```

`INSTRUMENT_PACKAGE` defaults to `lsst.obs.nickel`. You can also set it in your
`.env` file (it is one of the recognized env keys) or inline in a YAML pipeline
config. Once set, `stips` imports `lsst.obs.<x>.profile`, and every collection
name, Butler query, and skymap reference is driven by your profile — collections
become `<your collection_prefix>/...`.

> If the package isn't installed, config loading does **not** crash: the profile
> is left as `None` and commands that need it raise a clear "pip install it and
> set INSTRUMENT_PACKAGE" error. If you hit that, your obs package isn't
> importable in the active venv.

---

## 8. Step 7 — Run

Same CLI, your instrument:

```bash
stips bootstrap                 # create repo, register your instrument, ingest refcats, skymap
stips calibs <night>            # build bias/flat, certify
stips science <night> --ra <RA> --dec <DEC>
stips dia <night> --auto
stips fphot <night> --ra <RA> --dec <DEC>
stips lightcurve --ra <RA> --dec <DEC> --collections <...>
# or drive the whole thing from a YAML config:
stips run scripts/config/<target>/pipeline.yaml
```

---

## 9. Verifying & common gotchas

**Translation parity — test first.** Before running pipelines, point
`astro_metadata_translator` at a real raw FITS header from your telescope and
confirm the translator resolves `physical_filter`, `observation_type`,
`exposure_id`, `datetime_begin/end`, `day_obs`, and `tracking_radec` to sane
values. Most fork bugs are header-mapping bugs, and they surface here cheaply.

**Checklist:**

- [ ] `name`, `site`, `filters`, `header_map`, `camera` set (the required fields).
- [ ] `filter_aliases` covers every spelling your headers actually emit (check
      real files, not the manual).
- [ ] `filter_key` matches your FITS filter keyword.
- [ ] A `@hook` exists for every header quirk (observation typing, coordinate
      bugs, exposure-ID scheme, temperature units, datetime derivation).
- [ ] Bindings renamed: `<X>Translator`, `<X>`, `<X>RawFormatter`.
- [ ] `camera/<x>.yaml` reflects your CCD dimensions, pixel scale, plate scale.
- [ ] `pyproject.toml` name + `astro_metadata_translator` entry point renamed.
- [ ] `instrument_class` points to `lsst.obs.<x>.<X>`.
- [ ] Package installed editable in the venv (`uv pip install -e` or `uv sync`).
- [ ] `INSTRUMENT_PACKAGE=lsst.obs.<x>` exported / in `.env`.
- [ ] Translator parity verified against a real header.

**Other gotchas:**

- **Single-CCD assumption.** STIPS targets single-detector cameras. A
  multi-detector mosaic needs more than a profile and is out of scope here.
- **Camera geometry matters.** A wrong plate scale or detector size silently
  corrupts WCS fitting and source matching. Get `camera/<x>.yaml` right early.
- **`night_to_dayobs_offset_days`.** Local observing night vs. UTC `day_obs`
  trips up collection naming and Butler queries — set it correctly for your
  longitude (Nickel uses `1`).
- **`exposure_id` must fit 31 bits.** If your scheme can overflow, the hook
  should raise (Nickel's does) rather than silently wrap.
- **Hooks return the right types.** `temperature` returns an astropy
  `Quantity`; `datetime_*` return `astropy.time.Time`; `tracking_radec` returns
  a `SkyCoord`. Match the framework's expectations.
