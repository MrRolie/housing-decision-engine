"""Which risk decides it — THE ASSEMBLER (spec §0.1 item 17).

It turns one spec into the `DecompositionOutcome` the other pieces exchange:
the estimators (`decomposition_math`) take arrays, the reversal solver
(`break_even`) answers about stated inputs, and the formatter
(`decomposition_text`) renders what this module builds. Its surface is

    decompose(spec, *, det, mc, verdict, raw, prior) -> DecompositionOutcome

plus the two predicates the block's cost and its refusals turn on
(`live_channels`, `channels_that_draw`), the margin (`margin_per_path`) and
the one cost model (`planned_evaluations`, `largest_affordable_paths`). What
each refusal and figure means is `docs/reference/API_CONTRACT.md`'s.

WHAT IT DOES, in the order it does it, because the order is the cost model:

  1. the refusals decidable from the spec and the flags — no futures, one
     option, no live channel or one, the budget gate, too few futures to
     interval. They fire before a single path is priced;
  2. the `A` matrix, and the two refusals only it can decide: a margin that
     is identical on every future (the whole block), and every future on one
     side of the line (the spread register alone, which then prices no `B`);
  3. otherwise `B` and one `A_B^(c)` per live channel, addressed per path;
  4. the level register — the freeze mask, paired against `A`'s own first
     paths — and the all-frozen run whose identity, failing, refuses the whole
     block (`freeze_leak`, `identity_failed`);
  5. the reversal register: `break_even.reversal_register`'s rows and
     structural zeros, plus the dead-draw rows only this module can see.

Every refusal is a judgment about the DATA and so is this module's; the
formatter renders a refusal and never decides one.

TWO THINGS THIS MODULE IS CAREFUL NOT TO BE. It is not a second verdict:
every probability it reports is a frequency of `f`'s own sign on paths it
priced, and `verdict` is carried through untouched. And it is not a second
home for the estimators: no index, interval, standard error or resolution
rule is computed here.

THE LIVENESS RULE (§3.6, ruled §0.1 item 22). A channel is live when at least
one of its draw sites REACHES A CASH FLOW — never when it merely consumes a
draw. The two questions have different answers on real configs (pinned at
the generator in `tests/test_channel_streams.py`), so `live_channels` reads the
spec for what reaches a cash flow and `channels_that_draw` for what advances a
generator; the difference is reported as a structural zero, never hidden.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import numpy.typing as npt

from . import decomposition_math as dm
from .config import single_path_run
from .decomposition import (
    CHANNELS,
    Channel,
    Decomposition,
    DecompositionOutcome,
    DecompositionRefusal,
    LEVEL_PATHS,
    IndistinguishableLevel,
    Interaction,
    Interval,
    Level,
    LevelRegister,
    LevelRow,
    RefusedInteraction,
    RefusedSpread,
    ResolvedInteraction,
    ResolvedLevel,
    ResolvedShares,
    ReversalRegister,
    Shares,
    SpreadRegister,
    SpreadRow,
    StructuralZero,
    UnresolvedShares,
    Width,
    channel,
)
from .monte_carlo import addressed_streams, run_monte_carlo

__all__ = [
    "decompose",
    "margin_per_path",
    "live_channels",
    "channels_that_draw",
    "planned_evaluations",
    "largest_affordable_paths",
    "identity_budget",
    "EVALUATION_CEILING",
    "OPTION_NAMES",
]

Array = npt.NDArray[np.float64]

OPTION_NAMES: Tuple[str, ...] = ("condo", "house", "rent")

# Every channel id the freeze mask covers. Id 7 is the income trajectory and is
# not a channel (§3.5): it reaches a boolean, so freezing it could move no
# figure, and `run_monte_carlo` refuses the id outright.
ALL_CHANNEL_IDS: Tuple[int, ...] = tuple(c.id for c in CHANNELS)

# The two matrices the spread register draws (§3.3): `A` is matrix 0 and `B` is
# matrix 1, and `A_B^(c)` is matrix 0 with channel c taken from matrix 1.
MATRIX_A = 0
MATRIX_B = 1

# §8 refusal 6's ceiling, in model evaluations. THE SPEC NAMES NO FIGURE, so
# this one is the engine's own and the refusal says so. Derivation: the shipped
# `num_sims` default at seven live channels must not refuse — §9 calls it "the
# common case and not a worst case" — so the ceiling clears it with headroom,
# and fires around the point where a run wants to be asked for rather than
# waited on (`planned_evaluations` prices both; §9 has the per-path timing).
# It is a gate on WORK, never a cap on `k_live`: a cap at seven under a
# seven-channel taxonomy could never fire.
EVALUATION_CEILING = 250_000

# The smallest sample this block will interval, DERIVED rather than chosen. A
# 95% interval cuts 2.5% from each tail, and the bootstrap resamples PATHS, so
# its whole information content is the `n` futures it was given: one future
# weighs `1/n` of every figure. When `1/n` exceeds 0.025 — below forty futures
# — a single path is wider than the tail the interval claims to cut, and the
# bound it prints is that path rather than the distribution.
#
# The same floor closes a fail-safe hole found by this module's own test at two
# futures: a 300-resample bootstrap draws a degenerate resample (every index the
# same path) with probability `n**(1-n)` each time, so below five futures it is
# arithmetically certain to hit one, and `bootstrap_spread_intervals` refuses
# with a ValueError. Unguarded, that reached a user as a traceback instead of a
# named refusal — the cheap all-clear's noisier cousin, and still a surface that
# could not say why.
MIN_INTERVALLED_FUTURES = 40


# ---------------------------------------------------------------------------
# §2 — the one quantity everything is decomposed on
# ---------------------------------------------------------------------------

def margin_per_path(mc, best: str) -> Array:
    """`f`, the decision margin, priced on every path:

        f(w) = min over the other priced options of PV_o(w) - PV_best(w)

    where `best` is `verdict.best`, the DETERMINISTIC winner — never the
    majority, and never recomputed here. The `min` keeps a third option inside
    the target, where a pairwise gap would delete its channels from the table
    with no row saying so.

    This is the one home for the formula. A caller that wants `f` on a
    `ComparisonMonteCarloResult` calls this; it never restates the subtraction.
    """
    pvs = {
        name: np.asarray(getattr(mc, name).pvs, dtype=np.float64)
        for name in OPTION_NAMES
        if getattr(mc, name, None) is not None
    }
    if best not in pvs:
        raise ValueError(
            f"the verdict's best option is {best!r} and this Monte Carlo result "
            f"prices {sorted(pvs)}: there is no margin to decompose"
        )
    others = [arr for name, arr in pvs.items() if name != best]
    if not others:
        raise ValueError(
            "only one option is priced, so no margin exists (§8 refusal 3); "
            "the block refuses rather than decomposing a single option"
        )
    stacked = np.stack(others, axis=0)
    return np.asarray(stacked.min(axis=0) - pvs[best], dtype=np.float64)


# ---------------------------------------------------------------------------
# §3.6 — liveness, and the question it is NOT
# ---------------------------------------------------------------------------

def _priced(spec) -> Tuple[str, ...]:
    return tuple(n for n in OPTION_NAMES if getattr(spec, n, None) is not None)


def _owned(spec) -> Tuple[str, ...]:
    return tuple(n for n in ("condo", "house") if getattr(spec, n, None) is not None)


def _hazard_years(event, years: int) -> Tuple[bool, bool]:
    """(the event can occur, the year it occurs varies) under the hazard model.

    Mirrors `_sample_event_year_hazard`: the loop skips a year whose hazard is
    non-positive without drawing, so an event whose hazard is zero for every
    year inside the horizon both consumes nothing and never occurs. A hazard
    that clamps to certainty at its own start year occurs in that year on every
    path, so its TIMING does not vary even though it draws.
    """
    start = max(1, event.hazard_start_year)
    can_occur = False
    varies = False
    for year in range(start, max(0, years) + 1):
        hazard = event.hazard_base + event.hazard_growth * (year - start)
        hazard = min(max(hazard, 0.0), 1.0)
        if hazard <= 0:
            continue
        can_occur = True
        if hazard < 1.0:
            varies = True
            break
        # Certain in this year: it always fires here, so nothing later is
        # reachable and the timing is a constant.
        break
    return can_occur, varies


def _jitter_year_varies(event, years: int) -> bool:
    """True when `_sample_event_year`'s jitter can land on two different years.

    `timing_std_years` alone is not enough: the draw is clamped into
    `[min_year, min(max_year, years)]`, so a window one year wide returns the
    same integer on every path and the draw reaches no cash flow.
    """
    if event.timing_std_years <= 0:
        return False
    low = max(1, event.min_year)
    high = event.max_year if event.max_year is not None else years
    high = min(high, years)
    return high > low


def _event_draws(event, years: int) -> bool:
    """True when this event's draw sites consume a draw on some path.

    Two sites: the year, and the cost shock. The cost shock is taken
    UNCONDITIONALLY in the year the event lands (`_correlated_z` runs before
    `_sample_event_cost` reads `cost_vol`), so an event that occurs at all
    makes its channel draw whatever its volatilities are. That is one of the
    three streams that still move on a spec with every volatility at zero.
    """
    if years <= 0:
        return False
    if event.timing_model == "hazard":
        can_occur, varies = _hazard_years(event, years)
        return can_occur or varies
    # Jitter: the year is clamped into the horizon, so the event always occurs
    # and its cost z is always drawn; the year draw itself is taken only at a
    # positive std.
    return True


def _event_reaches_a_cash_flow(event, years: int) -> bool:
    """True when re-drawing this event's sites can move the option's PV.

    Three ways: the cost varies (a positive `cost_vol` on an event that can
    occur), the year varies under jitter, or whether-and-when varies under a
    hazard. All three need a cost to move — an event whose `base_cost` is zero
    prices zero in every year, because `_sample_event_cost` multiplies the base.
    """
    if years <= 0 or event.base_cost == 0:
        return False
    if event.timing_model == "hazard":
        can_occur, varies = _hazard_years(event, years)
        if varies:
            return True
        return can_occur and event.cost_vol > 0
    if _jitter_year_varies(event, years):
        return True
    return event.cost_vol > 0


def _has_other_costs(params) -> bool:
    return any(c.annual_amount != 0 for c in getattr(params, "other_recurring_costs", ()))


def _maintenance_is_charged(house) -> bool:
    """True when the house's maintenance line is non-zero somewhere.

    `house_maintenance_vol` multiplies `rate * house_value`; at a rate of zero
    the shock reaches nothing.
    """
    if house.annual_maintenance_rate != 0:
        return True
    return any(rate != 0 for _, rate in getattr(house, "maintenance_curve", ()) or ())


def _composed_escalation_is_nonzero(spec, base_rate: float) -> bool:
    """True when `_effective_growth_rate` can return something other than 0.

    The renter's escalation SHOCK scales the composed rate, so on a rate that
    composes to exactly zero every year the shock moves no cash flow. In
    nominal mode the rate is `(1 + base) * factor - 1`, which is non-zero
    whenever either the base rate or the inflation rate is; in real mode it is
    the base rate itself.
    """
    if spec.economic.mode == "nominal":
        return base_rate != 0 or spec.economic.inflation_rate != 0
    return base_rate != 0


def _crash_moves_a_value(spec) -> bool:
    """True when some OWNED option's price-shock channel can move its value.

    `_apply_price_shock` returns before reading the severity at a non-positive
    hazard, and a severity mean of zero multiplies the value by exactly 1, so
    both are liveness conditions rather than decoration. The crash is applied
    only inside the condo and house simulators, so a hazard on the renter (which
    `_world_draws` would still count) reaches nothing.
    """
    for name in _owned(spec):
        shock = getattr(getattr(spec, name), "price_shock", None)
        if shock is not None and shock.annual_hazard > 0 and shock.severity_mean > 0:
            return True
    return False


def _prior_rows(prior, spec) -> bool:
    """True when a loaded prior has rows for a priced owned option."""
    if prior is None:
        return False
    for name in _owned(spec):
        try:
            rows = prior.rows_for_dwelling(name)
        except Exception:  # pragma: no cover - a prior that cannot answer
            return False
        if rows:
            return True
    return False


def _inflation_reaches_a_cash_flow(spec) -> bool:
    """§3.5's third structural zero, decided from the spec.

    In NOMINAL mode the inflation factor composes into every growth rate the
    model has, so a priced option is enough. In REAL mode
    `_effective_growth_rate` DISCARDS the factor by construction, and the
    inflation draw reaches a cash flow only through a non-zero
    `corr_inflation_*` whose own shock is live; with every correlation off the
    channel draws every year and moves nothing, whatever its volatility (pinned
    in `tests/test_channel_streams.py::TestDeadChannelExactness`).
    """
    sim = spec.simulation
    if spec.economic.mode == "nominal":
        return bool(_priced(spec))
    for pull in _inflation_pulls(spec):
        if pull is not None:
            return True
    return False


def _inflation_pulls(spec) -> List[Tuple[str, str, float]]:
    """The (rho key, vol key, rho) triples by which the economy reaches a cost.

    §4 and §0.1 item 6: the `economy` row's provenance cell must list the
    `corr_inflation_*` keys AND THE OPTION VOLS THEY PULL FROM, because which
    vols are pulled depends on which rho is non-zero — so they cannot be static
    sizing keys and arrive as extra width entries from the code that reads the
    config. This is that code.
    """
    sim = spec.simulation
    years = sim.years
    out: List[Tuple[str, str, float]] = []
    if (sim.corr_inflation_condo != 0 and spec.condo is not None
            and sim.condo_fee_vol > 0 and spec.condo.monthly_fee != 0):
        out.append(("simulation.corr_inflation_condo",
                    "simulation.condo_fee_vol", sim.corr_inflation_condo))
    if (sim.corr_inflation_house != 0 and spec.house is not None
            and sim.house_maintenance_vol > 0 and _maintenance_is_charged(spec.house)):
        out.append(("simulation.corr_inflation_house",
                    "simulation.house_maintenance_vol", sim.corr_inflation_house))
    if sim.corr_inflation_other != 0 and sim.other_cost_vol > 0 and any(
            _has_other_costs(getattr(spec, name)) for name in _priced(spec)):
        out.append(("simulation.corr_inflation_other",
                    "simulation.other_cost_vol", sim.corr_inflation_other))
    if sim.corr_inflation_event_cost != 0:
        for name in _priced(spec):
            params = getattr(spec, name)
            if any(e.cost_vol > 0 and _event_reaches_a_cash_flow(e, years)
                   for e in params.events):
                out.append(("simulation.corr_inflation_event_cost",
                            f"{name}.events", sim.corr_inflation_event_cost))
    return out


def _renter_capital(spec) -> float:
    """The renter's capital leg, including the tax block's refunds.

    `investment_return_vol` reaches a cash flow only through this, and the
    simulator skips the whole leg at a capital of zero.
    """
    if spec.rent is None:
        return 0.0
    refunds = spec.tax.refunds if getattr(spec, "tax", None) is not None else 0.0
    return float(spec.rent.invested_down_payment + refunds)


def live_channels(spec, prior=None) -> Tuple[int, ...]:
    """The channels that MOVE A NUMBER on this spec, read from the spec (§3.6).

    Not the channels that draw — see `channels_that_draw`, and the module
    docstring for why the difference is the finding rather than a detail. The
    rule is one sentence: a channel is live when at least one of its draw sites
    reaches a cash flow, which is a question about volatilities, hazards, costs
    and mode, and is answered without pricing a path.

    `prior` is the loaded `ScenarioPrior` when the caller has one (the CLI loads
    it once at its edge). Without it a wired `market_scenario` is read as live,
    which is what the spec states it is — the prior's rows are what would refute
    it, and an absent prior is not evidence.
    """
    sim = spec.simulation
    years = sim.years
    live: List[int] = []

    if _inflation_reaches_a_cash_flow(spec) and spec.economic.inflation_vol > 0:
        live.append(0)

    if _owned(spec) and (sim.value_growth_vol > 0 or _crash_moves_a_value(spec)):
        live.append(1)

    if _owned(spec) and spec.market_scenario is not None and (
            prior is None or _prior_rows(prior, spec)):
        live.append(2)

    if spec.condo is not None:
        condo = spec.condo
        if (
            (sim.condo_fee_vol > 0 and condo.monthly_fee != 0)
            or (sim.other_cost_vol > 0 and _has_other_costs(condo))
            or any(_event_reaches_a_cash_flow(e, years) for e in condo.events)
        ):
            live.append(3)

    if spec.house is not None:
        house = spec.house
        if (
            (sim.house_maintenance_vol > 0 and _maintenance_is_charged(house))
            or (sim.other_cost_vol > 0 and _has_other_costs(house))
            or any(_event_reaches_a_cash_flow(e, years) for e in house.events)
        ):
            live.append(4)

    if spec.rent is not None:
        rent = spec.rent
        escalation_live = (
            sim.rent_escalation_vol > 0
            and rent.monthly_rent != 0
            and _composed_escalation_is_nonzero(spec, rent.rent_escalation_rate)
        )
        if (
            rent.reset_hazard > 0
            or escalation_live
            or (sim.other_cost_vol > 0 and _has_other_costs(rent))
            or any(_event_reaches_a_cash_flow(e, years) for e in rent.events)
        ):
            live.append(5)

    if (spec.rent is not None and sim.investment_return_vol > 0
            and _renter_capital(spec) > 0 and years > 0):
        live.append(6)

    return tuple(live)


def channels_that_draw(spec, prior=None) -> Tuple[int, ...]:
    """The channels whose draw sites ADVANCE A GENERATOR on this spec.

    The other question, kept separate on purpose. Its answer is what
    `tests/test_channel_streams.py` asserts at the bit-generator state, and the
    channels in here but not in `live_channels` are §3.5's third kind of
    structural zero: a channel that draws and reaches nothing.

    This belongs beside `_world_draws`, which already reads the spec once for
    exactly this question about the world's own three channels. It is here so
    that it sits beside `live_channels`, the question it must not be confused
    with; if it moves to `monte_carlo.py`, the world's flags and the option
    channels' would be one table instead of two.
    """
    sim = spec.simulation
    years = sim.years
    draws: List[int] = []

    if spec.economic.inflation_vol > 0 and years > 0:
        draws.append(0)

    crash = any(
        (getattr(getattr(spec, name), "price_shock", None) is not None
         and getattr(spec, name).price_shock.annual_hazard > 0)
        for name in _priced(spec)
    )
    if (crash or sim.value_growth_vol > 0) and years > 0:
        draws.append(1)

    if spec.market_scenario is not None and (prior is None or _prior_rows(prior, spec)):
        draws.append(2)

    # The condo's fee z and the house's maintenance z are taken every year
    # whether or not their volatility is positive, and so are both options'
    # other-cost z's; the event-cost z is taken in the year the event lands.
    # So a priced owned option's channel always draws.
    if spec.condo is not None and years > 0:
        draws.append(3)
    if spec.house is not None and years > 0:
        draws.append(4)

    if spec.rent is not None and years > 0:
        rent = spec.rent
        if (
            rent.reset_hazard > 0
            or sim.rent_escalation_vol > 0
            or (sim.other_cost_vol > 0 and rent.other_recurring_costs)
            or any(_event_draws(e, years) for e in rent.events)
        ):
            draws.append(5)

    if (spec.rent is not None and sim.investment_return_vol > 0
            and _renter_capital(spec) > 0 and years > 0):
        draws.append(6)

    return tuple(draws)


# ---------------------------------------------------------------------------
# §9 — the cost model: one formula, for the gate and for the count
# ---------------------------------------------------------------------------

def planned_evaluations(paths: int, k_live: int, level_paths: int, *,
                        spread_priced: bool = True) -> int:
    """The model evaluations this module spends — ONE formula, for the budget
    gate and for the count a test takes of what was actually priced:

        N * (k_live + 2)  +  m * (k_live + 1)

    The spread register prices `A`, `B` and one `A_B^(c)` per live channel at N
    paths; the level register prices one freeze per live channel AND the
    all-frozen run at `m`. A cost model that left the all-frozen run out once
    recommended an N that priced above the ceiling it was chosen under; one
    formula cannot disagree with itself.

    `spread_priced=False` is the run where every future lies on one side of the
    line: only `A` is priced for the spread register. The gate cannot know that
    before it prices `A`, so it takes the default, and its figure is the most the
    module can spend — which is why the refusal says "up to". The reversal
    register's evaluations are `break_even`'s, at the config's own `num_sims`,
    and are not counted here.
    """
    spread = int(paths) * (int(k_live) + 2) if spread_priced else int(paths)
    return spread + int(level_paths) * (int(k_live) + 1)


def _level_paths(paths: int) -> int:
    return max(2, min(int(paths), LEVEL_PATHS))


# ---------------------------------------------------------------------------
# §8 — the refusals, which are judgments about the data
# ---------------------------------------------------------------------------

def _refuse(code: str, reason: str, channel_id: Optional[int] = None) -> DecompositionRefusal:
    return DecompositionRefusal(code=code, reason=reason, channel_id=channel_id)


def _refusal_before_pricing(spec, mc, verdict, live: Tuple[int, ...],
                            paths: int) -> Optional[DecompositionRefusal]:
    """Every §8 refusal that can be decided without pricing a path, in the
    order of the questions: are there futures at all, is there a margin, is
    there more than one live channel to split it between, and is the work
    affordable. Each reason is the ONE measured fact that fired it (spec §0.1
    item 35) — a fact about this run, never an account of why it holds and
    never a route to another run.
    """
    if mc is None or single_path_run(spec):
        return _refuse("no_futures", "this run has no futures")
    if verdict is None or verdict.rule == "single_option":
        return _refuse("single_option", "this run prices one option")
    if len(live) == 0:
        return _refuse("no_spread", "no channel is live on this run")
    if len(live) == 1:
        only = channel(live[0])
        return _refuse("one_channel",
                       f"one channel is live on this run: {only.label}",
                       channel_id=only.id)
    level_paths = _level_paths(paths)
    work = planned_evaluations(paths, len(live), level_paths)
    if work > EVALUATION_CEILING:
        # The one figure a refusal may carry beyond its fact (§0.1 item 35):
        # the largest N the ceiling admits, computed by the gate's own cost
        # model, so it can never name an N this gate would refuse.
        largest = largest_affordable_paths(len(live))
        return _refuse(
            "budget",
            f"{paths:,} futures at {len(live)} live channels price up to {work:,} "
            f"path evaluations, above the ceiling of {EVALUATION_CEILING:,} [set in "
            f"the engine]; the largest path count within it is {largest:,}",
        )
    return None


def largest_affordable_paths(k_live: int) -> int:
    """The largest `--decompose=N` whose planned work clears
    `EVALUATION_CEILING` at `k_live` live channels — read off
    `planned_evaluations` itself, which is monotone in N, so the cost model
    keeps one home and this can never name an N the gate would refuse, nor
    one whose priced work exceeds the ceiling it was chosen under."""
    low, high = 0, EVALUATION_CEILING
    while low < high:
        mid = (low + high + 1) // 2
        if planned_evaluations(mid, k_live, _level_paths(mid)) <= EVALUATION_CEILING:
            low = mid
        else:
            high = mid - 1
    return low


# ---------------------------------------------------------------------------
# §5 — the widths, and who typed them
# ---------------------------------------------------------------------------

def _width(spec, raw, key: str, note: Optional[str] = None) -> Optional[Width]:
    """One sizing key as a `Width`, or None when this config does not state it.

    An unstated sizing key is not a width: every volatility, hazard and
    correlation in the model defaults to 0.0, so a key the config leaves out
    sizes nothing and has no figure to print. The source class comes from
    `spec.sources` — `SourceEcho.classify`'s own answer, never inferred from the
    key's name (test T14) — and `unattributed` is what the echo itself calls a
    stated key on a config with no `sources:` block.
    """
    echo = getattr(spec, "sources", None)
    entry = echo.get(key) if echo is not None else None
    if entry is not None:
        return Width(key=key, formatted=entry.formatted, source=entry.source,
                     anchor=entry.anchor, note=note)
    if raw is None:
        return None
    # A spec built from a config always carries an echo; this path is the
    # directly-constructed spec, where the raw mapping is the only evidence.
    from .sources import format_source_value, raw_value
    try:
        value = raw_value(raw, key)
    except (KeyError, TypeError, IndexError):
        return None
    return Width(key=key, formatted=format_source_value(key, value),
                 source="unattributed", anchor=None, note=note)


def _widths_for(spec, raw, entry: Channel) -> Tuple[Width, ...]:
    """The widths on one channel's row: its sizing keys, plus §4's extras.

    §0.1 item 6: the `economy` row must name the option vols its correlations
    pull from, and which those are depends on which rho is non-zero, so they
    cannot be static sizing keys. Each arrives with the rho that pulls it and
    rho squared, as figures; what rho squared is, is the contract's.
    """
    widths: List[Width] = []
    seen: set = set()
    for key in entry.sizing_keys:
        got = _width(spec, raw, key)
        if got is not None and got.key not in seen:
            widths.append(got)
            seen.add(got.key)
    if entry.id == 0:
        for rho_key, vol_key, rho in _inflation_pulls(spec):
            note = f"pulled by {rho_key} = {rho:g}; rho squared {rho * rho:g}"
            got = _width(spec, raw, vol_key, note=note)
            if got is not None and (got.key, note) not in seen:
                widths.append(got)
                seen.add((got.key, note))
    return tuple(widths)


# ---------------------------------------------------------------------------
# §3.5 — structural zeros
# ---------------------------------------------------------------------------

def _dead_draw_rows(spec, raw, live: Tuple[int, ...],
                    drawing: Tuple[int, ...]) -> List[StructuralZero]:
    """The `dead_draw` rows: every channel that draws on this spec and is not
    live, enumerated over the CATEGORY and decided here, the one place that
    holds both predicates (`channels_that_draw`, `live_channels`)."""
    rows: List[StructuralZero] = []
    for channel_id in drawing:
        if channel_id in live:
            continue
        entry = channel(channel_id)
        widths = _widths_for(spec, raw, entry)
        rows.append(StructuralZero(
            kind="dead_draw",
            label=entry.label,
            keys=tuple(w.key for w in widths) or entry.sizing_keys,
            channel_id=channel_id,
        ))
    return rows


def _reversal_register(spec, raw, det, mc, live: Tuple[int, ...],
                       drawing: Tuple[int, ...]) -> ReversalRegister:
    """§6's register: `break_even.reversal_register`, plus the dead-draw rows
    it cannot see.

    The solved rows, the per-boundary refusals of §8 item 7 and the structural
    zeros are all `break_even.reversal_register`'s by ruling (§0.1 items 5 and
    17) — the assembler calls it and adds nothing to what it returns except the
    channels only the liveness predicates know about. It is handed THIS run's
    own `det` and `mc`, so the register and the block cannot disagree about the
    base case.

    Without a raw mapping there is nothing to solve on: every candidate in §6
    is a key the CONFIG states, and `reversal_register` re-loads the config to
    probe it. A directly-constructed spec therefore gets the structural zeros
    this module can see and no solved rows — an empty tuple that says the
    assembler found no candidate, never that none exists.
    """
    register = ReversalRegister(
        exact=(), estimated=(), structural_zeros=(),
        no_distance_reason="this block was handed no config mapping")
    if raw is not None:
        from .break_even import reversal_register as solve_reversal_register
        register = solve_reversal_register(raw, det, mc)
    extra = _dead_draw_rows(spec, raw, live, drawing)
    if not extra:
        return register
    return dataclasses.replace(
        register, structural_zeros=register.structural_zeros + tuple(extra))


# ---------------------------------------------------------------------------
# §3.3 — the spread register
# ---------------------------------------------------------------------------

def _interval(pair) -> Interval:
    return Interval(low=float(pair[0]), high=float(pair[1]))


def _share_point(shares: Shares) -> float:
    """ONE row's first-order point estimate, resolved or not."""
    if isinstance(shares, ResolvedShares):
        return shares.alone
    if isinstance(shares, UnresolvedShares):
        return shares.provisional_alone
    raise TypeError(f"a spread row carries a {type(shares).__name__}, which is "
                    f"neither ResolvedShares nor UnresolvedShares")


