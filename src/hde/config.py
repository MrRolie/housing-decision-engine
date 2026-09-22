"""
Configuration loading and validation for the cost analysis engine.

This module handles loading YAML configuration files and converting
them into the appropriate dataclass instances.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import difflib
import math

import yaml

import datetime

from .anchors import ANCHORS, match_window
from .mortgage_insurance import (
    MortgageInsurance,
    MortgageInsuranceError,
    anchors_used as insurance_anchors_used,
    resolve as resolve_mortgage_insurance,
)
from .land_transfer_tax import (
    LandTransferTax,
    LandTransferTaxError,
    anchors_used as transfer_tax_anchors_used,
    option_province,
    resolve as resolve_land_transfer_tax,
)
from .pv import mortgage_payment
from .market_scenario import LoadedScenarioPrior, time_anchor_violations
from .rates import (
    MortgageCompoundingError,
    RateConventionError,
    RateConverter,
    convention_of,
    converted_for,
    default_inflation_rate,
    deflate,
    effective_mortgage_rate,
    mortgage_compounding_of,
)
from .serialization import (
    cost_family,
    cover_clause,
    default_anchor,
    rate_label,
    real_discount_rate,
    reference_matches,
    school_tax_line,
)
from .sources import build_source_echo, unstated_uncertainty
from .tax_treatment import (
    TaxParams,
    TaxTreatmentError,
    anchors_used as tax_anchors_used,
    derives_renter_capital,
    resolve as resolve_tax,
    tfsa_room_warning,
)
# The direction vocabulary, one home (docs/specs/2026-09-21-unpriced-dimensions.md
# §13): the coherence warnings below FORMAT from these rather than each spelling
# its own. Import-safe — `unpriced` reaches only `anchors` and `rates` at module
# level and loads this module lazily, inside the call.
from .unpriced import NEUTRAL, TOWARD_BUYING, TOWARD_RENTING
from .deterministic import (
    mortgage_leg_pv, renewals_priced_inside, renter_terminal_for,
)
from .models import (
    ComparisonDeterministicResult,
    compute_verdict,
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
    "simulation", "economic", "market_scenario", "province", "sources", "rates", "tax",
})
# Legacy/alias top-level names → the section that replaced them. There is no
# top-level monte_carlo section (and never was in this engine); a config that
# declares one almost certainly means 'simulation'.
_TOP_LEVEL_HINTS = {"monte_carlo": "simulation"}

_CONDO_KEYS = frozenset({
    "monthly_fee", "fee_escalation_rate", "events", "other_recurring_costs",
    "reserve_contribution_rate", "reserve_initial_balance",
    "reserve_growth_rate", "initial_value", "purchase_costs", "purchase_costs_rate",
    "financed_purchase_costs", "value_growth_rate", "property_tax_rate",
    "down_payment", "cash_available", "mortgage_rate", "mortgage_rate_compounding",
    "mortgage_term_years", "mortgage_renewal_years", "mortgage_renewal_rates", "all_cash",
    "selling_cost_rate", "price_shock", "mortgage_insurance", "province",
    "land_transfer_tax", "municipality", "first_time_buyer",
})
_HOUSE_KEYS = frozenset({
    "initial_value", "purchase_costs", "purchase_costs_rate", "financed_purchase_costs",
    "value_growth_rate", "annual_maintenance_rate", "property_tax_rate", "events",
    "other_recurring_costs", "maintenance_curve", "down_payment", "cash_available",
    "mortgage_rate", "mortgage_rate_compounding", "mortgage_term_years",
    "mortgage_renewal_years", "mortgage_renewal_rates", "all_cash",
    "selling_cost_rate",
    "price_shock", "mortgage_insurance", "province",
    "land_transfer_tax", "municipality", "first_time_buyer",
})
_RENT_KEYS = frozenset({
    "monthly_rent", "rent_escalation_rate", "invested_down_payment",
    "investment_return_rate", "events", "other_recurring_costs",
    "reset_hazard", "reset_to_monthly_rent", "reset_market_escalation_rate",
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
    "rent_escalation_vol", "investment_return_vol", "value_growth_vol",
})
_MARKET_SCENARIO_KEYS = frozenset({"path", "geography"})
_PRICE_SHOCK_KEYS = frozenset({"annual_hazard", "severity_mean", "severity_vol"})
# The tax treatment of the two sides' money (2026-09-05; tax_treatment.py).
_TAX_KEYS = frozenset({
    "marginal_rate", "renter_capital", "taxable_return_treatment",
    "retirement_marginal_rate", "fhsa", "hbp_withdrawal",
})
_RENTER_CAPITAL_KEYS = frozenset({"tfsa", "rrsp", "fhsa", "taxable"})
_FHSA_KEYS = frozenset({"balance", "annual_contribution", "years_until_purchase"})
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
    "tax": _TAX_KEYS,
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

        # Nested tax blocks: renter_capital and fhsa (the same pattern).
        if section == "tax":
            for sub, known_sub in (("renter_capital", _RENTER_CAPITAL_KEYS), ("fhsa", _FHSA_KEYS)):
                nested = block.get(sub)
                if isinstance(nested, dict):
                    for key in nested:
                        if key not in known_sub:
                            problems.append(
                                _unknown_key_message(f"tax.{sub}.{key}", key, known_sub)
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
    "house": ("value_growth_rate", "annual_maintenance_rate", "selling_cost_rate"),
    "rent": ("rent_escalation_rate", "invested_down_payment", "investment_return_rate"),
    "income": ("income_growth_rate", "affordability_threshold"),
}


# The words YAML 1.1 reads as booleans, by the boolean they become.
_YAML_BOOL_WORDS = {True: "ON", False: "NO or OFF"}


def _refuse_boolean_jurisdictions(data: Dict[str, Any]) -> None:
    """`province: ON` is what a person writes for Ontario, and YAML reads the
    bare word as the boolean True. Served answers showed the refusal that used
    to follow — "no anchored schedule for province True" — read as a missing
    schedule rather than a quoting problem, so the boolean is refused HERE,
    before any schedule or tax lookup sees it, with the fix spelled out."""
    def check(prefix: str, key: str, value: Any, noun: str, example: str) -> None:
        if isinstance(value, bool):
            raise ConfigValidationError(
                f"{prefix}{key}: {value} is not a {noun} — YAML reads an unquoted "
                f"{_YAML_BOOL_WORDS[value]} as a boolean; quote it: {key}: {example}")

    check("", "province", data.get("province"), "province code", '"ON"')
    for option in ("condo", "house"):
        block = data.get(option)
        if not isinstance(block, dict):
            continue
        check(f"{option}.", "province", block.get("province"), "province code", '"ON"')
        check(f"{option}.", "municipality", block.get("municipality"), "municipality",
              '"montreal" | "toronto"')


def _municipality(data: Dict[str, Any]) -> Optional[str]:
    """The option's stated city, normalised the way the schedules key it."""
    value = data.get("municipality")
    return value.strip().lower() if isinstance(value, str) else None


def _school_tax_cited(spec: ComparisonSpec, option_name: str) -> bool:
    """True when the option's property-tax figure already carries the school
    tax: the read-back cites a municipal + school SUM for one of its lines, or
    a `sources:` declaration names a school_tax anchor for its rate or line."""
    for entry in reference_matches(spec):
        if entry["option"] == option_name and any(
                m["name"].startswith("school_tax.") for m in entry["matches"]):
            return True
    echo = spec.sources
    if echo is not None:
        for e in echo.of_class("anchor"):
            if e.key.startswith(f"{option_name}.") and e.anchor and "school_tax." in e.anchor:
                return True
    return False


def _defaults_applied(data: Dict[str, Any]) -> List[str]:
    """Dotted names of assumption keys whose values came from defaults."""
    applied: List[str] = []
    if "discount_rate" not in data:
        applied.append("simulation.discount_rate")
    for section, keys in _ASSUMPTION_KEYS.items():
        block = data.get(section)
        for key in keys:
            if section == "economic" or isinstance(block, dict):
                if not isinstance(block, dict) or key not in block:
                    applied.append(f"{section}.{key}")
        # Nested price-shock hyperparameters (S4b slot 3): defaulted only when
        # a price_shock block exists but omits the sub-key — the TREB-anchored
        # severity is then applied and must be echoed like any other default.
        if section in ("condo", "house") and isinstance(block, dict):
            shock = block.get("price_shock")
            if isinstance(shock, dict):
                for sub in ("severity_mean", "severity_vol"):
                    if sub not in shock:
                        applied.append(f"{section}.price_shock.{sub}")
        # The lease reset's MARKET growth rate, same shape: defaulted to the
        # shelter-projection anchor only when the channel is wired. Reporting
        # it on every run without a reset would name a figure nothing reads,
        # and NOT reporting it when the channel is live would leave the user's
        # answer resting on a market growth rate they never saw.
        if section == "rent" and isinstance(block, dict):
            hazard = block.get("reset_hazard")
            if (isinstance(hazard, (int, float)) and not isinstance(hazard, bool)
                    and hazard > 0 and "reset_market_escalation_rate" not in block):
                applied.append("rent.reset_market_escalation_rate")
    # A capital the tax block derived from its shares is neither a default nor
    # a stated value (2026-09-08): the source echo carries it as derived.
    if derives_renter_capital(data) and "rent.invested_down_payment" in applied:
        applied.remove("rent.invested_down_payment")
    return applied


def _rate_gap_clause(r_inv: float, dr: float) -> str:
    """Two rates spelled to the first decimal that tells them APART.

    `rate_label` rounds to one decimal, so 5.200% and 5.163% both render
    "5.2%" — and the capital-term sentence then showed two equal figures and
    named a spread between them (2026-09-21). The default discount rate
    composes to 5.163% in nominal mode, so every household typing a 5.2%
    return landed here. Empty when no precision separates them, which cannot
    happen while a spread of at least fifty cents is being claimed.
    """
    for places in range(3, 10):
        if f"{r_inv:.{places}%}" != f"{dr:.{places}%}":
            return f" (the two round alike: {r_inv:.{places}%} against {dr:.{places}%})"
    return ""


def _capital_leg(pv: float, noun: str, lever: str) -> str:
    """One leg of the renter's tax component with the key that moves IT — the
    taxable share's drag and the FHSA rollover haircut answer to different
    inputs, so a reader who moves the first must not be told the second will
    follow."""
    back = "" if pv > 0 else " credited back, not charged"
    return f"${abs(pv):,.0f} of {noun}{back} (lever: {lever})"


