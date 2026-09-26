"""Which risk decides it — the three registers, as TYPES ONLY.

Design record: `docs/specs/2026-09-22-which-risk-decides-it.md`. What every
field means, when it refuses and which figures move with the sample is written
once, in `docs/reference/API_CONTRACT.md` § The `decomposition` block, and is
checked against runs there; this module does not restate it. It holds the
seven-channel table and the shape of every object the assembler
(`decomposition_run`), the estimators (`decomposition_math`), the reversal
solver (`break_even`) and the formatter (`decomposition_text`) hand each other.
It computes NOTHING: no statistic, no draw, no sentence.

What the SHAPES are for, which is this module's own business:

  - THE BINDING. The spread register may never be emitted without the level
    register beside it, because the spread's top row can be a channel whose
    shift the same run cannot tell from zero (the flagship fixture's case,
    pinned in `tests/test_decomposition_run.py::TestThePublishedFigures`).
    `Decomposition` requires all three registers with no default on any, so
    no spread-only result can be constructed; the formatter completes the
    guard (`decomposition_text`), and this module cannot reach it.
  - TWO STATES THAT ARE NOT NONE AND NOT ZERO. A figure that did not resolve
    is its own type carrying its own estimate under a `provisional_*` name that
    the resolved type does not have, and the two share no base: a reader of
    `row.shares.alone` on an unresolved row raises rather than printing noise
    as a finding. `ResolvedInteraction` / `RefusedInteraction` use the same
    device, so a residual cannot be printed on the branch that refused it.
  - EXACT AND ESTIMATED REVERSALS ARE NOT ONE KIND WITH A FLAG, and neither
    are a solved crossing and a sampled one: no shared base class and no shared
    field set, so they cannot be concatenated into one ordered table.
  - NO DEFAULT on a field whose absence would be a claim ("nothing
    corroborated this", "nobody's figure in particular"): the producer states
    it in the call.
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

    Grouping over draw sites keeps Sobol's independence assumption true: the
    engine composes every correlation from independent primitives, and grouping
    over config keys would import the dependence back. `sizing_keys` are the
    dotted config keys that SIZE the channel, looked up in `sources.SourceEcho`
    for the row's provenance; a key may size more than one channel.
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
        # The correlations are sizing keys, not decoration: rho squared of each
        # correlated shock's variance is attributed here, so the cell that
        # omits them is itself a wrong answer (§4). The option vols those keys
        # PULL FROM depend on which rho is non-zero and so cannot live in a
        # static table: they reach the row as extra `Width` entries from the
        # assembler, which reads the spec.
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


# The most paths the LEVEL register prices (§9): a paired mean needs far fewer
# paths than a variance ratio. Held here, beside the types, because two pieces
# need it: the assembler sizes the register with it, and the formatter's route
# clause must know it to say truthfully whether a larger run would resolve a
# level row.
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
    """A `{low, high}` interval, never clamped into [0, 1].

    What produces it, per field, is `docs/reference/API_CONTRACT.md`'s. Its
    bounds depend on the bootstrap's salt and resample count while the point
    estimates do not, so nobody tunes the salt to match a figure in the design
    record, and tests assert inequalities with margin rather than bounds.
    """

    low: float
    high: float


def _require_one_top(kind: str, leading: Optional[int],
                     unresolved_top: Optional[int]) -> None:
    """A register's top row is EITHER the leader (it resolved) OR the unresolved
    top (it did not) — never both. Both set would let the text name one channel
    as leading while the JSON names another as the largest.
    """
    if leading is not None and unresolved_top is not None:
        raise ValueError(
            f"{kind} names channel {leading} as leading AND channel {unresolved_top} "
            f"as an unresolved top row: the top row by point estimate either "
            f"resolved or did not, so exactly one of the two can be set")


@dataclass(frozen=True)
class Width:
    """One input that SIZES a channel, with whose figure it is.

    `source` is whatever `sources.SourceEcho.classify` returns for `key` — read
    from there, never inferred from the key's name and never restated as a
    vocabulary here. `formatted` is None when the key's value is not a figure.
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
    """A channel's two Sobol shares, both of which resolved.

    The estimators are `decomposition_math.first_order_indices` and
    `total_order_indices`, whose docstrings carry their formulas and why the
    first-order numerator is centred. No attribute here is shared by name with
    `UnresolvedShares`.
    """

    alone: float
    alone_ci: Interval
    with_interaction: float
    with_interaction_ci: Interval


