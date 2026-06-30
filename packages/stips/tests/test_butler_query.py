"""Tests for stips.core.butler_query (structured Butler queries).

The in-stack snippets can't run without an installed LSST stack, so these tests
exercise the two deterministic halves: (1) the snippet builders produce valid,
correctly-parameterized Python, and (2) the public helpers map a mocked
``run_butler_python_json`` result to the right typed value.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _cfg(repo: str = "/repo") -> MagicMock:
    cfg = MagicMock()
    cfg.repo = repo
    return cfg


class TestScriptBuilders:
    def test_count_script_is_valid_python_and_parameterized(self):
        from stips.core.butler_query import _build_count_script

        s = _build_count_script(
            "/repo", "difference_image", ["Nickel/diff/run"], "day_obs=20230519", None
        )
        ast.parse(s)  # raises SyntaxError if the snippet is malformed
        # modern API + v27 registry fallback both present
        assert "query_datasets" in s
        assert "queryDatasets" in s
        assert "explain=False" in s
        # values embedded
        assert "/repo" in s
        assert "difference_image" in s
        assert "Nickel/diff/run" in s
        assert "day_obs=20230519" in s

    def test_count_script_escapes_awkward_values(self):
        from stips.core.butler_query import _build_count_script

        # repr() embedding must keep the script valid even with quotes inside
        s = _build_count_script("/r'epo", "dt", ["c'oll"], "name='x'", 1)
        ast.parse(s)
        assert "limit=1" in s

    def test_list_collections_script_valid(self):
        from stips.core.butler_query import _build_list_collections_script

        s = _build_list_collections_script("/repo", "templates/*")
        ast.parse(s)
        assert "collections.query" in s
        assert "queryCollections" in s  # fallback
        assert "templates/*" in s

    def test_qg_count_script_uses_len(self):
        from stips.core.butler_query import _build_qg_count_script

        s = _build_qg_count_script("/tmp/x.qgraph")
        ast.parse(s)
        assert "QuantumGraph.loadUri" in s
        assert "len(qg)" in s
        assert "/tmp/x.qgraph" in s


class TestCountAndExistence:
    def test_count_datasets_returns_int(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 7}
        ):
            assert butler_query.count_datasets(_cfg(), "dt", "coll") == 7

    def test_count_datasets_none_on_failure(self):
        from stips.core import butler_query

        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.count_datasets(_cfg(), "dt", "coll") is None

    def test_count_datasets_passes_where_and_repo(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 0}
        ) as m:
            butler_query.count_datasets(
                _cfg("/myrepo"),
                "difference_image",
                "Nickel/diff/run",
                where="day_obs=42",
            )
        script = m.call_args[0][0]
        assert "/myrepo" in script
        assert "day_obs=42" in script
        # count queries are uncapped
        assert "limit=None" in script

    def test_has_datasets_true_false(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 1}
        ):
            assert butler_query.has_datasets(_cfg(), "dt", "coll") is True
        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 0}
        ):
            assert butler_query.has_datasets(_cfg(), "dt", "coll") is False

    def test_has_datasets_uses_limit_1(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 1}
        ) as m:
            butler_query.has_datasets(_cfg(), "dt", "coll")
        assert "limit=1" in m.call_args[0][0]

    def test_has_datasets_false_on_failure(self):
        from stips.core import butler_query

        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.has_datasets(_cfg(), "dt", "coll") is False


class TestCollections:
    def test_list_collections_prefix_filter(self):
        from stips.core import butler_query

        ret = {"collections": ["templates/ps1/r", "Nickel/raw/x", "templates/deep/t1"]}
        with patch.object(butler_query, "run_butler_python_json", return_value=ret):
            out = butler_query.list_collections(_cfg(), "*", prefix="templates/")
        assert out == ["templates/ps1/r", "templates/deep/t1"]

    def test_list_collections_none_on_failure(self):
        from stips.core import butler_query

        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.list_collections(_cfg(), "*") is None

    def test_collection_exists(self):
        from stips.core import butler_query

        with patch.object(
            butler_query,
            "run_butler_python_json",
            return_value={"collections": ["x", "y"]},
        ):
            assert butler_query.collection_exists(_cfg(), "x") is True
        with patch.object(
            butler_query, "run_butler_python_json", return_value={"collections": []}
        ):
            assert butler_query.collection_exists(_cfg(), "x") is False

    def test_list_collection_types(self):
        from stips.core import butler_query

        ret = {"collections": {"a/run": "RUN", "a": "CHAINED"}}
        with patch.object(butler_query, "run_butler_python_json", return_value=ret):
            out = butler_query.list_collection_types(_cfg(), "a*")
        assert out == {"a/run": "RUN", "a": "CHAINED"}

    def test_list_collection_types_none_on_failure(self):
        from stips.core import butler_query

        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.list_collection_types(_cfg(), "a*") is None

    def test_collection_has_datasets(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"has_datasets": True}
        ):
            assert butler_query.collection_has_datasets(_cfg(), "x") is True
        with patch.object(
            butler_query, "run_butler_python_json", return_value={"has_datasets": False}
        ):
            assert butler_query.collection_has_datasets(_cfg(), "x") is False
        # failed query -> False (no exception)
        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.collection_has_datasets(_cfg(), "x") is False

    def test_script_builders_valid(self):
        import ast

        from stips.core import butler_query

        ast.parse(butler_query._build_collection_types_script("/repo", "a*"))
        s = butler_query._build_collection_has_datasets_script("/repo", "a/run")
        ast.parse(s)
        assert "query_info" in butler_query._build_collection_types_script(
            "/repo", "a*"
        )
        assert "include_summary=True" in s


class TestQuantumGraph:
    def test_is_empty_true_false_none(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 0}
        ):
            assert butler_query.quantum_graph_is_empty(_cfg(), "/x.qg") is True
        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 3}
        ):
            assert butler_query.quantum_graph_is_empty(_cfg(), "/x.qg") is False
        with patch.object(butler_query, "run_butler_python_json", return_value=None):
            assert butler_query.quantum_graph_is_empty(_cfg(), "/x.qg") is None

    def test_quanta_count(self):
        from stips.core import butler_query

        with patch.object(
            butler_query, "run_butler_python_json", return_value={"count": 12}
        ):
            assert butler_query.quantum_graph_quanta_count(_cfg(), "/x.qg") == 12
