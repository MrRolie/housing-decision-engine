"""The channel seam: docs/specs/2026-09-22-which-risk-decides-it.md §3.1-§3.6.

`run_monte_carlo` can now be told which generator each channel's draw sites read
(`streams`) and which channels are pinned to the value `compute_deterministic`
uses (`freeze`). Nothing a user runs asks for either, so this file is the whole
verification surface for the seam, and it is built against one specific way of
being wrong.

WHY AN OUTPUT-LEVEL ASSERTION IS NOT ENOUGH, which this repo has been bitten by
before (`test_price_dispersion_and_lease_reset.py` carries the same warning
about the absence invariant). With every volatility at zero, nothing downstream
READS a draw: a draw site that consumed the wrong channel's stream would produce
a byte-identical answer and a test that looks only at the numbers would pass
while the seam was broken. Worse, the decomposition this seam exists for would
then attribute one channel's movement to another and print a confident table
naming the wrong risk. So the tests that matter here assert on
`rng.bit_generator.state` — before and after — which moves when a draw is taken
whether or not the draw changes a number.

The three assertions the seam owes its caller, each with its own class below:

  1. `streams=None` consumes today's stream (the committed Monte Carlo golden is
     the byte-level proof of it; `TestLegacyBinding` pins the mechanism).
  2. every channel frozen prices the central case on every path
     (`TestAllFrozenIdentity`).
  3. re-drawing a structurally dead channel changes nothing, exactly
     (`TestDeadChannelExactness`).
"""

import copy
import dataclasses
import pathlib

import numpy as np
import pytest

from hde.config import load_config
from hde.deterministic import compute_deterministic
from hde.models import (
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    EventConfig,
    HouseParams,
    IncomeParams,
    MarketScenario,
    PayDropEvent,
    RecurringOtherCost,
    RentParams,
    SimulationParams,
    compute_verdict,
)
from hde.monte_carlo import addressed_streams, channel_stream, run_monte_carlo

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
PRIOR = "tests/fixtures/scenario_prior_golden.json"

# The channel ids, as §3.1 fixes them. Spelled out here because a test that
# hardcoded them silently would be pinning its own arithmetic instead of the
# spec's: 0 economy, 1 market, 2 population, 3 condo, 4 house, 5 shelter,
# 6 portfolio, and 7 the income trajectory, which is not a channel.
CHANNELS = (0, 1, 2, 3, 4, 5, 6)
IDS = CHANNELS + (7,)


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

def _held_streams(seed=1_000):
    """One generator per id, HELD so its state can be read after the run.

    Each id gets its own seed, so this binding is also the shape in which a
    cross-channel leak moves numbers; the identical-seed binding that makes a
    leak invisible in the output is built by `_twinned_streams`.
    """
    return {c: np.random.default_rng(seed + c) for c in IDS}


def _twinned_streams(seed=7):
    """One generator per id, all seeded IDENTICALLY.

    Every id then yields the same numbers in the same order, so any draw site
    reading the wrong channel produces a byte-identical answer. The only
    remaining evidence is which generator moved, which is what the tests using
    this binding assert on.
    """
    return {c: np.random.default_rng(seed) for c in IDS}


def _states(streams):
    return {c: copy.deepcopy(g.bit_generator.state) for c, g in streams.items()}


def _moved(before, after):
    return {c for c in before if before[c] != after[c]}


def _pv_arrays(mc):
    out = {}
    for name in ("condo", "house", "rent"):
        opt = getattr(mc, name)
        if opt is not None:
            out[name] = np.asarray(opt.pvs)
    return out


