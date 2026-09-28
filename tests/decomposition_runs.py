"""Real `--decompose` runs, priced once per test session and shared.

The block's sentence tests (`test_decomposition_sentences.py`) and its
contract tests (`test_decomposition_contract_doc.py`) read the same runs; each
run is the CLI's own output — `--json` and text — for one config, plus what
the test needs to re-derive a figure from the matrices behind it.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import io
import json
import pathlib
import sys
import tempfile
import types

import numpy as np
import yaml

from hde import decomposition_run as dr
from hde.decomposition import INCOME_STREAM_ID
from hde.cli import main as cli_main
from hde.config import load_config_dict
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "reference" / "API_CONTRACT.md"
FIXTURE = REPO / "tests" / "fixtures" / "uncertainty_surface.yaml"
MIN_INTERACTION = REPO / "tests" / "fixtures" / "min_interaction.yaml"
EXAMPLES = REPO / "examples"
MORTGAGE = EXAMPLES / "mortgage_house_vs_rent.yaml"
SHOWCASE = EXAMPLES / "showcase_demographic_prior.yaml"
ADVANCED = EXAMPLES / "advanced_config.yaml"
THREE = EXAMPLES / "rent_vs_condo_vs_house.yaml"
INCOME = EXAMPLES / "income_shock.yaml"
MONTREAL = EXAMPLES / "first_time_buyer_montreal.yaml"

# Every future names another option than the central case's winner: rent wins
# the central case on its starting rent, and a near-certain reset to a much
# higher one puts the condo in front on every path (P(f > 0) is exactly 0).
ALL_OTHER = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "events": [],
              "other_recurring_costs": [{"name": "property_tax", "annual_amount": 2600,
                                         "escalation_rate": 0.0}]},
    "rent": {"monthly_rent": 1150, "rent_escalation_rate": 0.0, "reset_hazard": 0.9,
             "reset_to_monthly_rent": 2500, "invested_down_payment": 355200,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 2000, "random_seed": 42, "condo_fee_vol": 0.02,
                   "rent_escalation_vol": 0.01},
}
# One priced option.
CONDO_ONLY = {k: copy.deepcopy(ALL_OTHER[k]) for k in ("years", "discount_rate",
                                                        "economic", "condo")}
CONDO_ONLY["simulation"] = {"num_sims": 2000, "random_seed": 42, "condo_fee_vol": 0.05}
# Futures exist, and no channel reaches a cash flow: real mode discards the
# inflation draw and every correlation is off, so the one channel that draws
# moves nothing.
NO_REACH = {k: copy.deepcopy(ALL_OTHER[k]) for k in ("years", "discount_rate", "condo")}
NO_REACH["economic"] = {"mode": "real", "inflation_rate": 0.0, "inflation_vol": 0.02}
NO_REACH["rent"] = {"monthly_rent": 1150, "rent_escalation_rate": 0.0,
                    "invested_down_payment": 355200, "investment_return_rate": 0.03}
NO_REACH["simulation"] = {"num_sims": 2000, "random_seed": 42}
# Two channels that draw and reach no cash flow beside two that do: the
# economy in real terms with one correlation ON and no shock behind it (no
# house is priced), and the housing market with a crash hazard of severity 0
# and no value volatility.
DEAD = copy.deepcopy(ALL_OTHER)
DEAD["economic"] = {"mode": "real", "inflation_rate": 0.0, "inflation_vol": 0.01}
DEAD["rent"].update({"reset_hazard": 0.05, "reset_to_monthly_rent": 1500})
DEAD["condo"]["price_shock"] = {"annual_hazard": 0.05, "severity_mean": 0.0,
                                "severity_vol": 0.1}
DEAD["simulation"].update({"condo_fee_vol": 0.10, "value_growth_vol": 0.0,
                           "corr_inflation_house": 0.5})
# A financed condo far enough ahead that no crossing of the central case's
# verdict lies anywhere in its contract rate's bracket.
FAR = copy.deepcopy(ALL_OTHER)
del FAR["condo"]["all_cash"]
FAR["condo"].update({"down_payment": 100000, "mortgage_rate": 0.045,
                     "mortgage_term_years": 25})
FAR["rent"].update({"monthly_rent": 4000, "reset_hazard": 0.0,
                    "rent_escalation_rate": 0.02})
del FAR["rent"]["reset_to_monthly_rent"]
FAR["simulation"]["rent_escalation_vol"] = 0.05
# A financed condo with nothing borrowed: its contract rate is stated and moves
# no present value, so the reversal register searches it and finds it inert.
INERT = copy.deepcopy(ALL_OTHER)
del INERT["condo"]["all_cash"]
INERT["condo"].update({"down_payment": 350000, "mortgage_rate": 0.045,
                       "mortgage_term_years": 25})
# The same financed condo nearer rent, with the renter's portfolio drawn: the
# central case's winner holds across the contract rate's whole bracket and its
# decisiveness does not, so the only crossing on the row is bisected.
SAMPLED_ONLY = copy.deepcopy(FAR)
SAMPLED_ONLY["rent"]["monthly_rent"] = 2400
SAMPLED_ONLY["simulation"].update({"rent_escalation_vol": 0.10,
                                   "investment_return_vol": 0.12})
# The one-side-of-the-line guard's two edges, each one future away from it:
# rent (the central case's winner) cheapest in exactly one of 2,000 futures,
# and the house cheapest in all but one. The spread register prints a table
# on both; a guard widened by any tolerance refuses one of them.
NEAR_NONE = copy.deepcopy(ALL_OTHER)
NEAR_NONE["rent"]["reset_hazard"] = 0.5
NEAR_ALL = yaml.safe_load(MORTGAGE.read_text(encoding="utf-8"))
NEAR_ALL["house"]["mortgage_rate"] = 0.0633
NEAR_ALL["simulation"].update({"random_seed": 8, "num_sims": 2000})
# Three options, the third far behind: only the renter's channels are live, and
# they move rent, which never enters the margin — so the margin is one figure
# on every future while two channels are live (spec §0.1 item 37).
THIRD_FAR = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"initial_value": 400000, "monthly_fee": 300, "fee_escalation_rate": 0.0,
              "all_cash": True, "purchase_costs": 5000, "value_growth_rate": 0.0},
    "house": {"initial_value": 450000, "all_cash": True, "purchase_costs": 5000,
              "annual_maintenance_rate": 0.01, "value_growth_rate": 0.0},
    "rent": {"monthly_rent": 6000, "rent_escalation_rate": 0.02,
             "invested_down_payment": 405000, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "rent_escalation_vol": 0.05,
                   "investment_return_vol": 0.10},
}
# The same, with one renter's channel live: one live channel that never moves
# the margin.
THIRD_FAR_ONE = copy.deepcopy(THIRD_FAR)
THIRD_FAR_ONE["rent"]["rent_escalation_rate"] = 0.0
del THIRD_FAR_ONE["simulation"]["rent_escalation_vol"]
THIRD_FAR_ONE["simulation"]["investment_return_vol"] = 0.02
# Futures exist only because the income pay-drop draws: no channel is live,
# while the affordability report moves with the draw.
INCOME_ONLY = {
    "years": 15, "discount_rate": 0.072,
    "condo": {"monthly_fee": 700, "fee_escalation_rate": 0.052, "initial_value": 500000,
              "all_cash": True, "purchase_costs": 7500},
    "rent": {"monthly_rent": 2500, "rent_escalation_rate": 0.062,
             "invested_down_payment": 500000, "investment_return_rate": 0.051},
    "income": {"annual_income": 120000, "income_growth_rate": 0.052,
               "affordability_threshold": 0.35,
               "pay_drop_events": [{"year": 3, "magnitude": 0.80, "year_jitter_std": 2,
                                    "magnitude_vol": 0.25}]},
    "simulation": {"num_sims": 2000, "random_seed": 42},
    "economic": {"mode": "real"},
}
# The same with the condo's fee drawn: one channel is live, and the pay-drop
# draw beside it.
INCOME_ONE_CHANNEL = copy.deepcopy(INCOME_ONLY)
INCOME_ONE_CHANNEL["simulation"]["condo_fee_vol"] = 0.05


def _rare_reset(*, one_channel: bool) -> dict:
    """The three-option example with a lease reset so rare that the tenancy
    is live on 5,000 futures and not on 40 (spec §0.1 item 48's witnesses).
    With `one_channel`, the house and the condo event's cost volatility are
    gone, so on 40 futures the condo's costs are the one live channel."""
    raw = yaml.safe_load(THREE.read_text(encoding="utf-8"))
    raw["rent"].update({"reset_hazard": 0.0005, "reset_to_monthly_rent": 3600})
    raw["sources"].update({"rent.reset_hazard": "assistant",
                           "rent.reset_to_monthly_rent": "user"})
    if one_channel:
        del raw["house"]
        del raw["simulation"]["house_maintenance_vol"]
        del raw["condo"]["events"][0]["cost_vol"]
        raw["sources"] = {key: source for key, source in raw["sources"].items()
                          if not key.startswith("house.")
                          and key != "simulation.house_maintenance_vol"}
    return raw


RARE_RESET_THREE = _rare_reset(one_channel=False)
RARE_RESET_ONE = _rare_reset(one_channel=True)

# A five-year house against rent on which the decisiveness verdict goes
# decisive for house, then not decisive, then decisive for rent, all between
# two neighbouring points of the 65-point scan (spec §0.1 item 47's witness).
# At the stated 4.40% the run is decisive for house, so the crossing out of
# its region is an upper edge; `DECISIVE_STEP_LOWER` states 8.00%, where the
# run is decisive for rent and the same stretch lies below a lower edge.
DECISIVE_STEP = {
    "years": 5,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "house": {"initial_value": 550000, "down_payment": 110000, "mortgage_rate": 0.044,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 2300, "rent_escalation_rate": 0.031,
             "invested_down_payment": 110000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 42, "house_maintenance_vol": 0.2,
                   "rent_escalation_vol": 0.05},
}
DECISIVE_STEP_LOWER = copy.deepcopy(DECISIVE_STEP)
DECISIVE_STEP_LOWER["house"]["mortgage_rate"] = 0.08
# The same house and rent with a condo priced near rent: as the house's rate
# rises, the option most futures call cheapest goes house, then condo, then
# rent, and the condo's stretch lies inside one cell of a ten-point scan.
THIRD_IN_ONE_CELL = copy.deepcopy(DECISIVE_STEP)
THIRD_IN_ONE_CELL["condo"] = {"monthly_fee": 1350, "fee_escalation_rate": 0.031,
                              "initial_value": 400000, "all_cash": True,
                              "purchase_costs": 6000, "value_growth_rate": 0.031}
THIRD_IN_ONE_CELL["simulation"].update({"condo_fee_vol": 0.3, "value_growth_vol": 0.02})

# A figure on a crossing's axis, printed on its side of the crossing (spec §0.1
# items 54 and 60). The decisiveness of `DECISIVE_STEP` goes decisive for house,
# not decisive, decisive for rent inside one printed step of a sampled
# crossing: the lower edge's `was` is a sliver narrower than 0.01%.
SLIVER_LOW = copy.deepcopy(DECISIVE_STEP_LOWER)
SLIVER_LOW["rent"]["monthly_rent"] = 2300.5
SLIVER_LOW["simulation"].update({"house_maintenance_vol": 0.015,
                                 "rent_escalation_vol": 0.004})
# Its upper-edge twin: the run is decisive for house, and the stretch that is
# not decisive lies above the edge, narrower than one printed step.
SLIVER_HIGH = copy.deepcopy(DECISIVE_STEP)
SLIVER_HIGH["simulation"].update({"house_maintenance_vol": 0.008,
                                  "rent_escalation_vol": 0.002})
# A stated rate above a solved crossing and below a sampled one, both within
# one printed step of it.
STATED_BESIDE_CROSSING = copy.deepcopy(DECISIVE_STEP)
STATED_BESIDE_CROSSING["house"]["mortgage_rate"] = 0.06273


def _near_ones(rate: float, rent: float, vols=(0.2, 0.05)) -> dict:
    """`DECISIVE_STEP` at a stated contract rate and a rent that puts the
    central case's crossing within a few billionths of a percent of it."""
    raw = copy.deepcopy(DECISIVE_STEP)
    raw["house"]["mortgage_rate"] = rate
    raw["rent"]["monthly_rent"] = rent
    raw["simulation"].update({"house_maintenance_vol": vols[0],
                              "rent_escalation_vol": vols[1]})
    return raw


# A stated rate below the central case's crossing by less than the old
# solver's tolerance, which left the crossing's figure below the stated one.
STATED_JUST_BELOW = _near_ones(0.0379, 1503.230397975693, (0.0002, 0.00005))
STATED_JUST_BELOW_B = _near_ones(0.06275, 2300.825245734851)
# A crossing just below a four-decimal figure: floored from a point above it,
# every figure read the other state.
CROSSING_BELOW_A_STEP = _near_ones(0.044, 2299.849758979105)
# A stated rate between the floored figures of a solved and a sampled crossing.
STATED_BETWEEN = _near_ones(0.03795, 1504.817709, (0.0002, 0.00005))
# A stated rate a hundred-trillionth of a percent below the mortgage example's
# central-case crossing: rounded at twelve decimals it lies above every
# floored figure of that crossing, so the crossing is not printed.
STATED_UNDER_A_CROSSING = yaml.safe_load(MORTGAGE.read_text(encoding="utf-8"))
STATED_UNDER_A_CROSSING["house"]["mortgage_rate"] = 0.0678488725623162
# A stated rate at the lower end of the bracket of `DECISIVE_STEP`'s sampled
# crossing, which that crossing's own floored figure prints below and the
# solved crossing's above: no rounding of it prints on its side of both, so
# the sampled crossing is not printed.
STATED_AT_A_SAMPLED_CROSSING = copy.deepcopy(DECISIVE_STEP)
STATED_AT_A_SAMPLED_CROSSING["house"]["mortgage_rate"] = 0.06278717945831885
# The same crossing with the stated rate 1e-13 under its lower end: every
# floored figure up to ten decimals, the finest its bracket allows, lies below
# the stated figure, so the crossing is not printed.
STATED_JUST_UNDER_A_SAMPLED_CROSSING = copy.deepcopy(DECISIVE_STEP)
STATED_JUST_UNDER_A_SAMPLED_CROSSING["house"]["mortgage_rate"] = 0.06278717945821885
# The same house against a rent so low that the house is the central case's
# winner only below about 1.02%, a few hundredths of a percent inside the
# bracket's low end.
CROSSING_NEAR_THE_LOW_END = copy.deepcopy(DECISIVE_STEP)
CROSSING_NEAR_THE_LOW_END["rent"]["monthly_rent"] = 646
# A rent that puts the central case's crossing at 6.24441%, and a stated rate
# at the upper end of its bracket, whose four-decimal figure is the crossing's
# own, so it prints at five.
STATED_JUST_ABOVE_A_CROSSING = copy.deepcopy(DECISIVE_STEP)
STATED_JUST_ABOVE_A_CROSSING["rent"]["monthly_rent"] = 2290.88
STATED_JUST_ABOVE_A_CROSSING["house"]["mortgage_rate"] = 0.062444104452362044
# A stated rate at the lower end of the mortgage example's sampled
# decisiveness crossing, which only that crossing's own figure prints beside.
STATED_AT_A_CROSSING_S_LOWER_END = yaml.safe_load(MORTGAGE.read_text(encoding="utf-8"))
STATED_AT_A_CROSSING_S_LOWER_END["house"]["mortgage_rate"] = 0.06736205021603381
# The same crossing with the stated rate inside its bracket, where the run is
# not decisive.
STATED_INSIDE_A_SAMPLED_CROSSING = yaml.safe_load(MORTGAGE.read_text(encoding="utf-8"))
STATED_INSIDE_A_SAMPLED_CROSSING["house"]["mortgage_rate"] = 0.06736205021662316
# A stated rate two floats under the central case's crossing, where the
# central case's winner is already rent.
STATED_TWO_FLOATS_UNDER_A_CROSSING = _near_ones(0.06582347916331133, 2400.9, (0.002, 0.05))
STATED_TWO_FLOATS_UNDER_A_CROSSING["simulation"]["random_seed"] = 7
# A stated rate at the high end of its bracket.
STATED_AT_THE_BRACKET_HIGH_END = copy.deepcopy(DECISIVE_STEP)
STATED_AT_THE_BRACKET_HIGH_END["house"]["mortgage_rate"] = 0.10
# The fixture with its first renewal rate just below the renewal key's
# central-case crossing: rounded to the nearest at two decimals, it would
# print above that crossing's figure.
PATH_NOTE_BELOW_A_CROSSING =yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
PATH_NOTE_BELOW_A_CROSSING["house"]["mortgage_renewal_rates"][0] = 0.016051
# A renewal ladder of one repeated rate one float under the central case's
# crossing, where this run's winner is already rent (spec §0.1 item 65).
LADDER_JUST_UNDER_A_CROSSING = {
    "years": 10,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "house": {"initial_value": 550000, "down_payment": 110000, "mortgage_rate": 0.0527,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "mortgage_renewal_years": 5,
              "mortgage_renewal_rates": [0.06715813612987188, 0.06715813612987188],
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 1837.96, "rent_escalation_rate": 0.031,
             "invested_down_payment": 110000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 7, "house_maintenance_vol": 0.002,
                   "rent_escalation_vol": 0.05},
}
# A reference just below the central case's crossing (spec §0.1 item 66).
REFERENCE_BESIDE_A_CROSSING = copy.deepcopy(DECISIVE_STEP)
REFERENCE_BESIDE_A_CROSSING["rent"]["monthly_rent"] = 1696.44
# Three options, where a decisiveness crossing is decisive for another option
# than this run's winner (spec §0.1 item 63): on the contract rate of a
# financed house beside a financed condo whose fee is drawn wide.
DECISIVE_FOR_ANOTHER = {
    "years": 5,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "condo": {"initial_value": 400000, "down_payment": 80000, "mortgage_rate": 0.05,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "monthly_fee": 1254.1807, "fee_escalation_rate": 0.03, "purchase_costs": 6000,
              "value_growth_rate": 0.031},
    "house": {"initial_value": 550000, "down_payment": 110000, "mortgage_rate": 0.08,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 2300, "rent_escalation_rate": 0.031,
             "invested_down_payment": 110000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 7, "condo_fee_vol": 4.0,
                   "house_maintenance_vol": 0.02, "rent_escalation_vol": 0.005},
}
# The same three options with the condo's contract rate two floats under its
# own solved crossing: on the house's contract rate, the central case's winner
# at the lower end of a solved crossing's bracket is not the one the stretch
# below that crossing reads.
THREE_WAY_TIE = copy.deepcopy(DECISIVE_FOR_ANOTHER)
THREE_WAY_TIE["condo"]["mortgage_rate"] = 0.04999962040678628
# The fixture with a dearer house on 60 futures: the renewal ladder's
# decisiveness crossing is decisive for the house while this run's winner is
# rent.
DECISIVE_FOR_THE_HOUSE = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
DECISIVE_FOR_THE_HOUSE["simulation"]["num_sims"] = 60
DECISIVE_FOR_THE_HOUSE["house"].update({"initial_value": 580000, "down_payment": 116000})
del DECISIVE_FOR_THE_HOUSE["sources"]["house.other_recurring_costs.property_tax.annual_amount"]
# The fixture with its renewals at or past the amortization: the ladder it
# states moves no present value (spec §0.1 item 64).
INERT_LADDER = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
INERT_LADDER["house"]["mortgage_renewal_years"] = 25
# A figure on the axis other than the stated one, inside a sampled crossing's
# bracket where the futures read that crossing's `becomes` (spec §0.1 item
# 60): the contracted rate the fixture states and cites, beside renewals at one
# rate, and the first rate of a ladder.
REFERENCE_INSIDE_A_SAMPLED_CROSSING = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
REFERENCE_INSIDE_A_SAMPLED_CROSSING["house"]["mortgage_renewal_rates"] = [
    0.027164030806393624] * 4
PATH_FIGURE_INSIDE_A_SAMPLED_CROSSING = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
PATH_FIGURE_INSIDE_A_SAMPLED_CROSSING["house"]["mortgage_renewal_rates"] = [
    0.02716403080667974, 0.05, 0.048, 0.02954943580452318]
# A house bought outright beside a ladder it states: neither of its two
# financing keys moves a present value, so both are refused rows.
TWO_REFUSED = {
    "years": 20,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "house": {"initial_value": 550000, "down_payment": 550000, "mortgage_rate": 0.044,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "mortgage_renewal_years": 5, "mortgage_renewal_rates": [0.05, 0.055],
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 2300, "rent_escalation_rate": 0.031,
             "invested_down_payment": 550000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 300, "random_seed": 42, "house_maintenance_vol": 0.3,
                   "rent_escalation_vol": 0.01},
}
# The same house on a loan of one dollar: its contract rate moves the house's
# present value by less than a dollar, and it is an exact row.
ONE_DOLLAR_LOAN = copy.deepcopy(TWO_REFUSED)
del ONE_DOLLAR_LOAN["house"]["mortgage_renewal_years"]
del ONE_DOLLAR_LOAN["house"]["mortgage_renewal_rates"]
ONE_DOLLAR_LOAN["house"]["down_payment"] = 549999
ONE_DOLLAR_LOAN["rent"]["invested_down_payment"] = 549999
# A crossing whose figure is checked AT that figure (spec §0.1 items 54 and
# 60): a billionth of the figure above it, the field reads the crossing's
# `becomes`, a sampled crossing's and a solved one's.
SAMPLED_JUST_ABOVE_ITS_FIGURE = copy.deepcopy(DECISIVE_STEP)
SAMPLED_JUST_ABOVE_ITS_FIGURE["rent"]["monthly_rent"] = 2299.343123435974
SOLVED_JUST_ABOVE_ITS_FIGURE = copy.deepcopy(DECISIVE_STEP)
SOLVED_JUST_ABOVE_ITS_FIGURE["rent"]["monthly_rent"] = 2299.199459552765
# And a billionth of the figure below it, a state other than the crossing's
# `was`.
SAMPLED_WAS_JUST_UNDER_ITS_FIGURE = copy.deepcopy(SLIVER_LOW)
SAMPLED_WAS_JUST_UNDER_ITS_FIGURE["rent"]["monthly_rent"] = 2303.615429943832
SOLVED_WAS_JUST_UNDER_ITS_FIGURE = copy.deepcopy(DECISIVE_STEP_LOWER)
SOLVED_WAS_JUST_UNDER_ITS_FIGURE["rent"]["monthly_rent"] = 2299.21875
SOLVED_WAS_JUST_UNDER_ITS_FIGURE["condo"] = {
    "monthly_fee": 1211.688020825386, "fee_escalation_rate": 0.031, "initial_value": 400000,
    "all_cash": True, "purchase_costs": 6000, "value_growth_rate": 0.031}
# Level rows a fraction of a dollar each (spec §0.1 item 62's witness): at
# whole dollars no row's pair shows its judgment.
LEVEL_UNDER_A_DOLLAR = {
    "years": 5,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "condo": {"monthly_fee": 380.296648, "fee_escalation_rate": 0.021,
              "initial_value": 420000, "all_cash": True, "purchase_costs": 6000,
              "value_growth_rate": 0.031},
    "house": {"initial_value": 550000, "down_payment": 110000, "mortgage_rate": 0.038,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 1506.398161, "rent_escalation_rate": 0.031,
             "invested_down_payment": 110000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 42, "house_maintenance_vol": 0.0002,
                   "rent_escalation_vol": 0.00005, "condo_fee_vol": 0.0002},
}

# What a width names (spec §0.1 item 49): every input that sized a draw on the
# run, and nothing else.
# A price shock stating only its hazard: the severity it draws is sized by the
# two anchored defaults the read-back lists under `defaults applied`.
HAZARD_ONLY = yaml.safe_load(THREE.read_text(encoding="utf-8"))
HAZARD_ONLY["condo"]["price_shock"] = {"annual_hazard": 0.05}
HAZARD_ONLY["sources"]["condo.price_shock.annual_hazard"] = "assistant"
HAZARD_ONLY["simulation"]["num_sims"] = 400
# A correlation onto the condo's fee on a run that prices no condo.
CORRELATION_UNPRICED_CONDO = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0, "inflation_vol": 0.02},
    "house": {"initial_value": 450000, "all_cash": True, "purchase_costs": 5000,
              "annual_maintenance_rate": 0.01, "value_growth_rate": 0.0},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01,
             "invested_down_payment": 455000, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "house_maintenance_vol": 0.2,
                   "condo_fee_vol": 0.1, "corr_inflation_condo": 0.5,
                   "corr_inflation_house": 0.5, "rent_escalation_vol": 0.05},
}
# Its mirror: a correlation onto the house's maintenance with no house priced.
CORRELATION_UNPRICED_HOUSE = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0, "inflation_vol": 0.02},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.0},
    "rent": {"monthly_rent": 1400, "rent_escalation_rate": 0.01,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 200, "random_seed": 42, "condo_fee_vol": 0.1,
                   "house_maintenance_vol": 0.2, "corr_inflation_condo": 0.5,
                   "corr_inflation_house": 0.5, "rent_escalation_vol": 0.05},
}
# Correlations onto other cost lines and events that no draw of this run
# reaches: the renter's one cost line is not drawn at an other-cost volatility
# of zero, the house holds no cost line, and no option holds an event. The
# variants give each correlation a shock it does pull.
CORRELATIONS_PULL_NOTHING = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0, "inflation_vol": 0.02},
    "house": {"initial_value": 450000, "all_cash": True, "purchase_costs": 5000,
              "annual_maintenance_rate": 0.01, "value_growth_rate": 0.0},
    "rent": {"monthly_rent": 1450, "rent_escalation_rate": 0.01,
             "invested_down_payment": 455000, "investment_return_rate": 0.03,
             "other_recurring_costs": [{"name": "tenant_insurance", "annual_amount": 300,
                                        "escalation_rate": 0.0}]},
    "simulation": {"num_sims": 200, "random_seed": 42, "house_maintenance_vol": 0.2,
                   "rent_escalation_vol": 0.05, "other_cost_vol": 0.0,
                   "corr_inflation_house": 0.5, "corr_inflation_other": 0.4,
                   "corr_inflation_event_cost": 0.3},
}
RENTER_LINE_DRAWN = copy.deepcopy(CORRELATIONS_PULL_NOTHING)
RENTER_LINE_DRAWN["simulation"]["other_cost_vol"] = 0.1
OWNED_LINE = copy.deepcopy(CORRELATIONS_PULL_NOTHING)
OWNED_LINE["house"]["other_recurring_costs"] = [
    {"name": "property_tax", "annual_amount": 3000, "escalation_rate": 0.0}]
