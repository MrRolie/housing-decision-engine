"""The assembler: `hde.decomposition_run` (spec §0.1 item 17).

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`. This file is the
verification surface for the piece that turns a spec into a `Decomposition` —
the liveness rule the cost model and the refusals turn on, the three bit-exact
contracts of §11 that prove the assembly is WIRED rather than merely running,
every §8 refusal the assembler owns, and the figures §7 published.

THE THREE BIT-EXACT CONTRACTS, and why each is the sharpest test available:

  * ALL CHANNELS FROZEN reproduces the central case. Bit-exact ACROSS PATHS —
    every path prices the same margin — and within one ULP of the totals
    subtracted against `verdict.margin_pv`. Not bit-exact against the verdict
    itself: §3.4's "bit for bit" is false there, because the simulators
    compound year by year while `compute_deterministic` takes `(1 + g) ** n`.
    The measured deviation is 5.821e-11, which is exactly one ULP of the
    house's own total, and the budget below is stated in ULPs of the figures
    being subtracted rather than as a tolerance somebody liked.
  * A STRUCTURALLY DEAD CHANNEL's swap changes nothing, exactly. No estimator
    noise to hide behind: two channels sharing an id fails it outright.
  * THE GOLDEN IS UNTOUCHED by this module existing, and by a decomposition
    running between two legacy runs.

WHICH CHANNELS DRAW AND WHICH ARE LIVE is measured on the run (§0.1 item 39);
the tests here hold that measurement to answers known from the model's
structure, and `tests/test_decomposition_liveness.py` holds it to independent
instruments on the configs where a copy of the simulator's logic got it wrong.

EVERY REFUSAL IS TESTED IN BOTH DIRECTIONS. A test that it fires, and a test
that it does NOT fire on the nearest legal call — an over-wide refusal fails
only on calls that were always legal, and nothing in an ordinary suite hunts
for that.
"""
from __future__ import annotations

import dataclasses
import re
import json
import pathlib

import numpy as np
import pytest
import yaml

from hde.config import load_config, single_path_run
from hde.decomposition import (
    LEVEL_PATHS,
    REFUSAL_CODES,
    SPREAD_REFUSAL_CODES,
    Decomposition,
    DecompositionRefusal,
    IndistinguishableLevel,
    RefusedInteraction,
    RefusedSpread,
    SpreadRegister,
    ResolvedInteraction,
    ResolvedLevel,
    ResolvedShares,
    UnresolvedShares,
    Width,
    channel,
    channel_by_key,
)
from hde.decomposition_text import format_decomposition
from hde.deterministic import compute_deterministic
from hde.models import (
    ComparisonSpec,
    CondoParams,
    EconomicParams,
    EventConfig,
    HouseParams,
    RecurringOtherCost,
    RentParams,
    SimulationParams,
    compute_verdict,
)
from hde.monte_carlo import _load_prior_if_any, addressed_streams, run_monte_carlo
from hde.serialization import decomposition_to_dict

import hde.decomposition_math as dm
import hde.decomposition_run as dr
from hde.decomposition_run import (
    EVALUATION_CEILING,
    decompose,
    margin_per_path,
    measure_channels,
    planned_evaluations,
)

from .test_channel_streams import _all_channels_spec, _one_live_channel_spec

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface.yaml"
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "uncertainty_surface_mc_golden.json"
EXAMPLES = REPO_ROOT / "examples"


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

def _inputs(spec, *, raw=None):
    """The four objects the CLI hands the seam, for one spec."""
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate,
                              single_path=single_path_run(spec))
    return dict(det=det, mc=mc, verdict=verdict, raw=raw)


def _measure(spec, paths=None):
    """The engine's own measurement of draws and liveness on `paths` futures."""
    det = compute_deterministic(spec)
    verdict = compute_verdict(det, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate)
    return measure_channels(spec, det=det, verdict=verdict, paths=paths)


def _fixture_spec(num_sims=None):
    spec = load_config(str(FIXTURE))
    if num_sims is None:
        return spec
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, num_sims=num_sims))


def _fixture_raw():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


class _Spy:
    """Counts the evaluations this module spends, by replacing its own binding.

    `hde.decomposition_run.run_monte_carlo` is the name every matrix goes
    through, so this sees all of them.
    """

    def __init__(self, monkeypatch):
        self.runs = []
        inner = dr.run_monte_carlo

        def counting(spec, streams=None, *, freeze=()):
            self.runs.append((int(spec.simulation.num_sims), tuple(freeze)))
            return inner(spec, streams, freeze=freeze)

        monkeypatch.setattr(dr, "run_monte_carlo", counting)

    @property
    def evaluations(self):
        return sum(paths for paths, _ in self.runs)


# ---------------------------------------------------------------------------
# Constructed specs, each built so exactly one thing about it is interesting
# ---------------------------------------------------------------------------

def _twin_owners_spec(num_sims=64, differ=False):
    """Two owned options that price IDENTICALLY on every path.

    Same value, same growth, no fees, no maintenance, no costs, no events, both
    all cash. The market and the economy both move BOTH options by exactly the
    same factor, so `f` is the same figure on every future and `Var(f)` is 0
    with TWO live channels — §8 refusal 5, which is otherwise hard to reach: a
    channel that moves a cash flow normally moves `f` with it.

    `differ` breaks the twinning by one dollar of initial value, which is the
    nearest legal call: the same two live channels, and a spread.
    """
    condo_value = 500_000
    house_value = 500_001 if differ else 500_000
    return ComparisonSpec(
        simulation=SimulationParams(
            years=10, discount_rate=0.04, num_sims=num_sims, random_seed=3,
            value_growth_vol=0.06,
        ),
        economic=EconomicParams(mode="nominal", inflation_rate=0.02,
                                inflation_vol=0.01),
        condo=CondoParams(initial_value=condo_value, monthly_fee=0.0,
                          all_cash=True, value_growth_rate=0.02),
        house=HouseParams(initial_value=house_value, all_cash=True,
                          value_growth_rate=0.02, annual_maintenance_rate=0.0),
    )


def _every_future_agrees_spec(num_sims=80):
    """A renter who is cheaper in EVERY future — §8's "prints, no shares".

    The condo costs four times what renting does, so no channel can move a
    future across the boundary: `P(f > 0)` is exactly 1. Two channels are live
    (the condo's fees and the renter's portfolio), so the block does not fall to
    any other refusal on the way.
    """
    return ComparisonSpec(
        simulation=SimulationParams(
            years=10, discount_rate=0.04, num_sims=num_sims, random_seed=9,
            condo_fee_vol=0.10, investment_return_vol=0.10,
        ),
        economic=EconomicParams(mode="real", inflation_rate=0.0),
        condo=CondoParams(initial_value=2_000_000, monthly_fee=1_200,
                          all_cash=True, value_growth_rate=0.0),
        rent=RentParams(monthly_rent=500, rent_escalation_rate=0.0,
                        invested_down_payment=10_000,
                        investment_return_rate=0.03),
    )


def _drawing_but_dead_house_spec(num_sims=64):
    """Two live channels, and a house whose channel draws and reaches nothing.

    The house has no maintenance rate, no cost lines and no events, so its
    maintenance shock is drawn every year and multiplied by a volatility of
    zero. §3.5's third structural zero, on a config that still prints.
    """
    return ComparisonSpec(
        simulation=SimulationParams(
            years=8, discount_rate=0.04, num_sims=num_sims, random_seed=17,
            condo_fee_vol=0.08, investment_return_vol=0.10,
        ),
        economic=EconomicParams(mode="real", inflation_rate=0.0),
        condo=CondoParams(initial_value=400_000, monthly_fee=350,
                          all_cash=True, value_growth_rate=0.02),
        house=HouseParams(initial_value=600_000, all_cash=True,
                          value_growth_rate=0.02, annual_maintenance_rate=0.0),
        rent=RentParams(monthly_rent=1_900, rent_escalation_rate=0.0,
                        invested_down_payment=400_000,
                        investment_return_rate=0.04),
    )


def _single_option_spec(num_sims=32):
    return ComparisonSpec(
        simulation=SimulationParams(years=8, discount_rate=0.04,
                                    num_sims=num_sims, random_seed=4,
                                    condo_fee_vol=0.08),
        economic=EconomicParams(mode="real", inflation_rate=0.0),
        condo=CondoParams(initial_value=400_000, monthly_fee=350,
                          all_cash=True, value_growth_rate=0.02),
    )


