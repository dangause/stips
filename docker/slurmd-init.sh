#!/bin/bash
# Compute node init script for STIPS Slurm cluster.
#
# Sets up munge key and waits for slurmctld, then hands off to systemd
# which manages munge + slurmd with proper cgroup v2 scope creation.

set -e

# =============================================================================
# Munge key setup (before systemd starts munge.service)
# =============================================================================

# Pick up shared munge key from cluster volume
if [[ -f /shared-munge/munge.key ]]; then
    cp /shared-munge/munge.key /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
fi

# =============================================================================
# Wait for slurmctld to be ready
# =============================================================================

echo "[SLURM-INIT] Waiting for slurmctld..."
for i in $(seq 1 120); do
    if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(('slurmctld', 6817))
s.close()
" 2>/dev/null; then
        echo "[SLURM-INIT] slurmctld is ready"
        break
    fi
    if (( i % 10 == 0 )); then
        echo "[SLURM-INIT] slurmctld not ready (attempt $i/120)..."
    fi
    sleep 2
done

# =============================================================================
# Hand off to systemd (PID 1)
# =============================================================================

echo "[SLURM-INIT] Starting systemd (munge + slurmd)..."
exec /usr/sbin/init
