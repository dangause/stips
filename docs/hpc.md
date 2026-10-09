# Running on a cluster

STIPS can send the expensive steps to a Slurm or HTCondor cluster through
Rubin's [Batch Processing
Service](https://pipelines.lsst.io/modules/lsst.ctrl.bps/index.html) (BPS).
Science processing, difference imaging, and forced photometry run as cluster
jobs. Calibrations and lightcurve extraction are small, so they stay on the
machine running `stips`, and every quantum graph is built there so STIPS can
check it before submitting.

## What the cluster needs

- A filesystem shared by the submit host and the compute nodes, holding the
  repository, raw data, reference catalogs, and the STIPS checkout.
- The Rubin stack on the compute nodes: either one installation on the shared
  filesystem, or the STIPS Apptainer image (see {ref}`install-container`).
- A site file in `bps/sites/` that matches your cluster. In `slurm.yaml`,
  edit the `#SBATCH` lines under `scheduler_options` (partition, account,
  mail), the node size and walltime, `max_blocks` (Slurm jobs at once), and
  the per-task memory at the end. The `worker_init` block that sets up the
  stack on each node is filled in by STIPS from your config.

## A whole campaign

Add an execution block to the config:

```yaml
options:
  execution: bps
  site: slurm                  # slurm, htcondor, singularity-slurm, or local
  container_image: /shared/stips.sif   # with singularity-slurm only
  concurrent_nights: 4         # nights submitted in parallel
```

or pass `--site` to override it for one run:

```bash
stips -c target.yaml run --site slurm
```

## One step at a time

```bash
stips -c target.yaml bps submit science 20230519 --site slurm --project <account>
stips -c target.yaml bps submit dia 20230519 --site slurm --band r
```

On Slurm (and the `local` site), BPS works through Parsl: `bps submit` waits
until the jobs finish and returns no run ID. On HTCondor it returns at once
with a run ID for `stips bps status` and `stips bps cancel`; `stips bps
list` shows recent runs. `--site local --dry-run` shows what would be
submitted without a cluster.

## More

- {doc}`architecture-bps-docker-slurm` explains how submission works and how
  to run the Docker-based test cluster.
- Rubin's [BPS documentation](https://pipelines.lsst.io/modules/lsst.ctrl.bps/index.html)
  covers the configuration options.
