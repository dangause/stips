# Install the Rubin Science Pipelines

STIPS does its image processing with the Rubin Observatory's [LSST Science
Pipelines](https://pipelines.lsst.io/), usually called *the Rubin stack*. STIPS
does not bundle the stack, except in the {ref}`STIPS container
<install-container>`, so a native installation needs both.

:::{admonition} Which version
:class: important
STIPS is validated on release **`v30_0_3`**, and that is the release to
install. The Rubin documentation describes its newest release; substitute
`v30_0_3` wherever it shows a version tag. STIPS's CI also runs against the
weekly `w_2025_32`, and a scheduled job tracks the latest weekly. To move to a
different release, follow the {doc}`stack-bump-runbook`.
:::

## Before you start

- **Platform.** Rubin develops on AlmaLinux 9. The stack also runs on other
  Linux distributions and on macOS. On Windows, use the
  {ref}`container <install-container>`.
- **System packages.** On Debian or Ubuntu, `sudo apt-get install curl patch`;
  on AlmaLinux, `sudo dnf install patch`; on macOS, `xcode-select --install`.
  See Rubin's [prerequisites](https://pipelines.lsst.io/install/prereqs.html).
- **File locking.** The filesystem holding the stack and your Butler
  repositories must support `flock`. Local disks do; some network filesystems
  are mounted without it.

## Install with `lsstinstall`

This follows Rubin's [lsstinstall
instructions](https://pipelines.lsst.io/install/lsstinstall.html) with STIPS's
release tag:

```bash
mkdir -p ~/lsst_stack && cd ~/lsst_stack
curl -OL https://ls.st/lsstinstall
chmod u+x lsstinstall
./lsstinstall -T v30_0_3               # conda environment for this release
source loadLSST.sh                      # or loadLSST.bash / loadLSST.zsh
eups distrib install -t v30_0_3 lsst_distrib
setup lsst_distrib
```

- `lsstinstall` creates a self-contained conda environment in the directory;
  it does not touch your other Python installations.
- Install **`lsst_distrib`**, not the smaller `lsst_apps`: STIPS needs the
  calibration-product (`cp_pipe`) and batch-processing (`ctrl_bps`) packages
  it includes.
- With prebuilt binaries the install takes about ten minutes. Platforms without
  them fall back to a source build that can take a couple of hours.
- For one installation shared by several users, see Rubin's notes on [shared
  installations](https://pipelines.lsst.io/install/lsstinstall.html#setting-unix-permissions-for-shared-installations).

To keep several releases side by side, install each into its own directory
(for example `~/lsst_stacks/v30_0_3`) and point each config's `STACK_DIR` at
the one it should use.

## Check the installation

In a new shell:

```bash
source ~/lsst_stack/loadLSST.sh
setup lsst_distrib
eups list -s lsst_distrib             # each prints the installed version
eups list -s cp_pipe
butler --help
pipetask --help
```

Rubin's [demo](https://pipelines.lsst.io/install/demo.html) is a fuller test
but is not needed for STIPS.

## Point STIPS at the stack

Set `STACK_DIR` in your config's `env:` block to the directory that contains
`loadLSST.sh`:

```yaml
env:
  STACK_DIR: /home/you/lsst_stack
```

You do not need to activate the stack yourself. Each time STIPS runs a stack
command it sources `loadLSST`, runs `setup lsst_distrib`, and sets up
`obs_stips` from your STIPS checkout. Next, {doc}`installation`.

## Containers and clusters

- **Containers.** Rubin publishes the stack as Docker images,
  [`ghcr.io/lsst/scipipe`](https://ghcr.io/lsst/scipipe); the tag for STIPS's
  release is `al9-v30_0_3`. The STIPS image is built on it and adds STIPS
  itself, so with the STIPS image you need nothing from this page. See
  {ref}`install-container`.
- **Clusters.** Install the stack once on a filesystem every node can see, or
  run the STIPS Apptainer image. See {doc}`hpc`.

## Getting help

- Rubin's [installation documentation](https://pipelines.lsst.io/install/index.html)
  and [release notes](https://pipelines.lsst.io/releases/index.html).
- The [Rubin Community Forum](https://community.lsst.org/), for installation
  problems.
- {doc}`troubleshooting`, for problems connecting STIPS to the stack.
