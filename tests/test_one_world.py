"""One world per path — the shared economic draw (Part A of
docs/specs/2026-09-21-one-world-simulation.md).

Before this slice, one Monte Carlo iteration held three unrelated economies:
`_simulate_condo_pv_once` drew its own inflation path, `_simulate_house_pv_once`
drew another from the same generator, and `_simulate_rent_pv_once` drew none at
all — it composed with the fixed scalar `economic.inflation_rate`, so a
renter's costs could not move with the economy under any setting. The three
totals were then stacked and ranked by position, and `prob_condo_cheapest`,
`prob_house_cheapest` and `prob_rent_cheapest` — the numbers the decisiveness
rule reads — were published as the chance each option is cheapest in the SAME
future.

The four tests below are the spec's §6 plan for Part A.

NOTE ON MODE. `_effective_growth_rate` returns the base rate unchanged in real
mode: the inflation factor reaches a cash flow only in NOMINAL mode, where the
only live channel in real mode is `z_inflation` through the `corr_inflation_*`
keys. So the two tests that need inflation to move money run nominal, and say
so. That is a property of the engine's real/nominal contract, not of this fix.
"""

import dataclasses
import json
import pathlib
import statistics

import numpy as np
import pytest

from hde.config import load_config
from hde.deterministic import compute_deterministic
from hde.models import (
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    RentParams,
    SimulationParams,
)
from hde.monte_carlo import (
    _draw_path_world,
    _is_flat,
    _pv_escalating_series,
    _simulate_condo_pv_once,
    _simulate_rent_pv_once,
    run_monte_carlo,
)
from hde.pv import pv_recurring_with_escalation
from hde.serialization import det_to_dict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO_ROOT / "examples").glob("*.yaml"))


def _cost_only_pair(inflation_vol: float, years: int = 20):
    """A condo and a renter reduced to pure cost streams — no asset on either
    side, so both totals rise with inflation and their covariance is positive
    by construction. The spec's variance claim, Var(A − B) = Var(A) + Var(B) −
    2·Cov(A, B), only predicts a FALL when that covariance is non-negative; a
    leveraged owner can sit on the other side of it (nominal inflation lifts
    the asset against a fixed nominal mortgage), so the test pins the case the
    claim is stated for.
    """
    condo = CondoParams(monthly_fee=1_200.0, fee_escalation_rate=0.02,
                        initial_value=0.0, value_growth_rate=0.0, all_cash=True)
    rent = RentParams(monthly_rent=1_800.0, rent_escalation_rate=0.02,
                      invested_down_payment=0.0)
    sim = SimulationParams(years=years, discount_rate=0.05, num_sims=2_000,
                           random_seed=2026)
    econ = EconomicParams(mode="nominal", inflation_rate=0.02,
                          inflation_vol=inflation_vol)
    return condo, rent, sim, econ


# --------------------------------------------------------------------------
# 1. Same-world identity — the fix is invisible when nothing is random.
# --------------------------------------------------------------------------

def test_one_world_equals_three_worlds_when_nothing_is_random():
    """With every volatility at zero there is exactly ONE possible world, so a
    shared draw and three private draws cannot differ. Stated three ways: the
    world consumes no randomness, worlds drawn from unrelated generator states
    are equal objects, and the Monte Carlo lands exactly on the deterministic
    engine on every path."""
    condo, rent, sim, econ = _cost_only_pair(inflation_vol=0.0)
    sim = dataclasses.replace(sim, num_sims=50)

    # (a) the world consumes no draws: the generator is where it was.
    rng = np.random.default_rng(7)
    before_state = rng.bit_generator.state
    world = _draw_path_world(rng, econ, sim.years)
    assert rng.bit_generator.state == before_state
    assert _is_flat(world.inflation_factors)
    assert _is_flat(world.z_inflation)

    # (b) three worlds drawn from unrelated generator states ARE one world.
    w1 = _draw_path_world(np.random.default_rng(1), econ, sim.years)
    w2 = _draw_path_world(np.random.default_rng(999), econ, sim.years)
    assert w1 == w2 == world

    # (c) every path reproduces the deterministic engine exactly.
    spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, rent=rent)
    mc = run_monte_carlo(spec)
    det = compute_deterministic(spec)
    # Exact uniqueness, not `std() == 0`: numpy's mean of a constant array of
    # large floats rounds, so the std of one repeated value is ~1e-11, not 0 —
    # a spread test on this array would pass on any engine.
    assert len(np.unique(mc.condo.pvs)) == 1
    assert len(np.unique(mc.rent.pvs)) == 1
    assert mc.condo.pvs[0] == pytest.approx(det.condo.total_pv, rel=1e-12)
    assert mc.rent.pvs[0] == pytest.approx(det.rent.total_pv, rel=1e-12)


