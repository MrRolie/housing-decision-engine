"""
The source-class echo (2026-09-03): every value in a config carries who put it
there — the user, the assistant answering for them, or a cited anchor — so the
read-back can tell one from the other.

Five dogfood reviews found the same failure: numbers the assistant typed on the
user's behalf (a 0% rent escalation, `investment_return_vol: 0.10`, a 25-year
amortization) left no trace — they are not `defaults applied` (the YAML DID
state them) and fired no warning, and in three of five answers the Monte Carlo
"too close to call" verdict rested entirely on assistant-typed volatility the
user never saw. These tests pin the block, the four echo lines, the JSON shape
and the one warning that names the unstated uncertainty.
"""

import copy

import pytest

from hde.config import (
    ConfigValidationError,
    load_config_dict,
    single_path_run,
    uncertainty_source_warnings,
)
from hde.deterministic import compute_deterministic
from hde.models import compute_verdict
from hde.monte_carlo import run_monte_carlo
from hde.serialization import assumptions_to_dict, format_assumptions
from hde.sources import attributable_keys, format_source_value, uncertainty_keys

# Uncertainty ON (investment_return_vol), so Monte Carlo decides the verdict.
BASE = {
    "years": 10,
    "discount_rate": 0.03,
    # declared real: the anchor declarations below state the anchors' own real
    # figures (the as-quoted comparison is pinned in test_rates.py, 2026-09-05)
    "rates": "real",
    "condo": {"initial_value": 300_000, "monthly_fee": 400, "all_cash": True},
    "rent": {"monthly_rent": 1_500, "invested_down_payment": 300_000,
             "investment_return_rate": 0.03},
    "simulation": {"num_sims": 200, "random_seed": 7, "investment_return_vol": 0.10},
}

ALL_KEYS = [
    "years", "discount_rate", "rates",
    "condo.initial_value", "condo.monthly_fee", "condo.all_cash",
    "rent.monthly_rent", "rent.invested_down_payment", "rent.investment_return_rate",
    "simulation.num_sims", "simulation.random_seed", "simulation.investment_return_vol",
]


def cfg(sources=None, **overrides):
    data = copy.deepcopy(BASE)
    for key, value in overrides.items():
        data[key] = value
    if sources is not None:
        data["sources"] = sources
    return data


def lines(data):
    return format_assumptions(load_config_dict(data))


