"""
Configuration loading and validation for the cost analysis engine.

This module handles loading YAML configuration files and converting
them into the appropriate dataclass instances.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import difflib

import yaml

import datetime

from .anchors import ANCHORS
from .market_scenario import LoadedScenarioPrior, time_anchor_violations
from .models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    ComparisonSpec,
    PayDropEvent,
    RentParams,
    IncomeParams,
    MarketScenario,
    PriceShockParams,
)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


# ---------------------------------------------------------------------------
# Known-key schema (audit F1: unknown-key rejection)
#
# Every accepted config key is declared here. A key outside these sets is a
# typo; the per-section parsers would otherwise silently ignore it, so both
# loaders diff the provided keys against this schema and refuse loudly with a
# did-you-mean suggestion.
# ---------------------------------------------------------------------------

_TOP_LEVEL_KEYS = frozenset({
    "years", "discount_rate", "condo", "house", "rent", "income",
    "simulation", "economic", "market_scenario",
})
# Legacy/alias top-level names → the section that replaced them. There is no
# top-level monte_carlo section (and never was in this engine); a config that
# declares one almost certainly means 'simulation'.
_TOP_LEVEL_HINTS = {"monte_carlo": "simulation"}

_CONDO_KEYS = frozenset({
    "monthly_fee", "fee_escalation_rate", "events", "other_recurring_costs",
    "reserve_contribution_rate", "reserve_initial_balance",
    "reserve_growth_rate", "initial_value", "value_growth_rate",
    "down_payment", "mortgage_rate", "mortgage_term_years", "all_cash",
    "selling_cost_rate", "price_shock",
})
_HOUSE_KEYS = frozenset({
    "initial_value", "value_growth_rate", "annual_maintenance_rate", "events",
    "other_recurring_costs", "maintenance_curve", "down_payment",
    "mortgage_rate", "mortgage_term_years", "all_cash", "selling_cost_rate",
    "price_shock",
})
_RENT_KEYS = frozenset({
    "monthly_rent", "rent_escalation_rate", "invested_down_payment",
    "investment_return_rate", "events", "other_recurring_costs",
})
_ECONOMIC_KEYS = frozenset({"mode", "inflation_rate", "inflation_vol"})
_INCOME_KEYS = frozenset({
    "annual_income", "income_growth_rate", "affordability_threshold",
    "pay_drop_events",
})
_SIMULATION_KEYS = frozenset({
    "num_sims", "random_seed", "house_maintenance_vol", "condo_fee_vol",
    "other_cost_vol", "corr_inflation_house", "corr_inflation_condo",
    "corr_inflation_other", "corr_inflation_event_cost", "shock_model",
    "rent_escalation_vol", "investment_return_vol",
})
_MARKET_SCENARIO_KEYS = frozenset({"path", "geography"})
_PRICE_SHOCK_KEYS = frozenset({"annual_hazard", "severity_mean", "severity_vol"})
_EVENT_KEYS = frozenset({
    "name", "base_cost", "expected_year", "timing_std_years", "min_year",
    "max_year", "cost_vol", "timing_model", "hazard_base", "hazard_growth",
    "hazard_start_year", "cost_distribution",
})
_RECURRING_COST_KEYS = frozenset({"name", "annual_amount", "escalation_rate"})
_PAY_DROP_EVENT_KEYS = frozenset({
    "year", "magnitude", "year_jitter_std", "magnitude_vol",
})
_MAINTENANCE_CURVE_KEYS = frozenset({"year", "rate"})

_SECTION_KEYS: Dict[str, frozenset] = {
    "condo": _CONDO_KEYS,
    "house": _HOUSE_KEYS,
    "rent": _RENT_KEYS,
    "economic": _ECONOMIC_KEYS,
    "income": _INCOME_KEYS,
    "simulation": _SIMULATION_KEYS,
    "market_scenario": _MARKET_SCENARIO_KEYS,
}


def _unknown_key_message(dotted: str, key: str, known: frozenset) -> str:
    close = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.6)
    message = f"unknown key '{dotted}'"
    if close:
        message += f" — did you mean '{close[0]}'?"
    return message


def _reject_unknown_keys(data: Dict[str, Any]) -> None:
    """
    Refuse unknown config keys with a did-you-mean suggestion.

    Checked on the parsed YAML mapping, before section parsing — a typo'd key
    (e.g. ``fee_escalation_ratte``) would otherwise be silently dropped by the
    per-section ``dict.get`` parsers.
    """
    problems: List[str] = []

    for key in data:
        if key in _TOP_LEVEL_KEYS:
            continue
        if key in _TOP_LEVEL_HINTS:
            problems.append(
                f"unknown key '{key}' — did you mean '{_TOP_LEVEL_HINTS[key]}'?"
            )
        else:
            problems.append(_unknown_key_message(key, key, _TOP_LEVEL_KEYS))

    for section, known in _SECTION_KEYS.items():
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for key in block:
            if key not in known:
                problems.append(_unknown_key_message(f"{section}.{key}", key, known))

        # Nested price_shock block (condo / house option blocks).
        shock = block.get("price_shock")
        if isinstance(shock, dict):
            for key in shock:
                if key not in _PRICE_SHOCK_KEYS:
                    problems.append(
                        _unknown_key_message(f"{section}.price_shock.{key}", key, _PRICE_SHOCK_KEYS)
                    )

        # List-entry sections: events / other_recurring_costs (condo, house, rent),
        # house.maintenance_curve, income.pay_drop_events.
        entry_schemas = [
            ("events", _EVENT_KEYS),
            ("other_recurring_costs", _RECURRING_COST_KEYS),
        ]
        if section == "house":
            entry_schemas.append(("maintenance_curve", _MAINTENANCE_CURVE_KEYS))
        if section == "income":
            entry_schemas.append(("pay_drop_events", _PAY_DROP_EVENT_KEYS))
        for list_key, entry_known in entry_schemas:
            entries = block.get(list_key)
            if not isinstance(entries, list):
                continue
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                for key in entry:
                    if key not in entry_known:
                        problems.append(
                            _unknown_key_message(
                                f"{section}.{list_key}[{i}].{key}", key, entry_known
                            )
                        )

    if problems:
        raise ConfigValidationError("\n".join(problems))


# ---------------------------------------------------------------------------
# Assumption provenance (audit U1)
#
# The subset of assumption-relevant keys the echo block surfaces. 'defaults
# applied' lists any of these that the user YAML did not provide — the values
# the engine silently filled in. economic defaults apply even when the section
# is absent; option sections only count when the section itself is present.
# ---------------------------------------------------------------------------

_ASSUMPTION_KEYS: Dict[str, tuple] = {
    "economic": ("mode", "inflation_rate"),
    "condo": ("fee_escalation_rate", "value_growth_rate", "selling_cost_rate"),
    "house": ("value_growth_rate", "selling_cost_rate"),
    "rent": ("rent_escalation_rate", "invested_down_payment", "investment_return_rate"),
    "income": ("income_growth_rate", "affordability_threshold"),
}


def _defaults_applied(data: Dict[str, Any]) -> List[str]:
    """Dotted names of assumption keys whose values came from defaults."""
    applied: List[str] = []
    for section, keys in _ASSUMPTION_KEYS.items():
        block = data.get(section)
        for key in keys:
            if section == "economic" or isinstance(block, dict):
                if not isinstance(block, dict) or key not in block:
                    applied.append(f"{section}.{key}")
    return applied


def coherence_warnings(spec: ComparisonSpec) -> List[str]:
    """
    Coherence warnings (audit U2): assumptions that parse fine but smell wrong.

    Pure function of the spec; callers surface these (CLI stderr '[warning]',
    MCP response 'warnings' list) and NEVER refuse — these are judgment calls
    the operator may well have made deliberately.
    """
    warns: List[str] = []
    econ = spec.economic
    sim = spec.simulation

    if econ.mode == "real" and econ.inflation_rate > 0:
        warns.append(
            f"economic.inflation_rate={econ.inflation_rate:.1%} is set but "
            f"ignored in real mode (mode='real')"
        )

    if spec.rent is not None and "rent.rent_escalation_rate" in spec.defaults_applied:
        warns.append(
            f"rent.rent_escalation_rate defaulted to "
            f"{spec.rent.rent_escalation_rate:.1%} real (FP Canada 2026 "
            f"shelter-cost growth; QC continuing leases ≈ CPI ⇒ 0.0% real) "
            f"— set explicitly for your market view"
        )

    if econ.mode == "nominal" and econ.inflation_rate == 0:
        warns.append(
            "nominal mode with inflation_rate=0 — FP Canada 2026 long-term "
            "inflation assumption is 2.1%"
        )

    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None:
            continue
        if econ.mode == "real" and opt.value_growth_rate >= 0.04:
            warns.append(
                f"{name}.value_growth_rate={opt.value_growth_rate:.1%} in real "
                f"mode looks like a nominal quote"
            )
        if 0 < opt.initial_value < 10_000:
            warns.append(
                f"{name}.initial_value=${opt.initial_value:,.0f} — units? "
                f"dollars expected"
            )

    if not 0 <= sim.discount_rate <= 0.15:
        warns.append(
            f"discount_rate={sim.discount_rate:.1%} outside [0, 15%] — "
            f"double-check units/decimals"
        )

    if spec.rent is not None and spec.rent.monthly_rent > 20_000:
        warns.append(
            f"rent.monthly_rent=${spec.rent.monthly_rent:,.0f}/mo above "
            f"$20,000 — units? dollars expected"
        )

    if sim.years < 5:
        warns.append(
            f"years={sim.years} < 5 — selling costs dominate short horizons"
        )

    # An all-cash purchase puts the WHOLE price down — the case with the most
    # unmodeled renter capital (readiness plan B.5; the old sum read
    # down_payment, which is None for all_cash, so the warning never fired).
    owned_down = sum(
        (o.initial_value if o.all_cash else (o.down_payment or 0.0))
        for o in (spec.condo, spec.house) if o is not None
    )
    if (
        owned_down > 0
        and spec.rent is not None
        and spec.rent.invested_down_payment == 0
    ):
        warns.append(
            f"owned options put ${owned_down:,.0f} down but "
            f"rent.invested_down_payment=0 — renter capital unmodeled, "
            f"verdict not like-for-like"
        )

    return warns


def all_warnings(
    spec: ComparisonSpec,
    prior: Optional[LoadedScenarioPrior] = None,
    current_year: Optional[int] = None,
) -> List[str]:
    """
    Every warning a surface should show for one run: the coherence warnings
    plus, when a demographic prior is loaded, the time-anchor violations
    (wall clock past START_CALENDAR_YEAR). ONE assembly for the CLI's stderr,
    the CLI's --json `warnings`, and the MCP response, so no surface can drop
    a class of warning the others carry (readiness plan A.2). `current_year`
    is injectable for tests; the wall clock is read only here at the edge.
    """
    warns = coherence_warnings(spec)
    if prior is not None:
        if current_year is None:
            current_year = datetime.date.today().year
        raw = prior.data_vintage.get("constants_as_of")
        warns = warns + time_anchor_violations(
            current_year, raw if isinstance(raw, str) else None)
    return warns


def single_path_run(spec: ComparisonSpec) -> bool:
    """
    True when every uncertainty input is off (audit U3): a Monte Carlo run
    would produce num_sims identical paths. Callers must then skip the
    uncertainty act like the no-MC path and stamp the run 'not a forecast'.
    """
    sim = spec.simulation
    vols = (
        sim.house_maintenance_vol,
        sim.condo_fee_vol,
        sim.other_cost_vol,
        sim.rent_escalation_vol,
        sim.investment_return_vol,
        spec.economic.inflation_vol,
    )
    if any(v != 0 for v in vols):
        return False
    if spec.market_scenario is not None:
        return False  # prior draws demographic drift per path
    for opt in (spec.condo, spec.house, spec.rent):
        if opt is None:
            continue
        shock = getattr(opt, "price_shock", None)
        if shock is not None and shock.annual_hazard > 0:
            return False
        for event in opt.events:
            if event.timing_std_years != 0 or event.cost_vol != 0:
                return False
            if event.timing_model == "hazard" and (
                event.hazard_base != 0 or event.hazard_growth != 0
            ):
                return False
    if spec.income is not None:
        for drop in spec.income.pay_drop_events:
            if drop.year_jitter_std != 0 or drop.magnitude_vol != 0:
                return False
    return True


def _parse_bool(value: Any, field_name: str) -> bool:
    """
    Strictly parse a boolean config value.

    Accepts real booleans, and the exact strings "true"/"false" (any case) for
    YAML round-trip tolerance. Everything else raises — notably guarding the
    ``bool("false") is True`` trap where any non-empty string coerces to True.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise ConfigValidationError(
        f"{field_name} must be a boolean (true/false), got {value!r}"
    )


