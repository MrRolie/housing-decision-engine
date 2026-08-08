"""Reconciliation-gate contract (spec §5 "Reconciliation gate" — the AGGREGATE BACKSTOP
half of Invariant I1).

I1 in one line: ISQ population enters the owner roll-forward EXACTLY ONCE, at band entry.
This gate is the coarse half of enforcing that. Roll a 75+ owner cohort forward one decade;
all-cause retention (survivors still owning / initial) must land in [0.20, 0.40] — the Myers
0.26–0.31 all-cause envelope WIDENED. Outside → CalibrationError.

WHAT THE GATE DELIBERATELY DOES NOT DO (spec §5, codex r7-F5 — the reason this file pins the
band and nothing else): at q_live's low end a DOUBLED mortality decrement still retains ≈0.25,
INSIDE this band, so the envelope cannot carry exactly-once. That proof is the stock-flow
equation plus the roll-forward's ORACLE-EXACT mutation test, which asserts the double-decrement
strictly changes the hand-computed pinned values. This file therefore never asserts that the
band detects a double-count — asserting it would encode the exact false claim the spec fenced.

COMPOSITION CAVEAT, recorded not asserted (spec §5, codex r9-F4): retention is STATE-DEPENDENT,
so the band is only well-defined against a PINNED cohort mix — the one the initialization
equations produce on the committed vintage for MTL_RMR, with per-state Solo_m/Solo_f/Couple
retention paths additionally pinned in the oracle fixture. `check_reconciliation` takes a bare
float, so it cannot verify that obligation and no test here pretends to — the obligation is
discharged where the cohort is built, and it is flagged in `gates.py`'s docstring for the same
reason.

WHERE THE DRIFT GUARD LIVES (same call as `decrements.py`, and for the same measured reason):
`gates.py` keeps the band literal rather than importing `demoflow.loaders.constants`, because
that import pulls pandas transitively via `loaders/validate.py` and this module is pure
arithmetic. The band is ALREADY declared twice today — `CONSTANTS["reconciliation_band"]` holds
(0.20, 0.40) as an anchored constant — so the single-source rule constants.py states ("a second
declaration site is a defect") is honored TEST-SIDE here: the two sites are bound below, and the
derivation from the Myers envelope is bound with them. Test-side enforcement, production-side
isolation — same detection, no coupling.
"""

import math

import pytest

from demoflow.cohort.decrements import Q_LIVE_BAND
from demoflow.cohort.gates import RECONCILIATION_BAND, check_reconciliation
from demoflow.errors import CalibrationError
from demoflow.loaders.constants import CONSTANTS


# ---------------------------------------------------------------- plan bodies (verbatim)

def test_band_is_myers_widened():
    assert RECONCILIATION_BAND == (0.20, 0.40)


def test_in_band_passes():
    check_reconciliation(0.30)  # no raise


def test_below_band_raises():
    with pytest.raises(CalibrationError, match="reconciliation"):
        check_reconciliation(0.15)


def test_above_band_raises():
    with pytest.raises(CalibrationError, match="reconciliation"):
        check_reconciliation(0.45)


def test_closed_band_endpoints_pass():
    check_reconciliation(0.20)
    check_reconciliation(0.40)


# ------------------------------------------------------ ADDED: drift + fail-loud enforcement

def test_band_matches_its_anchor_and_strictly_widens_the_myers_envelope():
    """Two live declaration sites for one band, bound so either drifting fails loudly, plus
    the DERIVATION that makes the second site's number legitimate.

    "Widened" is not decoration: it is why a gate motivated by a 0.26–0.31 literature figure
    may legally pass 0.21. Asserted as STRICT containment on both ends — a "widening" that
    merely reproduced the Myers endpoints, or that widened one end only, would be a different
    gate than the spec ruled. The I3 separation asserts stay because the two bands are
    different QUANTITIES: Myers is all-cause retention over a decade, Q_LIVE_BAND is an annual
    survivor-conditional sale hazard, and a refresh that pointed this gate at either would be
    the exact interchange spec §5 forbids.
    """
    assert RECONCILIATION_BAND == CONSTANTS["reconciliation_band"].value

    myers_lo, myers_hi = CONSTANTS["myers_retention_envelope"].value
    assert (myers_lo, myers_hi) == (0.26, 0.31)          # the vintage this file pins
    lo, hi = RECONCILIATION_BAND
    assert lo < myers_lo and myers_hi < hi               # STRICT containment, both ends
    assert RECONCILIATION_BAND != (myers_lo, myers_hi)   # I3: never the envelope itself
    assert RECONCILIATION_BAND != Q_LIVE_BAND            # I3: never the q_live band


def test_gate_signals_only_by_raising_never_by_return_value():
    """A gate that returned a verdict would be one `if check_reconciliation(r):` away from a
    silent all-clear — the caller's truthiness test on `None` never fires, in EITHER direction.
    Pinned so the signature cannot quietly become bool-returning.
    """
    assert check_reconciliation(0.30) is None


def test_non_finite_retention_raises_and_the_plausible_rewrite_would_not():
    """NaN is the fail-loud case with teeth. A roll-forward that divides 0.0 survivors by 0.0
    initial hands this gate a NaN, and a gate that PASSES NaN is a cheap all-clear.

    The single chained `lo <= x <= hi` comparison refuses NaN because every ordering against
    NaN is False, so the negation fires. The obvious rewrite — `x < lo or x > hi` — is False
    on both disjuncts and would pass NaN silently. Both conditions are evaluated inline below,
    so this test PROVES the divergence rather than asserting it from memory, and the rewrite is
    fenced by demonstration, not by comment.
    """
    nan = float("nan")
    lo, hi = RECONCILIATION_BAND
    assert not (lo <= nan <= hi)          # implemented condition -> negation raises
    assert not (nan < lo or nan > hi)     # the rewrite's condition -> would NOT raise

    for bad in (nan, math.inf, -math.inf):
        with pytest.raises(CalibrationError):
            check_reconciliation(bad)


def test_message_names_the_offending_value_and_the_band_is_closed_to_the_ulp():
    """Two properties one call apart.

    (a) The message must name the OFFENDER, not just the rule — a bare "outside band" makes a
    failing run undiagnosable. Asserted on the `.4f` render, not on the raw repr: note the band
    renders as `(0.2, 0.4)` (Python drops the trailing zero), so a match on the literal string
    "0.20" would be checking the offender's render and nothing else — spelled out so a future
    edit does not "fix" this assert into vacuity.

    (b) The band is CLOSED at exactly the pinned literals, not approximately: one ULP outside
    either endpoint raises, while the endpoints themselves pass (plan body above). Together
    they pin the comparison to the literal rather than to a rounded or epsilon-padded neighbour.
    """
    with pytest.raises(CalibrationError, match=r"retention 0\.1500 outside band"):
        check_reconciliation(0.15)
    assert repr(RECONCILIATION_BAND) == "(0.2, 0.4)"   # why (a) does not match on "0.20"

    lo, hi = RECONCILIATION_BAND
    for outside in (math.nextafter(lo, 0.0), math.nextafter(hi, 1.0)):
        with pytest.raises(CalibrationError):
            check_reconciliation(outside)
