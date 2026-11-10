"""Cluster sizing (options.cluster), the Slurm site files and the Apptainer launch text."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[3]


def _mock_config(tmp_path):
    config = MagicMock()
    config.instrument_dir = REPO_ROOT / "instruments" / "ctio1m"
    config.repo = tmp_path / "repo"
    config.stack_dir = Path("/opt/lsst/software/stack")
    config.cp_pipe_dir = None
    config.raw_parent_dir = Path("/shared/raw")
    config.refcat_repo = Path("/shared/refcats")
    return config


def _render_site(tmp_path, site, **fields):
    from stips.core.bps import BPSConfig, render_bps_config

    bps_cfg = BPSConfig(
        pipeline="custom", night="20110906", site=site, qgraph_file="/g.qg", **fields
    )
    render_bps_config(bps_cfg, _mock_config(tmp_path), tmp_path / "submit")
    text = (tmp_path / "submit" / "sites" / f"{site}.yaml").read_text()
    return text, yaml.safe_load(text)["site"][site]


class TestClusterOptions:
    def test_empty(self):
        from stips.core.bps import cluster_options

        assert cluster_options(None) == {}
        assert cluster_options({}) == {}

    def test_coerces_types(self):
        from stips.core.bps import cluster_options

        out = cluster_options(
            {"cores_per_node": "8", "mem_per_worker": 4, "partition": "short", "walltime": "01:00:00"}
        )
        assert out == {"cores_per_node": 8, "mem_per_worker": 4.0, "partition": "short", "walltime": "01:00:00"}

    def test_unknown_key_is_an_error(self):
        from stips.core.bps import cluster_options

        with pytest.raises(ValueError, match="mem_per_cpu"):
            cluster_options({"mem_per_cpu": 4})

    def test_unquoted_walltime_is_an_error(self):
        from stips.core.bps import cluster_options

        # YAML 1.1 reads an unquoted 4:00:00 as the base-60 integer 14400
        raw = yaml.safe_load("walltime: 4:00:00")
        assert raw["walltime"] == 14400
        with pytest.raises(ValueError, match="quoted"):
            cluster_options(raw)

    def test_every_key_is_a_bpsconfig_field(self):
        from dataclasses import fields

        from stips.core.bps import CLUSTER_KEYS, BPSConfig

        assert set(CLUSTER_KEYS) <= {f.name for f in fields(BPSConfig)}


class TestRunConfigCluster:
    def test_reaches_the_bps_executor(self, tmp_path):
        from stips.core.run import RunConfig, _create_executor

        cfg = tmp_path / "run.yaml"
        cfg.write_text(
            yaml.safe_dump(
                {
                    "target": {"name": "T", "ra": 1.0, "dec": -2.0},
                    "nights": ["20110906"],
                    "options": {
                        "execution": "bps",
                        "site": "singularity-slurm",
                        "cluster": {"partition": "short", "max_blocks": 3},
                    },
                }
            )
        )
        run_cfg = RunConfig.from_yaml(cfg)
        assert run_cfg.cluster == {"partition": "short", "max_blocks": 3}
        executor = _create_executor(run_cfg)
        assert executor.cluster == {"partition": "short", "max_blocks": 3}


class TestSlurmSiteFiles:
    @pytest.mark.parametrize("site", ["slurm", "singularity-slurm"])
    def test_cluster_values_rendered(self, tmp_path, site):
        text, section = _render_site(
            tmp_path,
            site,
            partition="short",
            cores_per_node=8,
            mem_per_node=32,
            mem_per_worker=4.0,
            walltime="01:00:00",
            max_blocks=3,
        )
        assert section["class"].startswith("stips.core.bps_sites.")
        assert section["partition"] == "short"
        assert section["cores_per_node"] == 8
        assert section["mem_per_node"] == 32
        assert section["mem_per_worker"] == 4.0
        assert section["walltime"] == "01:00:00"
        assert section["max_blocks"] == 3
        assert section["exclusive"] is False
        # No made-up account: empty unless the user names one
        assert section["account"] == ""
        assert "--account" not in text

    def test_project_becomes_the_account(self, tmp_path):
        _, section = _render_site(tmp_path, "slurm", project="astro123")
        assert section["account"] == "astro123"

    def test_singularity_worker_setup(self, tmp_path):
        text, section = _render_site(
            tmp_path, "singularity-slurm", container_image="/s/stips.sif", container_bind="/s:/s"
        )
        assert section["class"] == "stips.core.bps_sites.ApptainerSlurm"
        assert section["image"] == "/s/stips.sif"
        assert section["bind"] == "/s:/s"
        setup = section["worker_setup"]
        assert "setup lsst_distrib" in setup
        assert f'INSTRUMENT_DIR="{REPO_ROOT / "instruments" / "ctio1m"}"' in setup
        # Shell text the renderer must leave alone
        assert '"${pkg_dir%/}"' in setup
        # The old site shadowed pipetask with a nested apptainer call, which
        # cannot work once the worker itself runs in the image.
        assert "commandPrefix" not in text


class TestContainerLaunchCmd:
    def test_wraps_and_escapes(self):
        from stips.core.bps_apptainer import container_launch_cmd

        cmd = container_launch_cmd(
            "process_worker_pool.py {debug} -a {addresses}",
            image="/s/stips.sif",
            bind="/s/checkout:/opt/stips,/s:/s",
            script="/s/repo/bps/submit/x/stips-worker.sh",
        )
        assert cmd.startswith("unset $(compgen -e | grep -E '^(APPTAINER|SINGULARITY)_'); apptainer exec --cleanenv --bind /s/checkout:/opt/stips,/s:/s ")
        assert cmd.endswith("bash /s/repo/bps/submit/x/stips-worker.sh process_worker_pool.py {debug} -a {addresses}")
        # Parsl formats the whole command; its own placeholders still format
        # and the prefix survives.
        formatted = cmd.format(debug="-d", addresses="10.0.0.1")
        assert "process_worker_pool.py -d -a 10.0.0.1" in formatted
        assert '--env "PARSL_CORES=$PARSL_CORES,PARSL_MEMORY_GB=$PARSL_MEMORY_GB"' in formatted

    def test_braces_in_prefix_survive_format(self):
        from stips.core.bps_apptainer import container_launch_cmd

        cmd = container_launch_cmd("w {x}", image="/a/{odd}.sif", bind="", script="/s.sh")
        assert "--bind" not in cmd
        assert cmd.format(x=1).endswith("'/a/{odd}.sif' bash /s.sh w 1")

    def test_worker_setup_script(self):
        from stips.core.bps_apptainer import worker_setup_script

        script = worker_setup_script("source /x\nsetup lsst_distrib\n")
        assert script.startswith("#!/bin/bash\n")
        assert "export SHELL=/bin/bash\n" in script
        assert script.endswith('setup lsst_distrib\nexec "$@"\n')


class TestSitesNeedTheStack:
    """bps_sites imports ctrl_bps_parsl; exercise it where the stack exists."""

    def test_apptainer_slurm_executor(self, tmp_path):
        pytest.importorskip("lsst.ctrl.bps.parsl")
        from lsst.ctrl.bps import BpsConfig

        from stips.core.bps_sites import ApptainerSlurm

        submit = tmp_path / "submit"
        config = BpsConfig(
            {
                "computeSite": "s",
                "submitPath": str(submit),
                "operator": "me",
                "project": "p",
                "campaign": "c",
                "site": {
                    "s": {
                        "nodes": 1,
                        "cores_per_node": 8,
                        "mem_per_node": 32,
                        "mem_per_worker": 4,
                        "walltime": "01:00:00",
                        "partition": "short",
                        "max_blocks": 3,
                        "exclusive": False,
                        "image": "/s/stips.sif",
                        "bind": "/s:/s",
                        "worker_setup": 'export A="${B:-}"\n',
                    }
                },
            }
        )
        executor = ApptainerSlurm(config).get_executors()[0]
        provider = executor.provider
        assert provider.max_blocks == 3
        assert provider.exclusive is False
        assert provider.scheduler_options.startswith(
            f"#SBATCH --chdir={submit}\n#SBATCH --partition=short\n"
        )
        assert executor.mem_per_worker == 4.0
        assert "apptainer exec --cleanenv --bind /s:/s " in executor.launch_cmd
        assert executor.block_error_handler.keywords == {"threshold": 3}
        script = (submit / "stips-worker.sh").read_text()
        assert 'export A="${B:-}"' in script
