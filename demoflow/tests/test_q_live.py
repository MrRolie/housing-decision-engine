"""q_live annualization contract (spec §5 "Living-exit calibration", Invariant I3).

I3 in one line: `q_live` is the SURVIVOR-CONDITIONAL living-sale hazard, anchored to CMHC
36%/5yr (75+, QC) → `1−(1−0.36)^(1/5)`, band [0.06, 0.11]/yr. The Myers all-cause retention
numbers (0.26–0.31 over a decade) are a SANITY CHECK ONLY and are NEVER a calibration target
for this hazard — they include death, so calibrating q_live to them double-counts mortality.

WHERE THE DRIFT GUARDS LIVE (measured design call, ADDED beyond the plan's two bodies):
`decrements.py` keeps the spec's literals (0.36, (0.06, 0.11)) rather than importing
`demoflow.loaders.constants` — MEASURED: that import pulls pandas transitively via
`loaders/validate.py`, so a pure-arithmetic cohort module would drag the I/O layer's
dependency into its import graph, and neither sibling from this task set (`cohort/basis.py`,
`cohort/init.py`) imports loaders. The single-source rule constants.py states ("a second
declaration site is a defect") is honored HERE instead: every literal in the implementation
is pinned against its anchor below, so a CMHC refresh (spec §7c names one) landing in
constants.py while `decrements.py` keeps a stale literal FAILS this file. Test-side
enforcement, production-side isolation — same detection, no coupling.
"""

import math

import pytest

from demoflow.cohort.decrements import annualize_q_live, Q_LIVE_BAND
from demoflow.errors import CalibrationError
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS, CONSTANTS, SWEEP_GRID


# ---------------------------------------------------------------- plan bodies (verbatim)

def test_annualize_cmhc_36pct_5yr_is_about_8_5pct():
    # 1 - (1 - 0.36)^(1/5) ~= 0.0854 (spec §5 / I3)
    assert annualize_q_live(0.36) == pytest.approx(0.0854, abs=1e-3)


def test_annualized_value_in_band():
    q = annualize_q_live(0.36)
    assert Q_LIVE_BAND[0] <= q <= Q_LIVE_BAND[1]   # [0.06, 0.11]


# ------------------------------------------------------- ADDED: drift + domain enforcement

def test_exact_value_and_the_pinned_anchor_agree_at_the_anchor_s_precision():
    """The plan's `abs=1e-3` tolerance admits a wrong FORMULA: naive simple division
    (0.36/5 = 0.072) is 0.0134 off and caught, but this pins the exact IEEE value so any
    re-derivation is visible, and ties it to the anchor at the anchor's own precision.

    UNITS NOTE (the reason `q_live_five_year` was deleted from constants.py): 0.36 is a
    FIVE-YEAR rate and carries NO band; the [0.06, 0.11] band belongs to the ANNUAL rate.
    A tripwire comparing the 5-year figure against the annual band fires crossed forever.
    """
    q = annualize_q_live(0.36)
    # Measured exact on this interpreter: 0.08538989614534731. Pinned at rel=1e-12 rather
    # than bit-equality — a fractional-exponent `pow` is libm-dependent and this branch runs
    # on more than one box. MEASURED to keep full kill power: the three mutants this assert
    # catches land at 0.072 / 0.04405 / 0.085, the nearest 4.6e-3 relative — nine orders of
    # magnitude above the tolerance, so the looseness buys portability and costs no rigor.
    assert q == pytest.approx(0.08538989614534731, rel=1e-12)
    assert round(q, 3) == CONSTANTS["q_live_annual"].value  # 0.085 — the anchor's precision
    assert CONSTANTS["cmhc_senior_sale_5yr"].band is None   # the 5-yr figure is unbanded


def test_the_run_s_hash_covered_central_value_is_the_anchor_not_this_float():
    """FORWARD HAZARD, fenced here (spec §7 identity envelope): `assumptions_hash()` covers
    `CENTRAL_ASSUMPTIONS["q_live_per_year"]` = 0.085, while this function returns 0.0853899.
    A consumer that feeds `annualize_q_live(0.36)` straight into the roll-forward moves the
    run's numbers by 3.9e-4/yr while the hash stays byte-identical. The two agree only after
    rounding to the anchor's 3 decimals — asserted so the gap is a KNOWN quantity, not a
    surprise: the hash-covered run value is the anchor; this function derives it.
    """
    central = CENTRAL_ASSUMPTIONS["q_live_per_year"]
    assert central == CONSTANTS["q_live_annual"].value      # single source, already locked
    assert annualize_q_live(0.36) != central                # they are NOT the same float
    assert math.isclose(annualize_q_live(0.36), central, abs_tol=5e-4)


