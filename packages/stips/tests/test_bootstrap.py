"""Tests for stips.core.bootstrap — the Python port of the bootstrap script.

Covers ``needs_bootstrap`` (with the ``butler_query.collection_exists`` adapter
mocked), the MONSTER shard ECSV map build/repair, and ``run()``'s step order,
idempotency, ``refcats`` chain extension (never redefinition) and error
surfacing. All stack-free: ``run_butler`` and the ``butler_query`` helpers are
replaced by a recording fake.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _cfg(repo: Path) -> mock.Mock:
    cfg = mock.Mock()
    cfg.repo = repo
    cfg.profile = None  # no active profile: only skymaps + refcats are checked
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


def test_needs_bootstrap_when_profile_skymap_chain_missing(tmp_path):
    from stips.core import bootstrap, butler_query

    (tmp_path / "butler.yaml").write_text("")
    cfg = _cfg(tmp_path)
    cfg.profile = SimpleNamespace(skymap_collection="skymaps/nickelRings")
    seen = []

    # skymaps + refcats present, the profile's skymap chain absent -> bootstrap.
    def exists(config, name):
        seen.append(name)
        return name in ("skymaps", "refcats")

    with mock.patch.object(butler_query, "collection_exists", side_effect=exists):
        assert bootstrap.needs_bootstrap(cfg) is True
    assert "skymaps/nickelRings" in seen

    with mock.patch.object(butler_query, "collection_exists", return_value=True):
        assert bootstrap.needs_bootstrap(cfg) is False


# --- run() ------------------------------------------------------------------


def _full_cfg(tmp_path, *, refcat_repo=None):
    prof = SimpleNamespace(
        name="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
    )
    return SimpleNamespace(
        repo=tmp_path / "repo",
        refcat_repo=refcat_repo,
        instrument_dir=tmp_path / "instruments" / "nickel",
        instrument_class="instruments.nickel.instrument.Instrument",
        require_profile=lambda: prof,
        resolve_config=lambda name: tmp_path / "configs" / name,
    )


def _shards(tmp_path, n=3):
    d = tmp_path / "refcats" / "data" / "refcats" / "the_monster_20250219_afw"
    d.mkdir(parents=True)
    for i in (131072, 131073, 131074)[:n]:
        (d / f"refcat_htm7_{i}.fits").write_bytes(b"x")
    return tmp_path / "refcats", d


class _Butler:
    """Records run_butler argv and answers queries from a mutable state dict."""

    def __init__(self, state):
        self.calls = []
        # {"collections": set(), "chains": {name: [members]},
        #  "datasets": set of (RUN, skymap name) holding a skyMap (default empty)}
        self.state = state
        self.dataset_queries = []
        state.setdefault("datasets", set())

    def run_butler(self, args, config, *, check=True, log_file=None, **kw):
        self.calls.append(list(args))
        cmd = args[0]
        if cmd == "create":
            (config.repo / "butler.yaml").parent.mkdir(parents=True, exist_ok=True)
            (config.repo / "butler.yaml").write_text("")
        elif cmd == "ingest-files":
            self.state["collections"].add(args[4])
        elif cmd == "collection-chain":
            if self.state.get("chain_noop"):
                return subprocess.CompletedProcess(args, 0)
            chain = args[2]
            if "--mode" in args and args[args.index("--mode") + 1] == "extend":
                # Mirrors Butler: creates a missing chain, and moves an
                # already-present child to the end instead of erroring.
                members = self.state["chains"].setdefault(chain, [])
                for a in args[3:]:
                    if a.startswith("--") or a == "extend":
                        continue
                    if a in members:
                        members.remove(a)
                    members.append(a)
            else:
                self.state["chains"][chain] = [
                    a for a in args[3:] if not a.startswith("--") and a != "redefine"
                ]
            self.state["collections"].add(chain)
        elif cmd == "register-skymap":
            if self.state.get("skymap_fails"):
                return subprocess.CompletedProcess(args, 1)
            self.state["collections"].add("skymaps")
            if self.state.get("skymap_lands", True):
                name = args[args.index("-c") + 1].split("=", 1)[1]
                self.state["datasets"].add(("skymaps", name))
        return subprocess.CompletedProcess(args, 0)

    def collection_exists(self, config, name):
        return name in self.state["collections"]

    def chain_members(self, config, name):
        return (
            list(self.state["chains"][name]) if name in self.state["chains"] else None
        )

    def has_datasets(self, config, dataset_type, collections, *, where=""):
        """A skyMap is visible in a RUN holding it, or through a chain member.

        Honours a ``skymap = '<name>'`` where clause; no clause matches any skymap.
        """
        self.dataset_queries.append((dataset_type, collections, where))
        names = [collections] if isinstance(collections, str) else list(collections)
        m = re.search(r"skymap\s*=\s*'([^']*)'", where or "")
        want = m.group(1) if m else None

        def visible(name):
            if any(
                run == name and (want is None or sky == want)
                for run, sky in self.state["datasets"]
            ):
                return True
            return any(visible(m) for m in self.state["chains"].get(name, []))

        return dataset_type == "skyMap" and any(visible(n) for n in names)


@contextmanager
def _patched(bootstrap, fake):
    """Enter all four stack-free patches (run_butler + the butler_query helpers)."""
    from stips.core import butler_query

    with ExitStack() as es:
        es.enter_context(mock.patch.object(bootstrap, "run_butler", fake.run_butler))
        es.enter_context(
            mock.patch.object(butler_query, "collection_exists", fake.collection_exists)
        )
        es.enter_context(
            mock.patch.object(butler_query, "chain_members", fake.chain_members)
        )
        es.enter_context(
            mock.patch.object(butler_query, "has_datasets", fake.has_datasets)
        )
        yield


def test_run_fresh_repo_does_every_step_in_order(tmp_path):
    from stips.core import bootstrap

    refcat_repo, shards = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    fake = _Butler({"collections": set(), "chains": {}})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg, log_file=tmp_path / "b.log")
    assert res.success and res.error is None
    assert (
        res.repo_created
        and res.instrument_registered
        and res.refcats_ingested
        and res.skymap_registered
    )
    cmds = [c[0] for c in fake.calls]
    assert cmds == [
        "create",
        "register-instrument",
        "register-dataset-type",
        "ingest-files",
        "collection-chain",
        "register-skymap",
        "collection-chain",
    ]
    assert fake.calls[1] == [
        "register-instrument",
        str(cfg.repo),
        cfg.instrument_class,
        "--update",
    ]
    assert fake.calls[2] == [
        "register-dataset-type",
        str(cfg.repo),
        "the_monster_20250219_local",
        "SimpleCatalog",
        "htm7",
    ]
    ingest = fake.calls[3]
    assert ingest[:5] == [
        "ingest-files",
        "-t",
        "direct",
        str(cfg.repo),
        "the_monster_20250219_local",
    ]
    assert ingest[5] == "refcats/the_monster_20250219_local"
    assert ingest[6] == str(shards / "filename_to_htm.ecsv")
    assert fake.calls[4] == [
        "collection-chain",
        str(cfg.repo),
        "refcats",
        "--mode",
        "extend",
        "refcats/the_monster_20250219_local",
    ]
    assert fake.calls[5] == [
        "register-skymap",
        str(cfg.repo),
        "-C",
        str(cfg.resolve_config("makeSkyMap.py")),
        "-c",
        "name=nickelRings-v1",
    ]
    assert fake.calls[6] == [
        "collection-chain",
        str(cfg.repo),
        "skymaps/nickelRings",
        "--mode",
        "extend",
        "skymaps",
    ]


def test_run_is_idempotent_and_never_redefines_refcats(tmp_path):
    from stips.core import bootstrap

    refcat_repo, shards = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    cfg.repo.mkdir(parents=True)
    (cfg.repo / "butler.yaml").write_text("")
    state = {
        "collections": {
            "refcats/the_monster_20250219_local",
            "refcats",
            "skymaps/nickelRings",
            "refcats/gaia_dr3/20261001",
        },
        "chains": {
            "refcats": [
                "refcats/gaia_dr3/20261001",
                "refcats/the_monster_20250219_local",
            ],
            "skymaps/nickelRings": ["skymaps"],
        },
        "datasets": {("skymaps", "nickelRings-v1")},
    }
    fake = _Butler(state)
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert res.success
    cmds = [c[0] for c in fake.calls]
    assert "create" not in cmds and "ingest-files" not in cmds
    assert cmds.count("collection-chain") == 0  # both chains already complete
    assert (
        state["chains"]["refcats"][0] == "refcats/gaia_dr3/20261001"
    )  # Gaia run preserved
    assert cmds.count("register-skymap") == 0  # already registered in skymaps
    # The chain-visibility check runs on the skip path too.
    assert (
        "skyMap",
        "skymaps/nickelRings",
        "skymap = 'nickelRings-v1'",
    ) in fake.dataset_queries


def test_second_instrument_in_shared_repo_registers_its_own_skymap(tmp_path):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    # A shared repo: skymaps holds another instrument's skymap only.
    state = _initialized_state(datasets={("skymaps", "otherRings-v1")})
    state["collections"].discard("skymaps/nickelRings")
    del state["chains"]["skymaps/nickelRings"]
    fake = _Butler(state)
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg)
    assert res.success
    reg = [c for c in fake.calls if c[0] == "register-skymap"]
    assert len(reg) == 1 and reg[0][-2:] == ["-c", "name=nickelRings-v1"]
    assert [c for c in fake.calls if c[0] == "collection-chain"] == [
        [
            "collection-chain",
            str(cfg.repo),
            "skymaps/nickelRings",
            "--mode",
            "extend",
            "skymaps",
        ]
    ]
    assert state["chains"]["skymaps/nickelRings"] == ["skymaps"]


def test_skip_path_warns_when_skymap_not_visible_through_chain(tmp_path, caplog):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    state = _initialized_state(chain_noop=True)
    state["collections"].discard("skymaps/nickelRings")
    del state["chains"]["skymaps/nickelRings"]
    fake = _Butler(state)
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg)
    assert res.success
    assert not [c for c in fake.calls if c[0] == "register-skymap"]
    assert any(
        "No skyMap dataset visible" in r.getMessage() and r.levelname == "WARNING"
        for r in caplog.records
    )


def test_run_logs_by_butler_yaml_without_querying_the_registry(tmp_path, caplog):
    import logging

    from stips.core import bootstrap

    caplog.set_level(logging.INFO, logger="stips.core.bootstrap")
    cfg = _full_cfg(tmp_path, refcat_repo=None)
    fake = _Butler({"collections": set(), "chains": {}})
    boom = mock.Mock(side_effect=AssertionError("needs_bootstrap must not run"))
    with mock.patch.object(bootstrap, "needs_bootstrap", boom), _patched(
        bootstrap, fake
    ):
        assert bootstrap.run(cfg, dry_run=True).success
        assert f"Bootstrapping repository: {cfg.repo}" in caplog.text
        cfg.repo.mkdir(parents=True)
        (cfg.repo / "butler.yaml").write_text("")
        caplog.clear()
        assert bootstrap.run(cfg, dry_run=True).success
        assert f"Repository exists; verifying/repairing: {cfg.repo}" in caplog.text
    boom.assert_not_called()


def test_run_adds_monster_to_existing_refcats_chain_with_extend(tmp_path):
    from stips.core import bootstrap

    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    state = {
        "collections": {"refcats", "refcats/gaia_dr3/x"},
        "chains": {"refcats": ["refcats/gaia_dr3/x"]},
    }
    fake = _Butler(state)
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        assert bootstrap.run(cfg).success
    chain_calls = [
        c for c in fake.calls if c[0] == "collection-chain" and c[2] == "refcats"
    ]
    assert chain_calls == [
        [
            "collection-chain",
            str(cfg.repo),
            "refcats",
            "--mode",
            "extend",
            "refcats/the_monster_20250219_local",
        ]
    ]
    assert state["chains"]["refcats"] == [
        "refcats/gaia_dr3/x",
        "refcats/the_monster_20250219_local",
    ]


def test_missing_shards_fails_naming_the_directory(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=tmp_path / "refcats")
    fake = _Butler({"collections": set(), "chains": {}})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert not res.success
    assert "the_monster_20250219_afw" in res.error and "refcat_htm7_" in res.error
    assert res.repo_created and res.instrument_registered and not res.refcats_ingested


def test_missing_refcat_repo_fails_before_touching_refcats(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    fake = _Butler({"collections": set(), "chains": {}})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert not res.success and "REFCAT_REPO" in res.error


def test_register_skymap_failure_is_a_warning(tmp_path, caplog):
    from stips.core import bootstrap

    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    fake = _Butler({"collections": set(), "chains": {}, "skymap_fails": True})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert res.success and res.skymap_registered
    assert any(
        "register-skymap" in r.getMessage() and r.levelname == "WARNING"
        for r in caplog.records
    )


def test_register_skymap_warns_when_no_skymap_visible(tmp_path, caplog):
    from stips.core import bootstrap

    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    # register-skymap "succeeds" but no skyMap lands: absent before and after.
    fake = _Butler({"collections": set(), "chains": {}, "skymap_lands": False})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert res.success
    assert any(
        "No skyMap dataset visible" in r.getMessage() and r.levelname == "WARNING"
        for r in caplog.records
    )


def _initialized_state(**over):
    """A fully-bootstrapped repo: MONSTER RUN, both chains, skyMap in skymaps."""
    state = {
        "collections": {
            "refcats/the_monster_20250219_local",
            "refcats",
            "refcats/gaia_dr3/x",
            "skymaps",
            "skymaps/nickelRings",
        },
        "chains": {
            "refcats": ["refcats/gaia_dr3/x", "refcats/the_monster_20250219_local"],
            "skymaps/nickelRings": ["skymaps"],
        },
        "datasets": {("skymaps", "nickelRings-v1")},
    }
    state.update(over)
    return state


def _initialized_cfg(tmp_path):
    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    cfg.repo.mkdir(parents=True)
    (cfg.repo / "butler.yaml").write_text("")
    return cfg


def test_initialized_repo_still_re_registers_instrument(tmp_path):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    fake = _Butler(_initialized_state())
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=False), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert fake.calls == [
        ["register-instrument", str(cfg.repo), cfg.instrument_class, "--update"]
    ]
    assert res.success and res.error is None
    assert (
        res.repo_created
        and res.instrument_registered
        and res.refcats_ingested
        and res.skymap_registered
    )


def test_rebootstrap_after_dropping_monster_run_reingests(tmp_path):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    state = _initialized_state()
    state["collections"].discard("refcats/the_monster_20250219_local")
    state["chains"]["refcats"] = ["refcats/gaia_dr3/x"]
    fake = _Butler(state)
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=False), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert res.success and res.error is None
    assert [c[0] for c in fake.calls] == [
        "register-instrument",
        "register-dataset-type",
        "ingest-files",
        "collection-chain",
    ]
    assert fake.calls[-1] == [
        "collection-chain",
        str(cfg.repo),
        "refcats",
        "--mode",
        "extend",
        "refcats/the_monster_20250219_local",
    ]
    assert state["chains"]["refcats"] == [
        "refcats/gaia_dr3/x",
        "refcats/the_monster_20250219_local",
    ]


def test_rebootstrap_with_missing_skymap_chain_recreates_it(tmp_path):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    state = _initialized_state()
    state["collections"].discard("skymaps/nickelRings")
    del state["chains"]["skymaps/nickelRings"]
    fake = _Butler(state)
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=False), _patched(
        bootstrap, fake
    ):
        res = bootstrap.run(cfg)
    assert res.success
    cmds = [c[0] for c in fake.calls]
    assert "register-skymap" not in cmds
    assert [c for c in fake.calls if c[0] == "collection-chain"] == [
        [
            "collection-chain",
            str(cfg.repo),
            "skymaps/nickelRings",
            "--mode",
            "extend",
            "skymaps",
        ]
    ]
    assert state["chains"]["skymaps/nickelRings"] == ["skymaps"]


def test_chain_query_failure_never_redefines(tmp_path):
    """A failed chain_members probe must not fall back to a redefining call."""
    from stips.core import bootstrap, butler_query

    cfg = _initialized_cfg(tmp_path)
    state = _initialized_state()
    state["collections"].discard("refcats/the_monster_20250219_local")
    state["chains"]["refcats"] = ["refcats/gaia_dr3/x"]
    fake = _Butler(state)
    # Both in-stack probes fail (collection_exists -> False, chain_members ->
    # None) while the chain really exists with a Gaia member.
    with _patched(bootstrap, fake), mock.patch.object(
        butler_query, "chain_members", lambda config, name: None
    ), mock.patch.object(butler_query, "collection_exists", lambda config, name: False):
        bootstrap._ensure_chain_member(
            cfg, "refcats", "refcats/the_monster_20250219_local", None
        )
    assert fake.calls == [
        [
            "collection-chain",
            str(cfg.repo),
            "refcats",
            "--mode",
            "extend",
            "refcats/the_monster_20250219_local",
        ]
    ]
    assert state["chains"]["refcats"] == [
        "refcats/gaia_dr3/x",
        "refcats/the_monster_20250219_local",
    ]


def test_present_monster_run_needs_no_refcat_repo(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    cfg.repo.mkdir(parents=True)
    (cfg.repo / "butler.yaml").write_text("")
    fake = _Butler(_initialized_state())
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg)
    assert res.success and res.error is None
    assert fake.calls == [
        ["register-instrument", str(cfg.repo), cfg.instrument_class, "--update"]
    ]


def test_initialized_repo_re_register_failure_becomes_result_error(tmp_path):
    from stips.core import bootstrap

    cfg = _initialized_cfg(tmp_path)
    fake = _Butler(_initialized_state())

    def boom(args, config, **kw):
        raise subprocess.CalledProcessError(3, ["butler", *args])

    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=False), _patched(
        bootstrap, fake
    ):
        with mock.patch.object(bootstrap, "run_butler", boom):
            res = bootstrap.run(cfg)
    assert not res.success
    assert "register-instrument" in res.error and "exit 3" in res.error


def test_initialized_repo_dry_run_touches_nothing(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    fake = _Butler({"collections": set(), "chains": {}})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=False), _patched(
        bootstrap, fake
    ):
        assert bootstrap.run(cfg, dry_run=True).success
    assert fake.calls == []


def test_butler_failure_becomes_result_error(tmp_path):
    from stips.core import bootstrap

    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    fake = _Butler({"collections": set(), "chains": {}})

    def boom(args, config, **kw):
        if args[0] == "ingest-files":
            raise subprocess.CalledProcessError(2, ["butler", *args])
        return fake.run_butler(args, config, **kw)

    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        with mock.patch.object(bootstrap, "run_butler", boom):
            res = bootstrap.run(cfg)
    assert not res.success and "ingest-files" in res.error and "exit 2" in res.error


def test_dry_run_touches_nothing(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    fake = _Butler({"collections": set(), "chains": {}})
    with mock.patch.object(bootstrap, "needs_bootstrap", return_value=True), _patched(
        bootstrap, fake
    ):
        assert bootstrap.run(cfg, dry_run=True).success
    assert fake.calls == []


# --- ECSV map ---------------------------------------------------------------


def test_build_monster_map_writes_sorted_absolute_ecsv(tmp_path):
    from astropy.table import Table
    from stips.core import bootstrap

    _, shards = _shards(tmp_path)
    (shards / "notes.txt").write_text("ignored")
    out = bootstrap.build_monster_map(shards, shards / "filename_to_htm.ecsv")
    t = Table.read(out, format="ascii.ecsv")
    assert list(t.colnames) == ["path", "htm7"]
    assert list(t["htm7"]) == [131072, 131073, 131074]
    assert all(p.startswith(os.path.abspath(shards)) for p in t["path"])


def test_build_monster_map_keeps_symlinked_refcat_path(tmp_path):
    from astropy.table import Table
    from stips.core import bootstrap

    _, shards = _shards(tmp_path)
    link = tmp_path / "linked_shards"
    link.symlink_to(shards, target_is_directory=True)
    out = bootstrap.build_monster_map(link, tmp_path / "map.ecsv")
    t = Table.read(out, format="ascii.ecsv")
    assert all(p.startswith(str(link) + os.sep) for p in t["path"])


def test_ensure_monster_map_reuses_map_whose_path_has_a_space(tmp_path):
    from stips.core import bootstrap

    _, shards = _shards(tmp_path / "a b")
    m = bootstrap.ensure_monster_map(shards)
    mtime = m.stat().st_mtime_ns
    assert bootstrap.ensure_monster_map(shards) == m
    assert m.stat().st_mtime_ns == mtime  # reused, not rebuilt


def test_map_with_unparseable_row_is_invalid(tmp_path):
    from stips.core import bootstrap

    m = tmp_path / "filename_to_htm.ecsv"
    m.write_text('# %ECSV 1.0\n"/x/refcat_htm7_1.fits 1\n')  # unbalanced quote
    assert bootstrap._map_is_valid(m) is False


def test_map_with_header_but_no_rows_is_rebuilt(tmp_path):
    from stips.core import bootstrap

    _, shards = _shards(tmp_path)
    m = shards / "filename_to_htm.ecsv"
    m.write_text("# %ECSV 1.0\n# ---\n# datatype: []\npath htm7\n")
    assert bootstrap._map_is_valid(m) is False
    assert bootstrap.ensure_monster_map(shards) == m
    assert "refcat_htm7_131072" in m.read_text()


def test_ensure_monster_map_reuses_valid_rebuilds_stale_or_non_ecsv(tmp_path):
    from stips.core import bootstrap

    _, shards = _shards(tmp_path)
    m = shards / "filename_to_htm.ecsv"
    first = bootstrap.ensure_monster_map(shards)
    assert first == m
    mtime = m.stat().st_mtime_ns
    assert (
        bootstrap.ensure_monster_map(shards) == m and m.stat().st_mtime_ns == mtime
    )  # reused
    m.write_text("path htm7\n/nowhere/refcat_htm7_1.fits 1\n")  # not ECSV -> rebuilt
    bootstrap.ensure_monster_map(shards)
    assert m.read_text().startswith("# %ECSV")
    m.write_text(
        m.read_text().replace(os.path.abspath(shards), "/stale/host")
    )  # stale -> rebuilt
    bootstrap.ensure_monster_map(shards)
    assert "/stale/host" not in m.read_text()


def test_ensure_monster_map_falls_back_to_tempdir_when_read_only(tmp_path, monkeypatch):
    import tempfile

    from stips.core import bootstrap

    _, shards = _shards(tmp_path)
    monkeypatch.setattr(bootstrap, "_dir_is_writable", lambda d: False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    out = bootstrap.ensure_monster_map(shards)
    assert out == tmp_path / "tmp" / "stips_refcat_ecsv" / "filename_to_htm.ecsv"
    assert out.exists()


# --- MONSTER optional (refcat mode does not use it) --------------------------


def test_register_chain_script_registers_chained_collection():
    from stips.core.bootstrap import _build_register_chain_script

    s = _build_register_chain_script("/repo", "refcats")
    assert "writeable=True" in s and "'/repo'" in s
    assert "CollectionType.CHAINED" in s and "refcats" in s
    assert "registerCollection" in s  # v27 fallback
    compile(s, "<snippet>", "exec")


def test_register_empty_chain_raises_when_snippet_fails(tmp_path, monkeypatch):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path)
    monkeypatch.setattr(
        bootstrap, "run_butler_python_json", lambda script, config: None
    )
    with pytest.raises(bootstrap.BootstrapError, match="refcats"):
        bootstrap.register_empty_chain(cfg, "refcats")


def test_register_empty_chain_runs_snippet(tmp_path, monkeypatch):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path)
    seen = []

    def fake(script, config):
        seen.append(script)
        return {"registered": "refcats", "created": True}

    monkeypatch.setattr(bootstrap, "run_butler_python_json", fake)
    bootstrap.register_empty_chain(cfg, "refcats")
    assert len(seen) == 1 and str(cfg.repo) in seen[0]


def test_not_required_without_shards_skips_and_registers_empty_chain(
    tmp_path, monkeypatch, caplog
):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    fake = _Butler({"collections": set(), "chains": {}, "datasets": set()})
    registered = []
    monkeypatch.setattr(
        bootstrap,
        "register_empty_chain",
        lambda config, name, log_file=None: registered.append(name),
    )
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=False)
    assert res.success and res.monster_skipped and not res.refcats_ingested
    assert registered == ["refcats"]
    cmds = [c[0] for c in fake.calls]
    assert "ingest-files" not in cmds and "register-dataset-type" not in cmds
    assert any(
        r.levelname == "WARNING"
        and "MONSTER" in r.getMessage()
        and "skipp" in r.getMessage()
        for r in caplog.records
    )


def test_not_required_with_empty_refcat_repo_names_the_directory(
    tmp_path, monkeypatch, caplog
):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=tmp_path / "empty")
    fake = _Butler({"collections": set(), "chains": {}, "datasets": set()})
    registered = []
    monkeypatch.setattr(
        bootstrap,
        "register_empty_chain",
        lambda config, name, log_file=None: registered.append(name),
    )
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=False)
    assert res.success and res.monster_skipped and registered == ["refcats"]
    assert any(
        r.levelname == "WARNING" and "the_monster_20250219_afw" in r.getMessage()
        for r in caplog.records
    )


def test_not_required_with_shards_still_ingests(tmp_path, monkeypatch):
    from stips.core import bootstrap

    refcat_repo, _ = _shards(tmp_path)
    cfg = _full_cfg(tmp_path, refcat_repo=refcat_repo)
    fake = _Butler({"collections": set(), "chains": {}, "datasets": set()})
    monkeypatch.setattr(
        bootstrap,
        "register_empty_chain",
        lambda *a, **k: pytest.fail("should not be called"),
    )
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=False)
    assert res.success and res.refcats_ingested and not res.monster_skipped
    assert "ingest-files" in [c[0] for c in fake.calls]


def test_required_without_shards_still_fails(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=tmp_path / "empty")
    fake = _Butler({"collections": set(), "chains": {}, "datasets": set()})
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=True)
    assert not res.success and "the_monster_20250219_afw" in res.error
    assert not res.monster_skipped


def test_not_required_with_existing_chain_does_not_reregister(tmp_path, monkeypatch):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    state = _initialized_state()
    state["collections"].discard("refcats/the_monster_20250219_local")
    state["chains"]["refcats"] = ["refcats/gaia_dr3/x"]
    fake = _Butler(state)
    monkeypatch.setattr(
        bootstrap,
        "register_empty_chain",
        lambda *a, **k: pytest.fail("chain exists"),
    )
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=False)
    assert res.success and res.monster_skipped
    assert state["chains"]["refcats"] == ["refcats/gaia_dr3/x"]


def test_not_required_with_present_monster_run_counts_as_ingested(tmp_path):
    from stips.core import bootstrap

    cfg = _full_cfg(tmp_path, refcat_repo=None)
    cfg.repo.mkdir(parents=True)
    (cfg.repo / "butler.yaml").write_text("")
    fake = _Butler(_initialized_state())
    with _patched(bootstrap, fake):
        res = bootstrap.run(cfg, require_monster=False)
    assert res.success and res.refcats_ingested and not res.monster_skipped
