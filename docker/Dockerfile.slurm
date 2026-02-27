# Slurm Services for NPS Docker Test Cluster
#
# Built from the same LSST base image as NPS so all containers share
# AlmaLinux 9 + Slurm 22.05 + LSST stack. Compute nodes can run pipetask.
#
# Build:
#   docker build -t nps-slurm:latest -f docker/Dockerfile.slurm .
#
# Run (via docker-compose.slurm.yml):
#   CMD determines which daemon runs: slurmctld, slurmd, or slurmdbd

ARG LSST_TAG=v30_0_3
FROM ghcr.io/lsst/scipipe:al9-${LSST_TAG}

LABEL org.opencontainers.image.description="NPS Slurm cluster node (AlmaLinux 9 + Slurm 22 + LSST)"

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
# NPS packages (so compute nodes can run pipetask)
# =============================================================================
WORKDIR /opt/nps

COPY packages/obs_nickel/ packages/obs_nickel/
COPY packages/obs_nickel_data/ packages/obs_nickel_data/

RUN source /opt/lsst/software/stack/loadLSST.bash && \
    setup lsst_distrib && \
    pip install --no-deps -e packages/obs_nickel && \
    chmod +x /opt/nps/packages/obs_nickel/pipelines/*.yaml 2>/dev/null || true

# Add LSST conda env to default PATH so Parsl's process_worker_pool.py
# is available when Slurm jobs start on compute nodes
ENV PATH=/opt/lsst/software/stack/conda/envs/lsst-scipipe-12.1.0/bin:$PATH

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