def _level_point(level: Level) -> float:
    """ONE row's |shift| point estimate, resolved or not."""
    if isinstance(level, ResolvedLevel):
        return abs(level.delta)
    if isinstance(level, IndistinguishableLevel):
        return abs(level.provisional_delta)
    raise TypeError(f"a level row carries a {type(level).__name__}, which is "
                    f"neither ResolvedLevel nor IndistinguishableLevel")


def _top_row(points: Sequence[Tuple[int, float, bool]]) -> Tuple[Optional[int], Optional[int]]:
    """`(leading_channel_id, unresolved_top_channel_id)` from one register's
    rows as `(channel_id, point estimate, resolved)` — the ONE rule both
    registers name their top row by.

    The top row is the largest POINT estimate over EVERY row, resolved or not.
    It leads only if it resolved; otherwise it is the unresolved top and nothing
    leads. The largest RESOLVED row is never promoted in its place: that named a
    smaller shift "the largest" on examples/basic_config.yaml and handed the
    spread table's lead, in the JSON, to a sliver of the spread on
    examples/rent_vs_condo_vs_house.yaml. A tie on the point goes to the first
    row in live-channel order. The callers hand it each row's point through
    `_share_point` and `_level_point`, the level's taken in SIZE.
    """
    if not points:
        return None, None
    channel_id, _, resolved = max(points, key=lambda entry: entry[1])
    return (channel_id, None) if resolved else (None, channel_id)


