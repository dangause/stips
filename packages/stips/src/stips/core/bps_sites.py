"""Parsl BPS site classes for Slurm clusters.

``lsst.ctrl.bps.parsl.sites.Slurm`` reads only ``nodes``, ``cores_per_node``,
``walltime``, ``mem_per_node``, ``qos``, ``singleton``, ``account`` and
``scheduler_options`` from the site config. Everything else a STIPS site file
used to set was dropped, and Parsl's own defaults applied: one Slurm job at a
time (``max_blocks=1``), whole nodes (``--exclusive``), and no ``worker_init``.

:class:`StipsSlurm` passes the scaling keys through. :class:`ApptainerSlurm`
also starts each Parsl worker inside an Apptainer image, for clusters whose
nodes have no LSST stack. Only the worker needs the image: every quantum the
worker runs inherits its environment.

The site file names one of them as ``class:``; ``bps/sites/slurm.yaml`` and
``bps/sites/singularity-slurm.yaml`` show the keys.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, TypeVar

from lsst.ctrl.bps.parsl.sites import Slurm
from parsl.executors.base import ParslExecutor
from parsl.jobs.error_handlers import windowed_error_handler

from stips.core.bps_apptainer import container_launch_cmd, worker_setup_script

__all__ = ("ApptainerSlurm", "StipsSlurm")

T = TypeVar("T")


def _get(config: Any, key: str, kind: type[T], default: T | None = None, *, raw: bool = False) -> T | None:
    """Look up ``key`` in a BPS config section.

    Like ``lsst.ctrl.bps.parsl.configuration.get_bps_config_value``, but an
    int is accepted where a float is wanted, and ``raw=True`` leaves ``$VAR``
    and ``{var}`` alone, so shell text reaches the worker as written rather
    than expanded in the controller's environment.
    """
    options: dict[str, Any] = {
        "expandEnvVars": not raw,
        "replaceVars": not raw,
        "required": False,
    }
    if default is not None:
        options["default"] = default
    found, value = config.search(key, options)
    if not found:
        return default
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, kind):
        raise RuntimeError(f"Site config {key}={value!r} is not of type {kind.__name__}")
    return value


class StipsSlurm(Slurm):
    """Slurm site that honours the scaling keys of a STIPS site file.

    Recognised in addition to the keys of
    ``lsst.ctrl.bps.parsl.sites.Slurm``:

    - ``partition`` (`str`): Slurm partition, or a comma-separated list of
      them; empty for the cluster default.
    - ``max_blocks``, ``min_blocks``, ``init_blocks`` (`int`) and
      ``parallelism`` (`float`): how many Slurm jobs Parsl may hold at once
      and how eagerly it starts them.
    - ``exclusive`` (`bool`): request whole nodes; default ``False``
      (Parsl's own default is ``True``).
    - ``mem_per_worker`` (`float`): GB per Parsl worker; with
      ``mem_per_node`` it sets how many quanta run at once in one Slurm job.
    - ``worker_init`` (`str`): shell run in each Slurm job (on the host)
      before the workers start.
    - ``max_failed_blocks`` (`int`): stop the workflow once this many Slurm
      jobs in a row have failed; default 3. Parsl's own rule stops only when
      every job it holds has failed, which never happens while a replacement
      is pending, so a worker that cannot start would be resubmitted for as
      long as the controller lives.
    """

    def make_executor(
        self,
        label: str,
        *,
        provider_options: dict[str, Any] | None = None,
        executor_options: dict[str, Any] | None = None,
        mem_per_worker: float | None = None,
        **kwargs: Any,
    ) -> ParslExecutor:
        site = self.site
        executor_options = dict(executor_options or {})
        max_failed = _get(site, "max_failed_blocks", int, 3)
        if max_failed < 1:
            raise RuntimeError(f"max_failed_blocks must be at least 1, got {max_failed}")
        executor_options.setdefault(
            "block_error_handler",
            functools.partial(windowed_error_handler, threshold=max_failed),
        )
        options = dict(provider_options or {})
        options.setdefault("exclusive", _get(site, "exclusive", bool, False))
        for key, kind in (
            ("max_blocks", int),
            ("min_blocks", int),
            ("init_blocks", int),
            ("parallelism", float),
        ):
            value = _get(site, key, kind)
            if value is not None:
                options.setdefault(key, value)
        worker_init = _get(site, "worker_init", str, "", raw=True)
        if worker_init:
            options.setdefault("worker_init", worker_init)
        if mem_per_worker is None:
            mem_per_worker = _get(site, "mem_per_worker", float)

        executor = super().make_executor(
            label,
            provider_options=options,
            executor_options=executor_options,
            mem_per_worker=mem_per_worker,
            **kwargs,
        )

        # The base class lets a ``scheduler_options`` key in the site file win
        # over an argument, so these lines go onto the provider afterwards.
        provider = executor.provider
        partition = _get(site, "partition", str, "")
        if partition:
            provider.scheduler_options = (
                f"#SBATCH --partition={partition}\n{provider.scheduler_options}"
            )
        # sbatch would otherwise start the block in the controller's working
        # directory, which for a controller inside an image may not exist on
        # the host (Slurm then falls back to /tmp).
        submit = _get(self.config, "submitPath", str, "")
        if submit:
            provider.scheduler_options = (
                f"#SBATCH --chdir={submit}\n{provider.scheduler_options}"
            )
        return executor


class ApptainerSlurm(StipsSlurm):
    """Slurm site whose Parsl workers run inside an Apptainer image.

    Recognised in addition to the keys of :class:`StipsSlurm`:

    - ``image`` (`str`): the image on the shared filesystem. Empty means the
      image the controller itself runs in (``APPTAINER_CONTAINER``).
    - ``bind`` (`str`): ``apptainer --bind`` list for the worker, in host
      paths. Empty means ``STIPS_APPTAINER_BIND`` from the environment, which
      ``scripts/hpc/stips-apptainer`` sets. The repository, raw data,
      reference catalogues and the BPS submit directory must all be visible
      inside the worker at the paths the controller uses.
    - ``worker_setup`` (`str`): shell run inside the image before the worker
      starts (stack setup, STIPS paths). Written into the submit directory as
      ``stips-worker.sh``.
    - ``apptainer`` (`str`): the command on the compute nodes; default
      ``apptainer``.
    """

    def make_executor(self, label: str, **kwargs: Any) -> ParslExecutor:
        executor = super().make_executor(label, **kwargs)
        site = self.site

        image = _get(site, "image", str, "") or os.environ.get("APPTAINER_CONTAINER", "")
        if not image:
            raise RuntimeError(
                "ApptainerSlurm needs an image: set options.container_image in "
                "the run config, or run the controller inside the image "
                "(scripts/hpc/stips-apptainer)."
            )
        bind = _get(site, "bind", str, "") or os.environ.get("STIPS_APPTAINER_BIND", "")
        apptainer = _get(site, "apptainer", str, "apptainer")
        setup = _get(site, "worker_setup", str, "", raw=True)

        submit = _get(self.config, "submitPath", str, "")
        if not submit:
            raise RuntimeError("BPS config has no submitPath")
        submit_path = Path(submit)
        submit_path.mkdir(parents=True, exist_ok=True)
        script = submit_path / "stips-worker.sh"
        script.write_text(worker_setup_script(setup))
        script.chmod(0o755)

        executor.launch_cmd = container_launch_cmd(
            executor.launch_cmd,
            image=image,
            bind=bind,
            script=str(script),
            apptainer=apptainer,
        )
        return executor
