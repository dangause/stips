"""Tests for stips.core.bootstrap.needs_bootstrap.

``needs_bootstrap`` decides whether ``stips bootstrap`` must (re-)run. It now
uses the structured ``butler_query.collection_exists`` adapter instead of
grepping ``butler query-collections`` CLI stdout; these tests pin its exact
decision semantics with that adapter mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _cfg(repo: Path) -> mock.Mock:
    cfg = mock.Mock()
    cfg.repo = repo
    return cfg


def test_needs_bootstrap_when_butler_yaml_missing(tmp_path):
    from stips.core import bootstrap

    # No butler.yaml at all -> bootstrap, without even querying collections.
    assert bootstrap.needs_bootstrap(_cfg(tmp_path)) is True


def test_no_bootstrap_when_repo_and_collections_present(tmp_path):
    from stips.core import bootstrap, butler_query

    (tmp_path / "butler.yaml").write_text("")
    with mock.patch.object(butler_query, "collection_exists", return_value=True):
        assert bootstrap.needs_bootstrap(_cfg(tmp_path)) is False


def test_needs_bootstrap_when_a_collection_missing(tmp_path):
    from stips.core import bootstrap, butler_query

    (tmp_path / "butler.yaml").write_text("")

    # skymaps present, refcats absent -> bootstrap.
    def exists(config, name):
        return name == "skymaps"

    with mock.patch.object(butler_query, "collection_exists", side_effect=exists):
        assert bootstrap.needs_bootstrap(_cfg(tmp_path)) is True


def test_needs_bootstrap_when_query_fails(tmp_path):
    from stips.core import bootstrap, butler_query

    (tmp_path / "butler.yaml").write_text("")

    # collection_exists() returns False on a failed in-stack query -> bootstrap.
    with mock.patch.object(butler_query, "collection_exists", return_value=False):
        assert bootstrap.needs_bootstrap(_cfg(tmp_path)) is True


def test_needs_bootstrap_when_adapter_raises(tmp_path):
    from stips.core import bootstrap, butler_query

    (tmp_path / "butler.yaml").write_text("")

    with mock.patch.object(
        butler_query, "collection_exists", side_effect=RuntimeError("boom")
    ):
        assert bootstrap.needs_bootstrap(_cfg(tmp_path)) is True
