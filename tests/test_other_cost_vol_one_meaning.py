"""Board item 14 — `simulation.other_cost_vol` means ONE thing.

Until 2026-09-21 the key was applied two ways. On the condo and house paths it
was one lognormal innovation per YEAR per cost line, compounding on the carried
amount (so a line's level spread grew as `vol * sqrt(t)`). On the rent path it
was ONE draw per path, applied to the base amount, after which the series
escalated deterministically — a level that was uncertain at year 0 and frozen
for the rest of the horizon.

Measured on the tip (40,000 paths, `discount_rate: 0`, one $10,000/yr line on
each of the three options, `other_cost_vol: 0.05` the only stochastic input):

    level sd of log(amount_t / base)     PV sd of the cost line
    year   condo   house    rent         years   condo      house      rent
       1  0.0498  0.0503  0.0501             1     500        502       505
       5  0.1115  0.1117  0.0501             5   3,689      3,734     2,496
      10  0.1583  0.1574  0.0501            10   9,747      9,892     5,013
      25  0.2500  0.2489  0.0501            25  37,697     37,292    12,529

and a draw census showed 25.00 shocks/path on each owned option against 1.00 on
the renter. The schema note said "annual vol of other recurring costs", which
described the owned behaviour only — false on exactly the side a reader
checking the renter's exposure would look at.

The owned meaning is the right one and the renter now shares it: an assessor
re-assesses from last year's assessment and an insurer re-prices from last
year's premium, so the innovation is annual and the level is sticky. A renter's
tenant insurance and parking are the same economic objects as an owner's, so
there is no second key and no second correlation key — `corr_inflation_other`
is named for the cost CATEGORY, as `corr_inflation_event_cost` already is.
"""

import numpy as np
import pytest

import hde.monte_carlo as mc
from hde.models import (
    EconomicParams,
    RecurringOtherCost,
    RentParams,
    SimulationParams,
)
from hde.monte_carlo import PathWorld, _simulate_rent_pv_once


YEARS = 10


def _world(years=YEARS, stochastic=False, seed=7):
    """A hand-built world, so the baseline is the fixture and never another
    call to the function under test."""
    if stochastic:
        zs = tuple(np.random.default_rng(seed).normal(size=years).tolist())
    else:
        zs = tuple(0.0 for _ in range(years))
    return PathWorld(
        inflation_factors=tuple(1.0 for _ in range(years)),
        z_inflation=zs,
        inflation_is_stochastic=stochastic,
    )


def _rent(n_costs=1, amount=1_000.0):
    return RentParams(
        monthly_rent=1_500,
        rent_escalation_rate=0.0,
        invested_down_payment=0.0,
        other_recurring_costs=[
            RecurringOtherCost(name=f"line{i}", annual_amount=amount,
                               escalation_rate=0.0)
            for i in range(n_costs)
        ],
    )


def _sim(vol=0.05, years=YEARS, corr=0.0):
    return SimulationParams(
        years=years, discount_rate=0.03, num_sims=1,
        other_cost_vol=vol, corr_inflation_other=corr,
    )


ECON = EconomicParams(mode="real", inflation_rate=0.02, inflation_vol=0.0)


class TestTheRenterDrawsOnceAYear:
    """The count is the whole finding: 1 draw per path was the old meaning,
    `years` draws per line is the new one."""

    @pytest.mark.parametrize("n_costs", [1, 2])
    def test_one_shock_per_year_per_cost_line(self, monkeypatch, n_costs):
        calls = []
        orig = mc._correlated_z

        def counting(base_z, rho, rng):
            calls.append((base_z, rho))
            return orig(base_z, rho, rng)

        monkeypatch.setattr(mc, "_correlated_z", counting)
        # No events, so the other-cost loop is the ONLY caller of _correlated_z.
        _simulate_rent_pv_once(
            _rent(n_costs=n_costs), _sim(), ECON, _world(),
            np.random.default_rng(1),
        )
        assert len(calls) == YEARS * n_costs, (
            f"expected one shock per year per line ({YEARS * n_costs}), "
            f"got {len(calls)} — a level shock draws once per line"
        )

    def test_switched_off_the_channel_consumes_no_draw(self):
        """The absence invariant AT THE GENERATOR (the technique of
        `test_no_channel_consumes_a_draw_while_switched_off`): with the vol at
        zero a leaked draw is invisible in the output, because nothing reads
        it, but it shifts every later draw in configs that never asked for the
        feature."""
        rng = np.random.default_rng(1)
        before = rng.bit_generator.state["state"]["state"]
        _simulate_rent_pv_once(
            _rent(n_costs=2), _sim(vol=0.0), ECON, _world(), rng)
        assert rng.bit_generator.state["state"]["state"] == before, (
            "the renter's other-cost channel consumed a draw while switched off"
        )

        # And switched ON it must consume, or the guard above would also pass
        # on an engine that had stopped drawing altogether.
        rng = np.random.default_rng(1)
        start = rng.bit_generator.state["state"]["state"]
        _simulate_rent_pv_once(
            _rent(n_costs=2), _sim(vol=0.05), ECON, _world(), rng)
        assert rng.bit_generator.state["state"]["state"] != start

    def test_switched_off_the_pv_is_the_closed_form(self):
        """Off, the branch must stay on `_pv_escalating_series`, which collapses
        a flat rate to `pv_recurring_with_escalation`. Asserted BIT-FOR-BIT,
        not approximately: an unrolled recomputation agrees to about 1e-12
        relative, which is exactly the size of drift that would move a shipped
        answer's last printed digits while every tolerance-based test stayed
        green.

        The expected value is built from the helpers directly, so this is not a
        baseline taken from another call to the function under test. With no
        events and no invested capital the simulator returns
        `rent_pv + 0.0 + other_pv + 0 - 0.0`, and adding zero is exact.
        """
        from hde.monte_carlo import _effective_growth_rate, _pv_escalating_series

        # The rent leg is zeroed so the cost line IS the total: the closed form
        # and an unrolled sum differ by ~2 ULP of the cost line, which a larger
        # rent leg added on top would round away (measured: at monthly_rent
        # 1,500 the 8e-12 gap falls under half a ULP of the 162,073 total and
        # the assertion below cannot fail). A non-zero escalation keeps the
        # geometric series a real one.
        world = _world(years=25)
        sim = _sim(vol=0.0, years=25)
        rent = RentParams(
            monthly_rent=0.0, rent_escalation_rate=0.0,
            invested_down_payment=0.0,
            other_recurring_costs=[RecurringOtherCost(
                name="insurance", annual_amount=10_000.0,
                escalation_rate=0.035)],
        )
        got = _simulate_rent_pv_once(
            rent, sim, ECON, world, np.random.default_rng(1))
        rate = _effective_growth_rate(0.035, 1.0, ECON)
        expected = _pv_escalating_series(10_000.0, [rate] * 25, 0.03, 25)
        assert got == expected, f"{got!r} != {expected!r}"


