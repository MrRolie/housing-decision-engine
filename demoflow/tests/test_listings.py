"""Transfer-vs-market split contract (spec §5 "Transfer-vs-market split", plan Task 24).

Exits carry cause; `phi_market(cause)` fractions with estate-lag convolution — voluntary exits
list promptly, death/estate exits convert to listings with lag L and an eventual-listing fraction.

WHY THE BINDING TEST BELOW IS A RELOAD AND NOT AN EQUALITY READ (the whole point of this file's
added half): `PHI_VOLUNTARY` / `ESTATE_EVENTUAL_FRACTION` / `ESTATE_LAG_YEARS` are RUN-CONTRACT
central values, and `assumptions_hash()` covers exactly what `CENTRAL_ASSUMPTIONS` holds — so a
literal redeclared in `listings.py` would move the run's numbers while the hash stayed
byte-identical, breaking spec §9's artifact identity. That defect is INVISIBLE to any equality
assertion: a literal `0.9` equals `CENTRAL_ASSUMPTIONS["phi_voluntary"]` today and passes every
read. The discriminating check MUTATES the dict, RELOADS the module, and asserts the module's
values MOVED — which only a read-through binding survives.

This inverts the call `decrements.py` and `gates.py` made (they keep their literals and are pinned
test-side, to avoid the pandas that `loaders/validate.py` pulls transitively). Those are BAND
literals with anchors in `CONSTANTS`, outside the hash payload; these three are the hash payload.
Same single-source rule, different enforcement, because the failure modes differ.
"""

import importlib

import pytest

from demoflow.cohort import listings as listings_mod
from demoflow.cohort.listings import (
    phi_market, market_listings, PHI_VOLUNTARY, ESTATE_EVENTUAL_FRACTION, ESTATE_LAG_YEARS,
)
from demoflow.errors import CalibrationError
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS, SWEEP_GRID


# ---------------------------------------------------------------- plan bodies (verbatim)

def test_phi_central_values():
    # RUN CONTRACT central values (codex r8-F1): voluntary 0.9, estate eventual 0.725, L=2.
    assert PHI_VOLUNTARY == 0.9 and 0.7 <= PHI_VOLUNTARY <= 1.0
    assert ESTATE_EVENTUAL_FRACTION == 0.725 and 0.6 <= ESTATE_EVENTUAL_FRACTION <= 0.85
    assert ESTATE_LAG_YEARS == 2 and ESTATE_LAG_YEARS in (1, 2, 3)
    assert phi_market("voluntary") == 0.9


def test_estate_lag_crosses_year_boundary():
    # 100 estate exits in 2034, L=1, fraction 0.75 -> 75 listings in 2035.
    # 40 voluntary exits in 2035 -> 40*0.9 = 36 listings in 2035.
    listings = market_listings(
        voluntary_by_year={2035: 40.0},
        estate_by_year={2034: 100.0},
        lag=1, eventual_fraction=0.75,
    )
    assert listings[2035] == pytest.approx(75.0 + 36.0)   # 111 total in 2035


def test_unknown_cause_raises():
    with pytest.raises(ValueError):
        phi_market("bequest_of_dragons")


# ------------------------------------------------------- added: the read-through binding guard

def test_central_values_are_bound_read_through_not_redeclared(monkeypatch):
    """THE DISCRIMINATING CHECK (seat carry, 2026-08-13). Mutate all three
    `CENTRAL_ASSUMPTIONS` entries, re-execute the module source, and assert every value MOVED.

    A `listings.py` that redeclares `PHI_VOLUNTARY = 0.9` re-executes to 0.9 under a mutated
    dict and fails here — which is exactly the hash-bypass defect the carry names. Both surfaces
    are asserted, because they bind at different moments and a fix could reach only one: the
    module ATTRIBUTES (import-time binding) and `market_listings`' DEFAULT PATH (signature
    defaults, bound at `def` time). The lag sentinel is 3, not the central 2, so the landing YEAR
    moves as well as the magnitudes — a stale lag would still land 2042 and fail the key lookup.
    """
    sentinels = {"phi_voluntary": 0.61, "estate_eventual_fraction": 0.53, "estate_lag_years": 3}
    for key, value in sentinels.items():
        monkeypatch.setitem(CENTRAL_ASSUMPTIONS, key, value)
    try:
        moved = importlib.reload(listings_mod)

        assert moved.PHI_VOLUNTARY == 0.61
        assert moved.ESTATE_EVENTUAL_FRACTION == 0.53
        assert moved.ESTATE_LAG_YEARS == 3
        assert moved.phi_market("voluntary") == 0.61
        assert moved.phi_market("estate") == 0.53

        # Default path (no lag / eventual_fraction passed) — what the headline run calls.
        out = moved.market_listings({2040: 100.0}, {2040: 100.0})
        assert out[2040] == pytest.approx(61.0)          # 100 * 0.61 voluntary
        assert out[2043] == pytest.approx(53.0)          # 100 * 0.53, landing at 2040 + lag 3
        assert 2042 not in out                           # the central lag of 2 did NOT survive
    finally:
        monkeypatch.undo()                # restore the dict BEFORE re-executing the module
        importlib.reload(listings_mod)

    assert listings_mod.PHI_VOLUNTARY == CENTRAL_ASSUMPTIONS["phi_voluntary"]
    assert listings_mod.ESTATE_EVENTUAL_FRACTION == CENTRAL_ASSUMPTIONS["estate_eventual_fraction"]
    assert listings_mod.ESTATE_LAG_YEARS == CENTRAL_ASSUMPTIONS["estate_lag_years"]


# ------------------------------------------------------- added: the headline-run arithmetic

