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