OWNED_LINE["rent"]["monthly_rent"] = 1700
OWNED_EVENT = copy.deepcopy(CORRELATIONS_PULL_NOTHING)
OWNED_EVENT["house"]["events"] = [
    {"name": "roof_replacement", "base_cost": 20000, "expected_year": 12, "cost_vol": 0.15}]
OWNED_EVENT["rent"]["monthly_rent"] = 1500

# A width is a structural fact (spec §0.1 item 53): a sizing input of a
# channel's draws, for an option the run prices, as the read-back states or
# defaults it — whether or not the draw fires. Each config below states an
# input whose draw never fires on the run, and its width prints all the same.
# The condo's one event has a hazard that starts after the horizon.
EV_LATE_START = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "nominal", "inflation_rate": 0.02, "inflation_vol": 0.02},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.02,
              "events": [{"name": "roof_replacement", "base_cost": 15000, "cost_vol": 0.2,
                          "expected_year": 20, "timing_model": "hazard",
                          "hazard_base": 0.05, "hazard_growth": 0.01,
                          "hazard_start_year": 25}]},
    "rent": {"monthly_rent": 1400, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42, "condo_fee_vol": 0.1,
                   "value_growth_vol": 0.05, "investment_return_vol": 0.05,
                   "rent_escalation_vol": 0.05, "corr_inflation_event_cost": 0.5},
}
# A cost line on the condo and none on the house, one other-cost volatility.
LINES_CONDO_ONLY = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.01,
              "other_recurring_costs": [{"name": "property_tax", "annual_amount": 2600,
                                         "escalation_rate": 0.0}]},
    "house": {"initial_value": 400000, "value_growth_rate": 0.01,
              "annual_maintenance_rate": 0.012, "all_cash": True, "purchase_costs": 6000},
    "simulation": {"num_sims": 400, "random_seed": 42, "house_maintenance_vol": 0.30,
                   "condo_fee_vol": 0.1, "other_cost_vol": 0.1},
}
# The same condo against rent, the house's volatility still stated: the one
# owned option priced is the condo, so which channel is whose option shows.
LINES_CONDO_NO_HOUSE = copy.deepcopy(LINES_CONDO_ONLY)
del LINES_CONDO_NO_HOUSE["house"]
LINES_CONDO_NO_HOUSE["condo"]["events"] = []     # an events list with no entry
LINES_CONDO_NO_HOUSE["rent"] = {"monthly_rent": 1300, "rent_escalation_rate": 0.01,
                                "invested_down_payment": 355200,
                                "investment_return_rate": 0.03}
