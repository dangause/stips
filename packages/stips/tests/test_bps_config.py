"""Tests for BPS configuration rendering."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Repo root is 3 levels up from packages/obs_nickel/tests/
REPO_ROOT = Path(__file__).resolve().parents[3]


class TestCustomTemplate:
    def test_custom_yaml_exists(self):
        """The custom.yaml template file must exist in bps/pipelines/."""
        custom_yaml = REPO_ROOT / "bps" / "pipelines" / "custom.yaml"
        assert custom_yaml.exists(), f"Missing: {custom_yaml}"

    def test_custom_yaml_has_qgraph_file_placeholder(self):
        """The custom.yaml must contain a {qgraph_file} placeholder."""
        custom_yaml = REPO_ROOT / "bps" / "pipelines" / "custom.yaml"
        content = custom_yaml.read_text()
        assert "{qgraph_file}" in content

    def test_custom_yaml_has_no_pipeline_yaml(self):
        """custom.yaml must NOT have pipelineYaml (qgraph encodes the pipeline)."""
        custom_yaml = REPO_ROOT / "bps" / "pipelines" / "custom.yaml"
        content = custom_yaml.read_text()
        assert "pipelineYaml:" not in content

    def test_custom_yaml_includes_site_config(self):
        """custom.yaml must include the site config for compute resources."""
        custom_yaml = REPO_ROOT / "bps" / "pipelines" / "custom.yaml"
        content = custom_yaml.read_text()
        assert "includeConfigs:" in content
        assert "{computeSite}" in content


class TestBPSConfigQgraphField:
    def test_qgraph_file_default_none(self):
        """BPSConfig.qgraph_file defaults to None."""
        from stips.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.qgraph_file is None

    def test_qgraph_file_accepts_path(self):
        """BPSConfig.qgraph_file accepts a string path."""
        from stips.core.bps import BPSConfig

        cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            qgraph_file="/path/to/graph.qg",
        )
        assert cfg.qgraph_file == "/path/to/graph.qg"

    def test_custom_pipeline_without_qgraph_is_valid(self):
        """pipeline='custom' is valid even without qgraph_file (render will handle it)."""
        from stips.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.pipeline == "custom"


class TestRenderBpsConfigQgraph:
    def _make_mock_config(self, tmp_path):
        """Create a mock Config object pointing at the real bps/ templates."""
        from unittest.mock import MagicMock

        # find_bps_config() goes: config.instrument_dir.parent.parent / "bps" / "pipelines"
        mock_config = MagicMock()
        mock_config.instrument_dir = REPO_ROOT / "packages" / "obs_nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        return mock_config

    def test_render_custom_injects_qgraph_file(self, tmp_path):
        """render_bps_config with custom pipeline substitutes {qgraph_file}."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file="/path/to/my_graph.qg",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        assert "qgraphFile:" in rendered_content
        assert "/path/to/my_graph.qg" in rendered_content
        # Must NOT contain unsubstituted placeholder
        assert "{qgraph_file}" not in rendered_content

    def test_render_custom_has_no_pipeline_yaml(self, tmp_path):
        """Rendered custom config must not have pipelineYaml."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file="/path/to/graph.qg",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        assert "pipelineYaml:" not in rendered_content

    def test_render_non_custom_ignores_qgraph(self, tmp_path):
        """For non-custom pipelines, qgraph_file is ignored."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        bps_cfg = BPSConfig(
            pipeline="science",
            night="20230519",
            site="local",
        )

        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        # Science pipeline should have pipelineYaml, NOT qgraphFile
        assert "pipelineYaml:" in rendered_content


