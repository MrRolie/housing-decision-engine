import hashlib
from pathlib import Path

import pytest

from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, verify_pin
from demoflow.errors import LoaderError


def test_committed_workbooks_match_pins():
    for name, expected in WORKBOOK_SHA256.items():
        digest = hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
        assert digest == expected, f"{name} drifted: {digest} != {expected}"


def test_verify_pin_raises_on_drift(tmp_path):
    bad = tmp_path / "pop-as-rmr-base.xlsx"
    bad.write_bytes(b"not the workbook")
    with pytest.raises(LoaderError, match="sha256"):
        verify_pin(bad, "pop-as-rmr-base.xlsx")


def test_verify_pin_raises_on_unregistered_name(tmp_path):
    """ADDED beyond the plan's two bodies: the plan's drift test matches on
    "sha256", which `re.search`-matches BOTH branch messages ("sha256 drift
    for ..." and "no sha256 pin registered for ..."). A typo'd key in
    WORKBOOK_SHA256 would therefore leave that test green while the raised
    reason is wrong. This pins the unregistered-name branch with a
    DISCRIMINATING match so the two fail-loud paths cannot be confused."""
    unpinned = tmp_path / "pop-as-mrc-base.xlsx"
    unpinned.write_bytes(b"a workbook with no pin registered")
    with pytest.raises(LoaderError, match="no sha256 pin registered"):
        verify_pin(unpinned, "pop-as-mrc-base.xlsx")
