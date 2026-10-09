# The `obs` Abstraction: How Instrument Profiles Integrate with `obs_stips`

This document explains, in technical detail, how STIPS supports many telescopes from one
codebase: how an instrument is described, how that description is loaded, and how the generic
`obs_stips` LSST glue turns it into a concrete, Butler-registerable instrument at runtime.

> **Audience:** developers working on the framework or forking it for a new telescope.
> **Prerequisite:** familiarity with the LSST `obs_base` instrument/translator/formatter model.

---

## 1. The central idea

Telescope-specific knowledge is **never** baked into the framework code. Instead:

- The **framework** (`stips` + `obs_stips`) is written once and is fully instrument-neutral.
- Each **telescope** is a *declarative directory* — `instruments/<name>/` — whose `profile.py`
  is essentially a filled-in form (data + a few quirk callbacks).
- At runtime the framework **reads the profile and synthesizes** a concrete LSST instrument
  by binding the profile onto generic base classes.

Adding a telescope means creating a directory, not writing a package. Fixing a pipeline bug
means fixing it once in the framework; every telescope benefits.

```mermaid
flowchart TB
    subgraph FW["Framework (generic, shipped once)"]
        stips["<b>stips/</b><br/>CLI · Config · orchestration<br/>pipeline tooling"]
        obs_stips["<b>obs_stips/</b><br/>generic Instrument / Translator / Formatter<br/>default pipelines + configs"]
    end
    subgraph INST["Instruments (declarative data, one dir per telescope)"]
        nickel["<b>instruments/nickel/</b><br/>profile.py · camera/ · fetch.py"]
        ctio["<b>instruments/ctio1m/</b><br/>profile.py · camera/ · fetch.py"]
    end
    data["<b>obs_nickel_data/</b><br/>curated calibs (defects, crosstalk)"]

    stips -->|reads INSTRUMENT_DIR| nickel
    obs_stips -->|binds profile onto<br/>generic classes| nickel
    nickel -.declares.-> data

    classDef fw fill:#e3f2fd,stroke:#1565c0;
    classDef inst fill:#e8f5e9,stroke:#2e7d32;
    class stips,obs_stips fw;
    class nickel,ctio inst;
```

> **Doc drift note:** older docs/CLAUDE.md text refers to an importable `lsst.obs.nickel`
> package under `packages/obs_nickel/` selected by an `INSTRUMENT_PACKAGE` env var. That model
> was replaced by the "collapse" refactor described here: instruments are plain directories
> loaded **by path** via `INSTRUMENT_DIR`. There is no per-instrument importable package or
> EUPS product anymore.

---

## 2. The profile: one object describes the whole instrument

`InstrumentProfile` (`packages/stips/src/stips/profile.py:47`) is the single surface a forking
team edits. It is a dataclass holding everything instrument-specific as **data**, plus a small
dictionary of **hooks** for behavior that can't be expressed declaratively.

```mermaid
classDiagram
    class InstrumentProfile {
        +str name
        +Site site
        +dict filters          : physical_filter → band
        +dict filter_aliases   : raw FITS value → physical_filter
        +dict~str,Field~ header_map : metadata prop → FITS key
        +str|CameraSpec camera
        +str filter_key = "FILTNAM"
        +str instrument_header_value  : matched vs INSTRUME
        +dict const_map
        +str instrument_class  : FQN Butler persists
        +str collection_prefix
        +str skymap_name / skymap_collection
        +dict isr_overrides
        +str obs_data_package
        +Callable fetch_data
        +dict~str,Callable~ hooks
    }
    class Site {
        +float latitude / longitude / elevation
        +str name   : of_site() if set
    }
    class Field {
        +str key
        +str unit
        +Any default
    }
    class CameraSpec {
        +int nx / ny
        +float pixel_size_um
        +float plate_scale_arcsec_per_pixel
        +bool flip_x / flip_y
        +float gain / read_noise / saturation
    }
    InstrumentProfile --> Site
    InstrumentProfile --> "many" Field : header_map
    InstrumentProfile --> CameraSpec : camera (optional form)
```

### Two filter maps pointing opposite ways

A frequent point of confusion. The two dictionaries serve different stages:

| Field | Direction | Drives |
|-------|-----------|--------|
| `filters` | `physical_filter → band` | The canonical filter registry → `FilterDefinitionCollection` |
| `filter_aliases` | raw FITS value → `physical_filter` | `to_physical_filter()` during ingest |

For Nickel (`instruments/nickel/profile.py:28`): `filters` maps `"R" → "r"`, while
`filter_aliases` maps the messy header values `"R'"`, `"RP"`, `"rp"` onto a clean
`physical_filter`. Ingest normalizes header → physical_filter → band.

### Declarative fields vs. hooks

Simple mappings are data. Everything else is a **hook** — a function registered on the profile:

```python
@hook(profile)
def observation_type(header):
    ...  # classify object/flat/bias/dark/focus from messy OBJECT/OBSTYPE
```

The `hook` decorator (`profile.py:104`) simply stores the function in `profile.hooks[name]`.
Nickel's most important hook is `tracking_radec` (`instruments/nickel/profile.py:246`), which
works around the telescope's known stale-`DEC`-header bug by cross-checking `CRVAL1/2` against
the `RA`/`DEC` keywords.

---

## 3. Loading a profile: the dual by-path loader

A profile is loaded by **file path** (not by `import`), and it is loaded in **two different
runtime contexts** that don't share an interpreter — so there are two near-identical loaders
that must stay in lockstep.

```mermaid
flowchart LR
    subgraph A["CLI / Python context"]
        cfg["stips.core.config<br/>load_active_profile()<br/>config.py:19"]
    end
    subgraph B["LSST-stack subprocess context"]
        ldr["lsst.obs.stips.profile_loader<br/>load_profile_from_dir()<br/>profile_loader.py:18"]
    end
    dir["INSTRUMENT_DIR<br/>= instruments/nickel/"]
    py["profile.py"]
    obj["profile object<br/>(InstrumentProfile)"]

    cfg -->|importlib by path| py
    ldr -->|importlib by path| py
    dir --> py
    py --> obj

    note["Two loaders kept in sync<br/>by convention (code comments)"]
    cfg -.-> note
    ldr -.-> note
```

**Why two loaders?**

- `stips.core.config.load_active_profile()` runs in the CLI's own Python (full `stips`
  available). It populates `Config.profile`.
- `lsst.obs.stips.profile_loader.load_profile_from_dir()` is **stdlib-only**, because it runs
  inside the bare LSST-stack environment where the `stips` package may not be importable.

Both do the same three things:

1. Resolve `<INSTRUMENT_DIR>/profile.py`.
2. **Append** the instrument dir to `sys.path` (see below).
3. `importlib`-exec the file and return its module-level `profile` object.

The two implementations are kept in sync **by convention** — each carries a code comment
pointing at the other (`config.py:27`, `profile_loader.py:5`). The stack-side loader has unit
coverage in `test_profile_loader.py` (load-by-path, `sys.path` insertion, missing-file error);
there is no automated assertion that the two bodies are byte-identical, so edit them together.

### Why `sys.path.append`, not `insert(0)`

The instrument dir holds generically-named modules (`profile.py`, `fetch.py`, `camera/`).
Prepending them to `sys.path` would let `instruments/nickel/profile.py` **shadow** any
third-party `import profile` (galsim has one). Appending makes stdlib/installed packages win,
while a uniquely-named co-located hook module like `fetch` still resolves because nothing else
provides it. This is exactly why `instruments/nickel/profile.py:9` can do
`from fetch import fetch_data`. (See the comment at `profile_loader.py:28`.)

---

## 4. Synthesis: binding the profile onto generic classes

The LSST stack needs concrete `Instrument`, `MetadataTranslator`, and `RawFormatter`
*classes*. `obs_stips` ships these as **generic base classes** with an unbound `profile = None`.
The module `lsst.obs.stips.active` (`packages/obs_stips/python/lsst/obs/stips/active.py`) does
the binding at **import time**:

```python
# active.py (abbreviated)
_profile = load_profile_from_dir(os.environ["INSTRUMENT_DIR"])   # fail-loud if unset

class Translator(StipsTranslator):   profile = _profile
class Instrument(StipsInstrument):   profile = _profile; translatorClass = Translator
class RawFormatter(StipsRawFormatter):
    instrumentClass = Instrument
    translatorClass = Translator
    filterDefinitions = Instrument.filterDefinitions
```

```mermaid
flowchart TB
    env["env: INSTRUMENT_DIR"] --> active
    subgraph active["import lsst.obs.stips.active"]
        load["_profile = load_profile_from_dir(INSTRUMENT_DIR)"]
        T["class Translator(StipsTranslator)<br/>profile = _profile"]
        I["class Instrument(StipsInstrument)<br/>profile = _profile<br/>translatorClass = Translator"]
        R["class RawFormatter(StipsRawFormatter)<br/>instrumentClass = Instrument"]
        load --> T --> I --> R
    end

    subgraph generic["obs_stips generic bases (profile = None)"]
        ST["StipsTranslator<br/>translator.py"]
        SI["StipsInstrument<br/>instrument.py"]
        SR["StipsRawFormatter<br/>formatter.py"]
    end
    T -.subclasses.-> ST
    I -.subclasses.-> SI
    R -.subclasses.-> SR
```

Key design points:

- **`active` is not imported by `obs_stips/__init__`.** Importing the package stays
  side-effect-free, so plotting-only code paths work even with `INSTRUMENT_DIR` unset.
  Importing `active` *itself* requires the env var and fails loud otherwise (`active.py:22`).
- **The binding is by class attribute.** `StipsInstrument.__init_subclass__`
  (`instrument.py:37`) reads the bound `profile` at subclass-creation time and resolves
  `name`, `policyName`, `obsDataPackage`, and `filterDefinitions` — *without* instantiation, so
  Butler can read class-level metadata cheaply.

---

## 5. The Butler round trip: why `INSTRUMENT_DIR` must follow the subprocess

Here's the subtlety that ties it all together. When Butler registers an instrument it persists
the **fully-qualified class name**, which for *every* STIPS telescope is the same string:
`lsst.obs.stips.active.Instrument` (set via `profile.instrument_class`,
`instruments/nickel/profile.py:71`).

Later, Butler re-imports that FQN to re-instantiate the instrument. Re-importing `active`
re-runs `load_profile_from_dir(os.environ["INSTRUMENT_DIR"])` — so **the identity of the
instrument is carried by the env var + profile file, not by the persisted class name.**

```mermaid
sequenceDiagram
    participant CLI as stips CLI
    participant Stack as stack.py (subprocess builder)
    participant Sub as LSST subprocess (pipetask/butler)
    participant Active as lsst.obs.stips.active
    participant Butler

    CLI->>Stack: run_with_stack(config)
    Note over Stack: export INSTRUMENT_DIR=instruments/nickel
    Stack->>Sub: bash: source loader#59; setup#59; run command
    Sub->>Active: import (register-instrument)
    Active->>Active: load_profile_from_dir($INSTRUMENT_DIR)
    Active-->>Sub: concrete Instrument bound to Nickel profile
    Sub->>Butler: register class FQN "lsst.obs.stips.active.Instrument"
    Note over Butler: stores only the FQN string

    rect rgb(245,245,245)
    Note over Sub,Butler: later run — same or different process
    Butler->>Active: re-import FQN to re-instantiate
    Active->>Active: load_profile_from_dir($INSTRUMENT_DIR) AGAIN
    Active-->>Butler: identity re-resolved from env + profile.py
    end
```

Practical consequence: **every** LSST subprocess must have `INSTRUMENT_DIR` exported.
`stack.py:_build_setup_script()` (`packages/stips/src/stips/core/stack.py:37`) does this — see
§7.

---

## 6. How the generic classes consume the profile

### 6.1 `StipsInstrument` — registration & camera

`instrument.py:28`. Generic LSST `Instrument` subclass. Highlights:

- `__init_subclass__` (`:37`) pulls `name`, `policyName`, `obsDataPackage`, and builds
  `filterDefinitions` — one `FilterDefinition(physical_filter, band=band)` per `profile.filters`
  entry (`:49`).
- `getCamera()` (`:63`) branches on the `camera` field:

```mermaid
flowchart TB
    gc["getCamera()"] --> q{"profile.camera<br/>is a CameraSpec?"}
    q -->|yes| bc["build_camera(spec)<br/>synthesize afw Camera in-memory<br/>camera_builder.py:202"]
    q -->|no, it's a yaml path| bn{"CCD_BINNING &gt; 1?"}
    bn -->|no| yc["yamlCamera.makeCamera(file)<br/>(stock LSST loader)"]
    bn -->|yes| byc["build_yaml_camera(file, binning)<br/>on-chip binning transform<br/>camera_builder.py:136"]
```

- `register()` (`:88`) writes the single-CCD geometry with stable raft/slot labels `R00`/`S00`.

### 6.2 `StipsTranslator` — header translation by profile

`translator.py:9`. Subclasses astro_metadata_translator's `FitsTranslator`.

- `__init_subclass__` (`:14`) compiles `profile.header_map` into amt's `_trivial_map` and
  `profile.const_map` into `_const_map`.
- `can_translate()` (`:23`) decides whether this translator owns a file by substring-matching
  `profile.instrument_header_value or profile.name` against the FITS `INSTRUME`. (This is how
  the profile named `"CTIO1m"` claims files whose `INSTRUME` is `"Y4KCam"`.)
- Every `to_*` method follows the same **hook-first, default-fallback** pattern:

```mermaid
flowchart LR
    call["to_observation_type()"] --> h{"profile.hooks has<br/>'observation_type'?"}
    h -->|yes| hook["return hook(header)"]
    h -->|no| def["return generic default<br/>(e.g. 'science')"]
```

So the translator carries *no* instrument knowledge: declarative headers come from
`header_map`, and anything irregular is a profile hook. `_hook(name)` (`:33`) is just
`self.profile.hooks.get(name)`.

### 6.3 `StipsRawFormatter`

Generic raw formatter, bound to the synthesized `Instrument`/`Translator` in `active.py:45`.

---

## 7. Config & pipeline resolution: instrument-dir-first, framework fallback

A fork can override any single pipeline YAML or config `.py` by dropping a same-named file into
its own directory — without forking the shared files.

`Config.resolve_pipeline()` / `resolve_config()` (`config.py:141`–`157`):

```mermaid
flowchart LR
    req["resolve_config('dia/subtractImages.py')"] --> c1{"exists in<br/>INSTRUMENT_DIR/configs/ ?"}
    c1 -->|yes| use1["use instrument's file"]
    c1 -->|no| use2["use framework default<br/>obs_stips/instrument_defaults/configs/"]
```

The same instrument-dir-first logic applies to pipelines (`<dir>/pipelines/`) and the skymap
geometry config (`SKYMAP_CFG`).

---

## 8. End-to-end: from CLI command to a running pipeline

`stack.py:_build_setup_script()` (`:37`) assembles the bash prefix that activates the stack and
exports everything the subprocess (and Butler-inside-it) needs to re-resolve the profile:

```mermaid
sequenceDiagram
    participant U as user
    participant CLI as stips CLI
    participant Cfg as config.load()
    participant Stack as stack._build_setup_script
    participant Sh as bash subprocess

    U->>CLI: stips -c pipeline.yaml science 20230519
    CLI->>Cfg: load(config.yaml)
    Cfg->>Cfg: read env: block (REPO, STACK_DIR, INSTRUMENT_DIR, ...)
    Cfg->>Cfg: load_active_profile(INSTRUMENT_DIR)  ← profile object
    Cfg-->>CLI: Config(profile=...)
    CLI->>Stack: build setup script
    Note over Stack: export REPO / STACK_DIR / RAW_PARENT_DIR<br/>export INSTRUMENT_DIR  ← keystone<br/>export SKYMAP_* / CCD_BINNING (from profile)<br/>setup obs_stips, stips, obs_data_package
    Stack-->>Sh: source loadLSST#59; setup#59; #lt;pipetask ...#gt;
    Sh->>Sh: import lsst.obs.stips.active → re-resolve profile
    Sh-->>U: pipeline runs as the active instrument
```

What `stack.py` exports and why it matters (all in `_build_setup_script`):

