"""Which risk decides it — THE ASSEMBLER (spec §0.1 item 17).

It turns one spec into the `DecompositionOutcome` the other pieces exchange:
the estimators (`decomposition_math`) take arrays, and the formatter
(`decomposition_text`) renders what this module builds. Its surface is

    decompose(spec, *, det, mc, verdict, raw, paths) -> DecompositionOutcome

plus the measurement the block's refusals and its channel count turn on
(`measure_channels`), the margin (`margin_per_path`) and the one cost model
(`planned_evaluations`, `largest_affordable_paths`). What each refusal and
figure means is `docs/reference/API_CONTRACT.md`'s.

WHAT IT DOES, in the order it does it, because the order is the cost model:

  1. the refusals the spec and the flags decide: no futures, one option, too
     few futures to interval, and more futures than the ceiling allows even to
     draw once. They fire before a single path is priced;
  2. the `A` matrix, recording which streams' generators advance as it is
     priced, and the refusal only it can decide: a margin identical on every
     future;
  3. the budget gate, on the number of streams that drew on `A`;
  4. one `A_B^(c)` per stream that drew, and from them which channels are
     live, which decides the channel refusals (`no_spread` with no channel
     live, `one_channel`) and the header's count. A stream that drew and is
     not live is a row of the spread register's, measured on these futures;
  5. when futures sit on both sides of the line, `B`, and the spread register
     over the live channels' `A_B^(c)`;
  6. the level register — the freeze mask, paired against `A`'s own first
     paths — and the all-frozen run whose identity, failing, refuses the whole
     block (`freeze_leak`, `identity_failed`).

Every refusal the block carries, the whole block's and the spread's, is
decided here; the formatter renders a refusal and never decides one. A check
on the way that cannot pass raises `CheckFailed` with its code and the one
fact it measured, and `decompose` returns that as the block's refusal (§0.1
item 58). Nothing else is caught: an exception that is no check is an engine
defect, and reaches the caller as one.

It is not a second verdict: `verdict` is carried through untouched. The
probabilities this module takes itself are frequencies of `f`'s sign on
futures it priced: over all N for whether the futures sit on both sides of the
line, and over the level register's first paths for its `prob_best_*`. And it
is not a second home for the estimators: no index, interval, standard error or
resolution rule is computed here.

DRAWS AND LIVENESS ARE MEASURED, NEVER PREDICTED (§0.1 item 39). Whether a
stream draws is whether its generator advanced while `A` was priced; whether a
channel is live is whether re-drawing it (`A_B^(c)`) moved some option's
present value on some future by more than the all-frozen identity's own
budget (`identity_budget`, `decomposition_math.identity_holds`) — one
threshold, one home. A copy of the simulator's logic that answered either
question from the config disagreed with the simulator on real configs, so
there is none.
"""
from __future__ import annotations

import dataclasses
import math
from decimal import ROUND_CEILING, Decimal
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import numpy.typing as npt

from . import decomposition_math as dm
from .config import single_path_run
from .decomposition import (
    CHANNELS,
    INCOME_STREAM_ID,
    INCOME_STREAM_LABEL,
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
    "CheckFailed",
    "signed_dollars",
    "ceiled_figure",
    "margin_per_path",
    "measure_channels",
    "ChannelMeasurement",
    "planned_evaluations",
    "largest_affordable_paths",
    "identity_budget",
    "EVALUATION_CEILING",
    "OPTION_NAMES",
]

Array = npt.NDArray[np.float64]

OPTION_NAMES: Tuple[str, ...] = ("condo", "house", "rent")

# Every channel id the freeze mask covers. Id 7 is the income stream and is not
# a channel: its draws feed the affordability report, and `run_monte_carlo`
# refuses the id in `freeze` outright.
ALL_CHANNEL_IDS: Tuple[int, ...] = tuple(c.id for c in CHANNELS)

# Every stream a run can draw from: the seven channels and the income stream.
# Which of them DREW on a run is measured (`_DrawRecorder`), never read off the
# config.
STREAM_IDS: Tuple[int, ...] = ALL_CHANNEL_IDS + (INCOME_STREAM_ID,)

# The two matrices the spread register draws (§3.3): `A` is matrix 0 and `B` is
# matrix 1, and `A_B^(c)` is matrix 0 with channel c taken from matrix 1.
MATRIX_A = 0
MATRIX_B = 1

