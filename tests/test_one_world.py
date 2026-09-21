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


# ---------------------------------------------------------------------------
# The market joins the world (2026-09-21, the completion of Part A)
# ---------------------------------------------------------------------------
#
# Part A shared the INFLATION path and stopped there. Two channels kept
# drawing per option, and both are properties of the market rather than of a
# property:
#
#   * the price-crash Bernoulli and its severity. Measured on the shipped
#     Montréal showcase before the fix: 325 condo crashes against 308 house
#     crashes over 400 paths, in unrelated years, leaving the condo total and
#     the house total essentially UNCORRELATED (corr −0.038) although both are
#     wired with the same 3% hazard and the same 20% severity in one city.
#     std(condo − house) came out at 68,852 — larger than either option's own
#     std (50,478 and 44,941), which is the signature of a covariance pinned
#     at zero.
#
#   * the ISQ population scenario. The condo and the house picked the SAME
#     scenario on 105 of 300 paths (35%), against the 33% you get by chance
#     with three scenarios. Quebec realizes one population future per path.
#
# The tests below invert those two measurements. Both fail on the engine as it
# stood before this slice.

SHOWCASE = REPO_ROOT / "examples" / "showcase_demographic_prior.yaml"


def _showcase(num_sims: int):
    spec = load_config(str(SHOWCASE))
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, num_sims=num_sims)
    )


def test_condo_and_house_crash_in_the_same_years(monkeypatch):
    """One market, one crash. With identical hazard and severity the two
    properties must take the drawdown in exactly the same years on every path.

    Asserts SET EQUALITY of the (path, year) pairs each option crashed in, not
    a count or a spread: equal counts would also hold if the crashes merely
    happened to balance out across unrelated years, which is the defect.
    """
    from hde import monte_carlo as mc

    fired: dict = {"condo": [], "house": []}
    which = {"option": None, "year": 0}

    real_apply = mc._apply_price_shock

    def spy(value_tracks, shock, tilt, u, z):
        before = list(value_tracks)
        out = real_apply(value_tracks, shock, tilt, u, z)
        if any(a != b for a, b in zip(before, out)):
            fired[which["option"]].append((which["path"], which["year"]))
        return out

    monkeypatch.setattr(mc, "_apply_price_shock", spy)

    # Label the draws by option and count years inside each option's loop by
    # watching the world accessor, which is called once per year per option.
    real_crash_draw = mc.PathWorld.crash_draw

    def counting_crash_draw(self, year):
        which["year"] = year
        return real_crash_draw(self, year)

    monkeypatch.setattr(mc.PathWorld, "crash_draw", counting_crash_draw)

    for name, label in (("_simulate_condo_pv_once", "condo"),
                        ("_simulate_house_pv_once", "house")):
        real = getattr(mc, name)

        def wrapped(*a, _real=real, _label=label, **k):
            which["option"] = _label
            if _label == "condo":
                which["path"] = which.get("path", -1) + 1
            return _real(*a, **k)

        monkeypatch.setattr(mc, name, wrapped)

    mc.run_monte_carlo(_showcase(120))

    assert fired["condo"], "the showcase's 3% hazard must fire somewhere in 120 paths"
    assert set(fired["condo"]) == set(fired["house"]), (
        "identical price_shock params in one market must crash both properties "
        "in the same (path, year) slots"
    )
    assert len(fired["condo"]) == len(fired["house"])


def test_condo_and_house_share_one_population_future(monkeypatch):
    """The ISQ scenario is a property of the path, so both options must read
    the same one — 100% agreement, not the 35% that independent draws give."""
    from hde import monte_carlo as mc

    seen: list = []
    real = mc._drift_context

    def spy(prior_rows, world):
        out = real(prior_rows, world)
        if out is not None:
            seen.append(out[0])
        return out

    monkeypatch.setattr(mc, "_drift_context", spy)
    mc.run_monte_carlo(_showcase(150))

    pairs = list(zip(seen[0::2], seen[1::2]))
    assert len(pairs) == 150
    assert all(a == b for a, b in pairs), (
        "the condo and the house must read the same ISQ scenario on every path"
    )
    # And the scenario must still VARY across paths, or the assertion above
    # would pass on an engine that had stopped drawing altogether.
    assert len(set(seen)) > 1