def _margin_per_path(spec, mc):
    """`f`, the decision margin, priced on every path (spec §2):

        f(w) = min over the other priced options of PV_o(w) - PV_best(w)

    where `best` is the DETERMINISTIC winner. The shipped consumer of this
    quantity is the decomposition module; this is a test-local restatement of
    the spec's formula so that the seam's own contract can be asserted without
    depending on a file another builder owns.
    """
    det = compute_deterministic(spec)
    verdict = compute_verdict(det, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    pvs = _pv_arrays(mc)
    others = np.stack([v for k, v in pvs.items() if k != verdict.best], axis=0)
    return others.min(axis=0) - pvs[verdict.best], verdict


# ---------------------------------------------------------------------------
# Specs, each built so that exactly one thing about it is interesting
# ---------------------------------------------------------------------------

def _all_channels_spec(num_sims=24, years=8, **sim_over):
    """Condo, house, renter and an income block, with every volatility OFF.

    The base for the per-channel toggle tests: each one turns on the single key
    that makes one channel draw, and nothing else in the spec can respond.
    Correlations are left at zero so that turning on `inflation_vol` changes a
    channel's draw COUNT rather than which branch of `_correlated_z` runs.
    """
    sim = dict(
        years=years, discount_rate=0.04, num_sims=num_sims, random_seed=11,
        condo_fee_vol=0.0, house_maintenance_vol=0.0, other_cost_vol=0.0,
        rent_escalation_vol=0.0, investment_return_vol=0.0, value_growth_vol=0.0,
    )
    sim.update(sim_over)
    return ComparisonSpec(
        simulation=SimulationParams(**sim),
        economic=EconomicParams(mode="nominal", inflation_rate=0.02,
                                inflation_vol=0.0),
        condo=CondoParams(
            initial_value=400_000, monthly_fee=350, all_cash=True,
            value_growth_rate=0.02,
            other_recurring_costs=[RecurringOtherCost("tax", 2_400, 0.02)],
            events=[EventConfig("assessment", 9_000, 4)],
        ),
        house=HouseParams(
            initial_value=600_000, all_cash=True, value_growth_rate=0.02,
            annual_maintenance_rate=0.01,
            other_recurring_costs=[RecurringOtherCost("tax", 3_600, 0.02)],
            events=[EventConfig("roof", 14_000, 5)],
        ),
        rent=RentParams(
            monthly_rent=1_900, rent_escalation_rate=0.01,
            invested_down_payment=400_000, investment_return_rate=0.04,
            other_recurring_costs=[RecurringOtherCost("insurance", 340, 0.02)],
            events=[EventConfig("moving", 3_000, 6)],
        ),
        income=IncomeParams(
            annual_income=140_000, income_growth_rate=0.02,
            pay_drop_events=[PayDropEvent(year=4, magnitude=0.7)],
        ),
    )


def _one_live_channel_spec(num_sims=32, years=10, mode="nominal",
                           inflation_vol=0.0):
    """A condo and a renter, with the CONDO the only channel that draws.

    The condo's fee shock is drawn whether or not `condo_fee_vol` is positive
    (it always has been), so a priced condo always makes channel 3 live. Every
    other channel here is a structural zero: no house, no prior, no crash, no
    value dispersion, and a renter with no events, no shocked costs, no reset
    hazard and, in `inflation_vol=0`, no economy to read.
    """
    return ComparisonSpec(
        simulation=SimulationParams(
            years=years, discount_rate=0.04, num_sims=num_sims, random_seed=5,
            condo_fee_vol=0.09,
        ),
        economic=EconomicParams(mode=mode, inflation_rate=0.02,
                                inflation_vol=inflation_vol),
        condo=CondoParams(initial_value=400_000, monthly_fee=350, all_cash=True,
                          value_growth_rate=0.02),
        rent=RentParams(monthly_rent=1_900, rent_escalation_rate=0.01,
                        invested_down_payment=400_000,
                        investment_return_rate=0.04),
    )


def _fixture_spec(num_sims):
    spec = load_config(str(FIXTURE))
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, num_sims=num_sims))


# ---------------------------------------------------------------------------
# 1. The legacy binding
# ---------------------------------------------------------------------------

