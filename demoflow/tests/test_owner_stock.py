"""OwnerStock — the ED DENOMINATOR (spec §7 r3-F3), and the doors that must not read
`missing` as `zero`.

WHAT IS PLAN-VERBATIM AND WHAT IS RE-DERIVED, so a reviewer never has to guess:

  * `test_owner_stock_all_age_pit_fixed_equation` is the plan's Task-26 body, unchanged. Note
    that BOTH its ages (70, 80) carry BOTH rates — which is exactly why it never exercised the
    missing-rate door and why the plan's second body could assert the defect unnoticed.

  * The plan's `test_owner_stock_ignores_ages_without_rates` (age 40, population 1,000, EMPTY
    rate dicts, expected 0.0) is REPLACED, on the seat carry. It asserted the "missing is not
    zero" defect the Task-25 review already raised and `demand/formation.py` already resolved
    for the SAME two curves — and here the direction is worse: OwnerStock is the DENOMINATOR,
    so a silently-shrunk stock INFLATES excess demand, the very quantity the rankings rank on.
    Demand shrinking quietly is bad; the denominator shrinking quietly moves every ranking row
    in the optimistic direction. Its replacement carries BOTH arms — the hole RAISES, the
    documented sub-floor CONVENTION still contributes zero — so a future reader can tell which
    silence is which.

  * Everything else is added, and each test names the silent failure it kills.
"""
import math

import pytest

from demoflow.balance.owner_stock import OWNERSHIP_LATTICE_FLOOR, owner_stock
from demoflow.demand import formation
from demoflow.errors import LoaderError
from demoflow.loaders import census


# --- the plan's contract test (Task 26, verbatim) -------------------------------------

def test_owner_stock_all_age_pit_fixed_equation():
    # OwnerStock = Σ_a pop(a) * headship(a) * ownership(a)
    # 1000*0.6*0.65 + 500*0.7*0.60 = 390 + 210 = 600.
    s = owner_stock(
        pop_by_age={70: 1000.0, 80: 500.0},
        headship_by_age={70: 0.6, 80: 0.7},
        ownership_by_age={70: 0.65, 80: 0.60},
    )
    assert s == pytest.approx(600.0)


# --- the re-derived door (replaces `test_owner_stock_ignores_ages_without_rates`) ------

def test_missing_ownership_AT_OR_ABOVE_the_floor_raises_rather_than_shrinking_the_DENOMINATOR():
    """A hole in the ownership curve must be LOUD — here more than anywhere else in the tree.

    The curve below demonstrably HAS rates at that lattice height (50), so "undefined below
    the Census floor" cannot explain the absence at 40: the curve is holed. Under the plan's
    `.get(a, 0.0)` this call returns 0.0 — and 0.0 is not even a survivable denominator, so
    the r9-F5 guard would catch THAT one. The dangerous shape is the partial hole: a real
    curve missing a few ages still returns a plausible four-digit stock, every intermediate
    value a plausible float, and ED comes out too HIGH with nothing downstream able to notice.
    Both are the same defect; only one of them announces itself.
    """
    with pytest.raises(LoaderError, match="ownership"):
        owner_stock(pop_by_age={40: 1000.0}, headship_by_age={40: 0.6},
                    ownership_by_age={50: 0.65})

    # the partial hole, priced: the same stock with the age-40 rate present is 260 higher.
    dense = dict(pop_by_age={40: 1000.0, 50: 1000.0},
                 headship_by_age={40: 0.6, 50: 0.6}, ownership_by_age={40: 0.65, 50: 0.65})
    assert owner_stock(**dense) == pytest.approx(780.0)
    with pytest.raises(LoaderError, match="ownership"):
        owner_stock(**(dense | {"ownership_by_age": {50: 0.65}}))


@pytest.mark.parametrize("age", list(range(0, OWNERSHIP_LATTICE_FLOOR)))
def test_ownership_absent_BELOW_the_census_lattice_floor_contributes_nothing(age):
    """The OTHER arm: below the Census lattice the absence is a CONVENTION, not a hole.

    98-10-0231-01 publishes no owner-maintainer rate below 25, so `ownership(a)` is UNDEFINED
    there and the term contributes nothing. That convention is not decided here — it is
    `census.py`'s own `zero_support_note` (T13b 2026-08-08), which names THIS equation as the
    consumer it is stated for: "spec:395 sums pop(a) x headship(a) x ownership(a) over ages ...
    every consumer today pairs it with ownership(a) — undefined, hence contributing nothing,
    below the ownership lattice's floor of 25". The Task-29 pipeline sketch builds ownership
    over `range(25, 101)` against a population running 0..100, so EVERY run takes this path at
    all twenty-five sub-floor ages — not at some boundary corner.

    Parametrized over all twenty-five because the convention is identical at each and a test
    that pins only one leaves the rest free to change under it. The second arm pins that a rate
    which IS supplied sub-floor is still USED, so the convention can never swallow a curve
    someone extended downward; the third pins that it is also ASSERTED, which is what scopes
    the convention to ABSENCE and never to a bad value.
    """
    supplied = dict(pop_by_age={age: 1000.0}, headship_by_age={age: 0.5})

    assert owner_stock(**supplied, ownership_by_age={40: 0.65}) == 0.0
    assert owner_stock(**supplied, ownership_by_age={age: 0.55}) == pytest.approx(275.0)
    with pytest.raises(LoaderError, match=rf"ownership\[{age}\]"):
        owner_stock(**supplied, ownership_by_age={age: 1.5})