def _spread_register(
    f_a: Array, f_b: Array, f_ab: Array, live: Tuple[int, ...],
    widths_by_channel: Dict[int, Tuple[Width, ...]], seed: int,
) -> SpreadRegister:
    """The spread register: two Sobol shares, the flip fraction and the gap
    between the shares per channel, and the interaction residual.

    Every figure comes from `decomposition_math`; the only judgments here are
    which rows resolved, which row is on top and whether it leads (`_top_row`),
    and which rows' gaps resolved.

    A ROW IS UNRESOLVED IF EITHER FIGURE IS (§0.1 item 11). Conservative is
    correct for the same reason the register refuses at all: the alternative
    prints one resolved figure beside one that is noise and leaves the reader
    to notice.

    Never called when every future lies on one side of the line: that case is
    `_no_sign_variation`, a named refusal in this register's slot, and it prices
    no `B` matrix.
    """
    first = dm.first_order_indices(f_a, f_b, f_ab)
    total = dm.total_order_indices(f_a, f_ab)
    flip = dm.sign_flip_fraction_of_futures(f_a, f_ab)
    gaps = dm.interaction_gaps(f_a, f_b, f_ab)
    first_ci, total_ci, flip_ci, sum_ci = dm.bootstrap_spread_intervals(
        f_a, f_b, f_ab, seed=seed)
    gap_ci = dm.bootstrap_interaction_gap_intervals(f_a, f_b, f_ab, seed=seed)

    rows: List[SpreadRow] = []
    for position, channel_id in enumerate(live):
        widths = widths_by_channel.get(channel_id, ())
        alone, together = float(first[position]), float(total[position])
        if dm.share_is_resolved(alone) and dm.share_is_resolved(together):
            shares: Shares = ResolvedShares(
                alone=alone,
                alone_ci=_interval(first_ci[position]),
                with_interaction=together,
                with_interaction_ci=_interval(total_ci[position]),
            )
        else:
            shares = UnresolvedShares(
                provisional_alone=alone,
                provisional_alone_ci=_interval(first_ci[position]),
                provisional_with_interaction=together,
                provisional_with_interaction_ci=_interval(total_ci[position]),
            )
        rows.append(SpreadRow(
            channel_id=channel_id,
            shares=shares,
            flip=float(flip[position]),
            flip_ci=_interval(flip_ci[position]),
            widths=widths,
            interaction_gap=float(gaps[position]),
            interaction_gap_ci=_interval(gap_ci[position]),
        ))

    leading, unresolved_top = _top_row([
        (row.channel_id, _share_point(row.shares), isinstance(row.shares, ResolvedShares))
        for row in rows])

    total_first_order = dm.sum_first_order_shares(first)
    residual = dm.residual_interaction(total_first_order, sum_ci[0], sum_ci[1])
    if residual is None:
        interaction: Interaction = RefusedInteraction(
            first_order_sum=total_first_order,
            first_order_sum_ci=_interval(sum_ci),
        )
    else:
        interaction = ResolvedInteraction(
            first_order_sum=total_first_order,
            first_order_sum_ci=_interval(sum_ci),
            residual=residual[0],
            residual_ci=Interval(low=residual[1], high=residual[2]),
        )

    interacting = tuple(
        row.channel_id for row in rows
        if dm.interaction_is_resolved(row.interaction_gap_ci.low))
    return SpreadRegister(rows=tuple(rows), interaction=interaction,
                          leading_channel_id=leading,
                          unresolved_top_channel_id=unresolved_top,
                          interaction_channel_ids=interacting)