class TestLegacyBinding:
    """`streams=None` is every channel on the SAME generator object.

    The byte-level proof that this leaves a shipped run alone is
    `tests/fixtures/uncertainty_surface_mc_golden.json`, checked by
    `test_uncertainty_surface.py`. What these tests add is the mechanism: that
    the default really is the one-generator binding, and not a second draw path
    that happens to agree on the configs anyone has looked at.
    """

    def test_default_equals_one_generator_bound_to_every_channel(self):
        spec = _fixture_spec(24)
        one = np.random.default_rng(spec.simulation.random_seed)
        explicit = run_monte_carlo(spec, {c: one for c in IDS})
        default = run_monte_carlo(spec)
        for name, arr in _pv_arrays(default).items():
            np.testing.assert_array_equal(
                arr, _pv_arrays(explicit)[name],
                err_msg="%s moved: streams=None is not the one-generator "
                        "binding, so there are two draw paths through the "
                        "module and the golden only guards one" % name,
            )
        assert (default.prob_rent_cheapest, default.prob_condo_cheapest) == \
            (explicit.prob_rent_cheapest, explicit.prob_condo_cheapest)
        assert default.affordability_mc == explicit.affordability_mc

    def test_the_default_run_varies_at_all(self):
        """The control. Every equality above would also hold on an engine that
        had stopped drawing, so one assertion has to see movement."""
        mc = run_monte_carlo(_fixture_spec(24))
        assert len(set(np.asarray(mc.rent.pvs).tolist())) > 1

    def test_a_streams_mapping_that_misses_a_live_channel_refuses(self):
        """An unbound draw site is a REFUSAL, never a quiet fallback: a channel
        silently sharing another's stream is the defect this seam exists to make
        impossible."""
        with pytest.raises(ValueError, match="channel 3"):
            run_monte_carlo(_one_live_channel_spec(num_sims=2), {})

    @pytest.mark.parametrize("bad", ([7], [-1], [9], [2, 12]))
    def test_freezing_something_that_is_not_a_channel_refuses(self, bad):
        with pytest.raises(ValueError, match="no channel"):
            run_monte_carlo(_one_live_channel_spec(num_sims=2), freeze=bad)


# ---------------------------------------------------------------------------
# 2. The all-frozen identity (spec §3.4, test plan T2)
# ---------------------------------------------------------------------------

