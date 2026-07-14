"""Framework-provided test harness for instrument profiles.

``stips.testing.instrument_contract`` is a real importable module (not a pytest
conftest) so instrument test dirs and the auto-discovered contract module can
import it explicitly -- no ambient ``conftest`` resolution, no sys.path games.
"""
