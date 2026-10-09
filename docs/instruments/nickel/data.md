# Getting Nickel data

Nickel frames are archived by Lick Observatory at
[archive.ucolick.org](https://archive.ucolick.org/archive/). STIPS queries
the archive anonymously, so it downloads the frames that are public.

## Download

Add the archive client to the config's `env:` block and download nights:

```yaml
env:
  LICK_ARCHIVE_DIR: /path/to/stips/instruments/nickel/vendor/lick_searchable_archive
```

```bash
uv pip install tenacity                       # needed by the archive client
stips -c target.yaml download                 # every night in the config
stips -c target.yaml download 20230519        # one night
stips -c target.yaml download --missing-only  # nights not yet on disk
```

A night is the local (Pacific) date on which it starts. STIPS fetches every
frame taken that night, including biases, flats, and other observers'
targets, into `RAW_PARENT_DIR/<night>/raw/`. Two optional keys change the
source: `LICK_ARCHIVE_URL` (default `https://archive.ucolick.org/archive`) and
`LICK_ARCHIVE_INSTR` (default `NICKEL_DIR`).

## Files and frame types

Raw files are named `d<OBSNUM>.fits`, where `OBSNUM` is an observatory-wide
counter (night 20230519 ran from `d228001.fits` to `d228176.fits`).
STIPS classifies each frame from `OBSTYPE` and `OBJECT`:

| Frame | Recognized by |
|---|---|
| Flat | `OBSTYPE` is `flat`, or `OBJECT` contains "flat" |
| Bias | `OBJECT` contains "bias" |
| Focus, pointing, test | `OBJECT` contains "focus", "point", "test", or "post"; skipped |
| Science | Everything else |

Before ingesting a night, `stips calibs` screens the raw directory. It leaves
out frames smaller than the night's usual 1056 × 1024 (Nickel nights contain
small test readouts) and files that are truncated or unreadable, and it
reports what it skipped.

## Header problems STIPS handles

**Object names vary.** Observers enter the same target differently on
different nights (`2023ixf`, `SN2023ixf`). Each night STIPS processes one
`OBJECT` value; see {doc}`../../new-campaign`.

**The pointing can be wrong.** The telescope's `DEC` keyword sometimes stays
at the previous pointing. STIPS compares the WCS position (`CRVAL1/2`) with
`RA`/`DEC` and uses the latter when they disagree by more than 1°. When both
are wrong, `stips run` drops exposures more than 5° from the target before
processing. A standalone `stips science` does the same when given `--ra` and
`--dec`.

**r′ and i′ look like r and i.** Headers from 2020 to 2023 record the
Sloan-like filters in a malformed card that the stack reads as `r` and `i`.
STIPS maps those values to the `rp` and `ip` bands, not to Cousins R and I,
because the two filter sets need different colour terms.

**Exposure IDs.** STIPS builds each exposure's 31-bit ID from its date and
`OBSNUM` modulo 10,000. The full `OBSNUM` stays in the observation ID (for
example `20230520_228001`), and `stips calibs` stops a night before ingest if
two of its frames would get the same ID.