def test_default_argument_tracks_the_cmhc_anchor():
    """Staleness guard for the refresh spec §7c schedules ("CMHC senior-sale-rate refresh"):
    the module's default and the anchor must name the SAME rate, so a refreshed anchor with a
    stale literal here fails. Non-vacuous today, not merely armed for the refresh — MEASURED:
    a `five_year_rate: float = 0.30` mutant is killed by this test and by no other in the file.
    """
    assert annualize_q_live() == annualize_q_live(CONSTANTS["cmhc_senior_sale_5yr"].value)
    assert CONSTANTS["cmhc_senior_sale_5yr"].value == 0.36   # the vintage this file pins


def test_band_is_the_anchor_s_band_and_the_sweep_grid_s_endpoints():
    """Three declaration sites for one band — module literal, anchor, sweep grid — bound
    together so any one drifting fails loudly. I3 guard on the last two asserts: the Myers
    envelope must never become this band.
    """
    assert Q_LIVE_BAND == (0.06, 0.11)                              # spec §5
    assert Q_LIVE_BAND == CONSTANTS["q_live_annual"].band
    assert Q_LIVE_BAND == SWEEP_GRID["q_live_per_year"]             # endpoints sweep, not headline
    myers = CONSTANTS["myers_retention_envelope"].value             # (0.26, 0.31), ALL-CAUSE/decade
    assert Q_LIVE_BAND != myers                                     # I3: never interchangeable
    lo, hi = myers
    assert not lo <= annualize_q_live(0.36) <= hi                   # different quantity entirely


def test_out_of_domain_raises_before_the_complex_branch():
    """The domain guard is LOAD-BEARING, not decoration — MEASURED: Python returns a COMPLEX
    number for a negative base with a fractional exponent, silently.
    `(1.0 - 1.2) ** 0.2` == (0.5863590650926145+0.4260147974712481j) — no exception. Without
    the guard a >1 rate yields a complex "hazard" that propagates into the roll-forward.
    NaN is covered by the same comparison (every ordering against NaN is False).
    """
    assert isinstance((1.0 - 1.2) ** 0.2, complex)   # the branch the guard exists to block

    for bad in (1.2, 1.0, -0.01, float("nan"), float("inf")):
        with pytest.raises(CalibrationError):
            annualize_q_live(bad)

    with pytest.raises(CalibrationError, match="1.2"):   # the message names the offender
        annualize_q_live(1.2)

    q = annualize_q_live(0.36)
    assert isinstance(q, float) and not isinstance(q, complex)  # the valid path stays real


def test_boundary_and_monotonicity():
    """0.0 is IN domain (a cohort that never sells → zero hazard); 1.0 is OUT by the strict
    upper bound — a certain 5-year sale is a data defect, not a calibration input.

    THE TWO DOMAINS IN `decrements.py` DIFFER ON PURPOSE, and neither is the other's typo:
    `annualize_q_live` guards `[0,1)` — this test's side — while `_check_unit` guards the
    branch probabilities on an INCLUSIVE `[0,1]`, fenced from its own side by
    test_partition.py::test_check_unit_domain_is_inclusive_and_rejects_nonfinite. The
    inclusive bound is NECESSARY, not merely permissive: the live engine returns EXACTLY 1.0
    at its terminal age (`q_at(120, "M", 2035) == 1.0`, short-circuited before any table
    lookup), so a strict `< 1.0` on branch probabilities would refuse a real mortality value on
    a path the roll-forward can reach — its upper age end is deliberately unbounded. That is an
    ASSERTION, not a recollection: test_rollforward.py::test_roll_one_year_guards_its_own_age_domain
    pins both the terminal 1.0 and the age-120 roll it feeds, so an engine that stops returning
    1.0 breaks there rather than quietly invalidating this paragraph. A "harmonization" of the
    two guards breaks one of the pair whichever way it is done, and both fences exist so that it
    breaks loudly rather than silently admitting the degenerate rate here.
    """
    assert annualize_q_live(0.0) == 0.0
    with pytest.raises(CalibrationError):
        annualize_q_live(1.0)
    # strictly increasing in the 5-year rate — a survivor-conditional hazard cannot fall
    # as the 5-year sale rate rises
    rates = [0.0, 0.1, 0.26, 0.36, 0.45, 0.9]
    annuals = [annualize_q_live(r) for r in rates]
    assert annuals == sorted(annuals) and len(set(annuals)) == len(annuals)