def line_starting(data, prefix):
    hits = [ln for ln in lines(data) if ln.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


# ---------------------------------------------------------------------------
# 1. The block: what it accepts and the three refusals
# ---------------------------------------------------------------------------

class TestBlockParsing:
    def test_the_three_forms_parse(self):
        spec = load_config_dict(cfg({
            "rent.monthly_rent": "user",
            "simulation.investment_return_vol": "assistant",
            "rent.investment_return_rate": "anchor:rent.investment_return_rate",
        }))
        echo = spec.sources
        assert echo.declared is True
        assert echo.classify("rent.monthly_rent") == "user"
        assert echo.classify("simulation.investment_return_vol") == "assistant"
        assert echo.classify("rent.investment_return_rate") == "anchor"
        assert echo.anchor_name("rent.investment_return_rate") == "rent.investment_return_rate"

    def test_no_block_leaves_every_key_unattributed(self):
        spec = load_config_dict(cfg())
        assert spec.sources.declared is False
        assert [e.key for e in spec.sources.entries] == ALL_KEYS
        assert all(e.source == "unattributed" for e in spec.sources.entries)

    def test_a_key_not_set_in_the_config_is_refused(self):
        # condo is all-cash: mortgage_rate is a real schema key, but this config
        # does not state it, so there is nothing to attribute.
        with pytest.raises(ConfigValidationError, match="condo.mortgage_rate"):
            load_config_dict(cfg({"condo.mortgage_rate": "user"}))

    def test_a_typo_gets_a_did_you_mean(self):
        with pytest.raises(ConfigValidationError, match=r"did you mean 'rent.monthly_rent'"):
            load_config_dict(cfg({"rent.montly_rent": "user"}))

    def test_a_container_key_is_not_attributable(self):
        # 'condo' IS set — saying "not a value this config states" would be the
        # untrue refusal; it is a block, and the refusal points at its leaves.
        with pytest.raises(ConfigValidationError,
                           match=r"'condo' is a block, not a value.*condo.initial_value"):
            load_config_dict(cfg({"condo": "user"}))

    def test_a_value_outside_the_three_forms_is_refused(self):
        with pytest.raises(ConfigValidationError, match="'user', 'assistant' or 'anchor:"):
            load_config_dict(cfg({"rent.monthly_rent": "guess"}))

    def test_a_non_string_value_is_refused(self):
        with pytest.raises(ConfigValidationError, match="'user', 'assistant' or 'anchor:"):
            load_config_dict(cfg({"rent.monthly_rent": 3}))

    def test_an_unknown_anchor_name_is_refused(self):
        with pytest.raises(ConfigValidationError, match="unknown anchor 'rent.no_such_rate'"):
            load_config_dict(cfg({"rent.monthly_rent": "anchor:rent.no_such_rate"}))

    def test_an_unknown_anchor_gets_a_did_you_mean(self):
        with pytest.raises(ConfigValidationError, match=r"did you mean 'rent.investment_return_rate'"):
            load_config_dict(cfg({"rent.monthly_rent": "anchor:rent.investment_return_rat"}))

    def test_a_non_mapping_block_is_refused(self):
        with pytest.raises(ConfigValidationError, match="sources"):
            load_config_dict(cfg(sources=["rent.monthly_rent"]))

    def test_the_block_changes_no_number(self):
        plain = compute_deterministic(load_config_dict(cfg()))
        attributed = compute_deterministic(load_config_dict(cfg({
            k: "user" for k in ALL_KEYS
        })))
        assert plain.condo.total_pv == attributed.condo.total_pv
        assert plain.rent.total_pv == attributed.rent.total_pv


# ---------------------------------------------------------------------------
# 2. The echo lines
# ---------------------------------------------------------------------------

class TestAssumptionLines:
    def test_no_block_says_so_in_one_line(self):
        line = line_starting(cfg(), "sources:")
        assert line == ("sources: none declared — the read-back cannot tell the "
                        "user's numbers from the assistant's")
        assert not any(ln.startswith(("user-stated:", "assistant-typed:",
                                      "anchor-sourced:", "unattributed:"))
                       for ln in lines(cfg()))

    def test_user_stated_line(self):
        data = cfg({"rent.monthly_rent": "user", "years": "user"})
        line = line_starting(data, "user-stated:")
        assert line == "user-stated: years=10, rent.monthly_rent=$1,500/mo"

    def test_assistant_typed_line(self):
        data = cfg({"simulation.investment_return_vol": "assistant"})
        assert (line_starting(data, "assistant-typed:")
                == "assistant-typed: simulation.investment_return_vol=10.0%")

    def test_anchor_sourced_line_names_the_anchor(self):
        data = cfg({"rent.investment_return_rate": "anchor:rent.investment_return_rate"})
        assert (line_starting(data, "anchor-sourced:")
                == "anchor-sourced: rent.investment_return_rate=3.0% "
                   "[rent.investment_return_rate]")

    def test_unattributed_line_lists_what_the_block_left_out(self):
        data = cfg({"rent.monthly_rent": "user"})
        line = line_starting(data, "unattributed:")
        assert "rent.monthly_rent" not in line
        assert "condo.monthly_fee=$400/mo" in line
        assert "simulation.investment_return_vol=10.0%" in line

    def test_a_fully_attributed_config_has_no_unattributed_line(self):
        data = cfg({k: "user" for k in ALL_KEYS})
        assert not any(ln.startswith("unattributed:") for ln in lines(data))
        assert not any(ln.startswith("sources: none declared") for ln in lines(data))

    def test_values_are_in_the_configs_own_units(self):
        assert format_source_value("rent.monthly_rent", 1500) == "$1,500/mo"
        assert format_source_value("condo.initial_value", 300000) == "$300,000"
        assert format_source_value("simulation.investment_return_vol", 0.1) == "10.0%"
        assert format_source_value("house.mortgage_term_years", 25) == "25"
        assert format_source_value("simulation.num_sims", 10000) == "10,000"
        assert format_source_value("condo.all_cash", True) == "true"
        assert format_source_value("economic.mode", "real") == "'real'"
        assert format_source_value("house.events", [{"name": "roof"}]) == "1 entry"
        assert format_source_value("house.events", [{}, {}]) == "2 entries"


# ---------------------------------------------------------------------------
# 3. The JSON shape
# ---------------------------------------------------------------------------

class TestJsonShape:
    def test_sources_block_shape(self):
        spec = load_config_dict(cfg({
            "rent.monthly_rent": "user",
            "simulation.investment_return_vol": "assistant",
            "rent.investment_return_rate": "anchor:rent.investment_return_rate",
        }))
        doc = assumptions_to_dict(spec)["sources"]
        assert set(doc) == {"declared", "user", "assistant", "anchor", "unattributed", "sweep"}
        assert doc["sweep"] == []  # only a grid point of a scan carries a swept key
        assert doc["declared"] is True
        assert doc["user"] == [{"key": "rent.monthly_rent", "value": 1500,
                                "formatted": "$1,500/mo"}]
        assert doc["assistant"] == [{"key": "simulation.investment_return_vol",
                                     "value": 0.10, "formatted": "10.0%"}]
        assert doc["anchor"] == {"rent.investment_return_rate": "rent.investment_return_rate"}
        assert {e["key"] for e in doc["unattributed"]} == set(ALL_KEYS) - {
            "rent.monthly_rent", "simulation.investment_return_vol",
            "rent.investment_return_rate"}
        for entry in doc["unattributed"]:
            assert set(entry) == {"key", "value", "formatted"}

    def test_no_block_json(self):
        doc = assumptions_to_dict(load_config_dict(cfg()))["sources"]
        assert doc["declared"] is False
        assert doc["user"] == [] and doc["assistant"] == [] and doc["anchor"] == {}
        assert [e["key"] for e in doc["unattributed"]] == ALL_KEYS


# ---------------------------------------------------------------------------
# 4. The warning: decisiveness resting on numbers the user never stated
# ---------------------------------------------------------------------------

def run(data):
    spec = load_config_dict(data)
    det = compute_deterministic(spec)
    mc = run_monte_carlo(spec)
    verdict = compute_verdict(det, mc, years=spec.simulation.years,
                              discount_rate=spec.simulation.discount_rate,
                              single_path=single_path_run(spec))
    return spec, det, verdict


class TestUncertaintyWarning:
    def test_fires_when_monte_carlo_decides_and_the_vol_is_unattributed(self):
        spec, det, verdict = run(cfg())
        assert verdict.rule == "mc_floor"
        warns = uncertainty_source_warnings(spec, det, verdict)
        assert len(warns) == 1
        assert warns[0].startswith("decisiveness rests on uncertainty inputs the user did not state:")
        assert "simulation.investment_return_vol=10.0% (unattributed)" in warns[0]

    def test_names_an_assistant_typed_input_as_assistant(self):
        spec, det, verdict = run(cfg({"simulation.investment_return_vol": "assistant"}))
        warns = uncertainty_source_warnings(spec, det, verdict)
        assert "simulation.investment_return_vol=10.0% (assistant)" in warns[0]

    def test_carries_the_deterministic_line(self):
        spec, det, verdict = run(cfg())
        clause = uncertainty_source_warnings(spec, det, verdict)[0].split("—", 1)[1]
        det_only = compute_verdict(det, None, years=spec.simulation.years,
                                   discount_rate=spec.simulation.discount_rate)
        assert f"the deterministic line alone says {det_only.best}" in clause
        assert f"${det_only.margin_pv:,.0f}" in clause
        assert ("decisive under the 5% band" in clause)
        assert (("not decisive" in clause) is (not det_only.decisive))

    def test_silent_when_every_uncertainty_input_is_user_stated(self):
        spec, det, verdict = run(cfg({"simulation.investment_return_vol": "user"}))
        assert uncertainty_source_warnings(spec, det, verdict) == []

    def test_silent_when_every_key_is_user_stated(self):
        spec, det, verdict = run(cfg({k: "user" for k in ALL_KEYS}))
        assert uncertainty_source_warnings(spec, det, verdict) == []

    def test_silent_without_monte_carlo(self):
        spec = load_config_dict(cfg())
        det = compute_deterministic(spec)
        verdict = compute_verdict(det, None, years=spec.simulation.years,
                                  discount_rate=spec.simulation.discount_rate)
        assert verdict.rule == "margin_band"
        assert uncertainty_source_warnings(spec, det, verdict) == []

    def test_silent_on_a_single_path_run(self):
        data = cfg()
        data["simulation"].pop("investment_return_vol")
        spec, det, verdict = run(data)
        assert single_path_run(spec)
        assert verdict.rule == "margin_band"
        assert uncertainty_source_warnings(spec, det, verdict) == []

    def test_names_price_shock_and_event_uncertainty_too(self):
        data = cfg()
        data["condo"]["price_shock"] = {"annual_hazard": 0.03, "severity_mean": 0.20,
                                        "severity_vol": 0.10}
        data["condo"]["events"] = [{"name": "assessment", "base_cost": 15000,
                                    "expected_year": 5, "cost_vol": 0.2}]
        data["sources"] = {"simulation.investment_return_vol": "user"}
        spec, det, verdict = run(data)
        text = uncertainty_source_warnings(spec, det, verdict)[0]
        assert "condo.price_shock.annual_hazard=3.0% (unattributed)" in text
        assert "condo.events=1 entry" in text
        assert "cost_vol 20.0%" in text
        assert "simulation.investment_return_vol" not in text


# ---------------------------------------------------------------------------
# 5. The uncertainty-input set is the engine's own definition
# ---------------------------------------------------------------------------

class TestUncertaintyKeysMirrorSinglePath:
    """Whatever `uncertainty_keys` names must be exactly what stops
    `single_path_run` — one definition of "widens the distribution", so the
    warning can never miss an input the engine treats as uncertainty."""

    RICH = {
        "years": 10,
        "condo": {
            "initial_value": 300_000, "monthly_fee": 400, "all_cash": True,
            "price_shock": {"annual_hazard": 0.03, "severity_mean": 0.2, "severity_vol": 0.1},
            "events": [{"name": "assessment", "base_cost": 10_000,
                        "expected_year": 5, "cost_vol": 0.2, "timing_std_years": 2}],
        },
        "house": {"initial_value": 400_000, "all_cash": True,
                  "annual_maintenance_rate": 0.01},
        "rent": {"monthly_rent": 1_500},
        "income": {"annual_income": 90_000,
                   "pay_drop_events": [{"year": 4, "magnitude": 0.8,
                                        "magnitude_vol": 0.1, "year_jitter_std": 1}]},
        "economic": {"inflation_vol": 0.01},
        "simulation": {"num_sims": 50, "house_maintenance_vol": 0.2,
                       "condo_fee_vol": 0.05, "other_cost_vol": 0.05,
                       "rent_escalation_vol": 0.01, "investment_return_vol": 0.1},
    }

    def test_a_rich_config_is_not_single_path(self):
        assert not single_path_run(load_config_dict(copy.deepcopy(self.RICH)))

    def test_turning_off_every_named_key_makes_it_single_path(self):
        data = copy.deepcopy(self.RICH)
        named = uncertainty_keys(data)
        assert named, "the detector named nothing in a config full of uncertainty"
        for key in named:
            parts = key.split(".")
            block = data
            for part in parts[:-1]:
                block = block[part]
            leaf = block[parts[-1]]
            if isinstance(leaf, list):
                block[parts[-1]] = []
            else:
                block[parts[-1]] = 0.0
        assert single_path_run(load_config_dict(data)), named

    def test_market_scenario_counts_as_uncertainty(self):
        # The prior draws demographic drift per path — `single_path_run` says so,
        # and the detector must agree.
        data = copy.deepcopy(self.RICH)
        data["market_scenario"] = {"path": "tests/fixtures/scenario_prior_golden.json",
                                   "geography": "MTL_RMR"}
        assert "market_scenario.path" in uncertainty_keys(data)

    def test_every_named_key_is_attributable(self):
        data = copy.deepcopy(self.RICH)
        assert set(uncertainty_keys(data)) <= set(attributable_keys(data))


# ---------------------------------------------------------------------------
# Summed anchor declarations (2026-09-04)
#
# A Québec owner's property-tax rate is the municipal rate PLUS the province's
# school rate. Both halves are anchored, so the declaration must be able to say
# so — and name both, rather than degrade to `assistant`.
# ---------------------------------------------------------------------------

SUM_DECL = "anchor:property_tax.laval+school_tax.qc"


def _tax_cfg(source):
    return {
        "years": 10,
        "house": {"initial_value": 600_000, "all_cash": True,
                  "property_tax_rate": 0.0066989},
        "rent": {"monthly_rent": 2_000},
        "sources": {"house.property_tax_rate": source},
    }


class TestSummedAnchorDeclarations:
    def test_a_sum_of_two_registered_names_is_accepted(self):
        spec = load_config_dict(_tax_cfg(SUM_DECL))
        echo = spec.sources
        assert echo.classify("house.property_tax_rate") == "anchor"
        assert echo.anchor_name("house.property_tax_rate") == (
            "property_tax.laval+school_tax.qc")

    def test_the_echo_prints_both_anchors(self):
        line = [ln for ln in format_assumptions(load_config_dict(_tax_cfg(SUM_DECL)))
                if ln.startswith("anchor-sourced:")]
        assert line == ["anchor-sourced: house.property_tax_rate=0.7% "
                        "[property_tax.laval+school_tax.qc]"]

    def test_the_json_echo_carries_both_anchors(self):
        doc = assumptions_to_dict(load_config_dict(_tax_cfg(SUM_DECL)))
        assert doc["sources"]["anchor"] == {
            "house.property_tax_rate": "property_tax.laval+school_tax.qc"}

    def test_each_name_in_a_sum_is_validated(self):
        with pytest.raises(ConfigValidationError, match="unknown anchor 'school_tax.zz'"):
            load_config_dict(_tax_cfg("anchor:property_tax.laval+school_tax.zz"))

    def test_a_typo_in_a_summed_name_gets_a_did_you_mean(self):
        with pytest.raises(ConfigValidationError, match=r"did you mean 'school_tax.qc'"):
            load_config_dict(_tax_cfg("anchor:property_tax.laval+school_tax.q"))

    def test_an_empty_half_is_refused(self):
        with pytest.raises(ConfigValidationError, match="'user', 'assistant' or 'anchor:"):
            load_config_dict(_tax_cfg("anchor:property_tax.laval+"))

    def test_whitespace_around_each_half_is_tolerated(self):
        spec = load_config_dict(_tax_cfg("anchor: property_tax.laval + school_tax.qc "))
        assert spec.sources.anchor_name("house.property_tax_rate") == (
            "property_tax.laval+school_tax.qc")

    def test_the_posted_mortgage_rate_can_be_declared(self):
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "down_payment": 200_000,
                      "mortgage_rate": 0.0618272, "mortgage_term_years": 25},
            "rent": {"monthly_rent": 2_000},
            "sources": {"house.mortgage_rate": "anchor:mortgage_rate.posted_5y"},
        })
        assert spec.sources.anchor_name("house.mortgage_rate") == "mortgage_rate.posted_5y"


