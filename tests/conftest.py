"""Suite-wide fixtures."""
import pytest

from hde import rate_paths


@pytest.fixture(autouse=True)
def _fresh_rate_path_pins():
    """A renewal-rate path file's sha256 is pinned per process (R19 of
    docs/specs/2026-10-01-renewal-rate-path-file.md); every test starts with
    none pinned, so a test that rewrites a file cannot trip another."""
    rate_paths.reset_pins()
    yield
    rate_paths.reset_pins()