def _parse_event(event_data: Dict[str, Any], years: int) -> EventConfig:
    """
    Parse an event configuration from YAML data.
    
    Args:
        event_data: Dictionary with event fields
        years: Analysis horizon (for validation)
    
    Returns:
        EventConfig instance
    
    Raises:
        ConfigValidationError: If required fields are missing or invalid
    """
    required = ["name", "base_cost", "expected_year"]
    for field in required:
        if field not in event_data:
            raise ConfigValidationError(f"Event missing required field: {field}")
    
    expected_year = event_data["expected_year"]
    if expected_year < 1:
        raise ConfigValidationError(
            f"Event '{event_data['name']}' has expected_year < 1: {expected_year}"
        )
    
    timing_model = str(event_data.get("timing_model", "jitter")).lower()
    if timing_model not in ("jitter", "hazard"):
        raise ConfigValidationError(f"Invalid timing_model for event '{event_data['name']}': {timing_model}")
    
    cost_distribution = str(event_data.get("cost_distribution", "lognormal")).lower()
    if cost_distribution not in ("normal", "lognormal"):
        raise ConfigValidationError(
            f"Invalid cost_distribution for event '{event_data['name']}': {cost_distribution}"
        )
    
    return EventConfig(
        name=str(event_data["name"]),
        base_cost=float(event_data["base_cost"]),
        expected_year=int(expected_year),
        timing_std_years=float(event_data.get("timing_std_years", 0.0)),
        min_year=int(event_data.get("min_year", 1)),
        max_year=int(event_data["max_year"]) if event_data.get("max_year") is not None else None,
        cost_vol=float(event_data.get("cost_vol", 0.0)),
        timing_model=timing_model,  # type: ignore
        hazard_base=float(event_data.get("hazard_base", 0.0)),
        hazard_growth=float(event_data.get("hazard_growth", 0.0)),
        hazard_start_year=int(event_data.get("hazard_start_year", 1)),
        cost_distribution=cost_distribution,  # type: ignore
    )


