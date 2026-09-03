"""The input contract, emitted as data (agents query the living
schema; docs rot, this cannot). REQUIRED flags and NOTES are hand-curated beside
the machine key-sets; a test pins completeness against `_SECTION_KEYS` so a key
added to the parser without a schema entry fails the suite.
"""
from __future__ import annotations

from typing import Any, Dict

from .anchors import ANCHORS
from .config import _SECTION_KEYS

_NOMINAL_PLANNING = ANCHORS["economic.inflation_rate.nominal_planning"]

# Jurisdictions the registry has no source for, read OFF the registry so the
# note cannot claim "source: none" for a city that has since been sourced.
_UNSOURCED_JURISDICTIONS = ", ".join(
    name.split(".", 1)[1].replace("_", " ").title()
    for name, anchor in sorted(ANCHORS.items())
    if name.startswith("property_tax.") and anchor.kind == "unsourced"
)

# key -> (required?, note[, required_if]) per section; top-level scalars AND the
# section blocks themselves live under "top". `required` means "required when the
# block is present"; `required_if` states a conditional requirement in the
# validator's own words so the schema and the refusal can never disagree.
_NOTES: Dict[str, Dict[str, Any]] = {
    "top": {
        "years": (True, "analysis horizon in years (>=1)"),
        "discount_rate": (False, "annual discount rate, DECIMAL (0.05 = 5%); DEFAULT 0.03 "
                                  "real = the anchored investment return (FP Canada 2026 PAG "
                                  "60/40), the household's opportunity cost; "
                                "real terms if economic.mode=real (default); in nominal mode the "
                                 "DEFAULT composes with inflation_rate ((1+0.03)(1+π)−1) while a "
                                 "typed value is used as entered"),
        # Section blocks: all optional, but at least one option must be present;
        # a key marked required inside a block is required only when the block is.
        "condo": (False, "optional block — at least ONE of condo / house / rent must be "
                         "present; keys marked required apply only when the block is present"),
        "house": (False, "optional block — at least ONE of condo / house / rent must be present"),
        "rent": (False, "optional block — at least ONE of condo / house / rent must be present"),
        "income": (False, "optional block; enables affordability ratios"),
        "simulation": (False, "optional block; Monte Carlo + uncertainty knobs"),
        "economic": (False, "optional block; real (default) vs nominal mode"),
        "market_scenario": (False, "optional block; demographic prior (path + geography)"),
    },
    "condo": {
        "initial_value": (True, "purchase price in DOLLARS (480000, not 480)"),
        "value_growth_rate": (False, "annual REAL price growth, decimal; default 0.0 — "
                                       "neutral, no universal long-run real default; set "
                                       "your view or a market_scenario prior. With a prior, "
                                       "its drift is ADDED to this base in the Monte Carlo; "
                                       "the deterministic line uses this base alone"),
        "monthly_fee": (True, "condo fee, $/month — REQUIRED whenever a condo: block is "
                             "present; use 0 for a fee-free unit"),
        "fee_escalation_rate": (False, "annual fee growth, decimal; default 0.0"),
        "down_payment": (False, "$ paid at purchase; with mortgage_rate + mortgage_term_years "
                               "it is the capital structure", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "cash_available": (False, "$ of cash you bring to the closing table — an ALTERNATIVE to "
                                   "down_payment, never both: the engine nets purchase_costs out of "
                                   "it and the remainder IS the down payment (financed_purchase_costs "
                                   "ride the loan and are NOT netted). Use it when you know the pile "
                                   "rather than the split; the assumptions line shows the netting, and "
                                   "the loan-to-value and the 20% mortgage-insurance test read the "
                                   "computed figure. Like-for-like rent.invested_down_payment = this "
                                   "number", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_rate": (False, "EFFECTIVE ANNUAL rate, decimal, with ANNUAL level payments; "
                                "a Canadian posted rate is semi-annually compounded — convert: "
                                "r_eff = (1 + r_posted/2)^2 − 1", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_term_years": (False, "amortization term in years", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "all_cash": (False, "true = the whole price is paid at purchase, no financing", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026); "
                                       "dominates short horizons"),
        "purchase_costs": (False, "$ paid at purchase (year 0, undiscounted, outside the "
                                   "affordability ratio): land-transfer/welcome tax, notary, "
                                   "inspection, a mortgage-insurance premium paid in cash; "
                                   "default 0 — warns when an owned option models no purchase "
                                   "or carrying costs"),
        "financed_purchase_costs": (False, "$ rolled INTO THE LOAN at purchase — a financed "
                                            "mortgage-insurance premium (CMHC/Sagen, due under 20% "
                                            "down): raises the payment and the balance, never year-0 "
                                            "cash; requires the mortgage block; default 0"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs during "
                          "the horizon (roof, appliances, special assessment); purchase-time "
                          "costs belong in purchase_costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "property tax, home/unit insurance, utilities the "
                                         "owner pays; escalation_rate is REAL (composed with "
                                         "inflation in nominal mode). PROPERTY TAX AND HOME "
                                         "INSURANCE ARE YOUR OWN FIGURES — the engine applies "
                                         "no default for either. Published figures to check "
                                         "them against: `hde --print-anchors`, keys "
                                         "property_tax.<municipality> and "
                                         "home_insurance.<province>; a line named 'property "
                                         "tax' or 'insurance' is cited by name in the "
                                         "assumptions read-back when your figure equals a "
                                         "published one. Municipal rates are levied on "
                                         "ASSESSED value, which is not market value (Ontario's "
                                         "2026 assessments are January 2016 values), so a rate "
                                         "× purchase price is an approximation. Québec's "
                                         "school tax is a separate provincial levy on top "
                                         "of the municipal rate (school_tax.qc). No source "
                                         f"registered for: {_UNSOURCED_JURISDICTIONS}"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
        "reserve_contribution_rate": (False, "fraction of each year's fees set aside into the "
                                             "reserve fund; default 0 = reserve not modelled"),
        "reserve_initial_balance": (False, "$ in the reserve fund at year 0; default 0"),
        "reserve_growth_rate": (False, "annual growth on the reserve balance, decimal; default 0"),
    },
    "house": {
        "initial_value": (True, "purchase price in DOLLARS"),
        "value_growth_rate": (False, "annual REAL price growth, decimal; default 0.0 — "
                                       "neutral, no universal long-run real default; set "
                                       "your view or a market_scenario prior. With a prior, "
                                       "its drift is ADDED to this base in the Monte Carlo; "
                                       "the deterministic line uses this base alone"),
        "annual_maintenance_rate": (False, "fraction of value per year; DEFAULT 0.0 = no "
                                            "maintenance modelled (neutral, warns when omitted); "
                                            "NAHB 2019 AHS routine ≈ 0.6% of value/yr"),
        "maintenance_curve": (False, "list of {year, rate} overrides"),
        "down_payment": (False, "$ paid at purchase; with mortgage_rate + mortgage_term_years "
                               "it is the capital structure", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "cash_available": (False, "$ of cash you bring to the closing table — an ALTERNATIVE to "
                                   "down_payment, never both: the engine nets purchase_costs out of "
                                   "it and the remainder IS the down payment (financed_purchase_costs "
                                   "ride the loan and are NOT netted). Use it when you know the pile "
                                   "rather than the split; the assumptions line shows the netting, and "
                                   "the loan-to-value and the 20% mortgage-insurance test read the "
                                   "computed figure. Like-for-like rent.invested_down_payment = this "
                                   "number", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_rate": (False, "EFFECTIVE ANNUAL rate, decimal, with ANNUAL level payments; "
                                "a Canadian posted rate is semi-annually compounded — convert: "
                                "r_eff = (1 + r_posted/2)^2 − 1", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "mortgage_term_years": (False, "amortization term in years", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "all_cash": (False, "true = the whole price is paid at purchase, no financing", "owned option: declare all_cash: true OR the full mortgage block (down_payment OR cash_available, plus mortgage_rate + mortgage_term_years) — the two are exclusive"),
        "selling_cost_rate": (False, "fraction at sale; DEFAULT 0.05 — seller-side "
                                       "commissions 4–5% + notary (WOWA 2026)"),
        "purchase_costs": (False, "$ paid at purchase (year 0, undiscounted, outside the "
                                   "affordability ratio): land-transfer/welcome tax, notary, "
                                   "inspection, a mortgage-insurance premium paid in cash; "
                                   "default 0 — warns when an owned option models no purchase "
                                   "or carrying costs"),
        "financed_purchase_costs": (False, "$ rolled INTO THE LOAN at purchase — a financed "
                                            "mortgage-insurance premium (CMHC/Sagen, due under 20% "
                                            "down): raises the payment and the balance, never year-0 "
                                            "cash; requires the mortgage block; default 0"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs during "
                          "the horizon (roof, appliances, special assessment); purchase-time "
                          "costs belong in purchase_costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "property tax, home/unit insurance, utilities the "
                                         "owner pays; escalation_rate is REAL (composed with "
                                         "inflation in nominal mode). PROPERTY TAX AND HOME "
                                         "INSURANCE ARE YOUR OWN FIGURES — the engine applies "
                                         "no default for either. Published figures to check "
                                         "them against: `hde --print-anchors`, keys "
                                         "property_tax.<municipality> and "
                                         "home_insurance.<province>; a line named 'property "
                                         "tax' or 'insurance' is cited by name in the "
                                         "assumptions read-back when your figure equals a "
                                         "published one. Municipal rates are levied on "
                                         "ASSESSED value, which is not market value (Ontario's "
                                         "2026 assessments are January 2016 values), so a rate "
                                         "× purchase price is an approximation. Québec's "
                                         "school tax is a separate provincial levy on top "
                                         "of the municipal rate (school_tax.qc). No source "
                                         f"registered for: {_UNSOURCED_JURISDICTIONS}"),
        "price_shock": (False, "{annual_hazard, severity_mean, severity_vol}"),
    },
    "rent": {
        "monthly_rent": (True, "$/month"),
        "rent_escalation_rate": (False, "annual; DEFAULT 0.01 real (FP Canada 2026 "
                                          "PAG shelter-cost growth)"),
        "invested_down_payment": (False, "capital the renter keeps invested instead of buying: charged at year 0 like "
                                        "the buyer's down payment and credited at its terminal value; like-for-like "
                                        "= the buyer's TOTAL year-0 cash, down_payment + purchase_costs (all cash: "
                                        "price + purchase_costs); DEFAULT 0 = assume it earns exactly the discount rate"),
        "investment_return_rate": (False, "annual, REAL (composed with inflation in nominal "
                                            "mode like value growth); DEFAULT 0.03 (FP Canada "
                                            "2026 PAG 60/40)"),
        "events": (False, "list of {name, base_cost, expected_year, ...} — one-offs such as "
                          "moving costs"),
        "other_recurring_costs": (False, "list of {name, annual_amount, escalation_rate} — "
                                         "tenant insurance, parking, utilities the tenant pays. "
                                         "The home_insurance.* anchors are HOMEOWNER premiums "
                                         "and are deliberately never matched against a tenant "
                                         "policy: different product, different price"),
    },
    "economic": {
        "mode": (False, '"real" (DEFAULT — every rate you enter is real) or "nominal": '
                        'growth, escalation and return inputs (value, fee, rent, other, income, '
                        'investment_return_rate) stay REAL and the engine composes '
                        'inflation_rate on top of them, while discount_rate and mortgage_rate '
                        'are used as entered — never type a sticker growth rate into nominal mode'),
        "inflation_rate": (False, "ignored in real mode; DEFAULT 0.0 — nominal-mode "
                                    f"suggestion {_NOMINAL_PLANNING.value} ({_NOMINAL_PLANNING.short_cite})"),
        "inflation_vol": (False, "drives correlated cost shocks; default 0.0"),
    },
    "income": {
        "annual_income": (True, "$/year — REQUIRED whenever an income: block is present; "
                                "the block itself is optional (omit it to skip affordability)"),
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
        "house_maintenance_vol": (False, "annual vol of house maintenance (lognormal "
                                         "multiplicative shock); uncertainty knobs all "
                                         "default 0 = single-path run, NOT a forecast"),
        "condo_fee_vol": (False, "annual vol of condo fees; default 0 (see house_maintenance_vol)"),
        "other_cost_vol": (False, "annual vol of other recurring costs; default 0"),
        "rent_escalation_vol": (False, "vol of the rent escalation rate per path; default 0"),
        "investment_return_vol": (False, "ANNUAL volatility of the renter's gross return "
                                           "(one mean-preserving shock per year on 1 + r, so "
                                           "capital can end below principal): 0.10 ≈ a 60/40 "
                                           "portfolio, 0.16 ≈ all equities; default 0 = risk-free "
                                           "at investment_return_rate (asymmetric against an "
                                           "owned option with price_shock — the engine warns)"),
        "corr_inflation_house": (False, "correlation of house-maintenance shocks with the "
                                        "inflation shock, [-1, 1]; default 0; inert unless "
                                        "economic.inflation_vol > 0"),
        "corr_inflation_condo": (False, "correlation of condo-fee shocks with inflation, [-1, 1]; default 0"),
        "corr_inflation_other": (False, "correlation of other-cost shocks with inflation, [-1, 1]; default 0"),
        "corr_inflation_event_cost": (False, "correlation of event-cost shocks with inflation, [-1, 1]; default 0"),
        "shock_model": (False, '"lognormal" (default) or "normal"'),
    },
    "market_scenario": {
        "path": (True, "ScenarioPrior JSON (see examples/showcase_demographic_prior.yaml)"),
        "geography": (True, "exact string; the shipped prior (tests/fixtures/scenario_prior_golden.json) carries "
                            "HORS_RMR, LAVAL_RA13, MTL_ISLAND_RA06, MTL_RMR, QC_RMR — use the finest one that "
                            "contains the user's area; a refusal lists what the file has"),
    },
}


def input_schema() -> dict:
    """The full input contract as a dict (one section per YAML block)."""
    sections: Dict[str, Any] = {}
    for section, keys in _SECTION_KEYS.items():
        notes = _NOTES.get(section, {})
        block: Dict[str, Any] = {}
        for key in sorted(keys):
            required, note, *rest = notes.get(key, (False, ""))
            entry: Dict[str, Any] = {
                "required": bool(required),
                "note": note or "see examples/README.md",
            }
            if rest and rest[0]:
                # conditional requirement, quoting the validator's own sentence
                entry["required_if"] = rest[0]
            block[key] = entry
        sections[section] = block
    sections["top_level"] = {
        key: {"required": req, "note": note}
        for key, (req, note) in sorted(_NOTES["top"].items())
    }
    return sections
