"""Bootstrap a Butler repository.

Creates the repo, registers the active instrument, ingests the MONSTER
reference-catalog shards and registers the skymap — in Python, through the
same ``run_butler`` / ``butler_query`` helpers every other step uses. Each
step is idempotent so ``run()`` can be re-run on a half-built repo.

Reference catalogs: this module ingests the sharded MONSTER catalog from
``REFCAT_REPO`` into the ``refcats`` CHAINED collection whenever the shards
are present. Gaia DR3 / PS1 shards fetched on demand (``stips.core.refcat``)
live in the same chain; bootstrap only ever EXTENDS that chain, never
redefines it, so a re-bootstrap keeps them. MONSTER is required only when the
refcat mode uses it (``monster``); otherwise, with no shards, the ingest is
skipped with a warning and an empty ``refcats`` chain is registered so the
on-demand fetch has a chain to extend.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core import butler_query
from stips.core.stack import run_butler, run_butler_python_json

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)

MONSTER_SHARD_SUBDIR = "data/refcats/the_monster_20250219_afw"
MONSTER_SHARD_GLOB = "refcat_htm7_*.fits"
MONSTER_DATASET_TYPE = "the_monster_20250219_local"
MONSTER_RUN = f"refcats/{MONSTER_DATASET_TYPE}"
REFCATS_CHAIN = "refcats"
SKYMAP_RUN = "skymaps"
MAP_NAME = "filename_to_htm.ecsv"
_SHARD_RE = re.compile(r"refcat_htm7_(\d+)\.fits$")


class BootstrapError(RuntimeError):
    """A bootstrap step cannot proceed (missing input, failed butler command)."""


@dataclass
class BootstrapResult:
    """Result of bootstrap operation."""

    success: bool
    error: str | None = None
    repo_created: bool = False
    instrument_registered: bool = False
    refcats_ingested: bool = False
    skymap_registered: bool = False
    monster_skipped: bool = False


def needs_bootstrap(config: Config) -> bool:
    """Check if the repository needs bootstrapping.

    Returns True if the repo doesn't exist, or if critical infrastructure
    (``skymaps``, ``refcats`` and, with an active profile, its skymap chain) is
    missing — e.g. after a botched clean operation.

    Args:
        config: Pipeline configuration

    Returns:
        True if the repository needs (re-)bootstrapping
    """
    butler_yaml = config.repo / "butler.yaml"
    if not butler_yaml.exists():
        return True

    # Repo exists — verify critical collections are present.
    # A clean bug could remove skymaps/refcats while leaving butler.yaml.
    required = [SKYMAP_RUN, REFCATS_CHAIN]
    prof = getattr(config, "profile", None)
    skymap_chain = getattr(prof, "skymap_collection", None) if prof else None
    if skymap_chain:
        required.append(skymap_chain)
    for collection in required:
        try:
            # collection_exists() is False both when the collection is absent and
            # when the in-stack query fails to run — either way, bootstrap.
            if not butler_query.collection_exists(config, collection):
                log.warning(
                    f"Collection '{collection}' missing from repo — "
                    f"bootstrap needed"
                )
                return True
        except Exception:
            return True

    return False


# --------------------------------------------------------------------------- #
# MONSTER shard map
# --------------------------------------------------------------------------- #


def monster_shard_dir(config: Config) -> Path:
    """``<REFCAT_REPO>/data/refcats/the_monster_20250219_afw``."""
    if not config.refcat_repo:
        raise BootstrapError(
            "REFCAT_REPO is not set in the config env: block; bootstrap needs it to "
            f"find the MONSTER shards under <REFCAT_REPO>/{MONSTER_SHARD_SUBDIR}/"
        )
    return Path(config.refcat_repo) / MONSTER_SHARD_SUBDIR


def build_monster_map(shard_dir: Path, out_path: Path) -> Path:
    """Write the ``path, htm7`` ECSV map ``butler ingest-files`` consumes."""
    from astropy.table import Table

    rows = []
    for fn in Path(shard_dir).glob(MONSTER_SHARD_GLOB):
        m = _SHARD_RE.search(fn.name)
        if m:
            # abspath, not resolve(): a symlinked REFCAT_REPO keeps its link path.
            rows.append((os.path.abspath(fn), int(m.group(1))))
    rows.sort(key=lambda r: r[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Table(rows=rows, names=["path", "htm7"]).write(
        out_path, format="ascii.ecsv", overwrite=True
    )
    log.info("MONSTER map written: %s (%d shards)", out_path, len(rows))
    return out_path


def _dir_is_writable(d: Path) -> bool:
    return os.access(d, os.W_OK)


def _map_is_valid(map_path: Path) -> bool:
    """A usable map is ECSV, has a shard row, and its first shard path exists."""
    if not map_path.is_file() or map_path.stat().st_size == 0:
        return False
    with map_path.open() as fh:
        if not fh.readline().startswith("# %ECSV"):
            return False
        for line in fh:
            if "refcat_htm7_" in line:
                # astropy quotes a path containing whitespace; its ECSV quoting
                # is shell-compatible, so shlex recovers the whole first field.
                try:
                    first = shlex.split(line)[0]
                except (ValueError, IndexError):
                    return False
                return Path(first).is_file()
    return False  # a header with no shard rows would ingest nothing


def ensure_monster_map(shard_dir: Path) -> Path:
    """Return a valid ECSV map for ``shard_dir``, building or rebuilding it.

    Written next to the shards when that directory is writable, else under
    ``<tempdir>/stips_refcat_ecsv/`` (a read-only container mount).
    """
    shard_dir = Path(shard_dir)
    in_place = shard_dir / MAP_NAME
    if _map_is_valid(in_place):
        log.info("Using existing MONSTER map: %s", in_place)
        return in_place
    if _dir_is_writable(shard_dir):
        return build_monster_map(shard_dir, in_place)
    out = Path(tempfile.gettempdir()) / "stips_refcat_ecsv" / MAP_NAME
    log.info("Shard dir is read-only; writing the MONSTER map to %s", out)
    return build_monster_map(shard_dir, out)


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #


def _butler(
    args: list[str], config: Config, log_file: Path | None, *, check: bool = True
) -> subprocess.CompletedProcess:
    try:
        return run_butler(args, config, check=check, log_file=log_file)
    except subprocess.CalledProcessError as exc:
        where = f" (see {log_file})" if log_file else ""
        raise BootstrapError(
            f"butler {args[0]} failed with exit {exc.returncode}{where}"
        ) from exc


def create_repo(config: Config, log_file: Path | None = None) -> None:
    """Create the Butler repo unless ``butler.yaml`` already exists."""
    if (config.repo / "butler.yaml").is_file():
        log.info("Butler repository exists: %s", config.repo)
        return
    log.info("Creating Butler repository: %s", config.repo)
    _butler(["create", str(config.repo)], config, log_file)


def register_instrument(config: Config, log_file: Path | None = None) -> None:
    """Register (or re-register with ``--update``) the active instrument.

    Bootstrap is the deliberate way to add an instrument to a repo or to
    migrate a legacy ``class_name`` (see stips.core.pipeline.ensure_instrument_registered).
    """
    cls = config.instrument_class
    log.info("Registering instrument %s", cls)
    _butler(
        ["register-instrument", str(config.repo), cls, "--update"], config, log_file
    )


def ingest_monster(
    config: Config, log_file: Path | None = None, *, required: bool = True
) -> bool:
    """Ingest the MONSTER shards (once) and make them a member of ``refcats``.

    With the MONSTER RUN already present, ``REFCAT_REPO`` and the shard
    directory are not consulted at all: only the chain membership is ensured.
    Shards present under ``REFCAT_REPO`` are ingested whatever ``required``
    says. Without them (or without ``REFCAT_REPO``), ``required`` raises
    :class:`BootstrapError`; otherwise the ingest is skipped with a warning and
    an empty ``refcats`` chain is registered if none exists.

    Returns:
        True when MONSTER was ingested or was already present, False when the
        ingest was skipped.
    """
    if butler_query.collection_exists(config, MONSTER_RUN):
        # The RUN is only ever created by `ingest-files`, which requires the
        # dataset type to be registered; and with the RUN present the ingest is
        # skipped anyway.
        log.info("MONSTER RUN already present: %s", MONSTER_RUN)
        _ensure_chain_member(config, REFCATS_CHAIN, MONSTER_RUN, log_file)
        return True

    shard_dir = monster_shard_dir(config) if config.refcat_repo else None
    have_shards = bool(shard_dir and any(shard_dir.glob(MONSTER_SHARD_GLOB)))
    if not have_shards:
        if required:
            shard_dir = monster_shard_dir(config)  # raises when REFCAT_REPO is unset
            raise BootstrapError(
                f"No MONSTER refcat shards found under {shard_dir} (expected files "
                f"like {MONSTER_SHARD_GLOB}); see docs/reference-catalogs.md"
            )
        log.warning(
            "MONSTER shards not found under %s; refcat mode does not use MONSTER, "
            "skipping the ingest (set REFCAT_REPO and add shards to use mode "
            "'monster')",
            shard_dir or f"<REFCAT_REPO unset>/{MONSTER_SHARD_SUBDIR}",
        )
        if not butler_query.collection_exists(config, REFCATS_CHAIN):
            register_empty_chain(config, REFCATS_CHAIN, log_file)
        return False

    ecsv = ensure_monster_map(shard_dir)
    repo = str(config.repo)
    _butler(
        [
            "register-dataset-type",
            repo,
            MONSTER_DATASET_TYPE,
            "SimpleCatalog",
            "htm7",
        ],
        config,
        log_file,
        check=False,
    )
    log.info("Ingesting MONSTER -> %s", MONSTER_RUN)
    _butler(
        [
            "ingest-files",
            "-t",
            "direct",
            repo,
            MONSTER_DATASET_TYPE,
            MONSTER_RUN,
            str(ecsv),
        ],
        config,
        log_file,
    )
    _ensure_chain_member(config, REFCATS_CHAIN, MONSTER_RUN, log_file)
    return True


def _build_register_chain_script(repo: str, name: str) -> str:
    """Snippet registering an empty CHAINED collection ``name`` if absent."""
    return f"""
