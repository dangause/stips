"""Command text for running Parsl workers inside an Apptainer image.

Kept apart from :mod:`stips.core.bps_sites` (which imports the LSST stack) so
the text can be tested in a plain virtualenv.
"""

from __future__ import annotations

import shlex

__all__ = ("container_launch_cmd", "worker_setup_script")

#: Slurm job variables Parsl's worker pool sizes itself from. ``--cleanenv``
#: would hide them, and the pool would then count every core and all the free
#: memory of the node rather than what the Slurm job was given.
PASSED_ENV = ("PARSL_CORES", "PARSL_MEMORY_GB")


def container_launch_cmd(
    launch_cmd: str,
    *,
    image: str,
    bind: str,
    script: str,
    apptainer: str = "apptainer",
) -> str:
    """Wrap a Parsl ``HighThroughputExecutor.launch_cmd`` in ``apptainer exec``.

    The result runs on the compute node inside the Slurm job: ``apptainer``
    starts the image, ``script`` sets up the stack, and the worker pool runs
    with the arguments Parsl fills into ``launch_cmd``.

    Args:
        launch_cmd: The executor's launch command, still holding the
            ``{placeholders}`` Parsl formats in later.
        image: Image path on the shared filesystem.
        bind: ``--bind`` list (host paths, comma-separated); empty for none.
        script: The worker setup script (see :func:`worker_setup_script`).
        apptainer: Command that starts the image on the compute nodes.

    Returns:
        The new launch command. Braces in the prefix are doubled, because
        Parsl calls ``str.format`` on the whole command.
    """
    # The Slurm job inherits the controller's environment (sbatch exports it),
    # and a controller inside an image carries APPTAINER_BIND and the like,
    # which the host's apptainer would act on. Drop them first.
    scrub = "unset $(compgen -e | grep -E '^(APPTAINER|SINGULARITY)_');"
    parts = [scrub, shlex.quote(apptainer), "exec", "--cleanenv"]
    if bind:
        parts += ["--bind", shlex.quote(bind)]
    env = ",".join(f"{name}=${name}" for name in PASSED_ENV)
    parts += ["--env", f'"{env}"', shlex.quote(image), "bash", shlex.quote(script)]
    prefix = " ".join(parts).replace("{", "{{").replace("}", "}}")
    return f"{prefix} {launch_cmd}"


def worker_setup_script(setup: str) -> str:
    """Return the script that sets up the stack, then execs its arguments.

    Args:
        setup: Shell lines run inside the image before the worker starts.
    """
    body = setup.strip("\n")
    return (
        "#!/bin/bash\n"
        "# Written by stips.core.bps_sites.ApptainerSlurm. Runs inside the image\n"
        "# on each compute node, then starts the Parsl worker pool.\n"
        "# loadLSST.bash asks conda for a hook for $SHELL, which a worker\n"
        "# started from a controller inside an image may not have.\n"
        "export SHELL=/bin/bash\n"
        f"{body}\n"
        'exec "$@"\n'
    )
