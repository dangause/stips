# Install STIPS

There are two ways to run STIPS:

| | Container | Native |
|---|---|---|
| What you install | One image: the Rubin stack plus STIPS | The Rubin stack, then STIPS from source |
| Best for | Trying STIPS, clusters, Windows | Development, custom instruments, Linux or macOS workstations |
| Instruments included | All in the repository | All in the repository, plus your own |

Either way you also need reference catalogs and raw data; see
[](#what-else-you-need).

(install-container)=
## Container

Each STIPS release is published as a Docker image with the Rubin stack
(`v30_0_3`) and STIPS already set up:

```bash
docker pull ghcr.io/dangause/stips:2.2.4
```

Run commands by mounting your data at the image's standard paths:

```bash
docker run --rm \
  -v /path/to/repo:/data/repo \
  -v /path/to/raw:/data/raw \
  -v /path/to/refcats:/data/refcats \
  -v "$PWD":/config:ro \
  -v "$PWD/logs":/opt/stips/logs \
  ghcr.io/dangause/stips:2.2.4 \
  stips -c /config/target.yaml run
```

The config's `env:` block uses the paths inside the container:

```yaml
env:
  REPO: /data/repo
  STACK_DIR: /opt/lsst/software/stack
  INSTRUMENT_DIR: /opt/stips/instruments/nickel
  RAW_PARENT_DIR: /data/raw
  REFCAT_REPO: /data/refcats
```

On a cluster, use the [Apptainer](https://apptainer.org/docs/user/latest/)
build of the same image, with the same bind mounts:

```bash
apptainer pull stips.sif oras://ghcr.io/dangause/stips-sif:v2.2.4
apptainer run --bind /path/to/repo:/data/repo,/path/to/raw:/data/raw,/path/to/refcats:/data/refcats,$PWD:/config,$PWD/logs:/opt/stips/logs \
  stips.sif stips -c /config/target.yaml run
```

:::{note}
The image ships every instrument in the repository, with Nickel as the
default. For CTIO, set `INSTRUMENT_DIR: /opt/stips/instruments/ctio1m`; for
your own instrument, mount its directory and point `INSTRUMENT_DIR` at it.
:::

## Native install

### 1. Install the Rubin stack

Follow {doc}`install-rubin-stack` and note the directory that contains
`loadLSST.sh`; it becomes `STACK_DIR`.

### 2. Install STIPS

STIPS uses [uv](https://docs.astral.sh/uv/) to manage its own Python
environment, separate from the stack's.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # if you don't have uv
git clone https://github.com/dangause/stips.git
cd stips
uv sync
source .venv/bin/activate
stips --help
```

`uv sync` installs Python 3.12 if needed and creates `.venv/` with the `stips`
command and its tools. Instrument profiles are read from `instruments/` at run
time, so there is nothing per-instrument to install. [Git
LFS](https://git-lfs.com/) is needed only to run the test suite.

### 3. Write a config and check it

Start from an example, such as
`scripts/config/2023ixf/pipeline_ps1_template.yaml`, and set the `env:`
block:

```yaml
env:
  REPO: /data/stips/sn2023ixf_repo          # created on first run
  STACK_DIR: /home/you/lsst_stack           # contains loadLSST.sh
  INSTRUMENT_DIR: /home/you/stips/instruments/nickel
  RAW_PARENT_DIR: /data/raw                 # holds <YYYYMMDD>/raw/*.fits
  REFCAT_REPO: /data/refcats                # see Reference catalogs
```

Then check it:

```bash
stips -c target.yaml env
```

`stips env` prints the resolved paths and lists any that do not exist yet.
Before the first run that includes `REPO`, which the first run creates, and
possibly `RAW_PARENT_DIR`. It checks the stack only once every path exists.
{doc}`configuration` lists every key.

(what-else-you-need)=
## What else you need

**Reference catalogs**
: Astrometric and photometric calibration need reference stars. Setting up a
  repository currently requires MONSTER catalog shards for your fields under
  `REFCAT_REPO`. See {doc}`reference-catalogs`.

**Raw data**
: STIPS reads `RAW_PARENT_DIR/<night>/raw/*.fits`. `stips download` fetches
  nights from the instrument's archive: the Lick archive for Nickel, the
  NOIRLab archive for CTIO. For Nickel, set `LICK_ARCHIVE_DIR` to the client
  vendored in `instruments/nickel/vendor/lick_searchable_archive`.

Next: {doc}`quickstart`.