LINES_CONDO_NO_HOUSE["simulation"]["investment_return_vol"] = 0.05
# A crash hazard of zero, and its two severities defaulted.
HAZARD_ZERO = copy.deepcopy(HAZARD_ONLY)
HAZARD_ZERO["condo"]["price_shock"] = {"annual_hazard": 0.0}
HAZARD_ZERO["simulation"]["value_growth_vol"] = 0.05
HAZARD_ZERO["sources"]["simulation.value_growth_vol"] = "assistant"
# A lease-reset hazard of zero.
RESET_ZERO = copy.deepcopy(HAZARD_ONLY)
RESET_ZERO["rent"]["reset_hazard"] = 0.0
RESET_ZERO["simulation"]["rent_escalation_vol"] = 0.03
# A value volatility of zero beside a live crash.
VALUE_VOL_ZERO = copy.deepcopy(HAZARD_ONLY)
VALUE_VOL_ZERO["simulation"]["value_growth_vol"] = 0.0
# M28 with a value volatility, which sizes the house's draws with no condo
# priced, and a correlation of zero onto the house's maintenance: the rho and
# the shock it pulls are widths at rho squared 0, on a row whose re-draw moves
# nothing.
UNPRICED_CONDO_ZERO_RHO = copy.deepcopy(CORRELATION_UNPRICED_CONDO)
UNPRICED_CONDO_ZERO_RHO["simulation"].update({"corr_inflation_house": 0.0,
                                              "value_growth_vol": 0.05})
