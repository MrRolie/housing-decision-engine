"""Which risk decides it — the three registers, as TYPES ONLY.

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`. This module is the
contract four parallel tracks (spec §12) build against, and the only file they
share. It holds the seven-channel table and the shape of every object those
tracks hand each other. It computes NOTHING: no statistic, no draw, no
sentence. Arithmetic in this file is a defect — it belongs in the track that
owns it.

WHAT THE THREE REGISTERS ARE, because they answer different questions and a
reader who conflates two of them is the failure this feature exists to prevent
(spec §1):

  - the SPREAD register — where the scatter of the decision margin comes from,
    as grouped Sobol indices (§3.3);
  - the LEVEL register — what the simulated futures price that the central case
    does not, as the freeze mask's paired shift (§3.4). NOT "what if this input
    were different": a cost the deterministic line omits;
  - the REVERSAL register — what would have to change for the verdict to
    change, solved on inputs the user STATED and that carry no distribution
    (§6). It is the half with no assistant-chosen width anywhere in it.

THE BINDING (spec §5 mechanism 5, operator ruling 2026-09-22, superseding that
section's earlier "label" default). The spread register may NEVER be emitted
without the level register beside it. On this repo's own flagship fixture the
spread table's top row is the renter's portfolio at 0.88 of the scatter and
freezing it moves the decision by −$2,200, while the tenancy at 0.10 of the
scatter moves it by +$127,876 — 58x. A reader handed the spread table alone
quotes the channel that matters least. A label can be lost in a copy-paste; a
row the code will not emit without cannot be.

Here that ruling is encoded as far as a dataclass reaches: `Decomposition`
requires `spread`, `level` and `reversal` together, with no default on any of
them, so no "spread-only" result object can be constructed at all. THE
ENFORCEMENT IS COMPLETED BY TRACK D'S RENDERER — one function emits both
registers or neither, and no caller-reachable path returns the spread rows
alone (spec §12 track D, §7 formatter rule 1, test T7). This module cannot
reach the formatter; do not read the type as the whole guard.

TWO STATES THAT ARE NOT NONE AND NOT ZERO. A figure that did not resolve is a
DISTINCT STATE carrying its own estimate: §7 prints "not resolved at 2,000
futures (-0.001 [-0.002, 0.001])" and "indistinguishable from zero at 2,000
futures: your portfolio (-$3,805 ± $5,383)" as sentences with figures still in
them. No share is ever clamped into [0, 1] (§4) — a clamped number is the cheap
all-clear in this feature's costume. So the unresolved variants below name
their point estimate `provisional_*`, share NO attribute name with the resolved
variants for it, and derive from no common base: a formatter reaching for
`row.shares.alone` on an unresolved row raises `AttributeError` rather than
printing a figure as though it resolved.

The same device carries the interaction branch (§4): `ResolvedInteraction` has
a `residual`, `RefusedInteraction` has no such attribute at all, and §5
mechanism 4's assistant-typed share sum lives INSIDE the resolved variant —
so it is structurally impossible to print that sum on the branch where it is
noise.

EXACT AND ESTIMATED REVERSALS ARE NOT ONE KIND WITH A FLAG (spec §0, §6). The
split is a property of the model — whether the engine computed the distance
exactly or estimated it — never a ranking, and the operator's ruling forbids
ranking across it. `ExactReversal` and `EstimatedReversal` therefore share no
base class and no field set: the exact kind carries its licence evidence and a
confirming re-simulation, the estimated kind carries an interval and the sample
that produced it. `list(exact) + list(estimated)` does not typecheck and cannot
render as one ordered table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple, Union

if TYPE_CHECKING:  # no runtime import: this module stays free of engine code
    from .models import Verdict


# ---------------------------------------------------------------------------
# The channel partition (spec §3.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Channel:
    """One group of primitive DRAW SITES, not one group of config keys.

    The partition is over draw sites because the engine composes every
    correlation from independent primitives, so grouping this way makes Sobol's
    independence assumption true rather than assumed (§3.1). `sizing_keys` are
    the dotted config keys that SIZE the channel — the keys §5 mechanism 1
    looks up in `sources.SourceEcho` to build the provenance cell, so that
    column needs no second table. A key may size more than one channel
    (`simulation.other_cost_vol` sizes three) and that is the truth, not a
    defect.
    """

    id: int
    key: str
    label: str
    sizing_keys: Tuple[str, ...]


# The table. Ids are FIXED INTEGERS and are the positions in this tuple; they
# are never derived from set or dict iteration order (the defect `_world_draws`
# already sorts `drift_bands` to avoid). Per-path stream keying (§3.2) was
# chosen so that adding an eighth channel cannot move ids 0–6, and so that a
# config with a different `k_live` gets the same draws for the channels it
# shares. Changing an id changes every drawn number in a run.
CHANNELS: Tuple[Channel, ...] = (
    Channel(
        id=0,
        key="economy",
        label="the economy",
        # The correlations are sizing keys, not decoration: at rho = 0.5 a
        # QUARTER of that shock's variance (rho² = 0.25) is attributed here,
        # so the cell that omits them is itself a wrong answer (§4). §4 also
        # requires the cell to name THE OPTION VOLS THOSE KEYS PULL FROM, which
        # depend on which rho is non-zero and so cannot live in a static table:
        # they reach the row as extra `Width` entries or notes from the track
        # that reads the spec. §7's own draft lists only the keys below.
        sizing_keys=(
            "economic.inflation_vol",
            "simulation.corr_inflation_condo",
            "simulation.corr_inflation_house",
            "simulation.corr_inflation_other",
            "simulation.corr_inflation_event_cost",
        ),
    ),
    Channel(
        id=1,
        key="market",
        label="the housing market",
        sizing_keys=(
            "simulation.value_growth_vol",
            "condo.price_shock.annual_hazard",
            "condo.price_shock.severity_mean",
            "condo.price_shock.severity_vol",
            "house.price_shock.annual_hazard",
            "house.price_shock.severity_mean",
            "house.price_shock.severity_vol",
        ),
    ),
    Channel(
        id=2,
        key="population",
        label="the population",
        sizing_keys=("market_scenario.path", "market_scenario.geography"),
    ),
    Channel(
        id=3,
        key="condo",
        label="the condo's costs",
        sizing_keys=(
            "simulation.condo_fee_vol",
            "simulation.other_cost_vol",
            "condo.events",
        ),
    ),
    Channel(
        id=4,
        key="house",
        label="the house's costs",
        sizing_keys=(
            "simulation.house_maintenance_vol",
            "simulation.other_cost_vol",
            "house.events",
        ),
    ),
    # The renter split is not deferrable (§3.1): lumped, the renter is one row
    # naming nothing a household can act on. Split, the level register
    # separates them completely — one is pure risk, one is an omitted cost.
    Channel(
        id=5,
        key="shelter",
        label="your tenancy",
        sizing_keys=(
            "simulation.rent_escalation_vol",
            "simulation.other_cost_vol",
            "rent.events",
            "rent.reset_hazard",
        ),
    ),
    Channel(
        id=6,
        key="portfolio",
        label="the renter's portfolio",
        sizing_keys=("simulation.investment_return_vol",),
    ),
)


def channel(channel_id: int) -> Channel:
    """The channel with this fixed id. Ids are positions: `CHANNELS[i].id == i`."""
    if not 0 <= channel_id < len(CHANNELS):
        raise KeyError(channel_id)
    return CHANNELS[channel_id]


def channel_by_key(key: str) -> Channel:
    """The channel with this stable machine key."""
    for entry in CHANNELS:
        if entry.key == key:
            return entry
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Shared small types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Interval:
    """A 95% interval, never clamped into [0, 1].

    On every share and on ΣS_c it comes from the 300-resample bootstrap over
    path indices (§3.3), whose generator is seeded from the run's seed and a
    fixed salt — never from the run's own stream, so it consumes no draw and
    reproduces across processes (test T15). On `EstimatedBoundary.value_ci` it
    is instead where a re-simulated curve locates a crossing, which is a
    different mechanism carrying the same shape.
    """

    low: float
    high: float


@dataclass(frozen=True)
class Width:
    """One figure that SIZES a channel, with whose figure it is (§5 mechanism 1).

    Inline on its own row, never deferred to a trailing footnote (§7 rule 7): a
    reader cannot see the ranking without seeing whose numbers produced it.
    `source` is whatever `sources.SourceEcho.classify` returns for `key` —
    read from there, never inferred from the key's name (test T14) and never
    restated as a vocabulary here. `formatted` is None when the row names a key
    whose value is not a figure (`market_scenario.path`).
    """

    key: str
    formatted: Optional[str]
    source: str
    anchor: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# The spread register (spec §3.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedShares:
    """A channel's two Sobol shares, both inside [0, 1] at this sample size.

    `alone` is Saltelli 2010's first-order index: if you learned this channel's
    realization exactly and nothing else, the spread's variance would fall by
    that fraction. `with_interaction` is Jansen 1999's total index. Neither is
    how often the channel changes the answer — that is `SpreadRow.flip`.
    """

    alone: float
    alone_ci: Interval
    with_interaction: float
    with_interaction_ci: Interval


@dataclass(frozen=True)
class UnresolvedShares:
    """The same two shares, not resolved at this register's sample size.

    Reached when a share falls outside [0, 1] — the house's measured
    `-0.001 [-0.002, 0.001]` on the fixture. The estimates are KEPT and printed
    ("not resolved at 2,000 futures (-0.001 [-0.002, 0.001])"), never clamped
    and never dropped. They are named `provisional_*` so that no formatter can
    read a resolved figure off an unresolved row by attribute name.
    
    ONE ROW STATE FROM TWO FIGURE VERDICTS (seat ruling 2026-09-21, §0.1
    item 11): a row is unresolved if EITHER figure is unresolved. The rule was
    unstated and the assembly was about to have to invent it. Conservative is
    correct here for the same reason the register refuses at all — the
    alternative prints one resolved figure beside one that is noise and leaves
    the reader to notice, which is the failure this whole feature exists to
    stop. It also matches §7's own house row.
    """

    provisional_alone: float
    provisional_alone_ci: Interval
    provisional_with_interaction: float
    provisional_with_interaction_ci: Interval


Shares = Union[ResolvedShares, UnresolvedShares]


@dataclass(frozen=True)
class SpreadRow:
    """One channel's share of the decision margin's scatter.

    `flip` is a FRACTION OF FUTURES, not a share of the spread: re-drawing this
    channel and nothing else, this fraction of futures changes sides on which
    option is cheapest. It is never optional (§7 rule 4) and survives an
    unresolved row, so it sits outside `shares` — it is the only column that
    speaks in decision space, and on the fixture's portfolio the two numbers a
    reader will otherwise conflate are 0.88 and 0.41.

    `flip_ci` carries its bootstrap interval (seat ruling 2026-09-21, §0.1
    item 10). §3.3 says 95% intervals on EVERY figure; §7's draft prints no
    interval on this column, and the draft loses. The reason this column in
    particular may not be printed bare is the reason it exists: it is the one
    figure here stated in decision space, so a reader takes it as the answer
    to "how often does this change my mind" — and a point estimate with no
    width, standing where every neighbouring figure carries one, reads as the
    most certain number in the table when it is not.
    """

    channel_id: int
    shares: Shares
    flip: float
    flip_ci: Interval
    widths: Tuple[Width, ...]


@dataclass(frozen=True)
class ResolvedInteraction:
    """ΣS_c resolved: its bootstrap interval lies entirely BELOW 1 (§4).

    `residual` is `1 − ΣS_c`, movement no single channel owns. It exists only
    on this branch. `unstated_first_order_sum` is §5 mechanism 4 — the summed
    first-order shares of the channels whose widths are entirely
    assistant-typed, named as a sum of first-order shares and never as a joint
    share. It lives here rather than on the register because it is noise on the
    refused branch, and a block that refuses to print a figure as a residual
    and then prints it as a provenance finding tells the reader two different
    things about one number. None when every width is the user's or an
    anchor's, where the clause does not print at all.
    """

    first_order_sum: float
    first_order_sum_ci: Interval
    residual: float
    residual_ci: Interval
    unstated_first_order_sum: Optional[float] = None
    unstated_first_order_sum_ci: Optional[Interval] = None


@dataclass(frozen=True)
class RefusedInteraction:
    """ΣS_c refused: its interval includes or exceeds 1, so no residual prints.

    Measured on the fixture at its committed 2,000 paths: 1.164 [1.042, 1.310].
    The line says the shares add to more than the whole, that this is estimator
    noise and not a finding, and that interaction is not measurable at this
    sample size. There is deliberately no `residual` attribute: the refusal is
    unreachable if ΣS is clamped to 1 (test T5), and unprintable-by-accident if
    the field does not exist.
    """

    first_order_sum: float
    first_order_sum_ci: Interval


Interaction = Union[ResolvedInteraction, RefusedInteraction]


@dataclass(frozen=True)
class SpreadRegister:
    """Where the decision margin's scatter comes from.

    `leading_channel_id` is the resolved row with the largest `alone`, None
    when no row resolves. Three sentences name it — §5 mechanism 3's gate, §7's
    "on your portfolio the two are 0.88 and 41%", and the level register's
    closing "your portfolio is 88% of the spread" — and it is carried so that
    none of them has to branch on the `Shares` union to reach a point estimate.

    `superlative_licensed` is §5 mechanism 3's gate: true only when every width
    of the leading row is user-stated or anchored, and only then may the block
    write "X decides the spread of this answer". `check_first` is the figure
    the ungated sentence names instead — the one number the ranking would move
    on. Both are carried rather than re-derived by the formatter so that
    flipping one `sources:` entry changes them, and a test can say so (T14).
    """

    rows: Tuple[SpreadRow, ...]
    interaction: Interaction
    leading_channel_id: Optional[int]
    superlative_licensed: bool
    check_first: Optional[Width]


# ---------------------------------------------------------------------------
# The level register (spec §3.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedLevel:
    """A channel whose freeze moves the expected margin by more than 2·SE.

    `delta` is what the futures price that the central case does not — a cost
    the deterministic line omits, read as a cost and never as a risk.
    `prob_best_frozen` is P(best cheapest) with this channel priced the central
    case's way, the right-hand side of the "0.34 -> 0.54" column.
    """

    delta: float
    se: float
    prob_best_frozen: float


@dataclass(frozen=True)
class IndistinguishableLevel:
    """A channel whose freeze moves the margin by no more than 2·SE.

    The honest reading of the portfolio's `-$3,805 ± $5,383`, and a row a
    reader must SEE rather than an absence: the channel carrying 88% of the
    spread moves the answer by nothing that resolves, which is the whole
    finding. `provisional_delta` shares no name with `ResolvedLevel.delta` so
    that no formatter can print it in the resolved column.
    """

    provisional_delta: float
    se: float
    prob_best_frozen: float


Level = Union[ResolvedLevel, IndistinguishableLevel]


@dataclass(frozen=True)
class LevelRow:
    channel_id: int
    level: Level


@dataclass(frozen=True)
class LevelRegister:
    """What the simulated futures price that the central case does not.

    `paths` is this register's OWN sample (`m = min(num_sims, 2000)` by
    default): a paired mean needs far fewer paths than a variance ratio, so it
    is generally not the spread register's count.

    `futures_margin` and `prob_best_base` are measured ON THAT SAMPLE and are
    therefore NOT the header's `Decomposition.mean_margin` nor
    `verdict.prob_best`. They are separate estimates of the same quantities and
    the formatter must read them from here, or the block prints two figures for
    one truth without saying so. UNRULED, and the seat owes an answer: §3.4 has
    the unfrozen channels reading "their own unchanged A stream", which would
    make these identical to the header's whenever `paths == self.paths`, while
    §7's draft has them differ ($31,349 − (−$67,194) is $98,543, not the
    $100,876 gap it prints). If the register reprices A[:m] rather than drawing
    its own sample, these two fields collapse into the header's and should go.

    `all_frozen_margin` and `all_frozen_max_deviation` are the identity that
    makes this register a fact rather than a claim: with EVERY channel frozen
    the margin equals `verdict.margin_pv` on every path (measured 31348.656075,
    max deviation 5.8e-11). A mask that misses a draw site fails it; a mask
    that reaches another channel's site fails it (test T2).

    `accounted_for` is the sum of ALL rows' shifts, the indistinguishable ones
    included, against the gap `all_frozen_margin − futures_margin`. It is
    carried rather than summed by the formatter precisely because summing it
    would mean reaching into `provisional_delta`.

    `leading_channel_id` is the resolved row with the largest |Δ| — the channel
    the closing sentence names. None when no row resolves. WHICH sentence is
    chosen is `verdict.state`'s business, never the sign of anything (§7 rule
    2): a formatter with one branch prints a disagreement explanation on an
    agreement.
    """

    rows: Tuple[LevelRow, ...]
    paths: int
    prob_best_base: float
    futures_margin: float
    all_frozen_margin: float
    all_frozen_max_deviation: float
    accounted_for: float
    leading_channel_id: Optional[int]


# ---------------------------------------------------------------------------
# The reversal register (spec §6)
# ---------------------------------------------------------------------------

# The verdict fields a boundary can be solved on. `runner_up` is here because
# §6's own measured results report a runner-up crossing (2.9549% on the
# fixture) that its enumerating sentence omits.
BOUNDARY_FIELDS: Tuple[str, ...] = ("best", "runner_up", "mc_best", "decisive")

# §3.5's three kinds. `stated_path`: stated by the user, never drawn (the
# renewal ladder) — its row carries numbers from §6, never a dash.
# `no_pv_reach`: draws exist and reach no present value (the income block).
# `dead_draw`: a CHANNEL that draws every year and reaches no cash flow (the
# real-mode inflation trap), detected from the spec and costing no evaluation.
STRUCTURAL_ZERO_KINDS: Tuple[str, ...] = ("stated_path", "no_pv_reach", "dead_draw")


@dataclass(frozen=True)
class AxisReference:
    """A cited point on a reversal axis, to place the solved rate against.

    `note` carries what the citation does NOT license — a posted rate is a list
    price bracketing a guess from above, never a ceiling on a 2031 renewal.
    """

    label: str
    value: float
    formatted: str
    anchor: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class Boundary:
    """A verdict change solved EXACTLY, and confirmed by re-simulation.

    `curve_probabilities` come from the free curve, `confirming_probabilities`
    from one full re-simulation at the solved value; the row refuses when they
    differ (§6, test T11). Both are option→P(cheapest) pairs rather than a
    mapping, so the frozen row is frozen all the way down.
    """

    verdict_field: str
    value: float
    was: str
    becomes: str
    curve_probabilities: Tuple[Tuple[str, float], ...]
    confirming_probabilities: Tuple[Tuple[str, float], ...]


@dataclass(frozen=True)
class RefusedBoundary:
    """A boundary that exists on the curve and is not printed (§8 refusal 7).

    Either it is not identified inside Monte Carlo noise (bracket-wide |ΔP|
    under 2·SE) or its confirming re-simulation disagreed with the free curve.
    Recorded rather than dropped: a boundary that vanishes with no row is an
    absence a reader reads as "nothing here".
    """

    verdict_field: str
    reason: str


@dataclass(frozen=True)
class ExactReversal:
    """A stated input whose reversal distance the engine computed EXACTLY.

    Licensed by the exactness gate (§6): every option the key does not name is
    bit-identical, and the option it names moves by one constant on every path
    to `max_path_deviation_over_sd` of its own standard deviation. Measured
    separation on the fixture is fourteen orders of magnitude, so nothing here
    rests on a tuned threshold.

    `path_note` is `sweep.flattened_path_note`'s sentence, present whenever the
    config states this key as a path: every grid point replaces the whole
    stated path with ONE figure, so the user's own schedule is not a point on
    the line, and the row may never claim they stated a flat rate.

    `bracket_source` is the source class of the BRACKET's own width, in
    `Width.source`'s vocabulary — "assistant" for every `break_even`
    `RATE_BRACKETS` entry. §6's 2026-09-21 correction is why it exists: adding
    a renewal entry converts an honest refusal into an answer, a higher bar
    than replacing a silent default, so the bracket's width must be PRINTED
    rather than assumed. A bracket figure on a row with no source class is the
    honesty contract's own breach.
    """

    key: str
    option: str
    stated_formatted: str
    bracket_low: float
    bracket_high: float
    bracket_source: str
    probe_paths: int
    max_path_deviation_over_sd: float
    boundaries: Tuple[Boundary, ...]
    refused_boundaries: Tuple[RefusedBoundary, ...]
    references: Tuple[AxisReference, ...]
    path_note: Optional[str] = None


@dataclass(frozen=True)
class EstimatedBoundary:
    """A verdict change LOCATED by re-simulation, inside an interval.

    Deliberately not a `Boundary`: there is no confirming re-simulation to
    compare against, because re-simulation is how the value was found. The
    interval is the figure; the point is where inside it the estimate landed.
    """

    verdict_field: str
    value: float
    value_ci: Interval
    was: str
    becomes: str
    resimulation_paths: int


@dataclass(frozen=True)
class EstimatedReversal:
    """A stated input whose reversal distance the engine ESTIMATED.

    Shares no base class and no field set with `ExactReversal` (spec §0's
    ruling): the split is a property of the model, not a ranking, and two types
    that could be concatenated into one ordered table would reintroduce the
    ranking the operator refused. `max_path_deviation_over_sd` is here too, and
    it is the figure that FAILED the exactness gate — the reason this row is in
    this tuple rather than the other one.

    SLICE 1 POPULATES THIS NEVER, and that is not an oversight: §6 REFUSES
    every key that fails the exactness gate rather than estimating it, and §14
    defers the keys that would need estimating. The type exists because the
    operator's ruling is that the rows GROUP by exactness, and a group that
    appears later must not arrive as a flag bolted onto the exact kind.
    """

    key: str
    option: str
    stated_formatted: str
    bracket_low: float
    bracket_high: float
    bracket_source: str
    max_path_deviation_over_sd: float
    boundaries: Tuple[EstimatedBoundary, ...]
    refused_boundaries: Tuple[RefusedBoundary, ...]
    references: Tuple[AxisReference, ...]
    path_note: Optional[str] = None


@dataclass(frozen=True)
class StructuralZero:
    """A channel or input with zero spread BY CONSTRUCTION, not by measurement.

    Printed as a named row with its reason, never as a dash and never as a
    measured `0.00`: a reader who sees six rows with numbers and one with
    dashes concludes the dashed thing was weighed and found irrelevant, and on
    the renewal ladder the truth is the opposite.

    `reversal_key` joins to the `ExactReversal` that carries this row's
    numbers, so the renewal ladder's row states its three solved rates rather
    than an absence. `channel_id` is set only for `dead_draw`, which is one of
    the seven; the others are not channels at all.
    """

    kind: str
    label: str
    keys: Tuple[str, ...]
    reason: str
    stated_formatted: Optional[str] = None
    channel_id: Optional[int] = None
    reversal_key: Optional[str] = None


@dataclass(frozen=True)
class ReversalRegister:
    """What would have to change for the verdict to change.

    The two row kinds are separate tuples, not one tuple with a flag. Any of
    the three may be empty on a config that states no qualifying input, and an
    empty tuple is data — it says the engine found no candidate, never that
    none exists.
    """

    exact: Tuple[ExactReversal, ...]
    estimated: Tuple[EstimatedReversal, ...]
    structural_zeros: Tuple[StructuralZero, ...]


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------

# §8's refusals that suppress the whole block, each with a named reason. The
# per-boundary refusal (§8 item 7) is `RefusedBoundary` and does not suppress
# anything. Silence — the flag not passed — is `None`, not a refusal.
REFUSAL_CODES: Tuple[str, ...] = (
    "no_futures",      # --no-monte-carlo, or a single-path run: there are no futures
    "single_option",   # fewer than two options priced: no margin exists
    "one_channel",     # k_live == 1: the table would read 1.00 and be a tautology
    "no_spread",       # Var(f) == 0: every index is 0/0
    "budget",          # the work gate: names the figure and the two ways out
)


@dataclass(frozen=True)
class DecompositionRefusal:
    """The block declining to print, with its own reason (§8).

    A refusal is not silence and not an empty block: it says which condition
    fired. `channel_id` is set by `one_channel`, which NAMES the channel
    carrying all of the run's spread and prints no numbers.
    """

    code: str
    reason: str
    channel_id: Optional[int] = None


@dataclass(frozen=True)
class Decomposition:
    """The whole block: three registers, never fewer.

    `spread`, `level` and `reversal` carry no defaults, so there is no
    "spread-only" `Decomposition` to construct (§5 mechanism 5). That is the
    type's half of the binding; track D's renderer completes it.

    `verdict` is the run's own `models.Verdict` object, held rather than copied:
    every probability and every state in this block comes back from
    `models.compute_verdict` and none is recomputed here (§1). The header's
    margin, its fraction of the best option's PV and the majority's probability
    are read off it.

    `mean_margin` and `sd_margin` are E[f] and sd(f) on the spread register's
    own A matrix at `paths`. `sd_margin` against `verdict.margin_pv` is the
    ratio that leads the block: a share of a spread means nothing until the
    reader knows how wide that spread is against the answer.

    `live_channel_ids` are the channels that consume at least one draw on this
    spec, computed from the spec the way `_world_draws` computes the world's.
    """

    paths: int
    live_channel_ids: Tuple[int, ...]
    verdict: "Verdict"
    mean_margin: float
    sd_margin: float
    spread: SpreadRegister
    level: LevelRegister
    reversal: ReversalRegister


# What the entry point returns: the block, a named refusal, or None for
# silence — the flag not passed, which is every run shipped today.
DecompositionOutcome = Optional[Union[Decomposition, DecompositionRefusal]]
