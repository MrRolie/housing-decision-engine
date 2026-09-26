"""Which risk decides it — the three registers, as TYPES ONLY.

Design record: `docs/specs/2026-09-22-which-risk-decides-it.md`. What every
field means, when it refuses and which figures move with the sample is written
once, in `docs/reference/API_CONTRACT.md` § The `decomposition` block, and is
checked against runs there. Every class docstring below is that pointer and
nothing else (`POINTER`), and `tests/test_decomposition_contract.py` fails on a
class docstring that says more. This module holds the seven-channel table and
the shape of every object the assembler (`decomposition_run`), the estimators
(`decomposition_math`), the reversal solver (`break_even`) and the formatter
(`decomposition_text`) hand each other. It computes NOTHING: no statistic, no
draw, no sentence.

What the SHAPES are for, which is this module's own business:

  - THE BINDING. `Decomposition` requires all three registers with no default
    on any, so no spread-only result can be constructed; the formatter
    completes the guard (`decomposition_text`), and this module cannot reach
    it.
  - TWO STATES THAT ARE NOT NONE AND NOT ZERO. A figure that did not resolve
    is its own type, carrying its estimate under a `provisional_*` name the
    resolved type does not have, and the two share no base: reading a resolved
    name off an unresolved row raises rather than printing noise as a finding.
    `ResolvedInteraction` / `RefusedInteraction` use the same device, and the
    refused type has no residual attribute at all.
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


# Every class docstring in this module is this pointer and nothing more: a type
# that restated what its fields mean would be a second home for the contract,
# right the day it was written and wrong after the next change.
POINTER = "Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."


# ---------------------------------------------------------------------------
# The channel partition (spec §3.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Channel:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    # naming nothing a household can act on. Split, the two are two rows in
    # each register, each with its own figures.
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


# Income's stream id, OUTSIDE the seven (§0.1 item 21). A pay drop with a timing
# or a size volatility draws from it, and those draws feed the affordability
# report, so it needs a generator of its own, never shared with a channel. It
# is refused by name in `freeze`, and a hand-built binding missing an id the
# run reaches RAISES naming the id rather than falling back quietly. It is
# deliberately NOT in `CHANNELS`: that tuple is the decomposition's partition,
# not the stream roster, and `channel(INCOME_STREAM_ID)` therefore raises.
INCOME_STREAM_ID: int = 7

# The words the block names the income stream by, where it prints a row for it.
INCOME_STREAM_LABEL: str = "your pay drops"


# The most paths the LEVEL register prices (§9): a paired mean needs far fewer
# paths than a variance ratio. Held here, beside the types, because the
# assembler sizes the register with it and the budget gate prices it.
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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    alone: float
    alone_ci: Interval
    with_interaction: float
    with_interaction_ci: Interval


@dataclass(frozen=True)
class UnresolvedShares:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    provisional_alone: float
    provisional_alone_ci: Interval
    provisional_with_interaction: float
    provisional_with_interaction_ci: Interval


Shares = Union[ResolvedShares, UnresolvedShares]


@dataclass(frozen=True)
class SpreadRow:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    channel_id: int
    shares: Shares
    flip: float
    flip_ci: Interval
    widths: Tuple[Width, ...]
    interaction_gap: float
    interaction_gap_ci: Interval


@dataclass(frozen=True)
class ResolvedInteraction:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    first_order_sum: float
    first_order_sum_ci: Interval
    residual: float
    residual_ci: Interval


@dataclass(frozen=True)
class RefusedInteraction:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    first_order_sum: float
    first_order_sum_ci: Interval


Interaction = Union[ResolvedInteraction, RefusedInteraction]


@dataclass(frozen=True)
class SpreadRegister:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    rows: Tuple[SpreadRow, ...]
    interaction: Interaction
    leading_channel_id: Optional[int]
    unresolved_top_channel_id: Optional[int]
    interaction_channel_ids: Tuple[int, ...]

    def __post_init__(self) -> None:
        _require_one_top("SpreadRegister", self.leading_channel_id,
                         self.unresolved_top_channel_id)


# The spread register's OWN refusals, which suppress it and leave the level and
# reversal registers printing. §5's binding runs one way — the spread may not
# print without the level — so a refused spread beside a printed level is
# permitted (§0.1 item 7).
SPREAD_REFUSAL_CODES: Tuple[str, ...] = (
    "no_sign_variation",
)


@dataclass(frozen=True)
class RefusedSpread:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    code: str
    reason: str


# ---------------------------------------------------------------------------
# The level register (spec §3.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedLevel:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    delta: float
    se: float
    prob_best_frozen: float


@dataclass(frozen=True)
class IndistinguishableLevel:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    provisional_delta: float
    se: float
    prob_best_frozen: float


Level = Union[ResolvedLevel, IndistinguishableLevel]


@dataclass(frozen=True)
class LevelRow:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    channel_id: int
    level: Level


@dataclass(frozen=True)
class LevelRegister:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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

# The two kinds of row with no place in the spread or the level (§0.1 items 39
# and 40): one decided by the model's structure, one measured on the block's
# own futures. What each kind means is the contract's.
STRUCTURAL_ZERO_KINDS: Tuple[str, ...] = ("stated_path", "dead_draw")


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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    label: str
    value: float
    formatted: str
    anchor: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class SolvedBoundary:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    verdict_field: str
    reason: str


@dataclass(frozen=True)
class ExactReversal:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    kind: str
    label: str
    keys: Tuple[str, ...]
    channel_id: Optional[int] = None
    reversal_key: Optional[str] = None
    measured_paths: Optional[int] = None
    move_threshold: Optional[float] = None

    def __post_init__(self) -> None:
        # Each kind carries exactly the fields that say what it rests on: a
        # structural row names the exact row beside it and was measured on no
        # futures; a measured row names its stream, how many futures it was
        # measured on and the threshold it was held to.
        if self.kind not in STRUCTURAL_ZERO_KINDS:
            raise ValueError(f"StructuralZero.kind is {self.kind!r}, not one of "
                             f"{STRUCTURAL_ZERO_KINDS}")
        measured = (self.channel_id, self.measured_paths, self.move_threshold)
        if self.kind == "stated_path":
            if self.reversal_key is None or any(v is not None for v in measured):
                raise ValueError(
                    "a stated_path row names its reversal_key and carries no "
                    "measurement: no draw touches the key it names")
        elif self.reversal_key is not None or any(v is None for v in measured):
            raise ValueError(
                "a dead_draw row names its stream, the futures it was measured on "
                "and the threshold it was held to, and no reversal_key")


@dataclass(frozen=True)
class ReversalRegister:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    code: str
    reason: str
    channel_id: Optional[int] = None


@dataclass(frozen=True)
class Decomposition:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

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
# silence — a run that did not pass the flag.
DecompositionOutcome = Optional[Union[Decomposition, DecompositionRefusal]]