@dataclass(frozen=True)
class UnresolvedShares:
    """The same two shares, not resolved on this sample.

    The estimates are KEPT, under `provisional_*` names no resolved type
    carries, so no reader can take a resolved figure off an unresolved row. ONE
    ROW STATE FROM TWO FIGURE VERDICTS: a row is unresolved if EITHER figure is,
    because the alternative prints one resolved figure beside one that is noise
    and leaves the reader to notice.
    """

    provisional_alone: float
    provisional_alone_ci: Interval
    provisional_with_interaction: float
    provisional_with_interaction_ci: Interval


Shares = Union[ResolvedShares, UnresolvedShares]


@dataclass(frozen=True)
class SpreadRow:
    """One channel's row of the spread register.

    `flip` sits outside `shares` because it survives an unresolved row, and
    `flip_ci` travels with it because a bare point estimate among neighbours that
    all carry an interval reads as the most certain figure in the table.
    `interaction_gap` and its interval are the row's own measurement of what the
    channel does jointly with the others. What each figure is:
    `docs/reference/API_CONTRACT.md`.
    """

    channel_id: int
    shares: Shares
    flip: float
    flip_ci: Interval
    widths: Tuple[Width, ...]
    interaction_gap: float
    interaction_gap_ci: Interval


@dataclass(frozen=True)
class ResolvedInteraction:
    """The first-order sum resolved below one, so the residual exists.

    `residual` exists only on this branch, and so does the assistant-typed share
    sum, because on the refused branch that sum is noise: a block that refuses a
    figure as a residual and then prints it as a provenance finding tells the
    reader two things about one number.
    """

    first_order_sum: float
    first_order_sum_ci: Interval
    residual: float
    residual_ci: Interval
    unstated_first_order_sum: Optional[float] = None
    unstated_first_order_sum_ci: Optional[Interval] = None


@dataclass(frozen=True)
class RefusedInteraction:
    """The first-order sum did not resolve below one, so there is no residual.

    There is deliberately no `residual` attribute: clamping the sum to one would
    make the refusal unreachable, and a field that does not exist cannot be
    printed by accident. The flagship fixture takes this branch; the one config
    in this repo that takes the other is `tests/fixtures/min_interaction.yaml`.
    """

    first_order_sum: float
    first_order_sum_ci: Interval


Interaction = Union[ResolvedInteraction, RefusedInteraction]


@dataclass(frozen=True)
class SpreadRegister:
    """Where the decision margin's scatter comes from.

    WHICH ROW LEADS IS DECIDED ONCE, by the assembler's `_top_row`, and carried
    here as exactly one of `leading_channel_id` or `unresolved_top_channel_id`;
    the text and the JSON both read these fields, so neither re-derives the rule
    (the rule itself: `docs/reference/API_CONTRACT.md`). The same goes for
    `superlative_licensed`, `check_first`, `unattributed_channel_ids` and
    `interaction_channel_ids`: carried rather than re-derived by a renderer, so
    flipping one `sources:` entry changes them and a test can say so. None has a
    default.
    """

    rows: Tuple[SpreadRow, ...]
    interaction: Interaction
    leading_channel_id: Optional[int]
    unresolved_top_channel_id: Optional[int]
    superlative_licensed: bool
    check_first: Tuple[Width, ...]
    unattributed_channel_ids: Tuple[int, ...]
    interaction_channel_ids: Tuple[int, ...]

    def __post_init__(self) -> None:
        _require_one_top("SpreadRegister", self.leading_channel_id,
                         self.unresolved_top_channel_id)
        if self.leading_channel_id is None and (
                self.superlative_licensed or self.check_first):
            raise ValueError(
                "SpreadRegister licenses a superlative or names a figure to check "
                "first with no leading row: both are claims about the row that "
                "leads, and when the top row did not resolve no row leads")


# The spread register's OWN refusals, which suppress it and leave the level and
# reversal registers printing. §5's binding runs one way — the spread may not
# print without the level — so a refused spread beside a printed level is
# permitted, and is the honest shape (§0.1 item 7).
SPREAD_REFUSAL_CODES: Tuple[str, ...] = (
    "no_sign_variation",   # P(f > 0) is 0 or 1: every future on one side of the line
)


@dataclass(frozen=True)
class RefusedSpread:
    """The spread register declining to print, in the spread register's slot.

    A NAMED refusal rather than a `SpreadRegister` with no rows, because empty
    rows beside printed level rows leave the reader, and the formatter, to infer
    why. On the reason, because the ruling's wording misleads whoever writes it:
    the shares are well defined when the margin never changes sign; what
    degenerates is the FLIP column, identically zero since no re-draw moves a
    future across a line no future is near. So the sentence says there is nothing
    to apportion IN DECISION SPACE, not that the arithmetic failed.
    """

    code: str
    reason: str