# A house price shock stating its hazard alone, beside the condo's: all four
# defaulted severities, each with the cite the read-back gives it.
BOTH_SHOCKS_DEFAULTED = copy.deepcopy(HAZARD_ONLY)
BOTH_SHOCKS_DEFAULTED["house"]["price_shock"] = {"annual_hazard": 0.04}
BOTH_SHOCKS_DEFAULTED["sources"]["house.price_shock.annual_hazard"] = "assistant"

# A crash in every year of every future, at one fixed severity: the margin is
# one figure on every future, and below zero, so the identical-margin
# reason's sign has a witness (spec §0.1 item 44).
CRASH_EVERY_YEAR = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200, "value_growth_rate": 0.02,
              "price_shock": {"annual_hazard": 1.0, "severity_mean": 0.3,
                              "severity_vol": 0.0}},
    "rent": {"monthly_rent": 1400, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42},
}

# Rent cheapest in 1,998 of the level's 2,000 futures, and in 1,999 of them with
# the tenancy frozen: probabilities a hair under one (spec §0.1 item 51).
NEAR_ONE = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "nominal", "inflation_rate": 0.0, "inflation_vol": 0.02},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200,
              "other_recurring_costs": [{"name": "property_tax", "annual_amount": 2600,
                                         "escalation_rate": 0.0}]},
    "rent": {"monthly_rent": 1400, "rent_escalation_rate": 0.0,
             "invested_down_payment": 355200, "investment_return_rate": 0.03},
    "simulation": {"num_sims": 2000, "random_seed": 42, "condo_fee_vol": 0.05,
                   "rent_escalation_vol": 0.10},
}