def coherence_warnings(spec: ComparisonSpec, raw: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Coherence warnings (audit U2): assumptions that parse fine but smell wrong.

    Pure function of the spec; callers surface these (CLI stderr '[warning]',
    the --json `warnings` list) and NEVER refuse — these are judgment calls
    the operator may well have made deliberately. `raw` is the YAML mapping the
    spec was loaded from: with it the under-20% warning's price ceiling is
    solved through the loader like the financing line's (2026-09-08); without
    it both hold the seed figure — either way the two lines agree.
    """
    warns: List[str] = []
    econ = spec.economic
    sim = spec.simulation

    # Under the default convention inflation_rate is the DEFLATOR of every
    # typed rate in real mode (rates as quoted, 2026-09-05); only a config that
    # declares its rates real leaves it with nothing to do there.
    if econ.mode == "real" and econ.inflation_rate > 0 and spec.rates == "real":
        warns.append(
            f"economic.inflation_rate={econ.inflation_rate:.1%} is set but "
            f"ignored in real mode (mode='real', rates: real)"
        )

    # A quoted rate below inflation is a negative real rate — legitimate for a
    # flat sticker rent, alarming for the rate the whole comparison discounts
    # at: the future would be worth more than the present.
    typed_dr = next((c for c in spec.converted_rates if c.key == "discount_rate"), None)
    if typed_dr is not None and real_discount_rate(spec) < 0:
        warns.append(
            f"discount_rate {typed_dr.quoted:.1%} as quoted is below {econ.inflation_rate:.1%} "
            f"inflation_rate: {real_discount_rate(spec):.1%} real — the future is valued above "
            f"the present; a real discount rate is usually positive (the anchored default is "
            f"{ANCHORS['simulation.discount_rate'].value:.1%} real)"
        )

    # Real mode prices the mortgage as a level payment at the REAL rate; the
    # lender collects the payment at the quoted NOMINAL rate, which is higher.
    # Round-three evaluation 2026-09-02: two trial runs reported 27.9% / 30.2%
    # against a 32% threshold where the cash ratio was 33.2% / 35.8%.
    if econ.mode == "real" and spec.income is not None:
        for name, opt in (("condo", spec.condo), ("house", spec.house)):
            if opt is None or getattr(opt, "all_cash", False) or opt.mortgage_rate is None:
                continue
            if opt.down_payment is None or opt.mortgage_term_years is None:
                continue
            loan = opt.initial_value - opt.down_payment + opt.financed_purchase_costs
            pay = mortgage_payment(loan, opt.mortgage_rate, opt.mortgage_term_years)
            # With a renewal PRICED inside the horizon the payment steps, so
            # "the level payment" would name a figure the run does not hold: it
            # is the year-1 one. A ladder the horizon never reaches holds one
            # payment like any single-rate mortgage (2026-09-21).
            quoted_payment = ("the year-1 payment"
                              if renewals_priced_inside(opt, spec.simulation.years)
                              else "the level payment")
            warns.append(
                f"affordability: {name} ratios use {quoted_payment} at the REAL mortgage_rate "
                f"{opt.mortgage_rate:.2%} (${pay:,.0f}/yr); the lender collects the payment at the "
                f"quoted NOMINAL rate — higher whenever the rate entered here is a real rate — and can "
                f"breach the threshold where this does not; run mode: nominal with the quoted rate "
                f"(effective annual) for the cash GDS/TDS ratio"
            )

    if spec.rent is not None and "rent.rent_escalation_rate" in spec.defaults_applied:
        warns.append(
            f"rent.rent_escalation_rate defaulted to "
            f"{spec.rent.rent_escalation_rate:.1%} real (FP Canada 2026 "
            f"shelter-cost growth; QC continuing leases ≈ CPI ⇒ 0.0% real) "
            f"— set explicitly for your market view"
        )

    if econ.mode == "nominal" and econ.inflation_rate == 0:
        planning = ANCHORS["economic.inflation_rate.nominal_planning"]
        warns.append(
            f"nominal mode with inflation_rate=0 — {planning.short_cite} long-term "
            f"inflation assumption is {planning.value:.1%}"
        )

    if spec.house is not None and "house.annual_maintenance_rate" in spec.defaults_applied:
        warns.append(
            "house.annual_maintenance_rate defaulted to 0.0% — no maintenance "
            "modelled, which favours the house; NAHB 2019 AHS routine ≈ 0.6% of "
            "value/yr — set it for your property"
        )

    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None:
            continue
        # 4% REAL appreciation is above every long-run Canadian metro average
        # and right where a NOMINAL market quote (~3–5%) lands — a units
        # tripwire, not a plausibility band (the anchor band is -1%..2%). It
        # can only fire on a figure the config DECLARED real: under the default
        # convention a typed 4% is a quote, and the loader has deflated it.
        if econ.mode == "real" and spec.rates == "real" and opt.value_growth_rate >= 0.04:
            warns.append(
                f"{name}.value_growth_rate={opt.value_growth_rate:.1%} in real "
                f"mode looks like a nominal quote"
            )
        if 0 < opt.initial_value < 10_000:
            warns.append(
                f"{name}.initial_value=${opt.initial_value:,.0f} — units? "
                f"dollars expected"
            )

    # 15% is an order of magnitude above any real personal discount rate —
    # a decimal/percent typo tripwire (0.05 vs 5), not a plausibility band.
    # Magnitude only: a quoted rate below inflation deflates to a small
    # negative real rate, which the warning above names.
    if abs(sim.discount_rate) > 0.15:
        warns.append(
            f"discount_rate={sim.discount_rate:.1%} outside [-15%, 15%] — "
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
            f"rent.invested_down_payment=0 — the renter's equivalent capital is assumed to earn "
            f"exactly the discount rate (net present value 0); set invested_down_payment + "
            f"investment_return_rate to model a different return"
        )
    # The other half of that sentence (review F1, 2026-09-02): with capital
    # stated, the verdict-moving residual is D·[1 − ((1+r_inv)/(1+dr))^N] —
    # zero only when the renter earns exactly the discount rate. Say it in dollars.
    # Under a `tax:` block (2026-09-05) the terminal value is the after-tax one
    # the engine credits (`renter_terminal_for`, the one computation every
    # surface reads), and the sentence names the blended rate it implies.
    #
    # WHICH of the two causes fired decides the whole tail (2026-09-21). The
    # guard is a disjunction and one sentence served both branches: a household
    # whose rates were already equal was told to set them equal, on a term that
    # reached 96% of a served verdict's margin. The split is read off the ONE
    # terminal value rather than recomputed — the spread component is the term
    # the renter would carry at an UNTAXED return, and the tax component is the
    # remainder, identically the drag and the rollover haircut the same record
    # already carries. Each state names a lever that moves ITS OWN share.
    if spec.rent is not None and spec.rent.invested_down_payment > 0:
        r_inv = spec.rent.investment_return_rate
        if spec.economic.mode == "nominal":
            r_inv = (1 + r_inv) * (1 + spec.economic.inflation_rate) - 1
        dr, n_years, capital = spec.simulation.discount_rate, spec.simulation.years, spec.rent.invested_down_payment
        terminal = renter_terminal_for(spec)
        taxed = spec.tax is not None and spec.tax.renter_capital is not None
        discounted = (1 + dr) ** n_years
        net = terminal.capital - terminal.value / discounted
        spread = terminal.capital - terminal.untaxed_value / discounted
        tax_pv = net - spread
        legs = [_capital_leg(pv, noun, lever) for pv, noun, lever in (
            (terminal.drag / discounted, "drag on the taxable share", "tax.renter_capital"),
            (terminal.haircut / discounted, "FHSA rollover haircut",
             "tax.retirement_marginal_rate"))
            if abs(pv) >= 0.5]
        # A dollar gate per CAUSE, not a rate one: the sentence claims dollars,
        # and under the as-quoted convention a typed rate deflated to real and
        # recomposed to nominal differs from the figure typed by about 1e-16 —
        # enough to clear a 1e-12 rate test and buy a "net capital term $0"
        # line with a remedy attached. A fully sheltered renter at the discount
        # rate still has nothing to warn on.
        spread_named = abs(spread) >= 0.5
        tax_named = taxed and abs(tax_pv) >= 0.5
        if spread_named or tax_named:
            # The blended rate is what the whole capital earned after every tax
            # the engine applied — the FHSA rollover haircut included, when
            # there is one, and the clause says so.
            rollover = " and the FHSA rollover" if terminal.haircut else ""
            after_tax = (f" (after tax on the taxable share{rollover}: blended {terminal.blended_rate:.2%})"
                         if taxed else "")
            r_txt = rate_label(spec, 'rent.investment_return_rate', r_inv)
            dr_txt = rate_label(spec, 'discount_rate', dr)
            gap = (_rate_gap_clause(r_inv, dr)
                   if spread_named and r_txt == dr_txt else "")
            if abs(net) < 0.5:
                # The two causes all but cancel; naming a side on a sub-dollar
                # net would pick one arbitrarily.
                net_clause = "net capital term under $1 either way"
            else:
                side = "charged to" if net > 0 else "credited to"
                net_clause = f"net capital term ${abs(net):,.0f} {side} the renter"
            if not spread_named:
                # The rates carry none of the term, so the rate remedy is a
                # no-op and the sentence says so: the levers are the ones each
                # leg names.
                tail = ("the rate spread carries none of it, so setting "
                        "investment_return_rate = discount_rate changes nothing here — the "
                        "whole term is the tax the engine charged"
                        + (f": {' and '.join(legs)}" if legs else ""))
            elif not tax_named:
                tail = ("set investment_return_rate = discount_rate for a neutral comparison "
                        "or keep the spread deliberately")
            else:
                tail = (f"two causes, and fixing one moves only its own share: "
                        f"${abs(spread):,.0f} {'charged' if spread > 0 else 'credited'} by the "
                        f"spread between the two rates, which investment_return_rate = "
                        f"discount_rate removes, and ${abs(tax_pv):,.0f} "
                        f"{'charged' if tax_pv > 0 else 'credited'} by the tax the engine "
                        f"applied" + (f" — {' and '.join(legs)}" if legs else ""))
            warns.append(
                f"rent: invested capital ${terminal.capital:,.0f} earns "
                f"{r_txt}{after_tax} vs discount_rate {dr_txt}{gap} — "
                f"{net_clause} over {n_years} years; {tail}"
            )
        # No `tax:` block (2026-09-05): the renter's return is untaxed and the
        # owner's gain is exempt either way, so the omission leans toward
        # renting by the size of the drag — said by the engine, not left to the
        # answer's memory.
        if spec.tax is None:
            warns.append(
                f"rent: invested capital ${capital:,.0f} earns "
                f"{rate_label(spec, 'rent.investment_return_rate', r_inv)} untaxed — no tax: block, "
                f"so tax on the taxable share is not modelled ({TOWARD_RENTING}); state where the "
                f"savings sit (tax.renter_capital)"
            )
        # The tax side of the same money (2026-09-05). Gains are taxed in
        # nominal terms: a real-mode config that declares its rates real leaves
        # inflation_rate at the inert zero, and the drag then falls on the real
        # return alone.
        if (taxed and spec.tax.renter_capital.taxable > 0
                and spec.economic.mode == "real" and spec.economic.inflation_rate == 0):
            warns.append(
                "tax: real mode with inflation_rate=0 — the drag is applied to the real return, "
                "but gains are taxed in nominal terms; set economic.inflation_rate for the full "
                f"drag (understated: {TOWARD_RENTING})"
            )
        room = tfsa_room_warning(spec.tax)
        if room is not None:
            warns.append(room)
        # Like-for-like under the block: the buyer's pile plus the HBP withdrawal
        # IS the renter's capital, or the two sides do not hold the same money.
        # The HBP joins either financing path (2026-09-08): a stated
        # `cash_available` is the pile itself; a stated `down_payment` is the
        # pile less the cash purchase costs, so the buyer's year-0 cash —
        # down payment + purchase_costs, the schema's own like-for-like
        # definition — is what the withdrawal is added to. The loader has
        # already folded the additions into `down_payment`; the typed figure
        # is what the sentence names.
        if spec.tax is not None and spec.tax.hbp is not None:
            hbp = spec.tax.hbp.withdrawal
            for name, opt in (("condo", spec.condo), ("house", spec.house)):
                if opt is None or not opt.first_time_buyer or opt.all_cash:
                    continue
                if opt.cash_available is not None:
                    pile = opt.cash_available + hbp
                    stated = f"{name} cash_available ${opt.cash_available:,.0f} + HBP ${hbp:,.0f}"
                    rule = "cash_available + hbp_withdrawal"
                elif opt.down_payment is not None:
                    typed_down = opt.down_payment - spec.tax.day_one_additions
                    pile = typed_down + opt.purchase_costs + hbp
                    stated = (f"{name} down payment ${typed_down:,.0f} + purchase_costs "
                              f"${opt.purchase_costs:,.0f} + HBP ${hbp:,.0f}")
                    rule = "down_payment + purchase_costs + hbp_withdrawal"
                else:
                    continue
                if abs(pile - capital) > 1.0:
                    warns.append(
                        f"tax: like-for-like — {stated} = ${pile:,.0f} while rent.invested_down_payment "
                        f"is ${capital:,.0f}; the two sides do not hold the same money — like-for-like "
                        f"is {rule} = rent.invested_down_payment"
                    )

    # Owner carrying and purchase costs left at zero understate the buy side;
    # say so by name (2026-09-02 user-model evaluation: every trial run's property
    # tax, insurance and closing costs were silently zero).
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None:
            continue
        missing = []
        # What the USER typed: when the engine derived an insured mortgage on a
        # stated down payment it put the premium tax into purchase_costs, and
        # that tax alone must not silence the land-transfer/notary ask.
        typed_purchase_costs = opt.purchase_costs
        if opt.mortgage_insurance is not None and opt.cash_available is None:
            typed_purchase_costs -= opt.mortgage_insurance.premium_tax
        # A DERIVED transfer tax is priced, not typed: it must not silence the
        # ask for the costs nobody has stated (2026-09-04 — the largest closing
        # cost being computed says nothing about the notary and the inspector).
        if opt.land_transfer_tax is not None:
            typed_purchase_costs -= opt.land_transfer_tax.total
        if typed_purchase_costs <= 0.005:
            # A financed premium is modelled (it rides the loan) — do not list it
            # as missing (round-four evaluation 2026-09-02).
            premium = ("" if opt.financed_purchase_costs > 0
                       else ", mortgage-insurance premium")
            transfer = ("notary, inspection — the transfer tax is priced separately"
                        if opt.land_transfer_tax is not None
                        else "land-transfer tax, notary")
            missing.append(f"purchase_costs ({transfer}{premium})")
        if not opt.other_recurring_costs:
            missing.append("other_recurring_costs (property tax, insurance)")
        if missing:
            warns.append(
                f"{name}: not modelled — {'; '.join(missing)} — owner costs are "
                f"understated, which biases the verdict {TOWARD_BUYING}"
            )
        if opt.value_growth_rate == 0:
            warns.append(
                f"{name}.value_growth_rate=0.0% — no appreciation modelled ({NEUTRAL}); "
                f"the verdict is sensitive to it: state a view or bracket it "
                f"(a market_scenario prior adds drift in the Monte Carlo only)"
            )
        # A NOMINAL 0% typed for the home's value is a real decline of
        # inflation's size, not the neutral view — that is the OMITTED key
        # (0% real). Served answers took "prices flat" typed as 0.0 for
        # neutral and a 5% margin became 36% (2026-09-08). Only a typed
        # figure under the as-quoted convention is recorded as converted, so
        # the default and `rates: real` never reach here; nominal mode with
        # inflation_rate=0 leaves 0 quoted at 0 real, which the neutral
        # warning above already names.
        typed_growth = converted_for(spec.converted_rates, f"{name}.value_growth_rate")
        if (econ.mode == "nominal" and typed_growth is not None
                and typed_growth.quoted == 0 and econ.inflation_rate > 0):
            decline = -deflate(0.0, econ.inflation_rate)
            warns.append(
                f"{name}.value_growth_rate {typed_growth.quoted:.1%} as quoted is a "
                f"{decline:.1%}/yr REAL decline in the home's value; a \"flat\" view that "
                f"tracks inflation is {econ.inflation_rate:.1%} quoted — or omit the key for "
                f"the neutral 0% real default; say which reading the user meant"
            )

    # Under 20% down with nothing financed (round 6): a Canadian mortgage below
    # 20% down carries a mortgage-insurance premium; a config that omits it
    # understates the loan and the payment.
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None or opt.all_cash or opt.down_payment is None or not opt.initial_value:
            continue
        if opt.down_payment >= 0.20 * opt.initial_value:
            continue
        record = opt.mortgage_insurance
        share = opt.down_payment / opt.initial_value
        if record is not None and record.required:
            # The engine priced it: say what it charged, not what to go compute.
            tax_clause = (
                f", plus ${record.premium_tax:,.0f} of provincial tax on the premium paid in "
                f"cash at closing (it cannot be added to the loan)"
                if record.premium_tax else ", with no provincial tax on the premium"
            )
            # The ceiling a stated cash pile puts on the price closes the
            # warning (2026-09-08): the financing line's clause, built once.
            ceiling = cover_clause(spec, name, raw)
            warns.append(
                f"{name}: down payment {share:.2%} of price is under the 20% mortgage-insurance "
                f"line — the engine priced the insured mortgage at {record.ltv:.2%} loan-to-value: "
                f"{record.rate:.2%} = ${record.premium:,.0f} added to the loan{tax_clause} "
                f"[{record.cite}]. The premium is non-refundable and carries interest for the "
                f"whole amortization"
                + (f"; {ceiling}" if ceiling else "")
            )
        elif opt.financed_purchase_costs == 0:
            warns.append(
                f"{name}: down payment {share:.2%} of price is under the 20% "
                f"mortgage-insurance line with no financed_purchase_costs — an insured mortgage carries a "
                f"premium on the loan (CMHC/Sagen by loan-to-value band). Set mortgage_insurance: auto to "
                f"have the engine price it from the anchored schedule, or compute it, put it in "
                f"financed_purchase_costs, and label it; omitting it biases the verdict {TOWARD_BUYING}"
            )

    # Asymmetric tails (review F4 + evaluation round 2): an owned option with a
    # price-shock channel against a renter whose capital cannot lose.
    # `named_one_sided` records that one of the two SPECIFIC one-sided warnings
    # already fired with its own actionable fix, so the general symmetric check
    # below does not say the same thing a second time.
    named_one_sided = False
    if (spec.rent is not None and spec.rent.invested_down_payment > 0
            and spec.simulation.investment_return_vol == 0
            and any(o is not None and o.price_shock is not None for o in (spec.condo, spec.house))):
        named_one_sided = True
        warns.append(
            "asymmetric tails: an owned option carries a price_shock channel while "
            "simulation.investment_return_vol=0 leaves the renter's capital unable to lose — set "
            "investment_return_vol (0.10 ≈ 60/40 portfolio) or drop price_shock for a like-for-like "
            "worst case"
        )
    # One-sided uncertainty (evaluation round 5): a demographic prior makes the
    # owned value stochastic while the renter's capital stays a point mass, so
    # P(cheapest) compares a distribution to a point.
    if (spec.rent is not None and spec.rent.invested_down_payment > 0
            and spec.simulation.investment_return_vol == 0
            and spec.market_scenario is not None
            and any(o is not None for o in (spec.condo, spec.house))):
        named_one_sided = True
        warns.append(
            "one-sided uncertainty: the market_scenario prior makes the owned option's value "
            "stochastic while simulation.investment_return_vol=0 leaves the renter's PV a point "
            "mass — P(cheapest) compares a distribution to a point and is OVERconfident: the "
            "too-close-to-call zone is wider than shown; set investment_return_vol (0.10 ≈ 60/40 "
            "portfolio) for a like-for-like band, or read the deterministic line"
        )

    # The same defect from either direction (2026-09-04 review). The two checks
    # above both require investment_return_vol=0, so they only ever caught the
    # point-mass RENTER; a single-path owned side against a renter carrying
    # return volatility measured the renter's dispersion alone and said nothing.
    # Whichever side is alone in carrying dispersion, P(cheapest) is that side's
    # spread against a fixed number, and it is OVERconfident for that reason.
    owned_spread, renter_spread, shared_spread = dispersion_sources(spec)
    if (not named_one_sided and not shared_spread
            and spec.rent is not None
            and any(o is not None for o in (spec.condo, spec.house))
            and bool(owned_spread) != bool(renter_spread)):
        if renter_spread:
            carrier, still = "the renter's PV", "the owned option's PV"
            listed, fix = renter_spread, ("give the owned side its own uncertainty "
                                          "(simulation.value_growth_vol, price_shock, "
                                          "simulation.house_maintenance_vol / "
                                          "condo_fee_vol, or a market_scenario prior)")
        else:
            carrier, still = "the owned option's PV", "the renter's PV"
            listed, fix = owned_spread, ("give the renter's side its own uncertainty "
                                         "(simulation.investment_return_vol, 0.10 ≈ 60/40 "
                                         "portfolio; simulation.rent_escalation_vol; or, for a "
                                         "sitting tenant below market, rent.reset_hazard with "
                                         "rent.reset_to_monthly_rent)")
        warns.append(
            f"one-sided uncertainty: {carrier} is the only stochastic side "
            f"({', '.join(listed)}) while {still} is a single path — P(cheapest) measures that "
            f"one side's dispersion against a fixed number and is OVERconfident: the "
            f"too-close-to-call zone is wider than shown; {fix} — or read the deterministic line"
        )

    # Québec's school tax (2026-09-04): the municipal rate is not the bill. A
    # Québec owner pays the province-wide school rate on top of it, and served
    # answers modelled the municipal line alone — an understatement that leans
    # toward buying. Silent when a line names the school tax, or when the
    # property-tax figure already carries it (a cited or declared sum).
    school = ANCHORS["school_tax.qc"]
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None or option_province(opt.province, opt.municipality) != "QC":
            continue
        names = [cost.name for cost in opt.other_recurring_costs]
        if not any(cost_family(n) == "property_tax." for n in names):
            continue
        if any(school_tax_line(n) for n in names) or _school_tax_cited(spec, name):
            continue
        warns.append(
            f"{name}: no school-tax line — Québec levies {school.name} "
            f"({school.value:.5%} of assessed value) on top of the municipal rate; add it "
            f"or list it as not modelled ({TOWARD_BUYING})"
        )

    # Renewal risk (slice 1, docs/specs/2026-09-03-mortgage-renewal-risk.md §6).
    # The engine priced one rate for a whole amortization; a Canadian fixed term
    # is at most five years, so a 25-year amortization resets four times and the
    # reset is the largest risk the buy side carries.
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if (opt is None or opt.all_cash or opt.mortgage_rate is None
                or opt.mortgage_term_years is None):
            continue
        if opt.mortgage_renewal_years is None:
            if opt.mortgage_term_years <= 5:
                # A five-year term covers an amortization this short outright,
                # so "the rate resets at every renewal" would name a reset this
                # mortgage never has — and the remedy it prescribes would then
                # be refused as inert (2026-09-21).
                # At a one-year amortization no shorter term exists, so the
                # remedy below would be unsatisfiable: say the mortgage cannot
                # renew instead of prescribing a term the loader refuses.
                remedy = (
                    f"set mortgage_renewal_years (under {opt.mortgage_term_years}) + "
                    f"mortgage_renewal_rates to price a renewal path (the engine anchors "
                    f"no renewal rate — the path is yours to state)"
                    if opt.mortgage_term_years >= 2 else
                    "no term shorter than a year exists, so this mortgage cannot renew "
                    "at all and there is nothing here to price"
                )
                warns.append(
                    f"{name}: renewal risk is not modelled — mortgage_rate "
                    f"{opt.mortgage_rate:.2%} is held for the whole "
                    f"{opt.mortgage_term_years}-year amortization; a 5-year Canadian fixed "
                    f"term covers it with no renewal at all, but any shorter term resets "
                    f"the rate before the loan is paid off; {remedy}"
                )
            else:
                warns.append(
                    f"{name}: renewal risk is not modelled — mortgage_rate "
                    f"{opt.mortgage_rate:.2%} is held for the whole "
                    f"{opt.mortgage_term_years}-year amortization, but a Canadian fixed term "
                    f"runs at most 5 years and the rate resets at every renewal; set "
                    f"mortgage_renewal_years + mortgage_renewal_rates to price a renewal path "
                    f"(the engine anchors no renewal rate — the path is yours to state)"
                )
            continue
        if opt.mortgage_renewal_years >= opt.mortgage_term_years:
            warns.append(
                f"{name}.mortgage_renewal_years={opt.mortgage_renewal_years} is at or past "
                f"the {opt.mortgage_term_years}-year amortization — the mortgage never "
                f"renews inside its own life, so mortgage_renewal_rates are inert and the "
                f"run prices mortgage_rate {opt.mortgage_rate:.2%} for the whole term"
            )
            continue
        horizon = spec.simulation.years
        if renewals_priced_inside(opt, horizon) == 0:
            # `_financing_pv` stops at the first segment past the horizon, so a
            # ladder that starts after it reaches no PV, no balance and no
            # verdict. Declaring the keys must not buy silence from the
            # not-modelled warning above (2026-09-21).
            first = opt.mortgage_renewal_years + 1
            warns.append(
                f"{name}: the stated renewal ladder prices nothing in this run — the "
                f"first renewal falls at year {first}, past the {horizon}-year horizon, "
                f"so the verdict holds mortgage_rate {opt.mortgage_rate:.2%} for its whole "
                f"length and renewal risk is still not modelled ({TOWARD_BUYING} while rates "
                f"rise); run at least {first} years to price the renewal path"
            )
            continue
        # The list means one rate per RENEWAL: the engine prepends mortgage_rate
        # for the opening term, so entry 1 prices the FIRST RENEWAL. Read as one
        # rate per five-year BLOCK — the other natural reading of "a list in
        # order" — the same figures would mean the whole path one term earlier.
        # Where the two readings give DIFFERENT counts the loader refuses; where
        # they coincide (a horizon that is a whole number of terms and shorter
        # than the amortization) nothing catches it, and the tell is that entry 1
        # repeats mortgage_rate, so the first renewal steps by nothing.
        #
        # Deliberately reads the DECLARED list, not the priced schedule: the
        # subject IS the gap between what was typed and how it was read. The
        # engine cannot tell the readings apart, so it discloses rather than
        # resolves — and never refuses, because holding the contract rate
        # through the first renewal is a real thing to model (2026-09-21).
        rates = opt.mortgage_renewal_rates or []
        if rates and abs(rates[0] - opt.mortgage_rate) <= 1e-12:
            first_renewal = opt.mortgage_renewal_years + 1
            warns.append(
                f"{name}.mortgage_renewal_rates opens at {rates[0]:.2%}, the same figure as "
                f"mortgage_rate: the engine reads this list as ONE RATE PER RENEWAL, so that "
                f"entry prices year {first_renewal} and the opening term runs at mortgage_rate "
                f"on its own — the first renewal therefore steps by nothing. Read as one rate "
                f"per {opt.mortgage_renewal_years}-year BLOCK, the other natural reading, the "
                f"same list would put that figure on year 1 and every later one a term earlier "
                f"than it lands here. Both are legitimate and the engine cannot tell them "
                f"apart: check the '{name} renewals:' line against the path you meant"
            )
        if opt.down_payment is None:
            continue
        # The bias this warning exists to name is an economic one, so it is
        # measured on what the run PRICED, not on the declared rate list: a
        # rate past the last renewal, or past the horizon, reaches no payment,
        # and a short list's last entry carries forward over renewals nobody
        # typed. Reading the list let either silence the warning (2026-09-21).
        dr = spec.simulation.discount_rate
        laddered_pv = mortgage_leg_pv(opt, dr, horizon)
        flat_pv = mortgage_leg_pv(opt, dr, horizon, laddered=False)
        cheaper = round(flat_pv - laddered_pv)
        if cheaper >= 1:
            warns.append(
                f"{name}: the stated renewal path prices the mortgage ${cheaper:,.0f} "
                f"below its contract rate mortgage_rate {opt.mortgage_rate:.2%} held "
                f"throughout (PV ${laddered_pv:,.0f} against ${flat_pv:,.0f} over the "
                f"{horizon}-year horizon) — a renewal path that costs less than the "
                f"contract biases the verdict {TOWARD_BUYING}; state the renewal path you "
                f"want stressed, not the one you hope for"
            )

    # The POSTED rate is a list price (2026-09-04): the registry's own entry
    # says contracted rates run lower. A mortgage_rate that IS the posted
    # figure — in either of its stated conventions, within the read-back
    # matcher's window — is named as such, because the verdict's margin moves
    # with the rate and nothing else in the run would say the rate is a ceiling.
    posted = ANCHORS["mortgage_rate.posted_5y"]
    window = match_window(posted.name)
    for name, opt in (("condo", spec.condo), ("house", spec.house)):
        if opt is None or opt.all_cash or opt.mortgage_rate is None:
            continue
        if any(abs(opt.mortgage_rate - stated) <= window for stated in posted.stated_values()):
            # The figure as the config typed it (2026-09-08: the spec's rate is
            # the effective annual one the quote converts to).
            shown = opt.mortgage_rate if opt.mortgage_rate_quoted is None else opt.mortgage_rate_quoted
            warns.append(
                f"{name}.mortgage_rate {shown:.2%} is the POSTED 5-year rate "
                f"({posted.name}); its source says contracted rates run lower — see "
                f"mortgage_rate.contracted_5y_uninsured / mortgage_rate.contracted_5y_insured "
                f"in --print-anchors; the verdict's margin moves with the rate"
            )

    return warns


def dispersion_sources(spec: ComparisonSpec) -> Tuple[List[str], List[str], List[str]]:
    """Which inputs give each side of the comparison a DISTRIBUTION, named:
    (owned, renter, shared).

    `single_path_run` answers the whole-run version of this question ("is every
    uncertainty input off?"); this one answers it per side, which is what a
    probability that compares the two sides needs. An input is listed against
    the side whose Monte Carlo path actually reads it (monte_carlo.py), so
    `other_cost_vol` counts only for an option that HAS other recurring costs,
    and inflation volatility — which every path composes — is shared.
    """
    sim = spec.simulation
    owned: List[str] = []
    renter: List[str] = []
    shared: List[str] = []
    if spec.economic.inflation_vol:
        shared.append("economic.inflation_vol")
    if spec.market_scenario is not None:
        owned.append("market_scenario (demographic drift per path)")
    # value_growth_vol moves the value track of EVERY owned option, so it is
    # named once against the owned side rather than once per option.
    if sim.value_growth_vol and any(o is not None for o in (spec.condo, spec.house)):
        owned.append("simulation.value_growth_vol")
    for name, option, own_vol in (("condo", spec.condo, "condo_fee_vol"),
                                  ("house", spec.house, "house_maintenance_vol")):
        if option is None:
            continue
        if getattr(sim, own_vol):
            owned.append(f"simulation.{own_vol}")
        shock = option.price_shock
        if shock is not None and shock.annual_hazard > 0:
            owned.append(f"{name}.price_shock")
        if option.other_recurring_costs and sim.other_cost_vol:
            owned.append("simulation.other_cost_vol")
        if _stochastic_events(option):
            owned.append(f"{name}.events")
    if spec.rent is not None:
        if sim.rent_escalation_vol:
            renter.append("simulation.rent_escalation_vol")
        if sim.investment_return_vol and spec.rent.invested_down_payment > 0:
            renter.append("simulation.investment_return_vol")
        if spec.rent.other_recurring_costs and sim.other_cost_vol:
            renter.append("simulation.other_cost_vol")
        if _stochastic_events(spec.rent):
            renter.append("rent.events")
        # The lease reset is the renter's own tail: on some paths the rent
        # series moves to a different track and on others it does not. Missing
        # it made this function assert the OPPOSITE of the truth -- a config
        # with an owned price_shock and a renter reset was told "the renter's
        # PV is a single path" while that PV ran from $291,579 to $534,562
        # (measured 2026-09-21 over 2,000 paths). A warning that states the
        # opposite of the truth is worse than no warning, so every channel
        # that widens a side is named here.
        if spec.rent.reset_hazard > 0:
            renter.append("rent.reset_hazard")
    return owned, renter, shared


def _stochastic_events(option: Any) -> bool:
    """True when any of an option's events carries timing or cost dispersion."""
    for event in option.events:
        if event.timing_std_years != 0 or event.cost_vol != 0:
            return True
        if event.timing_model == "hazard" and (event.hazard_base != 0
                                               or event.hazard_growth != 0):
            return True
    return False


def affordability_warnings(det: "ComparisonDeterministicResult") -> List[str]:
    """Warnings that need the deterministic result: an option whose housing
    cost/income ratio breaches the threshold in any year (the report prints the
    ratios, but a breach must also reach the `[warning]` channel)."""
    warns: List[str] = []
    rpt = det.income_report
    if rpt is None:
        return warns
    for name, ratios, exceeds in (
        ("rent", rpt.rent_ratios, rpt.years_rent_exceeds),
        ("condo", rpt.condo_ratios, rpt.years_condo_exceeds),
        ("house", rpt.house_ratios, rpt.years_house_exceeds),
    ):
        if ratios and exceeds:
            warns.append(
                f"affordability: {name} housing cost exceeds {rpt.threshold:.0%} of income "
                f"in years {exceeds} (max {max(ratios):.1%}) — GDS-shaped ratio (housing cost "
                f"incl. maintenance over income, no other debts): CMHC's cap for that shape is "
                f"39% GDS, not the 44% TDS [income.affordability_threshold]"
            )
    return warns


def uncertainty_source_warnings(
    spec: ComparisonSpec,
    det: "ComparisonDeterministicResult",
    verdict: Optional[Any] = None,
) -> List[str]:
    """
    The decisiveness-provenance warning (2026-09-03): when Monte Carlo DECIDES
    the verdict and the inputs that widen the distribution are not the user's,
    say so — and price the alternative.

    Fires only under the `mc_floor` rule; the deterministic tie band reads no
    uncertainty input, so nothing rests on one there. Every uncertainty input
    (the same set `single_path_run` reads) that is assistant-typed or
    unattributed is named with its value, and the closing clause states what
    the deterministic line alone says: in three of five evaluation answers the
    decision was called "too close to call" on volatility the user never
    stated, while the deterministic margin was decisive.
    """
    if verdict is None or verdict.rule != "mc_floor":
        return []
    unstated = unstated_uncertainty(spec.sources)
    if not unstated:
        return []
    det_only = compute_verdict(
        det, None, years=spec.simulation.years,
        discount_rate=spec.simulation.discount_rate,
    )
    if det_only is None:
        return []
    band = ANCHORS["verdict.tie_band"].value
    named = ", ".join(
        f"{e.key}={e.formatted}" + (f" ({e.detail})" if e.detail else "")
        + f" ({e.source})"
        for e in unstated
    )
    return [
        f"decisiveness rests on uncertainty inputs the user did not state: {named} — "
        f"the deterministic line alone says {det_only.best} by "
        f"${det_only.margin_pv:,.0f} ({det_only.margin_frac:.1%} of its PV — "
        f"{'' if det_only.decisive else 'not '}decisive under the {band:.0%} band)"
    ]


def anchors_in_use(spec: ComparisonSpec) -> List[str]:
    """Every registry entry whose figure this run USED, in use order, once
    each: the defaults the loader applied, the anchors a `sources:` block
    declared, and the schedules the loader priced — the insured mortgage's
    band and premium tax, the transfer-tax brackets the price reached, the
    brackets a `tax:` block's income reached and the limits its legs read. A
    reference entry the run never touched is not here, so nothing can be said
    about it — a lapsed figure the run did not use is not the run's problem."""
    names: List[str] = []
    for key in spec.defaults_applied:
        anchor = default_anchor(spec, key)
        if anchor is not None:
            names.append(anchor.name)
    if spec.sources is not None:
        for entry in spec.sources.of_class("anchor"):
            for part in (entry.anchor or "").split("+"):
                part = part.strip()
                # `<family>.*` is the loader's own attribution of a derived
                # transfer tax; the record below carries it bracket by bracket.
                if part and not part.endswith(".*") and part in ANCHORS:
                    names.append(part)
    for opt in (spec.condo, spec.house):
        if opt is None:
            continue
        names.extend(insurance_anchors_used(opt.mortgage_insurance))
        names.extend(transfer_tax_anchors_used(opt.land_transfer_tax, opt.initial_value))
    names.extend(tax_anchors_used(spec.tax))
    return list(dict.fromkeys(names))


def validity_warnings(spec: ComparisonSpec, run_date: datetime.date) -> List[str]:
    """One line per anchor the run used whose source says the figure changes
    after a date `run_date` has passed (`Anchor.valid_until`: the Québec tax
    on insurance premiums steps up for premiums paid after 2026-12-31; an
    indexed 2026 bracket ceiling is a 2026 ceiling). Silent through the date
    itself, silent for every entry the run never touched. Pure in `run_date`,
    which `all_warnings` reads from the wall clock at the edge."""
    lines: List[str] = []
    for name in anchors_in_use(spec):
        anchor = ANCHORS[name]
        if not anchor.valid_until or anchor.value is None:
            continue
        if run_date > datetime.date.fromisoformat(anchor.valid_until):
            lines.append(
                f"anchor {name} ({anchor.value:g}) is past its validity date "
                f"{anchor.valid_until}: the source says the figure changes after that "
                f"date — re-read {anchor.short_cite} before relying on the run"
            )
    return lines


def all_warnings(
    spec: ComparisonSpec,
    prior: Optional[LoadedScenarioPrior] = None,
    current_year: Optional[int] = None,
    run_date: Optional[datetime.date] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Every warning a surface should show for one run: the coherence warnings
    plus, when a demographic prior is loaded, the time-anchor violations
    (wall clock past START_CALENDAR_YEAR), plus the anchors the run used past
    their validity date (`validity_warnings`). ONE assembly for the CLI's
    stderr, and the CLI's --json `warnings`, so no surface can drop
    a class of warning the others carry (readiness plan A.2). `current_year`
    and `run_date` are injectable for tests; the wall clock is read only here
    at the edge. `raw` (the YAML mapping) reaches `coherence_warnings` for the
    price ceiling.
    """
    warns = coherence_warnings(spec, raw)
    if prior is not None:
        if current_year is None:
            current_year = datetime.date.today().year
        as_of = prior.data_vintage.get("constants_as_of")
        warns = warns + time_anchor_violations(
            current_year, as_of if isinstance(as_of, str) else None)
    if run_date is None:
        run_date = datetime.date.today()
    return warns + validity_warnings(spec, run_date)


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
        sim.value_growth_vol,
        spec.economic.inflation_vol,
    )
    if any(v != 0 for v in vols):
        return False
    if spec.rent is not None and spec.rent.reset_hazard > 0:
        return False  # the tenancy can end on some paths and not others
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


def _parse_recurring_cost(
    cost_data: Dict[str, Any], conv: RateConverter, option: str,
) -> RecurringOtherCost:
    """
    Parse a recurring other cost from YAML data.

    `escalation_rate` is a typed rate like any other: as quoted under the
    default convention (deflated by inflation_rate; a line that does not rise
    in sticker terms falls in real terms), recorded under the named-line key
    `<option>.other_recurring_costs.<name>.escalation_rate` — the same key a
    `sources:` declaration uses for it. Omitted, it is 0.0 REAL (the line
    tracks inflation), like every other default.

    Raises:
        ConfigValidationError: If required fields are missing
    """
    required = ["name", "annual_amount"]
    for field in required:
        if field not in cost_data:
            raise ConfigValidationError(f"Recurring cost missing required field: {field}")

    name = str(cost_data["name"])
    return RecurringOtherCost(
        name=name,
        annual_amount=float(cost_data["annual_amount"]),
        escalation_rate=conv.real(
            cost_data, "escalation_rate",
            f"{option}.other_recurring_costs.{name}.escalation_rate", 0.0),
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


def _net_down_payment(
    data: Dict[str, Any], name: str, purchase_costs: float,
) -> Tuple[Optional[float], Optional[float]]:
    """
    The owned option's down payment and the cash pile it was netted from.

    `cash_available` is the figure a buyer actually knows — the pile they bring
    to the closing table. The down payment is what survives paying the CASH
    purchase costs out of it; `financed_purchase_costs` ride the loan and are
    never netted. Stating both inputs is ambiguous intent, so it is refused by
    name rather than resolved by precedence (2026-09-03: every threshold serve
    hand-computed this subtraction for the user, unchecked).

    `purchase_costs` is the RESOLVED figure — the dollar key or the one derived
    from `purchase_costs_rate` — so a price sweep re-nets the pile at every grid
    point instead of subtracting the seed price's closing costs throughout.
    """
    down = None if "down_payment" not in data else float(data["down_payment"])
    cash = None if "cash_available" not in data else float(data["cash_available"])
    if down is not None and cash is not None:
        raise ConfigValidationError(
            f"{name}: down_payment and cash_available are both set — declare exactly one "
            f"(cash_available states the pile you bring and the engine nets purchase_costs "
            f"out of it; down_payment states the resulting figure directly)")
    if cash is not None:
        down = cash - purchase_costs
    return down, cash


# ---------------------------------------------------------------------------
# Price-proportional inputs, derived per load (2026-09-03 answer reviews)
#
# `--break-even <option>.initial_value` and `--sweep` on the same key re-run the
# whole loader at every grid point, so whatever the loader DERIVES from the
# price moves with it and whatever is typed in dollars does not. Closing costs
# and the property-tax bill are price-proportional in reality; held at the seed
# price's size they moved one answer's "buying wins above" band by ~$50k and
# another's clear-win edge by $35k. These two keys are the rate alternatives:
# stated once, re-derived every load.
# ---------------------------------------------------------------------------

def _purchase_costs(data: Dict[str, Any], name: str) -> float:
    """`purchase_costs` in dollars, or `purchase_costs_rate` × the price."""
    if "purchase_costs_rate" not in data:
        return float(data.get("purchase_costs", 0.0))
    if "purchase_costs" in data:
        raise ConfigValidationError(
            f"{name}: purchase_costs and purchase_costs_rate are both set — declare exactly "
            f"one (purchase_costs_rate is a fraction of initial_value, re-derived at every "
            f"price a sweep or break-even tries; purchase_costs states the dollars directly)")
    rate = float(data["purchase_costs_rate"])
    if rate < 0:
        raise ConfigValidationError(
            f"{name}.purchase_costs_rate={rate} is negative — it is a fraction of the "
            f"purchase price (0.03 = 3%)")
    return rate * float(data.get("initial_value", 0.0))


# A recurring cost whose name says "tax" IS the annual tax bill (property or
# school): both are levied on assessed value, so both are what property_tax_rate
# replaces. Matching on the name is what the schema gives — there is no dollar
# property-tax key, only an `other_recurring_costs` line.
def _tax_lines(other_costs: List[RecurringOtherCost]) -> List[RecurringOtherCost]:
    return [c for c in other_costs if "tax" in c.name.lower()]


def _property_tax_cost(
    data: Dict[str, Any], name: str, other_costs: List[RecurringOtherCost],
    value_growth_rate: float,
) -> Optional[RecurringOtherCost]:
    """The property-tax line derived from `property_tax_rate`, or None.

    "Fraction of value per year": the year-1 bill is `rate × initial_value` and
    it escalates at the option's own `value_growth_rate` — the RESOLVED real
    figure, so a growth rate typed as quoted is converted once, here too — so it
    stays that fraction of the home's value the way `annual_maintenance_rate`
    does. (The two ride different escalation conventions — other costs compound
    from year 1, the value from year 2; the one-year offset is the documented
    divergence in ARCHITECTURE.md § Conventions, not a second modelling choice
    made here.)
    """
    if "property_tax_rate" not in data:
        return None
    clash = _tax_lines(other_costs)
    if clash:
        raise ConfigValidationError(
            f"{name}: property_tax_rate and the other_recurring_costs line "
            f"{clash[0].name!r} are both set — declare exactly one (the rate is a fraction "
            f"of initial_value, re-derived at every price a sweep or break-even tries; the "
            f"dollar line states one year's bill and stays fixed while the price moves)")
    rate = float(data["property_tax_rate"])
    if rate < 0:
        raise ConfigValidationError(
            f"{name}.property_tax_rate={rate} is negative — it is a fraction of value "
            f"per year (0.0085 = 0.85%)")
    return RecurringOtherCost(
        name=f"property tax ({rate:.2%} of value)",
        annual_amount=rate * float(data.get("initial_value", 0.0)),
        escalation_rate=value_growth_rate,
    )


def _apply_land_transfer_tax(
    data: Dict[str, Any], name: str, top_province: Optional[str],
    initial_value: float, purchase_costs: float,
) -> Tuple[float, Optional[LandTransferTax]]:
    """
    Derive the transfer tax (src/hde/land_transfer_tax.py) and fold it into
    `purchase_costs` — it is cash at closing, like the notary's bill.

    Called BEFORE `_net_down_payment`, so a stated `cash_available` has the tax
    taken out of it with the rest of the closing costs; and derived HERE, in the
    loader, so `--sweep` and `--break-even` re-derive it at every grid point
    instead of freezing the seed price's brackets (a Montréal price scan crosses
    the $552,300 knee from 1.5% to 2%).
    """
    try:
        tax, record = resolve_land_transfer_tax(
            data, name,
            top_province=top_province,
            initial_value=initial_value,
            purchase_costs=purchase_costs,
        )
    except LandTransferTaxError as exc:
        raise ConfigValidationError(str(exc)) from exc
    return purchase_costs + tax, record


def _apply_mortgage_insurance(
    data: Dict[str, Any], name: str, top_province: Optional[str],
    initial_value: float, down_payment: Optional[float], cash_available: Optional[float],
    purchase_costs: float,
) -> Tuple[Optional[float], float, float, Optional[MortgageInsurance]]:
    """
    Derive the insured mortgage (src/hde/mortgage_insurance.py) and fold its two
    money legs back into the option: the premium joins `financed_purchase_costs`
    (it rides the loan, so nothing downstream needs to know), and the provincial
    tax on it is cash — netted out of a stated `cash_available`, else added to
    `purchase_costs`.

    Derived HERE, in the loader, so `--sweep` and `--break-even` — which re-run
    the loader at every grid point — re-derive the tier per point instead of
    freezing the base config's premium (round-7 evaluation 2026-09-03: a price scan
    held a 2.80% premium fixed while the loan-to-value crossed into 3.10%).
    """
    try:
        return resolve_mortgage_insurance(
            data, name,
            top_province=top_province,
            initial_value=initial_value,
            down_payment=down_payment,
            cash_available=cash_available,
            purchase_costs=purchase_costs,
            financed_purchase_costs=float(data.get("financed_purchase_costs", 0.0)),
            all_cash=_parse_bool(data.get("all_cash", False), f"{name}.all_cash"),
            mortgage_term_years=(None if "mortgage_term_years" not in data
                                 else int(data["mortgage_term_years"])),
        )
    except MortgageInsuranceError as exc:
        raise ConfigValidationError(str(exc)) from exc


def _mortgage_rate(data: Dict[str, Any], name: str) -> Tuple[Optional[float], str, Optional[float]]:
    """(the rate as quoted, its compounding, the EFFECTIVE annual rate the
    payment uses) for one owned option — the one conversion a typed mortgage
    rate gets (2026-09-08): a semi-annual quote (the default, the Canadian
    fixed-rate convention) becomes (1 + r/2)^2 − 1; an effective annual quote
    is used as typed. (None, convention, None) with no rate typed."""
    try:
        compounding = mortgage_compounding_of(data)
    except MortgageCompoundingError as exc:
        raise ConfigValidationError(f"{name}.{exc}") from exc
    if "mortgage_rate" not in data:
        return None, compounding, None
    quoted = float(data["mortgage_rate"])
    return quoted, compounding, effective_mortgage_rate(quoted, compounding)


def _mortgage_renewal(
    data: Dict[str, Any], name: str, compounding: str,
) -> Tuple[Optional[int], Optional[List[float]], Optional[List[float]]]:
    """(the rate contract's length, the EFFECTIVE annual rate per renewal, the
    rates as quoted) for one owned option — the renewal ladder, slice 1.

    A scalar applies to every renewal; a list is read in order and its last
    entry carries forward. Both keys travel together: the engine has no
    defensible renewal rate of its own and will not invent one, and a rate with
    no term has nothing to apply over — either alone is refused.

    A renewal rate is a quoted contract rate of `mortgage_rate`'s class (spec
    §5), so it takes the SAME compounding conversion and never meets inflation:
    the same typed figure in the two fields means the same rate.
    """
    has_years = "mortgage_renewal_years" in data
    has_rates = "mortgage_renewal_rates" in data
    if not has_years and not has_rates:
        return None, None, None
    if has_years and not has_rates:
        raise ConfigValidationError(
            f"{name}.mortgage_renewal_years={data['mortgage_renewal_years']} is set without "
            f"{name}.mortgage_renewal_rates — no renewal rate is anchored or forecast by this "
            f"engine, so state the rate you want priced at renewal (one figure for every "
            f"renewal, or a list in order)")
    if has_rates and not has_years:
        raise ConfigValidationError(
            f"{name}.mortgage_renewal_rates is set without {name}.mortgage_renewal_years — "
            f"the rates have no term to apply over; state the RATE contract's length in years "
            f"(a Canadian fixed term is at most 5), not the amortization "
            f"({name}.mortgage_term_years)")

    years = int(data["mortgage_renewal_years"])
    if years <= 0:
        raise ConfigValidationError(
            f"{name}.mortgage_renewal_years must be > 0, got {years}")

    raw = data["mortgage_renewal_rates"]
    if isinstance(raw, (list, tuple)):
        quoted = [float(r) for r in raw]
    else:
        quoted = [float(raw)]
    if not quoted:
        raise ConfigValidationError(
            f"{name}.mortgage_renewal_rates is an empty list — state at least one rate "
            f"(one figure applies to every renewal), or remove both renewal keys")
    for rate in quoted:
        if rate < 0:
            raise ConfigValidationError(
                f"{name}.mortgage_renewal_rates must be >= 0, got {rate}")

    # More rates than the mortgage has renewals: the schedule reads them by
    # index and simply stops, so the surplus entries would price NOTHING and
    # nothing downstream would say so. A stated figure the run discards in
    # silence is the honesty contract running backwards, and the engine cannot
    # tell which reading the user meant — one rate per renewal, or one per
    # five-year block counting the opening term — so it refuses (2026-09-21).
    amortization = data.get("mortgage_term_years")
    if amortization is not None:
        amortization = int(amortization)
        if amortization > 0:
            segments = -(-amortization // years)          # ceil, as the schedule counts
            renewals = segments - 1
            if renewals >= 1 and len(quoted) > renewals:
                dropped = ", ".join(f"{r:.2%}" for r in quoted[renewals:])
                raise ConfigValidationError(
                    f"{name}.mortgage_renewal_rates has {len(quoted)} rates but the "
                    f"{amortization}-year amortization renews {renewals} times on a "
                    f"{years}-year term — {dropped} would be priced nowhere. The FIRST "
                    f"entry is the rate at the FIRST RENEWAL (year {years + 1}); the "
                    f"opening term runs at {name}.mortgage_rate and is not in this list. "
                    f"State one rate per renewal ({renewals}), a shorter list whose last "
                    f"entry carries forward, or one figure for every renewal")
    return years, [effective_mortgage_rate(r, compounding) for r in quoted], quoted


def _day_one_additions(data: Dict[str, Any], name: str, tax: Optional[TaxParams]) -> Tuple[bool, float]:
    """(first_time_buyer, what the `tax:` block adds to this option's day-one
    cash — the FHSA refunds and the HBP withdrawal, for a first-time buyer)."""
    first_time = _parse_bool(data.get("first_time_buyer", False), f"{name}.first_time_buyer")
    additions = tax.day_one_additions if (tax is not None and first_time) else 0.0
    return first_time, additions


def _parse_condo(condo_data: Dict[str, Any], years: int, conv: RateConverter,
                 top_province: Optional[str] = None,
                 tax: Optional[TaxParams] = None) -> CondoParams:
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
        _parse_recurring_cost(c, conv, "condo")
        for c in condo_data.get("other_recurring_costs", [])
    ]

    value_growth_rate = conv.real(condo_data, "value_growth_rate", "condo.value_growth_rate",
                                  ANCHORS["condo.value_growth_rate"].value)
    mortgage_rate_quoted, mortgage_rate_compounding, mortgage_rate = _mortgage_rate(condo_data, "condo")
    (renewal_years, renewal_rates,
     renewal_rates_quoted) = _mortgage_renewal(condo_data, "condo", mortgage_rate_compounding)
    property_tax = _property_tax_cost(condo_data, "condo", other_costs, value_growth_rate)
    if property_tax is not None:
        other_costs.append(property_tax)

    purchase_costs = _purchase_costs(condo_data, "condo")
    purchase_costs, transfer_tax = _apply_land_transfer_tax(
        condo_data, "condo", top_province,
        float(condo_data.get("initial_value", 0.0)), purchase_costs)
    down_payment, cash_available = _net_down_payment(condo_data, "condo", purchase_costs)
    # A first-time buyer's FHSA refunds and HBP withdrawal join the pile HERE —
    # after the netting, before the insurance tier is chosen on the loan that
    # remains (2026-09-05). `cash_available` stays as typed; the financing line
    # shows the addition.
    first_time_buyer, additions = _day_one_additions(condo_data, "condo", tax)
    (down_payment, purchase_costs, financed_purchase_costs,
     insurance) = _apply_mortgage_insurance(
        condo_data, "condo", top_province,
        float(condo_data.get("initial_value", 0.0)),
        None if down_payment is None else down_payment + additions,
        None if cash_available is None else cash_available + additions,
        purchase_costs)

    return CondoParams(
        monthly_fee=float(condo_data["monthly_fee"]),
        fee_escalation_rate=conv.real(condo_data, "fee_escalation_rate", "condo.fee_escalation_rate",
                                      ANCHORS["condo.fee_escalation_rate"].value),
        events=events,
        other_recurring_costs=other_costs,
        reserve_contribution_rate=float(condo_data.get("reserve_contribution_rate", 0.0)),
        reserve_initial_balance=float(condo_data.get("reserve_initial_balance", 0.0)),
        reserve_growth_rate=conv.real(condo_data, "reserve_growth_rate", "condo.reserve_growth_rate", 0.0),
        initial_value=float(condo_data.get("initial_value", 0.0)),
        value_growth_rate=value_growth_rate,
        down_payment=down_payment,
        cash_available=cash_available,
        mortgage_rate=mortgage_rate, mortgage_rate_quoted=mortgage_rate_quoted,
        mortgage_rate_compounding=mortgage_rate_compounding,
        mortgage_term_years=(None if "mortgage_term_years" not in condo_data else int(condo_data["mortgage_term_years"])),
        mortgage_renewal_years=renewal_years,
        mortgage_renewal_rates=renewal_rates,
        mortgage_renewal_rates_quoted=renewal_rates_quoted,
        all_cash=_parse_bool(condo_data.get("all_cash", False), "condo.all_cash"),
        # WOWA 2026: seller-side commissions ≈ 4–5% + notary ⇒ 5% all-in
        selling_cost_rate=float(condo_data.get("selling_cost_rate", ANCHORS["condo.house.selling_cost_rate"].value)),
        purchase_costs=purchase_costs,
        financed_purchase_costs=financed_purchase_costs,
        province=condo_data.get("province", top_province),
        municipality=_municipality(condo_data),
        mortgage_insurance=insurance,
        land_transfer_tax=transfer_tax,
        first_time_buyer=first_time_buyer,
        price_shock=(
            _parse_price_shock(condo_data["price_shock"], "condo")
            if "price_shock" in condo_data else None
        ),
    )


def _parse_house(house_data: Dict[str, Any], years: int, conv: RateConverter,
                 top_province: Optional[str] = None,
                 tax: Optional[TaxParams] = None) -> HouseParams:
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
        _parse_recurring_cost(c, conv, "house")
        for c in house_data.get("other_recurring_costs", [])
    ]

    maintenance_curve_raw = house_data.get("maintenance_curve", [])
    maintenance_curve = []
    for point in maintenance_curve_raw:
        if "year" not in point or "rate" not in point:
            raise ConfigValidationError("maintenance_curve entries must have 'year' and 'rate'")
        maintenance_curve.append((int(point["year"]), float(point["rate"])))
    maintenance_curve.sort(key=lambda x: x[0])

    value_growth_rate = conv.real(house_data, "value_growth_rate", "house.value_growth_rate",
                                  ANCHORS["house.value_growth_rate"].value)
    mortgage_rate_quoted, mortgage_rate_compounding, mortgage_rate = _mortgage_rate(house_data, "house")
    (renewal_years, renewal_rates,
     renewal_rates_quoted) = _mortgage_renewal(house_data, "house", mortgage_rate_compounding)
    property_tax = _property_tax_cost(house_data, "house", other_costs, value_growth_rate)
    if property_tax is not None:
        other_costs.append(property_tax)

    purchase_costs = _purchase_costs(house_data, "house")
    purchase_costs, transfer_tax = _apply_land_transfer_tax(
        house_data, "house", top_province,
        float(house_data["initial_value"]), purchase_costs)
    down_payment, cash_available = _net_down_payment(house_data, "house", purchase_costs)
    first_time_buyer, additions = _day_one_additions(house_data, "house", tax)
    (down_payment, purchase_costs, financed_purchase_costs,
     insurance) = _apply_mortgage_insurance(
        house_data, "house", top_province,
        float(house_data["initial_value"]),
        None if down_payment is None else down_payment + additions,
        None if cash_available is None else cash_available + additions,
        purchase_costs)

    return HouseParams(
        initial_value=float(house_data["initial_value"]),
        value_growth_rate=value_growth_rate,
        annual_maintenance_rate=float(house_data.get("annual_maintenance_rate", ANCHORS["house.annual_maintenance_rate"].value)),
        events=events,
        other_recurring_costs=other_costs,
        maintenance_curve=maintenance_curve,
        down_payment=down_payment,
        cash_available=cash_available,
        mortgage_rate=mortgage_rate, mortgage_rate_quoted=mortgage_rate_quoted,
        mortgage_rate_compounding=mortgage_rate_compounding,
        mortgage_term_years=(None if "mortgage_term_years" not in house_data else int(house_data["mortgage_term_years"])),
        mortgage_renewal_years=renewal_years,
        mortgage_renewal_rates=renewal_rates,
        mortgage_renewal_rates_quoted=renewal_rates_quoted,
        all_cash=_parse_bool(house_data.get("all_cash", False), "house.all_cash"),
        # WOWA 2026: seller-side commissions ≈ 4–5% + notary ⇒ 5% all-in
        selling_cost_rate=float(house_data.get("selling_cost_rate", ANCHORS["condo.house.selling_cost_rate"].value)),
        purchase_costs=purchase_costs,
        financed_purchase_costs=financed_purchase_costs,
        province=house_data.get("province", top_province),
        municipality=_municipality(house_data),
        mortgage_insurance=insurance,
        land_transfer_tax=transfer_tax,
        first_time_buyer=first_time_buyer,
        price_shock=(
            _parse_price_shock(house_data["price_shock"], "house")
            if "price_shock" in house_data else None
        ),
    )


def _parse_tax(data: Dict[str, Any]) -> Optional[TaxParams]:
    """The `tax:` block (tax_treatment.resolve), parsed from the raw mapping
    BEFORE the options — its refunds and HBP withdrawal join a first-time
    buyer's day-one cash inside the option parsers. None when absent."""
    try:
        return resolve_tax(
            data,
            rent=data["rent"] if isinstance(data.get("rent"), dict) else None,
            income=data["income"] if isinstance(data.get("income"), dict) else None,
            province=data.get("province"),
            owned={name: data[name] for name in ("condo", "house") if isinstance(data.get(name), dict)},
        )
    except TaxTreatmentError as exc:
        raise ConfigValidationError(str(exc)) from exc


