#!/bin/bash
# Slurm service entrypoint for STIPS test cluster.
#
# Starts munge authentication, then runs the requested Slurm daemon.
# CMD determines which daemon: slurmctld, slurmd, or slurmdbd.

set -e

DAEMON="${1:-slurmctld}"

# =============================================================================
# Munge authentication
# =============================================================================

# If a shared munge key is mounted (from volume), use it
if [[ -f /shared-munge/munge.key ]]; then
    cp /shared-munge/munge.key /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
fi

# Export the munge key to the shared volume (so other containers can use it)
if [[ -d /shared-munge ]] && [[ ! -f /shared-munge/munge.key ]]; then
    cp /etc/munge/munge.key /shared-munge/munge.key
    chmod 644 /shared-munge/munge.key
fi

# Ensure runtime directories exist (tmpfs on /run may wipe them)
mkdir -p /var/run/munge /var/log/munge /var/run/dbus
chown munge:munge /var/run/munge /var/log/munge

# Start D-Bus system daemon (required by Slurm cgroup/v2 plugin)
if command -v dbus-daemon &>/dev/null; then
    dbus-daemon --system --fork --nopidfile 2>/dev/null && \
        echo "[SLURM] dbus-daemon started" || \
        echo "[SLURM] dbus-daemon failed (cgroup scope creation may fail)"
fi

echo "[SLURM] Starting munged..."
munged --force
echo "[SLURM] munged started"

# =============================================================================
# Wait for dependencies
# =============================================================================

if [[ "$DAEMON" == "slurmdbd" ]]; then
    echo "[SLURM] Waiting for MySQL..."
    for i in $(seq 1 60); do
        if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(('mysql', 3306))
s.close()
" 2>/dev/null; then
            echo "[SLURM] MySQL is ready"
            break
        fi
        echo "[SLURM] MySQL not ready (attempt $i/60)..."
        sleep 2
    done
fi

if [[ "$DAEMON" == "slurmctld" ]]; then
    echo "[SLURM] Waiting for slurmdbd..."
    for i in $(seq 1 60); do
        if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(('slurmdbd', 6819))
s.close()
" 2>/dev/null; then
            echo "[SLURM] slurmdbd is ready"
            break
        fi
        echo "[SLURM] slurmdbd not ready (attempt $i/60)..."
        sleep 2
    done
fi

if [[ "$DAEMON" == "slurmd" ]]; then
    echo "[SLURM] Waiting for slurmctld..."
    for i in $(seq 1 60); do
        if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(('slurmctld', 6817))
s.close()
" 2>/dev/null; then
            echo "[SLURM] slurmctld is ready"
            break
        fi
        echo "[SLURM] slurmctld not ready (attempt $i/60)..."
        sleep 2
    done
fi

# =============================================================================
# Start the daemon
# =============================================================================

echo "[SLURM] Starting $DAEMON in foreground..."

case "$DAEMON" in
    slurmctld)
        exec slurmctld -D -vv
        ;;
    slurmd)
        exec slurmd -D -vv
        ;;
    slurmdbd)
        exec slurmdbd -D -vv
        ;;
    *)
        echo "[SLURM] Unknown daemon: $DAEMON"
        echo "[SLURM] Valid options: slurmctld, slurmd, slurmdbd"
        exit 1
        ;;
esac