class TestAllFrozenIdentity:
    """With every channel frozen, every path prices the central case.

    This is the sharpest assertion available on the freeze mask, and it costs
    one run: a mask that misses a draw site leaves a shock on and the paths
    scatter; a mask that reaches a site belonging to another channel takes that
    channel's shock off too and the level it lands on is wrong.

    On the OWNED options the frozen path and `compute_deterministic` are not
    bit-identical and cannot be made so from this module: the simulators
    compound the value track year by year while the deterministic engine takes
    `(1 + g) ** years`, so the two differ by float ordering. Measured on the
    fixture: 5.821e-11 on the condo and 1.164e-10 on the house, which is 1 and
    2 units in the last place of a ~$450,000 double; the renter, whose frozen
    legs collapse to the same closed forms, is exact to the bit. The assertions
    below are therefore stated in ULPs rather than dollars, which keeps them
    within a factor of four of bit-equality — far tighter than any defect in a
    mask could hide in — and they assert bit-equality outright for the one thing
    that must be exactly constant: the value every path lands on.
    """

    ULP_BUDGET = 4

    @pytest.mark.parametrize("addressed", (True, False))
    def test_every_path_prices_the_deterministic_option(self, addressed):
        spec = _fixture_spec(48)
        streams = (addressed_streams(spec.simulation.random_seed)
                   if addressed else None)
        mc = run_monte_carlo(spec, streams, freeze=CHANNELS)
        det = compute_deterministic(spec)
        for name, arr in _pv_arrays(mc).items():
            assert np.all(arr == arr[0]), (
                "%s scatters with every channel frozen, so the mask misses a "
                "draw site" % name)
            expected = getattr(det, name).total_pv
            budget = self.ULP_BUDGET * np.spacing(abs(expected))
            assert abs(arr[0] - expected) <= budget, (
                "%s frozen at %r, central case %r: off by %.3e, more than %d "
                "ULP" % (name, arr[0], expected, abs(arr[0] - expected),
                         self.ULP_BUDGET))

    def test_the_frozen_margin_is_the_verdict_s_own_margin(self):
        """The identity the level register rests on, at the margin itself.

        `f` is a DIFFERENCE of two option totals near $450,000 that comes out
        near $31,000, so its error is bounded by the ULPs of the numbers
        subtracted and not by its own: on the fixture the frozen margin lands
        exactly 1 ULP of the largest option total away from `verdict.margin_pv`,
        which is 16 ULP of the margin. Scaling the budget to the margin would
        make this assertion a statement about cancellation rather than about the
        mask, so it is scaled to what was subtracted.
        """
        spec = _fixture_spec(48)
        mc = run_monte_carlo(spec, addressed_streams(spec.simulation.random_seed),
                             freeze=CHANNELS)
        f, verdict = _margin_per_path(spec, mc)
        assert np.all(f == f[0]), "the frozen margin is not one number"
        scale = max(abs(float(arr[0])) for arr in _pv_arrays(mc).values())
        budget = self.ULP_BUDGET * np.spacing(scale)
        assert abs(f[0] - verdict.margin_pv) <= budget, (
            "frozen f = %r against verdict.margin_pv = %r (off by %.3e, more "
            "than %d ULP of $%.0f)"
            % (f[0], verdict.margin_pv, abs(f[0] - verdict.margin_pv),
               self.ULP_BUDGET, scale))

    def test_the_unfrozen_margin_scatters(self):
        """The control: the identity above must be a fact about the freeze, not
        about a fixture whose paths never move."""
        spec = _fixture_spec(48)
        mc = run_monte_carlo(spec, addressed_streams(spec.simulation.random_seed))
        f, verdict = _margin_per_path(spec, mc)
        assert np.std(f) > 1_000.0
        assert abs(float(np.mean(f)) - verdict.margin_pv) > 1_000.0

    @pytest.mark.parametrize("channel", CHANNELS)
    def test_a_frozen_channel_takes_no_draw_at_all(self, channel):
        """Frozen means the generator is never touched, not that its draw is
        multiplied by zero.

        The distinction is the §3.4 trap: `_shock_multiplier(vol, 0.0,
        "lognormal")` is `exp(-vol**2 / 2)`, not 1.0, so a mask built by
        zeroing the z would shift the level of every channel it froze while
        still consuming the stream.
        """
        spec = _fixture_spec(16)
        streams = _held_streams()
        before = _states(streams)
        run_monte_carlo(spec, streams, freeze=[channel])
        moved = _moved(before, _states(streams))
        assert channel not in moved, (
            "channel %d is frozen and still consumed a draw" % channel)
        assert moved, "no channel drew at all, so this assertion cannot fail"

    @pytest.mark.parametrize("channel,untouched", [
        (1, ("rent",)),      # the market: the renter owns no home to reprice
        (3, ("house", "rent")),
        (4, ("condo", "rent")),
        (6, ("condo", "house")),
    ])
    def test_freezing_a_channel_leaves_the_options_that_do_not_read_it(
            self, channel, untouched):
        """The freeze is addressed: it reaches one channel's draw sites and no
        others. Only checkable with per-path streams — under the legacy binding
        a removed draw shifts everything downstream of it."""
        spec = _fixture_spec(24)
        streams = addressed_streams(spec.simulation.random_seed)
        base = _pv_arrays(run_monte_carlo(spec, streams))
        frozen = _pv_arrays(run_monte_carlo(spec, streams, freeze=[channel]))
        for name in untouched:
            np.testing.assert_array_equal(
                base[name], frozen[name],
                err_msg="freezing channel %d moved %s, which does not read it"
                        % (channel, name))
        assert any(not np.array_equal(base[n], frozen[n]) for n in base), (
            "freezing channel %d moved nothing at all" % channel)


# ---------------------------------------------------------------------------
# 3. Dead-channel exactness (spec §3.5, test plan T3)
# ---------------------------------------------------------------------------