def _parse_rent(data: Dict[str, Any], years: int, conv: RateConverter,
                derived_capital: Optional[float] = None) -> RentParams:
    """Parse RentParams from YAML data. `derived_capital` is the renter's
    capital the `tax:` block derived from its `renter_capital` shares when
    `invested_down_payment` is omitted (2026-09-08); a stated figure wins."""
    if "monthly_rent" not in data:
        raise ConfigValidationError("rent section missing required field: monthly_rent")
    events = [_parse_event(e, years) for e in data.get("events", [])]
    other = [_parse_recurring_cost(c, conv, "rent") for c in data.get("other_recurring_costs", [])]
    fallback = 0.0 if derived_capital is None else derived_capital

    # The lease-reset channel: both keys or neither. A hazard with no market
    # figure has nothing to reset to, and a market figure with no hazard is a
    # number the user supplied that the engine would silently ignore — the
    # honesty contract makes that the worse of the two failures, so both raise
    # (docs/specs/2026-09-21-one-world-simulation.md §4).
    reset_hazard = float(data.get("reset_hazard", 0.0))
    reset_to = data.get("reset_to_monthly_rent")
    # `not (0 <= h <= 1)` rather than `h < 0 or h > 1`, because every comparison
    # against NaN is False: the second form ACCEPTS `.nan`, and a NaN hazard
    # then never fires (`rng.random() < nan` is always False), so the engine
    # would silently price no reset at all for a user who stated one. Same
    # class as the paired-key refusals below.
    if not (0.0 <= reset_hazard <= 1.0):
        raise ConfigValidationError(
            f"rent.reset_hazard must be an annual probability in [0, 1], got {reset_hazard}"
        )
    if reset_hazard > 0 and reset_to is None:
        raise ConfigValidationError(
            "rent.reset_hazard is set but rent.reset_to_monthly_rent is missing: the "
            "engine will not guess what a comparable unit asks. State the monthly "
            "market rent, or remove reset_hazard."
        )
    if "reset_market_escalation_rate" in data and reset_hazard <= 0:
        raise ConfigValidationError(
            "rent.reset_market_escalation_rate is set but rent.reset_hazard is 0, so "
            "there is no market track for it to grow and the figure would be ignored."
        )
    if reset_to is not None and reset_hazard <= 0:
        raise ConfigValidationError(
            "rent.reset_to_monthly_rent is set but rent.reset_hazard is 0, so the "
            "reset can never happen and the figure would be ignored. State the annual "
            "probability the tenancy ends, or remove reset_to_monthly_rent."
        )
    # Finite AND positive. `inf > 0` is True, so a bare positivity test lets an
    # infinite figure through validation and the run then dies in the read-back
    # formatter with an OverflowError — a crash where a refusal belongs.
    if reset_to is not None and not (0 < float(reset_to) < math.inf):
        raise ConfigValidationError(
            f"rent.reset_to_monthly_rent must be a positive number, got {reset_to}"
        )

    return RentParams(
        monthly_rent=float(data["monthly_rent"]),
        # FP Canada 2026 PAG shelter-cost growth 3.1% − 2.1% = 1.0% real
        rent_escalation_rate=conv.real(data, "rent_escalation_rate", "rent.rent_escalation_rate",
                                       ANCHORS["rent.rent_escalation_rate"].value),
        invested_down_payment=float(data.get("invested_down_payment", fallback)),
        # FP Canada 2026 PAG 60/40 ≈ 3.0% real
        investment_return_rate=conv.real(data, "investment_return_rate", "rent.investment_return_rate",
                                         ANCHORS["rent.investment_return_rate"].value),
        events=events,
        other_recurring_costs=other,
        reset_hazard=reset_hazard,
        reset_to_monthly_rent=None if reset_to is None else float(reset_to),
        reset_market_escalation_rate=conv.real(
            data, "reset_market_escalation_rate", "rent.reset_market_escalation_rate",
            ANCHORS["rent.rent_escalation_rate"].value),
    )


