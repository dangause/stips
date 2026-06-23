"""CTIO Y4KCam NOIRLab-archive raw-data fetch (implements the ``fetch_data`` hook).

CTIO 1.0m / Y4KCam raw data lives in the public NOIRLab Astro Data Archive
(``astroarchive.noirlab.edu``). This downloads a night's raw frames (bias, flat,
object) into the layout expected by ingestion:

  ${RAW_PARENT_DIR}/${NIGHT}/raw/<archive-basename>.fits.fz

The archive exposes a plain HTTP/JSON API (advanced-search ``find`` to list a
night, ``retrieve/<md5sum>`` to download), so unlike the Nickel Lick fetch this
module needs no third-party client — it stays stdlib-only (``urllib``/``json``),
which keeps importing the CTIO profile (which wires ``fetch_data``) cheap.

Settings are read from the framework config's generic ``env`` block:
  ``NOIRLAB_API``        archive base URL (default ``https://astroarchive.noirlab.edu``)
  ``NOIRLAB_INSTRUMENT`` archive instrument name (default ``y4kcam``)
  ``NOIRLAB_PROPOSAL``   optional proposal-id filter (e.g. ``2007A-0002``)
  ``NOIRLAB_OBSTYPES``   optional comma list to restrict obs_type (default all)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

_DEFAULT_API = "https://astroarchive.noirlab.edu"
_DEFAULT_INSTRUMENT = "y4kcam"
_FIND_LIMIT = 5000


def _night_to_caldat(night: str) -> str:
    """``YYYYMMDD`` observing night -> archive ``caldat`` ``YYYY-MM-DD``."""
    try:
        return dt.datetime.strptime(night, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError as err:
        raise ValueError(f"Invalid night '{night}' (use YYYYMMDD)") from err


def _post_json(url: str, payload: dict, timeout: int = 120) -> list:
    """POST a JSON body and return the decoded JSON (a list of row dicts)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _find_night(
    api: str, instrument: str, caldat: str, proposal: str | None, obstypes: list[str]
) -> list[dict]:
    """List a night's raw frames via the advanced-search ``find`` endpoint."""
    search = [
        ["instrument", instrument],
        ["proc_type", "raw"],
        ["caldat", caldat, caldat],
    ]
    if proposal:
        search.append(["proposal", proposal])
    payload = {
        "outfields": ["md5sum", "archive_filename", "obs_type", "ifilter", "proposal"],
        "search": search,
    }
    rows = _post_json(f"{api}/api/adv_search/find/?limit={_FIND_LIMIT}", payload)
    # First element is a META/HEADER dict; real rows carry "md5sum".
    rows = [r for r in rows if isinstance(r, dict) and "md5sum" in r]
    if obstypes:
        keep = {o.lower() for o in obstypes}
        rows = [r for r in rows if str(r.get("obs_type", "")).lower() in keep]
    return rows


def _retrieve(api: str, md5sum: str, dest: Path, timeout: int = 300) -> None:
    """Download one file by md5sum to ``dest`` (atomic via a .part tmp file)."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(f"{api}/api/retrieve/{md5sum}/")
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)


def _fetch_night(
    night: str,
    raw_root: Path,
    *,
    api: str,
    instrument: str,
    proposal: str | None,
    obstypes: list[str],
    overwrite: bool = False,
) -> int:
    """Download a night's raws from NOIRLab.

    Returns a status code (NOT via ``sys.exit``):
      0 -> data downloaded and/or already present (ok)
      1 -> hard failure (one or more download errors)
      2 -> no data found in the archive for this night
    """
    raw_dir = Path(raw_root).expanduser() / night / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    caldat = _night_to_caldat(night)

    try:
        rows = _find_night(api, instrument, caldat, proposal, obstypes)
    except (urllib.error.URLError, ValueError) as err:  # pragma: no cover - network
        logging.error("NOIRLab find query failed for %s: %s", night, err)
        return 1
    logging.info(
        "NOIRLab find: %s raw frames for %s (caldat %s)", len(rows), night, caldat
    )
    if not rows:
        return 2

    downloaded = skipped = errors = 0
    for row in rows:
        name = Path(str(row["archive_filename"])).name  # basename only
        if not name:
            logging.warning("Skipping row without a filename: %s", row)
            continue
        dest = raw_dir / name
        if dest.exists() and not overwrite:
            skipped += 1
            continue
        try:
            _retrieve(api, row["md5sum"], dest)
            downloaded += 1
        except Exception as err:  # pragma: no cover - network
            errors += 1
            logging.error("Download failed for %s (%s): %s", name, row["md5sum"], err)

    logging.info(
        "Done. downloaded=%s skipped=%s errors=%s -> %s",
        downloaded,
        skipped,
        errors,
        raw_dir,
    )
    if errors:
        return 1
    if downloaded == 0 and skipped == 0:
        return 2
    return 0


def fetch_data(night: str, config, *, overwrite: bool = False) -> str:
    """``InstrumentProfile.fetch_data`` hook for CTIO (NOIRLab Astro Data Archive).

    Downloads a night's raws into ${RAW_PARENT_DIR}/<night>/raw/. NOIRLab
    settings come from the config's generic ``env`` block. Returns
    ``"ok"`` | ``"not_found"`` | ``"failed"``.
    """
    env = getattr(config, "env", {}) or {}
    obstypes = [o for o in env.get("NOIRLAB_OBSTYPES", "").split(",") if o.strip()]
    code = _fetch_night(
        night,
        Path(config.raw_parent_dir),
        api=env.get("NOIRLAB_API", _DEFAULT_API).rstrip("/"),
        instrument=env.get("NOIRLAB_INSTRUMENT", _DEFAULT_INSTRUMENT),
        proposal=env.get("NOIRLAB_PROPOSAL") or None,
        obstypes=obstypes,
        overwrite=overwrite,
    )
    return {0: "ok", 2: "not_found"}.get(code, "failed")