# ---------------------------------------------------------------------------
# A declaration is validated by FIGURE, not just by name (2026-09-04)
#
# `anchor:property_tax.quebec_city` was accepted on a 0.82539% rate — the
# anchor publishes 0.7464% — and the same run printed "anchor-sourced" beside
# "no anchor match" for the one number. A name-only check lets a declaration
# claim provenance the figure does not have, which is worse than no block at
# all: it dresses an assistant's estimate as a cited one.
# ---------------------------------------------------------------------------

class TestDeclarationsAreValidatedByFigure:
    def test_the_right_name_on_the_wrong_figure_is_refused(self):
        with pytest.raises(ConfigValidationError,
                           match="house.property_tax_rate.*property_tax.quebec_city"):
            load_config_dict(_tax_cfg("anchor:property_tax.quebec_city"))

    def test_the_refusal_names_both_figures(self):
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict(_tax_cfg("anchor:property_tax.quebec_city"))
        message = str(excinfo.value)
        assert "0.007464" in message      # what the anchor publishes
        assert "0.0066989" in message     # what the config states

    def test_a_second_plausible_name_is_refused_on_the_same_figure(self):
        with pytest.raises(ConfigValidationError, match="property_tax.toronto"):
            load_config_dict(_tax_cfg("anchor:property_tax.toronto"))

    def test_the_matching_figure_is_still_accepted(self):
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True,
                      "property_tax_rate": 0.007464},
            "rent": {"monthly_rent": 2_000},
            "sources": {"house.property_tax_rate": "anchor:property_tax.quebec_city"},
        })
        assert spec.sources.anchor_name("house.property_tax_rate") == "property_tax.quebec_city"

    def test_a_summed_declaration_is_checked_against_the_sum(self):
        with pytest.raises(ConfigValidationError, match="property_tax.montreal"):
            load_config_dict(_tax_cfg("anchor:property_tax.montreal+school_tax.qc"))

    def test_a_source_none_anchor_cannot_be_declared(self):
        """Gatineau holds no figure at all; a declaration pointing at it would
        cite an absence as a source."""
        with pytest.raises(ConfigValidationError, match="source: none"):
            load_config_dict(_tax_cfg("anchor:property_tax.gatineau"))

    def test_the_window_is_the_matcher_s_own_half_basis_point(self):
        near = 0.0066989 + 4e-6
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "all_cash": True,
                      "property_tax_rate": near},
            "rent": {"monthly_rent": 2_000},
            "sources": {"house.property_tax_rate": SUM_DECL},
        })
        assert spec.sources.classify("house.property_tax_rate") == "anchor"
        with pytest.raises(ConfigValidationError, match="property_tax.laval"):
            load_config_dict({
                "years": 10,
                "house": {"initial_value": 600_000, "all_cash": True,
                          "property_tax_rate": 0.0066989 + 5e-5},
                "rent": {"monthly_rent": 2_000},
                "sources": {"house.property_tax_rate": SUM_DECL},
            })

    def test_a_nominal_inflation_declaration_is_pointed_at_the_sibling_anchor(self):
        """`economic.inflation_rate` publishes 0.0 — the real-mode inert value.
        A nominal config stating 2.1% and declaring that anchor is refused on
        the figure; the refusal names the sibling that DOES hold 2.1% rather
        than leaving the user to find it (round-9 review)."""
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict({
                "years": 10,
                "economic": {"mode": "nominal", "inflation_rate": 0.021},
                "house": {"initial_value": 600_000, "all_cash": True},
                "rent": {"monthly_rent": 2_000},
                "sources": {"economic.inflation_rate": "anchor:economic.inflation_rate"},
            })
        message = str(excinfo.value)
        assert "economic.inflation_rate.nominal_planning" in message
        assert "2.1%" in message

    def test_real_mode_gets_the_sibling_hint_too(self):
        """The planning figure is the deflator of as-quoted rates in real mode
        (2026-09-05), so the hint is no longer a nominal-mode fact."""
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict({
                "years": 10,
                "economic": {"mode": "real", "inflation_rate": 0.021},
                "house": {"initial_value": 600_000, "all_cash": True},
                "rent": {"monthly_rent": 2_000},
                "sources": {"economic.inflation_rate": "anchor:economic.inflation_rate"},
            })
        assert "nominal_planning" in str(excinfo.value)

    def test_a_non_numeric_value_cannot_be_anchor_sourced(self):
        with pytest.raises(ConfigValidationError, match="condo.all_cash"):
            load_config_dict(cfg({"condo.all_cash": "anchor:rent.investment_return_rate"}))

    def test_the_posted_mortgage_rate_is_accepted_at_its_effective_restatement(self):
        """6.09% posted is quoted semi-annually compounded; `mortgage_rate` is
        an effective annual rate. They are one figure in two conventions, and
        the registry says so — so the effective form is a valid declaration."""
        spec = load_config_dict({
            "years": 10,
            "house": {"initial_value": 600_000, "down_payment": 200_000,
                      "mortgage_rate": 0.0618270225, "mortgage_term_years": 25},
            "rent": {"monthly_rent": 2_000},
            "sources": {"house.mortgage_rate": "anchor:mortgage_rate.posted_5y"},
        })
        assert spec.sources.anchor_name("house.mortgage_rate") == "mortgage_rate.posted_5y"

    def test_a_rate_that_is_neither_the_posted_nor_the_effective_form_is_refused(self):
        with pytest.raises(ConfigValidationError, match="mortgage_rate.posted_5y"):
            load_config_dict({
                "years": 10,
                "house": {"initial_value": 600_000, "down_payment": 200_000,
                          "mortgage_rate": 0.045, "mortgage_term_years": 25},
                "rent": {"monthly_rent": 2_000},
                "sources": {"house.mortgage_rate": "anchor:mortgage_rate.posted_5y"},
            })