# Two rare hazards, one on the condo's price and one on the lease: the margin
# is one figure on almost every future. At 400 futures one of the bootstrap's
# resamples holds one figure, and the block refuses (`degenerate_resample`,
# §0.1 item 58); at 2,000 it prints, and the condo's costs draw, move nothing
# and have no width, so their row names no keys.
RARE2 = {
    "years": 10, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.0, "initial_value": 350000,
              "all_cash": True, "purchase_costs": 5200,
              "price_shock": {"annual_hazard": 0.0005}},
    "rent": {"monthly_rent": 1500, "rent_escalation_rate": 0.01, "reset_hazard": 0.0005,
             "reset_to_monthly_rent": 2500, "invested_down_payment": 355200,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 400, "random_seed": 42},
}


# Three options, the condo's costs dominant: on 200 futures at this seed the
# condo's alone share lies inside [0, 1] and its share with interaction above
# 1, so the with-interaction half of the row rule alone keeps that row
# unresolved (spec §0.1 item 11).
TOGETHER_ABOVE_ONE = {
    "years": 20,
    "economic": {"mode": "nominal", "inflation_rate": 0.021},
    "condo": {"monthly_fee": 450, "fee_escalation_rate": 0.021, "initial_value": 420000,
              "all_cash": True, "purchase_costs": 6000, "value_growth_rate": 0.031},
    "house": {"initial_value": 550000, "down_payment": 110000, "mortgage_rate": 0.03,
              "mortgage_rate_compounding": "effective_annual", "mortgage_term_years": 25,
              "purchase_costs": 8200, "value_growth_rate": 0.031,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 2300, "rent_escalation_rate": 0.031,
             "invested_down_payment": 110000, "investment_return_rate": 0.051},
    "simulation": {"num_sims": 400, "random_seed": 1, "house_maintenance_vol": 0.2,
                   "rent_escalation_vol": 0.05, "condo_fee_vol": 0.1},
}