def _parse_recurring_cost(cost_data: Dict[str, Any]) -> RecurringOtherCost:
    """
    Parse a recurring other cost from YAML data.
    
    Args:
        cost_data: Dictionary with cost fields
    
    Returns:
        RecurringOtherCost instance
    
    Raises:
        ConfigValidationError: If required fields are missing
    """
    required = ["name", "annual_amount"]
    for field in required:
        if field not in cost_data:
            raise ConfigValidationError(f"Recurring cost missing required field: {field}")
    
    return RecurringOtherCost(
        name=str(cost_data["name"]),
        annual_amount=float(cost_data["annual_amount"]),
        escalation_rate=float(cost_data.get("escalation_rate", 0.0)),
    )


def _parse_pay_drop_event(data: Dict[str, Any]) -> PayDropEvent:
    """Parse a PayDropEvent from YAML data."""
    if "year" not in data:
        raise ConfigValidationError("pay_drop_event missing required field: year")
    if "magnitude" not in data:
        raise ConfigValidationError("pay_drop_event missing required field: magnitude")
    return PayDropEvent(
        year=int(data["year"]),
        magnitude=float(data["magnitude"]),
        year_jitter_std=float(data.get("year_jitter_std", 0.0)),
        magnitude_vol=float(data.get("magnitude_vol", 0.0)),
    )