class TestDeadChannelExactness:
    """Re-drawing a channel nothing reads must change nothing, BIT FOR BIT.

    This is the alignment test: it has no estimator noise to hide behind, so a
    partition in which two channels share an id, or in which a stream is spawned
    positionally and reshuffles when the set of live channels changes, fails it
    outright.
    """

    DEAD_ON_THE_ONE_LIVE_SPEC = (0, 1, 2, 4, 5, 6)

    @pytest.mark.parametrize("dead", DEAD_ON_THE_ONE_LIVE_SPEC)
    def test_swapping_a_structurally_dead_channel_changes_nothing(self, dead):
        spec = _one_live_channel_spec()
        seed = spec.simulation.random_seed
        a = run_monte_carlo(spec, addressed_streams(seed, 0))
        swapped = run_monte_carlo(spec, addressed_streams(seed, 0, {dead: 1}))
        f_a, _ = _margin_per_path(spec, a)
        f_s, _ = _margin_per_path(spec, swapped)
        np.testing.assert_array_equal(
            f_s, f_a,
            err_msg="channel %d draws nothing on this spec, so taking its "
                    "stream from the other matrix must not move f" % dead)
        for name, arr in _pv_arrays(a).items():
            np.testing.assert_array_equal(arr, _pv_arrays(swapped)[name])

    def test_swapping_the_live_channel_does_move_it(self):
        """The control that makes the six assertions above able to fail."""
        spec = _one_live_channel_spec()
        seed = spec.simulation.random_seed
        f_a, _ = _margin_per_path(spec, run_monte_carlo(spec, addressed_streams(seed, 0)))
        f_s, _ = _margin_per_path(
            spec, run_monte_carlo(spec, addressed_streams(seed, 0, {3: 1})))
        assert not np.array_equal(f_a, f_s)
        assert float(np.std(f_a)) > 0.0

    def test_a_drawn_channel_that_reaches_nothing_is_exact_too(self):
        """§3.5's third kind of structural zero, and the subtle one.

        In REAL mode `_effective_growth_rate` discards the inflation factor by
        construction, so with every `corr_inflation_*` key at zero the economy
        channel draws every year and reaches no cash flow. Re-drawing it must
        still change nothing to the bit — the channel is dead in the only sense
        the decomposition cares about, even though its generator moves.
        """
        spec = _one_live_channel_spec(mode="real", inflation_vol=0.02)
        seed = spec.simulation.random_seed
        a = run_monte_carlo(spec, addressed_streams(seed, 0))
        swapped = run_monte_carlo(spec, addressed_streams(seed, 0, {0: 1}))
        np.testing.assert_array_equal(
            _pv_arrays(a)["condo"], _pv_arrays(swapped)["condo"])
        np.testing.assert_array_equal(
            _pv_arrays(a)["rent"], _pv_arrays(swapped)["rent"])

        # ... and the channel really is drawing, or the paragraph above is a
        # story about a generator nobody touched.
        streams = _held_streams()
        before = _states(streams)
        run_monte_carlo(spec, streams)
        assert 0 in _moved(before, _states(streams))


# ---------------------------------------------------------------------------
# 4. Which channel each draw site reads (spec §3.1)
# ---------------------------------------------------------------------------

def _with_sim(spec, **over):
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, **over))


def _with_econ(spec, **over):
    return dataclasses.replace(
        spec, economic=dataclasses.replace(spec.economic, **over))


def _jitter_event(spec, option):
    params = getattr(spec, option)
    events = [dataclasses.replace(e, timing_std_years=2.0) for e in params.events]
    return dataclasses.replace(
        spec, **{option: dataclasses.replace(params, events=events)})


# One knob per id, each chosen so that turning it on changes the number of
# draws taken from exactly one stream. The event-timing knobs are used for the
# option channels because a fee or maintenance shock is drawn whether or not its
# volatility is positive, so those keys move no COUNT.
KNOBS = {
    0: ("economic.inflation_vol", lambda s: _with_econ(s, inflation_vol=0.015)),
    1: ("simulation.value_growth_vol", lambda s: _with_sim(s, value_growth_vol=0.07)),
    2: ("market_scenario", lambda s: dataclasses.replace(
        s, market_scenario=MarketScenario(path=PRIOR, geography="MTL_RMR"))),
    3: ("condo.events[].timing_std_years", lambda s: _jitter_event(s, "condo")),
    4: ("house.events[].timing_std_years", lambda s: _jitter_event(s, "house")),
    5: ("rent.reset_hazard", lambda s: dataclasses.replace(
        s, rent=dataclasses.replace(s.rent, reset_hazard=0.5,
                                    reset_to_monthly_rent=2_600))),
    6: ("simulation.investment_return_vol",
        lambda s: _with_sim(s, investment_return_vol=0.10)),
    7: ("income.pay_drop_events[].year_jitter_std", lambda s: dataclasses.replace(
        s, income=dataclasses.replace(
            s.income,
            pay_drop_events=[dataclasses.replace(e, year_jitter_std=2.0)
                             for e in s.income.pay_drop_events]))),
}