def _one_side_of_the_line(best_cheapest: float) -> bool:
    """§0.1 items 7, 29 and 36: the spread register refuses when `f` never
    changes sign on the block's futures — `P(f > 0)` of exactly 0 or exactly 1.
    A design choice about what prints, not a claim that a re-draw could move no
    future across the line (item 36 measured one that does). The ONE home of
    that condition."""
    return best_cheapest in (0.0, 1.0)


def _no_sign_variation(best: str, futures: int, best_cheapest: float) -> RefusedSpread:
    """The spread register's refusal in its own slot; the level and reversal
    registers still print. Its reason is the measured fact alone (§0.1 item
    36)."""
    if not _one_side_of_the_line(best_cheapest):
        raise ValueError(
            f"P({best} cheapest) is {best_cheapest!r} on this sample, so futures sit on "
            f"both sides of the line and the spread register has shares to print")
    reason = (f"{best} is cheapest in all {futures:,} of these futures"
              if best_cheapest == 1.0 else
              f"{best} is cheapest in none of these {futures:,} futures")
    return RefusedSpread(code="no_sign_variation", reason=reason)


# ---------------------------------------------------------------------------
# §3.4 — the level register
# ---------------------------------------------------------------------------

def _level_register(spec, verdict, best: str, f_a: Array, live: Tuple[int, ...],
                    seed: int, level_paths: int) -> LevelRegister:
    """§3.4's freeze mask, paired against `A`'s OWN first `m` paths.

    §0.1 item 1: the register computes its own baseline. Its comparisons are
    paired against `A`, so the baseline is `f(A[:m])` taken from the `A` matrix
    already priced — never `verdict`, whose `prob_best` comes from the LEGACY
    single-generator binding and is a different sample of the same quantity.
    `futures_margin` and `prob_best_base` are this register's figures, reported
    beside the verdict's rather than reconciled with them: their difference is
    information about the estimator.

    The pairing is what the per-path stream keying buys. A frozen run at `m`
    paths reads `channel_stream(seed, 0, c, i)` for every unfrozen channel on
    path `i`, exactly as the `A` run did, so the two differ ONLY in the frozen
    channel and the standard error is taken on the difference.
    """
    base = np.asarray(f_a[:level_paths], dtype=np.float64)
    spec_at_m = _spec_at(spec, level_paths)
    frozen = np.empty((len(live), base.size), dtype=np.float64)
    probs: List[float] = []
    for position, channel_id in enumerate(live):
        result = _run(spec_at_m, MATRIX_A, freeze=(channel_id,))
        f_frozen = margin_per_path(result, best)
        frozen[position] = f_frozen
        probs.append(float(np.mean(f_frozen > 0.0)))

    deltas, errors = dm.level_shifts(base, frozen)
    resolved = dm.level_resolved_mask(deltas, errors)
    rows: List[LevelRow] = []
    for position, channel_id in enumerate(live):
        delta, error = float(deltas[position]), float(errors[position])
        level: Level = (
            ResolvedLevel(delta=delta, se=error, prob_best_frozen=probs[position])
            if bool(resolved[position])
            else IndistinguishableLevel(provisional_delta=delta, se=error,
                                        prob_best_frozen=probs[position])
        )
        rows.append(LevelRow(channel_id=channel_id, level=level))

    # The identity that makes this register a fact rather than a claim (§3.4,
    # test T2, as amended by §0.1 item 19): with EVERY channel frozen every
    # path prices one margin, bit for bit, and that margin is the verdict's
    # own to within a ULP budget. Two fields, because they are two claims: the
    # spread ACROSS paths is what a missed draw site breaks, and `decompose`
    # refuses the block when it is not 0.0. Every id is frozen, not only the
    # live ones — the claim is about the mask, and a dead channel's freeze is
    # what makes it a no-op.
    all_frozen = margin_per_path(
        _run(spec_at_m, MATRIX_A, freeze=ALL_CHANNEL_IDS), best)

    leading, unresolved_top = _top_row([
        (row.channel_id, _level_point(row.level), isinstance(row.level, ResolvedLevel))
        for row in rows])

    return LevelRegister(
        rows=tuple(rows),
        paths=int(base.size),
        prob_best_base=float(np.mean(base > 0.0)),
        futures_margin=float(np.mean(base)),
        all_frozen_margin=float(all_frozen[0]),
        all_frozen_path_spread=float(np.max(np.abs(all_frozen - all_frozen[0]))),
        all_frozen_deviation=float(abs(all_frozen[0] - verdict.margin_pv)),
        accounted_for=float(np.sum(deltas)),
        leading_channel_id=leading,
        unresolved_top_channel_id=unresolved_top,
    )