# ---------------------------------------------------------------------------
# The level register (spec §3.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedLevel:
    """A channel whose freeze moves the expected margin by more than the
    resolution multiple of its standard error — a cost the central case leaves
    out, read as a cost and never as a risk.
    """

    delta: float
    se: float
    prob_best_frozen: float


@dataclass(frozen=True)
class IndistinguishableLevel:
    """A channel whose freeze moves the margin by no more than the resolution
    multiple of its standard error: a row a reader must SEE rather than an
    absence, since a channel can carry most of the scatter and move the answer
    by nothing this run can tell from zero. `provisional_delta` shares no name
    with `ResolvedLevel.delta`, so no renderer can print it in the resolved
    column.
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

    `futures_margin` and `prob_best_base` are computed on the register's OWN
    sample, the first `paths` of the block's `A` matrix, because the freeze
    comparisons are paired against it and a borrowed baseline would unpair them;
    they are not the verdict's figures, which come from another sample. The gap
    is not stored, because it is the subtraction of two fields that are.

    THE IDENTITY IS TWO CLAIMS, SO IT IS TWO FIELDS. With every channel frozen,
    the paths must agree with each other EXACTLY (`all_frozen_path_spread`, what
    a missed draw site breaks) and agree with the central case to within a
    units-in-the-last-place budget (`all_frozen_deviation`), never exactly: the
    simulators compound year by year while the central case takes a closed form.
    The assembler refuses the whole block when either fails, so a register that
    reaches a reader held both. The measured instance is pinned in
    `tests/test_decomposition_run.py::TestThePublishedFigures`.

    THE CLOSING'S CHANNEL IS DECIDED ONCE, by the rule `SpreadRegister` uses
    (`leading_channel_id` / `unresolved_top_channel_id`); WHICH sentence is chosen
    is `verdict.state`'s business, never the sign of anything.
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
# §6's own measured results report a runner-up crossing that its enumerating
# sentence omits.
BOUNDARY_FIELDS: Tuple[str, ...] = ("best", "runner_up", "mc_best", "decisive")

# §3.5's three kinds, and whether each is drawn — two of the three are, so no
# heading over all of them may say "not drawn". `stated_path`: stated in the
# config, whoever typed it, and touched by no draw (a renewal ladder, a contract
# rate). `no_pv_reach`: drawn, and reaching no option's present value (the
# income block). `dead_draw`: a CHANNEL that is drawn and reaches no cash flow,
# detected from the spec and costing no evaluation.
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
    """A cited point on a reversal axis, to place a solved rate against, already
    expressed on that axis.

    `note` carries what the citation does NOT license, and how it was converted
    when the axis is quoted another way than the published figure.
    """

    label: str
    value: float
    formatted: str
    anchor: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class SolvedBoundary:
    """A crossing solved on the DETERMINISTIC verdict — `best`, `runner_up`.

    A property of the config, not of the sample, so it carries no path count and
    no seed (seed-invariance is pinned in `tests/test_reversal_register.py`).
    `confirming_probabilities` is CORROBORATION and never the value's basis, and
    an EMPTY TUPLE when the run has no futures; it has no default, because
    "nothing corroborated this" is a claim the producer states.
    `was`/`becomes` and `further_changes` read as
    `docs/reference/API_CONTRACT.md` says; both are validated here because a
    coercion upstream once turned a decisiveness into "True".
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

    A property of the sample as much as of the config, so it carries
    `curve_paths` and `seed`, which are what its value depends on. IT SHARES NO
    BASE CLASS AND NO FIELD SET WITH `SolvedBoundary`: one type for both let a
    reader meet a sampled crossing in the typography of an exact one.
    `curve_paths` is deliberately not `paths`, which would collide with
    `LevelRegister.paths` and `Decomposition.paths`. This is a different axis
    from `ExactReversal` vs `EstimatedReversal`, which splits across KEYS; a
    licensed key carries both boundary kinds.
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
    """A boundary field on which nothing is printed, with the reason — recorded
    rather than dropped, because an absent row reads as "nothing here".
    """

    verdict_field: str
    reason: str


