# Running on a cluster

STIPS can send the expensive steps to a Slurm or HTCondor cluster through
Rubin's [Batch Processing
Service](https://pipelines.lsst.io/modules/lsst.ctrl.bps/index.html) (BPS).
Science processing, difference imaging and forced photometry run as cluster
jobs, from quantum graphs built on the machine running `stips` so STIPS can
check them before submitting. Calibrations and lightcurve extraction are
small, so they stay on that machine.

A visit's quanta run as two cluster jobs rather than one job each
(`clusterAlgorithm` in the site file), because starting `pipetask` costs about
10 s per job, longer than most per-visit tasks take. One job holds the tasks
that later steps need, the other the rest (analysis and plots), so that a
failing analysis quantum cannot hold back the tasks that combine visits: BPS
skips every job downstream of a failed one. Those combining tasks run as jobs
of their own.

On Slurm, BPS works through Parsl. The `stips` process (the *controller*)
submits Slurm jobs called *blocks*; each block starts a Parsl worker pool on one
node, and each worker runs one quantum at a time. `bps submit` waits until every
quantum has finished, so the controller stays up for the whole step.

## Pick a site

| Site | Compute nodes have | Controller runs |
|---|---|---|
| `singularity-slurm` | no LSST stack; the STIPS Apptainer image provides it | inside the image, via `scripts/hpc/stips-apptainer` |
| `slurm` | the Rubin stack on a shared filesystem | in that stack |
| `htcondor` | an HTCondor pool | anywhere `bps` can submit from |
| `local` | (one machine) | locally; for testing |

Every site needs a filesystem shared by the controller and the compute nodes,
holding the repository, raw data, reference catalogues and, for
`singularity-slurm`, the image.

## Size the blocks

The `options.cluster` block of the run config sets the Slurm request for the
`slurm` and `singularity-slurm` sites:

```yaml
options:
  execution: bps
  site: singularity-slurm
  container_image: /shared/images/stips.sif   # singularity-slurm only
  concurrent_nights: 2           # nights submitted in parallel
  cluster:
    partition: ""                # default: the cluster's default partition
    account: ""                  # default: your default Slurm account
    cores_per_node: 8            # per block
    mem_per_node: 32             # GB per block
    mem_per_worker: 4            # GB per quantum slot
    walltime: "04:00:00"         # per block; quote it
    max_blocks: 4                # blocks held at once
```

A block runs `min(cores_per_node, mem_per_node / mem_per_worker)` quanta at once,
so the example above runs up to 32 quanta on four nodes. `walltime` bounds a
block, not the step: when Slurm ends a block, the quanta it was running are
retried and Parsl starts another block while work remains.

A night parallelises over its visits, so workers beyond the number of visits
sit idle. Science processing of 2×2-binned Y4KCam frames peaks at about
1.3 GB per quantum, so `mem_per_worker: 2` suffices there; unbinned or larger
detectors need more.

Pick a partition with free memory, not just free cores. A partition whose
cores are idle can still have its memory allocated to other jobs, and blocks
then wait in the queue with reason `Priority`. `scontrol show node <node>`
shows a node's `AllocTRES` against its `RealMemory`, and `sbatch --test-only`
with a block's request (`--partition=... --cpus-per-task=12 --mem=24G
--time=4:00:00 --wrap true`) gives Slurm's estimated start and the partition
it would use. A comma-separated list of partitions is accepted; check with
`--test-only` which one Slurm picks, since it need not be the one that would
start the block soonest.

If 3 blocks in a row fail (a worker that cannot start, say), the step stops
with Parsl's error report rather than resubmitting for as long as the
controller lives. The `max_failed_blocks` key in the site file changes the
count.

An unknown key in `options.cluster` is an error, and so is an unquoted
walltime: YAML reads `4:00:00` as the integer 14400.

## Apptainer clusters (`singularity-slurm`)

The controller runs inside the image and needs the host's Slurm client, because
the image's client may be too old for the cluster's controller. Slurm rejects
clients more than two releases older than itself. `scripts/hpc/stips-apptainer`
binds the client in and starts a command inside the image:

```bash
export STIPS_SIF=/shared/images/stips.sif
# Everything the run config names, at the same path inside the image; a
# STIPS checkout over /opt/stips is optional.
export STIPS_BIND=/shared/stips/checkout:/opt/stips,/shared/stips:/shared/stips
/shared/stips/checkout/scripts/hpc/stips-apptainer stips -c /shared/stips/configs/target.yaml run
```

It binds the client commands (`sbatch`, `sacct`, `squeue`, `scancel`, ...),
their libraries and plugin directory, the Slurm config (a file, or the
configless cache under `/run/slurm`), the munge socket, and `passwd`/`group`
files with an entry for `SlurmUser`, which the client looks up while reading
the config.

Run it inside a small Slurm job rather than on the login node: it uses one or
two cores and a few GB, but lives as long as the workflow does.

```bash
sbatch --partition=<partition> --time=0-04:00:00 --mem=4G --cpus-per-task=2 \
  --wrap "/shared/stips/checkout/scripts/hpc/stips-apptainer stips -c /shared/stips/configs/target.yaml run"
```

The blocks run the Parsl worker pool inside the same image, with the same
`STIPS_BIND`. `stips.core.bps_sites.ApptainerSlurm` wraps Parsl's launch
command in `apptainer exec`, and a setup script (`stips-worker.sh` in the BPS
submit directory) sets up the stack first. Every quantum inherits that
environment.

## Native-stack clusters (`slurm`)

The compute nodes source the stack named by `STACK_DIR` in the config; the
`worker_init` block of `bps/sites/slurm.yaml` does it. Add any `#SBATCH`
lines your cluster needs (mail, constraints) under `scheduler_options` there;
partition, account and sizing come from `options.cluster`.

## One step at a time

```bash
stips -c target.yaml bps submit science 20230519 --site singularity-slurm
stips -c target.yaml bps submit dia 20230519 --site slurm --band r --project <account>
```

These read `options.container_image` and `options.cluster` from the same
config. On HTCondor `bps submit` returns at once with a run ID for `stips bps
status` and `stips bps cancel`; `stips bps list` shows recent runs. `--site
local --dry-run` shows what would be submitted without a cluster.

## More

- {doc}`architecture-bps-docker-slurm` explains how submission works and how
  to run the Docker-based test cluster.
- Rubin's [BPS documentation](https://pipelines.lsst.io/modules/lsst.ctrl.bps/index.html)
  covers the configuration options.