def _parse_price_shock(data: Dict[str, Any], label: str) -> PriceShockParams:
    """Parse a price_shock block (S4b Slot 3) from YAML data."""
    if not isinstance(data, dict):
        raise ConfigValidationError(f"{label}.price_shock must be a mapping")
    return PriceShockParams(
        annual_hazard=float(data.get("annual_hazard", 0.0)),
        severity_mean=float(data.get("severity_mean", ANCHORS["price_shock.severity_mean"].value)),
        severity_vol=float(data.get("severity_vol", ANCHORS["price_shock.severity_vol"].value)),
    )


def _parse_market_scenario(data: Dict[str, Any]) -> MarketScenario:
    """Parse the market_scenario block (S4b Slot 1) from YAML data."""
    if not isinstance(data, dict):
        raise ConfigValidationError("market_scenario must be a mapping with 'path' and 'geography'")
    for field in ("path", "geography"):
        if field not in data:
            raise ConfigValidationError(f"market_scenario missing required field: {field}")
        if not isinstance(data[field], str) or not data[field]:
            raise ConfigValidationError(f"market_scenario.{field} must be a non-empty string")
    return MarketScenario(path=data["path"], geography=data["geography"])


def _parse_condo(condo_data: Dict[str, Any], years: int) -> CondoParams:
    """
    Parse condo parameters from YAML data.
    """
    if "monthly_fee" not in condo_data:
        raise ConfigValidationError("Condo section missing required field: monthly_fee")
    
    events = [
        _parse_event(e, years) 
        for e in condo_data.get("events", [])
    ]
    
    other_costs = [
        _parse_recurring_cost(c) 
        for c in condo_data.get("other_recurring_costs", [])
    ]
    
    return CondoParams(
        monthly_fee=float(condo_data["monthly_fee"]),
        fee_escalation_rate=float(condo_data.get("fee_escalation_rate", 0.0)),
        events=events,
        other_recurring_costs=other_costs,
        reserve_contribution_rate=float(condo_data.get("reserve_contribution_rate", 0.0)),
        reserve_initial_balance=float(condo_data.get("reserve_initial_balance", 0.0)),
        reserve_growth_rate=float(condo_data.get("reserve_growth_rate", 0.0)),
        initial_value=float(condo_data.get("initial_value", 0.0)),
        value_growth_rate=float(condo_data.get("value_growth_rate", 0.0)),
        down_payment=(None if "down_payment" not in condo_data else float(condo_data["down_payment"])),
        mortgage_rate=(None if "mortgage_rate" not in condo_data else float(condo_data["mortgage_rate"])),
        mortgage_term_years=(None if "mortgage_term_years" not in condo_data else int(condo_data["mortgage_term_years"])),
        all_cash=_parse_bool(condo_data.get("all_cash", False), "condo.all_cash"),
        # WOWA 2026: seller-side commissions ≈ 4–5% + notary ⇒ 5% all-in
        selling_cost_rate=float(condo_data.get("selling_cost_rate", ANCHORS["condo.house.selling_cost_rate"].value)),
        price_shock=(
            _parse_price_shock(condo_data["price_shock"], "condo")
            if "price_shock" in condo_data else None
        ),
    )


