# LSST-Based Slurm Cluster Design

**Date:** 2026-02-24
**Branch:** `feature/dpg/bps-full`
**Goal:** Replace the giovtorres/slurm-docker-cluster (CentOS 7, Slurm 19, amd64-only) with a custom Slurm cluster built from the same LSST base image as NPS (AlmaLinux 9, Slurm 22, ARM native).

## Problem

The existing Docker Slurm test environment uses `giovtorres/slurm-docker-cluster:latest`, a 2020-era image with:
- **Slurm 19.05** — incompatible wire protocol with Slurm 22.05 in the NPS container
- **CentOS 7 / amd64-only** — requires Rosetta emulation on Apple Silicon, no LSST stack
- **MySQL auth issues** — old MySQL client can't authenticate with MySQL 8.0's `caching_sha2_password`
- **No LSST on compute nodes** — workers can't execute `pipetask` commands

## Solution

Build all Slurm services from `ghcr.io/lsst/scipipe:al9-v30_0_3` (the same LSST base image). This gives:
- Matching Slurm 22.05 across all containers (from AlmaLinux 9 EPEL)
- ARM-native execution (no emulation)
- LSST stack pre-installed on compute nodes for real BPS job execution
- No third-party image dependency

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│   All containers: AlmaLinux 9 + Slurm 22.05 (EPEL)     │
├──────────┬──────────┬──────────┬────────┬───────────────┤
│  mysql   │ slurmdbd │ slurmctld│ c1, c2 │   nps-hpc     │
│(mysql:8) │  (slurm) │  (slurm) │(slurm) │ (nps:latest)  │
└──────────┴──────────┴──────────┴────────┴───────────────┘
```

## Components

### Dockerfile.slurm (new)

Single Dockerfile for all Slurm services (slurmctld, slurmd, slurmdbd). Based on LSST scipipe image:
- Installs `slurm`, `slurm-slurmctld`, `slurm-slurmd`, `slurm-slurmdbd`, `munge`, `mariadb-connector-c` from EPEL
- Generates munge key at build time
- Copies `slurm.conf` into image
- Entrypoint starts munged, then runs the daemon specified by CMD

### slurm.conf (updated)

Single config file compatible with Slurm 22.05, used by all containers:
- ClusterName=nps-test
- 2 compute nodes (c1, c2), 4 CPUs / 4GB each
- Partition "normal", max walltime 5 days
- auth/munge authentication
- MariaDB accounting via slurmdbd

### docker-compose.slurm.yml (updated)

- Slurm services use `nps-slurm:latest` (built from Dockerfile.slurm)
- MySQL upgraded to 8.0 with `mysql_native_password` default auth
- NPS shares the same slurm-etc volume (no separate client config needed)
- Munge key shared via munge-etc named volume

### What stays unchanged

- NPS container (Dockerfile, entrypoint.sh)
- BPS site configs (bps/sites/)
- Smoke test script (docker/scripts/run-bps-test.sh)
- Network topology and data volumes

## Implementation Tasks

1. Create `docker/Dockerfile.slurm` from LSST base with Slurm 22 services
2. Create `docker/slurm-entrypoint.sh` to start munged + requested daemon
3. Update `docker/slurm/slurm.conf` for Slurm 22 compatibility
4. Rewrite `docker/docker-compose.slurm.yml` to use new image
5. Revert NPS Dockerfile (remove slurm-client.conf and munge.key hacks)
6. Build and run smoke test
