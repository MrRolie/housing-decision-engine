"""Which risk decides it — the three registers, as TYPES ONLY.

Design: `docs/specs/2026-09-22-which-risk-decides-it.md`. This module is the
contract every piece of the block is written against (spec §12's four pieces,
plus the assembler §0.1 item 17 found missing from them), and the only file
they share. It holds the seven-channel table and the shape of every object
those pieces hand each other. It computes NOTHING: no statistic, no draw, no
sentence. Arithmetic in this file is a defect — it belongs in the module that
owns it.

WHO BUILDS A `Decomposition`: the assembler, at
`hde/decomposition_run.py :: decompose(spec, *, det, mc, verdict, raw, prior)`
(§0.1 item 17). Every §8 refusal is ITS judgment, because it is the thing that
sees the data; the formatter RENDERS refusals and never decides them. The one
refusal the CLI owns is the seam being absent, which exits 1 with a named
error rather than printing nothing.

WHAT THE THREE REGISTERS ARE, because they answer different questions and a
reader who conflates two of them is the failure this feature exists to prevent
(spec §1):

  - the SPREAD register — where the scatter of the decision margin comes from,
    as grouped Sobol indices (§3.3);
  - the LEVEL register — what the simulated futures price that the central case
    does not, as the freeze mask's paired shift (§3.4). NOT "what if this input
    were different": a cost the deterministic line omits;
  - the REVERSAL register — what would have to change for the verdict to
    change, solved on inputs the CONFIG states, whoever typed them, and that
    carry no distribution (§6). No width is drawn in it, but the bracket each
    row is solved inside is assistant-chosen, and each row says so
    (`ExactReversal.bracket_source`), as it says whose the stated value is.

THE BINDING (spec §5 mechanism 5, operator ruling 2026-09-22, superseding that
section's earlier "label" default). The spread register may NEVER be emitted
without the level register beside it. On this repo's own flagship fixture the
level register (the freeze mask, 2,000 paths) prints the spread table's top
row, the renter's portfolio at 0.88 of the scatter, as moving the margin by
−$3,805 ± $5,385 — nothing that resolves — while the tenancy, at 0.10 of the
scatter, moves it by +$125,074 ± $1,775. A reader handed the spread table alone
quotes a channel whose shift this run cannot tell from zero and misses the one
that moves the margin. A label can be lost in a copy-paste; a row the code will
not emit without cannot be.

Here that ruling is encoded as far as a dataclass reaches: `Decomposition`
requires `spread`, `level` and `reversal` together, with no default on any of
them, so no "spread-only" result object can be constructed at all. THE
ENFORCEMENT IS COMPLETED BY THE FORMATTER (`decomposition_text`) — one function
emits both registers or neither, and no caller-reachable path returns the
spread rows alone (spec §7 formatter rule 1, test T7). This module cannot
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
        # they reach the row as extra `Width` entries or notes from the
        # assembler, which reads the spec. §7's own draft lists only the keys
        # below.
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
    # separates them — one carries scatter with no shift that resolves, one is
    # an omitted cost.
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


# Income's stream id, OUTSIDE the seven (§3.5.2, §0.1 item 21). It draws —
# `pay_drop_events` carries a timing and a severity draw — and reaches no
# present value, so it is a structural zero and never a row in any register. It
# still needs an id, because the streams binding must hand it a generator never
# shared with a channel that reaches a PV. It is refused by name in `freeze`,
# and a hand-built binding missing an id the run reaches RAISES naming the
# channel rather than falling back quietly. It is deliberately NOT in
# `CHANNELS`: that tuple is the decomposition's partition, not the stream
# roster, and `channel(INCOME_STREAM_ID)` therefore raises.
INCOME_STREAM_ID: int = 7


# §9: the most paths the LEVEL register prices. A paired mean needs far fewer
# paths than a variance ratio, so the register takes `min(N, LEVEL_PATHS)` of
# the decomposition's N and does not follow it upward. Held here, beside the
# types, because two pieces need it: the assembler sizes the register with it,
# and the formatter must know it to say truthfully whether a larger run would
# resolve a level row — past it, none does.
LEVEL_PATHS: int = 2000


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
    reproduces across processes (test T15). Its BOUNDS depend on that salt and
    on the resample count and will not reproduce across either; the point
    estimates never touch the bootstrap and are bit-identical across salts
    (§0.1 item 15). NOBODY TUNES THE SALT to match a figure in the design
    document, every interval printed in §7 is re-taken once the streams land,
    and §10's assertions stay inequalities with margin for that reason.

    On `EstimatedBoundary.value_ci` it is instead where a re-simulated curve
    locates a crossing — a different mechanism carrying the same shape.
    """

    low: float
    high: float