class TestEachDrawSiteReadsItsOwnChannel:
    """The partition, asserted at the generator rather than at the output.

    Every test here compares two runs of the same base spec with the same eight
    seeds, one of which has a single key turned on. The key's own stream must
    move and every other stream must come out bit-identical. A draw site reading
    the wrong channel fails this even on a config where it changes no number,
    which is the failure mode an output assertion cannot see.
    """

    def test_the_base_spec_touches_exactly_three_streams(self):
        """What the instrument reads before any knob is turned.

        Pinned because the toggle tests below are DIFFERENCES, and a difference
        against an unknown baseline says less than it looks like it does.

        Three of the eight streams move with EVERY volatility in the spec set to
        zero, and it is worth naming why, because it is what §3.6 liveness has
        to be computed from rather than guessed: the cost shocks are drawn and
        then multiplied by a zero volatility, not skipped. The condo's fee z,
        the house's maintenance z, both options' other-cost z's and all three
        options' event-cost z's are taken unconditionally. So any priced option
        with a cost line or an event makes its channel consume draws, and a
        channel that consumes draws is not the same thing as a channel that
        moves a number.
        """
        streams = _held_streams()
        before = _states(streams)
        run_monte_carlo(_all_channels_spec(), streams)
        assert _moved(before, _states(streams)) == {3, 4, 5}, (
            "the condo, the house and the renter each draw a cost shock here "
            "whatever their volatilities; nothing else in this spec draws"
        )

    @pytest.mark.parametrize("channel", sorted(KNOBS))
    def test_one_knob_moves_one_stream(self, channel):
        key, turn_on = KNOBS[channel]
        base, toggled = _all_channels_spec(), turn_on(_all_channels_spec())

        base_streams, toggled_streams = _held_streams(), _held_streams()
        run_monte_carlo(base, base_streams)
        run_monte_carlo(toggled, toggled_streams)
        after_base, after_toggled = _states(base_streams), _states(toggled_streams)

        assert after_base[channel] != after_toggled[channel], (
            "%s is on, and channel %d's stream did not move: the draw site it "
            "controls is reading some other channel" % (key, channel))
        leaked = {c for c in IDS
                  if c != channel and after_base[c] != after_toggled[c]}
        assert not leaked, (
            "%s is on, and it moved channel(s) %s as well as %d: a draw site "
            "is reading a stream that does not belong to it"
            % (key, sorted(leaked), channel))

    def test_the_renter_s_five_draw_sites_split_five_and_one(self):
        """§3.1's renter split, stated as the two knobs that prove it.

        Of the renter's five draw sites, exactly one — the per-year `z_inv` on
        the invested capital — is the portfolio channel. `investment_return_vol`
        must therefore move channel 6 and leave 5 alone, and every shelter-side
        knob must do the reverse. Measured for the spec, lumping them gives one
        row at 0.809 of the spread that names nothing a household can act on;
        split, the portfolio carries the spread and the shelter carries the
        level, and they are different kinds of thing.
        """
        base = _all_channels_spec()
        shelter_on = _with_sim(
            dataclasses.replace(
                base, rent=dataclasses.replace(
                    base.rent, reset_hazard=0.5, reset_to_monthly_rent=2_600,
                    events=[dataclasses.replace(e, timing_std_years=2.0)
                            for e in base.rent.events])),
            rent_escalation_vol=0.06, other_cost_vol=0.05)
        portfolio_on = _with_sim(base, investment_return_vol=0.10)

        s_base, s_shelter, s_port = (_held_streams(), _held_streams(),
                                     _held_streams())
        run_monte_carlo(base, s_base)
        run_monte_carlo(shelter_on, s_shelter)
        run_monte_carlo(portfolio_on, s_port)
        a_base, a_shelter, a_port = (_states(s_base), _states(s_shelter),
                                     _states(s_port))

        assert a_port[6] != a_base[6] and a_port[5] == a_base[5], (
            "z_inv is the portfolio's draw and nothing else of the renter's is")
        assert a_shelter[5] != a_base[5] and a_shelter[6] == a_base[6], (
            "the escalation, event, reset and other-cost draws are the "
            "shelter's, and none of them is the portfolio's")

    def test_a_leak_is_visible_in_the_state_where_it_is_invisible_in_the_output(self):
        """The test this seam is really built for.

        The binding gives every id a generator seeded IDENTICALLY, so all eight
        streams yield the same numbers in the same order. On this spec the
        condo's fee shock is the only draw site in the engine, and the economy
        takes no draw at all (`inflation_vol` is zero). A site reading channel 0
        instead of channel 3 would therefore consume the same numbers, in the
        same order, and produce a byte-identical answer — no output assertion
        anywhere could fail. What changes is which generator moved, and that is
        what this asserts.
        """
        spec = _one_live_channel_spec(num_sims=8)
        fresh = _twinned_streams()
        expected_quiet = _states(fresh)[0]
        streams = _twinned_streams()
        run_monte_carlo(spec, streams)
        after = _states(streams)

        assert after[3] != expected_quiet, (
            "the condo's fee shock is this spec's only draw site and channel 3 "
            "never moved")
        for quiet in (0, 1, 2, 4, 5, 6, 7):
            assert after[quiet] == expected_quiet, (
                "channel %d took a draw it has no draw site for: on this spec "
                "only the condo draws, and every stream carries the same "
                "numbers, so this is the only assertion that can see it"
                % quiet)