def _parse_income(data: Dict[str, Any], conv: RateConverter) -> IncomeParams:
    """Parse IncomeParams from YAML data."""
    if "annual_income" not in data:
        raise ConfigValidationError("income section missing required field: annual_income")
    events = [_parse_pay_drop_event(e) for e in data.get("pay_drop_events", [])]
    return IncomeParams(
        annual_income=float(data["annual_income"]),
        # FP Canada 2026 PAG salary growth 3.1% − 2.1% = 1.0% real
        income_growth_rate=conv.real(data, "income_growth_rate", "income.income_growth_rate",
                                     ANCHORS["income.income_growth_rate"].value),
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
        value_growth_vol=float(sim_data.get("value_growth_vol", 0.0)),
        investment_return_vol=float(sim_data.get("investment_return_vol", 0.0)),
    )


def _parse_economic(econ_data: Optional[Dict[str, Any]], rates: str) -> EconomicParams:
    """
    Parse economic parameters from YAML data.

    An omitted `inflation_rate` is the FP Canada planning figure when it is the
    deflator of as-quoted rates in real mode (`rates.default_inflation_rate`),
    else the real-mode inert zero — echoed under `defaults applied` either way.
    """
    if econ_data is None:
        econ_data = {}

    mode = econ_data.get("mode", "real")
    if mode not in ("nominal", "real"):
        raise ConfigValidationError(f"Invalid economic mode: {mode}. Must be 'nominal' or 'real'.")

    return EconomicParams(
        mode=mode,  # type: ignore
        inflation_rate=float(econ_data.get("inflation_rate", default_inflation_rate(mode, rates))),
        inflation_vol=float(econ_data.get("inflation_vol", 0.0)),
    )