def _parse_house(house_data: Dict[str, Any], years: int) -> HouseParams:
    """
    Parse house parameters from YAML data.
    """
    if "initial_value" not in house_data:
        raise ConfigValidationError("House section missing required field: initial_value")
    
    events = [
        _parse_event(e, years) 
        for e in house_data.get("events", [])
    ]
    
    other_costs = [
        _parse_recurring_cost(c) 
        for c in house_data.get("other_recurring_costs", [])
    ]
    
    maintenance_curve_raw = house_data.get("maintenance_curve", [])
    maintenance_curve = []
    for point in maintenance_curve_raw:
        if "year" not in point or "rate" not in point:
            raise ConfigValidationError("maintenance_curve entries must have 'year' and 'rate'")
        maintenance_curve.append((int(point["year"]), float(point["rate"])))
    maintenance_curve.sort(key=lambda x: x[0])
    
    return HouseParams(
        initial_value=float(house_data["initial_value"]),
        value_growth_rate=float(house_data.get("value_growth_rate", 0.0)),
        annual_maintenance_rate=float(house_data.get("annual_maintenance_rate", 0.0)),
        events=events,
        other_recurring_costs=other_costs,
        maintenance_curve=maintenance_curve,
        down_payment=(None if "down_payment" not in house_data else float(house_data["down_payment"])),
        mortgage_rate=(None if "mortgage_rate" not in house_data else float(house_data["mortgage_rate"])),
        mortgage_term_years=(None if "mortgage_term_years" not in house_data else int(house_data["mortgage_term_years"])),
        all_cash=_parse_bool(house_data.get("all_cash", False), "house.all_cash"),
        # WOWA 2026: seller-side commissions ≈ 4–5% + notary ⇒ 5% all-in
        selling_cost_rate=float(house_data.get("selling_cost_rate", ANCHORS["condo.house.selling_cost_rate"].value)),
        price_shock=(
            _parse_price_shock(house_data["price_shock"], "house")
            if "price_shock" in house_data else None
        ),
    )


def _parse_rent(data: Dict[str, Any], years: int) -> RentParams:
    """Parse RentParams from YAML data."""
    if "monthly_rent" not in data:
        raise ConfigValidationError("rent section missing required field: monthly_rent")
    events = [_parse_event(e, years) for e in data.get("events", [])]
    other = [_parse_recurring_cost(c) for c in data.get("other_recurring_costs", [])]
    return RentParams(
        monthly_rent=float(data["monthly_rent"]),
        # FP Canada 2026 PAG shelter-cost growth 3.1% − 2.1% = 1.0% real
        rent_escalation_rate=float(data.get("rent_escalation_rate", ANCHORS["rent.rent_escalation_rate"].value)),
        invested_down_payment=float(data.get("invested_down_payment", 0.0)),
        # FP Canada 2026 PAG 60/40 ≈ 3.0% real
        investment_return_rate=float(data.get("investment_return_rate", ANCHORS["rent.investment_return_rate"].value)),
        events=events,
        other_recurring_costs=other,
    )


