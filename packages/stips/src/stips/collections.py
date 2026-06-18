"""Butler collection-name builder, parameterized by instrument collection prefix."""

from __future__ import annotations

from datetime import datetime, timezone


def generate_run_timestamp() -> str:
    """Generate a UTC timestamp for collection naming."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class CollectionNames:
    """Generate standard collection names for a pipeline run."""

    # NOTE: the prefix="Nickel" default is a transitional back-compat scaffold;
    # it is removed in the final Phase-2b task (Task 10) once all call sites pass
    # the prefix explicitly.
    def __init__(self, night: str, run_ts: str | None = None, prefix: str = "Nickel"):
        self.night = night
        self.run_ts = run_ts or generate_run_timestamp()
        self.prefix = prefix

    # Raw data
    @property
    def raw_run(self) -> str:
        return f"{self.prefix}/raw/{self.night}/{self.run_ts}"

    # Calibration products
    @property
    def cp_bias(self) -> str:
        return f"{self.prefix}/cp/{self.night}/bias/{self.run_ts}"

    @property
    def cp_bias_run(self) -> str:
        return f"{self.cp_bias}/run"

    @property
    def cp_flat(self) -> str:
        return f"{self.prefix}/cp/{self.night}/flat/{self.run_ts}"

    @property
    def cp_flat_run(self) -> str:
        return f"{self.cp_flat}/run"

    @property
    def curated_run(self) -> str:
        return f"{self.prefix}/calib/curated/{self.run_ts}"

    @property
    def curated_chain(self) -> str:
        return f"{self.prefix}/calib/curated"

    @property
    def calib_out(self) -> str:
        return f"{self.prefix}/calib/{self.night}"

    @property
    def calib_chain(self) -> str:
        return f"{self.prefix}/calib/current"

    # Science processing
    @property
    def science_parent(self) -> str:
        return f"{self.prefix}/runs/{self.night}/processCcd/{self.run_ts}"

    @property
    def science_run(self) -> str:
        return f"{self.science_parent}/run"

    @property
    def coadd_parent(self) -> str:
        return f"{self.prefix}/runs/{self.night}/coadd/{self.run_ts}"

    @property
    def coadd_run(self) -> str:
        return f"{self.coadd_parent}/run"

    # Difference imaging
    @property
    def diff_parent(self) -> str:
        return f"{self.prefix}/runs/{self.night}/diff/{self.run_ts}"

    @property
    def diff_run(self) -> str:
        return f"{self.diff_parent}/run"
