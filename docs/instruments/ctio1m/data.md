# Getting CTIO data

Y4KCam frames are public in the [NOIRLab Astro Data
Archive](https://astroarchive.noirlab.edu/). STIPS downloads them through the
archive's web API; no account is needed.

## Download

The download needs `funpack`, from [CFITSIO](https://heasarc.gsfc.nasa.gov/fitsio/),
to decompress the archive's `.fits.fz` files: `brew install cfitsio` on macOS,
or `sudo apt-get install libcfitsio-bin` on Debian and Ubuntu. Without it the
files stay compressed and cannot be ingested.

```bash
stips -c target.yaml download                   # every night in the config
stips -c target.yaml download 20070321          # one night
```

A night is the Chilean calendar date on which it starts, and STIPS fetches
every raw frame of that date into `RAW_PARENT_DIR/<night>/raw/`. Optional
`env:` keys narrow the query:

| Key | Default | Meaning |
|---|---|---|
| `NOIRLAB_PROPOSAL` | | Only this proposal, such as `2007A-0002`. Leave unset for older frames, which may carry none. |
| `NOIRLAB_OBSTYPES` | all | Comma list of observation types to fetch |
| `NOIRLAB_INSTRUMENT` | `y4kcam` | Archive instrument name |
| `NOIRLAB_API` | `https://astroarchive.noirlab.edu` | Archive address |

## Binned data

Y4KCam was used both unbinned and binned 2 × 2. Set `CCD_BINNING: 2` in the
`env:` block for binned raws. The camera geometry is fixed when a repository
is set up, so binned and unbinned data need separate repositories.

## Files and headers

Raw files are named `y<YYMMDD>.<NNNN>.fits`: the local night and a sequence
number that restarts each night. STIPS builds exposure IDs from those two
values rather than from the UT date, because a Chilean night spans two UT
dates and the UT date would give two nights' frames the same ID. Times come
from `MJD-OBS`, falling back to `DATE-OBS`.

**Pointing offsets.** The telescope's header coordinates can be off by a
fixed amount for a whole observing run. Measured offsets are corrected
automatically:

| Dates (UT) | Correction | Measured on |
|---|---|---|
| 27 Sep – 17 Dec 2006 | 257″ east, 320″ north | Blind astrometric solutions of four nights |
| 17 – 22 Jan 2010 | None needed (about 60″, within the matcher's range) | The SA98 run |

Data from other dates get no correction, and science processing warns when a
night falls outside every measured range. If astrometry fails on such a
night, measure its offset with a blind solve (for example with
[astrometry.net](https://nova.astrometry.net/)) and add a row to
`_BORESIGHT_OFFSET_TABLE` in the profile.
