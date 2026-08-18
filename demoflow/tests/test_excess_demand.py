"""The excess-demand fraction (spec §7, codex F4) — the hand-worked fixture, the r9-F5
denominator boundary, and the guards that keep an UNBOUNDED fraction from being emitted.

The first two tests are the plan's Task-26 bodies, unchanged (the boundary triple 999 / 1000 /
1001 is the spec's own fixture set and stays verbatim). Everything below `# --- added guards`
is added; each names the silent failure it kills, and the two structural ones follow
`cohort/listings.py`'s precedent for adding a guard beyond a plan body — the rejected shapes
are silently wrong rather than loudly wrong.

TRANCHE 1 STOPS HERE, at the raw fraction. The ED→drift mapping (β, `balance/mapping.py`) is
Tranche 2 and is gated on the S4b input-slot sketch: nothing in this file or its module
scaffolds toward it.
"""
import math

import pytest

from demoflow.balance.excess_demand import MIN_OWNER_STOCK, excess_demand
from demoflow.cohort.listings import market_listings
from demoflow.demand.formation import total_owner_demand
from demoflow.errors import CalibrationError


# --- the plan's contract tests (Task 26, verbatim) ------------------------------------

def test_hand_worked_ed_with_estate_lag_boundary_crossing():
    # ED(g,t,s) = [D - S] / OwnerStock, all annual, household-denominated (spec §7).
    # D = native 200 + immigrant 50 = 250.
    # S = voluntary(2035)=40*0.9=36  +  estate(2034)=100 lists in 2035 at 0.75 = 75  => 111.
    #     (estate-lag boundary crossing: 2034 death -> 2035 listing; explicit non-central params).
    # OwnerStock(2035) = 5000.  ED = (250 - 111) / 5000 = 139/5000 = 0.0278.
    D = total_owner_demand(native=200.0, immigrant=50.0)
    S = market_listings(voluntary_by_year={2035: 40.0}, estate_by_year={2034: 100.0},
                        lag=1, eventual_fraction=0.75)[2035]
    assert S == pytest.approx(111.0)
    ed = excess_demand(D=D, S=S, owner_stock=5000.0)
    assert ed == pytest.approx(0.0278, abs=1e-6)


def test_owner_stock_numeric_boundary_999_1000_1001():
    # codex r9-F5: OwnerStock < 1,000 households raises (never leave "near-zero" to taste).
    assert MIN_OWNER_STOCK == 1000.0
    with pytest.raises(CalibrationError, match="1000|OwnerStock"):
        excess_demand(D=10.0, S=5.0, owner_stock=999.0)
    excess_demand(D=10.0, S=5.0, owner_stock=1000.0)    # boundary: allowed (>= 1000)
    excess_demand(D=10.0, S=5.0, owner_stock=1001.0)


# --- added guards -----------------------------------------------------------------------

def test_the_r9_F5_guard_CANNOT_see_a_non_finite_denominator_on_its_own():
    """The measured hole the finiteness check exists to close — asserted, not described.

    Every ordering against NaN is False (the same comparison rule `cohort/decrements` relies
    on), so a NaN OwnerStock walks straight through `owner_stock < MIN_OWNER_STOCK` and the
    spec's "never emit an unbounded fraction" is violated by the very guard written to enforce
    it. An INFINITE stock is the mirror: it passes the `<` compare honestly and divides to a
    flat 0.0 — a perfectly balanced market, reported with no trace of the input that produced
    it. This test pins the comparison rule itself, so the two checks in `excess_demand` can
    never be "simplified" back into one. What the assertions below pin is the SEPARATENESS of
    the finiteness check, not its position: neither NaN nor +inf can trip `<
    MIN_OWNER_STOCK` at all, so the magnitude compare could not preempt it whichever ran
    first — collapsing the pair is the regression, reordering it is not.
    """
    assert not (float("nan") < MIN_OWNER_STOCK)
    assert not (float("inf") < MIN_OWNER_STOCK)
    assert math.isnan((250.0 - 111.0) / float("nan"))
    assert (250.0 - 111.0) / float("inf") == 0.0


@pytest.mark.parametrize("stock", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_OwnerStock_raises_instead_of_emitting_an_unbounded_fraction(stock):
    with pytest.raises(CalibrationError, match="OwnerStock"):
        excess_demand(D=250.0, S=111.0, owner_stock=stock)


@pytest.mark.parametrize("D,S,match", [
    (float("nan"), 111.0, r"\bD\b"),        # word-boundary: the message names WHICH term,
    (250.0, float("nan"), r"\bS\b"),        # and a loose "D" would also match "demand"
    (float("inf"), 111.0, r"\bD\b"),
    (250.0, float("-inf"), r"\bS\b"),
])
def test_a_non_finite_NUMERATOR_term_raises_here_rather_than_at_the_emitter(D, S, match):
    """The numerator has a LIVE door today: `market_listings` asserts its lag and its
    eventual-listing fraction, but never the exit COUNTS — a NaN estate count convolves into a
    NaN S and arrives here as an ordinary float argument. Spec §7's emitter does refuse
    non-finite output (`allow_nan=False`), but only if the NaN survives to it, and ED is the
    last arithmetic before the artifact. Caught at the boundary that can still name WHICH term
    was bad; downstream all that is left is a NaN row.
    """
    with pytest.raises(CalibrationError, match=match):
        excess_demand(D=D, S=S, owner_stock=5000.0)


def test_a_NEGATIVE_ED_is_legitimate_and_must_never_be_clamped():
    """Excess SUPPLY is a real reading, not an error: S > D means more owner households are
    listing than forming. The spec's Tranche-2 mapping handles the sign explicitly ("reversed
    for ED < 0"), so a floor at zero here would silently delete the entire downside half of the
    ranked signal — the direction a demographic-decline model exists to measure."""
    assert excess_demand(D=111.0, S=250.0, owner_stock=5000.0) == pytest.approx(-0.0278,
                                                                                abs=1e-6)


def test_ED_is_scale_invariant():
    """Invariance to geography SIZE — the property that lets geographies of very different size
    be ranked against each other at all. Scaling all three terms by a common factor must not
    move the quotient; a stray absolute term added to either side would.

    NOT the same claim as "dimensionless", which is what this docstring used to say (corrected
    2026-08-15, spec §7 amendment #12): D and S are annual FLOWS over a stock LEVEL, so ED
    carries yr^-1 — a net turnover rate. The common factor below is a pure NUMBER, so this test
    exercises size-invariance and says nothing about the unit either way."""
    base = excess_demand(D=250.0, S=111.0, owner_stock=5000.0)
    for k in (0.5, 3.7, 100.0):
        assert excess_demand(D=250.0 * k, S=111.0 * k,
                             owner_stock=5000.0 * k) == pytest.approx(base)