# ---------------------------------------------------------------------------
# 1. Liveness — the rule, and the question it is NOT
# ---------------------------------------------------------------------------

class TestLiveness:
    """§3.6 and §0.1 items 22 and 39: a channel that draws is not a channel
    that moves a number, and both are measured on the run. Each answer here is
    known from the model's structure, not from another run of the same
    measurement."""

    # §3.6's own measured table: a record of the same question answered before
    # this measurement existed. A config on which the two disagree names which.
    SPEC_TABLE = {
        "first_time_buyer_montreal.yaml": (),
        "income_shock.yaml": ("condo",),
        "basic_config.yaml": ("condo", "house"),
        "mortgage_house_vs_rent.yaml": ("house", "shelter"),
        "rent_vs_condo_vs_house.yaml": ("condo", "house"),
        "advanced_config.yaml": ("economy", "condo", "house"),
        "showcase_demographic_prior.yaml": ("market", "population", "condo",
                                            "house", "portfolio"),
    }

    @pytest.mark.parametrize("name", sorted(SPEC_TABLE))
    def test_the_measurement_reproduces_the_spec_s_table(self, name):
        expected = self.SPEC_TABLE[name]
        spec = load_config(str(EXAMPLES / name))
        got = tuple(channel(c).key for c in _measure(spec, paths=40).live)
        assert got == expected, (
            "§3.6 measured the live channels on this shipped config and this "
            f"measurement disagrees: {got} against {expected}")

    def test_the_fixture_has_all_seven_live_and_its_income_stream_draws(self):
        got = _measure(_fixture_spec(), paths=40)
        assert got.live == tuple(range(7))
        assert got.drawn == tuple(range(8))
        assert got.moves[dc_income()] <= got.threshold

    def test_the_two_questions_have_different_answers(self):
        """The finding, on a config where the difference is total.

        `tests/test_channel_streams.py` pins, at the bit-generator state, that
        three streams advance on this spec with every volatility at zero; a
        measurement that called drawing live would print a three-row table of
        channels that move nothing."""
        got = _measure(_all_channels_spec())
        assert got.drawn == (3, 4, 5)
        assert got.live == ()
        assert all(got.moves[c] == 0.0 for c in got.drawn)

    def test_the_real_mode_inflation_trap_draws_and_is_not_live(self):
        """§3.5's third kind, the one the spec names: real mode discards the
        inflation factor, and no correlation is on to carry it."""
        got = _measure(_one_live_channel_spec(mode="real", inflation_vol=0.02))
        assert 0 in got.drawn
        assert 0 not in got.live

    def test_nominal_mode_makes_the_same_inflation_draw_live(self):
        """The nearest legal call: the factor composes into every growth rate."""
        assert 0 in _measure(_one_live_channel_spec(mode="nominal",
                                                    inflation_vol=0.02)).live

    def test_a_zero_severity_crash_hazard_draws_and_is_not_live(self):
        """`_apply_price_shock` multiplies the value by `1 - 0`, so a hazard
        with no severity behind it draws its crash uniforms and moves nothing."""
        from hde.models import PriceShockParams
        spec = _twin_owners_spec()
        spec = dataclasses.replace(
            spec,
            simulation=dataclasses.replace(spec.simulation, value_growth_vol=0.0),
            condo=dataclasses.replace(
                spec.condo,
                price_shock=PriceShockParams(annual_hazard=0.05,
                                             severity_mean=0.0)))
        got = _measure(spec)
        assert 1 in got.drawn and 1 not in got.live
        lively = dataclasses.replace(
            spec, condo=dataclasses.replace(
                spec.condo,
                price_shock=PriceShockParams(annual_hazard=0.05,
                                             severity_mean=0.2)))
        assert 1 in _measure(lively).live


def dc_income():
    from hde.decomposition import INCOME_STREAM_ID
    return INCOME_STREAM_ID


# ---------------------------------------------------------------------------
# 2. §2 — the margin, and the one home for its formula
# ---------------------------------------------------------------------------

class TestMargin:

    def test_the_margin_keeps_the_third_option(self):
        """§2 property 3: the `min` keeps the option a pairwise gap deletes."""
        spec = _drawing_but_dead_house_spec()
        mc = run_monte_carlo(spec)
        f = margin_per_path(mc, "rent")
        others = np.minimum(np.asarray(mc.condo.pvs), np.asarray(mc.house.pvs))
        np.testing.assert_array_equal(f, others - np.asarray(mc.rent.pvs))

    def test_a_single_priced_option_has_no_margin(self):
        spec = _single_option_spec()
        mc = run_monte_carlo(spec)
        with pytest.raises(ValueError, match="no margin exists"):
            margin_per_path(mc, "condo")


# ---------------------------------------------------------------------------
# 3. §11's three bit-exact contracts
# ---------------------------------------------------------------------------

