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
# A financed condo with nothing borrowed: its contract rate is stated and moves
# no present value, so the reversal register searches it and finds it inert.
INERT = copy.deepcopy(ALL_OTHER)
del INERT["condo"]["all_cash"]
INERT["condo"].update({"down_payment": 350000, "mortgage_rate": 0.045,
                       "mortgage_term_years": 25})
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


def _prior_no_rent() -> dict:
    """The showcase with no renter, and none of the renter's inputs or their
    sources."""
    raw = yaml.safe_load(SHOWCASE.read_text(encoding="utf-8"))
    renter = ("simulation.rent_escalation_vol", "simulation.investment_return_vol")
    del raw["rent"]
    raw["sources"] = {key: source for key, source in raw["sources"].items()
                      if not key.startswith("rent.") and key not in renter}
    for key in renter:
        raw["simulation"].pop(key.split(".", 1)[1], None)
    return raw


# The population prior with no renter priced: its rows reach the condo's and
# the house's values and the renter's none, so its widths print (§0.1 item 53's
# option map).
PRIOR_NO_RENT = _prior_no_rent()


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
    "near_none": (NEAR_NONE, "2000"),
    "near_all": (NEAR_ALL, "2000"),
    # The fixture at its own count of futures: the interval on the alone
    # shares' sum lies entirely above 1, so no residual clause prints.
    "fixture_own": (FIXTURE,),
    "rare2": (RARE2, "2000"),
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
