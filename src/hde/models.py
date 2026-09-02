"""
Domain models for the condo vs house cost analysis engine.

This module defines all the dataclasses used to represent parameters,
configurations, and results throughout the simulation.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Literal, Tuple

import numpy as np
import numpy.typing as npt

from .anchors import ANCHORS
from .pv import pv_to_monthly_savings


@dataclass
class RecurringOtherCost:
    """
    Represents a recurring cost beyond base fees/maintenance.
    
    Examples: property insurance, property taxes, landscaping service, etc.
    
    Attributes:
        name: Descriptive name for the cost
        annual_amount: Annual cost in year 1 (base year)
        escalation_rate: Annual growth rate (0.0 = no growth)
    """
    name: str
    annual_amount: float
    escalation_rate: float = 0.0
    # Optional deterministic real escalation; stochastic piece lives in SimulationParams.other_cost_vol


@dataclass
class MarketScenario:
    """
    S4b Slot 1 — reference to a demoflow ScenarioPrior artifact (demoflow spec §7(a)).

    Attributes:
        path: Path to the ScenarioPrior JSON file (whole-of-grid; loading filters
            rows to ``geography``).
        geography: Exact Geography string value to consume, e.g. "MTL_RMR".
    """
    path: str
    geography: str


@dataclass
class PriceShockParams:
    """
    S4b Slot 3 — price-drawdown channel parameters (default-off).

    The channel fires per year with probability
    ``annual_hazard × drawdown_weight_tilt(current band row)`` (tilt comes from
    the loaded ScenarioPrior; 1.0 = neutral when no prior is loaded).
    """
    annual_hazard: float = 0.0      # P(price drawdown begins this year)
    # TREB 1989–96: −27.6% nominal peak-trough (≈ −39.4% real); channel default-off
    severity_mean: float = ANCHORS["price_shock.severity_mean"].value
    # calibrated dispersion, not independently sourced — see anchors.py rationale
    severity_vol: float = ANCHORS["price_shock.severity_vol"].value


class InputError(Exception):
    """Fail-loud refusal of a semantically invalid engine input (e.g. composing
    a REAL-terms ScenarioPrior into a nominal-mode run)."""
    pass


@dataclass
class EventConfig:
    """
    Configuration for a one-time event (e.g., roof replacement, HVAC, special assessment).
    
    Supports both deterministic (expected_year) and stochastic timing (timing_std_years)
    as well as hazard-based timing models.
    
    Attributes:
        name: Descriptive name for the event
        base_cost: Expected cost of the event
        expected_year: The "typical" year when the event occurs (deterministic baseline)
        timing_std_years: Standard deviation for timing jitter in Monte Carlo (0.0 = no jitter)
        min_year: Earliest year the event can occur (default: 1)
        max_year: Latest year the event can occur (None = analysis horizon)
        cost_vol: Volatility for cost in Monte Carlo (std dev of normal shock, 0.0 = no randomness)
        timing_model: "jitter" (default) or "hazard"
        hazard_base: Base annual hazard (probability of occurrence) starting at hazard_start_year
        hazard_growth: Additional hazard added per year after hazard_start_year
        hazard_start_year: Year when hazard-based timing begins
        cost_distribution: Distribution used for cost shocks ("lognormal" default to avoid negatives)
    """
    name: str
    base_cost: float
    expected_year: int
    timing_std_years: float = 0.0
    min_year: int = 1
    max_year: Optional[int] = None
    cost_vol: float = 0.0
    timing_model: Literal["jitter", "hazard"] = "jitter"
    hazard_base: float = 0.0  # Annual hazard at hazard_start_year
    hazard_growth: float = 0.0  # Incremental hazard per year after hazard_start_year
    hazard_start_year: int = 1
    cost_distribution: Literal["normal", "lognormal"] = "lognormal"


@dataclass
class CondoParams:
    """
    Parameters for condo ownership costs.
    
    Attributes:
        monthly_fee: Base monthly condo/HOA fee
        fee_escalation_rate: Annual growth rate for fees (0.0 = level fees)
        events: List of one-time events (e.g., special assessments)
        other_recurring_costs: Additional recurring costs beyond the monthly fee
        reserve_contribution_rate: Fraction of annual fees set aside for reserves each year
        reserve_initial_balance: Starting reserve balance
        reserve_growth_rate: Deterministic growth on reserves
    """
    monthly_fee: float
    # FP Canada 2026 PAG shelter 3.1% nominal ≈ 1.0% real is the upper reference; 0.0 = fees track inflation
    fee_escalation_rate: float = ANCHORS["condo.fee_escalation_rate"].value
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
    reserve_contribution_rate: float = 0.0  # Fraction of annual fees set aside each year
    reserve_initial_balance: float = 0.0
    reserve_growth_rate: float = 0.0  # Deterministic annual growth on reserve balance
    # --- S4a: condo as an owned, appreciating asset + capital structure ---
    initial_value: float = 0.0
    # neutral, uncited — no defensible universal real appreciation default (anchors.py)
    value_growth_rate: float = ANCHORS["condo.value_growth_rate"].value
    down_payment: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    all_cash: bool = False
    # WOWA 2026: seller-side commissions ≈ 4–5% + notary/discharge ⇒ 5% all-in
    selling_cost_rate: float = ANCHORS["condo.house.selling_cost_rate"].value
    purchase_costs: float = 0.0  # $ paid at purchase (closing costs), year 0, outside the affordability ratio
    financed_purchase_costs: float = 0.0  # $ rolled into the loan principal (e.g. a financed mortgage-insurance premium)
    # --- S4b Slot 3: price-drawdown channel (default None = off) ---
    price_shock: Optional[PriceShockParams] = None


@dataclass
class HouseParams:
    """
    Parameters for house ownership costs.
    
    Attributes:
        initial_value: House value at year 0 (used for maintenance calculation)
        value_growth_rate: Annual growth rate of house value (for maintenance calculation)
        annual_maintenance_rate: Annual maintenance as a fraction of house value
        events: List of one-time events (e.g., roof, HVAC, plumbing)
        other_recurring_costs: Additional recurring costs beyond maintenance
        maintenance_curve: Optional (year, rate) points for age/condition curve; interpolated annually
    """
    initial_value: float
    # neutral, uncited — no defensible universal real appreciation default (anchors.py)
    value_growth_rate: float = ANCHORS["house.value_growth_rate"].value
    # neutral, uncited — 0.0 = no maintenance modelled; the echo + a warning say so (anchors.py)
    annual_maintenance_rate: float = ANCHORS["house.annual_maintenance_rate"].value
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
    maintenance_curve: List[Tuple[int, float]] = field(default_factory=list)  # (year, rate) pairs sorted by year
    # --- S4a capital structure (net-wealth model) ---
    down_payment: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    all_cash: bool = False
    # WOWA 2026: seller-side commissions ≈ 4–5% + notary/discharge ⇒ 5% all-in
    selling_cost_rate: float = ANCHORS["condo.house.selling_cost_rate"].value
    purchase_costs: float = 0.0  # $ paid at purchase (closing costs), year 0, outside the affordability ratio
    financed_purchase_costs: float = 0.0  # $ rolled into the loan principal (e.g. a financed mortgage-insurance premium)
    # --- S4b Slot 3: price-drawdown channel (default None = off) ---
    price_shock: Optional[PriceShockParams] = None


@dataclass
class SimulationParams:
    """
    Parameters controlling the simulation.
    
    Attributes:
        years: Analysis horizon in years
        discount_rate: Discount rate for PV calculations (nominal or real per EconomicParams)
        num_sims: Number of Monte Carlo simulations
        random_seed: Seed for reproducible random number generation
        house_maintenance_vol: Volatility (std dev) for house maintenance costs
        condo_fee_vol: Volatility (std dev) for condo fee costs
        other_cost_vol: Volatility for other_recurring_costs
        corr_inflation_house: Correlation between inflation shock and house maintenance shock
        corr_inflation_condo: Correlation between inflation shock and condo fee shock
        corr_inflation_other: Correlation between inflation shock and other cost shock
        corr_inflation_event_cost: Correlation between inflation shock and event cost shock
        shock_model: "lognormal" (default) or "normal" for multiplicative shocks
    """
    years: int
    discount_rate: float = ANCHORS["simulation.discount_rate"].value
    num_sims: int = 10_000
    random_seed: int = 42
    house_maintenance_vol: float = 0.0
    condo_fee_vol: float = 0.0
    other_cost_vol: float = 0.0
    corr_inflation_house: float = 0.0
    corr_inflation_condo: float = 0.0
    corr_inflation_other: float = 0.0
    corr_inflation_event_cost: float = 0.0
    shock_model: Literal["lognormal", "normal"] = "lognormal"
    rent_escalation_vol: float = 0.0
    investment_return_vol: float = 0.0


@dataclass
class EconomicParams:
    """
    Economic assumptions for the analysis.
    
    In v1, these are primarily documentary. The user is expected to provide
    consistent parameters (i.e., if mode is "real", discount_rate should be real).
    
    Attributes:
        mode: Whether parameters are in "nominal" or "real" terms
        inflation_rate: Expected inflation rate (used if mode == "nominal")
        inflation_vol: Volatility for annual inflation shock (used for correlation)
    """
    mode: Literal["nominal", "real"] = "real"
    # real-mode inert value; nominal-mode planning figure lives in anchors.py (2.1%)
    inflation_rate: float = ANCHORS["economic.inflation_rate"].value
    inflation_vol: float = 0.0


# ----- S3 Input Types -----

@dataclass
class PayDropEvent:
    """A one-time income shock event."""
    year: int
    magnitude: float        # fraction of income retained (0.8 = 20% cut)
    year_jitter_std: float = 0.0
    magnitude_vol: float = 0.0


@dataclass
class RentParams:
    """Parameters for the rent option."""
    monthly_rent: float
    # FP Canada 2026 PAG shelter-cost growth 3.1% − 2.1% inflation = 1.0% real
    rent_escalation_rate: float = ANCHORS["rent.rent_escalation_rate"].value
    invested_down_payment: float = 0.0
    # FP Canada 2026 PAG 60/40 ≈ 5.1% nominal − 2.1% = 3.0% real
    investment_return_rate: float = ANCHORS["rent.investment_return_rate"].value
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)


@dataclass
class IncomeParams:
    """Employment cash flow parameters for affordability modeling."""
    annual_income: float
    # FP Canada 2026 PAG salary growth 3.1% − 2.1% inflation = 1.0% real
    income_growth_rate: float = ANCHORS["income.income_growth_rate"].value
    # Legacy GDS guideline 32% — below CMHC's 39% cap; hde's numerator is broader than PITH
    affordability_threshold: float = ANCHORS["income.affordability_threshold"].value
    pay_drop_events: List[PayDropEvent] = field(default_factory=list)


@dataclass
class ComparisonSpec:
    """Single input bundle for all comparison engines. Replaces the 4-tuple."""
    simulation: SimulationParams
    economic: EconomicParams
    condo: Optional[CondoParams] = None
    house: Optional[HouseParams] = None
    rent: Optional[RentParams] = None
    income: Optional[IncomeParams] = None
    # --- S4b Slot 1: demographic drift prior (default None = off) ---
    market_scenario: Optional[MarketScenario] = None
    # --- Audit U1: assumption keys whose values came from defaults, not user
    # YAML (dotted, e.g. 'rent.rent_escalation_rate'). Populated by the config
    # loader; empty when the spec is constructed directly. Pure provenance —
    # reports serialize it, engines never read it.
    defaults_applied: List[str] = field(default_factory=list)


# ----- Result Dataclasses -----

@dataclass
class MonteCarloSummary:
    """
    Summary statistics for a Monte Carlo distribution.
    
    Attributes:
        mean: Mean of the distribution
        std: Standard deviation
        p5: 5th percentile
        p50: Median (50th percentile)
        p95: 95th percentile
    """
    mean: float
    std: float
    p5: float
    p50: float
    p95: float


# ----- S3 Result Types -----

# Breakdown key constants — drift protection when fields are renamed
CONDO_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"purchase_costs_pv", "fee_pv", "events_pv", "other_pv", "reserve_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
HOUSE_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"purchase_costs_pv", "maintenance_pv", "events_pv", "other_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
RENT_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"invested_capital_pv", "rent_pv", "events_pv", "other_pv", "invested_dp_benefit_pv"})


@dataclass
class OptionResult:
    """Per-option deterministic result.

    cash_year1 / principal_year1 (round-four dogfood 2026-09-02): the
    UNDISCOUNTED year-1 cash outlay (the affordability numerator: fees, tax,
    other costs, the full mortgage payment; rent for the renter) and the
    principal repaid in year 1 (payment − loan × rate; 0 without a mortgage).
    A sticker-cash reader takes the $/month PV equivalent as out-of-pocket;
    these two figures let the answer say what the cash gap is and that the
    PV win is equity at sale."""
    total_pv: float
    breakdown: Dict[str, float]  # keys defined by {CONDO,HOUSE,RENT}_BREAKDOWN_KEYS
    cash_year1: Optional[float] = None
    principal_year1: Optional[float] = None
    appreciation_year1: Optional[float] = None  # owned: initial_value × effective growth (composed in nominal mode); 0 for rent


@dataclass
class AffordabilityReport:
    """Deterministic affordability layer."""
    annual_incomes: List[float]
    threshold: float
    rent_ratios: Optional[List[float]] = None
    condo_ratios: Optional[List[float]] = None
    house_ratios: Optional[List[float]] = None
    years_rent_exceeds: List[int] = field(default_factory=list)
    years_condo_exceeds: List[int] = field(default_factory=list)
    years_house_exceeds: List[int] = field(default_factory=list)


@dataclass
class ComparisonDeterministicResult:
    """Per-option deterministic results + affordability + prior provenance."""
    condo: Optional[OptionResult] = None
    house: Optional[OptionResult] = None
    rent: Optional[OptionResult] = None
    income_report: Optional[AffordabilityReport] = None
    # S4b provenance: present only when a ScenarioPrior was loaded
    market_scenario: Optional[Dict[str, str]] = None


@dataclass
class MonteCarloOptionResult:
    """Per-option MC result. The pvs array never crosses a surface boundary — only
    the MonteCarloSummary scalars are serialized."""
    pvs: npt.NDArray[np.float64]
    summary: MonteCarloSummary


@dataclass
class AffordabilityMCReport:
    """MC affordability layer."""
    threshold: float
    prob_rent_exceeds: Optional[float] = None
    prob_condo_exceeds: Optional[float] = None
    prob_house_exceeds: Optional[float] = None


@dataclass
class ComparisonMonteCarloResult:
    """Per-option Monte Carlo results + P(option cheapest) + affordability MC."""
    condo: Optional[MonteCarloOptionResult] = None
    house: Optional[MonteCarloOptionResult] = None
    rent: Optional[MonteCarloOptionResult] = None
    prob_rent_cheapest: Optional[float] = None
    prob_condo_cheapest: Optional[float] = None
    prob_house_cheapest: Optional[float] = None
    affordability_mc: Optional[AffordabilityMCReport] = None
    # S4b provenance: present only when a ScenarioPrior was loaded
    market_scenario: Optional[Dict[str, str]] = None


# ----- Verdict (readiness plan B.1, 2026-09-01) -----

@dataclass(frozen=True)
class Verdict:
    """
    The decision, computed ONCE and consumed by every surface (story headline,
    text report, --json): which option is cheapest, by how much versus the
    runner-up (the decision-relevant gap, never the costliest), and whether
    that gap is decisive under the rule that applied.

    rule: "single_option" | "mc_floor" | "margin_band"
    reason: one sentence stating the rule, the measured quantity and the
        anchored threshold, e.g. "P(rent cheapest) = 81% ≥ 65% floor [hde verdict rule]".
    mc_mean_best: the option with the lowest Monte Carlo MEAN total PV when
        Monte Carlo ran with real uncertainty (None otherwise). When it
        differs from `best` — a jump process such as price_shock moves the
        mean without moving the deterministic line — `reason` says so with
        both means; "lowest expected cost" is then the mean, not `best`.
    """
    best: str
    runner_up: Optional[str]
    margin_pv: float
    margin_frac: float
    monthly_equivalent: Optional[float]
    prob_best: Optional[float]
    decisive: bool
    rule: str
    reason: str
    mc_mean_best: Optional[str] = None


def compute_verdict(
    det: "ComparisonDeterministicResult",
    mc: Optional["ComparisonMonteCarloResult"] = None,
    *,
    years: int,
    discount_rate: float = 0.0,
    single_path: bool = False,
) -> Optional[Verdict]:
    """
    Decisiveness rule (operator-ruled 2026-09-01; constants in anchors.py):
      - primary, when Monte Carlo ran with real uncertainty (``mc`` given and
        not ``single_path``) and carries a probability for the deterministic
        winner: decisive ⇔ P(best cheapest) ≥ verdict.prob_floor;
      - fallback otherwise: decisive ⇔ margin / |best PV| ≥ verdict.tie_band.
    Returns None when no option is priced.
    """
    costs = {
        key: opt.total_pv
        for key, opt in (("condo", det.condo), ("house", det.house), ("rent", det.rent))
        if opt is not None
    }
    if not costs:
        return None
    ranked = sorted(costs.items(), key=lambda kv: kv[1])
    best, best_pv = ranked[0]
    if len(ranked) == 1:
        return Verdict(best, None, 0.0, 0.0, None, None, True, "single_option",
                       "only one option priced — nothing to compare")
    runner_up, runner_pv = ranked[1]
    margin = runner_pv - best_pv
    # Fraction of the WINNER's total PV (the ruled tie band is stated that way);
    # a zero winner PV (net wealth exactly offsetting cost) falls back to the
    # runner-up's magnitude so the ratio stays finite.
    denom = abs(best_pv) if best_pv != 0 else abs(runner_pv)
    margin_frac = margin / denom if denom > 0 else 0.0
    monthly = (
        pv_to_monthly_savings(margin, discount_rate, years)
        if discount_rate > 0 and years > 0 else None
    )

    prob_best: Optional[float] = None
    means: Dict[str, float] = {}
    mc_mean_best: Optional[str] = None
    if mc is not None and not single_path:
        prob_best = getattr(mc, f"prob_{best}_cheapest")
        means = {k: getattr(mc, k).summary.mean for k in costs if getattr(mc, k) is not None}
        if means:
            mc_mean_best = min(means, key=lambda k: means[k])

    floor = ANCHORS["verdict.prob_floor"].value
    band = ANCHORS["verdict.tie_band"].value
    if prob_best is not None:
        decisive = prob_best >= floor
        rule = "mc_floor"
        reason = (
            f"P({best} cheapest) = {prob_best:.0%} {'≥' if decisive else '<'} "
            f"{floor:.0%} floor [hde verdict rule]"
        )
        if not decisive:
            others = {
                k: getattr(mc, f"prob_{k}_cheapest") for k in costs if k != best
            }
            others = {k: v for k, v in others.items() if v is not None}
            if others:
                mc_best = max(others, key=lambda k: others[k])
                if others[mc_best] > prob_best:
                    reason += f"; Monte Carlo favours {mc_best} ({others[mc_best]:.1%})"
    else:
        decisive = margin_frac >= band
        rule = "margin_band"
        why = "single-path run, uncertainty inputs off" if single_path else "no Monte Carlo"
        reason = (
            f"margin {margin_frac:.1%} of {best} PV {'≥' if decisive else '<'} "
            f"{band:.0%} tie band [hde verdict rule] ({why})"
        )
    if mc_mean_best is not None and mc_mean_best != best:
        reason += (f"; Monte Carlo mean favours {mc_mean_best} "
                   f"(${means[mc_mean_best]:,.0f} vs ${means[best]:,.0f})")
    return Verdict(best, runner_up, margin, margin_frac, monthly, prob_best,
                   decisive, rule, reason, mc_mean_best)
