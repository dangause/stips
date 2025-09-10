from __future__ import annotations

import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def tail_lines(s: str, n: int) -> str:
    if not s:
        return ""
    lines = s.rstrip("\n").splitlines()
    return "\n".join(lines[-n:]) if n > 0 else s


def run(
    cmd: List[str],
    check: bool,
    stdout_log: Optional[Path] = None,
    stderr_log: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess, tee stdout/stderr into files (if provided)."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = proc.communicate()
    if stdout_log:
        ensure_parent(stdout_log)
        stdout_log.write_text(out or "")
    if stderr_log:
        ensure_parent(stderr_log)
        stderr_log.write_text(err or "")
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=out, stderr=err
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def write_csv_row(csv_path: Path, headers: List[str], row: Dict[str, Any]) -> None:
    ensure_parent(csv_path)
    new = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if new:
            w.writeheader()
        safe = {h: row.get(h, "") for h in headers}
        w.writerow(safe)