class TestTheRenterSharesTheOwnersCorrelationKey:
    """`corr_inflation_other` is named for the cost category, not a tenure.
    At rho = 1 `_correlated_z` returns `base_z` bit-for-bit, so the z reaching
    the shock must BE that year's inflation z — which is only possible once the
    renter's shock carries a year index."""

    def test_the_shock_reads_that_years_inflation_z(self, monkeypatch):
        world = _world(stochastic=True)
        seen = []
        orig = mc._shock_multiplier

        def recording(vol, z, model):
            if vol == 0.05:
                seen.append(z)
            return orig(vol, z, model)

        monkeypatch.setattr(mc, "_shock_multiplier", recording)
        _simulate_rent_pv_once(
            _rent(), _sim(corr=1.0), ECON, world, np.random.default_rng(1))

        assert seen == list(world.z_inflation), (
            "at corr_inflation_other = 1 the renter's other-cost shock must be "
            "that year's inflation shock"
        )

    def test_the_key_is_inert_when_inflation_has_no_variance(self, monkeypatch):
        """`world.corr` drops rho when there is nothing to correlate with, so
        the shock keeps its full width instead of being shrunk by
        sqrt(1 - rho^2). Pins that the renter's new call goes through
        `world.corr` and not `sim.corr_inflation_other` directly."""
        seen = []
        orig = mc._correlated_z

        def recording(base_z, rho, rng):
            seen.append(rho)
            return orig(base_z, rho, rng)

        monkeypatch.setattr(mc, "_correlated_z", recording)
        _simulate_rent_pv_once(
            _rent(), _sim(corr=0.9), ECON, _world(stochastic=False),
            np.random.default_rng(1))
        assert set(seen) == {0.0}, seen


class TestOneMeaning:
    """The invariant the schema note now states: the same cost line, the same
    vol, on the renter and on an owner, produces the same distribution."""

    def test_the_renters_level_spread_matches_the_owners(self):
        """Measured on the ENGINE, through `run_monte_carlo`, with
        `other_cost_vol` the only stochastic input and `discount_rate: 0`, so
        each option's PV spread is entirely this one channel.

        Distinct-value counts rather than a bare spread assertion: `numpy.std`
        of a constant array of large floats returns ~1e-11, not 0, so a spread
        test can pass on an engine that has stopped drawing.
        """
        from hde.config import load_config_dict
        from hde.monte_carlo import run_monte_carlo

        years, amount, sims = 25, 10_000.0, 8_000
        cost = [{"name": "property tax", "annual_amount": amount,
                 "escalation_rate": 0.0}]
        spec = load_config_dict({
            "years": years, "discount_rate": 0.0,
            "economic": {"mode": "real", "inflation_rate": 0.02,
                         "inflation_vol": 0.0},
            "condo": {"initial_value": 400_000, "all_cash": True,
                      "monthly_fee": 0, "value_growth_rate": 0.0,
                      "selling_cost_rate": 0.0, "purchase_costs": 0,
                      "other_recurring_costs": list(cost)},
            "rent": {"monthly_rent": 1_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 0,
                     "other_recurring_costs": list(cost)},
            "simulation": {"num_sims": sims, "random_seed": 42,
                           "other_cost_vol": 0.05},
        })
        res = run_monte_carlo(spec)
        condo = np.asarray(res.condo.pvs, dtype=float)
        rent = np.asarray(res.rent.pvs, dtype=float)

        # Both sides must actually be drawing.
        assert len(set(condo.tolist())) == sims
        assert len(set(rent.tolist())) == sims

        ratio = rent.std(ddof=1) / condo.std(ddof=1)
        # At 8,000 paths the relative standard error of each sd estimate is
        # ~0.8%, so this band is ~12 sigma wide. The old level shock put the
        # ratio at 0.33.
        assert 0.85 < ratio < 1.15, (
            f"the renter's other-cost dispersion is {ratio:.2f}x the owner's "
            f"on an identical cost line; one key, one meaning"
        )
