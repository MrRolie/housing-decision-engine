"""
Deterministic present value calculations for condo vs house costs.

This module provides functions for computing the present value of
ownership costs using deterministic (fixed) parameters, without
any randomness or Monte Carlo simulation.
"""

from typing import List, Optional, Tuple

from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    ComparisonSpec,
    ComparisonDeterministicResult,
    OptionResult,
    AffordabilityReport,
    RentParams,
    IncomeParams,
    PayDropEvent,
    CONDO_BREAKDOWN_KEYS,
    HOUSE_BREAKDOWN_KEYS,
    RENT_BREAKDOWN_KEYS,
)
from .pv import (
    pv_single,
    pv_annuity,
    pv_growth_annuity,
    pv_recurring_with_escalation,
    mortgage_payment,
    outstanding_balance,
)


def _effective_growth_rate(base_rate: float, econ: EconomicParams) -> float:
    """
    Combine user growth/escalation with inflation when operating in nominal mode.
    """
    if econ.mode == "nominal":
        return (1 + base_rate) * (1 + econ.inflation_rate) - 1
    return base_rate


def _require_valued_growth(effective_growth: float, label: str) -> None:
    """
    Reject an appreciation factor <= 0 before valuing terminal equity.

    ``value_N = initial_value * (1 + g) ** years``: when ``1 + g < 0`` the power
    flips sign by the parity of ``years``, producing garbage terminal equity
    (config validation rejects value_growth_rate <= -1; this is the defense for
    directly-constructed params that bypass config).
    """
    if 1 + effective_growth <= 0:
        raise ValueError(
            f"{label} value_growth_rate implies a non-positive appreciation factor "
            f"(1+g={1 + effective_growth:.4f}); growth <= -100% cannot be valued")


def _financing_pv(
    initial_value: float,
    down_payment: Optional[float],
    mortgage_rate: Optional[float],
    mortgage_term_years: Optional[int],
    all_cash: bool,
    selling_cost_rate: float,
    value_N: float,
    dr: float,
    n_years: int,
) -> Tuple[float, float, float]:
    """
    (downpayment_pv, mortgage_pv, terminal_equity_pv) for an owned option.

    Fail-loud (strategic Mod 5): direct-construction callers that declare neither
    all_cash nor a complete mortgage block raise here, not compute silent garbage.
    """
    if not all_cash and (
        down_payment is None or mortgage_rate is None or mortgage_term_years is None
    ):
        raise ValueError(
            "owned option requires all_cash=True OR a full mortgage block "
            "(down_payment + mortgage_rate + mortgage_term_years)"
        )
    if all_cash:
        downpayment_pv = initial_value
        mortgage_pv = 0.0
        balance_N = 0.0
    else:
        # Fail-loud on impossible mortgage blocks that would otherwise compute
        # silent garbage: down_payment > initial_value drives the loan negative,
        # and mortgage_payment() returns 0.0 for non-positive principal.
        if not (0 <= down_payment <= initial_value):
            raise ValueError(
                f"owned option down_payment must be in [0, initial_value], "
                f"got down_payment={down_payment}, initial_value={initial_value}")
        if mortgage_rate < 0:
            raise ValueError(f"owned option mortgage_rate must be >= 0, got {mortgage_rate}")
        if mortgage_term_years <= 0:
            raise ValueError(f"owned option mortgage_term_years must be > 0, got {mortgage_term_years}")
        downpayment_pv = down_payment
        loan = initial_value - down_payment
        payment = mortgage_payment(loan, mortgage_rate, mortgage_term_years)
        mortgage_pv = pv_annuity(payment, dr, min(n_years, mortgage_term_years))
        balance_N = outstanding_balance(
            loan, mortgage_rate, mortgage_term_years, n_years, payment
        )
    equity_N = value_N * (1 - selling_cost_rate) - balance_N
    terminal_equity_pv = -pv_single(equity_N, dr, n_years)
    return downpayment_pv, mortgage_pv, terminal_equity_pv


