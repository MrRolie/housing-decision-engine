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
    fee_escalation_rate: float = 0.0
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)
    reserve_contribution_rate: float = 0.0  # Fraction of annual fees set aside each year
    reserve_initial_balance: float = 0.0
    reserve_growth_rate: float = 0.0  # Deterministic annual growth on reserve balance
    # --- S4a: condo as an owned, appreciating asset + capital structure ---
    initial_value: float = 0.0
    value_growth_rate: float = 0.0
    down_payment: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_term_years: Optional[int] = None
    all_cash: bool = False
    # WOWA 2026: seller-side commissions ≈ 4–5% + notary/discharge ⇒ 5% all-in
    selling_cost_rate: float = ANCHORS["condo.house.selling_cost_rate"].value
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
    value_growth_rate: float = 0.0
    annual_maintenance_rate: float = 0.0
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
    discount_rate: float
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
    inflation_rate: float = 0.0
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
class DeterministicResult:
    """
    Results from deterministic present value analysis.
    
    All values are in present value terms.
    
    Attributes:
        condo_pv_base: PV of condo monthly fees
        condo_pv_events: PV of condo one-time events
        condo_pv_other: PV of condo other recurring costs
        condo_pv_total: Total PV of condo costs
        house_pv_base: PV of house annual maintenance
        house_pv_events: PV of house one-time events
        house_pv_other: PV of house other recurring costs
        house_pv_total: Total PV of house costs
        diff_pv: house_pv_total - condo_pv_total (positive = house more expensive)
    """
    condo_pv_base: float
    condo_pv_events: float
    condo_pv_other: float
    condo_pv_total: float

    house_pv_base: float
    house_pv_events: float
    house_pv_other: float
    house_pv_total: float

    diff_pv: float


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


@dataclass
class MonteCarloResult:
    """
    Results from Monte Carlo simulation.
    
    Attributes:
        condo_pv: Array of condo PV values (shape: num_sims,)
        house_pv: Array of house PV values (shape: num_sims,)
        diff_pv: Array of house - condo PV values (shape: num_sims,)
        condo_summary: Summary statistics for condo PV distribution
        house_summary: Summary statistics for house PV distribution
        diff_summary: Summary statistics for difference distribution
        prob_house_more_expensive: P(diff_pv > 0)
    """
    condo_pv: npt.NDArray[np.float64]
    house_pv: npt.NDArray[np.float64]
    diff_pv: npt.NDArray[np.float64]

    condo_summary: MonteCarloSummary
    house_summary: MonteCarloSummary
    diff_summary: MonteCarloSummary

    prob_house_more_expensive: float


# ----- S3 Result Types -----

# Breakdown key constants — drift protection when fields are renamed
CONDO_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"fee_pv", "events_pv", "other_pv", "reserve_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
HOUSE_BREAKDOWN_KEYS: FrozenSet[str] = frozenset(
    {"maintenance_pv", "events_pv", "other_pv",
     "downpayment_pv", "mortgage_pv", "terminal_equity_pv"}
)
RENT_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"rent_pv", "events_pv", "other_pv", "invested_dp_benefit_pv"})


@dataclass
class OptionResult:
    """Per-option deterministic result."""
    total_pv: float
    breakdown: Dict[str, float]  # keys defined by {CONDO,HOUSE,RENT}_BREAKDOWN_KEYS


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
    """Replaces DeterministicResult."""
    condo: Optional[OptionResult] = None
    house: Optional[OptionResult] = None
    rent: Optional[OptionResult] = None
    income_report: Optional[AffordabilityReport] = None
    # S4b provenance: present only when a ScenarioPrior was loaded
    market_scenario: Optional[Dict[str, str]] = None


@dataclass
class MonteCarloOptionResult:
    """Per-option MC result. pvs array never crosses MCP boundary."""
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
    """Replaces MonteCarloResult."""
    condo: Optional[MonteCarloOptionResult] = None
    house: Optional[MonteCarloOptionResult] = None
    rent: Optional[MonteCarloOptionResult] = None
    prob_rent_cheapest: Optional[float] = None
    prob_condo_cheapest: Optional[float] = None
    prob_house_cheapest: Optional[float] = None
    affordability_mc: Optional[AffordabilityMCReport] = None
    # S4b provenance: present only when a ScenarioPrior was loaded
    market_scenario: Optional[Dict[str, str]] = None