import json
from lsst.daf.butler import Butler, CollectionType

butler = Butler.from_config({repo!r}, writeable=True)
name = {name!r}
try:
    created = butler.collections.register(name, CollectionType.CHAINED)
except AttributeError:
    # v27 fallback
    created = butler.registry.registerCollection(name, CollectionType.CHAINED)
print(json.dumps({{"registered": name, "created": bool(created)}}))
"""


def register_empty_chain(
    config: Config, name: str, log_file: Path | None = None
) -> None:
    """Create CHAINED collection ``name`` with no members (idempotent).

    The ``butler`` CLI cannot create an empty chain, so this is the one
    in-stack mutation snippet in bootstrap. Needed when MONSTER is skipped:
    ``stips refcat fetch`` extends ``refcats`` and must find it.
    """
    out = run_butler_python_json(
        _build_register_chain_script(str(config.repo), name), config
    )
    if not isinstance(out, dict) or out.get("registered") != name:
        raise BootstrapError(
            f"could not register the empty chain {name!r} in {config.repo} "
            "(see the preceding run_butler_python warning for the stack output)"
        )
    log.info(
        "Chain %s %s",
        name,
        "created (empty)" if out.get("created") else "already present",
    )


def _ensure_chain_member(
    config: Config, chain: str, member: str, log_file: Path | None
) -> None:
    """Make ``member`` part of CHAINED ``chain`` without disturbing other members.

    Always ``--mode extend``, never the bare form (whose default mode is
    ``redefine``): extend creates a missing chain and moves an already-present
    child to the end, so a failed membership probe can at worst reorder the
    chain, never drop its Gaia/PS1 runs.
    """
    members = butler_query.chain_members(config, chain)
    if members is not None and member in members:
        log.info("Chain %s already contains %s", chain, member)
        return
    log.info("Linking %s into chain %s", member, chain)
    _butler(
        ["collection-chain", str(config.repo), chain, "--mode", "extend", member],
        config,
        log_file,
    )


def register_skymap(config: Config, log_file: Path | None = None) -> None:
    """Register the profile's skymap and chain its RUN under the skymap collection.

    Quiet on re-run: when the ``skymaps`` RUN already holds the profile's
    ``skyMap`` (keyed on ``skymap_name``, so another instrument's skymap in a
    shared repo does not count) the registration is skipped and only the chain
    membership is ensured. A non-zero ``register-skymap`` is a warning (a
    config error the sanity query below surfaces).
    """
    prof = config.require_profile()
    where = f"skymap = '{prof.skymap_name}'"
    if butler_query.has_datasets(config, "skyMap", SKYMAP_RUN, where=where):
        log.info("SkyMap %r already registered in %s", prof.skymap_name, SKYMAP_RUN)
        _ensure_chain_member(config, prof.skymap_collection, SKYMAP_RUN, log_file)
        _check_skymap_visible(config, prof, where)
        return
    cfg_path = config.resolve_config("makeSkyMap.py")
    log.info("Registering SkyMap %r (config: %s)", prof.skymap_name, cfg_path)
    proc = _butler(
        [
            "register-skymap",
            str(config.repo),
            "-C",
            str(cfg_path),
            "-c",
            f"name={prof.skymap_name}",
        ],
        config,
        log_file,
        check=False,
    )
    if proc.returncode != 0:
        log.warning(
            "register-skymap exited %s; see %s",
            proc.returncode,
            log_file or "the butler output",
        )
    _ensure_chain_member(config, prof.skymap_collection, SKYMAP_RUN, log_file)
    _check_skymap_visible(config, prof, where)


def _check_skymap_visible(config: Config, prof, where: str) -> None:
    """Warn when the profile's skyMap is not visible through its chain."""
    if not butler_query.has_datasets(
        config, "skyMap", prof.skymap_collection, where=where
    ):
        log.warning(
            "No skyMap dataset visible in %s after registration", prof.skymap_collection
        )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run(
    config: Config,
    *,
    dry_run: bool = False,
    log_file: Path | None = None,
    require_monster: bool = True,
) -> BootstrapResult:
    """Bootstrap a Butler repository.

    Order: create repo -> register instrument -> ingest MONSTER -> register
    skymap. A failing step stops the run and is reported in
    ``BootstrapResult.error``; the per-step flags record how far it got.

    Idempotent: safe to re-run on an initialized repo; each step skips what
    already exists (ingest when the MONSTER RUN is present, chain members
    already linked, a registered skymap) and always re-registers the
    instrument with ``--update``. That is how ``stips bootstrap`` adds the
    active instrument to a shared repo, migrates a legacy class name (as
    ``ensure_instrument_registered``'s error messages advise), or re-ingests
    MONSTER after its RUN was removed.

    ``require_monster`` comes from the config's ``refcat.mode`` (True only for
    ``monster``). MONSTER shards found under ``REFCAT_REPO`` are ingested in
    any mode, and a present MONSTER RUN only has its chain membership ensured.
    Without shards (or ``REFCAT_REPO``), a required MONSTER fails the run;
    otherwise the ingest is skipped with a warning, an empty ``refcats`` chain
    is registered if absent (the on-demand Gaia/PS1 fetch extends it), and
    ``monster_skipped`` is set.
    """
    result = BootstrapResult(success=False)
    if (config.repo / "butler.yaml").is_file():
        log.info("Repository exists; verifying/repairing: %s", config.repo)
    else:
        log.info("Bootstrapping repository: %s", config.repo)
    if dry_run:
        monster_step = (
            "ingest MONSTER"
            if require_monster
            else "ingest MONSTER if shards are present, else register an "
            "empty refcats chain"
        )
        log.info(
            "[DRY RUN] Would create the repo, register the instrument, "
            "%s, register the skymap",
            monster_step,
        )
        result.success = True
        return result
    try:
        create_repo(config, log_file)
        result.repo_created = True
        register_instrument(config, log_file)
        result.instrument_registered = True
        ingested = ingest_monster(config, log_file, required=require_monster)
        result.refcats_ingested = ingested
        result.monster_skipped = not ingested
        register_skymap(config, log_file)
        result.skymap_registered = True
    except BootstrapError as exc:
        result.error = str(exc)
        log.error("Bootstrap failed: %s", exc)
        return result
    except Exception as exc:  # e.g. stack activation; keep failures in the result
        result.error = f"Bootstrap failed: {exc}"
        log.exception("Bootstrap failed unexpectedly")
        return result
    result.success = True
    log.info("Bootstrap complete")
    return result
