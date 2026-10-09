# Set up a campaign

A campaign is one target observed over many nights. This page goes from a new
target to a lightcurve; {doc}`quickstart` shows the same flow on a worked
example.

## 1. Collect what you need

| | Example | Notes |
|---|---|---|
| Name | `2023ixf` | Selects frames by their `OBJECT` header; see below |
| RA, Dec | `210.910750`, `54.311694` | Decimal degrees at full precision; see below |
| Nights | `20230519`, `20230521`, … | Local date at the start of each night |
| Bands | `r`, `i` | The profile's band names |
| Template | `ps1` | See {doc}`templates` |

Each night, STIPS processes the frames of one `OBJECT` value: the one that
contains `object`, ignoring case; if several do, the exact match, or else
the first.
Frames logged under another spelling that night (`SN2023ixf` beside
`2023ixf`) are skipped, so check the headers of nights with inconsistent
names.

:::{admonition} Use full-precision coordinates
:class: warning
Convert the TNS position (`14:03:38.580 +54:18:42.10`) to decimal degrees
with six or more decimals (`210.910750, 54.311694`). Rounding to two
decimals moves the measurement by up to 17″, enough to miss a point source
on Nickel's 0.37″ pixels. The symptom is a lightcurve of consistently
negative flux: the host galaxy's background instead of the supernova.
:::

## 2. Write the config

Copy the closest example from
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config)
(`2023ixf/pipeline_ps1_template.yaml` for a northern supernova) and edit it:

```yaml
env: { ... }               # as in Installation

object: "my_target"
ra: 123.456789
dec: 45.678901
bands: ["r", "i"]

template:
  type: ps1
  size: 0.4

science:
  nights: [20240101, 20240105, 20240112]
```

{doc}`configuration` lists every key. For variable stars and transits, see
{doc}`time-series`.

## 3. Get the data

```bash
stips -c my_target.yaml download                  # every night in the config
stips -c my_target.yaml download --missing-only   # only nights not yet on disk
```

Each night needs biases, flats in every band you process, and the science
frames, under `RAW_PARENT_DIR/<night>/raw/`. Data from anywhere other than
the instrument's archive can be copied there by hand.

## 4. Run

```bash
stips -c my_target.yaml run --dry-run
stips -c my_target.yaml run
```

A failed night does not stop the others (`options.continue_on_error`, on by
default), and the summary at the end lists what failed. Exposures whose
headers place them far from the target are dropped automatically.

Each run reprocesses every listed night into new collections and rebuilds
coadd templates; survey templates and reference catalogs are reused.
`options.skip_calibs`, `skip_science`, and `skip_dia` skip a stage for every
night, which saves time when only a later stage needs redoing.

## 5. Check and iterate

- Inspect `REPO/lightcurves/lightcurve_<object>.csv` and its plot; see
  {doc}`outputs`.
- Exclude bad exposures by ID with `stips science <night> --bad <id>,<id>`.
- To add nights, append them to `science.nights` and run again.
- Remove results before redoing a step differently with `stips clean`; see
  {doc}`outputs`.
