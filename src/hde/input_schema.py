"""The input contract, emitted as data (TOOL-SURFACES: agents query the living
schema; docs rot, this cannot). REQUIRED flags and NOTES are hand-curated beside
the machine key-sets; a test pins completeness against `_SECTION_KEYS` so a key
added to the parser without a schema entry fails the suite.
"""
from __future__ import annotations

from typing import Any, Dict

from .anchors import ANCHORS
from .config import _SECTION_KEYS

_NOMINAL_PLANNING = ANCHORS["economic.inflation_rate.nominal_planning"]

# key -> (required?, note) per section; top-level scalars included as a section.
_NOTES: Dict[str, Dict[str, Any]] = {
    "top": {
        "years": (True, "analysis horizon in years (>=1)"),
        "discount_rate": (True, "annual discount rate, DECIMAL (0.05 = 5%); "
                                "real terms if economic.mode=real (default)"),
    },
    "condo": {
        "initial_value": (True, "purchase price in DOLLARS (480000, not 480)"),
        "value_growth_rate": (False, "annual REAL price growth, decimal; default 0.0 — "
                                       "neutral, no universal long-run real default; set "
                                       "your view or a market_scenario prior"),
        "monthly_fee": (False, "condo fee, $/month; default 0"),
        "fee_escalation_rate": (False, "annual fee growth, decimal; default 0.0"),
        "down_payment": (False, "with mortgage_rate+term: capital structure"),
        "mortgage_rate": (False, "annual rate, decimal"),
        "mortgage_term_years": (False, "amortization term"),
        "all_cash": (False, "no financing; XOR with mortgage fields"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026); "
                                       "dominates short horizons"),
        "events": (False, "list of {name, base_cost, expected_year, ...}"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate}"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
    },
    "house": {
        "initial_value": (True, "purchase price in DOLLARS"),
        "value_growth_rate": (False, "annual REAL price growth, decimal; default 0.0 — "
                                       "neutral, no universal long-run real default; set "
                                       "your view or a market_scenario prior"),
        "annual_maintenance_rate": (False, "fraction of value per year; DEFAULT 0.0 = no "
                                            "maintenance modelled (neutral, warns when omitted); "
                                            "NAHB 2019 AHS routine ≈ 0.6% of value/yr"),
        "maintenance_curve": (False, "list of {year, rate} overrides"),
        "down_payment": (False, "with mortgage_rate+term: capital structure"),
        "mortgage_rate": (False, "annual rate, decimal"),
        "mortgage_term_years": (False, "amortization term"),
        "all_cash": (False, "no financing; XOR with mortgage fields"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026)"),
        "events": (False, "list of {name, base_cost, expected_year, ...}"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate}"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
    },
    "rent": {
        "monthly_rent": (True, "$/month"),
        "rent_escalation_rate": (False, "annual; DEFAULT 0.01 real (FP Canada 2026 "
                                          "PAG shelter-cost growth)"),
        "invested_down_payment": (False, "capital the renter invests instead; "
                                        "DEFAULT 0 — set it or the comparison is "
                                        "not like-for-like"),
        "investment_return_rate": (False, "annual; DEFAULT 0.03 real (FP Canada 2026 "
                                            "PAG 60/40)"),
        "events": (False, "list of {name, base_cost, expected_year, ...}"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate}"),
    },
    "economic": {
        "mode": (False, '"real" (DEFAULT — growth/discount must be real) or "nominal"'),
        "inflation_rate": (False, "ignored in real mode; DEFAULT 0.0 — nominal-mode "
                                    f"suggestion {_NOMINAL_PLANNING.value} ({_NOMINAL_PLANNING.short_cite})"),
        "inflation_vol": (False, "drives correlated cost shocks; default 0.0"),
    },
    "income": {
        "annual_income": (False, "enables affordability reporting"),
        "income_growth_rate": (False, "annual; DEFAULT 0.01 real (FP Canada 2026 PAG "
                                        "salary growth)"),
        "affordability_threshold": (False, "cost/income ratio; DEFAULT 0.32 (legacy GDS "
                                             "32%, below CMHC's 39% cap)"),
        "pay_drop_events": (False, "list of {year, magnitude, year_jitter_std, magnitude_vol}; "
                                    "magnitude = retained-income fraction in (0, 1] (0.8 = 20% "
                                    "cut); shocked draws are clamped to [0.01, 1.0]"),
    },
    "simulation": {
        "num_sims": (False, "Monte Carlo paths; default 10,000"),
        "random_seed": (False, "default 42 — same seed, same answer"),
        "house_maintenance_vol": (False, "uncertainty knobs: all default 0 = "
                                         "single-path run, NOT a forecast"),
        "shock_model": (False, '"lognormal" (default) or "normal"'),
    },
    "market_scenario": {
        "path": (True, "ScenarioPrior JSON (see examples/showcase_demographic_prior.yaml)"),
        "geography": (True, "exact string, e.g. MTL_RMR; refusal lists what exists"),
    },
}


def input_schema() -> dict:
    """The full input contract as a dict (one section per YAML block)."""
    sections: Dict[str, Any] = {}
    for section, keys in _SECTION_KEYS.items():
        notes = _NOTES.get(section, {})
        sections[section] = {
            key: {
                "required": bool(notes.get(key, (False, ""))[0]),
                "note": notes.get(key, (False, ""))[1] or "see docs/examples",
            }
            for key in sorted(keys)
        }
    sections["top_level"] = {
        key: {"required": req, "note": note}
        for key, (req, note) in sorted(_NOTES["top"].items())
    }
    return sections
