"""Fields: docs/reference/API_CONTRACT.md § The `decomposition` block.

Design: docs/specs/2026-09-22-which-risk-decides-it.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple, Union

if TYPE_CHECKING:
    from .models import Verdict


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 52.
POINTER = "Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."


# ---------------------------------------------------------------------------
# Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.1.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Channel:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    id: int
    key: str
    label: str
    sizing_keys: Tuple[str, ...]


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.2.
CHANNELS: Tuple[Channel, ...] = (
    Channel(
        id=0,
        key="economy",
        label="the economy",
        # Design: docs/specs/2026-09-22-which-risk-decides-it.md §4.
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
    # Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.1.
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


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 21.
INCOME_STREAM_ID: int = 7

# Fields: docs/reference/API_CONTRACT.md § The `decomposition` block.
INCOME_STREAM_LABEL: str = "your pay drops"


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §9.
LEVEL_PATHS: int = 2000


def channel(channel_id: int) -> Channel:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.1."""
    if not 0 <= channel_id < len(CHANNELS):
        raise KeyError(channel_id)
    return CHANNELS[channel_id]


def channel_by_key(key: str) -> Channel:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.1."""
    for entry in CHANNELS:
        if entry.key == key:
            return entry
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Fields: docs/reference/API_CONTRACT.md § The `decomposition` block.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Interval:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    low: float
    high: float


def _require_one_top(kind: str, leading: Optional[int],
                     unresolved_top: Optional[int]) -> None:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""
    if leading is not None and unresolved_top is not None:
        raise ValueError(
            f"{kind}.leading_channel_id is {leading} and unresolved_top_channel_id "
            f"is {unresolved_top}: at most one of the two is set")


def _require_kind(register: str, zeros: Tuple[object, ...], kind: str) -> None:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""
    for zero in zeros:
        if getattr(zero, "kind", None) != kind:
            raise ValueError(
                f"{register}.structural_zeros holds a {getattr(zero, 'kind', zero)!r} "
                f"row, not a {kind!r} row")


@dataclass(frozen=True)
class Width:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    key: str
    formatted: Optional[str]
    source: str
    anchor: Optional[str] = None
    note: Optional[str] = None
    tag: Optional[str] = None


# ---------------------------------------------------------------------------
# Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.3.
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
    structural_zeros: Tuple["StructuralZero", ...]

    def __post_init__(self) -> None:
        _require_one_top("SpreadRegister", self.leading_channel_id,
                         self.unresolved_top_channel_id)
        _require_kind("SpreadRegister", self.structural_zeros, "dead_draw")


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 7.
SPREAD_REFUSAL_CODES: Tuple[str, ...] = (
    "no_sign_variation",
)


@dataclass(frozen=True)
class RefusedSpread:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    code: str
    reason: str
    structural_zeros: Tuple["StructuralZero", ...]

    def __post_init__(self) -> None:
        _require_kind("RefusedSpread", self.structural_zeros, "dead_draw")


# ---------------------------------------------------------------------------
# Design: docs/specs/2026-09-22-which-risk-decides-it.md §3.4.
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
# Design: docs/specs/2026-09-22-which-risk-decides-it.md §6.
# ---------------------------------------------------------------------------

# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 4.
BOUNDARY_FIELDS: Tuple[str, ...] = ("best", "runner_up", "mc_best", "decisive")

# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 items 39 and 40.
STRUCTURAL_ZERO_KINDS: Tuple[str, ...] = ("stated_path", "dead_draw")


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §6.
FURTHER_CHANGE_SIDES: Tuple[str, ...] = ("above", "below")


def _require_side(kind: str, verdict_field: str, further_changes: object) -> None:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §6."""
    if further_changes is not None and further_changes not in FURTHER_CHANGE_SIDES:
        raise ValueError(
            f"{kind}.further_changes for {verdict_field!r} is {further_changes!r}, "
            f"not None or one of {FURTHER_CHANGE_SIDES}")


def _require_words(kind: str, verdict_field: str, was: object, becomes: object) -> None:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §6."""
    for name, value in (("was", was), ("becomes", becomes)):
        if not isinstance(value, str) or not value.strip():
            raise TypeError(
                f"{kind}.{name} for {verdict_field!r} is {value!r} "
                f"({type(value).__name__}), not words")


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
    upper_end: float
    formatted: str
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
    upper_end: float
    formatted: str
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


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 50.
BOUNDARY_REFUSAL_CODES: Tuple[str, ...] = (
    "unchanged",
    "not_on_axis",
    "not_identified",
    "unconfirmed",
    "not_exact",
    "no_futures",
    "scan_mismatch",
    "not_printable",
    "not_orderable",
)

# Fields: docs/reference/API_CONTRACT.md § The `decomposition` block.
EDGE_REFUSAL_CODES: Tuple[str, ...] = (
    "not_identified",
    "unconfirmed",
    "not_printable",
    "not_orderable",
)

NO_DISTANCE_CODES: Tuple[str, ...] = (
    "no_candidate",
    "no_mapping",
    "single_option",
)

# Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 64.
REVERSAL_REFUSAL_CODES: Tuple[str, ...] = ("not_admitted",)


def _require_types(where: str, items: Tuple[object, ...],
                   allowed: Tuple[type, ...]) -> None:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 24."""
    for item in items:
        if not isinstance(item, allowed):
            raise TypeError(f"{where} holds a {type(item).__name__}, not one of "
                            f"{tuple(t.__name__ for t in allowed)}")