# ---------------------------------------------------------------------------
# Lines declared by NAME (2026-09-04)
#
# `house.other_recurring_costs` is one attributable thing — a list — and an
# anchor sources a number, so the property-tax and insurance lines, the two
# largest unsourced figures in a typical run, could carry no anchor at all.
# Served answers showed exactly that: an $813 insurance line that IS the
# StatCan figure echoed as `unattributed`. The named-leaf form
# `<option>.other_recurring_costs.<line name>.annual_amount` (and
# `.escalation_rate`) fixes it; the bare list key stays declarable as user /
# assistant and keeps refusing the anchor form.
# ---------------------------------------------------------------------------

from hde.anchors import ANCHORS  # noqa: E402
from hde.serialization import reference_matches  # noqa: E402

LAVAL_LINE = round(ANCHORS["property_tax.laval"].value * 600_000, 2)
INS = "house.other_recurring_costs.home_insurance.annual_amount"
TAX = "house.other_recurring_costs.property_tax.annual_amount"


def _lines_cfg(sources, lines=None):
    if lines is None:
        lines = [
            {"name": "property_tax", "annual_amount": LAVAL_LINE, "escalation_rate": 0.0},
            {"name": "home_insurance", "annual_amount": 813},
        ]
    return {
        "years": 10,
        "house": {"initial_value": 600_000, "all_cash": True,
                  "other_recurring_costs": lines},
        "rent": {"monthly_rent": 2_000},
        "sources": sources,
    }