def _prior_without(option: str, simulation_keys: tuple) -> dict:
    """The showcase with no `option`, and none of that option's inputs or
    their sources."""
    raw = yaml.safe_load(SHOWCASE.read_text(encoding="utf-8"))
    del raw[option]
    raw["sources"] = {key: source for key, source in raw["sources"].items()
                      if not key.startswith(f"{option}.") and key not in simulation_keys}
    for key in simulation_keys:
        raw["simulation"].pop(key.split(".", 1)[1], None)
    return raw


# The population prior with no renter priced: its rows reach the condo's and
# the house's values and the renter's none, so its widths print (§0.1 item 53's
# option map).
PRIOR_NO_RENT = _prior_without(
    "rent", ("simulation.rent_escalation_vol", "simulation.investment_return_vol"))
# The population prior beside ONE owned option, each way: its rows reach both
# owned options' values, so its widths print beside either one alone.
PRIOR_NO_CONDO = _prior_without(
    "condo", ("simulation.condo_fee_vol", "simulation.corr_inflation_condo"))
PRIOR_NO_HOUSE = _prior_without(
    "house", ("simulation.house_maintenance_vol", "simulation.corr_inflation_house"))


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

def _cli(*argv):
    """`hde <argv>` in this process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["hde", *map(str, argv)]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main()
    finally:
        sys.argv = saved
    return code, out.getvalue(), err.getvalue()


def _strict(text):
    def refuse(token):
        raise ValueError(f"non-finite token {token!r} in the document")
    return json.loads(text, parse_constant=refuse)


def _sweep_states(path, key, values, futures):
    """What `--sweep <key>=<values>` says at each value, field by field, in
    the words a boundary uses; `futures` runs the sweep with Monte Carlo. Each
    value is typed at its full `repr`, so two adjacent floats stay two."""
    argv = [path, "--sweep", f"{key}=" + ",".join(repr(float(v)) for v in values), "--json"]
    if not futures:
        argv.insert(1, "--no-monte-carlo")
    code, out, _ = _cli(*argv)
    assert code == 0
    rows = _strict(out)["sweeps"][0]["rows"]
    assert [row["value"] for row in rows] == [float(v) for v in values], rows
    return [{"best": r["best"], "runner_up": r["runner_up"], "mc_best": r["mc_best"],
             "decisive": f"decisive for {r['best']}" if r["decisive"] else "not decisive"}
            for r in rows]


def _block_text(out):
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if "which risk decides it" in line or "all of this run's spread" in line)
    return "\n".join(lines[start:])


class Run:
    """One config run twice through the CLI — `--json` and text — with the
    raw mapping and the inputs the assembler was handed, for re-derivation."""

    def __init__(self, source, *extra):
        """`source` is a config file, run as it is, or a mapping, written to
        a file of its own first."""
        self.source = source
        self.raw = (_load(source) if isinstance(source, pathlib.Path)
                    else copy.deepcopy(source))
        self.extra = extra
        self._path = None

    def materialise(self, directory):
        if isinstance(self.source, pathlib.Path):
            path = self.source
        else:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "config.yaml"
            path.write_text(yaml.safe_dump(self.raw, sort_keys=False), encoding="utf-8")
        self._path = path
        code, out, _ = _cli(path, "--decompose", *self.extra, "--json")
        assert code == 0, out
        self.doc = _strict(out)
        self.block = self.doc["decomposition"]
        code, out, _ = _cli(path, "--decompose", *self.extra, "-q")
        assert code == 0
        self.text = _block_text(out)
        self.spec = load_config_dict(self.raw)
        return self

    @property
    def path(self):
        return self._path

    def inputs(self):
        spec = self.spec
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        verdict = compute_verdict(det, mc, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        return det, mc, verdict

    def paths(self):
        return int(self.block["paths"])

    def f_a(self):
        best = self.doc["verdict"]["best"]
        spec = dr._spec_at(self.spec, self.paths())
        return dr.margin_per_path(dr._run(spec, dr.MATRIX_A), best)


def _load(path):
    return yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Forcing a check no correct engine fails (§0.1 item 58)
# ---------------------------------------------------------------------------

def force_income_move(monkeypatch, move):
    """The income stream's re-draw handed back as `A`'s own present values
    moved by `move` on every future, for every priced option."""
    original = dr._redraws

    def redraws(spec_at_paths, drawn):
        out = original(spec_at_paths, drawn)
        if INCOME_STREAM_ID in out:
            base = dr._run(spec_at_paths, dr.MATRIX_A)
            out[INCOME_STREAM_ID] = types.SimpleNamespace(**{
                name: (None if getattr(base, name, None) is None else types.SimpleNamespace(
                    pvs=np.asarray(getattr(base, name).pvs, dtype=np.float64) + move))
                for name in ("condo", "house", "rent")})
        return out
    monkeypatch.setattr(dr, "_redraws", redraws)


def untag(monkeypatch, key=None):
    """The read-back's tag withheld from `key`, or from every key."""
    import hde.serialization as serialization
    original = serialization.read_back_tag
    monkeypatch.setattr(serialization, "read_back_tag",
                        lambda spec, name: None if key in (None, name)
                        else original(spec, name))


