from pathlib import Path

import pytest
from actuarial.compat import active_mortality, get_qx, set_active_mortality

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P1-actuarial-cross-env.md"


def test_p1_observation_recorded():
    assert NOTE.exists(), "run probes/run_p1.py first"


def test_qc_basis_qx_matches_skeleton_oracle():
    set_active_mortality("CPM2014_combined", "CPM-B")
    assert active_mortality() == ("CPM2014_combined", "CPM-B")
    assert get_qx(75, "M", 2035) == pytest.approx(0.0156, abs=5e-4)
    assert get_qx(75, "F", 2035) == pytest.approx(0.0115, abs=5e-4)


def test_get_qx_rejects_bad_gender():
    set_active_mortality("CPM2014_combined", "CPM-B")
    with pytest.raises(ValueError):
        get_qx(75, "male", 2035)