class TestLineSourcesByName:
    def test_a_leaf_is_declarable_by_line_name(self):
        spec = load_config_dict(_lines_cfg({INS: "user"}))
        assert spec.sources.classify(INS) == "user"
        assert f"{INS}=$813" in line_starting(_lines_cfg({INS: "user"}), "user-stated:")

    def test_an_insurance_line_equal_to_the_anchor_may_declare_it(self):
        spec = load_config_dict(_lines_cfg({INS: "anchor:home_insurance.qc"}))
        assert spec.sources.anchor_name(INS) == "home_insurance.qc"
        assert line_starting(_lines_cfg({INS: "anchor:home_insurance.qc"}),
                             "anchor-sourced:") == f"anchor-sourced: {INS}=$813 [home_insurance.qc]"

    def test_a_dollar_tax_line_the_read_back_cites_may_declare_the_same_anchor(self):
        """The two surfaces apply one window: a line the other-costs read-back
        cites as Laval's rate is a line `sources:` accepts as Laval's rate."""
        spec = load_config_dict(_lines_cfg({TAX: "anchor:property_tax.laval"}))
        cited = [m["name"] for e in reference_matches(spec) for m in e["matches"]]
        assert "property_tax.laval" in cited
        assert spec.sources.anchor_name(TAX) == "property_tax.laval"

    def test_a_dollar_tax_line_the_read_back_does_not_cite_is_refused(self):
        lines = [{"name": "property_tax", "annual_amount": 9_999}]
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict(_lines_cfg({TAX: "anchor:property_tax.laval"}, lines))
        message = str(excinfo.value)
        assert "0.005909" in message                 # the anchor's rate
        assert f"{9_999 / 600_000:g}" in message     # the line as a rate on initial_value
        assert "$9,999" in message

    def test_a_summed_declaration_on_a_dollar_line_compares_against_the_sum(self):
        total = ANCHORS["property_tax.laval"].value + ANCHORS["school_tax.qc"].value
        lines = [{"name": "property_tax", "annual_amount": round(total * 600_000, 2)}]
        spec = load_config_dict(_lines_cfg({TAX: "anchor:property_tax.laval+school_tax.qc"}, lines))
        assert spec.sources.anchor_name(TAX) == "property_tax.laval+school_tax.qc"

    def test_an_unknown_line_name_is_refused_naming_the_lines_that_exist(self):
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict(_lines_cfg({"house.other_recurring_costs.insurance.annual_amount": "user"}))
        message = str(excinfo.value)
        assert "names no line" in message
        assert "'property_tax', 'home_insurance'" in message

    def test_a_leaf_the_line_does_not_state_is_refused(self):
        key = "house.other_recurring_costs.home_insurance.escalation_rate"
        with pytest.raises(ConfigValidationError, match="does not state escalation_rate"):
            load_config_dict(_lines_cfg({key: "assistant"}))

    def test_the_escalation_rate_leaf_is_declarable(self):
        key = "house.other_recurring_costs.property_tax.escalation_rate"
        assert f"{key}=0.0%" in line_starting(_lines_cfg({key: "assistant"}), "assistant-typed:")

    def test_an_option_without_lines_is_refused_plainly(self):
        cfg = _lines_cfg({"condo.other_recurring_costs.tax.annual_amount": "user"})
        cfg["condo"] = {"initial_value": 300_000, "monthly_fee": 300, "all_cash": True}
        with pytest.raises(ConfigValidationError, match="condo has no other_recurring_costs lines"):
            load_config_dict(cfg)

    def test_the_bare_list_still_refuses_the_anchor_form_and_points_at_the_named_form(self):
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config_dict(_lines_cfg({"house.other_recurring_costs": "anchor:home_insurance.qc"}))
        message = str(excinfo.value)
        assert "an anchor sources a number, not list" in message
        assert "house.other_recurring_costs.<line name>.annual_amount" in message

    def test_the_bare_list_is_still_declarable_as_user(self):
        spec = load_config_dict(_lines_cfg({"house.other_recurring_costs": "user"}))
        assert spec.sources.classify("house.other_recurring_costs") == "user"
        assert spec.sources.get(INS) is None

    def test_declaring_one_leaf_echoes_the_rest_of_that_list_per_leaf(self):
        cfg = _lines_cfg({INS: "anchor:home_insurance.qc"})
        unattributed = line_starting(cfg, "unattributed:")
        assert f"{TAX}=$3,545" in unattributed
        assert "house.other_recurring_costs.property_tax.escalation_rate=0.0%" in unattributed
        assert "house.other_recurring_costs=2 entries" not in unattributed

    def test_the_bare_key_and_a_leaf_may_both_be_declared(self):
        cfg = _lines_cfg({"house.other_recurring_costs": "user", INS: "anchor:home_insurance.qc"})
        assert "house.other_recurring_costs=2 entries" in line_starting(cfg, "user-stated:")
        assert INS in line_starting(cfg, "anchor-sourced:")

    def test_an_undeclared_list_is_still_one_unattributed_entry(self):
        cfg = _lines_cfg({"years": "user"})
        unattributed = line_starting(cfg, "unattributed:")
        assert "house.other_recurring_costs=2 entries" in unattributed
        assert INS not in unattributed

    def test_the_json_echo_carries_the_named_key(self):
        doc = assumptions_to_dict(load_config_dict(_lines_cfg({INS: "anchor:home_insurance.qc"})))
        assert doc["sources"]["anchor"] == {INS: "home_insurance.qc"}

    def test_duplicate_line_names_are_refused_when_declared(self):
        lines = [{"name": "tax", "annual_amount": 1_000}, {"name": "tax", "annual_amount": 2_000}]
        with pytest.raises(ConfigValidationError, match="two house.other_recurring_costs lines are named 'tax'"):
            load_config_dict(_lines_cfg({"house.other_recurring_costs.tax.annual_amount": "user"}, lines))

    def test_a_line_name_with_a_dot_resolves(self):
        lines = [{"name": "property tax (0.55% of value)", "annual_amount": 3_300}]
        key = "house.other_recurring_costs.property tax (0.55% of value).annual_amount"
        spec = load_config_dict(_lines_cfg({key: "assistant"}, lines))
        assert spec.sources.classify(key) == "assistant"

    def test_a_rent_line_is_declarable_by_name(self):
        cfg = _lines_cfg({"rent.other_recurring_costs.tenant insurance.annual_amount": "user"})
        cfg["rent"]["other_recurring_costs"] = [{"name": "tenant insurance", "annual_amount": 300}]
        spec = load_config_dict(cfg)
        assert spec.sources.classify("rent.other_recurring_costs.tenant insurance.annual_amount") == "user"

    def test_a_rate_anchor_on_a_rent_dollar_line_is_refused_without_a_price(self):
        cfg = _lines_cfg({"rent.other_recurring_costs.property tax.annual_amount":
                          "anchor:property_tax.laval"})
        cfg["rent"]["other_recurring_costs"] = [{"name": "property tax", "annual_amount": 3_545.4}]
        with pytest.raises(ConfigValidationError, match="no initial_value"):
            load_config_dict(cfg)