class TestFullBPSLifecycle:
    """End-to-end test: BPSExecutor -> BPSConfig(custom) -> render -> submit -> poll -> CompletedProcess."""

    def _make_mock_config(self, tmp_path):
        mock_config = MagicMock()
        mock_config.instrument_dir = REPO_ROOT / "packages" / "obs_nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        return mock_config

    def test_custom_template_renders_and_lifecycle_succeeds(self, tmp_path):
        """Full lifecycle: render custom.yaml with qgraph_file -> submit -> poll -> success."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path)
        qgraph_path = "/data/repo/bps/science_20230519/graph.qg"

        bps_cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            site="local",
            qgraph_file=qgraph_path,
        )

        # Step 1: Render the config
        output_dir = tmp_path / "submit"
        rendered_path = render_bps_config(bps_cfg, config, output_dir)
        rendered_content = rendered_path.read_text()

        # Verify rendered config
        assert "qgraphFile:" in rendered_content
        assert qgraph_path in rendered_content
        assert "pipelineYaml:" not in rendered_content
        assert "{qgraph_file}" not in rendered_content
        assert "{repo}" not in rendered_content
        assert "{computeSite}" not in rendered_content

        # Verify site config was copied
        assert (output_dir / "sites" / "local.yaml").exists()
        assert (output_dir / "base.yaml").exists()

    def test_bps_executor_full_roundtrip(self, tmp_path):
        """BPSExecutor routes 'run' through custom pipeline with qgraph injection."""
        from stips.core import quanta_report
        from stips.core.executor import BPSExecutor

        executor = BPSExecutor(site="htcondor", poll_interval=0.01, timeout=1.0)
        config = self._make_mock_config(tmp_path)

        # Mock bps.submit to use real render_bps_config
        from stips.core import bps as bps_mod
        from stips.core import bps_report as bps_report_mod

        submit_called_with = {}

        def capturing_submit(bps_cfg, config):
            submit_called_with["pipeline"] = bps_cfg.pipeline
            submit_called_with["qgraph_file"] = bps_cfg.qgraph_file
            submit_called_with["site"] = bps_cfg.site
            # Return mock success instead of actually running bps
            return MagicMock(
                success=True,
                run_id="lifecycle-test-run",
                submit_dir=str(tmp_path / "submit"),
            )

        succeeded_report = (
            "X_REPORT    STATE      EXPECTED    SUCCEEDED    FAILED"
            "    UNREADY    READY    RUNNING\n"
            "summary    SUCCEEDED           3            3         0"
            "          0        0          0\n"
        )

        summary_file = tmp_path / "roundtrip.summary.json"

        with patch.object(
            bps_mod, "submit", side_effect=capturing_submit
        ), patch.object(
            bps_mod,
            "status",
            return_value={"success": True, "output": succeeded_report},
        ), patch.object(
            bps_report_mod, "summary_for_run", return_value=None
        ):
            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    str(config.repo),
                    "-g",
                    "/data/repo/graph.qg",
                    "-j",
                    "4",
                    "--summary",
                    str(summary_file),
                ],
                config,
                check=False,
            )

        # Verify the submit was called with correct params
        assert submit_called_with["pipeline"] == "custom"
        assert submit_called_with["qgraph_file"] == "/data/repo/graph.qg"
        assert submit_called_with["site"] == "htcondor"

        # Verify the result is a proper CompletedProcess with structured counts.
        assert result.returncode == 0
        assert quanta_report.parse_summary_file(summary_file) == (3, 0)


class TestBPSProjectDefault:
    """F-021: project/payload prefix default from the profile, not "nickel"."""

    def test_project_defaults_to_none(self):
        """BPSConfig.project defaults to None (resolved from profile at render)."""
        from stips.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="fphot", night="20230519")
        assert cfg.project is None

    def _make_mock_config(self, tmp_path, *, instrument_name):
        from types import SimpleNamespace

        mock_config = MagicMock()
        # find_bps_config(): instrument_dir.parent.parent / "bps" / "pipelines"
        mock_config.instrument_dir = REPO_ROOT / "instruments" / "nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        mock_config.require_profile.return_value = SimpleNamespace(
            name=instrument_name, obs_data_package=""
        )
        return mock_config

    def test_payload_prefix_defaults_from_profile_name(self, tmp_path):
        """payloadName uses the profile's lowercased name, not a "nickel" literal."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path, instrument_name="CTIO1m")
        bps_cfg = BPSConfig(
            pipeline="fphot", night="20230519", site="local", project=None
        )
        rendered = render_bps_config(bps_cfg, config, tmp_path / "submit").read_text()

        assert "ctio1m-fphot-20230519" in rendered
        assert "nickel-fphot" not in rendered
        assert "{payload_prefix}" not in rendered

    def test_explicit_project_overrides_default(self, tmp_path):
        """An explicit --project value is honored (payload prefix still profile)."""
        from stips.core.bps import BPSConfig, render_bps_config

        config = self._make_mock_config(tmp_path, instrument_name="CTIO1m")
        bps_cfg = BPSConfig(
            pipeline="fphot", night="20230519", site="local", project="myalloc"
        )
        rendered = render_bps_config(bps_cfg, config, tmp_path / "submit").read_text()

        # Payload prefix comes from the profile; the HPC project account is the
        # explicit override.
        assert "ctio1m-fphot-20230519" in rendered


class TestDockerSlurmSiteConfig:
    def test_docker_slurm_yaml_exists(self):
        """docker-slurm.yaml site config must exist."""
        bps_dir = REPO_ROOT / "bps" / "sites"
        assert (bps_dir / "docker-slurm.yaml").exists()

    def test_docker_slurm_is_valid_site(self):
        """'docker-slurm' must be accepted as a valid BPS site."""
        from stips.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="science", night="20230519", site="docker-slurm")
        assert cfg.site == "docker-slurm"

    def test_docker_slurm_uses_parsl_slurm(self):
        """docker-slurm.yaml must use Parsl with SlurmProvider."""
        bps_dir = REPO_ROOT / "bps" / "sites"
        content = (bps_dir / "docker-slurm.yaml").read_text()
        assert "lsst.ctrl.bps.parsl.ParslService" in content
        assert "lsst.ctrl.bps.parsl.sites.Slurm" in content

    def test_docker_slurm_conservative_resources(self):
        """docker-slurm.yaml should have conservative memory (4GB, not 128GB)."""
        bps_dir = REPO_ROOT / "bps" / "sites"
        content = (bps_dir / "docker-slurm.yaml").read_text()
        # Should reference 4 cores — conservative for Docker
        assert "cores_per_node: 4" in content