def _parse_income(data: Dict[str, Any]) -> IncomeParams:
    """Parse IncomeParams from YAML data."""
    if "annual_income" not in data:
        raise ConfigValidationError("income section missing required field: annual_income")
    events = [_parse_pay_drop_event(e) for e in data.get("pay_drop_events", [])]
    return IncomeParams(
        annual_income=float(data["annual_income"]),
        # FP Canada 2026 PAG salary growth 3.1% − 2.1% = 1.0% real
        income_growth_rate=float(data.get("income_growth_rate", ANCHORS["income.income_growth_rate"].value)),
        # Legacy GDS 32% guideline (below CMHC's 39% cap; broader-than-PITH numerator)
        affordability_threshold=float(data.get("affordability_threshold", ANCHORS["income.affordability_threshold"].value)),
        pay_drop_events=events,
    )


def _parse_simulation(sim_data: Optional[Dict[str, Any]], years: int, discount_rate: float) -> SimulationParams:
    """
    Parse simulation parameters from YAML data.
    
    Uses top-level years and discount_rate, with optional overrides from simulation section.
    """
    if sim_data is None:
        sim_data = {}
    shock_model = str(sim_data.get("shock_model", "lognormal")).lower()
    
    return SimulationParams(
        years=years,
        discount_rate=discount_rate,
        num_sims=int(sim_data.get("num_sims", 10_000)),
        random_seed=int(sim_data.get("random_seed", 42)),
        house_maintenance_vol=float(sim_data.get("house_maintenance_vol", 0.0)),
        condo_fee_vol=float(sim_data.get("condo_fee_vol", 0.0)),
        other_cost_vol=float(sim_data.get("other_cost_vol", 0.0)),
        corr_inflation_house=float(sim_data.get("corr_inflation_house", 0.0)),
        corr_inflation_condo=float(sim_data.get("corr_inflation_condo", 0.0)),
        corr_inflation_other=float(sim_data.get("corr_inflation_other", 0.0)),
        corr_inflation_event_cost=float(sim_data.get("corr_inflation_event_cost", 0.0)),
        shock_model=shock_model,  # type: ignore
        rent_escalation_vol=float(sim_data.get("rent_escalation_vol", 0.0)),
        investment_return_vol=float(sim_data.get("investment_return_vol", 0.0)),
    )


def _parse_economic(econ_data: Optional[Dict[str, Any]]) -> EconomicParams:
    """
    Parse economic parameters from YAML data.
    """
    if econ_data is None:
        return EconomicParams()
    
    mode = econ_data.get("mode", "real")
    if mode not in ("nominal", "real"):
        raise ConfigValidationError(f"Invalid economic mode: {mode}. Must be 'nominal' or 'real'.")
    
    return EconomicParams(
        mode=mode,  # type: ignore
        inflation_rate=float(econ_data.get("inflation_rate", 0.0)),
        inflation_vol=float(econ_data.get("inflation_vol", 0.0)),
    )