@dataclass(frozen=True)
class ExactReversal:
    """A stated input whose reversal distance the engine computed EXACTLY, because
    the exactness gate licensed its free curve.

    `path_note` is `sweep.flattened_path_note`'s sentence whenever the config
    states the key as a path, so the row never claims the user stated a flat
    rate. `bracket_source` exists because a bracket that turns an honest refusal
    into an answer must show whose width it is. `probe_paths` is never zero and
    `max_path_deviation_over_sd` never reads zero-because-unmeasured: an all-clear
    nothing earned is worse than no field. `stated_source` has no default for the
    same reason `SolvedBoundary.confirming_probabilities` has none.
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
    """A verdict change LOCATED by re-simulation, inside an interval — neither of the
    two solved kinds: re-simulation is how the value was found, so there is
    nothing to confirm it against.
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
    """A stated input whose reversal distance the engine did not compute exactly.

    Shares no base class and no field set with `ExactReversal`: the split is a
    property of the model, never a ranking. SLICE ONE ESTIMATES NOTHING: a key
    the gate refuses lands here with no boundary and every field refused under
    the gate's own reason, so that it is named rather than absent, and a group
    that appears later does not arrive as a flag bolted onto the exact kind.
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
    measured zero: a reader who sees a dash concludes the thing was weighed and
    found irrelevant. `reversal_key` joins a stated path to the `ExactReversal`
    carrying its crossings; `channel_id` is set only for a `dead_draw`, the one
    kind that is a channel.
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

    The two row kinds are separate tuples, never one tuple with a flag.
    `structural_zeros` lives here because a stated path's row carries numbers
    from this register and the two render together. `no_distance_reason` is the
    producer's sentence for a register with no row: it knows what it searched
    and a renderer does not, and an empty register with no sentence reads as a
    finding that nothing would reverse the verdict.
    """

    exact: Tuple[ExactReversal, ...]
    estimated: Tuple[EstimatedReversal, ...]
    structural_zeros: Tuple[StructuralZero, ...]
    no_distance_reason: Optional[str]

    def __post_init__(self) -> None:
        # Exactly when no row carries a distance, the register says why — the
        # producer knows which keys it searched and the renderer does not.
        empty = not (self.exact or self.estimated)
        if empty != (self.no_distance_reason is not None):
            raise ValueError(
                "ReversalRegister.no_distance_reason is set exactly when neither "
                "`exact` nor `estimated` carries a row: an empty register says what "
                "was searched, and a register with rows has nothing to explain")


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------

# The refusals that suppress the whole block. When each fires is the refusal
# table in docs/reference/API_CONTRACT.md; the per-boundary refusal is
# `RefusedBoundary` and suppresses nothing. Silence — the flag not passed — is
# `None`, not a refusal.
REFUSAL_CODES: Tuple[str, ...] = (
    "no_futures",
    "too_few_futures",
    "single_option",
    "one_channel",
    "no_spread",
    "budget",
    "freeze_leak",
    "identity_failed",
)


@dataclass(frozen=True)
class DecompositionRefusal:
    """The WHOLE block declining to print, with its own reason — decided by the
    assembler, which sees the data, and merely rendered by the formatter. For
    the case where only the spread register refuses, see `RefusedSpread`.
    """

    code: str
    reason: str
    channel_id: Optional[int] = None


@dataclass(frozen=True)
class Decomposition:
    """The whole block: three registers, never fewer.

    `spread`, `level` and `reversal` carry no defaults, so there is no
    spread-only `Decomposition` to construct; the binding runs ONE WAY, which is
    why `spread` may be a `RefusedSpread`. `verdict` is the run's own
    `models.Verdict`, held rather than copied: every probability and state in the
    block comes back from `models.compute_verdict`. `max_paths` is carried so the
    formatter's route clause can say truthfully whether a larger run exists.
    `live_channel_ids` are the channels that REACH A CASH FLOW, which is not the
    same as the channels that draw — a count that must not be taken from
    generator state.
    """

    paths: int
    max_paths: int
    live_channel_ids: Tuple[int, ...]
    verdict: "Verdict"
    mean_margin: float
    sd_margin: float
    spread: Union[SpreadRegister, RefusedSpread]
    level: LevelRegister
    reversal: ReversalRegister

    def __post_init__(self) -> None:
        if not 0 < self.paths <= self.max_paths:
            raise ValueError(
                f"Decomposition prices {self.paths} paths against a largest affordable "
                f"count of {self.max_paths}: the budget gate refuses any count above it, "
                f"so a block past it is a producer defect")


# What the entry point returns: the block, a named refusal, or None for
# silence — the flag not passed, which is every run shipped today.
DecompositionOutcome = Optional[Union[Decomposition, DecompositionRefusal]]
