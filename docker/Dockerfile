# Small Telescope Image Processing Suite Docker Image
# Based on official LSST Science Pipelines
#
# Build:
#   docker build -t stips:latest -f docker/Dockerfile .
#   docker build --build-arg LSST_TAG=v30_0_3 -t stips:v30 .
#
# Run:
#   docker run -v /path/to/repo:/data/repo \
#              -v /path/to/raw:/data/raw \
#              -v /path/to/refcats:/data/refcats \
#              stips:latest stips env

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
LABEL org.opencontainers.image.source="https://github.com/dangause/stips"
LABEL org.opencontainers.image.description="Small Telescope Image Processing Suite for LSST Science Pipelines"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"

USER root

# =============================================================================
# Install STIPS Packages
# =============================================================================

# Create STIPS directory structure
WORKDIR /opt/stips

# Copy package source code
COPY packages/stips/ packages/stips/
COPY packages/obs_stips/ packages/obs_stips/
COPY instruments/nickel/ instruments/nickel/

# Copy scripts and BPS configs
COPY scripts/ /opt/stips/scripts/
COPY bps/ /opt/stips/bps/

# Install Slurm client tools, munge, and utilities (for BPS job submission)
RUN dnf install -y epel-release && \
    dnf install -y slurm munge munge-libs which && \
    dnf clean all

# Copy Slurm config (must match cluster's slurm.conf)
COPY docker/slurm/slurm.conf /etc/slurm/slurm.conf

# Install packages into LSST conda environment
# Using a single RUN to keep layers minimal
# Dashboard deps (fastapi, uvicorn, etc.) installed separately since --no-deps
# skips them to avoid touching LSST-managed packages
RUN source /opt/lsst/software/stack/loadLSST.bash && \
    setup lsst_distrib && \
    cd /opt/stips && \
    pip install --no-deps -e packages/stips && \
    pip install --no-deps -e packages/obs_stips && \
    pip install fastapi "uvicorn[standard]" jinja2 sse-starlette && \
    chmod +x /opt/stips/scripts/pipeline/*.sh 2>/dev/null || true

# Copy entrypoint
COPY docker/entrypoint.sh /opt/stips/docker/entrypoint.sh
RUN chmod +x /opt/stips/docker/entrypoint.sh

# Create stips-exec helper for `docker exec` commands
# (docker exec doesn't inherit entrypoint environment)
RUN printf '#!/bin/bash\nsource /opt/lsst/software/stack/loadLSST.bash\nsetup lsst_distrib\nsetup -r /opt/stips/packages/obs_stips obs_stips 2>/dev/null || true\nif [ -d /opt/stips/instruments/nickel/obs_nickel_data ]; then\n  setup -r /opt/stips/instruments/nickel/obs_nickel_data obs_nickel_data 2>/dev/null || true\nfi\nexport REPO=/data/repo RAW_PARENT_DIR=/data/raw REFCAT_REPO=/data/refcats\nexport INSTRUMENT_DIR=/opt/stips/instruments/nickel\nexport STIPS_DEFAULTS=/opt/stips/packages/obs_stips/instrument_defaults\nexport STACK_DIR=/opt/lsst/software/stack\nexport KMP_AFFINITY=disabled\nexport NUMEXPR_MAX_THREADS=1\n# Copy munge key if available\nif [ -f /shared-munge/munge.key ] && [ ! -f /etc/munge/munge.key ]; then\n  cp /shared-munge/munge.key /etc/munge/munge.key\n  chown munge:munge /etc/munge/munge.key\n  chmod 400 /etc/munge/munge.key\nfi\n# Start munge if not running\nif ! pgrep -x munged >/dev/null 2>&1; then\n  runuser -u munge -- munged 2>/dev/null || true\nfi\nexec "$@"\n' > /usr/local/bin/stips-exec && \
    chmod +x /usr/local/bin/stips-exec

# Create data directories (will be mount points)
RUN mkdir -p /data/repo /data/raw /data/refcats /data/outputs /config /opt/stips/logs

# Expose dashboard port
EXPOSE 8080

# =============================================================================
# Environment Configuration
# =============================================================================
ENV STIPS_ROOT=/opt/stips
ENV INSTRUMENT_DIR=/opt/stips/instruments/nickel
ENV STIPS_DEFAULTS=/opt/stips/packages/obs_stips/instrument_defaults
ENV OBS_NICKEL_DATA=/opt/stips/instruments/nickel/obs_nickel_data
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
ENTRYPOINT ["/opt/stips/docker/entrypoint.sh"]
CMD ["stips", "--help"]