class TestBitExactContracts:

    def test_all_channels_frozen_reproduces_the_central_case(self):
        """T2. Bit-exact across paths, and one ULP of the totals subtracted.

        This is the identity that makes the level register a fact rather than a
        claim: a mask that misses a draw site fails it, and a mask that reaches
        another channel's site fails it.
        """
        spec = _fixture_spec(num_sims=200)
        det = compute_deterministic(spec)
        verdict = compute_verdict(det, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        frozen = margin_per_path(
            dr._run(spec, dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS), verdict.best)
        assert float(np.ptp(frozen)) == 0.0, (
            "with every channel frozen every path must price the SAME margin, "
            "bit for bit; a spread here means a draw site escaped the mask"
        )
        deviation = float(np.max(np.abs(frozen - verdict.margin_pv)))
        budget = dr.identity_budget(det, verdict)
        assert deviation <= budget, (
            f"the frozen margin is {deviation:.3e} from the verdict's own, "
            f"above {budget:.3e} — the deterministic side takes (1+g)**n while "
            "the simulators compound year by year, so a few ULPs are expected "
            "and a real figure is not"
        )
        assert deviation > 0.0, (
            "an exactly-zero deviation would mean this test could not fail on "
            "the compounding difference it is budgeted for; if the engines are "
            "ever made identical, tighten the budget deliberately"
        )

    @pytest.mark.parametrize("dead", (0, 1, 2, 4, 5, 6))
    def test_swapping_a_dead_channel_changes_f_bit_for_bit(self, dead):
        """T3, through the assembler's own `_run`, which prices every matrix.

        On a spec where only the condo draws, every other channel's `A_B^(d)`
        must be `f(A)` to the bit — which is what makes `S_d` exactly 0.0 with
        no estimator noise anywhere in it.
        """
        spec = _one_live_channel_spec()
        base = margin_per_path(dr._run(spec, dr.MATRIX_A), "condo")
        swapped = margin_per_path(
            dr._run(spec, dr.MATRIX_A, {dead: dr.MATRIX_B}), "condo")
        np.testing.assert_array_equal(swapped, base)

    def test_swapping_the_live_channel_does_move_f(self):
        """The control that makes the six assertions above able to fail."""
        spec = _one_live_channel_spec()
        base = margin_per_path(dr._run(spec, dr.MATRIX_A), "condo")
        swapped = margin_per_path(
            dr._run(spec, dr.MATRIX_A, {3: dr.MATRIX_B}), "condo")
        assert not np.array_equal(base, swapped)

    def test_a_decomposition_leaves_the_legacy_stream_where_it_was(self):
        """T1, at this module's own boundary.

        The golden proves the legacy binding is byte-identical; this proves
        that running a decomposition in the same process does not move it. A
        module that reached for a global generator would fail here.
        """
        spec = _fixture_spec(num_sims=40)
        before = np.asarray(run_monte_carlo(spec).rent.pvs).copy()
        decompose(spec, paths=40, **_inputs(spec))
        after = np.asarray(run_monte_carlo(spec).rent.pvs)
        np.testing.assert_array_equal(after, before)

    def test_the_committed_golden_still_matches(self):
        """The golden itself, read and compared, so this file cannot pass while
        the shipped Monte Carlo has moved under it."""
        spec = _fixture_spec()
        mc = run_monte_carlo(spec)
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        probs = golden.get("probabilities", golden)
        for option in ("condo", "house", "rent"):
            key = f"prob_{option}_cheapest"
            if key in probs:
                assert getattr(mc, key) == pytest.approx(probs[key], abs=0.0), (
                    f"{key} moved against the committed golden"
                )


# ---------------------------------------------------------------------------
# 4. §8's refusals, each in both directions
# ---------------------------------------------------------------------------

class TestRefusals:
    """Every refusal the assembler owns: it fires when it should, and it does
    NOT fire on the nearest legal call."""

    def test_no_monte_carlo_refuses_with_the_one_fact(self):
        """§0.1 items 25 and 35: the block is futures-only, and the refusal
        states the fact that fired it and names no route — the three-option
        route it once named was a clause about a run the block did not price.
        *Kills it:* a route or an explanation back in the reason."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, **{**_inputs(spec), "mc": None})
        assert isinstance(got, DecompositionRefusal) and got.code == "no_futures"
        assert got.reason == "this run has no futures"

    def test_a_single_path_run_refuses_with_the_same_fact(self):
        """The other way to have no futures: every uncertainty input off."""
        spec = load_config(str(EXAMPLES / "first_time_buyer_montreal.yaml"))
        spec = dataclasses.replace(
            spec, simulation=dataclasses.replace(spec.simulation, num_sims=40))
        assert single_path_run(spec)
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal) and got.code == "no_futures"
        assert got.reason == "this run has no futures"

    def test_a_sample_too_small_to_interval_refuses_under_its_own_code(self):
        """Found by this file at two futures, where the bootstrap's own
        refusal escaped as a traceback instead of a named reason.

        Its own code, never `no_futures`: this run HAS futures, and a consumer
        keyed on the code would tell it that it has none.
        *Kills it:* reusing `no_futures`, or deleting the floor."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, paths=dr.MIN_INTERVALLED_FUTURES - 1,
                        **_inputs(spec))
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "too_few_futures"
        assert got.code in REFUSAL_CODES
        assert got.reason == (f"{dr.MIN_INTERVALLED_FUTURES - 1} futures were asked for, "
                              f"below the minimum of {dr.MIN_INTERVALLED_FUTURES}")

    def test_two_futures_refuse_rather_than_raise(self):
        """The case that found it: a 300-resample bootstrap over two paths
        draws a degenerate resample on half its draws."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, paths=2, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "too_few_futures"

    def test_the_floor_itself_does_not_refuse(self):
        """The nearest legal call: exactly the floor, where one future weighs
        exactly the tail rather than more than it."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, paths=dr.MIN_INTERVALLED_FUTURES, **_inputs(spec))
        assert isinstance(got, Decomposition)
        assert got.paths == dr.MIN_INTERVALLED_FUTURES

    def test_fewer_than_two_options_refuses(self):
        spec = _single_option_spec()
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "single_option"

    def test_no_verdict_on_a_one_option_run_refuses_as_single_option(self):
        """A library caller that passes no verdict: on a run that prices one
        option the refusal's fact holds, so it refuses; on a run that prices
        three it would not, so it raises (§0.1 item 44: a guard only a library
        caller reaches is pinned with a constructed call).
        *Kills it:* narrowing the guard to a verdict that is present, which
        reads `verdict.best` off None; or refusing the three-option call with
        "this run prices one option"."""
        spec = _single_option_spec()
        got = decompose(spec, **{**_inputs(spec), "verdict": None})
        assert isinstance(got, DecompositionRefusal)
        assert (got.code, got.reason) == ("single_option", "this run prices one option")
        assert format_decomposition(got).endswith(
            "not split (single_option): this run prices one option")
        spec = _fixture_spec(num_sims=40)
        with pytest.raises(ValueError, match="^no verdict was passed for a run that "
                                             "prices 3 options$"):
            decompose(spec, **{**_inputs(spec), "verdict": None})

    def test_two_options_do_not_refuse_as_single(self):
        spec = _drawing_but_dead_house_spec()
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, Decomposition)

    def test_one_live_channel_refuses_and_names_it(self):
        spec = load_config(str(EXAMPLES / "income_shock.yaml"))
        spec = dataclasses.replace(
            spec, simulation=dataclasses.replace(spec.simulation, num_sims=40))
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "one_channel"
        assert got.channel_id == channel_by_key("condo").id
        assert got.reason == "one channel is live on these 40 futures: the condo's costs"

    def test_two_live_channels_do_not_reach_the_one_channel_refusal(self):
        """The nearest legal call: the same shape with one more channel live."""
        spec = load_config(str(EXAMPLES / "income_shock.yaml"))
        spec = dataclasses.replace(
            spec,
            simulation=dataclasses.replace(spec.simulation, num_sims=40,
                                           value_growth_vol=0.05))
        assert len(_measure(spec).live) == 2
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, Decomposition)

    def test_every_volatility_at_zero_is_already_no_futures(self):
        """The config layer's own rule gets there first, and correctly: with
        every uncertainty input off there are no futures at all."""
        spec = _all_channels_spec(num_sims=40)
        assert single_path_run(spec)
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal) and got.code == "no_futures"

    def test_a_channel_that_draws_and_moves_nothing_leaves_one_margin(self):
        """The real-mode inflation trap with every correlation off:
        `single_path_run` reads a non-zero `inflation_vol` and says there are
        futures; there are, the economy draws on them, and every one prices the
        same margin — the measured fact the refusal states."""
        spec = _one_live_channel_spec(mode="real", inflation_vol=0.02)
        spec = dataclasses.replace(
            spec, simulation=dataclasses.replace(spec.simulation,
                                                 num_sims=40, condo_fee_vol=0.0))
        assert not single_path_run(spec)
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal) and got.code == "no_spread"
        assert re.fullmatch(r"the margin is identical on all 40 futures "
                            r"\(-?\$[\d,]+\.\d\d\)", got.reason), got.reason

    def test_a_constant_margin_refuses_with_two_channels_live(self):
        """§8 refusal 5: `Var(f) == 0` while channels move present values.

        Two identical owned options are moved by the market and the economy in
        lockstep, so both channels move both options, and `f` is still the same
        figure on every future.
        """
        spec = _twin_owners_spec()
        assert len(_measure(spec).live) == 2
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, DecompositionRefusal) and got.code == "no_spread"
        assert re.fullmatch(r"the margin is identical on all 64 futures \(\$[\d,]+\.\d\d\)",
                            got.reason), got.reason

    def test_one_dollar_of_difference_does_not_refuse(self):
        """The nearest legal call: the same two live channels, and a spread."""
        spec = _twin_owners_spec(differ=True)
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got, Decomposition)
        assert got.sd_margin > 0.0

    def test_more_futures_than_the_ceiling_refuses_before_pricing_anything(
            self, monkeypatch):
        """The call asks for 1,000,000 paths. Drawing them even once is above
        the ceiling, whatever number of streams would draw, so the stand-in
        for the pricer RAISES on the first evaluation instead of counting it: a
        broken gate fails here at once rather than running away. It is
        installed AFTER `_inputs`, whose own Monte Carlo run is not this
        module's.
        *Kills it:* deleting the gate, or moving it after the first matrix."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)

        def no_pricing(spec, streams=None, *, freeze=()):
            raise AssertionError(
                f"a matrix of {spec.simulation.num_sims:,} paths was priced: the "
                "budget gate must refuse before a single path is priced")

        monkeypatch.setattr(dr, "run_monte_carlo", no_pricing)
        got = decompose(spec, paths=1_000_000, **inputs)
        assert isinstance(got, DecompositionRefusal) and got.code == "budget"
        assert got.reason == (
            f"1,000,000 futures price 1,000,000 path evaluations before any "
            f"re-draw, above the ceiling of {EVALUATION_CEILING:,} [set in the engine]")
        # No route: nothing tells the reader what to run.
        assert "--decompose" not in got.reason

    def test_the_first_gate_is_exactly_the_ceiling(self):
        """Both sides of the pre-pricing gate: N at the ceiling passes it, one
        more refuses.
        *Kills it:* `>=` for `>`, or a gate that refuses earlier than the
        figure it names."""
        spec = _fixture_spec(num_sims=40)
        mc = run_monte_carlo(spec)
        verdict = compute_verdict(compute_deterministic(spec), mc,
                                  years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        assert dr._refusal_before_pricing(spec, mc, verdict, EVALUATION_CEILING) is None
        over = dr._refusal_before_pricing(spec, mc, verdict, EVALUATION_CEILING + 1)
        assert over is not None and over.code == "budget"

    def test_the_gate_on_k_prices_only_the_futures_it_counts_on(self, monkeypatch):
        """Past the first gate, the block prices its `N` futures once, counts
        the streams that drew on them, and refuses on that count before any
        re-draw: one matrix priced, and the reason names the count it measured.
        On the fixture every one of its eight streams draws.
        *Kills it:* gating on the live channels (a re-draw per stream would be
        priced first), or on any count but the one measured."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        spy = _Spy(monkeypatch)
        paths = 30_000
        got = decompose(spec, paths=paths, **inputs)
        assert isinstance(got, DecompositionRefusal) and got.code == "budget"
        assert spy.runs == [(paths, ())]
        k = 8
        largest = dr.largest_affordable_paths(k)
        assert got.reason == (
            f"30,000 futures with {k} streams drawing on them price up to "
            f"{planned_evaluations(paths, k, 2000):,} path evaluations, above the "
            f"ceiling of {EVALUATION_CEILING:,} [set in the engine]; the largest path "
            f"count within it is {largest:,}")
        # The figure counts the all-frozen run: N·(k+2) + 2,000·(k+1).
        assert planned_evaluations(paths, k, 2000) == paths * (k + 2) + 2000 * (k + 1)
        assert "--decompose" not in got.reason

    @pytest.mark.parametrize("k_draw", range(2, 9))
    def test_the_n_the_budget_refusal_names_is_the_largest_the_gate_admits(self, k_draw):
        """The figure the refusal prints is read off the gate's own cost
        model, so following it never meets the same refusal — and one more
        path would. The cost model is what the module SPENDS at most
        (`TestCost`), so the N it names also prices within the ceiling.
        *Kills it:* a closed form that drifts from `planned_evaluations`."""
        largest = dr.largest_affordable_paths(k_draw)
        assert largest >= dr.MIN_INTERVALLED_FUTURES
        assert planned_evaluations(largest, k_draw, dr._level_paths(largest)) <= EVALUATION_CEILING
        assert planned_evaluations(largest + 1, k_draw,
                                   dr._level_paths(largest + 1)) > EVALUATION_CEILING
        assert dr._budget_refusal(largest, k_draw) is None
        assert dr._budget_refusal(largest + 1, k_draw).code == "budget"

    def test_the_budget_gate_does_not_fire_at_the_ceiling(self):
        """Both sides of the boundary, without pricing either: the gate is a
        pure function of the figures it names."""
        paths = (EVALUATION_CEILING - LEVEL_PATHS * 8) // 9
        assert planned_evaluations(paths, 7, dr._level_paths(paths)) <= EVALUATION_CEILING
        assert dr._budget_refusal(paths, 7) is None
        over = dr._budget_refusal(paths + 1_000, 7)
        assert over is not None and over.code == "budget"


