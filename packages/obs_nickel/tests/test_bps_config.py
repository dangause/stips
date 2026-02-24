"""Tests for BPS configuration rendering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_tools/src"))

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
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.qgraph_file is None

    def test_qgraph_file_accepts_path(self):
        """BPSConfig.qgraph_file accepts a string path."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(
            pipeline="custom",
            night="20230519",
            qgraph_file="/path/to/graph.qg",
        )
        assert cfg.qgraph_file == "/path/to/graph.qg"

    def test_custom_pipeline_without_qgraph_is_valid(self):
        """pipeline='custom' is valid even without qgraph_file (render will handle it)."""
        from obs_nickel_data_tools.core.bps import BPSConfig

        cfg = BPSConfig(pipeline="custom", night="20230519")
        assert cfg.pipeline == "custom"


class TestRenderBpsConfigQgraph:
    def _make_mock_config(self, tmp_path):
        """Create a mock Config object pointing at the real bps/ templates."""
        from unittest.mock import MagicMock

        # find_bps_config() goes: config.obs_nickel.parent.parent / "bps" / "pipelines"
        mock_config = MagicMock()
        mock_config.obs_nickel = REPO_ROOT / "packages" / "obs_nickel"
        mock_config.repo = tmp_path / "repo"
        mock_config.stack_dir = Path("/fake/stack")
        mock_config.cp_pipe_dir = Path("/fake/cp_pipe")
        mock_config.raw_parent_dir = Path("/fake/raw")
        mock_config.refcat_repo = Path("/fake/refcats")
        return mock_config

    def test_render_custom_injects_qgraph_file(self, tmp_path):
        """render_bps_config with custom pipeline substitutes {qgraph_file}."""
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

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
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

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
        from obs_nickel_data_tools.core.bps import BPSConfig, render_bps_config

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