def _freeze_leak(level: LevelRegister) -> DecompositionRefusal:
    """The level register's identity failed, so the whole block refuses.

    With EVERY channel frozen, every path must price one and the same margin:
    `all_frozen_path_spread` is exactly zero on a correct engine, and anything
    else means a draw site escaped the freeze mask. Then each frozen run differs
    from `A` in more than the channel it froze, every shift is measured against a
    baseline that is not the central case, and the level line would print the
    all-frozen margin as the central case's over a run where it is not. The
    spread cannot print without the level, so nothing prints.

    `all_frozen_deviation` is NOT gated here but by `_identity_failed`: it is
    held to a ULP budget scaled to the totals subtracted, never to zero.
    """
    return _refuse(
        "freeze_leak",
        f"with every channel frozen, the margins of the {level.paths:,} paths "
        f"differ by up to ${level.all_frozen_path_spread:,.6g}",
    )


def identity_budget(det, verdict) -> float:
    """The ULP budget the all-frozen identity is held to ON THIS RUN:
    `decomposition_math.identity_ulp_budget` over the magnitude the margin is
    summed from — each priced option's breakdown terms added by size (its
    `total_pv` is their sum), that total itself, and the verdict's margin.

    The TERMS and not the total, because the rounding lives in them: a pair
    whose small totals net large terms measures many units of its total and one
    of its terms, and a budget scaled by the total refused that legal run
    (pinned in `tests/test_decomposition_run.py::TestTheIdentityIsGated`). The
    budget's rule has its one home in `decomposition_math`; which figures it is
    taken over has its one home here, and the tests import both.
    """
    figures: List[float] = [abs(verdict.margin_pv)]
    for option in (det.condo, det.house, det.rent):
        if option is not None:
            figures.append(abs(option.total_pv))
            figures.append(float(sum(abs(term) for term in option.breakdown.values())))
    return dm.identity_ulp_budget(figures)