# ---------------------------------------------------------------------------
# 5. §8's one printing case with no shares
# ---------------------------------------------------------------------------

class TestEveryFutureAgrees:
    """§0.1 item 7: `P(f > 0) == 1` refuses the SPREAD register by name, in its
    own slot, and the level register still prints."""

    def test_p_of_f_positive_equal_to_one_refuses_the_spread_by_name(
            self, monkeypatch):
        """*Kills it:* returning `SpreadRegister(rows=())`, which leaves the
        reader and the formatter to infer why, or dropping the level register
        along with the shares."""
        spec = _every_future_agrees_spec()
        inputs = _inputs(spec)
        f = margin_per_path(dr._run(dr._spec_at(spec, spec.simulation.num_sims),
                                    dr.MATRIX_A), inputs["verdict"].best)
        assert float(np.mean(f > 0.0)) == 1.0
        spy = _Spy(monkeypatch)
        got = decompose(spec, **inputs)
        assert isinstance(got, Decomposition)
        assert isinstance(got.spread, RefusedSpread)
        assert not isinstance(got.spread, SpreadRegister)
        assert got.spread.code == "no_sign_variation"
        assert got.spread.code in SPREAD_REFUSAL_CODES
        # §0.1 item 36: the measured fact alone — nothing about what a re-draw
        # the block never priced would do.
        best = got.verdict.best
        assert got.spread.reason == (
            f"{best} is cheapest in all {spec.simulation.num_sims:,} of these futures")
        # ...and the level register, which the one-way binding still prints.
        assert len(got.level.rows) == len(got.live_channel_ids)
        # Nothing measured for the spread would be printed, so no `B` matrix
        # is priced: `A`, one re-draw per drawing stream (which is how the
        # live channels are known), the level register's freezes and the
        # all-frozen run, and nothing else.
        k = len(got.live_channel_ids)
        drawn = k + len([z for z in got.spread.structural_zeros
                         if z.kind == "dead_draw"])
        assert sum(1 for _, freeze in spy.runs if not freeze) == 1 + drawn
        assert len(spy.runs) == 1 + drawn + k + 1

    @pytest.mark.parametrize("share, refuses", [
        (0.0, True), (1.0, True), (1e-12, False), (1.0 - 1e-12, False),
        (0.0005, False), (0.9995, False), (0.5, False)])
    def test_the_guard_is_exactly_the_two_ends(self, share, refuses):
        """`_one_side_of_the_line`, both ways: exactly 0 and exactly 1 refuse,
        and one future in any count does not.
        *Kills it:* widening the guard by any tolerance, or dropping a side."""
        assert dr._one_side_of_the_line(share) is refuses

    def test_every_future_on_the_other_side_refuses_with_that_fact(self):
        """The P(f > 0) == 0 side, worded for it."""
        refusal = dr._no_sign_variation("rent", 400, 0.0, ())
        assert refusal.reason == "rent is cheapest in none of these 400 futures"
        with pytest.raises(ValueError):
            dr._no_sign_variation("rent", 400, 0.5, ())

    def test_a_disagreeing_future_prints_the_shares(self):
        """The nearest legal call: one future on the other side of zero."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, paths=40, **_inputs(spec))
        assert isinstance(got, Decomposition)
        assert isinstance(got.spread, SpreadRegister)
        assert got.spread.rows
        # One of the two names the top row, whichever way it resolved.
        assert (got.spread.leading_channel_id is None) != (
            got.spread.unresolved_top_channel_id is None)


# ---------------------------------------------------------------------------
# 5b. The level register's identity, refused when it does not hold
# ---------------------------------------------------------------------------

class TestTheFreezeIdentity:
    """§0.1 item 19: with every channel frozen, every path prices ONE margin.
    `all_frozen_path_spread` is exactly 0.0 on a correct engine, and a non-zero
    value means a draw site escaped the mask — then the level register may not
    print as though the identity held."""

    @staticmethod
    def _leaky_mask(monkeypatch, escaped: int):
        """The all-frozen run with one channel left out of its mask: a real
        escaped draw site, priced by the real engine, not a doctored array."""
        inner = dr.run_monte_carlo

        def leaky(spec, streams=None, *, freeze=()):
            if tuple(freeze) == dr.ALL_CHANNEL_IDS:
                freeze = tuple(c for c in freeze if c != escaped)
            return inner(spec, streams, freeze=freeze)

        monkeypatch.setattr(dr, "run_monte_carlo", leaky)

    def test_a_draw_that_escapes_the_mask_refuses_the_whole_block(self, monkeypatch):
        """*Kills it:* deleting the check, which prints a level register — and
        the sentence "all 7 frozen reproduces the central case" — over a run
        where the paths disagree with each other."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        self._leaky_mask(monkeypatch, escaped=channel_by_key("shelter").id)
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "freeze_leak" and got.code in REFUSAL_CODES
        assert re.fullmatch(r"with every channel frozen, the margins of the 40 paths "
                            r"differ by up to \$\S+", got.reason), got.reason
        spread = float(got.reason.rsplit("$", 1)[1].replace(",", ""))
        assert spread > 0.0

    def test_a_leak_of_a_few_hundred_millionths_of_a_dollar_refuses(self, monkeypatch):
        """The same escaped draw site, on a channel sized so small that the
        paths differ by less than a millionth of a dollar: any difference
        refuses, not a large one. There is no real leak to witness it, so it
        is constructed (§0.1 item 44).
        *Kills it:* narrowing the check to a spread above $1 or above $1e-6,
        either of which prints the level register over this run."""
        spec = _fixture_spec(num_sims=40)
        spec = dataclasses.replace(spec, simulation=dataclasses.replace(
            spec.simulation, investment_return_vol=1e-14))
        inputs = _inputs(spec)
        self._leaky_mask(monkeypatch, escaped=channel_by_key("portfolio").id)
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got, DecompositionRefusal) and got.code == "freeze_leak"
        spread = float(got.reason.rsplit("$", 1)[1].replace(",", ""))
        assert 0.0 < spread < 1e-6, spread
        assert format_decomposition(got).endswith(f"not split (freeze_leak): {got.reason}")

    def test_an_exact_mask_does_not_refuse(self):
        """The nearest legal call: the same run with the mask whole.
        *Kills it:* widening the check to fire on a spread of exactly 0.0."""
        spec = _fixture_spec(num_sims=40)
        got = decompose(spec, paths=40, **_inputs(spec))
        assert isinstance(got, Decomposition)
        assert got.level.all_frozen_path_spread == 0.0