def _capital_bound_message(name: str, opt: Any) -> str:
    """The down-payment bound refusal, in the inputs the user actually typed.

    A config stating `cash_available` never typed a down payment, so quoting
    one back at it is a dead end; the refusal names the pile, the costs netted
    out of it and the figure that resulted.
    """
    if opt.cash_available is None:
        return f"{name}: down_payment must be in [0, initial_value]"
    if opt.down_payment < 0:
        return (f"{name}: cash_available ${opt.cash_available:,.0f} does not cover "
                f"purchase_costs ${opt.purchase_costs:,.0f} — nothing is left for a down payment")
    return (f"{name}: cash_available ${opt.cash_available:,.0f} less purchase_costs "
            f"${opt.purchase_costs:,.0f} nets a down payment of ${opt.down_payment:,.0f}, "
            f"above the price ${opt.initial_value:,.0f}")


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

    # A quoted rate below inflation deflates to a negative real rate, which the
    # coherence warning names; only a factor (1 + dr) at or below zero is refused.
    if sim.discount_rate <= -1:
        warnings.append(f"discount_rate must be > -1 (> -100%), got {sim.discount_rate}")

    if sim.num_sims < 1:
        warnings.append(f"num_sims must be >= 1, got {sim.num_sims}")

    # Every volatility is a standard deviation, so every one refuses a negative.
    # Until 2026-09-21 only `other_cost_vol` and `inflation_vol` did, and the
    # other four accepted a negative and treated it as OFF — a figure the user
    # took the trouble to type that the engine silently ignored, which is the
    # failure the honesty contract cares most about. One rule, one place.
    for _name, _vol in (
        ("house_maintenance_vol", sim.house_maintenance_vol),
        ("condo_fee_vol", sim.condo_fee_vol),
        ("other_cost_vol", sim.other_cost_vol),
        ("rent_escalation_vol", sim.rent_escalation_vol),
        ("investment_return_vol", sim.investment_return_vol),
        ("value_growth_vol", sim.value_growth_vol),
    ):
        if _vol < 0:
            warnings.append(f"{_name} should be >= 0, got {_vol}")

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

    for _name, _opt in (("condo", spec.condo), ("house", spec.house)):
        if _opt is not None and _opt.purchase_costs < 0:
            warnings.append(f"{_name}.purchase_costs must be non-negative, got {_opt.purchase_costs}")
        if _opt is not None and _opt.financed_purchase_costs < 0:
            warnings.append(f"{_name}.financed_purchase_costs must be non-negative, got {_opt.financed_purchase_costs}")
        if _opt is not None and _opt.financed_purchase_costs > 0 and _opt.all_cash:
            warnings.append(f"{_name}.financed_purchase_costs requires a mortgage block (nothing to finance under all_cash)")

    if spec.rent is not None:
        rent = spec.rent
        if rent.monthly_rent <= 0:
            warnings.append(f"rent.monthly_rent must be positive, got {rent.monthly_rent}")
        # Hard units tripwire (20%/yr rent escalation reads as a percent typed
        # as a decimal); the plausibility band is the anchor's (0–2% real). The
        # spec holds REAL figures, and a sticker rate below inflation is a small
        # negative one, so the tripwire is on magnitude.
        if not (abs(rent.rent_escalation_rate) < 0.20):
            warnings.append(f"rent.rent_escalation_rate must be between -0.20 and 0.20, got {rent.rent_escalation_rate}")
        if rent.invested_down_payment < 0:
            warnings.append(f"rent.invested_down_payment must be non-negative, got {rent.invested_down_payment}")
        # Hard units tripwire; the plausibility band is the anchor's (2–5% real).
        if not (abs(rent.investment_return_rate) < 0.25):
            warnings.append(f"rent.investment_return_rate must be between -0.25 and 0.25, got {rent.investment_return_rate}")

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
            or opt.cash_available is not None
            or opt.mortgage_rate is not None
            or opt.mortgage_term_years is not None
        )
        if opt.all_cash:
            # all_cash XOR mortgage block: a mortgage field alongside all_cash is
            # ambiguous intent and must be rejected, not silently ignored.
            if mortgage_fields_set:
                warnings.append(
                    f"{name}: all_cash: true is set together with mortgage fields "
                    f"(down_payment / cash_available / mortgage_rate / mortgage_term_years); "
                    f"declare exactly one")
        else:
            if opt.down_payment is None or opt.mortgage_rate is None or opt.mortgage_term_years is None:
                warnings.append(
                    f"{name}: declare all_cash: true OR a mortgage block "
                    f"(down_payment OR cash_available, plus mortgage_rate + mortgage_term_years)")
            elif not (0 <= opt.down_payment <= opt.initial_value):
                warnings.append(_capital_bound_message(name, opt))
            elif opt.mortgage_rate < 0 or opt.mortgage_term_years <= 0:
                warnings.append(f"{name}: mortgage_rate >= 0 and mortgage_term_years > 0 required")
        # The renewal ladder needs something to renew: an all-cash purchase has
        # no rate contract at all, and a half-declared mortgage block has no
        # opening balance to re-amortize.
        if opt.mortgage_renewal_years is not None:
            if opt.all_cash:
                warnings.append(
                    f"{name}: mortgage_renewal_years={opt.mortgage_renewal_years} is set with "
                    f"all_cash: true — an all-cash purchase has no rate contract to renew; "
                    f"declare exactly one")
            elif (opt.down_payment is None or opt.mortgage_rate is None
                  or opt.mortgage_term_years is None):
                warnings.append(
                    f"{name}: mortgage_renewal_years={opt.mortgage_renewal_years} needs a "
                    f"mortgage block to renew (down_payment OR cash_available, plus "
                    f"mortgage_rate + mortgage_term_years)")
        if not (0 <= opt.selling_cost_rate < 1):
            warnings.append(f"{name}: selling_cost_rate must be in [0, 1)")

    _check_capital_structure("condo", spec.condo)
    _check_capital_structure("house", spec.house)

    return warnings