def _identity_failed(level: LevelRegister, verdict, budget: float) -> DecompositionRefusal:
    """The all-frozen run agrees with ITSELF but not with the central case.

    `freeze_leak` catches paths that differ from each other. This is the other
    half of the identity (§3.4, amended by §0.1 item 19): every path prices one
    margin, and that margin must be the verdict's own to within
    `identity_budget` — a few units in the last place, the structural rounding
    between compounding year by year and `(1 + g) ** years`. Beyond it, the
    freeze does not reproduce the central case. The level register's shifts
    are measured against that freeze and the spread register is priced by the
    same machinery, so the WHOLE block refuses — both registers rest on it, and
    the spread may not print without the level.
    """
    return _refuse(
        "identity_failed",
        f"with every channel frozen, the {level.paths:,} paths price a margin of "
        f"${level.all_frozen_margin:,.2f} against the central case's "
        f"${verdict.margin_pv:,.2f}, ${level.all_frozen_deviation:.3g} apart, "
        f"above the ${budget:.3g} this check allows",
    )


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def _spec_at(spec, paths: int):
    """The same spec at a different path count, for one matrix."""
    return dataclasses.replace(
        spec, simulation=dataclasses.replace(spec.simulation, num_sims=int(paths)))


def _run(spec_at_paths, matrix_id: int, swapped: Optional[Dict[int, int]] = None,
         freeze: Sequence[int] = ()):
    """One matrix, priced through the addressed binding of §3.2.

    Every evaluation this module spends goes through here, so a test that
    replaces `run_monte_carlo` in this module's namespace counts all of them —
    and a partial freeze can never reach the legacy binding, which refuses it
    rather than returning an unpaired number.
    """
    streams = addressed_streams(spec_at_paths.simulation.random_seed,
                                matrix_id, swapped)
    return run_monte_carlo(spec_at_paths, streams, freeze=tuple(freeze))