class TestTheIncomeStreamIsReDrawn:
    """The income stream is re-drawn and measured like every other stream that
    drew, on the block's own futures: its `dead_draw` row says re-drawing it
    moved nothing, and a re-draw that moved something raises. Both rest on the
    re-draw being priced."""

    def test_every_stream_that_drew_is_re_drawn_including_the_income_stream(
            self, monkeypatch):
        """*Kills it:* re-drawing every drawing stream but the income stream,
        which leaves its row's clause asserted from structure (§0.1 item 39)."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        inner, swaps = dr._run, []

        def spy(spec_at_paths, matrix_id, swapped=None, freeze=()):
            if swapped:
                swaps.append(dict(swapped))
            return inner(spec_at_paths, matrix_id, swapped, freeze)

        monkeypatch.setattr(dr, "_run", spy)
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got, Decomposition)
        assert swaps == [{stream: dr.MATRIX_B} for stream in range(8)]
        income = [z for z in got.spread.structural_zeros
                  if z.channel_id == dc_income()]
        assert [z.kind for z in income] == ["dead_draw"]

    def test_a_re_draw_of_the_income_stream_that_moves_a_value_refuses(self, monkeypatch):
        """The income stream feeds the affordability report only, so no real
        run moves a present value with it; the move is constructed on the one
        re-draw, through `decompose` itself (§0.1 item 44), and the check
        refuses the block with the move it measured (§0.1 item 58).
        *Kills it:* skipping the income stream's re-draw, or the check."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        inner = dr._run

        def moving_income(spec_at_paths, matrix_id, swapped=None, freeze=()):
            result = inner(spec_at_paths, matrix_id, swapped, freeze)
            if swapped == {dc_income(): dr.MATRIX_B}:
                result.rent.pvs = result.rent.pvs + 1.0
            return result

        monkeypatch.setattr(dr, "_run", moving_income)
        got = decompose(spec, paths=40, **inputs)
        allowance = dr.identity_budget(inputs["det"], inputs["verdict"])
        assert (got.code, got.reason) == ("income_moved", (
            f"re-drawing the income stream moved an option's present value on these 40 "
            f"futures by up to $1, above ${dr.floored_figure(allowance, 3)}"))


