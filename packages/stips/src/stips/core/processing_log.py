"""Processing log for tracking pipeline execution and failures.

This module provides persistence for tracking which configs were used,
what failed, and the final status of each processing step.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class ConfigAttempt:
    """Record of a single config attempt."""

    config: str  # Config file name
    is_fallback: bool
    quanta_attempted: int = 0
    quanta_succeeded: int = 0
    quanta_failed: int = 0
    failed_exposures: list[dict] = field(default_factory=list)
    error: str | None = None
    # Set when the pipetask reported success (or ran) but the quanta summary
    # could not be parsed, so quanta_succeeded/quanta_failed are the honest
    # unparsed 0 rather than a fabricated count.
    quanta_parse_failed: bool = False


@dataclass
class ProcessingLog:
    """Log of processing for a single night/step."""

    night: str
    step: str  # 'science', 'dia', 'fphot', etc.
    timestamp: str
    configs_tried: list[ConfigAttempt] = field(default_factory=list)
    final_status: str = "pending"  # 'success', 'partial', 'failed'
    output_collection: str | None = None
    total_exposures: int = 0
    successful_exposures: int = 0
    started_at: str | None = None
    ended_at: str | None = None

    def add_attempt(self, attempt: ConfigAttempt) -> None:
        """Add a config attempt to the log."""
        self.configs_tried.append(attempt)

    def finalize(self) -> None:
        """Calculate final status based on attempts."""
        if not self.configs_tried:
            self.final_status = "failed"
            return

        # Count total successes across all attempts
        total_succeeded = sum(a.quanta_succeeded for a in self.configs_tried)
        total_failed = self.configs_tried[-1].quanta_failed  # Remaining failures

        if total_failed == 0 and total_succeeded > 0:
            self.final_status = "success"
        elif total_succeeded > 0:
            self.final_status = "partial"
        else:
            self.final_status = "failed"

        self.successful_exposures = total_succeeded
        self.ended_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "night": self.night,
            "step": self.step,
            "timestamp": self.timestamp,
            "configs_tried": [asdict(c) for c in self.configs_tried],
            "final_status": self.final_status,
            "output_collection": self.output_collection,
            "total_exposures": self.total_exposures,
            "successful_exposures": self.successful_exposures,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProcessingLog:
        """Create from dictionary."""
        configs = [ConfigAttempt(**c) for c in data.get("configs_tried", [])]
        return cls(
            night=data["night"],
            step=data["step"],
            timestamp=data["timestamp"],
            configs_tried=configs,
            final_status=data.get("final_status", "pending"),
            output_collection=data.get("output_collection"),
            total_exposures=data.get("total_exposures", 0),
            successful_exposures=data.get("successful_exposures", 0),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
        )


def get_log_dir(config: Config) -> Path:
    """Get the processing log directory for a repository."""
    log_dir = config.repo / "processing_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_path(config: Config, night: str, step: str) -> Path:
    """Get the log file path for a specific night/step."""
    return get_log_dir(config) / f"{night}_{step}.json"


def save_log(plog: ProcessingLog, config: Config) -> Path:
    """Save processing log to JSON file.

    Args:
        plog: Processing log to save
        config: Pipeline configuration

    Returns:
        Path to saved log file
    """
    log_path = get_log_path(config, plog.night, plog.step)
    with open(log_path, "w") as f:
        json.dump(plog.to_dict(), f, indent=2)
    log.debug(f"Saved processing log: {log_path}")
    return log_path


def load_log(config: Config, night: str, step: str) -> ProcessingLog | None:
    """Load processing log from JSON file.

    Args:
        config: Pipeline configuration
        night: Observing night
        step: Processing step name

    Returns:
        ProcessingLog if file exists, None otherwise
    """
    log_path = get_log_path(config, night, step)
    if not log_path.exists():
        return None

    with open(log_path) as f:
        data = json.load(f)
    return ProcessingLog.from_dict(data)


def create_log(night: str, step: str) -> ProcessingLog:
    """Create a new processing log.

    Args:
        night: Observing night
        step: Processing step name

    Returns:
        New ProcessingLog instance
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ProcessingLog(
        night=night,
        step=step,
        timestamp=timestamp,
        started_at=timestamp,
    )


def parse_pipetask_failures(stderr: str, stdout: str) -> list[dict]:
    """Parse pipetask output to extract failed exposures.

    Args:
        stderr: Standard error from pipetask
        stdout: Standard output from pipetask

    Returns:
        List of dicts with exposure_id and error message
    """
    failures = []
    combined = f"{stdout}\n{stderr}"

    # Look for quantum failure patterns in pipetask output
    # Common patterns:
    # - "Execution of quantum ... failed"
    # - "Exception ... for dataId={exposure: 12345, ...}"
    # - "Failed to execute"

    import re

    # Pattern for exposure IDs in error messages
    exposure_pattern = re.compile(r"exposure[=:\s]+(\d+)", re.IGNORECASE)
    error_pattern = re.compile(r"(Error|Exception|Failed|failure).*", re.IGNORECASE)

    # Split into chunks around error keywords
    lines = combined.split("\n")
    current_exposure = None
    current_error = None

    for line in lines:
        # Look for exposure ID
        exp_match = exposure_pattern.search(line)
        if exp_match:
            current_exposure = int(exp_match.group(1))

        # Look for error message
        err_match = error_pattern.search(line)
        if err_match:
            current_error = line.strip()

        # If we have both, record and reset
        if current_exposure and current_error:
            failures.append(
                {
                    "exposure_id": current_exposure,
                    "error": current_error[:200],  # Truncate long errors
                }
            )
            current_exposure = None
            current_error = None

    return failures