def test_the_floor_is_a_hard_numeric_edge_at_24_vs_25():
    """The convention's own boundary, adjacent ages, identical shapes — 24 is silence, 25 is a
    hole. Stated as one test because "below the floor" and "at the floor" are the same sentence
    read twice, and a reader should see the two verdicts side by side."""
    below = dict(pop_by_age={24: 1000.0}, headship_by_age={24: 0.5}, ownership_by_age={})
    at = dict(pop_by_age={25: 1000.0}, headship_by_age={25: 0.5}, ownership_by_age={})

    assert owner_stock(**below) == 0.0
    with pytest.raises(LoaderError, match="ownership"):
        owner_stock(**at)


def test_the_ownership_floor_is_the_demand_packages_constant_and_the_census_lattices():
    """ONE model-side declaration, pinned to the table that defines it — not a third literal.

    `formation.py` duplicates the number rather than importing it, for a stated reason: it
    keeps the demand package free of the CENSUS BAND TABLE (the same discipline as
    `living_arrangement._QC_CMAS` vs `census._QC_CMAS`). That reason does not extend to this
    import: balance→demand is model→model, in the direction `balance` already consumes (ED's
    numerator IS `formation`'s D), so importing costs no loaders coupling and no cycle. A third
    literal would be three drift sites held together by pairwise pins. The chain is asserted
    end to end here anyway, so this file is self-sufficient about what floor it is testing.
    """
    assert OWNERSHIP_LATTICE_FLOOR is formation.OWNERSHIP_LATTICE_FLOOR
    assert OWNERSHIP_LATTICE_FLOOR == min(lo for _label, lo, _hi in census._AGE_BANDS)


# --- the other door: headship ----------------------------------------------------------

@pytest.mark.parametrize("age,ownership_by_age", [
    (40, {40: 0.65}),      # at/above the floor: the term is real and gets deleted
    (10, {}),              # sub-floor: the term is zero anyway — the guard still fires
    (40, {}),              # BOTH curves holed at/above the floor: headship is the message
    (10, {10: 1.5}),       # BOTH defective SUB-floor (present + out-of-unit): same verdict
])
def test_missing_headship_at_a_POPULATED_age_raises(age, ownership_by_age):
    """Headship absence is a HOLE at EVERY age, with no convention to excuse it.

    The committed headship curve is banded across 0-100 (`census._HEADSHIP_BAND_SPEC`: 0-19,
    20-34, 35-54, 55-64, 65-74, 75+) and the Task-29 sketch materialises it over
    `range(0, 101)` — so unlike ownership, headship has no undefined region to point at, and a
    missing rate can only mean a holed or partially-built curve.

    The sub-floor case is strict because the CALL IS UNCONDITIONAL, not because of where it
    sits in the loop: `owner_stock` asks for headship at every populated age, and `_ownership`
    returns 0.0 sub-floor rather than skipping the term, so swapping the two guard calls
    changes nothing about which inputs raise. A caller whose headship curve is holed at age 10
    has a defective curve whatever ownership does at 10, and the alternative reading — "the
    term is zero anyway, so don't ask" — would make this guard's reach depend on the OTHER
    curve's silence. That is the class this whole file exists to refuse.

    THE LAST TWO CASES ARE THE ONE THING THE CALL ORDER DOES DECIDE: whenever both guards would
    independently raise at the SAME populated age, either message is available and the shipped
    order surfaces headship's — the curve with no legitimate excuse at any age. Without them a
    guard-order-swapped `owner_stock` passes this entire suite, which is how three durable
    sentences claiming the ORDER did the work went unchecked until the run-22 review caught
    them. Neither ownership message contains "headship", so `match=` discriminates.

    CASE 4 IS WHY THAT SET IS NOT "AT OR ABOVE THE FLOOR" — the narrowing the run-24 review
    caught, measured on a swapped replica. Below the floor an ABSENT ownership rate is the
    convention and no defect (case 2 is order-free for exactly that reason), but a PRESENT
    out-of-unit one is asserted at every age, so at 10 it collides with a holed headship
    exactly as a missing rate does at 40. Case 3 pinned the collision only above the floor and
    left the sub-floor half free to drift under a sentence that claimed it could not happen.
    """
    with pytest.raises(LoaderError, match="headship"):
        owner_stock(pop_by_age={age: 1000.0}, headship_by_age={},
                    ownership_by_age=ownership_by_age)