def _maintenance_rate_for_year(house: HouseParams, year: int) -> float:
    """
    Return maintenance rate for a given year using an optional age/condition curve.
    """
    if not house.maintenance_curve:
        return house.annual_maintenance_rate

    # Find surrounding points for interpolation
    points = house.maintenance_curve
    if year <= points[0][0]:
        return points[0][1]
    if year >= points[-1][0]:
        return points[-1][1]

    for (y0, r0), (y1, r1) in zip(points[:-1], points[1:]):
        if y0 <= year <= y1:
            span = y1 - y0
            weight = (year - y0) / span
            return r0 + weight * (r1 - r0)

    return house.annual_maintenance_rate


def _event_year_deterministic(event: EventConfig, years: int) -> int:
    """
    Deterministic placement of events. For hazard-based events, fall back to expected_year.
    """
    year = event.expected_year
    if event.min_year:
        year = max(event.min_year, year)
    if event.max_year is not None:
        year = min(event.max_year, year)
    return max(1, min(year, years))


def _compute_events_pv(
    events: list[EventConfig],
    discount_rate: float,
    years: int,
) -> float:
    """
    Compute PV of one-time events using their expected_year (deterministic).

    Events with expected_year outside [1, years] are clamped to valid range.
    """
    total_pv = 0.0
    for event in events:
        # Clamp year to valid range
        year = max(1, min(event.expected_year, years))
        total_pv += pv_single(event.base_cost, discount_rate, year)
    return total_pv


def _compute_other_recurring_pv(
    other_costs: list[RecurringOtherCost],
    discount_rate: float,
    years: int,
    econ: EconomicParams,
) -> float:
    """
    PV of other recurring costs (rent option): year-t cost = amount × (1+e)^t,
    with e composed with inflation in nominal mode exactly as the condo/house
    loops do (readiness plan D, 2026-09-01 — rent's other costs previously
    skipped inflation in nominal mode, unlike every other escalating flow).
    """
    total_pv = 0.0
    for cost in other_costs:
        total_pv += pv_recurring_with_escalation(
            cost.annual_amount,
            _effective_growth_rate(cost.escalation_rate, econ),
            discount_rate,
            years
        )
    return total_pv