# --------------------------------------------------------------------------
# 2. The variance claim, measured — the direction, not the figure.
# --------------------------------------------------------------------------

def test_sharing_the_inflation_path_narrows_the_condo_minus_rent_spread():
    """On a fixed seed, the spread of (condo total − rent total) FALLS when the
    two options are priced in one economy instead of two, because the
    covariance term stops being zero."""
    condo, rent, sim, econ = _cost_only_pair(inflation_vol=0.015)

    shared = []
    rng = np.random.default_rng(sim.random_seed)
    for _ in range(sim.num_sims):
        world = _draw_path_world(rng, econ, sim.years)
        c = _simulate_condo_pv_once(condo, sim, econ, world, rng)
        r = _simulate_rent_pv_once(rent, sim, econ, world, rng)
        shared.append(c - r)

    independent = []
    rng = np.random.default_rng(sim.random_seed)
    for _ in range(sim.num_sims):
        c = _simulate_condo_pv_once(
            condo, sim, econ, _draw_path_world(rng, econ, sim.years), rng)
        r = _simulate_rent_pv_once(
            rent, sim, econ, _draw_path_world(rng, econ, sim.years), rng)
        independent.append(c - r)

    assert statistics.pstdev(shared) < statistics.pstdev(independent)


# --------------------------------------------------------------------------
# 3. Rent moves with the economy — the cleanest statement of what was wrong.
# --------------------------------------------------------------------------

def test_renter_total_varies_when_only_inflation_is_uncertain():
    """With `inflation_vol` on and every other volatility off, the renter's
    total must vary across paths. Before the shared world it could not: the
    rent simulator composed with the fixed scalar and drew no inflation, so
    every path returned the same number."""
    _, rent, sim, econ = _cost_only_pair(inflation_vol=0.015)
    sim = dataclasses.replace(sim, num_sims=500)
    spec = ComparisonSpec(simulation=sim, economic=econ, rent=rent)

    mc = run_monte_carlo(spec)

    # Distinct values, and a spread far above the ~1e-11 that numpy reports
    # for a constant array of this magnitude: on the pre-world engine every
    # path returned ONE value and both assertions fail.
    assert len(np.unique(mc.rent.pvs)) > 1
    assert mc.rent.pvs.std() > 1.0


# --------------------------------------------------------------------------
# 4. Deterministic untouched — it draws nothing, so nothing here can reach it.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("config", EXAMPLES, ids=lambda p: p.stem)
def test_deterministic_block_is_independent_of_everything_random(config):
    """Every deterministic figure in every shipped example is unchanged by the
    seed and by the number of paths — the standing form of "the shared world
    cannot reach the deterministic engine"."""
    spec = load_config(str(config))
    baseline = json.dumps(det_to_dict(compute_deterministic(spec)), sort_keys=True)
    for seed, sims in ((1, 3), (98765, 11)):
        altered = dataclasses.replace(spec.simulation, random_seed=seed, num_sims=sims)
        other = dataclasses.replace(spec, simulation=altered)
        assert json.dumps(det_to_dict(compute_deterministic(other)), sort_keys=True) == baseline


# --------------------------------------------------------------------------
# The fast path is the same truth as the loop — the alarm on the two forms.
# --------------------------------------------------------------------------

def test_constant_rate_closed_form_matches_the_year_loop():
    """`_pv_escalating_series` takes the geometric closed form when every
    year's rate is identical, which is what keeps a flat world bit-for-bit on
    the pre-world arithmetic. The two forms are one truth, so they are checked
    against each other here rather than left to drift."""
    rate, dr, years, amount = 0.031, 0.047, 25, 21_600.0
    closed = _pv_escalating_series(amount, [rate] * years, dr, years)
    assert closed == pv_recurring_with_escalation(amount, rate, dr, years)

    nudged = [rate] * years
    nudged[-1] = rate + 1e-15  # forces the loop branch on the same economics
    assert _pv_escalating_series(amount, nudged, dr, years) == pytest.approx(
        closed, rel=1e-12)