# ---------------------------------------------------------------------------
# 5. The addressed binding is addressed (spec §3.2)
# ---------------------------------------------------------------------------

class TestPerPathAddressing:
    """A path's draws are a pure function of its index.

    §3.2 requires the key to be per path rather than one long stream per
    channel, and the reason is a trap with no symptom: `_sample_reset_year` and
    `_sample_event_year_hazard` both return early inside their year loop, so
    their draw COUNT depends on the outcome they produce. Consumed
    sequentially, a channel re-drawn to measure it would shift every later
    path's draws in that channel, the pick-freeze pairs would stop being pairs,
    and the answer would be wrong with nothing in the output to see it by.
    """

    def test_reversing_the_path_index_reverses_the_answer(self):
        """The property, stated so that a sequential implementation fails it.

        Handed a binding that maps path i to key n-1-i, an addressed engine
        returns the same paths in the opposite order. One that consumed a
        channel's stream in run order would ignore the key entirely and return
        the forward answer.
        """
        spec = _one_live_channel_spec(num_sims=16)
        seed, n = spec.simulation.random_seed, spec.simulation.num_sims
        forward = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed, 0)))
        backward = _pv_arrays(run_monte_carlo(spec, {
            c: (lambda i, c=c: channel_stream(seed, 0, c, n - 1 - i))
            for c in IDS
        }))
        assert len(set(forward["condo"].tolist())) == n, (
            "the paths must all differ, or a reversal could not be seen")
        np.testing.assert_array_equal(backward["condo"], forward["condo"][::-1])

    def test_a_path_is_priced_the_same_however_many_paths_follow_it(self):
        """A run of 16 paths and a run of 4 price path 0 identically, and so do
        the frozen runs. Under positional spawning the shorter run would get a
        different key."""
        spec = _one_live_channel_spec(num_sims=16)
        seed = spec.simulation.random_seed
        long_run = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed, 0)))
        short = dataclasses.replace(
            spec, simulation=dataclasses.replace(spec.simulation, num_sims=4))
        short_run = _pv_arrays(run_monte_carlo(short, addressed_streams(seed, 0)))
        np.testing.assert_array_equal(short_run["condo"], long_run["condo"][:4])

    def test_the_two_matrices_are_independent_draws_of_the_same_channels(self):
        """A and B must differ everywhere a channel is live, and a channel taken
        from B in A's matrix must land on exactly B's values."""
        spec = _one_live_channel_spec(num_sims=16)
        seed = spec.simulation.random_seed
        a = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed, 0)))["condo"]
        b = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed, 1)))["condo"]
        ab = _pv_arrays(
            run_monte_carlo(spec, addressed_streams(seed, 0, {3: 1})))["condo"]
        assert not np.array_equal(a, b)
        # Channel 3 is the only live channel here, so A with channel 3 taken
        # from B is B exactly. That is the strongest available statement that
        # the swap reaches the whole channel and nothing else.
        np.testing.assert_array_equal(ab, b)

    def test_the_same_seed_reproduces_the_addressed_run(self):
        spec = _one_live_channel_spec(num_sims=8)
        seed = spec.simulation.random_seed
        first = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed)))
        second = _pv_arrays(run_monte_carlo(spec, addressed_streams(seed)))
        for name, arr in first.items():
            np.testing.assert_array_equal(arr, second[name])