def test_sharing_the_market_raises_the_condo_house_correlation():
    """The measured consequence: two properties in one market must move
    together. Pins a floor, never a figure — but a floor chosen to need BOTH
    shared channels, because a threshold either partial fix clears would not
    be testing what its name says.

    Measured on the showcase at 400 paths, all three regimes:

        neither shared (the defect)      corr −0.038   std(c−h) 68,852
        drift shared, crash per option   corr  0.540   std(c−h) 44,965
        both shared (this engine)        corr  0.991   std(c−h)  7,721

    The 0.9 floor and the 0.3 ratio sit in the gap above the middle row, so
    reverting either channel to a per-option draw fails this test. Both
    thresholds were confirmed by mutating each channel in turn.
    """
    result = run_monte_carlo(_showcase(400))
    c = np.asarray(result.condo.pvs)
    h = np.asarray(result.house.pvs)
    corr = float(np.corrcoef(c, h)[0, 1])
    assert corr > 0.9, f"condo/house correlation fell to {corr:.3f}"
    # The spurious variance is out of the comparison: the difference is now
    # far tighter than either leg, which is what a positive covariance means.
    spread_ratio = float(np.std(c - h)) / float(np.std(c))
    assert spread_ratio < 0.3, f"std(condo − house) is {spread_ratio:.2f} of std(condo)"


def test_a_correlation_key_is_inert_without_inflation_volatility():
    """`corr_inflation_*` is documented as "inert unless
    economic.inflation_vol > 0". Before 2026-09-21 it was not: with no
    inflation volatility the inflation z is the constant 0.0, so
    `_correlated_z` returned `sqrt(1 - rho**2) * eps` — a unit normal SHRUNK by
    that factor. A user who set 0.9 expecting a correlation got their shock
    damped by 56% (std 1.000 -> 0.436 over 20,000 draws) and nothing said so.

    Measured through the engine rather than the helper, because the helper is
    correct in isolation: its premise is that `base_z` is a unit normal, and
    what broke was the caller handing it a constant.
    """
    def spread(rho: float) -> float:
        spec = ComparisonSpec(
            simulation=SimulationParams(
                years=15, discount_rate=0.03, num_sims=600, random_seed=4,
                condo_fee_vol=0.30, corr_inflation_condo=rho),
            economic=EconomicParams(mode="real", inflation_rate=0.02, inflation_vol=0.0),
            condo=CondoParams(initial_value=400_000, monthly_fee=400, all_cash=True),
        )
        return float(np.std(np.asarray(run_monte_carlo(spec).condo.pvs)))

    flat, correlated = spread(0.0), spread(0.9)
    assert flat > 0, "the fee volatility must actually produce a spread"
    assert correlated == pytest.approx(flat, rel=0.01), (
        f"rho damped the shock: {correlated:,.0f} vs {flat:,.0f}"
    )


def test_a_correlation_key_still_bites_when_inflation_is_live():
    """The guard on the test above: made inert unconditionally, the key would
    stop working in the case it exists for."""
    def spread(rho: float) -> float:
        spec = ComparisonSpec(
            simulation=SimulationParams(
                years=15, discount_rate=0.03, num_sims=600, random_seed=4,
                condo_fee_vol=0.30, corr_inflation_condo=rho),
            economic=EconomicParams(mode="nominal", inflation_rate=0.02, inflation_vol=0.03),
            condo=CondoParams(initial_value=400_000, monthly_fee=400, all_cash=True),
        )
        return float(np.std(np.asarray(run_monte_carlo(spec).condo.pvs)))

    assert spread(0.9) != pytest.approx(spread(0.0), rel=0.01)