class TestTheIdentityIsGated:
    """§3.4 as amended by §0.1 item 19: the all-frozen margin is the central
    case's own to within a ULP budget. The budget used to live only in this
    file, so the product would have printed "all N frozen reproduces the
    central case" at any deviation. It now lives in `decomposition_math`, the
    assembler refuses the WHOLE block past it, and this file imports it."""

    @staticmethod
    def _offset_all_frozen(monkeypatch, offset: float):
        """The all-frozen run with every path of the central case's winner
        moved by one constant: the paths still agree with EACH OTHER (so
        `freeze_leak` stays quiet) and the margin they agree on is `offset`
        from the central case's. Priced by the real engine; only that one
        run's array is moved."""
        inner = dr.run_monte_carlo

        def offset_run(spec, streams=None, *, freeze=()):
            result = inner(spec, streams, freeze=freeze)
            if tuple(freeze) == dr.ALL_CHANNEL_IDS:
                result.rent.pvs = result.rent.pvs + offset
            return result

        monkeypatch.setattr(dr, "run_monte_carlo", offset_run)

    def test_a_margin_off_the_central_case_refuses_the_whole_block(self, monkeypatch):
        """*Kills it:* deleting the gate, which prints every register — and
        "reproduces the central case" — over a freeze that does not."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        assert inputs["verdict"].best == "rent"
        self._offset_all_frozen(monkeypatch, 0.01)
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got, DecompositionRefusal)
        assert got.code == "identity_failed" and got.code in REFUSAL_CODES
        budget = dr.identity_budget(inputs["det"], inputs["verdict"])
        frozen = dr.margin_per_path(
            dr._run(dr._spec_at(spec, 40), dr.MATRIX_A, freeze=dr.ALL_CHANNEL_IDS), "rent")
        apart = abs(float(frozen[0]) - inputs["verdict"].margin_pv)
        assert got.reason == (
            f"with every channel frozen, the 40 paths price a margin of "
            f"${inputs['verdict'].margin_pv - 0.01:,.2f} against the central case's "
            f"${inputs['verdict'].margin_pv:,.2f}, ${dr.ceiled_figure(apart, 3)}"
            f" apart, above the ${dr.floored_figure(budget, 3)} this check allows")

    def test_at_the_budget_it_holds_and_one_step_past_it_refuses(self, monkeypatch):
        """Both sides of the boundary, on the run's own measured deviation:
        a budget exactly equal to it holds, the next float below it does not.
        *Kills it:* `<` for `<=` (the first half), or no gate (the second)."""
        spec = _fixture_spec(num_sims=40)
        inputs = _inputs(spec)
        measured = decompose(spec, paths=40, **inputs)
        assert isinstance(measured, Decomposition)
        deviation = measured.level.all_frozen_deviation
        assert deviation > 0.0, "a zero deviation cannot sit strictly above a budget"
        monkeypatch.setattr(dr, "identity_budget", lambda det, verdict: deviation)
        assert isinstance(decompose(spec, paths=40, **inputs), Decomposition)
        monkeypatch.setattr(dr, "identity_budget",
                            lambda det, verdict: float(np.nextafter(deviation, 0.0)))
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got, DecompositionRefusal) and got.code == "identity_failed"

    def test_the_budget_is_the_math_module_s_over_the_terms_summed(self):
        """One home: the assembler's budget is `identity_ulp_budget` over each
        option's breakdown terms added by size (its total is their sum), and
        nothing else."""
        spec = _fixture_spec(num_sims=40)
        det = compute_deterministic(spec)
        verdict = compute_verdict(det, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        options = (det.condo, det.house, det.rent)
        assert all(o.total_pv == sum(o.breakdown.values()) for o in options)
        terms = [sum(abs(x) for x in o.breakdown.values()) for o in options]
        assert dr.identity_budget(det, verdict) == 8.0 * np.spacing(max(terms))

    def test_a_small_net_total_over_large_terms_is_not_refused(self):
        """Why the budget is scaled by the TERMS. The twin all-cash owners net
        ~$400k of equity against their costs to totals of $23,170, and the
        all-frozen margin sits one ulp of those terms from the central case —
        32 ulps of the net total. Scaled by the total, the gate refused this
        legal run: an over-wide refusal that fails only on calls that were
        always legal. *Kills it:* scaling the budget by `total_pv` alone."""
        spec = _twin_owners_spec(differ=True)
        inputs = _inputs(spec)
        det = inputs["det"]
        net = max(abs(det.condo.total_pv), abs(det.house.total_pv))
        got = decompose(spec, **inputs)
        assert isinstance(got, Decomposition)
        assert got.level.all_frozen_deviation > 8.0 * np.spacing(net), (
            "the precondition: this run's deviation is beyond a budget scaled by "
            "the net total, so the test fails if the gate is ever scaled that way")


def test_the_level_rule_decides_which_level_rows_print_as_resolved(monkeypatch):
    """`decomposition_math.level_is_resolved` decides each level row: with the
    rule inverted, every row on the fixture turns the other way, in the
    register and in the text, where a row prints behind `not resolved:`
    exactly when the rule says no.
    *Kills it:* the table's mask computing the rule a second time, which the
    inverted rule leaves as it was."""
    spec = _fixture_spec(num_sims=40)
    inputs = _inputs(spec)
    as_is = decompose(spec, paths=40, **inputs)
    original = dm.level_is_resolved
    monkeypatch.setattr(dm, "level_is_resolved",
                        lambda delta, error: not original(delta, error))
    inverted = decompose(spec, paths=40, **inputs)
    before = [isinstance(row.level, ResolvedLevel) for row in as_is.level.rows]
    after = [isinstance(row.level, ResolvedLevel) for row in inverted.level.rows]
    assert before and after == [not resolved for resolved in before]
    text = format_decomposition(inverted).split("THE LEVEL", 1)[1]
    for row, resolved in zip(inverted.level.rows, after):
        (line,) = [line for line in text.splitlines()
                   if line.startswith(f"  {channel(row.channel_id).label} ")]
        assert ("not resolved:" in line) == (not resolved), line


# ---------------------------------------------------------------------------
# 6. The structural zeros only the liveness predicates can see
# ---------------------------------------------------------------------------

class TestStructuralZeros:

    def test_a_channel_that_draws_and_moves_nothing_gets_a_measured_row(self):
        """The house here has no maintenance rate, no cost lines and no events:
        its maintenance shock is drawn every year and multiplied by nothing.
        Its row carries the stream, the futures and the threshold it was
        measured on."""
        spec = _drawing_but_dead_house_spec()
        inputs = _inputs(spec)
        got = decompose(spec, **inputs)
        dead = [z for z in got.spread.structural_zeros if z.kind == "dead_draw"]
        assert [z.channel_id for z in dead] == [4]
        assert dead[0].measured_paths == spec.simulation.num_sims
        assert dead[0].move_threshold == dr.identity_budget(inputs["det"],
                                                            inputs["verdict"])
        assert dead[0].label == "the house's costs"

    def test_a_measured_row_names_all_the_block_s_futures_above_the_level_s(self):
        """Above 2,000 futures the level register reads the first 2,000, while
        draws and liveness are measured on all N: the row names N, and the
        printed row says N.
        *Kills it:* the row carrying the level's path count, which every run
        at N <= 2,000 agrees with."""
        spec = _drawing_but_dead_house_spec()
        got = decompose(spec, paths=2100, **_inputs(spec))
        assert (got.paths, got.level.paths) == (2100, 2000)
        (dead,) = [z for z in got.spread.structural_zeros if z.kind == "dead_draw"]
        assert dead.measured_paths == 2100
        assert ("  the house's costs: drawn on these 2,100 futures, and re-drawing it "
                "moved no option's present value by more than $"
                in format_decomposition(got))

    def test_a_live_channel_gets_no_dead_draw_row(self):
        """The nearest legal call: the same house with its volatility on."""
        spec = _drawing_but_dead_house_spec()
        spec = dataclasses.replace(
            spec,
            simulation=dataclasses.replace(spec.simulation,
                                           house_maintenance_vol=0.2),
            house=dataclasses.replace(spec.house, annual_maintenance_rate=0.01))
        got = decompose(spec, **_inputs(spec))
        assert 4 in got.live_channel_ids
        assert not [z for z in got.spread.structural_zeros
                    if z.kind == "dead_draw"]

    def test_one_stream_never_gets_two_rows(self):
        """The real-mode inflation trap on the fixture: the economy draws and
        moves nothing, and is named once."""
        spec = _fixture_spec(num_sims=40)
        spec = dataclasses.replace(
            spec,
            economic=dataclasses.replace(spec.economic, mode="real"),
            simulation=dataclasses.replace(
                spec.simulation, corr_inflation_condo=0.0,
                corr_inflation_house=0.0, corr_inflation_other=0.0,
                corr_inflation_event_cost=0.0))
        got = decompose(spec, paths=40, raw=_fixture_raw(), **{
            k: v for k, v in _inputs(spec).items() if k != "raw"})
        assert 0 not in got.live_channel_ids
        ids = [z.channel_id for z in got.spread.structural_zeros
               if z.channel_id is not None]
        assert ids.count(0) == 1, f"the economy is named {ids.count(0)} times"

    @pytest.mark.parametrize("corr_condo", [0.0, 0.5])
    def test_the_economy_s_dead_draw_is_drawn_and_moves_nothing(self, corr_condo):
        """The row's facts — drawn, and its re-draw moving no present value —
        on both configs that reach it: every correlation off, and one ON whose
        shock is dead (the condo's fee at zero volatility). Each fact checked
        with held generators, not the engine's addressed matrices."""
        spec = _fixture_spec(num_sims=40)
        spec = dataclasses.replace(
            spec,
            economic=dataclasses.replace(spec.economic, mode="real"),
            simulation=dataclasses.replace(
                spec.simulation, corr_inflation_condo=corr_condo, condo_fee_vol=0.0,
                corr_inflation_house=0.0, corr_inflation_other=0.0,
                corr_inflation_event_cost=0.0))
        got = decompose(spec, **_inputs(spec))
        dead = [z for z in got.spread.structural_zeros if z.channel_id == 0]
        assert len(dead) == 1 and dead[0].kind == "dead_draw"
        assert spec.economic.mode == "real"

        def held(economy_seed):
            seeds = {c: 1000 + c for c in dr.STREAM_IDS}
            seeds[0] = economy_seed
            return {c: np.random.default_rng(s) for c, s in seeds.items()}

        streams = held(1000)
        before = streams[0].bit_generator.state["state"]["state"]
        a = run_monte_carlo(spec, streams)
        assert streams[0].bit_generator.state["state"]["state"] != before
        b = run_monte_carlo(spec, held(2024))
        for name in ("condo", "house", "rent"):
            left, right = getattr(a, name), getattr(b, name)
            if left is not None:
                assert np.asarray(left.pvs).tobytes() == np.asarray(right.pvs).tobytes(), name


# ---------------------------------------------------------------------------
# 7. The cost model, measured rather than asserted
# ---------------------------------------------------------------------------

class TestCost:

    def test_the_gate_s_figure_is_what_the_module_prices(self, monkeypatch):
        """ONE formula for the gate and for the count: §9's cost model left
        out the all-frozen run that §3.4 prices at `m` paths, and the gate
        measured that figure while the module spent `m` more — so the N the
        budget refusal recommended priced above the ceiling it was chosen
        under. The count here is taken by replacing the pricer, never read
        off the formula it checks.
        *Kills it:* dropping the all-frozen run from `planned_evaluations`."""
        spy = _Spy(monkeypatch)
        spec = _drawing_but_dead_house_spec(num_sims=40)
        inputs = _inputs(spec)
        spy.runs.clear()
        got = decompose(spec, paths=40, **inputs)
        assert isinstance(got.spread, SpreadRegister)
        k_live = len(got.live_channel_ids)
        k_draw = k_live + len([z for z in got.spread.structural_zeros
                               if z.kind == "dead_draw"])
        assert (k_live, k_draw) == (2, 3)
        level = dr._level_paths(40)
        # What it spends: A, B, one re-draw per drawing stream, one freeze per
        # live channel and the all-frozen run...
        assert spy.evaluations == 40 * (k_draw + 2) + level * (k_live + 1)
        # ...which the gate's figure bounds, and reaches when every drawing
        # stream is live.
        assert spy.evaluations <= planned_evaluations(40, k_draw, level)
        assert planned_evaluations(40, k_live, level) == (
            40 * (k_live + 2) + level * (k_live + 1))
        # And the runs themselves are the matrices §3.3 and §3.4 name.
        assert sum(1 for _, freeze in spy.runs if not freeze) == k_draw + 2
        assert sum(1 for _, freeze in spy.runs if len(freeze) == 1) == k_live
        assert sum(1 for _, freeze in spy.runs
                   if len(freeze) == len(dr.ALL_CHANNEL_IDS)) == 1

    def test_a_run_where_every_future_agrees_prices_what_the_formula_says(
            self, monkeypatch):
        """When every future names one winner the spread register prices no
        `B` (§0.1 item 7), and the same formula says so with
        `spread_priced=False`: the re-draws are still priced, because they are
        how the live channels are known. The gate cannot know that before it
        prices them, so it takes the default — the most the module can spend —
        and its figure is an upper bound here, which the refusal says
        ("up to").
        *Kills it:* a formula that counts `B` on this run, or a gate figure
        below what such a run spends."""
        spec = _every_future_agrees_spec()
        inputs = _inputs(spec)
        spy = _Spy(monkeypatch)
        got = decompose(spec, **inputs)
        assert isinstance(got.spread, RefusedSpread)
        n, k = spec.simulation.num_sims, len(got.live_channel_ids)
        assert not got.spread.structural_zeros
        level = dr._level_paths(n)
        assert spy.evaluations == planned_evaluations(n, k, level, spread_priced=False)
        assert spy.evaluations == n * (k + 1) + level * (k + 1)
        assert spy.evaluations < planned_evaluations(n, k, level)

    def test_the_n_the_refusal_names_on_the_fixture_prices_within_the_ceiling(self):
        """The fixture's eight drawing streams, in figures: N·10 + 2,000·9 fits
        the 250,000 ceiling up to N = 23,200 exactly. A count that left out the
        all-frozen run once named an N that priced above the ceiling it was
        chosen under.
        *Kills it:* reading the N off a count that leaves out a run."""
        assert dr.largest_affordable_paths(8) == 23_200
        assert planned_evaluations(23_200, 8, dr._level_paths(23_200)) == 250_000
        assert planned_evaluations(23_201, 8, dr._level_paths(23_201)) > 250_000

    def test_the_sample_size_override_is_the_sample_size(self, monkeypatch):
        spy = _Spy(monkeypatch)
        spec = _fixture_spec(num_sims=400)
        inputs = _inputs(spec)
        spy.runs.clear()
        got = decompose(spec, paths=50, **inputs)
        assert got.paths == 50
        assert all(paths in (50, dr._level_paths(50)) for paths, _ in spy.runs)


# ---------------------------------------------------------------------------
# 8. §4 and §5 mechanism 4 — the resolved branch, on tables with known answers
# ---------------------------------------------------------------------------

class TestInteractionBranches:
    """The fixture takes §4's REFUSAL branch at its committed paths, so the
    resolved branch is exercised here on synthetic tables. The estimators are
    the shipped ones; only `f` is constructed."""

    @staticmethod
    def _interacting_tables(n=4000, seed=11):
        """Two channels whose product is most of the variance, so ΣS < 1."""
        rng = np.random.default_rng(seed)
        a1, a2 = rng.normal(size=n), rng.normal(size=n)
        b1, b2 = rng.normal(size=n), rng.normal(size=n)

        def f(x1, x2):
            return 0.2 * x1 + 0.2 * x2 + 3.0 * x1 * x2

        f_a = f(a1, a2)
        f_b = f(b1, b2)
        f_ab = np.stack([f(b1, a2), f(a1, b2)], axis=0)
        return f_a, f_b, f_ab

    def test_the_residual_prints_when_the_sum_resolves_below_one(self):
        f_a, f_b, f_ab = self._interacting_tables()
        widths = {0: (Width("economic.inflation_vol", "1%", "assistant"),),
                  1: (Width("simulation.value_growth_vol", "7%", "user"),)}
        register = dr._spread_register(f_a, f_b, f_ab, (0, 1), widths, seed=42, dead=())
        assert isinstance(register.interaction, ResolvedInteraction)
        assert register.interaction.first_order_sum_ci.high < 1.0
        assert register.interaction.residual > 0.0

    def test_a_config_with_no_sources_block_tags_every_width_unattributed(self):
        """End to end, through the widths the assembler reads from the spec: a
        shipped config with no `sources:` block states its volatilities with
        nobody's name on them, and every width is tagged so rather than filed
        under the assistant."""
        spec = load_config(str(EXAMPLES / "basic_config.yaml"))
        assert not spec.sources.declared
        got = decompose(spec, paths=200, **_inputs(spec))
        assert isinstance(got, Decomposition) and isinstance(got.spread, SpreadRegister)
        for row in got.spread.rows:
            assert row.widths and {w.source for w in row.widths} == {"unattributed"}

    def test_the_refused_branch_has_no_residual_at_all(self):
        """A purely additive model at a small sample, where ΣS's interval
        straddles 1 — the branch the fixture itself takes."""
        rng = np.random.default_rng(5)
        n = 300
        a1, a2 = rng.normal(size=n), rng.normal(size=n)
        b1, b2 = rng.normal(size=n), rng.normal(size=n)
        f_a, f_b = a1 + a2, b1 + b2
        f_ab = np.stack([b1 + a2, a1 + b2], axis=0)
        widths = {0: (), 1: ()}
        register = dr._spread_register(f_a, f_b, f_ab, (0, 1), widths, seed=7, dead=())
        assert isinstance(register.interaction, RefusedInteraction)
        assert not hasattr(register.interaction, "residual")

    def test_a_row_is_unresolved_if_either_figure_is(self):
        """§0.1 item 11, on a table built so that exactly one figure is out of
        range: the row must not print a resolved share beside noise."""
        rng = np.random.default_rng(3)
        n = 500
        a1, a2 = rng.normal(size=n), rng.normal(size=n)
        b1, b2 = rng.normal(size=n), rng.normal(size=n)
        # Channel 1 is dead in `f`, so its first-order estimate scatters around
        # zero and lands negative on this seed while its total stays at 0.
        f_a, f_b = a1, b1
        f_ab = np.stack([b1, a1 - 1e-9 * b2], axis=0)
        register = dr._spread_register(f_a, f_b, f_ab, (0, 1), {0: (), 1: ()},
                                       seed=13, dead=())
        dead = next(r for r in register.rows if r.channel_id == 1)
        assert isinstance(dead.shares, UnresolvedShares) or dead.shares.alone >= 0.0


# ---------------------------------------------------------------------------
# 9. §7's published figures, on the committed fixture at its committed paths
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixture_block():
    """The fixture's own decomposition, at seed 42 and its committed 2,000
    paths. Module-scoped: it costs 34,000 evaluations and every assertion
    below reads the same object, so the suite pays for it once.

    The seed and the path count are named here so that reseeding the fixture is
    a deliberate act with a failing test attached, not a silent re-tuning.
    """
    spec = _fixture_spec()
    assert spec.simulation.random_seed == 42
    assert spec.simulation.num_sims == 2000
    inputs = _inputs(spec, raw=_fixture_raw())
    got = decompose(spec, **inputs)
    assert isinstance(got, Decomposition)
    return got


def _share(row):
    return (row.shares.alone if isinstance(row.shares, ResolvedShares)
            else row.shares.provisional_alone)


def _row(block, key):
    target = channel_by_key(key).id
    return next(r for r in block.spread.rows if r.channel_id == target)


def _level(block, key):
    target = channel_by_key(key).id
    return next(r.level for r in block.level.rows if r.channel_id == target)


class TestThePublishedFigures:
    """T6 and the figure comparison: the channel with most of the spread moves
    the answer by nothing that resolves, and the channel with a tenth of it is
    what made the central case and the futures disagree.

    Inequalities with margin, never equalities to a published bound (§0.1 item
    15): point estimates never touch the bootstrap, but every bound depends on
    the salt and the resample count, and nobody tunes a salt to match a figure
    in a document.
    """

    def test_the_spread_register_names_the_portfolio(self, fixture_block):
        block = fixture_block
        assert block.spread.leading_channel_id == channel_by_key("portfolio").id
        assert _share(_row(block, "portfolio")) == pytest.approx(0.877, abs=0.01)
        assert _row(block, "portfolio").flip == pytest.approx(0.41, abs=0.02)
        # On the LOWER bootstrap bound, not the point estimate (T6).
        assert _row(block, "portfolio").shares.alone_ci.low > 0.7

    def test_the_level_register_names_the_tenancy(self, fixture_block):
        block = fixture_block
        assert block.level.leading_channel_id == channel_by_key("shelter").id
        shelter = _level(block, "shelter")
        assert isinstance(shelter, ResolvedLevel)
        assert shelter.delta > 100_000
        assert _share(_row(block, "shelter")) < 0.15

    def test_the_channel_with_most_of_the_spread_moves_nothing_that_resolves(
            self, fixture_block):
        portfolio = _level(fixture_block, "portfolio")
        assert isinstance(portfolio, IndistinguishableLevel)
        assert abs(portfolio.provisional_delta) < 2.0 * portfolio.se

    def test_the_house_s_costs_are_a_resolved_level_and_an_unresolved_share(
            self, fixture_block):
        """§0.1 item 18(a): §7's draft filed -$886 ± $179 under
        "indistinguishable from zero", and 4.95 SE is RESOLVED. The draft
        printed a real effect as noise, which is the failure this register
        exists to prevent."""
        house = _level(fixture_block, "house")
        assert isinstance(house, ResolvedLevel)
        assert abs(house.delta) > 2.0 * house.se
        assert isinstance(_row(fixture_block, "house").shares, UnresolvedShares)

    def test_the_first_order_shares_refuse_at_this_sample_size(self, fixture_block):
        interaction = fixture_block.spread.interaction
        assert isinstance(interaction, RefusedInteraction)
        assert interaction.first_order_sum > 1.0
        assert interaction.first_order_sum_ci.high > 1.0

    def test_the_all_frozen_identity_holds_on_the_committed_sample(
            self, fixture_block):
        spec = _fixture_spec()
        det = compute_deterministic(spec)
        budget = dr.identity_budget(det, fixture_block.verdict)
        assert fixture_block.level.all_frozen_path_spread == 0.0
        assert fixture_block.level.all_frozen_deviation <= budget
        assert fixture_block.level.all_frozen_margin == pytest.approx(
            fixture_block.verdict.margin_pv, abs=budget)

    def test_the_two_samples_of_p_best_are_both_reported(self, fixture_block):
        """§0.1 item 1: `verdict.prob_best` is the LEGACY binding's sample and
        `prob_best_base` is this register's own. They differ by sampling noise
        and both are reported; a build that borrowed the verdict's figure would
        make them equal to the bit."""
        block = fixture_block
        assert block.level.prob_best_base != block.verdict.prob_best
        assert block.level.prob_best_base == pytest.approx(
            block.verdict.prob_best, abs=0.03)
        # ...and the register's own figure is a frequency of its OWN sample.
        assert block.level.prob_best_base * block.level.paths == pytest.approx(
            round(block.level.prob_best_base * block.level.paths), abs=1e-9)

    def test_every_width_on_the_fixture_is_declared(self, fixture_block):
        """The fixture's `sources:` block claims every key it sets, so no
        width is tagged `unattributed`."""
        for row in fixture_block.spread.rows:
            assert all(w.source != "unattributed" for w in row.widths), row.channel_id

    def test_the_economy_row_names_the_vols_its_correlations_pull(
            self, fixture_block):
        """§0.1 item 6: the cell that lists only the rho keys is wrong, because
        which vols are pulled depends on which rho is non-zero."""
        widths = _row(fixture_block, "economy").widths
        keys = [w.key for w in widths]
        assert "economic.inflation_vol" in keys
        assert "simulation.corr_inflation_condo" in keys
        pulled = [w for w in widths if w.note]
        assert {"simulation.condo_fee_vol", "simulation.house_maintenance_vol",
                "simulation.other_cost_vol"} <= {w.key for w in pulled}
        assert any(w.note == "pulled by simulation.corr_inflation_condo = 0.5; rho "
                           "squared 0.25" for w in pulled)

    def test_the_gap_is_the_subtraction_of_the_two_figures_carried(
            self, fixture_block):
        """§0.1 item 2: the gap is a subtraction, never a stored number.

        The two figures are on the same sample — the level register's own — so
        the subtraction cannot disagree with them. The shifts account for most
        of it and the residue is named rather than absorbed.
        """
        level = fixture_block.level
        gap = level.all_frozen_margin - level.futures_margin
        assert gap == pytest.approx(100_876, abs=200)
        assert level.accounted_for == pytest.approx(98_114, abs=200)
        assert abs(level.accounted_for) < abs(gap)

    def test_every_width_on_every_row_carries_its_source_class(
            self, fixture_block):
        """§7 rule 7: inline on the row, never a trailing footnote — and read
        from `spec.sources`, never inferred from the key's name."""
        for row in fixture_block.spread.rows:
            assert row.widths, f"channel {row.channel_id} has no width at all"
            for width in row.widths:
                assert width.source in ("user", "assistant", "anchor",
                                        "unattributed")

    def test_the_three_registers_arrive_together(self, fixture_block):
        """The spread, the level and the reversal register arrive together,
        and the structural zero names the row that carries its solved rates."""
        assert fixture_block.spread.rows and fixture_block.level.rows
        register = fixture_block.reversal
        assert register.exact, "the fixture states a renewal ladder"
        keys = {row.key for row in register.exact}
        assert "house.mortgage_renewal_rates" in keys
        zeros = {z.reversal_key for z in register.structural_zeros}
        assert "house.mortgage_renewal_rates" in zeros


# ---------------------------------------------------------------------------
# The top row of each register: decided once, here, and read by every surface
# ---------------------------------------------------------------------------

class TestTheTopRowIsDecidedOnce:
    """Both registers name their top row by ONE rule (`_top_row`): the largest
    POINT estimate over every row, resolved or not, which leads only if it
    resolved. The formatter and the serializer read the result; neither
    re-derives it, so the text and the JSON cannot disagree about it."""

    @pytest.mark.parametrize("points, expected", [
        # the largest resolved: it leads
        ([(6, 0.88, True), (5, 0.10, True)], (6, None)),
        # an unresolved row larger than every resolved one: nothing leads
        ([(4, 0.01, True), (3, 1.07, False)], (None, 3)),
        # an unresolved row SMALLER than the resolved leader takes nothing
        ([(6, 0.88, True), (4, -0.001, False)], (6, None)),
        # no row resolves: the largest is the unresolved top
        ([(4, 90.0, False), (5, 1.0, False)], (None, 4)),
        # a tie on the point goes to the first row in live-channel order
        ([(3, 0.5, True), (4, 0.5, False)], (3, None)),
        ([], (None, None)),
    ], ids=["resolved-top", "unresolved-top", "small-unresolved",
            "none-resolve", "tie", "empty"])
    def test_the_rule(self, points, expected):
        """*Kills it:* selecting over the resolved rows only (the second case
        then promotes the 0.01), or suppressing the leader whenever any row is
        unresolved (the third case then loses it)."""
        assert dr._top_row(points) == expected

    def test_an_unresolved_largest_share_leads_nothing_in_text_or_json(self):
        """examples/rent_vs_condo_vs_house.yaml: the condo's costs carry a
        provisional share above 1 that does not resolve, and the house's costs
        resolve at about 0.01. The JSON named the house's costs as leading,
        and its maintenance volatility as the figure to check first, while the
        text said no channel leads. The register now carries the answer: the
        JSON names the unresolved top, and the text calls no row the largest
        (§0.1 item 35), with the condo's row behind "not resolved".
        *Kills it:* the old resolved-only selection."""
        spec = load_config(str(EXAMPLES / "rent_vs_condo_vs_house.yaml"))
        got = decompose(spec, **_inputs(spec))
        assert isinstance(got.spread, SpreadRegister)
        condo = channel_by_key("condo").id
        top = next(r for r in got.spread.rows if r.channel_id == condo)
        assert isinstance(top.shares, UnresolvedShares)
        assert (got.spread.leading_channel_id,
                got.spread.unresolved_top_channel_id) == (None, condo)
        doc = decomposition_to_dict(got)["spread"]
        assert (doc["leading_channel_id"], doc["unresolved_top_channel_id"]) == (
            None, condo)
        block = format_decomposition(got)
        assert "largest alone share" not in block
        assert any(line.startswith("  the condo's costs       not resolved: ")
                   for line in block.splitlines())

    def test_an_unresolved_largest_shift_is_the_one_the_closing_names(self):
        """examples/basic_config.yaml, a tie: the house's costs resolve at
        about +$252 and the condo's costs move the margin by about +$390
        without resolving, taking P(house cheapest) out of the tie band. The
        closing called the house's costs the largest single shift; the
        register now names the condo's costs as its unresolved top, and the
        text calls no row the largest.
        *Kills it:* the old resolved-only selection."""
        spec = load_config(str(EXAMPLES / "basic_config.yaml"))
        got = decompose(spec, **_inputs(spec))
        condo, house = channel_by_key("condo").id, channel_by_key("house").id
        levels = {r.channel_id: r.level for r in got.level.rows}
        assert isinstance(levels[house], ResolvedLevel)
        assert isinstance(levels[condo], IndistinguishableLevel)
        assert abs(levels[condo].provisional_delta) > abs(levels[house].delta)
        assert (got.level.leading_channel_id,
                got.level.unresolved_top_channel_id) == (None, condo)
        doc = decomposition_to_dict(got)["level"]
        assert (doc["leading_channel_id"], doc["unresolved_top_channel_id"]) == (
            None, condo)
        block = format_decomposition(got)
        assert "largest shift in size" not in block