def _require_code(kind: str, code: object, codes: Tuple[str, ...]) -> None:
    """Design: docs/specs/2026-09-22-which-risk-decides-it.md §6."""
    if code not in codes:
        raise ValueError(f"{kind}.code is {code!r}, not one of {codes}")


@dataclass(frozen=True)
class RefusedBoundary:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    verdict_field: str
    code: str
    reason: str

    def __post_init__(self) -> None:
        _require_code("RefusedBoundary", self.code, BOUNDARY_REFUSAL_CODES)


@dataclass(frozen=True)
class ExactReversal:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    key: str
    option: str
    stated_formatted: str
    stated_source: str
    stated_tag: str
    bracket_low: float
    bracket_high: float
    bracket_source: str
    probe_paths: int
    max_path_deviation_over_sd: float
    # Design: docs/specs/2026-09-22-which-risk-decides-it.md §0.1 item 24.
    boundaries: Tuple[Union[SolvedBoundary, SampledBoundary], ...]
    refused_boundaries: Tuple[RefusedBoundary, ...]
    references: Tuple[AxisReference, ...]
    path_note: Optional[str] = None

    def __post_init__(self) -> None:
        _require_types("ExactReversal.boundaries", self.boundaries,
                       (SolvedBoundary, SampledBoundary))


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
    stated_tag: str
    bracket_low: float
    bracket_high: float
    bracket_source: str
    max_path_deviation_over_sd: float
    boundaries: Tuple[EstimatedBoundary, ...]
    refused_boundaries: Tuple[RefusedBoundary, ...]
    references: Tuple[AxisReference, ...]
    path_note: Optional[str] = None

    def __post_init__(self) -> None:
        _require_types("EstimatedReversal.boundaries", self.boundaries,
                       (EstimatedBoundary,))


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
        if self.kind not in STRUCTURAL_ZERO_KINDS:
            raise ValueError(f"StructuralZero.kind is {self.kind!r}, not one of "
                             f"{STRUCTURAL_ZERO_KINDS}")
        measured = (self.channel_id, self.measured_paths, self.move_threshold)
        if self.kind == "stated_path":
            if self.reversal_key is None or any(v is not None for v in measured):
                raise ValueError(
                    f"a stated_path row has reversal_key {self.reversal_key!r} and "
                    f"channel_id, measured_paths, move_threshold {measured}: it sets "
                    f"the first and none of the three")
        elif self.reversal_key is not None or any(v is None for v in measured):
            raise ValueError(
                f"a dead_draw row has reversal_key {self.reversal_key!r} and channel_id, "
                f"measured_paths, move_threshold {measured}: it sets the three and "
                f"not the first")


@dataclass(frozen=True)
class RefusedReversal:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    key: str
    option: str
    code: str
    reason: str

    def __post_init__(self) -> None:
        _require_code("RefusedReversal", self.code, REVERSAL_REFUSAL_CODES)


@dataclass(frozen=True)
class ReversalRegister:
    """Fields: docs/reference/API_CONTRACT.md § The `decomposition` block."""

    exact: Tuple[ExactReversal, ...]
    estimated: Tuple[EstimatedReversal, ...]
    structural_zeros: Tuple[StructuralZero, ...]
    no_distance_code: Optional[str]
    no_distance_reason: Optional[str]
    refused: Tuple[RefusedReversal, ...] = ()

    def __post_init__(self) -> None:
        _require_kind("ReversalRegister", self.structural_zeros, "stated_path")
        _require_types("ReversalRegister.refused", self.refused, (RefusedReversal,))
        rows = len(self.exact) + len(self.estimated) + len(self.refused)
        empty = not rows
        if not (empty == (self.no_distance_reason is not None)
                == (self.no_distance_code is not None)):
            raise ValueError(
                f"ReversalRegister has {rows} rows, "
                f"no_distance_code {self.no_distance_code!r} and no_distance_reason "
                f"{self.no_distance_reason!r}: both are set exactly when there is no row")
        if empty:
            _require_code("ReversalRegister.no_distance", self.no_distance_code,
                          NO_DISTANCE_CODES)


# ---------------------------------------------------------------------------
# Design: docs/specs/2026-09-22-which-risk-decides-it.md §7.
# ---------------------------------------------------------------------------

# Design: docs/specs/2026-09-22-which-risk-decides-it.md §8.
REFUSAL_CODES: Tuple[str, ...] = (
    "no_futures",
    "too_few_futures",
    "single_option",
    "one_channel",
    "no_spread",
    "budget",
    "income_moved",
    "untagged_width",
    "degenerate_resample",
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
                f"count of {self.max_paths}")


# Design: docs/specs/2026-09-22-which-risk-decides-it.md §8.
DecompositionOutcome = Optional[Union[Decomposition, DecompositionRefusal]]