def validate_config(spec: ComparisonSpec) -> List[str]:
    """
    Validate configuration parameters.

    Returns a list of warning/error messages. Empty list means valid.
    """
    warnings = []

    # At least one housing/rent option must be provided
    if spec.condo is None and spec.house is None and spec.rent is None:
        warnings.append("At least one of condo, house, or rent must be defined")

    sim = spec.simulation
    econ = spec.economic

    if sim.years < 1:
        warnings.append(f"years must be >= 1, got {sim.years}")

    if sim.discount_rate < 0:
        warnings.append(f"discount_rate should be >= 0, got {sim.discount_rate}")

    if sim.num_sims < 1:
        warnings.append(f"num_sims must be >= 1, got {sim.num_sims}")

    if sim.other_cost_vol < 0:
        warnings.append(f"other_cost_vol should be >= 0, got {sim.other_cost_vol}")

    for name, rho in [
        ("corr_inflation_house", sim.corr_inflation_house),
        ("corr_inflation_condo", sim.corr_inflation_condo),
        ("corr_inflation_other", sim.corr_inflation_other),
        ("corr_inflation_event_cost", sim.corr_inflation_event_cost),
    ]:
        if rho < -1 or rho > 1:
            warnings.append(f"{name} should be between -1 and 1, got {rho}")

    if sim.shock_model not in ("lognormal", "normal"):
        warnings.append(f"shock_model must be 'lognormal' or 'normal', got {sim.shock_model}")

    if spec.condo is not None:
        condo = spec.condo
        if condo.monthly_fee < 0:
            warnings.append(f"condo.monthly_fee should be >= 0, got {condo.monthly_fee}")
        if condo.reserve_contribution_rate < 0:
            warnings.append(f"condo.reserve_contribution_rate should be >= 0, got {condo.reserve_contribution_rate}")
        if condo.reserve_initial_balance < 0:
            warnings.append(f"condo.reserve_initial_balance should be >= 0, got {condo.reserve_initial_balance}")
        if condo.reserve_growth_rate < -1:
            warnings.append(f"condo.reserve_growth_rate should be > -1, got {condo.reserve_growth_rate}")
        if condo.value_growth_rate <= -1:
            warnings.append(f"condo.value_growth_rate must be > -1 (> -100%), got {condo.value_growth_rate}")

    if spec.house is not None:
        house = spec.house
        if house.initial_value < 0:
            warnings.append(f"house.initial_value should be >= 0, got {house.initial_value}")

        if house.value_growth_rate <= -1:
            warnings.append(f"house.value_growth_rate must be > -1 (> -100%), got {house.value_growth_rate}")

        if house.annual_maintenance_rate < 0 or house.annual_maintenance_rate > 1:
            warnings.append(
                f"house.annual_maintenance_rate should be in [0, 1], got {house.annual_maintenance_rate}"
            )
        for year, rate in house.maintenance_curve:
            if year < 1:
                warnings.append(f"maintenance_curve year must be >=1, got {year}")
            if rate < 0 or rate > 1:
                warnings.append(f"maintenance_curve rate should be in [0,1], got {rate}")

    # Validate events from whichever options are present
    condo_events = spec.condo.events if spec.condo is not None else []
    house_events = spec.house.events if spec.house is not None else []
    rent_events = spec.rent.events if spec.rent is not None else []
    for event in condo_events + house_events + rent_events:
        if event.expected_year > sim.years:
            warnings.append(
                f"Event '{event.name}' has expected_year ({event.expected_year}) > years ({sim.years})"
            )
        if event.base_cost < 0:
            warnings.append(f"Event '{event.name}' has negative base_cost: {event.base_cost}")
        if event.hazard_base < 0 or event.hazard_base > 1:
            warnings.append(f"Event '{event.name}' hazard_base should be in [0,1], got {event.hazard_base}")
        if event.hazard_growth < 0:
            warnings.append(f"Event '{event.name}' hazard_growth should be >=0, got {event.hazard_growth}")
        if event.hazard_start_year < 1:
            warnings.append(f"Event '{event.name}' hazard_start_year must be >=1, got {event.hazard_start_year}")
        if event.cost_distribution not in ("normal", "lognormal"):
            warnings.append(
                f"Event '{event.name}' cost_distribution must be 'normal' or 'lognormal', got {event.cost_distribution}"
            )

    if spec.rent is not None:
        rent = spec.rent
        if rent.monthly_rent <= 0:
            warnings.append(f"rent.monthly_rent must be positive, got {rent.monthly_rent}")
        if not (0 <= rent.rent_escalation_rate < 0.20):
            warnings.append(f"rent.rent_escalation_rate must be between 0 and 0.20 (inclusive), got {rent.rent_escalation_rate}")
        if rent.invested_down_payment < 0:
            warnings.append(f"rent.invested_down_payment must be non-negative, got {rent.invested_down_payment}")
        if not (0 <= rent.investment_return_rate < 0.25):
            warnings.append(f"rent.investment_return_rate must be between 0 and 0.25 (inclusive), got {rent.investment_return_rate}")

    if spec.income is not None:
        income = spec.income
        if income.annual_income <= 0:
            warnings.append(f"income.annual_income must be positive, got {income.annual_income}")
        if not (0 < income.affordability_threshold < 1):
            warnings.append(f"income.affordability_threshold must be between 0 and 1, got {income.affordability_threshold}")
        for event in income.pay_drop_events:
            if not (0 < event.magnitude <= 1):
                warnings.append(f"pay_drop_event year={event.year}: magnitude must be in (0, 1]")

    if econ.inflation_vol < 0:
        warnings.append(f"inflation_vol should be >= 0, got {econ.inflation_vol}")

    if spec.market_scenario is not None:
        ms = spec.market_scenario
        # The prior file itself is validated (fail-loud) at engine entry; here we
        # only check the reference block's own sanity.
        if not ms.path or not ms.geography:
            warnings.append("market_scenario requires non-empty path and geography")

    for name, opt in [("condo", spec.condo), ("house", spec.house)]:
        if opt is None or opt.price_shock is None:
            continue
        ps = opt.price_shock
        if not (0 <= ps.annual_hazard <= 1):
            warnings.append(f"{name}.price_shock.annual_hazard should be in [0, 1], got {ps.annual_hazard}")
        if not (0 <= ps.severity_mean <= 1):
            warnings.append(f"{name}.price_shock.severity_mean should be in [0, 1], got {ps.severity_mean}")
        if ps.severity_vol < 0:
            warnings.append(f"{name}.price_shock.severity_vol should be >= 0, got {ps.severity_vol}")

    def _check_capital_structure(name, opt):
        if opt is None:
            return
        if name == "condo" and (opt.initial_value is None or opt.initial_value <= 0):
            warnings.append(f"{name}: initial_value must be > 0 in the net-wealth model")
        mortgage_fields_set = (
            opt.down_payment is not None
            or opt.mortgage_rate is not None
            or opt.mortgage_term_years is not None
        )
        if opt.all_cash:
            # all_cash XOR mortgage block: a mortgage field alongside all_cash is
            # ambiguous intent and must be rejected, not silently ignored.
            if mortgage_fields_set:
                warnings.append(
                    f"{name}: all_cash: true is set together with mortgage fields "
                    f"(down_payment / mortgage_rate / mortgage_term_years); declare exactly one")
        else:
            if opt.down_payment is None or opt.mortgage_rate is None or opt.mortgage_term_years is None:
                warnings.append(
                    f"{name}: declare all_cash: true OR a mortgage block "
                    f"(down_payment + mortgage_rate + mortgage_term_years)")
            elif not (0 <= opt.down_payment <= opt.initial_value):
                warnings.append(f"{name}: down_payment must be in [0, initial_value]")
            elif opt.mortgage_rate < 0 or opt.mortgage_term_years <= 0:
                warnings.append(f"{name}: mortgage_rate >= 0 and mortgage_term_years > 0 required")
        if not (0 <= opt.selling_cost_rate < 1):
            warnings.append(f"{name}: selling_cost_rate must be in [0, 1)")

    _check_capital_structure("condo", spec.condo)
    _check_capital_structure("house", spec.house)

    return warnings