# §8 refusal 6's ceiling, in model evaluations. THE SPEC NAMES NO FIGURE, so
# this one is the engine's own and the refusal says so. Derivation: the shipped
# `num_sims` default at seven channels must not refuse — §9 calls it "the
# common case and not a worst case" — so the ceiling clears it with headroom,
# and fires around the point where a run wants to be asked for rather than
# waited on (`planned_evaluations` prices both; §9 has the per-path timing).
# It is a gate on WORK, never a cap on the channel count: a cap at seven under
# a seven-channel taxonomy could never fire.
EVALUATION_CEILING = 250_000

# The smallest sample this block will interval, DERIVED rather than chosen. A
# 95% interval cuts 2.5% from each tail, and the bootstrap resamples PATHS, so
# its whole information content is the `n` futures it was given: one future
# weighs `1/n` of every figure. When `1/n` exceeds 0.025 — below forty futures
# — a single path is wider than the tail the interval claims to cut, and the
# bound it prints is that path rather than the distribution.
MIN_INTERVALLED_FUTURES = 40



class CheckFailed(Exception):
    """A check inside the block that cannot pass: the refusal `code` it
    carries and the one `reason` it measured (§0.1 items 35 and 58).
    `decompose` returns it as the block's refusal; nothing else in this module
    catches it."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"({code}): {reason}")
        self.code = code
        self.reason = reason


def signed_dollars(value: float, places: int = 0) -> str:
    """A dollar figure at `places` decimals, its sign before the dollar sign
    (`-$N`), and a figure whose printed digits are all zero with no sign: a printed
    zero has no side. The one rule for a dollar figure in the block's lines
    and in the reasons written here."""
    text = f"{abs(float(value)):,.{places}f}"
    if float(value) < 0.0 and float(text.replace(",", "")) != 0.0:
        return f"-${text}"
    return f"${text}"


def ceiled_figure(value: float, digits: int, grouping: str = "") -> str:
    """A positive upper bound at `digits` significant figures, taken UPWARD
    on the float's exact decimal value, so the printed figure is never below
    the value it stands for and a sentence that says no move exceeded it, or
    that a move was up to it, holds at the figure printed. `grouping` is the
    format's thousands separator (`","`), or none. A figure that is not finite
    prints as Python formats it (`inf`, `nan`), so the refusal stating it still
    returns."""
    if not math.isfinite(value):
        return f"{value:{grouping}.{digits}g}"
    exact = Decimal(value)
    step = Decimal(1).scaleb(exact.adjusted() - (digits - 1))
    return f"{float(exact.quantize(step, rounding=ROUND_CEILING)):{grouping}.{digits}g}"


def floored_figure(value: float, digits: int) -> str:
    """`ceiled_figure`'s mirror for a positive lower bound: taken DOWNWARD, so
    the printed figure is never above the value it stands for, and a sentence
    that says a figure lies above it holds at the figure printed."""
    return ceiled_figure(-value, digits).lstrip("-")


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
# §3.6 — draws and liveness, MEASURED on the block's own futures (§0.1 item 39)
# ---------------------------------------------------------------------------

class _DrawRecorder:
    """One matrix's addressed binding, noting which streams DRAW while it is
    priced.

    `run_monte_carlo` asks the binding for a stream's generator once per path
    (`_AddressedBinding` caches it), and the paths run one after another. So
    each generator handed out is compared with its own state at hand-out once
    the next one for the same stream is asked for, and every generator still
    open is compared at the end: a stream drew when some generator of it
    advanced. It is the generator-state instrument the contract tests use,
    kept as the engine's own measurement.
    """

    __slots__ = ("_inner", "_open", "_drawn")

    def __init__(self, inner) -> None:
        self._inner = inner
        self._open: Dict[int, Tuple[np.random.Generator, dict]] = {}
        self._drawn: set = set()

    def __getitem__(self, stream_id: int):
        source = self._inner[stream_id]

        def generator_for(path_index: int) -> np.random.Generator:
            got = source(path_index) if callable(source) else source
            if stream_id not in self._drawn:
                self._settle(stream_id)
                self._open[stream_id] = (got, got.bit_generator.state)
            return got

        return generator_for

    def _settle(self, stream_id: int) -> None:
        held = self._open.pop(stream_id, None)
        if held is not None and held[0].bit_generator.state != held[1]:
            self._drawn.add(stream_id)

    def drawn(self) -> Tuple[int, ...]:
        for stream_id in list(self._open):
            self._settle(stream_id)
        return tuple(sorted(self._drawn))


def _largest_move(base, redrawn) -> float:
    """The largest difference in any priced option's present value, on any
    future, between two priced matrices of the same futures."""
    moves = [
        float(np.max(np.abs(np.asarray(getattr(redrawn, name).pvs, dtype=np.float64)
                            - np.asarray(getattr(base, name).pvs, dtype=np.float64))))
        for name in OPTION_NAMES if getattr(base, name, None) is not None
    ]
    return max(moves) if moves else 0.0


def _liveness(base, redraws: Dict[int, object], threshold: float,
              paths: int) -> Tuple[Dict[int, float], Tuple[int, ...]]:
    """`(largest move per stream, live channel ids)` from `A` and each drawing
    stream's `A_B^(c)`.

    A channel is live when its move is NOT inside the all-frozen identity's
    own budget (`decomposition_math.identity_holds` against `identity_budget`):
    the one threshold, in its one home, so the engine never calls a difference
    live that it would call rounding in the identity check, nor the reverse.

    The income stream is re-drawn and measured like every other stream. It is
    not a channel, so a move beyond the budget there is not a row this block
    has a place for: the check fails (`income_moved`), naming the move, rather
    than printing a partition that leaves a present value's mover out.
    """
    moves = {stream_id: _largest_move(base, result)
             for stream_id, result in redraws.items()}
    moving = tuple(stream_id for stream_id in sorted(moves)
                   if not dm.identity_holds(moves[stream_id], threshold))
    if INCOME_STREAM_ID in moving:
        raise CheckFailed(
            "income_moved",
            f"re-drawing the income stream moved an option's present value on these "
            f"{int(paths):,} futures by up to ${ceiled_figure(moves[INCOME_STREAM_ID], 3)}, "
            f"above ${floored_figure(threshold, 3)}")
    return moves, moving


@dataclasses.dataclass(frozen=True)
class ChannelMeasurement:
    """What `measure_channels` measured on one sample of futures: the streams
    that drew, each drawing stream's largest present-value move under a
    re-draw, the threshold, and the channels live by it."""

    paths: int
    drawn: Tuple[int, ...]
    moves: Dict[int, float]
    threshold: float
    live: Tuple[int, ...]


def measure_channels(spec, *, det, verdict, paths: Optional[int] = None) -> ChannelMeasurement:
    """Draws and liveness on `paths` futures of `A` (default the config's
    `num_sims`), measured exactly as `decompose` measures them — the same
    recorder, the same re-draws, the same threshold — with no refusal and no
    budget gate in between. For a caller that wants the measurement alone, at
    a cost of one matrix per drawing stream plus `A`. The income-stream check
    raises `CheckFailed` here as it refuses the block in `decompose`."""
    spec_at_paths = _spec_at(spec, paths if paths is not None else spec.simulation.num_sims)
    base, drawn = _run_recording_draws(spec_at_paths)
    threshold = identity_budget(det, verdict)
    moves, live = _liveness(base, _redraws(spec_at_paths, drawn), threshold,
                            int(spec_at_paths.simulation.num_sims))
    return ChannelMeasurement(paths=int(spec_at_paths.simulation.num_sims), drawn=drawn,
                              moves=moves, threshold=threshold, live=live)


# ---------------------------------------------------------------------------
# §9 — the cost model: one formula, for the gate and for the count
# ---------------------------------------------------------------------------

def planned_evaluations(paths: int, k_draw: int, level_paths: int, *,
                        spread_priced: bool = True) -> int:
    """The most model evaluations this module spends — ONE formula, for the
    budget gate and for the count a test takes of what was actually priced:

        N * (k_draw + 2)  +  m * (k_draw + 1)

    `k_draw` is the number of streams that drew on `A`. The spread register
    prices `A`, `B` and one `A_B^(c)` per drawing stream at N paths; the level
    register prices one freeze per live channel — never more than `k_draw` —
    AND the all-frozen run at `m`. A cost model that left the all-frozen run
    out once recommended an N that priced above the ceiling it was chosen
    under; one formula cannot disagree with itself.

    `spread_priced=False` is the run where every future lies on one side of the
    line: `B` is not priced. The budget gate takes the default whichever side
    the futures sit on, so its figure is the most the module can spend, and
    its refusal says "up to".
    """
    spread = int(paths) * (int(k_draw) + (2 if spread_priced else 1))
    return spread + int(level_paths) * (int(k_draw) + 1)


def _level_paths(paths: int) -> int:
    return max(2, min(int(paths), LEVEL_PATHS))


def largest_affordable_paths(k_draw: int) -> int:
    """The largest `--decompose=N` whose planned work clears
    `EVALUATION_CEILING` with `k_draw` streams drawing — read off
    `planned_evaluations` itself, which is monotone in N, so the cost model
    keeps one home and this can never name an N the gate would refuse at that
    count, nor one whose priced work exceeds the ceiling it was chosen under.
    Fewer futures are a prefix of the same futures (`channel_stream` keys every
    path on its own index), so no stream draws on them that did not draw on
    more, and the count at the N it names is never larger."""
    low, high = 0, EVALUATION_CEILING
    while low < high:
        mid = (low + high + 1) // 2
        if planned_evaluations(mid, k_draw, _level_paths(mid)) <= EVALUATION_CEILING:
            low = mid
        else:
            high = mid - 1
    return low


# ---------------------------------------------------------------------------
# §8 — the refusals
# ---------------------------------------------------------------------------

def _refuse(code: str, reason: str, channel_id: Optional[int] = None) -> DecompositionRefusal:
    return DecompositionRefusal(code=code, reason=reason, channel_id=channel_id)


def _refusal_before_pricing(spec, mc, verdict, paths: int) -> Optional[DecompositionRefusal]:
    """Every §8 refusal decided before a single path is priced, in the order of
    the questions: are there futures at all, is there a margin, are there
    enough futures to interval, and can they be drawn even once within the
    ceiling. Each reason is the ONE measured fact that fired it (spec §0.1
    item 35) — a fact about this run, never an account of why it holds and
    never a route to another run.
    """
    if mc is None or single_path_run(spec):
        return _refuse("no_futures", "this run has no futures")
    priced = sum(getattr(spec, option) is not None for option in ("condo", "house", "rent"))
    if verdict is None and priced != 1:
        # The refusal below says the run prices one option; a caller that
        # passed no verdict for any other run is told nothing rather than that.
        raise ValueError(f"no verdict was passed for a run that prices {priced} options")
    if verdict is None or verdict.rule == "single_option":
        return _refuse("single_option", "this run prices one option")
    if paths < MIN_INTERVALLED_FUTURES:
        # Its own code, never `no_futures`: this run HAS futures, and a reader
        # (or a consumer keyed on the code) told it has none is told something
        # false about the run it just made.
        return _refuse(
            "too_few_futures",
            f"{paths:,} {'future was' if paths == 1 else 'futures were'} asked for, "
            f"below the minimum of {MIN_INTERVALLED_FUTURES}",
        )
    if paths > EVALUATION_CEILING:
        # `A` is priced whatever else happens, and it is where the drawing
        # streams are counted, so N above the ceiling is the one budget fact
        # decidable before pricing — and it holds whatever that count is.
        return _refuse(
            "budget",
            f"{paths:,} futures price {paths:,} path evaluations before any "
            f"re-draw, above the ceiling of {EVALUATION_CEILING:,} [set in the engine]",
        )
    return None


def _budget_refusal(paths: int, k_draw: int) -> Optional[DecompositionRefusal]:
    """§8 refusal 6 on the number of streams that drew on `A`, before any
    re-draw is priced. The largest N it prints is the one figure a refusal may
    carry beyond its fact (§0.1 item 35), computed by the gate's own cost model
    at the same count, so it can never name an N this gate would refuse."""
    work = planned_evaluations(paths, k_draw, _level_paths(paths))
    if work <= EVALUATION_CEILING:
        return None
    return _refuse(
        "budget",
        f"{paths:,} futures with {k_draw} streams drawing on them price up to "
        f"{work:,} path evaluations, above the ceiling of {EVALUATION_CEILING:,} "
        f"[set in the engine]; the largest path count within it is "
        f"{largest_affordable_paths(k_draw):,}",
    )


def _channel_refusal(live: Tuple[int, ...], paths: int) -> Optional[DecompositionRefusal]:
    """The refusals the live channels decide, measured on these futures: none
    live, or exactly one. Decided after the re-draws, never predicted."""
    if not live:
        return _refuse("no_spread", f"no channel is live on these {paths:,} futures")
    if len(live) == 1:
        only = channel(live[0])
        return _refuse("one_channel",
                       f"one channel is live on these {paths:,} futures: {only.label}",
                       channel_id=only.id)
    return None


# ---------------------------------------------------------------------------
# §5 — the widths, and who typed them (§0.1 item 53)
# ---------------------------------------------------------------------------

def _priced(spec) -> Tuple[str, ...]:
    return tuple(n for n in OPTION_NAMES if getattr(spec, n, None) is not None)


# The options whose draws a channel's sizing keys size, where the CHANNEL
# decides it. A cost or return channel's draws are its one option's: the three
# cost channels share `simulation.other_cost_vol`, so which option a key's
# draws belong to is the channel's, never the key's. The population prior's
# rows reach the owned options' values: `monte_carlo.run_monte_carlo` hands
# them to the condo's and the house's simulations, and the renter's reads none.
_CHANNEL_OPTIONS: Dict[int, Tuple[str, ...]] = {
    2: ("condo", "house"), 3: ("condo",), 4: ("house",), 5: ("rent",), 6: ("rent",)}

# On the economy's and the market's rows, the `simulation.*` sizing keys whose
# draws some options' simulations read and others' do not, and the options
# that read them: a correlation onto one option's shock, and the shock it
# pulls, are that option's; the market's value volatility sizes one draw the
# condo's and the house's simulations both read and the renter's does not.
# Any other key on those rows is under an option's own section, which is that
# option's, or sizes a draw every option's simulation reads.
_SIMULATION_KEY_OPTIONS: Dict[str, Tuple[str, ...]] = {
    "simulation.corr_inflation_condo": ("condo",),
    "simulation.corr_inflation_house": ("house",),
    "simulation.value_growth_vol": ("condo", "house"),
    "simulation.condo_fee_vol": ("condo",),
    "simulation.house_maintenance_vol": ("house",),
}

# Each economy correlation, and the sizing keys of the option shocks it
# composes the economy's draw into (`monte_carlo._correlated_z` at each draw
# site): §4 and §0.1 item 6 put those keys on the economy's row, noted.
_PULLS: Dict[str, Tuple[str, ...]] = {
    "simulation.corr_inflation_condo": ("simulation.condo_fee_vol",),
    "simulation.corr_inflation_house": ("simulation.house_maintenance_vol",),
    "simulation.corr_inflation_other": ("simulation.other_cost_vol",),
    "simulation.corr_inflation_event_cost": ("condo.events", "house.events", "rent.events"),
}


def sized_options(channel_id: int, key: str) -> Optional[Tuple[str, ...]]:
    """The options whose draws `key` sizes on channel `channel_id`'s row, or
    None where every option's simulation reads the draw. The one home of the
    filter §0.1 item 53 keeps: it is read off the simulator's draw sites
    (`monte_carlo`), never off a value the config gives the key."""
    if channel_id in _CHANNEL_OPTIONS:
        return _CHANNEL_OPTIONS[channel_id]
    section = key.split(".", 1)[0]
    if section in OPTION_NAMES:
        return (section,)
    return _SIMULATION_KEY_OPTIONS.get(key)


def _echo_of(spec, raw):
    """`spec`, carrying the read-back's source echo: the loader's own, or for
    a directly-constructed spec the echo that same loader builds from `raw`."""
    if getattr(spec, "sources", None) is not None or raw is None:
        return spec
    from .sources import build_source_echo
    return dataclasses.replace(spec, sources=build_source_echo(raw)[0])


def _given(spec, key: str) -> bool:
    """Whether the read-back carries `key`: the config states it (the source
    echo's entry) or the run defaulted it (`spec.defaults_applied`)."""
    echo = spec.sources
    return (echo is not None and echo.get(key) is not None) or key in spec.defaults_applied


def width_keys(spec, channel_id: int) -> Tuple[Tuple[str, Optional[str]], ...]:
    """`(key, pulled by)` for every width on channel `channel_id`'s row — the
    ONE home of which keys a row names (§0.1 item 53): the channel's sizing
    keys (`CHANNELS`) that the config states or the run defaulted, for an
    option this run prices (`sized_options`), in `CHANNELS`' order; then, on
    the economy's row, after all of those, the keys of the shocks its
    correlations among them pull, under the same rule, in the order of the
    correlations that pull them. `pulled by` is that correlation, or None."""
    priced = set(_priced(spec))

    def member(key: str) -> bool:
        options = sized_options(channel_id, key)
        return _given(spec, key) and (options is None or bool(priced.intersection(options)))

    out: List[Tuple[str, Optional[str]]] = []
    for key in channel(channel_id).sizing_keys:
        if member(key):
            out.append((key, None))
    for key, _ in list(out):
        out.extend((pulled, key) for pulled in _PULLS.get(key, ()) if member(pulled))
    return tuple(out)


def _width(spec, key: str, pulled_by: Optional[str], label: str) -> Width:
    """One member of `width_keys` on the row of `label` as a `Width`: its
    figure and its tag as the read-back gives them
    (`serialization.read_back_tag`, character for character), and for a pulled
    key the correlation's figure and its square. A member with no read-back
    tag fails the check (`untagged_width`): nothing can say whose figure it
    is, and a width left out would be an absence nobody reported."""
    from .serialization import default_anchor, echo_value, read_back_tag
    tag = read_back_tag(spec, key)
    if tag is None:
        raise CheckFailed("untagged_width",
                          f"{key}, a width on the row of {label}, has no tag in the "
                          f"read-back")
    note = None
    if pulled_by is not None:
        rho = float(getattr(spec.simulation, pulled_by.split(".", 1)[1]))
        note = f"pulled by {pulled_by} = {rho:g}; rho squared {rho * rho:g}"
    entry = spec.sources.get(key) if spec.sources is not None else None
    if entry is not None:
        return Width(key=key, formatted=entry.formatted, source=entry.source,
                     anchor=entry.anchor, note=note, tag=tag)
    anchor = default_anchor(spec, key)
    return Width(key=key, formatted=echo_value(spec, key), source="default",
                 anchor=anchor.name if anchor is not None else None, note=note, tag=tag)


def _widths_for(spec, raw, entry: Channel) -> Tuple[Width, ...]:
    """The widths on one channel's row: every member of `width_keys`, in
    its order."""
    spec = _echo_of(spec, raw)
    return tuple(_width(spec, key, pulled_by, entry.label)
                 for key, pulled_by in width_keys(spec, entry.id))


# ---------------------------------------------------------------------------
# The rows with no place in the spread or the level (§3.5, §0.1 items 39-40)
# ---------------------------------------------------------------------------

# The keys a row for the income stream names, where the config states them.
_INCOME_KEYS: Tuple[str, ...] = ("income.pay_drop_events",)


def _dead_draw_rows(spec, raw, drawn: Tuple[int, ...], live: Tuple[int, ...],
                    paths: int, threshold: float) -> List[StructuralZero]:
    """A `dead_draw` row for every stream that drew on these futures and is not
    live on them: both facts MEASURED, and scoped to the futures and the
    threshold they were measured on. The row names its stream, and the keys it
    carries are the keys of that stream's widths (`width_keys`; for the income
    stream, its keys the read-back carries). Its words are said of the stream,
    never of a key's cash flow (§0.1 items 40 and 53)."""
    spec = _echo_of(spec, raw)
    rows: List[StructuralZero] = []
    for stream_id in drawn:
        if stream_id in live:
            continue
        if stream_id == INCOME_STREAM_ID:
            label = INCOME_STREAM_LABEL
            keys = tuple(key for key in _INCOME_KEYS if _given(spec, key))
        else:
            entry = channel(stream_id)
            label = entry.label
            keys = tuple(w.key for w in _widths_for(spec, raw, entry))
        rows.append(StructuralZero(
            kind="dead_draw", label=label, keys=keys, channel_id=stream_id,
            measured_paths=int(paths), move_threshold=float(threshold)))
    return rows


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
    dead: Tuple[StructuralZero, ...],
) -> SpreadRegister:
    """The spread register: two Sobol shares, the flip fraction and the gap
    between the shares per channel, and the interaction residual.

    Every figure comes from `decomposition_math`; the only judgments here are
    which rows resolved, which row is on top and whether it leads (`_top_row`),
    and which rows' gaps resolved. A resample of the bootstrap that holds one
    value of `f` fails the check (`degenerate_resample`).

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
    try:
        first_ci, total_ci, flip_ci, sum_ci = dm.bootstrap_spread_intervals(
            f_a, f_b, f_ab, seed=seed)
    except dm.DegenerateResample as flat:
        raise CheckFailed(
            "degenerate_resample",
            f"the margin is identical on all {flat.n_futures:,} draws of bootstrap "
            f"resample {flat.resample:,} of {flat.n_resamples:,} "
            f"({signed_dollars(flat.value, 2)})") from flat
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
                          interaction_channel_ids=interacting,
                          structural_zeros=dead)


def _one_side_of_the_line(best_cheapest: float) -> bool:
    """§0.1 items 7, 29 and 36: the spread register refuses when `f` never
    changes sign on the block's futures — `P(f > 0)` of exactly 0 or exactly 1.
    A design choice about what prints, not a claim that a re-draw could move no
    future across the line (item 36 measured one that does). The ONE home of
    that condition."""
    return best_cheapest in (0.0, 1.0)


def _no_sign_variation(best: str, futures: int, best_cheapest: float,
                       dead: Tuple[StructuralZero, ...]) -> RefusedSpread:
    """The spread register's refusal in its own slot; the level register still
    prints. Its reason is the measured fact alone (§0.1 item 36)."""
    if not _one_side_of_the_line(best_cheapest):
        raise ValueError(
            f"P({best} cheapest) is {best_cheapest!r} on this sample, so futures sit on "
            f"both sides of the line and the spread register has shares to print")
    reason = (f"{best} is cheapest in all {futures:,} of these futures"
              if best_cheapest == 1.0 else
              f"{best} is cheapest in none of these {futures:,} futures")
    return RefusedSpread(code="no_sign_variation", reason=reason, structural_zeros=dead)


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
    all-frozen margin as the central case's over a run where it is not.

    `all_frozen_deviation` is NOT gated here but by `_identity_failed`: it is
    held to a ULP budget scaled to the totals subtracted, never to zero.
    """
    return _refuse(
        "freeze_leak",
        f"with every channel frozen, the margins of the {level.paths:,} paths "
        f"differ by up to ${ceiled_figure(level.all_frozen_path_spread, 6, ',')}",
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

    It is also the threshold liveness is measured against (`_liveness`): a
    re-draw that moves no present value by more than the rounding this check
    allows moves nothing the block can tell from rounding.
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
        f"{signed_dollars(level.all_frozen_margin, 2)} against the central case's "
        f"{signed_dollars(verdict.margin_pv, 2)}, "
        f"${ceiled_figure(level.all_frozen_deviation, 3)} apart, "
        f"above the ${floored_figure(budget, 3)} this check allows",
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

    Every evaluation this module spends goes through `run_monte_carlo` in this
    module's namespace (here and in `_run_recording_draws`), so a test that
    replaces it counts all of them — and a partial freeze can never reach the
    legacy binding, which refuses it rather than returning an unpaired number.
    """
    streams = addressed_streams(spec_at_paths.simulation.random_seed,
                                matrix_id, swapped)
    return run_monte_carlo(spec_at_paths, streams, freeze=tuple(freeze))


def _run_recording_draws(spec_at_paths):
    """`A`, priced once, and the stream ids whose generators advanced while it
    was: `(result, drawn ids)`."""
    recorder = _DrawRecorder(addressed_streams(spec_at_paths.simulation.random_seed,
                                               MATRIX_A))
    result = run_monte_carlo(spec_at_paths, recorder)
    return result, recorder.drawn()


def _redraws(spec_at_paths, drawn: Tuple[int, ...]) -> Dict[int, object]:
    """`A_B^(c)` for every stream that drew on `A`: `A` with that stream's
    draws taken from `B`, so the two differ in that stream alone."""
    return {stream_id: _run(spec_at_paths, MATRIX_A, {stream_id: MATRIX_B})
            for stream_id in drawn}


def decompose(spec, *, det, mc, verdict, raw=None,
              paths: Optional[int] = None) -> DecompositionOutcome:
    """WHICH RISK DECIDES IT — the whole block, assembled from one spec.

    The seam §0.1 item 17 names, and the only entry point: `--decompose` calls
    this and renders what comes back. Silence is the CLI's — the flag not
    passed means this function is never called — so what it returns is either
    the block or a named refusal, never None.

    Args:
        spec: the run's own `ComparisonSpec`.
        det, mc, verdict: THIS run's deterministic result, Monte Carlo result
            and verdict. They are read, never recomputed: the verdict stays
            `models.compute_verdict`'s; `mc` says whether the run has futures;
            `det` and `verdict` size the identity's budget.
        raw: the mapping the config came from, from which a spec that carries
            no source echo gets the read-back's tags for its widths.
        paths: `--decompose=N`'s sample-size override, consumed here because N
            is a compute-time figure (§0.1 item 16). Default is the config's
            own `num_sims`.

    Returns:
        `Decomposition`, or `DecompositionRefusal` when §8 says the honest
        output is a named reason rather than a table.
    """
    requested = int(paths) if paths is not None else int(spec.simulation.num_sims)
    refusal = _refusal_before_pricing(spec, mc, verdict, requested)
    if refusal is not None:
        return refusal

    seed = int(spec.simulation.random_seed)
    best = verdict.best
    level_paths = _level_paths(requested)
    spec_at_paths = _spec_at(spec, requested)

    # `A` first: the futures every figure is taken on, and the run the drawing
    # streams are counted on.
    base, drawn = _run_recording_draws(spec_at_paths)
    f_a = margin_per_path(base, best)
    if float(np.ptp(f_a)) == 0.0:
        # §0.1 item 37: the measured fact only. A channel can move an option
        # that never enters the margin; nothing here says which moves what.
        # Identical is max == min, exactly: a variance of 2,000 copies of one
        # figure is not always 0.0, because their mean need not be that figure
        # to the last bit.
        return _refuse(
            "no_spread",
            f"the margin is identical on all {f_a.size:,} futures "
            f"({signed_dollars(float(f_a[0]), 2)})",
        )
    refusal = _budget_refusal(requested, len(drawn))
    if refusal is not None:
        return refusal

    try:
        return _priced_block(spec, det, verdict, raw, requested, seed, best, level_paths,
                             spec_at_paths, base, drawn, f_a)
    except CheckFailed as failed:
        return _refuse(failed.code, failed.reason)


def _priced_block(spec, det, verdict, raw, requested: int, seed: int, best: str,
                  level_paths: int, spec_at_paths, base, drawn: Tuple[int, ...],
                  f_a: Array) -> DecompositionOutcome:
    """`decompose` from the re-draws on: the channel refusals, the spread and
    level registers and the identity's refusals. A check that cannot pass on
    the way raises `CheckFailed`, which `decompose` returns as the refusal."""
    # Which channels are live, on THESE futures: each drawing stream re-drawn.
    threshold = identity_budget(det, verdict)
    redraws = _redraws(spec_at_paths, drawn)
    _, live = _liveness(base, redraws, threshold, requested)
    refusal = _channel_refusal(live, requested)
    if refusal is not None:
        return refusal
    # Measured on these futures, so the spread register's (§0.1 item 48).
    dead = tuple(_dead_draw_rows(spec, raw, drawn, live, requested, threshold))

    spread: Union[SpreadRegister, RefusedSpread]
    best_cheapest = float(np.mean(f_a > 0.0))
    if _one_side_of_the_line(best_cheapest):
        spread = _no_sign_variation(best, int(f_a.size), best_cheapest, dead)
    else:
        f_b = margin_per_path(_run(spec_at_paths, MATRIX_B), best)
        # The table is CHANNEL-MAJOR: row c is that channel's `A_B^(c)`, the
        # same matrix its liveness was measured on, and `decomposition_math`
        # validates the shape and raises on a transpose rather than returning
        # a plausible wrong table.
        f_ab = np.stack([margin_per_path(redraws[channel_id], best)
                         for channel_id in live], axis=0)
        widths_by_channel = {
            channel_id: _widths_for(spec, raw, channel(channel_id))
            for channel_id in live
        }
        spread = _spread_register(f_a, f_b, f_ab, live, widths_by_channel, seed, dead)

    level = _level_register(spec, verdict, best, f_a, live, seed, level_paths)
    if level.all_frozen_path_spread != 0.0:
        return _freeze_leak(level)
    if not dm.identity_holds(level.all_frozen_deviation, threshold):
        return _identity_failed(level, verdict, threshold)

    return Decomposition(
        paths=int(f_a.size),
        max_paths=largest_affordable_paths(len(drawn)),
        live_channel_ids=live,
        verdict=verdict,
        mean_margin=float(np.mean(f_a)),
        sd_margin=float(np.std(f_a)),
        spread=spread,
        level=level,
    )