def _compute_condo_option(
    condo: CondoParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> OptionResult:
    """
    Compute the deterministic OptionResult for a condo.

    Preserves the exact year-by-year arithmetic of the original engine:
    per-year fee escalation, reserve accrual, and reserve coverage of events.

    Breakdown keys (CONDO_BREAKDOWN_KEYS):
      - fee_pv:     PV of escalating monthly fees
      - events_pv:  PV of one-time events (GROSS of reserve coverage)
      - other_pv:   PV of other recurring costs
      - reserve_pv: NEGATIVE PV of reserve coverage applied to events (offset)

    total_pv = fee_pv + events_pv + other_pv + reserve_pv, which (because
    pv_single is linear) reproduces the original net-of-reserve total exactly.
    """
    discount_rate = sim.discount_rate
    fee_growth = _effective_growth_rate(condo.fee_escalation_rate, econ)
    reserve_growth = _effective_growth_rate(condo.reserve_growth_rate, econ)

    other_cost_growth = [
        _effective_growth_rate(c.escalation_rate, econ)
        for c in condo.other_recurring_costs
    ]

    event_years = {
        e.name: _event_year_deterministic(e, sim.years) for e in condo.events
    }

    condo_fee = condo.monthly_fee * 12
    reserve_balance = condo.reserve_initial_balance
    fee_pv = 0.0
    events_pv = 0.0      # gross of reserve coverage
    other_pv = 0.0
    reserve_pv = 0.0     # accumulated as negative offset

    for year in range(1, sim.years + 1):
        # Base fees and reserve accrual
        condo_fee *= (1 + fee_growth)
        reserve_balance *= (1 + reserve_growth)
        reserve_contribution = condo_fee * condo.reserve_contribution_rate
        reserve_balance += reserve_contribution
        fee_pv += pv_single(condo_fee, discount_rate, year)

        # Other recurring costs
        for idx, rec_cost in enumerate(condo.other_recurring_costs):
            rec_growth = other_cost_growth[idx]
            amount = rec_cost.annual_amount * (1 + rec_growth) ** year
            other_pv += pv_single(amount, discount_rate, year)

        # Events: record gross cost, and the reserve coverage as a separate offset
        for event in condo.events:
            if event_years[event.name] == year:
                event_cost = event.base_cost
                covered = min(reserve_balance, event_cost)
                reserve_balance -= covered
                events_pv += pv_single(event_cost, discount_rate, year)
                reserve_pv -= pv_single(covered, discount_rate, year)

    condo_value_growth = _effective_growth_rate(condo.value_growth_rate, econ)
    _require_valued_growth(condo_value_growth, "condo")
    value_N = condo.initial_value * (1 + condo_value_growth) ** sim.years
    downpayment_pv, mortgage_pv, terminal_equity_pv = _financing_pv(
        condo.initial_value, condo.down_payment, condo.mortgage_rate,
        condo.mortgage_term_years, condo.all_cash, condo.selling_cost_rate,
        value_N, discount_rate, sim.years,
    )
    total_pv = (fee_pv + events_pv + other_pv + reserve_pv
                + downpayment_pv + mortgage_pv + terminal_equity_pv)
    breakdown = {
        "fee_pv": fee_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "reserve_pv": reserve_pv,
        "downpayment_pv": downpayment_pv,
        "mortgage_pv": mortgage_pv,
        "terminal_equity_pv": terminal_equity_pv,
    }
    assert set(breakdown.keys()) == CONDO_BREAKDOWN_KEYS
    return OptionResult(total_pv=total_pv, breakdown=breakdown)


def _compute_house_option(
    house: HouseParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> OptionResult:
    """
    Compute the deterministic OptionResult for a house.

    Preserves the exact year-by-year arithmetic of the original engine:
    value growth, age/condition maintenance curve, events, and other costs.

    Breakdown keys (HOUSE_BREAKDOWN_KEYS):
      - maintenance_pv: PV of maintenance (value * maintenance-rate-for-year)
      - events_pv:      PV of one-time events
      - other_pv:       PV of other recurring costs
    """
    discount_rate = sim.discount_rate
    house_value_growth = _effective_growth_rate(house.value_growth_rate, econ)
    _require_valued_growth(house_value_growth, "house")

    other_cost_growth = [
        _effective_growth_rate(c.escalation_rate, econ)
        for c in house.other_recurring_costs
    ]

    event_years = {
        e.name: _event_year_deterministic(e, sim.years) for e in house.events
    }

    house_value = house.initial_value
    maintenance_pv = 0.0
    events_pv = 0.0
    other_pv = 0.0

    for year in range(1, sim.years + 1):
        # Maintenance baseline using age/condition curve
        if year > 1:
            house_value *= (1 + house_value_growth)
        maintenance_rate = _maintenance_rate_for_year(house, year)
        maint_amount = maintenance_rate * house_value
        maintenance_pv += pv_single(maint_amount, discount_rate, year)

        # Other recurring costs
        for idx, rec_cost in enumerate(house.other_recurring_costs):
            rec_growth = other_cost_growth[idx]
            amount = rec_cost.annual_amount * (1 + rec_growth) ** year
            other_pv += pv_single(amount, discount_rate, year)

        # Events
        for event in house.events:
            if event_years[event.name] == year:
                events_pv += pv_single(event.base_cost, discount_rate, year)

    value_N = house.initial_value * (1 + house_value_growth) ** sim.years
    downpayment_pv, mortgage_pv, terminal_equity_pv = _financing_pv(
        house.initial_value, house.down_payment, house.mortgage_rate,
        house.mortgage_term_years, house.all_cash, house.selling_cost_rate,
        value_N, discount_rate, sim.years,
    )
    total_pv = (maintenance_pv + events_pv + other_pv
                + downpayment_pv + mortgage_pv + terminal_equity_pv)
    breakdown = {
        "maintenance_pv": maintenance_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "downpayment_pv": downpayment_pv,
        "mortgage_pv": mortgage_pv,
        "terminal_equity_pv": terminal_equity_pv,
    }
    assert set(breakdown.keys()) == HOUSE_BREAKDOWN_KEYS
    return OptionResult(total_pv=total_pv, breakdown=breakdown)


def _compute_rent_option(
    rent: RentParams,
    sim: SimulationParams,
    econ: EconomicParams,
) -> OptionResult:
    """
    Compute the deterministic OptionResult for the rent option.

    Breakdown keys (RENT_BREAKDOWN_KEYS):
      - rent_pv:                 PV of escalating rent
      - events_pv:               PV of one-time events (e.g., moving costs)
      - other_pv:                PV of other recurring costs
      - invested_dp_benefit_pv:  NEGATIVE PV of the invested down-payment benefit
                                  (a renter keeps the down payment invested; this
                                  reduces the net cost of renting, so it is stored
                                  as a negative offset).
    """
    dr = sim.discount_rate
    rent_escalation = _effective_growth_rate(rent.rent_escalation_rate, econ)

    annual_rent = rent.monthly_rent * 12
    rent_pv = pv_recurring_with_escalation(annual_rent, rent_escalation, dr, sim.years)
    events_pv = _compute_events_pv(rent.events, dr, sim.years)
    other_pv = _compute_other_recurring_pv(rent.other_recurring_costs, dr, sim.years, econ)

    if rent.invested_down_payment > 0:
        r_inv = rent.investment_return_rate
        # Future value of the invested down payment, discounted back to today.
        benefit = (
            rent.invested_down_payment
            * ((1 + r_inv) ** sim.years)
            / ((1 + dr) ** sim.years)
        )
    else:
        benefit = 0.0
    invested_dp_benefit_pv = -benefit  # negative = reduces cost

    total_pv = rent_pv + events_pv + other_pv + invested_dp_benefit_pv
    breakdown = {
        "rent_pv": rent_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "invested_dp_benefit_pv": invested_dp_benefit_pv,
    }
    assert set(breakdown.keys()) == RENT_BREAKDOWN_KEYS
    return OptionResult(total_pv=total_pv, breakdown=breakdown)


def _compute_income_trajectory(income: IncomeParams, years: int) -> List[float]:
    """
    Year-by-year income. Pay-drop events apply at their year and persist
    (the cut is permanent: income compounds from the post-drop level).
    """
    trajectory: List[float] = []
    current = income.annual_income
    for t in range(years):
        year = t + 1
        for event in income.pay_drop_events:
            if event.year == year:
                current *= event.magnitude
        trajectory.append(current)
        if t < years - 1:
            current *= (1 + income.income_growth_rate)
    return trajectory


def _annual_costs_for_option(
    option_type: str,
    params,
    sim: SimulationParams,
    econ: EconomicParams,
) -> List[float]:
    """
    Un-discounted annual housing cost by year, used for affordability ratios.

    Note: these are nominal/undiscounted cash outflows (not PVs); they are
    divided by the year's income to form an affordability ratio.
    """
    # Compute the level mortgage payment once (0 if all_cash or no mortgage block)
    mort_payment = 0.0
    mort_term = 0
    if option_type in ("house", "condo") and not getattr(params, "all_cash", False):
        if (params.down_payment is not None and params.mortgage_rate is not None
                and params.mortgage_term_years is not None):
            from .pv import mortgage_payment as _mortgage_payment
            loan = params.initial_value - params.down_payment
            mort_payment = _mortgage_payment(loan, params.mortgage_rate, params.mortgage_term_years)
            mort_term = params.mortgage_term_years

    # Nominal mode composes inflation into every escalation, exactly as the PV
    # engine does (readiness plan D.6 — `econ` was accepted and ignored here,
    # so nominal-mode ratios silently omitted inflation).
    def _g(rate: float) -> float:
        return _effective_growth_rate(rate, econ)

    costs: List[float] = []
    for t in range(sim.years):
        year = t + 1
        mort_t = mort_payment if year <= mort_term else 0.0
        ev_cost = sum(
            ev.base_cost for ev in params.events
            if _event_year_deterministic(ev, sim.years) == year
        )
        other_cost = sum(
            c.annual_amount * ((1 + _g(c.escalation_rate)) ** t)
            for c in params.other_recurring_costs
        )
        if option_type == "condo":
            base = params.monthly_fee * 12 * ((1 + _g(params.fee_escalation_rate)) ** t)
            costs.append(base + ev_cost + other_cost + mort_t)
        elif option_type == "house":
            house_val = params.initial_value * ((1 + _g(params.value_growth_rate)) ** t)
            maint_rate = _maintenance_rate_for_year(params, year)
            costs.append(house_val * maint_rate + ev_cost + other_cost + mort_t)
        elif option_type == "rent":
            base = params.monthly_rent * 12 * ((1 + _g(params.rent_escalation_rate)) ** t)
            costs.append(base + ev_cost + other_cost)
    return costs


def _compute_affordability_report(
    income: IncomeParams,
    spec: ComparisonSpec,
) -> AffordabilityReport:
    """
    Build the deterministic affordability report: an income trajectory plus,
    for each present option, the per-year cost/income ratio and the list of
    years where that ratio exceeds the affordability threshold.
    """
    incomes = _compute_income_trajectory(income, spec.simulation.years)
    threshold = income.affordability_threshold

    def ratios_and_exceeds(option_type, params):
        if params is None:
            return None, []
        costs = _annual_costs_for_option(
            option_type, params, spec.simulation, spec.economic
        )
        ratios = [
            c / inc if inc > 0 else float("inf")
            for c, inc in zip(costs, incomes)
        ]
        exceeds = [t + 1 for t, r in enumerate(ratios) if r > threshold]
        return ratios, exceeds

    rent_ratios, years_rent = ratios_and_exceeds("rent", spec.rent)
    condo_ratios, years_condo = ratios_and_exceeds("condo", spec.condo)
    house_ratios, years_house = ratios_and_exceeds("house", spec.house)

    return AffordabilityReport(
        annual_incomes=incomes,
        threshold=threshold,
        rent_ratios=rent_ratios,
        condo_ratios=condo_ratios,
        house_ratios=house_ratios,
        years_rent_exceeds=years_rent,
        years_condo_exceeds=years_condo,
        years_house_exceeds=years_house,
    )


def compute_deterministic(spec: ComparisonSpec) -> ComparisonDeterministicResult:
    """
    Run deterministic PV analysis for all options present in the spec.

    Computes a per-option OptionResult (with PV breakdown) for each of condo,
    house, and rent that is present in the spec, plus an affordability report
    if income parameters are provided.

    Args:
        spec: ComparisonSpec bundling simulation/economic params and the
              optional condo/house/rent/income parameter sets.

    Returns:
        ComparisonDeterministicResult with per-option results and an optional
        affordability report.

    Note:
        This function has no side effects and does not print anything.
        Use reporting helpers to generate human-readable output.
    """
    condo_result = (
        _compute_condo_option(spec.condo, spec.simulation, spec.economic)
        if spec.condo is not None
        else None
    )
    house_result = (
        _compute_house_option(spec.house, spec.simulation, spec.economic)
        if spec.house is not None
        else None
    )
    rent_result = (
        _compute_rent_option(spec.rent, spec.simulation, spec.economic)
        if spec.rent is not None
        else None
    )

    income_report = None
    if spec.income is not None:
        income_report = _compute_affordability_report(spec.income, spec)

    # S4b: a loaded ScenarioPrior stamps its identity on the result payload and
    # is REAL-terms only — same law as the MC engine (refusal before any math).
    provenance = None
    if spec.market_scenario is not None:
        from .monte_carlo import _require_real_mode, _load_prior_if_any
        _require_real_mode(spec)
        provenance = _load_prior_if_any(spec).provenance_block()

    return ComparisonDeterministicResult(
        condo=condo_result,
        house=house_result,
        rent=rent_result,
        income_report=income_report,
        market_scenario=provenance,
    )
