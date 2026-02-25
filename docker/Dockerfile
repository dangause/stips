# Nickel Processing Suite Docker Image
# Based on official LSST Science Pipelines
#
# Build:
#   docker build -t nps:latest -f docker/Dockerfile .
#   docker build --build-arg LSST_TAG=v30_0_3 -t nps:v30 .
#
# Run:
#   docker run -v /path/to/repo:/data/repo \
#              -v /path/to/raw:/data/raw \
#              -v /path/to/refcats:/data/refcats \
#              nps:latest nickel env

# =============================================================================
# Base Image: LSST Science Pipelines
# =============================================================================
# Using the official LSST Science Pipelines image from GitHub Container Registry
# See: https://github.com/orgs/lsst/packages/container/package/scipipe
#
# Available images:
#   - ghcr.io/lsst/scipipe:al9-v30_0_3    (AlmaLinux 9, latest stable)
#   - ghcr.io/lsst/scipipe:al9-w_2025_19  (AlmaLinux 9, weekly build)
#
ARG LSST_TAG=v30_0_3
FROM ghcr.io/lsst/scipipe:al9-${LSST_TAG}

# Set labels
LABEL org.opencontainers.image.source="https://github.com/lick-observatory/nickel_processing_suite"
LABEL org.opencontainers.image.description="Nickel Processing Suite for LSST Science Pipelines"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"

USER root

# =============================================================================
# Install NPS Packages
# =============================================================================

# Create NPS directory structure
WORKDIR /opt/nps

# Copy package source code
COPY packages/data_tools/ packages/data_tools/
COPY packages/obs_nickel/ packages/obs_nickel/
COPY packages/obs_nickel_data/ packages/obs_nickel_data/

# Copy scripts and BPS configs
COPY scripts/ /opt/nps/scripts/
COPY bps/ /opt/nps/bps/

# Install Slurm client tools, munge, and utilities (for BPS job submission)
RUN dnf install -y epel-release && \
    dnf install -y slurm munge munge-libs which && \
    dnf clean all

# Copy Slurm config (must match cluster's slurm.conf)
COPY docker/slurm/slurm.conf /etc/slurm/slurm.conf

# Install packages into LSST conda environment
# Using a single RUN to keep layers minimal
RUN source /opt/lsst/software/stack/loadLSST.bash && \
    setup lsst_distrib && \
    cd /opt/nps && \
    pip install --no-deps -e packages/data_tools && \
    pip install --no-deps -e packages/obs_nickel && \
    chmod +x /opt/nps/scripts/pipeline/*.sh 2>/dev/null || true

# Copy entrypoint
COPY docker/entrypoint.sh /opt/nps/docker/entrypoint.sh
RUN chmod +x /opt/nps/docker/entrypoint.sh

# Create data directories (will be mount points)
RUN mkdir -p /data/repo /data/raw /data/refcats /data/outputs /config

# =============================================================================
# Environment Configuration
# =============================================================================
ENV NPS_ROOT=/opt/nps
ENV OBS_NICKEL=/opt/nps/packages/obs_nickel
ENV OBS_NICKEL_DATA=/opt/nps/packages/obs_nickel_data
ENV STACK_DIR=/opt/lsst/software/stack

# Default data paths (override with -e or docker-compose)
ENV REPO=/data/repo
ENV RAW_PARENT_DIR=/data/raw
ENV REFCAT_REPO=/data/refcats

# Working directory
WORKDIR /data

# Healthcheck
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD source /opt/lsst/software/stack/loadLSST.bash && \
        setup lsst_distrib && \
        python -c "import lsst.daf.butler; print('ok')" || exit 1

# Entry point
ENTRYPOINT ["/opt/nps/docker/entrypoint.sh"]
CMD ["nickel", "--help"]