def _rates_of(data: Dict[str, Any]) -> str:
    try:
        return convention_of(data)
    except RateConventionError as exc:
        raise ConfigValidationError(str(exc)) from exc


def _build_spec(data: Dict[str, Any]) -> ComparisonSpec:
    """The one loader both entry points share: keys, jurisdictions, the rate
    convention, the sections, provenance, validation.

    Rates as quoted (2026-09-05): every typed growth, escalation, return and
    discount rate is converted ONCE here — deflated by inflation_rate in real
    mode, used as typed in nominal mode (the spec stores the real figure and the
    engines compose it back) — under the default `rates: as_quoted`; a config
    that states real figures says `rates: real` and is read as before. The
    discount rate anchor and every other anchored default stay real and compose
    in nominal mode exactly as they did (round-three evaluation 2026-09-02: the
    real anchor used as a nominal rate priced the future at ~0.9% real). Why the
    typed figure changed convention: served answers converted sticker numbers
    to real by hand and the engine composed inflation back on — one figure,
    inflated twice; and 2026-09-04's rule that a typed discount rate is real
    had assistants typing the real figure of a rate nobody quotes that way.
    """
    # Unknown-key diff runs before required-field checks so a typo (e.g.
    # 'yeers') gets a did-you-mean instead of a bare "missing field" refusal.
    _reject_unknown_keys(data)
    _refuse_boolean_jurisdictions(data)

    # Required top-level fields
    if "years" not in data:
        raise ConfigValidationError("Missing required field: years")
    years = int(data["years"])
    rates = _rates_of(data)
    econ = _parse_economic(data.get("economic"), rates)
    conv = RateConverter(rates, econ.mode, econ.inflation_rate)
    discount_rate = conv.discount_rate(data, ANCHORS["simulation.discount_rate"].value)

    # The tax treatment of the two sides' money (2026-09-05): resolved first,
    # because a first-time buyer's refunds and HBP withdrawal enter the option
    # parsers' day-one cash.
    tax = _parse_tax(data)
    condo = _parse_condo(data["condo"], years, conv, data.get("province"), tax) if "condo" in data else None
    house = _parse_house(data["house"], years, conv, data.get("province"), tax) if "house" in data else None
    # The renter's capital derived from the tax block's shares when the config
    # omits `rent.invested_down_payment` (2026-09-08); the echo says so.
    derived_capital = (tax.renter_capital.total
                       if tax is not None and tax.renter_capital is not None
                       and tax.renter_capital.total_derived else None)
    rent = _parse_rent(data["rent"], years, conv, derived_capital) if "rent" in data else None
    income = _parse_income(data["income"], conv) if "income" in data else None
    sim = _parse_simulation(data.get("simulation"), years, discount_rate)
    market_scenario = (
        _parse_market_scenario(data["market_scenario"]) if "market_scenario" in data else None
    )

    spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house, rent=rent, income=income,
                          market_scenario=market_scenario, tax=tax)
    spec.defaults_applied = _defaults_applied(data)
    spec.rates = rates
    spec.converted_rates = conv.converted
    # Source classes: who stated each value (2026-09-03). Parsed against the
    # config it describes, so a key the config does not set is refused here
    # rather than echoed as an attribution of nothing.
    derived_values = ({"rent.invested_down_payment": (derived_capital, "tax.renter_capital")}
                      if derived_capital is not None else None)
    spec.sources, source_problems = build_source_echo(data, derived_values=derived_values)
    if source_problems:
        raise ConfigValidationError("\n".join(source_problems))
    warnings = validate_config(spec)
    if warnings:
        raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))

    return spec


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

    return _build_spec(data)


def load_config_dict(data: Dict[str, Any]) -> ComparisonSpec:
    """
    Load configuration from a dictionary (useful for programmatic config).

    Args:
        data: Configuration dictionary (same structure as YAML)

    Returns:
        ComparisonSpec populated from the dictionary
    """
    return _build_spec(data)