def decompose(spec, *, det, mc, verdict, raw=None, prior=None,
              paths: Optional[int] = None) -> DecompositionOutcome:
    """WHICH RISK DECIDES IT — the whole block, assembled from one spec.

    The seam §0.1 item 17 names, and the only entry point: `--decompose` calls
    this and renders what comes back. Silence is the CLI's — the flag not
    passed means this function is never called — so what it returns is either
    the block or a named refusal, never None.

    Args:
        spec: the run's own `ComparisonSpec`.
        det, mc, verdict: THIS run's deterministic result, Monte Carlo result
            and verdict. They are read, never recomputed: the verdict's own
            state and probability stay `models.compute_verdict`'s, and the
            block's probabilities are frequencies of `f`'s sign on the paths
            it prices. `mc` is the LEGACY binding's own result, which is why
            `verdict.prob_best` and the level register's `prob_best_base` are
            two samples of one quantity and are both reported (§0.1 item 1).
        raw: the mapping the config came from. §6's candidates are keys the
            config STATES and the reversal solver re-loads it to probe them, so
            without it the block carries no solved rows.
        prior: the loaded demographic prior, when the caller has one. It
            sharpens liveness for the population channel and nothing else.
        paths: `--decompose=N`'s sample-size override, consumed here because N
            is a compute-time figure (§0.1 item 16). Default is the config's
            own `num_sims`.

    Returns:
        `Decomposition`, or `DecompositionRefusal` when §8 says the honest
        output is a named reason rather than a table.
    """
    requested = int(paths) if paths is not None else int(spec.simulation.num_sims)
    live = live_channels(spec, prior)
    drawing = channels_that_draw(spec, prior)

    refusal = _refusal_before_pricing(spec, mc, verdict, live, requested)
    if refusal is not None:
        return refusal
    if requested < MIN_INTERVALLED_FUTURES:
        # Its own code, never `no_futures`: this run HAS futures, and a reader
        # (or a consumer keyed on the code) told it has none is told something
        # false about the run it just made.
        return _refuse(
            "too_few_futures",
            f"{requested:,} futures were asked for, below the minimum of "
            f"{MIN_INTERVALLED_FUTURES}",
        )

    seed = int(spec.simulation.random_seed)
    best = verdict.best
    level_paths = _level_paths(requested)
    spec_at_paths = _spec_at(spec, requested)

    # `A` first, and the two questions it alone can answer: is there any spread
    # to apportion, and does any future disagree with the central case.
    f_a = margin_per_path(_run(spec_at_paths, MATRIX_A), best)
    if float(np.var(f_a)) == 0.0:
        # §0.1 item 37: the measured fact only. Liveness is judged on option
        # values, so a live channel can move an option that never enters the
        # margin; nothing here says which channels move what.
        value = float(f_a[0])
        return _refuse(
            "no_spread",
            f"the margin is identical on all {f_a.size:,} futures "
            f"({'-' if value < 0 else ''}${abs(value):,.2f})",
        )

    spread: Union[SpreadRegister, RefusedSpread]
    best_cheapest = float(np.mean(f_a > 0.0))
    if _one_side_of_the_line(best_cheapest):
        spread = _no_sign_variation(best, int(f_a.size), best_cheapest)
    else:
        f_b = margin_per_path(_run(spec_at_paths, MATRIX_B), best)
        f_ab = np.empty((len(live), f_a.size), dtype=np.float64)
        for position, channel_id in enumerate(live):
            # `A` with channel c's streams taken from `B`, so f(A) and
            # f(A_B^(c)) differ ONLY in channel c. The table is CHANNEL-MAJOR:
            # row c is that channel, and `decomposition_math` validates the
            # shape and raises on a transpose rather than returning a
            # plausible wrong table.
            f_ab[position] = margin_per_path(
                _run(spec_at_paths, MATRIX_A, {channel_id: MATRIX_B}), best)
        widths_by_channel = {
            channel_id: _widths_for(spec, raw, channel(channel_id))
            for channel_id in live
        }
        spread = _spread_register(f_a, f_b, f_ab, live, widths_by_channel, seed)

    level = _level_register(spec, verdict, best, f_a, live, seed, level_paths)
    if level.all_frozen_path_spread != 0.0:
        return _freeze_leak(level)
    budget = identity_budget(det, verdict)
    if not dm.identity_holds(level.all_frozen_deviation, budget):
        return _identity_failed(level, verdict, budget)
    reversal = _reversal_register(spec, raw, det, mc, live, drawing)

    return Decomposition(
        paths=int(f_a.size),
        max_paths=largest_affordable_paths(len(live)),
        live_channel_ids=live,
        verdict=verdict,
        mean_margin=float(np.mean(f_a)),
        sd_margin=float(np.std(f_a)),
        spread=spread,
        level=level,
        reversal=reversal,
    )