def test_default_path_is_the_central_run_contract():
    """The plan's only convolution fixture passes EXPLICIT off-central params (L=1, 0.75), so no
    plan body exercises the arithmetic the headline run actually performs. Hand oracle at the
    central contract: 200 voluntary in 2040 -> 200*0.9 = 180 listings in 2040; 400 estate exits
    in 2040 -> 400*0.725 = 290 listings in 2042 (lag 2). The two legs land in DIFFERENT years."""
    out = market_listings({2040: 200.0}, {2040: 400.0})
    assert out[2040] == pytest.approx(180.0)
    assert out[2042] == pytest.approx(290.0)
    assert set(out) == {2040, 2042}


def test_legs_accumulate_rather_than_overwrite():
    """Multi-year input: every year's voluntary term and every lagged estate term ADD. 2042 is
    the collision year — 100*0.9 voluntary plus 400*0.725 estate lagged from 2040 = 380."""
    out = market_listings({2040: 200.0, 2042: 100.0}, {2040: 400.0, 2041: 200.0})
    assert out[2040] == pytest.approx(180.0)
    assert out[2042] == pytest.approx(90.0 + 290.0)
    assert out[2043] == pytest.approx(145.0)             # 200 * 0.725, from 2041
    assert set(out) == {2040, 2042, 2043}


def test_phi_market_estate_is_the_eventual_fraction_and_carries_no_lag():
    """Caller trap, pinned. Spec §7's supply term is `S = Σ_cause exits(cause)·φ_market(cause),
    estate lagged L` — the lag is a SEPARATE rider that `phi_market` does not apply. A consumer
    folding `phi_market` over causes without the convolution gets the right decade total and the
    wrong year. The plan body asserts only the voluntary branch; this pins the estate branch and
    the omission with it."""
    assert phi_market("estate") == ESTATE_EVENTUAL_FRACTION
    exits = {"voluntary": 40.0, "estate": 100.0}
    unlagged_total = sum(n * phi_market(cause) for cause, n in exits.items())
    convolved = market_listings({2040: 40.0}, {2040: 100.0})
    assert convolved[2040] != pytest.approx(unlagged_total)      # timing differs by construction
    assert sum(convolved.values()) == pytest.approx(unlagged_total)   # magnitude does not


# ------------------------------------------------------- added: structural domain guards

def test_lag_domain_guard_rejects_the_silently_wrong_lags():
    """ADDED beyond the plan body (repo precedent: `decrements._check_unit`). STRUCTURAL, not a
    band check — bands bind the sweep, and the plan's own fixture legitimately passes L=1.
    A negative lag lands listings BEFORE the deaths that caused them; a fractional lag lands them
    on a year key no annual consumer ever looks up, silently deleting the whole estate leg."""
    with pytest.raises(CalibrationError, match="lag"):
        market_listings({2040: 10.0}, {2040: 10.0}, lag=-1)
    with pytest.raises(CalibrationError, match="lag"):
        market_listings({2040: 10.0}, {2040: 10.0}, lag=2.5)
    assert market_listings({}, {2040: 100.0}, lag=0)[2040] == pytest.approx(72.5)   # 0 is valid


def test_eventual_fraction_domain_guard():
    """Same class: a fraction outside [0,1] is not a sweep leg, it is a defect. NaN falls to the
    same comparison (every ordering against NaN is False), so it raises here too."""
    for bad in (-0.01, 1.01, float("nan")):
        with pytest.raises(CalibrationError, match="eventual_fraction"):
            market_listings({}, {2040: 10.0}, eventual_fraction=bad)


# ------------------------------------- added: phi_voluntary is REACHABLE (run-33 quant/stress F1)

def test_phi_voluntary_is_a_signature_parameter_the_sweep_can_reach():
    """WHY THREE OF FOUR DECLARED SWEEP AXES WERE NEVER SWEPT, named at its cause.

    `lag` and `eventual_fraction` were already parameters; `phi_voluntary` was hard-bound to the
    MODULE-LEVEL constant inside the function body, so the only way to reach its band endpoints
    was to mutate `CENTRAL_ASSUMPTIONS` and RELOAD this module — which a production sweep must
    never do (the test above does exactly that, deliberately, and a reload inside `pipeline.py`
    would rebind every consumer's import mid-run). Run-33's quant and stress gates both
    diagnosed this asymmetry as the likely reason `_rank_stability` iterated one axis.

    The DEFAULT is asserted in the same breath as the override: the read-through binding is the
    thing that keeps `assumptions_hash` honest, and a parameter that shadowed it with its own
    literal would be the second declaration site `constants.py` forbids.
    """
    lo, hi = SWEEP_GRID["phi_voluntary"]
    assert market_listings({2040: 100.0}, {}, phi_voluntary=lo)[2040] == pytest.approx(100.0 * lo)
    assert market_listings({2040: 100.0}, {}, phi_voluntary=hi)[2040] == pytest.approx(100.0 * hi)
    assert lo != PHI_VOLUNTARY and hi != PHI_VOLUNTARY          # both endpoints are OFF central
    assert market_listings({2040: 100.0}, {})[2040] == pytest.approx(100.0 * PHI_VOLUNTARY)


def test_phi_voluntary_domain_guard():
    """Parity with its two siblings, and for the same stated reason: a fraction outside [0,1] is
    not a sweep leg, it is a defect. A new parameter without the guard its neighbours carry is
    the one door on this function that would still admit a silently-wrong value."""
    for bad in (-0.01, 1.01, float("nan")):
        with pytest.raises(CalibrationError, match="phi_voluntary"):
            market_listings({2040: 10.0}, {}, phi_voluntary=bad)