def _require_one_top(kind: str, leading: Optional[int],
                     unresolved_top: Optional[int]) -> None:
    """A register's top row is EITHER the leader (it resolved) OR the
    unresolved top (it did not) — never both. Both set would let the text name
    one channel as leading while the JSON names another as the largest, the
    disagreement this pair of fields exists to end."""
    if leading is not None and unresolved_top is not None:
        raise ValueError(
            f"{kind} names channel {leading} as leading AND channel {unresolved_top} "
            f"as an unresolved top row: the top row by point estimate either "
            f"resolved or did not, so exactly one of the two can be set")


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

    `alone` is Saltelli 2010's first-order index, CENTRED (§0.1 item 13): the
    published numerator carries an `E[f]·mean(f_AB − f_A)` term, zero in
    expectation and noisy in sample, whose error grows with |E f| / sd(f) and
    reaches 2.1x at 3σ — which is a DECISIVE run, so the case where the engine
    calls the answer settled is the case where the attribution behind it is
    worst. Centring the numerator's `f(B)` by its sample mean removes the term
    and is identical in expectation. Read: if you learned this channel's
    realization exactly and nothing else, the spread's variance would fall by
    that fraction. `with_interaction` is Jansen 1999's total index. Neither is
    how often the channel changes the answer — that is `SpreadRow.flip`.

    Both denominators are `Var(f(A))` alone, never the pooled A∪B variance
    (§0.1 item 14): pooling tightens ΣS and could make §4's refusal branch
    unreachable, which deletes a refusal rather than changing a decimal.
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
    
    ONE ROW STATE FROM TWO FIGURE VERDICTS (ruled 2026-09-21, spec §0.1
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
    channel and nothing else, this fraction of futures changes the sign of the
    margin `f` — whether `verdict.best`, the central case's winner, is cheapest
    there. It is NOT the fraction whose cheapest option changes: a future that
    moves from the condo to the house while `best` stays beaten keeps its sign
    and is not counted. It is never optional (§7 rule 4) and survives an
    unresolved row, so it sits outside `shares` — it is the only column that
    speaks in decision space, and on the fixture's portfolio the two numbers a
    reader will otherwise conflate are 0.88 and 0.41.

    `flip_ci` carries its bootstrap interval (ruled 2026-09-21, spec §0.1
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
    things about one number. None when no row's widths are ALL assistant-typed,
    where the clause does not print at all. A row with any `unattributed`
    width is not in the sum — see `SpreadRegister.unattributed_channel_ids`.
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
    sample size. There is deliberately no `residual` attribute: clamping ΣS to
    1 would make the refusal unreachable, and a field that does not exist
    cannot be printed by accident.

    THIS IS THE BRANCH THE FIXTURE TAKES AT BOTH COMMITTED PATH COUNTS (§0.1
    item 12). §4 claimed 10,000 paths resolve it; measured, its own figure
    there is 1.023 [0.969, 1.091], which includes 1 and refuses too. The RULE
    stands and §4's example claim was deleted — a rule that bends to make its
    own example work is not a rule.
    """

    first_order_sum: float
    first_order_sum_ci: Interval


Interaction = Union[ResolvedInteraction, RefusedInteraction]


@dataclass(frozen=True)
class SpreadRegister:
    """Where the decision margin's scatter comes from.

    WHICH ROW LEADS IS DECIDED HERE, ONCE, over the POINT estimates of EVERY
    row — resolved or not — and the text and the JSON both read it. The top
    row by first-order point estimate (`alone`, or `provisional_alone` on an
    unresolved row) is exactly one of:

      - `leading_channel_id`, when that row RESOLVED. Three sentences name it
        — §5 mechanism 3's gate, §7's "on your portfolio the two are 0.88 and
        41%", and the level register's closing "your portfolio is 88% of the
        spread" — and it is carried so that none of them has to branch on the
        `Shares` union to reach a point estimate;
      - `unresolved_top_channel_id`, when it did NOT. Then no channel leads:
        `leading_channel_id` is None, the superlative is not licensed and there
        is no figure to check first. The largest RESOLVED row is never promoted
        in its place — on examples/rent_vs_condo_vs_house.yaml the condo's
        costs carry a provisional 1.07 that did not resolve and the largest
        resolved share is the house's costs at 0.01, so promoting it named, as
        the table's leader and the figure to check first, a channel carrying a
        hundredth of the spread. The text said "no channel leads" while the
        JSON named that channel; the rule now has this one home.

    Never both; both None only on a register with no rows, which the assembler
    does not produce (a spread with nothing to show is `RefusedSpread`).

    `superlative_licensed` is §5 mechanism 3's gate: true only when a row leads
    and every width of it is user-stated or anchored, and only then may the
    block write "X decides the spread of this answer". `check_first` is the
    figure the ungated sentence names instead — the one number the ranking
    would move on — and None when no row leads. Both are carried rather than
    re-derived by the formatter so that flipping one `sources:` entry changes
    them, and a test can say so (T14).

    `unattributed_channel_ids` are the rows, in row order, at least one of
    whose widths no `sources:` entry claims. They are NOT "the assistant chose":
    an unattributed figure is one nobody's name is on, and reading that silence
    as the assistant's answer is the inference the source echo exists to
    refuse. So they are never inside `ResolvedInteraction`'s assistant-typed
    sum, and they are carried on the register rather than on the interaction
    because WHOSE figures sized the rows is a fact on both branches of §4 —
    it is the sum that is noise on the refused one, not the provenance. No
    default: "none unattributed" is a claim the producer states.
    """

    rows: Tuple[SpreadRow, ...]
    interaction: Interaction
    leading_channel_id: Optional[int]
    unresolved_top_channel_id: Optional[int]
    superlative_licensed: bool
    check_first: Optional[Width]
    unattributed_channel_ids: Tuple[int, ...]

    def __post_init__(self) -> None:
        _require_one_top("SpreadRegister", self.leading_channel_id,
                         self.unresolved_top_channel_id)
        if self.leading_channel_id is None and (
                self.superlative_licensed or self.check_first is not None):
            raise ValueError(
                "SpreadRegister licenses a superlative or names a figure to check "
                "first with no leading row: both are claims about the row that "
                "leads, and when the top row did not resolve no row leads")


# The spread register's OWN refusals, which suppress it and leave the level and
# reversal registers printing. §5's binding runs one way — the spread may not
# print without the level — so a refused spread beside a printed level is
# permitted, and is the honest shape (§0.1 item 7).
SPREAD_REFUSAL_CODES: Tuple[str, ...] = (
    "no_sign_variation",   # P(f > 0) == 1: every future agrees with the central case
)


@dataclass(frozen=True)
class RefusedSpread:
    """The spread register declining to print, in the spread register's slot.

    §8's "prints, but with no shares" state. A NAMED refusal rather than a
    `SpreadRegister` with `rows=()`, because empty rows beside printed level
    rows leave the reader — and the formatter — to infer why (§0.1 item 7).

    ON THE REASON, because the ruling's own wording will mislead whoever
    writes it: item 7 says "the shares are undefined", and that is false as
    arithmetic. With `Var(f) > 0` the centred Saltelli and Jansen indices are
    perfectly well defined when `f` never changes sign. What degenerates is
    the FLIP column, identically 0 for every channel, since no re-draw moves a
    future across a boundary no future is near. The honest sentence is that
    the block has nothing to apportion IN DECISION SPACE — not that the
    arithmetic failed. (`Var(f) == 0` is the genuinely undefined case; it is
    §8 refusal 5 and suppresses the whole block through
    `DecompositionRefusal`.)
    """

    code: str
    reason: str


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

    `paths` is this register's OWN sample (`m = min(N, LEVEL_PATHS)`, N the
    decomposition's path count): a paired mean needs far fewer paths than a
    variance ratio, so it is generally not the spread register's count.

    `futures_margin` and `prob_best_base` are `f(A[:m])`'s own mean and sign
    rate, computed FROM `A` because the freeze comparisons are paired against
    `A` and a borrowed baseline would unpair them. They STAY as the
    decomposition's own figures (§0.1 item 1) and are NOT
    `Decomposition.mean_margin` nor `verdict.prob_best`: the verdict comes from
    the LEGACY binding — one generator, the shipped stream — while `A` is
    spawn-keyed, so those are two estimates of one quantity from two named
    samples. Their difference is information about the estimator, not a second
    home for one truth. §2's bit-exact `P(f > 0) == verdict.prob_best` is a
    claim about the legacy binding only.

    THE GAP IS A SUBTRACTION, NEVER A STORED NUMBER (§0.1 item 2): §7's draft
    printed a gap that disagreed with the two figures beside it by $2,333, so
    it renders as `all_frozen_margin − futures_margin` and cannot disagree
    again. `accounted_for` is stored because summing it would mean reaching
    into `provisional_delta`; the gap needs no such reach.

    `all_frozen_margin` and the two deviation fields are the identity that
    makes this register a fact rather than a claim — but NOT the identity §3.4
    claimed. "BIT FOR BIT" IS FALSE OF THE MARGIN, and §3.4 asserted it in the
    same sentence as the figure that disproves it (§0.1 item 19): the deviation
    is 5.821e-11, exactly 1 ULP of the $476,086 house total and 16 ULP of the
    $31,349 margin, and it is STRUCTURAL — the simulators compound the value
    track year by year while `deterministic.py` takes `(1 + g) ** years`. The
    renter, whose frozen legs collapse to the same closed forms, IS exact to
    the bit. So the instrument is two things, and they are two fields:

      - `all_frozen_path_spread` — the max deviation ACROSS PATHS, exactly 0.0
        when the mask is right. This is what a missed draw site actually
        breaks, and it is the sharp half;
      - `all_frozen_deviation` — that one value against `verdict.margin_pv`,
        held to a ULP budget scaled to the totals subtracted, never to zero
        (`decomposition_math.identity_ulp_budget`, its one home). Past that
        budget the assembler refuses the WHOLE block as `identity_failed`, so
        a register that reaches a reader always held it.

    A mask that misses a draw site fails the first; so does a mask that reaches
    another channel's site (test T2). Chasing bit-exactness on the margin would
    mean changing how the deterministic side compounds, which is a different
    feature and a worse trade.

    `accounted_for` is the sum of ALL rows' shifts, the indistinguishable ones
    included, against the gap `all_frozen_margin − futures_margin`. It is
    carried rather than summed by the formatter precisely because summing it
    would mean reaching into `provisional_delta`.

    THE CLOSING'S CHANNEL IS DECIDED HERE, by the rule `SpreadRegister` uses:
    the top row by |point shift| over EVERY row, resolved or not, is exactly
    one of `leading_channel_id` (it resolved: the channel the closing sentence
    names as the largest shift) or `unresolved_top_channel_id` (it did not:
    the closing names it with its provisional figure and says it did not
    resolve). A smaller resolved row is never promoted as the largest — on
    examples/basic_config.yaml the house's costs resolve at +$252 while the
    condo's costs move the margin by +$390 ± $273 and take P(house cheapest)
    out of the tie band, and a closing that called the house's costs "the
    largest single shift" was false. WHICH sentence is chosen is
    `verdict.state`'s business, never the sign of anything (§7 rule 2): a
    formatter with one branch prints a disagreement explanation on an
    agreement.

    `paths` never exceeds `LEVEL_PATHS`: a larger run does not resolve a
    row here once the register is at that count, so a sentence telling the
    reader to raise the path count is true only below it.
    """

    rows: Tuple[LevelRow, ...]
    paths: int
    prob_best_base: float
    futures_margin: float
    all_frozen_margin: float
    all_frozen_path_spread: float
    all_frozen_deviation: float
    accounted_for: float
    leading_channel_id: Optional[int]
    unresolved_top_channel_id: Optional[int]

    def __post_init__(self) -> None:
        _require_one_top("LevelRegister", self.leading_channel_id,
                         self.unresolved_top_channel_id)


# ---------------------------------------------------------------------------
# The reversal register (spec §6)
# ---------------------------------------------------------------------------

# The verdict fields a boundary can be solved on. `runner_up` is here because
# §6's own measured results report a runner-up crossing (2.9549% on the
# fixture) that its enumerating sentence omits.
BOUNDARY_FIELDS: Tuple[str, ...] = ("best", "runner_up", "mc_best", "decisive")

# §3.5's three kinds. `stated_path`: stated in the config, whoever typed it,
# and never drawn (the renewal ladder) — its row carries numbers from §6, never
# a dash.
# `no_pv_reach`: draws exist and reach no present value (the income block).
# `dead_draw`: a CHANNEL that draws every year and reaches no cash flow (the
# real-mode inflation trap), detected from the spec and costing no evaluation.
STRUCTURAL_ZERO_KINDS: Tuple[str, ...] = ("stated_path", "no_pv_reach", "dead_draw")


# The sides of a crossing on which the scan can see the verdict change AGAIN.
FURTHER_CHANGE_SIDES: Tuple[str, ...] = ("above", "below")


def _require_side(kind: str, verdict_field: str, further_changes: object) -> None:
    """`further_changes` is None or one of `FURTHER_CHANGE_SIDES` — the side of
    the crossing, away from the region where the verdict says what this run
    says, on which the searched range holds further changes this row does not
    report. Anything else would print as a side the reader cannot place."""
    if further_changes is not None and further_changes not in FURTHER_CHANGE_SIDES:
        raise ValueError(
            f"{kind}.further_changes for {verdict_field!r} is {further_changes!r}: "
            f"it is None or one of {FURTHER_CHANGE_SIDES}, the side of the crossing "
            f"on which the searched range changes again")


def _require_words(kind: str, verdict_field: str, was: object, becomes: object) -> None:
    """Every boundary's `was` and `becomes` are the WORDS a reader is shown for
    the verdict on each side of it — an option's name, or a decisiveness state
    such as "decisive for house" — never a raw value. Checked when the boundary
    is built, because the defect this refuses was a coercion upstream of it:
    `decisive` travelled as a bool, `str()` turned it into "True", and the
    block printed "changes from True to False" twice on one axis, once for a
    crossing that was a change from not decisive to decisive for the OTHER
    option (spec §6; a reading of `--sweep` either side is the check).
    """
    for name, value in (("was", was), ("becomes", becomes)):
        if not isinstance(value, str) or not value.strip():
            raise TypeError(
                f"{kind}.{name} for {verdict_field!r} is {value!r} "
                f"({type(value).__name__}), not words: a boundary states what the "
                f"verdict reads on each side of it as text a reader can be shown")


@dataclass(frozen=True)
class AxisReference:
    """A cited point on a reversal axis, to place the solved rate against.

    `note` carries what the citation does NOT license — a posted rate is a list
    price bracketing a guess from above; on a renewal axis, and only there, it
    is also never a ceiling on a renewal years from now. The renewal clause is
    keyed on the AXIS: a `mortgage_rate` row moves a rate the run prices from
    year 0, and on a run with no renewal the clause named a renewal the run
    does not have.
    """

    label: str
    value: float
    formatted: str
    anchor: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class SolvedBoundary:
    """A crossing solved on the DETERMINISTIC verdict — `best`, `runner_up`.

    A property of the config, not of the sample: measured identical to
    SEVEN DIGITS at seeds 42, 7, 1234, 99 and 2026 (§0.1 item 24). It carries
    no path count and no seed because its value depends on neither, and it
    prints at four decimals (`1.6052%`) for the same reason.

    `confirming_probabilities` is CORROBORATION and never the value's basis:
    one full re-simulation at the solved value, which the free curve has to
    agree with or the boundary is withheld as a `RefusedBoundary` (§6, test
    T11). It is an EMPTY TUPLE when the run has no futures —
    `break_even.reversal_register` called with `mc=None`, or on a single-path
    run — and the boundary is solved there all the same. The field
    has NO DEFAULT: "nothing corroborated this" is a claim its producer states
    in the call, never a value the type supplies to a caller that forgot to
    say. §0.1 item 25 rules that branch unreached from `--decompose` (§8
    refusal 2 refuses the whole block on a path-free run before any register
    is built), so it is the library shape.

    `was` and `becomes` READ THE KEY UPWARD, on every boundary of every kind:
    `was` is what the verdict field says just BELOW `value`, `becomes` what it
    says just above — whichever side of the crossing this run's own value sits
    on. So `--sweep` at a point either side prints `was` below and `becomes`
    above. Both are words (`_require_words`), never a raw value.

    `further_changes` — on every boundary kind — says whether the searched
    range holds MORE changes of this field beyond the crossing, on the side
    away from the region where the verdict says what this run says, that no
    row reports: "above", "below", or None when there are none. A row reports
    the NEAREST edge of that region (§6); on examples/mortgage_house_vs_rent.
    yaml `decisive` changes from decisive for house to not decisive at 6.74%
    and again, into decisive for rent, near 6.84%, and a row printing only the
    first let a reader take "not decisive" to hold to the top of the bracket.
    It has NO DEFAULT: "nothing further" is a claim the producer states.
    """

    verdict_field: str
    value: float
    was: str
    becomes: str
    further_changes: Optional[str]
    confirming_probabilities: Tuple[Tuple[str, float], ...]

    def __post_init__(self) -> None:
        _require_words("SolvedBoundary", self.verdict_field, self.was, self.becomes)
        _require_side("SolvedBoundary", self.verdict_field, self.further_changes)


@dataclass(frozen=True)
class SampledBoundary:
    """A crossing BISECTED on the Monte Carlo curve — `mc_best`, `decisive`.

    A property of the sample as much as of the config: the same `mc_best`
    boundary moved 2.698% → 2.805% across five seeds and 2.6923% → 2.8104%
    across `num_sims` 500–4000, so it carries `curve_paths` and `seed`, which
    are what its value depends on, and prints at two decimals (`2.72%`) with a
    clause naming both.

    IT SHARES NO BASE CLASS AND NO FIELD SET WITH `SolvedBoundary` (§0.1 item
    24). One type for both was this feature's cardinal error committed by its
    own contract: nothing downstream could tell a property of the config from a
    property of the sample, and a reader met "your verdict flips at 2.716%" in
    the same typography as an exact figure. `curve_paths` is deliberately not
    `paths`, which would collide with `LevelRegister.paths` and
    `Decomposition.paths`.

    THIS IS A DIFFERENT AXIS FROM `ExactReversal` vs `EstimatedReversal`. That
    gate splits ACROSS KEYS on whether the free-curve licence holds; this
    splits WITHIN ONE KEY, one level below where the gate operates. A licensed
    key carries both kinds at once.

    `was` / `becomes` read the key upward, and `further_changes` says what
    it says, as on `SolvedBoundary`. For
    `decisive` they are one of "decisive for <option>" or "not decisive" —
    three states on a two-option axis, never a boolean: a boolean merges
    decisive for one option with decisive for the other, and a crossing from
    not decisive into the OTHER option's decisiveness then prints as
    "True to False" (`break_even.decisive_state` is the one home of the words).
    """

    verdict_field: str
    value: float
    was: str
    becomes: str
    further_changes: Optional[str]
    curve_probabilities: Tuple[Tuple[str, float], ...]
    confirming_probabilities: Tuple[Tuple[str, float], ...]
    curve_paths: int
    seed: int

    def __post_init__(self) -> None:
        _require_words("SampledBoundary", self.verdict_field, self.was, self.becomes)
        _require_side("SampledBoundary", self.verdict_field, self.further_changes)


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

    `probe_paths` is never zero and `max_path_deviation_over_sd` never reads
    zero-because-unmeasured: the gate's licence has a standard deviation for a
    denominator, so a row that reaches this tuple was probed on paths even when
    the caller's own run priced no futures (`break_even.reversal_register` says
    what that costs). A field reading zero because nobody measured it is worse
    than no field — it is an all-clear nothing earned.

    `stated_source` is WHOSE figure the stated value is — "user", "anchor",
    "assistant" or "unattributed" — read from `sources.SourceEcho.classify`,
    the classifier the read-back's source echo prints, and never from a second
    one. The row's boundaries are solved on the config's figures whoever typed
    them, so a sentence about the user's OWN figures is true only when this
    says "user": the fixture's renewal ladder is assistant-typed, and the
    read-back says so in the same run. It has NO DEFAULT, for the reason
    `SolvedBoundary.confirming_probabilities` has none: "nobody's in
    particular" is a claim the producer states, never one the type supplies.
    """

    key: str
    option: str
    stated_formatted: str
    stated_source: str
    bracket_low: float
    bracket_high: float
    bracket_source: str
    probe_paths: int
    max_path_deviation_over_sd: float
    # Both of §6's boundary kinds land in this ONE tuple, as two TYPES rather
    # than one type with a flag: the exactness gate splits ROWS by key, and
    # these are two kinds WITHIN one key — `best` is a property of the config
    # and `mc_best` a property of this run's sample. No alias unions them under
    # a single name, because a name reads as a shared base class and there is
    # none.
    boundaries: Tuple[Union[SolvedBoundary, SampledBoundary], ...]
    refused_boundaries: Tuple[RefusedBoundary, ...]
    references: Tuple[AxisReference, ...]
    path_note: Optional[str] = None


@dataclass(frozen=True)
class EstimatedBoundary:
    """A verdict change LOCATED by re-simulation, inside an interval.

    Deliberately neither of §6's two boundary kinds: there is no confirming
    re-simulation to compare against, because re-simulation is how the value
    was found, and no curve was bisected. The interval is the figure; the point
    is where inside it the estimate landed. `was`, `becomes` and
    `further_changes` read as on `SolvedBoundary`.
    """

    verdict_field: str
    value: float
    value_ci: Interval
    was: str
    becomes: str
    further_changes: Optional[str]
    resimulation_paths: int

    def __post_init__(self) -> None:
        _require_words("EstimatedBoundary", self.verdict_field, self.was, self.becomes)
        _require_side("EstimatedBoundary", self.verdict_field, self.further_changes)


@dataclass(frozen=True)
class EstimatedReversal:
    """A stated input whose reversal distance the engine ESTIMATED.

    Shares no base class and no field set with `ExactReversal` (spec §0's
    ruling): the split is a property of the model, not a ranking, and two types
    that could be concatenated into one ordered table would reintroduce the
    ranking the operator refused. `max_path_deviation_over_sd` is here too, and
    it is the figure that FAILED the exactness gate — the reason this row is in
    this tuple rather than the other one. It is NaN when the gate refused
    because a present value it compares was not a finite number: not a number
    is what was measured. `stated_source` is `ExactReversal.stated_source`.

    SLICE 1 ESTIMATES NOTHING, and that is not an oversight: §6 REFUSES every
    key that fails the exactness gate rather than estimating it, and §14 defers
    the keys that would need estimating. Such a key still lands here — with no
    boundary, and every field refused under the gate's own reason — so that it
    is named rather than absent. The type exists because the operator's ruling
    is that the rows GROUP by exactness, and a group that appears later must
    not arrive as a flag bolted onto the exact kind.
    """

    key: str
    option: str
    stated_formatted: str
    stated_source: str
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

    `structural_zeros` lives HERE, and §7's fourth section ("NOT DRAWN IN THIS
    RUN") renders from it, because §3.5's renewal row carries a number that
    comes from §6 and the two render together. The stated `spread`/`level`/
    `reversal` triple had no home for that section; this placement is ruled,
    not assumed (§0.1 item 5).
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
    "too_few_futures", # futures exist, fewer than the block can put an interval on
    "single_option",   # fewer than two options priced: no margin exists
    "one_channel",     # k_live == 1: the table would read 1.00 and be a tautology
    "no_spread",       # Var(f) == 0: every index is 0/0
    "budget",          # the work gate: names the figure and the two ways out
    "freeze_leak",     # all channels frozen and the paths still differ: a draw escaped
    "identity_failed", # all channels frozen, the paths agree, and their margin is not
                       # the central case's within `identity_ulp_budget`
)


@dataclass(frozen=True)
class DecompositionRefusal:
    """The WHOLE block declining to print, with its own reason (§8).

    A refusal is not silence and not an empty block: it says which condition
    fired. `channel_id` is set by `one_channel`, which NAMES the channel
    carrying all of the run's spread and prints no numbers. Decided by the
    ASSEMBLER, which is the thing that sees the data, and merely rendered by
    the formatter (§0.1 item 17).

    For the case where only the SPREAD register refuses, see `RefusedSpread` —
    that one leaves the level and reversal registers printing.
    """

    code: str
    reason: str
    channel_id: Optional[int] = None


@dataclass(frozen=True)
class Decomposition:
    """The whole block: three registers, never fewer.

    `spread`, `level` and `reversal` carry no defaults, so there is no
    "spread-only" `Decomposition` to construct (§5 mechanism 5). That is the
    type's half of the binding; the formatter completes it (§7 rule 1). The binding
    runs ONE WAY, which is why `spread` may be a `RefusedSpread`: a refused
    spread beside a printed level is permitted and honest, a printed spread
    beside no level is not (§0.1 item 7).

    `verdict` is the run's own `models.Verdict` object, held rather than copied:
    every probability and every state in this block comes back from
    `models.compute_verdict` and none is recomputed here (§1). The header's
    margin, its fraction of the best option's PV and the majority's probability
    are read off it.

    `mean_margin` and `sd_margin` are E[f] and sd(f) on the spread register's
    own A matrix at `paths`. `sd_margin` against `verdict.margin_pv` is the
    ratio that leads the block: a share of a spread means nothing until the
    reader knows how wide that spread is against the answer.

    `live_channel_ids` are the channels that REACH A CASH FLOW on this spec —
    NOT the channels that draw (§0.1 item 22, correcting §3.6). With every
    volatility zeroed, three streams still move: the cost shocks are drawn and
    THEN multiplied by a zero vol rather than skipped, and all three options'
    event-cost draws are unconditional, so any priced option with a cost line
    consumes draws in its channel while moving no number. A channel that draws
    is not a channel that moves a number, so this count may NOT be taken from
    generator state — the mirror image of §3.2, where a leaked draw is
    invisible in the output and only generator state can catch it. The same
    instrument answers one question and lies about the other. The assembler
    computes it from the spec, beside `_world_draws`.
    """

    paths: int
    live_channel_ids: Tuple[int, ...]
    verdict: "Verdict"
    mean_margin: float
    sd_margin: float
    spread: Union[SpreadRegister, RefusedSpread]
    level: LevelRegister
    reversal: ReversalRegister


# What the entry point returns: the block, a named refusal, or None for
# silence — the flag not passed, which is every run shipped today.
DecompositionOutcome = Optional[Union[Decomposition, DecompositionRefusal]]
