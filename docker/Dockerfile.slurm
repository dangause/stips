# Slurm Services for STIPS Docker Test Cluster
#
# Built from the same LSST base image as STIPS so all containers share
# AlmaLinux 9 + Slurm 22.05 + LSST stack. Compute nodes can run pipetask.
#
# Build:
#   docker build -t stips-slurm:latest -f docker/Dockerfile.slurm .
#
# Run (via docker-compose.slurm.yml):
#   CMD determines which daemon runs: slurmctld, slurmd, or slurmdbd

ARG LSST_TAG=v30_0_3
FROM ghcr.io/lsst/scipipe:al9-${LSST_TAG}

LABEL org.opencontainers.image.description="STIPS Slurm cluster node (AlmaLinux 9 + Slurm 22 + LSST)"

USER root

# =============================================================================
# Install Slurm + Munge + MySQL client
# =============================================================================
RUN dnf install -y epel-release && \
    dnf install -y \
        slurm \
        slurm-slurmctld \
        slurm-slurmd \
        slurm-slurmdbd \
        munge \
        munge-libs \
        mariadb-connector-c \
        dbus-daemon \
        systemd \
        which \
        procps-ng \
        && \
    dnf clean all

# =============================================================================
# Munge authentication key (shared across cluster via volume)
# =============================================================================
RUN dd if=/dev/urandom of=/etc/munge/munge.key bs=1024 count=1 && \
    chown munge:munge /etc/munge/munge.key && \
    chmod 400 /etc/munge/munge.key

# =============================================================================
# Slurm configuration
# =============================================================================
COPY docker/slurm/slurm.conf /etc/slurm/slurm.conf
COPY docker/slurm/slurmdbd.conf /etc/slurm/slurmdbd.conf
RUN chmod 600 /etc/slurm/slurmdbd.conf
COPY docker/slurm/cgroup.conf /etc/slurm/cgroup.conf

# Create slurm user (EPEL package doesn't always create it) and required directories
RUN id slurm 2>/dev/null || useradd -r -s /sbin/nologin slurm && \
    mkdir -p /var/spool/slurm /var/spool/slurmd /var/log/slurm /var/lib/slurmd /var/run && \
    chown -R slurm:slurm /var/spool/slurm /var/spool/slurmd /var/log/slurm /var/lib/slurmd

# =============================================================================
# STIPS packages (so compute nodes can run pipetask)
# =============================================================================
WORKDIR /opt/stips

COPY packages/obs_stips/ packages/obs_stips/
COPY instruments/nickel/ instruments/nickel/
COPY packages/obs_nickel_data/ packages/obs_nickel_data/

RUN source /opt/lsst/software/stack/loadLSST.bash && \
    setup lsst_distrib && \
    pip install --no-deps -e packages/obs_stips && \
    chmod +x /opt/stips/packages/obs_stips/instrument_defaults/pipelines/*.yaml 2>/dev/null || true

# Add the LSST conda env to the default PATH so Parsl's process_worker_pool.py
# is available when Slurm jobs start on compute nodes (Slurm launches job steps
# with non-login shells that never source loadLSST).
#
# The env is named lsst-scipipe-<rubin-env-version> (e.g. lsst-scipipe-12.1.0),
# and that version number changes on every stack bump — hardcoding it guarantees
# a silent break. Resolve the single matching env at build time and expose it
# through a version-independent `current` symlink instead. See F-025 /
# docs/stack-bump-runbook.md.
RUN set -eu; \
    matches="$(ls -d /opt/lsst/software/stack/conda/envs/lsst-scipipe-*/ 2>/dev/null || true)"; \
    n="$(printf '%s\n' "$matches" | grep -c . || true)"; \
    if [ "$n" -ne 1 ]; then \
        echo "ERROR: expected exactly one lsst-scipipe conda env, found $n:" >&2; \
        printf '%s\n' "$matches" >&2; \
        exit 1; \
    fi; \
    ln -sfn "${matches%/}" /opt/lsst/software/stack/conda/envs/current
ENV PATH=/opt/lsst/software/stack/conda/envs/current/bin:$PATH

# =============================================================================
# Systemd setup (for compute nodes — slurmd requires cgroup v2 scopes via systemd)
# =============================================================================

# Enable munge + slurmd for systemd boot (used when compute nodes start with /sbin/init)
RUN systemctl enable munge slurmd 2>/dev/null || \
    (ln -sf /usr/lib/systemd/system/munge.service /etc/systemd/system/multi-user.target.wants/munge.service && \
     ln -sf /usr/lib/systemd/system/slurmd.service /etc/systemd/system/multi-user.target.wants/slurmd.service)

# Disable unnecessary systemd services to speed up boot
RUN (systemctl mask systemd-remount-fs.service sys-kernel-config.mount \
     sys-kernel-debug.mount systemd-logind.service getty.target console-getty.service \
     systemd-udev-trigger.service systemd-udevd.service systemd-random-seed.service \
     systemd-machine-id-commit.service 2>/dev/null || true)

# =============================================================================
# Entrypoints
# =============================================================================
COPY docker/slurm-entrypoint.sh /usr/local/bin/slurm-entrypoint.sh
COPY docker/slurmd-init.sh /usr/local/bin/slurmd-init.sh
RUN chmod +x /usr/local/bin/slurm-entrypoint.sh /usr/local/bin/slurmd-init.sh

ENTRYPOINT ["/usr/local/bin/slurm-entrypoint.sh"]
CMD ["slurmctld"]
