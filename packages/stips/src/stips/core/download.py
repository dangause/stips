"""Raw-data download orchestration.

Business logic behind the ``stips download`` command: resolving which nights to
fetch (from the CLI or the group ``-c`` YAML), detecting which nights already
have raw FITS on disk, and driving the active instrument's ``fetch_data`` hook
with per-night ok/not-found/failed accounting.

The CLI handler is presentation-only; all decisions live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import yaml

if TYPE_CHECKING:
    from stips.core.config import Config


@dataclass
class DownloadResult:
    """Outcome of a multi-night download.

    Attributes:
        succeeded: Nights fetched successfully (hook returned ``"ok"``).
        not_in_archive: Nights the hook reported missing (``"not_found"``).
        failed: Nights that raised or returned any other status.
    """

    succeeded: list[str] = field(default_factory=list)
    not_in_archive: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True when nothing outright failed (missing-from-archive is not a failure)."""
        return not self.failed


def nights_from_config(config_path: Path) -> list[str]:
    """Read science + coadd-template nights from a group ``-c`` pipeline YAML.

    Collects ``science.nights`` and (only for ``template.type == "coadd"``)
    ``template.nights`` into a sorted, de-duplicated list of ``YYYYMMDD`` strings.

    This mirrors the night selection :class:`stips.core.run.RunConfig` derives,
    but is deliberately standalone: the download command must stay lightweight and
    not import the full pipeline orchestrator.
    """
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    science_nights = (data.get("science") or {}).get("nights", [])
    template_config = data.get("template") or {}
    template_nights = (
        template_config.get("nights", [])
        if template_config.get("type") == "coadd"
        else []
    )

    all_nights = {str(n) for n in list(science_nights) + list(template_nights)}
    return sorted(all_nights)


def has_raw_data(night: str, config: Config) -> bool:
    """Return True if ``night`` already has FITS files under its raw directory."""
    raw_dir = config.raw_parent_dir / night / "raw"
    if not raw_dir.exists():
        return False
    fits = list(raw_dir.glob("*.fits")) + list(raw_dir.glob("*.fits.gz"))
    return len(fits) > 0


def missing_nights(nights: list[str], config: Config) -> list[str]:
    """Filter ``nights`` to those with no raw FITS on disk yet (preserving order)."""
    return [n for n in nights if not has_raw_data(n, config)]


def fetch_nights(
    nights: list[str],
    config: Config,
    *,
    overwrite: bool = False,
    on_event: Callable[[str, str, str | None], None] | None = None,
) -> DownloadResult:
    """Fetch each night via the active instrument's ``fetch_data`` hook.

    Args:
        nights: Nights (``YYYYMMDD``) to fetch.
        config: Pipeline configuration (its profile supplies ``fetch_data``).
        overwrite: Re-download nights that already have data.
        on_event: Optional progress callback invoked as
            ``on_event(night, status, error)`` where ``status`` is one of
            ``"start" | "ok" | "not_found" | "failed"``; ``error`` carries the
            exception text on a raised failure, else ``None``.

    Returns:
        DownloadResult tallying succeeded / not-in-archive / failed nights.
    """
    fetch_data = config.require_profile().fetch_data
    result = DownloadResult()

    def emit(night: str, status: str, error: str | None = None) -> None:
        if on_event is not None:
            on_event(night, status, error)

    for night in nights:
        emit(night, "start")
        try:
            status = fetch_data(night, config, overwrite=overwrite)
        except Exception as e:  # noqa: BLE001 - hook may raise anything
            result.failed.append(night)
            emit(night, "failed", str(e))
            continue

        if status == "ok":
            result.succeeded.append(night)
            emit(night, "ok")
        elif status == "not_found":
            result.not_in_archive.append(night)
            emit(night, "not_found")
        else:
            result.failed.append(night)
            emit(night, "failed")

    return result