def test_a_ZERO_population_needs_no_rates_at_all():
    """The carve-out `_households` already makes, for the same reason: where the population is
    zero the term is zero whatever the rates are, so demanding a rate would red on perfectly
    good input (an empty cell at the top of the lattice is a legitimate reading, and the ISQ
    frame carries plenty). Absence of a POPULATION cell is likewise not a hole here — unlike
    `formation`'s a−1 leg, no gain is measured against a prior stock, so an age simply not in
    the frame contributes nothing and needs nothing."""
    assert owner_stock(pop_by_age={40: 0.0}, headship_by_age={}, ownership_by_age={}) == 0.0
    assert owner_stock(pop_by_age={}, headship_by_age={}, ownership_by_age={}) == 0.0


# --- the numeric doors ------------------------------------------------------------------

@pytest.mark.parametrize("pop,match", [
    (float("nan"), "non-finite"),
    (float("inf"), "non-finite"),
    (-1000.0, "negative"),
])
def test_a_NON_FINITE_or_NEGATIVE_population_cell_is_refused_HERE(pop, match):
    """Both halves fail SILENTLY downstream, and this is the last place either is visible.

    NaN: it does not vanish from this sum (that is `formation`'s mechanism, where a NaN gain
    fails a `> 0` test) — it PROPAGATES to a NaN OwnerStock, and `NaN < MIN_OWNER_STOCK` is
    False, so the r9-F5 denominator guard passes it straight through and a NaN ED is emitted.
    `test_excess_demand.py` asserts that comparison rule directly rather than describing it.

    NEGATIVE: this module diverges from `formation`'s "P_resident ≥ 0 is asserted upstream"
    stance deliberately, because the position is different — this is the DENOMINATOR, where a
    negative cell SHRINKS the stock and INFLATES ED, the ranked quantity (`validate.py`'s
    `assert_nonneg_finite` names stocks in its own docstring). ISQ populations are already
    refused negative at load; this refuses one arriving by any other door.
    """
    with pytest.raises(LoaderError, match=match):
        owner_stock(pop_by_age={70: pop}, headship_by_age={70: 0.6},
                    ownership_by_age={70: 0.65})


@pytest.mark.parametrize("headship,ownership,match", [
    (1.2, 0.65, r"headship\[70\]"),
    (0.6, 1.5, r"ownership\[70\]"),
    (-0.1, 0.65, r"headship\[70\]"),
    (0.6, float("nan"), r"ownership\[70\]"),
])
def test_out_of_unit_rates_in_a_hand_built_curve_raise(headship, ownership, match):
    """A curve assembled by hand (fixtures, a sweep, a future caller) is not loader-checked,
    and this function takes plain dicts. A rate above 1 inflates the denominator and DEFLATES
    ED; the assertions are the same `assert_fraction` the loaders apply, re-applied at the use
    site — same discipline as `native_formation`."""
    with pytest.raises(LoaderError, match=match):
        owner_stock(pop_by_age={70: 1000.0}, headship_by_age={70: headship},
                    ownership_by_age={70: ownership})


# --- the spec property the sum must NOT inherit from D ----------------------------------

def test_the_sum_runs_over_ALL_AGES_including_75plus():
    """§7's denominator is `Σ_over_all_ages`, and the 75+ terms are IN it.

    Worth its own test because the neighbouring equation says the opposite: `native_formation`
    stops at 75 by design (D/S disjointness at the age boundary — 75+ dynamics live in S), so
    an implementer carrying that rule one module over would truncate the denominator and
    inflate every ED. The spec closes it explicitly: this is a stock LEVEL estimate, ISQ-
    embedded mortality is correct here, and I1 governs only the 75+ exit FLOW model.
    """
    assert formation.AGE_BOUNDARY == 75          # the rule that must NOT be inherited
    s = owner_stock(pop_by_age={90: 1000.0}, headship_by_age={90: 0.8},
                    ownership_by_age={90: 0.7})
    assert s == pytest.approx(560.0)
    assert math.isfinite(s) and s > 0.0