| Export | Source | Purpose |
|--------|--------|---------|
| `INSTRUMENT_DIR` | `config.instrument_dir` (`:67`) | **Keystone** — lets `active` re-resolve the profile in-subprocess |
| `SKYMAP_NAME` / `SKYMAP_COLLECTION` | `profile.skymap_*` (`:84`) | Instrument-specific skymap identity |
| `SKYMAP_CFG` | `resolve_config("makeSkyMap.py")` (`:95`) | Instrument-dir-first skymap geometry |
| `CCD_BINNING` | config `env:` block (`:77`) | On-chip binning camera transform |
| `obs_data_package` setup | `profile.obs_data_package` (`:106`) | `setup -r` only the active instrument's calib data |

Note there is **no** per-instrument EUPS `setup` — the instrument is purely declarative. Only
`obs_stips`, `stips`, and the profile's data package are set up as products.

---

## 9. Putting it together — the complete map

```mermaid
flowchart TB
    yaml["pipeline.yaml<br/>env: INSTRUMENT_DIR=instruments/nickel"] --> load
    load["config.load()<br/>load_active_profile()"] --> prof["profile object"]
    prof --> cfg["Config(profile=...)"]
    cfg --> stack["stack._build_setup_script()<br/>exports INSTRUMENT_DIR + profile-derived env"]
    stack --> sub["LSST subprocess"]

    sub --> active["import lsst.obs.stips.active<br/>load_profile_from_dir(INSTRUMENT_DIR)"]
    active --> bind["bind profile onto<br/>StipsInstrument / StipsTranslator / StipsRawFormatter"]
    bind --> butler["Butler: register / re-instantiate<br/>FQN lsst.obs.stips.active.Instrument"]

    prof -. drives .-> filters["FilterDefinitions<br/>(profile.filters)"]
    prof -. drives .-> cam["Camera<br/>(profile.camera / CameraSpec)"]
    prof -. drives .-> trans["header translation<br/>(header_map + hooks)"]
    prof -. drives .-> coll["collection names<br/>(collection_prefix)"]

    classDef k fill:#fff3e0,stroke:#e65100;
    class active,bind k;
```

---

## 10. Forking checklist (the abstraction in practice)

To add a telescope you touch only `instruments/<name>/`:

1. **`profile.py`** — declare `name`, `site`, `filters`, `filter_aliases`, `header_map`,
   `camera`, `instrument_class="lsst.obs.stips.active.Instrument"`, skymap identity, and any
   `@hook(profile)` quirk functions.
2. **`camera/`** — a single-CCD LSST `camera/<name>.yaml`, *or* set `camera=CameraSpec(...)` in
   the profile to skip the yaml entirely.
3. **`fetch.py`** (optional) — a `fetch_data(night, config, *, overwrite)` hook for archive
   downloads; wired via `profile.fetch_data`.
4. **`configs/` / `pipelines/`** (optional) — only the files you need to override; everything
   else falls back to `obs_stips/instrument_defaults/`.

Then point `INSTRUMENT_DIR` at the new directory. No framework code changes, no new package,
no EUPS product. See `docs/forking-stips.md` for the step-by-step walkthrough.

---

## Source map

| Concern | File |
|---------|------|
| Profile dataclass + `hook` decorator | `packages/stips/src/stips/profile.py` |
| CLI-side by-path loader | `packages/stips/src/stips/core/config.py:19` |
| Stack-side by-path loader | `packages/obs_stips/python/lsst/obs/stips/profile_loader.py` |
| Import-time synthesis | `packages/obs_stips/python/lsst/obs/stips/active.py` |
| Generic instrument | `packages/obs_stips/python/lsst/obs/stips/instrument.py` |
| Generic translator | `packages/obs_stips/python/lsst/obs/stips/translator.py` |
| Camera synthesis + binning | `packages/obs_stips/python/lsst/obs/stips/camera_builder.py` |
| Subprocess env wiring | `packages/stips/src/stips/core/stack.py:37` |
| Config/pipeline resolution | `packages/stips/src/stips/core/config.py:141` |
| Stack-side loader tests | `packages/obs_stips/tests/test_profile_loader.py` |
| Reference profile | `instruments/nickel/profile.py` |