# The runs every sentence and contract test reads: name -> (config, extra flags).
CORPUS = {
    "fixture": (FIXTURE, "300"),
    "mortgage": (MORTGAGE, "200"),
    "showcase": (SHOWCASE, "2000"),
    "min": (MIN_INTERACTION,),
    "advanced": (ADVANCED, "400"),
    # The economy's interaction gap resolves here with its interval's low end
    # a few thousandths above zero: the gap rule's narrow edge.
    "advanced_4000": (ADVANCED, "4000"),
    "three": (THREE, "300"),
    "all_other": (ALL_OTHER, "400"),
    "basic": (EXAMPLES / "basic_config.yaml", "300"),
    "dead": (DEAD, "300"),
    "far": (FAR, "200"),
    "inert": (INERT, "200"),
    "sampled_only": (SAMPLED_ONLY, "200"),
    "near_none": (NEAR_NONE, "2000"),
    "near_all": (NEAR_ALL, "2000"),
    # The fixture at its own count of futures: the interval on the alone
    # shares' sum lies entirely above 1, so no residual clause prints.
    "fixture_own": (FIXTURE,),
    "rare2": (RARE2, "2000"),
    "together_above_one": (TOGETHER_ABOVE_ONE, "200"),
    "decisive_step": (DECISIVE_STEP,),
    "decisive_step_lower": (DECISIVE_STEP_LOWER,),
    "path_note_below": (PATH_NOTE_BELOW_A_CROSSING, "300"),
    # A figure on a crossing's axis beside the crossing (spec §0.1 items 54
    # and 60), and a crossing no figure prints for (§0.1 item 61).
    "stated_just_below": (STATED_JUST_BELOW,),
    "stated_just_below_b": (STATED_JUST_BELOW_B,),
    "crossing_below_a_step": (CROSSING_BELOW_A_STEP,),
    "stated_between": (STATED_BETWEEN,),
    "stated_beside_crossing": (STATED_BESIDE_CROSSING,),
    "sliver_low": (SLIVER_LOW,),
    "sliver_high": (SLIVER_HIGH,),
    "stated_under_a_crossing": (STATED_UNDER_A_CROSSING, "200"),
    "stated_at_a_sampled_crossing": (STATED_AT_A_SAMPLED_CROSSING,),
    "stated_just_under_a_sampled_crossing": (STATED_JUST_UNDER_A_SAMPLED_CROSSING,),
    "crossing_near_the_low_end": (CROSSING_NEAR_THE_LOW_END,),
    "stated_just_above_a_crossing": (STATED_JUST_ABOVE_A_CROSSING,),
    "stated_at_a_crossing_s_lower_end": (STATED_AT_A_CROSSING_S_LOWER_END, "200"),
    "stated_inside_a_sampled_crossing": (STATED_INSIDE_A_SAMPLED_CROSSING, "200"),
    "stated_two_floats_under_a_crossing": (STATED_TWO_FLOATS_UNDER_A_CROSSING, "100"),
    "stated_at_the_bracket_high_end": (STATED_AT_THE_BRACKET_HIGH_END,),
    "ladder_just_under_a_crossing": (LADDER_JUST_UNDER_A_CROSSING,),
    "reference_beside_a_crossing": (REFERENCE_BESIDE_A_CROSSING,),
    # A decisiveness crossing identified on its own option (spec §0.1 item
    # 63), and a stated key no crossing moves (item 64).
    "decisive_for_another": (DECISIVE_FOR_ANOTHER, "100"),
    "three_way_tie": (THREE_WAY_TIE, "100"),
    "decisive_for_the_house": (DECISIVE_FOR_THE_HOUSE,),
    "inert_ladder": (INERT_LADDER, "300"),
    "two_refused": (TWO_REFUSED,),
    "one_dollar_loan": (ONE_DOLLAR_LOAN,),
    # A crossing's figure, checked at that figure (items 54 and 60).
    "sampled_just_above_its_figure": (SAMPLED_JUST_ABOVE_ITS_FIGURE,),
    "solved_just_above_its_figure": (SOLVED_JUST_ABOVE_ITS_FIGURE,),
    "sampled_was_just_under_its_figure": (SAMPLED_WAS_JUST_UNDER_ITS_FIGURE,),
    "solved_was_just_under_its_figure": (SOLVED_WAS_JUST_UNDER_ITS_FIGURE,),
    "reference_inside_a_sampled_crossing": (REFERENCE_INSIDE_A_SAMPLED_CROSSING, "300"),
    "path_figure_inside_a_sampled_crossing": (PATH_FIGURE_INSIDE_A_SAMPLED_CROSSING, "300"),
    # A level row's digits (spec §0.1 item 62).
    "pull_nothing": (CORRELATIONS_PULL_NOTHING,),
    "level_under_a_dollar": (LEVEL_UNDER_A_DOLLAR,),
}


# Where a mapping-sourced run writes its config; removed when the process ends.
_SCRATCH = tempfile.TemporaryDirectory(prefix="hde-decompose-runs-")


@functools.lru_cache(maxsize=None)
def run(name: str) -> "Run":
    """One corpus run, priced on first use and kept for the session."""
    source, *extra = CORPUS[name]
    return Run(source, *extra).materialise(pathlib.Path(_SCRATCH.name) / name)


def corpus():
    return {name: run(name) for name in CORPUS}