def load_config(path: str) -> ComparisonSpec:
    """
    Load configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file

    Returns:
        ComparisonSpec populated from the YAML file

    Raises:
        ConfigValidationError: If required fields are missing or invalid
        FileNotFoundError: If the config file doesn't exist
        yaml.YAMLError: If the YAML is malformed

    Example:
        >>> spec = load_config("examples/basic_config.yaml")
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ConfigValidationError("Empty configuration file")

    # Unknown-key diff runs before required-field checks so a typo (e.g.
    # 'yeers') gets a did-you-mean instead of a bare "missing field" refusal.
    _reject_unknown_keys(data)

    # Required top-level fields
    if "years" not in data:
        raise ConfigValidationError("Missing required field: years")
    if "discount_rate" not in data:
        raise ConfigValidationError("Missing required field: discount_rate")

    years = int(data["years"])
    discount_rate = float(data["discount_rate"])

    condo = _parse_condo(data["condo"], years) if "condo" in data else None
    house = _parse_house(data["house"], years) if "house" in data else None
    rent = _parse_rent(data["rent"], years) if "rent" in data else None
    income = _parse_income(data["income"]) if "income" in data else None
    sim = _parse_simulation(data.get("simulation"), years, discount_rate)
    econ = _parse_economic(data.get("economic"))
    market_scenario = (
        _parse_market_scenario(data["market_scenario"]) if "market_scenario" in data else None
    )

    spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house, rent=rent, income=income,
                          market_scenario=market_scenario)
    spec.defaults_applied = _defaults_applied(data)
    warnings = validate_config(spec)
    if warnings:
        raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))

    return spec


def load_config_dict(data: Dict[str, Any]) -> ComparisonSpec:
    """
    Load configuration from a dictionary (useful for programmatic config).

    Args:
        data: Configuration dictionary (same structure as YAML)

    Returns:
        ComparisonSpec populated from the dictionary
    """
    _reject_unknown_keys(data)

    if "years" not in data:
        raise ConfigValidationError("Missing required field: years")
    if "discount_rate" not in data:
        raise ConfigValidationError("Missing required field: discount_rate")

    years = int(data["years"])
    discount_rate = float(data["discount_rate"])

    condo = _parse_condo(data["condo"], years) if "condo" in data else None
    house = _parse_house(data["house"], years) if "house" in data else None
    rent = _parse_rent(data["rent"], years) if "rent" in data else None
    income = _parse_income(data["income"]) if "income" in data else None
    sim = _parse_simulation(data.get("simulation"), years, discount_rate)
    econ = _parse_economic(data.get("economic"))
    market_scenario = (
        _parse_market_scenario(data["market_scenario"]) if "market_scenario" in data else None
    )

    spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house, rent=rent, income=income,
                          market_scenario=market_scenario)
    spec.defaults_applied = _defaults_applied(data)
    warnings = validate_config(spec)
    if warnings:
        raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))

    return spec
