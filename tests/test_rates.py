"""
Rates as quoted (2026-09-05): every typed growth, escalation, return and
discount rate is the figure as the user sees it quoted, converted ONCE at load
— deflated in real mode, used as typed in nominal mode — while the anchored
defaults stay real and compose as before. Served answers had assistants
converting sticker numbers by hand and the engine inflating them a second time;
one number now means one thing.
"""

import json
import sys
from pathlib import Path

import pytest

from hde.anchors import ANCHORS
from hde.break_even import solve_break_even
from hde.cli import main as cli_main
from hde.config import ConfigValidationError, coherence_warnings, load_config, load_config_dict
from hde.deterministic import _effective_growth_rate, compute_deterministic
from hde.market_scenario import load_scenario_prior
from hde.rates import ConvertedRate, compose, deflate, is_convertible
from hde.serialization import (
    assumptions_to_dict, discount_rate_note, format_assumptions, rates_line, read_back_lines,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
PRIOR_PATH = str(ROOT / "tests" / "fixtures" / "scenario_prior_golden.json")
PI = 0.021
PLANNING = ANCHORS["economic.inflation_rate.nominal_planning"].value


def _cfg(**over):
    cfg = {
        "years": 10,
        "discount_rate": 0.05,
        "economic": {"mode": "real", "inflation_rate": PI},
        "condo": {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True,
                  "fee_escalation_rate": 0.03, "value_growth_rate": 0.04,
                  "purchase_costs": 6_000,
                  "other_recurring_costs": [
                      {"name": "property tax", "annual_amount": 3_000, "escalation_rate": 0.02}]},
        "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.03,
                 "invested_down_payment": 406_000, "investment_return_rate": 0.06},
        "income": {"annual_income": 90_000, "income_growth_rate": 0.03},
        "simulation": {"num_sims": 20, "random_seed": 1},
    }
    cfg.update(over)
    return cfg


def _nominal(**over):
    over.setdefault("economic", {"mode": "nominal", "inflation_rate": PI})
    return _cfg(**over)


class TestRealModeDeflatesTypedRates:
    def test_every_typed_rate_is_deflated_once(self):
        spec = load_config_dict(_cfg())
        assert spec.rates == "as_quoted"
        assert spec.condo.fee_escalation_rate == pytest.approx(deflate(0.03, PI))
        assert spec.condo.value_growth_rate == pytest.approx(deflate(0.04, PI))
        assert spec.condo.other_recurring_costs[0].escalation_rate == pytest.approx(deflate(0.02, PI))
        assert spec.rent.rent_escalation_rate == pytest.approx(deflate(0.03, PI))
        assert spec.rent.investment_return_rate == pytest.approx(deflate(0.06, PI))
        assert spec.income.income_growth_rate == pytest.approx(deflate(0.03, PI))
        assert spec.simulation.discount_rate == pytest.approx(deflate(0.05, PI))

    def test_the_conversions_are_recorded_with_both_figures(self):
        spec = load_config_dict(_cfg())
        by_key = {c.key: c for c in spec.converted_rates}
        assert by_key["rent.rent_escalation_rate"] == ConvertedRate(
            "rent.rent_escalation_rate", 0.03, deflate(0.03, PI))
        assert by_key["condo.other_recurring_costs.property tax.escalation_rate"].quoted == 0.02
        assert by_key["discount_rate"].effective == pytest.approx(deflate(0.05, PI))
        assert set(by_key) == {
            "discount_rate", "condo.fee_escalation_rate", "condo.value_growth_rate",
            "condo.other_recurring_costs.property tax.escalation_rate",
            "rent.rent_escalation_rate", "rent.investment_return_rate",
            "income.income_growth_rate"}

    def test_a_sticker_rate_below_inflation_is_a_negative_real_rate_and_loads(self):
        spec = load_config_dict(_cfg(rent={"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                                           "invested_down_payment": 406_000,
                                           "investment_return_rate": 0.0}))
        assert spec.rent.rent_escalation_rate == pytest.approx(deflate(0.0, PI))
        assert spec.rent.rent_escalation_rate < 0
        assert spec.rent.investment_return_rate < 0

    def test_the_derived_property_tax_line_escalates_at_the_converted_growth(self):
        cfg = _cfg()
        cfg["condo"] = {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True,
                        "value_growth_rate": 0.04, "property_tax_rate": 0.01}
        spec = load_config_dict(cfg)
        tax = spec.condo.other_recurring_costs[0]
        assert tax.escalation_rate == pytest.approx(deflate(0.04, PI))

    def test_a_quoted_rate_equal_to_inflation_is_zero_real_and_still_prices(self):
        spec = load_config_dict(_cfg(discount_rate=PI))
        assert spec.simulation.discount_rate == pytest.approx(0.0)
        assert compute_deterministic(spec).condo.total_pv > 0


class TestNominalModeUsesTypedRatesAsTyped:
    def test_the_effective_rate_is_the_quoted_figure(self):
        spec = load_config_dict(_nominal())
        econ = spec.economic
        assert _effective_growth_rate(spec.rent.rent_escalation_rate, econ) == pytest.approx(0.03)
        assert _effective_growth_rate(spec.condo.value_growth_rate, econ) == pytest.approx(0.04)
        assert _effective_growth_rate(spec.rent.investment_return_rate, econ) == pytest.approx(0.06)
        assert spec.simulation.discount_rate == pytest.approx(0.05)

    def test_the_record_says_the_quoted_figure_is_in_use(self):
        spec = load_config_dict(_nominal())
        by_key = {c.key: c for c in spec.converted_rates}
        assert by_key["rent.rent_escalation_rate"].effective == 0.03
        assert by_key["discount_rate"].effective == 0.05


class TestRatesRealIsTheEscape:
    def test_typed_rates_are_real_figures_and_nothing_is_converted(self):
        spec = load_config_dict(_cfg(rates="real"))
        assert spec.rates == "real"
        assert spec.converted_rates == []
        assert spec.rent.rent_escalation_rate == 0.03
        assert spec.simulation.discount_rate == 0.05

    def test_in_nominal_mode_they_compose_as_before(self):
        spec = load_config_dict(_nominal(rates="real"))
        assert spec.simulation.discount_rate == pytest.approx(compose(0.05, PI))
        assert _effective_growth_rate(spec.rent.rent_escalation_rate, spec.economic) == pytest.approx(compose(0.03, PI))

    def test_an_unknown_convention_is_refused(self):
        with pytest.raises(ConfigValidationError, match="as_quoted"):
            load_config_dict(_cfg(rates="nominal"))


class TestDefaultsStayRealAndComposed:
    def test_omitted_rates_are_the_anchored_real_defaults_in_real_mode(self):
        cfg = _cfg()
        del cfg["discount_rate"]
        del cfg["rent"]["rent_escalation_rate"]
        spec = load_config_dict(cfg)
        assert spec.rent.rent_escalation_rate == ANCHORS["rent.rent_escalation_rate"].value
        assert spec.simulation.discount_rate == ANCHORS["simulation.discount_rate"].value
        assert not any(c.key in ("discount_rate", "rent.rent_escalation_rate")
                       for c in spec.converted_rates)

    def test_and_compose_in_nominal_mode_exactly_as_before(self):
        cfg = _nominal()
        del cfg["discount_rate"]
        spec = load_config_dict(cfg)
        anchor = ANCHORS["simulation.discount_rate"].value
        assert spec.simulation.discount_rate == pytest.approx(compose(anchor, PI))
        assert discount_rate_note(spec) == (
            "composed at parse: (1 + 3.0% real)(1 + 2.1% inflation_rate) − 1 = 5.16% nominal")


class TestInflationIsTheDeflatorInRealMode:
    def test_omitted_inflation_is_the_planning_figure_and_a_default_applied(self):
        cfg = _cfg(economic={"mode": "real"})
        spec = load_config_dict(cfg)
        assert spec.economic.inflation_rate == PLANNING
        assert "economic.inflation_rate" in spec.defaults_applied
        assert spec.rent.rent_escalation_rate == pytest.approx(deflate(0.03, PLANNING))

    def test_the_echo_cites_the_planning_anchor(self):
        spec = load_config_dict(_cfg(economic={"mode": "real"}))
        entry = {e["key"]: e for e in assumptions_to_dict(spec)["defaults_applied"]}["economic.inflation_rate"]
        assert entry["value"] == PLANNING
        assert entry["anchor"]["name"] == "economic.inflation_rate.nominal_planning"
        assert entry["cite"] == "FP Canada 2026 PAG"
        text = "\n".join(format_assumptions(spec))
        assert "economic.inflation_rate=2.1% [FP Canada 2026 PAG]" in text

    def test_no_economic_block_at_all_still_deflates(self):
        cfg = _cfg()
        del cfg["economic"]
        spec = load_config_dict(cfg)
        assert spec.economic.inflation_rate == PLANNING
        assert spec.simulation.discount_rate == pytest.approx(deflate(0.05, PLANNING))

    def test_rates_real_keeps_the_inert_zero(self):
        spec = load_config_dict(_cfg(rates="real", economic={"mode": "real"}))
        assert spec.economic.inflation_rate == 0.0

    def test_nominal_mode_keeps_its_zero_and_its_warning(self):
        spec = load_config_dict(_nominal(economic={"mode": "nominal"}))
        assert spec.economic.inflation_rate == 0.0
        assert any("nominal mode with inflation_rate=0" in w for w in coherence_warnings(spec))

    def test_inflation_typed_in_real_mode_no_longer_warns_ignored(self):
        assert not any("ignored in real mode" in w for w in coherence_warnings(load_config_dict(_cfg())))

    def test_but_still_does_under_rates_real(self):
        warns = coherence_warnings(load_config_dict(_cfg(rates="real")))
        assert any("ignored in real mode" in w for w in warns)

    def test_a_high_quoted_growth_is_not_called_a_nominal_quote(self):
        spec = load_config_dict(_cfg(condo={"initial_value": 400_000, "monthly_fee": 300,
                                            "all_cash": True, "value_growth_rate": 0.05}))
        assert not any("nominal quote" in w for w in coherence_warnings(spec))

    def test_a_discount_rate_under_inflation_warns_that_the_real_rate_is_negative(self):
        warns = coherence_warnings(load_config_dict(_cfg(discount_rate=0.01)))
        assert any("discount_rate 1.0% as quoted" in w and "-1.1% real" in w for w in warns), warns


class TestAnchorDeclarationsCompareInTheAnchorsConvention:
    ANCHOR = ANCHORS["rent.rent_escalation_rate"]

    def _rent(self, typed, **top):
        cfg = _cfg(**top)
        cfg["rent"]["rent_escalation_rate"] = typed
        cfg["sources"] = {"rent.rent_escalation_rate": "anchor:rent.rent_escalation_rate"}
        return cfg

    def test_the_pag_anchors_carry_their_quoted_figure_as_a_restatement(self):
        for name, quoted in (("rent.rent_escalation_rate", 0.031),
                             ("income.income_growth_rate", 0.031),
                             ("rent.investment_return_rate", 0.051),
                             ("simulation.discount_rate", 0.051)):
            anchor = ANCHORS[name]
            assert quoted in anchor.stated_values(), name
            (_, why), = anchor.restatements
            assert "2.1%" in why, name

    def test_the_quoted_figure_the_source_prints_is_accepted(self):
        spec = load_config_dict(self._rent(0.031))
        assert spec.sources.anchor_name("rent.rent_escalation_rate") == "rent.rent_escalation_rate"
        assert spec.rent.rent_escalation_rate == pytest.approx(deflate(0.031, PI))

    def test_a_figure_that_deflates_to_the_real_value_is_accepted(self):
        exact = compose(self.ANCHOR.value, PI)
        spec = load_config_dict(self._rent(exact))
        assert spec.sources.anchor_name("rent.rent_escalation_rate") == "rent.rent_escalation_rate"
        assert spec.rent.rent_escalation_rate == pytest.approx(self.ANCHOR.value)

    def test_the_real_value_typed_as_quoted_is_refused_naming_both_conventions(self):
        with pytest.raises(ConfigValidationError) as err:
            load_config_dict(self._rent(0.01))
        message = str(err.value)
        assert "0.01" in message and "as quoted" in message and "real" in message

    def test_under_rates_real_the_real_value_is_accepted(self):
        spec = load_config_dict(self._rent(0.01, rates="real"))
        assert spec.sources.anchor_name("rent.rent_escalation_rate") == "rent.rent_escalation_rate"

    def test_the_echo_prints_the_figure_as_quoted(self):
        text = "\n".join(format_assumptions(load_config_dict(self._rent(0.031))))
        assert "anchor-sourced: rent.rent_escalation_rate=3.1% [rent.rent_escalation_rate]" in text

    def test_a_named_line_escalation_rate_is_compared_the_same_way(self):
        cfg = _cfg()
        cfg["condo"]["other_recurring_costs"][0]["escalation_rate"] = 0.031
        cfg["sources"] = {"condo.other_recurring_costs.property tax.escalation_rate":
                          "anchor:rent.rent_escalation_rate"}
        spec = load_config_dict(cfg)
        assert spec.sources.anchor_name(
            "condo.other_recurring_costs.property tax.escalation_rate") == "rent.rent_escalation_rate"

    def test_the_discount_rate_declaration_follows_the_rule(self):
        cfg = _cfg(discount_rate=0.051, sources={"discount_rate": "anchor:simulation.discount_rate"})
        assert load_config_dict(cfg).sources.anchor_name("discount_rate") == "simulation.discount_rate"
        with pytest.raises(ConfigValidationError):
            load_config_dict(_cfg(discount_rate=0.03, sources={"discount_rate": "anchor:simulation.discount_rate"}))


class TestTheReadBackLine:
    def test_real_mode_prints_both_forms_per_typed_rate(self):
        spec = load_config_dict(_cfg())
        assert rates_line(spec) == (
            "rates: as quoted · discount_rate 5.0% as quoted = 2.8% after 2.1% inflation · "
            "condo.fee_escalation_rate 3.0% as quoted = 0.9% after 2.1% inflation · "
            "condo.value_growth_rate 4.0% as quoted = 1.9% after 2.1% inflation · "
            "condo.other_recurring_costs.property tax.escalation_rate 2.0% as quoted = -0.1% after 2.1% inflation · "
            "rent.rent_escalation_rate 3.0% as quoted = 0.9% after 2.1% inflation · "
            "rent.investment_return_rate 6.0% as quoted = 3.8% after 2.1% inflation · "
            "income.income_growth_rate 3.0% as quoted = 0.9% after 2.1% inflation")

    def test_nominal_mode_says_the_quoted_figure_is_used_as_typed(self):
        spec = load_config_dict(_nominal())
        line = rates_line(spec)
        assert line.startswith("rates: as quoted · discount_rate 5.0% as quoted = 5.0% nominal, as typed · ")
        assert "rent.rent_escalation_rate 3.0% as quoted = 3.0% nominal, as typed" in line

    def test_nothing_typed_says_so(self):
        cfg = {"years": 5, "rent": {"monthly_rent": 1_500}}
        assert rates_line(load_config_dict(cfg)) == "rates: as quoted · no typed rate to convert"

    def test_rates_real_says_the_figures_are_real(self):
        assert rates_line(load_config_dict(_cfg(rates="real"))) == (
            "rates: real (declared) · typed rates are real figures, used as typed")
        assert rates_line(load_config_dict(_nominal(rates="real"))) == (
            "rates: real (declared) · typed rates are real figures, composed with "
            "2.1% inflation_rate at compute")

    def test_it_rides_the_assumptions_block_and_the_read_back_after_the_defaults(self):
        spec = load_config_dict(_cfg())
        echo = format_assumptions(spec)
        assert any(line.startswith("rates: as quoted") for line in echo)
        cfg = _cfg()
        del cfg["discount_rate"]
        spec = load_config_dict(cfg)
        lines = read_back_lines(spec, warnings=coherence_warnings(spec))
        defaults = next(i for i, l in enumerate(lines) if l.startswith("defaults applied:"))
        assert lines[defaults + 1].startswith("rates: as quoted · condo.fee_escalation_rate 3.0% as quoted")

    def test_the_mode_line_shows_the_typed_discount_rate_in_both_forms(self):
        assert format_assumptions(load_config_dict(_cfg()))[0] == (
            "mode: real terms · discount_rate 5.0% as quoted → 2.8% real (after 2.1% inflation)")
        assert format_assumptions(load_config_dict(_nominal()))[0] == (
            "mode: nominal terms · discount_rate 5.0% as quoted, used as typed (typed rates are "
            "as quoted and used as typed; anchored defaults are real and composed with "
            "inflation_rate; mortgage_rate is used as entered)")

    def test_the_discount_rate_note_says_which_conversion_ran(self):
        assert discount_rate_note(load_config_dict(_cfg())) == (
            "deflated at parse: (1 + 5.0% as quoted)/(1 + 2.1% inflation_rate) − 1 = 2.84% real")
        assert discount_rate_note(load_config_dict(_nominal())) == "as quoted: 5.0% nominal, used as typed"
        assert discount_rate_note(load_config_dict(_cfg(rates="real"))) is None

    def test_per_option_lines_carry_the_quoted_figure(self):
        text = "\n".join(format_assumptions(load_config_dict(_cfg())))
        assert "condo: value growth +1.9%/yr (4.0% as quoted)" in text
        assert "rent: escalation +0.9%/yr (3.0% as quoted)" in text
        nominal = "\n".join(format_assumptions(load_config_dict(_nominal())))
        assert "rent: escalation +3.0%/yr nominal, as quoted (0.9% real)" in nominal

    def test_the_line_is_byte_stable(self):
        a = rates_line(load_config_dict(_cfg()))
        b = rates_line(load_config_dict(_cfg()))
        assert a == b


class TestTheJsonShape:
    def test_assumptions_carry_the_convention_the_deflator_and_each_conversion(self):
        block = assumptions_to_dict(load_config_dict(_cfg()))
        assert block["rates"] == "as_quoted"
        assert block["inflation_rate"] == PI
        entry = next(c for c in block["converted_rates"] if c["key"] == "rent.rent_escalation_rate")
        assert entry == {"key": "rent.rent_escalation_rate", "quoted": 0.03,
                         "effective": pytest.approx(deflate(0.03, PI))}
        assert block["discount_rate"] == pytest.approx(deflate(0.05, PI))

    def test_rates_real_carries_an_empty_list(self):
        block = assumptions_to_dict(load_config_dict(_cfg(rates="real")))
        assert block["rates"] == "real" and block["converted_rates"] == []

    def test_it_reaches_the_cli(self, tmp_path, monkeypatch, capsys):
        import yaml
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(_cfg()), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["hde", str(path), "--json", "--no-monte-carlo"])
        assert cli_main() == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["assumptions"]["rates"] == "as_quoted"
        assert any(line.startswith("rates: as quoted") for line in doc["assumptions"]["read_back"])


class TestTheThresholdAxisIsTheQuotedOne:
    def test_the_prior_note_states_its_drift_as_quoted(self):
        raw = {
            "years": 10, "discount_rate": 0.03,
            "economic": {"mode": "real", "inflation_rate": PI},
            "market_scenario": {"path": PRIOR_PATH, "geography": "MTL_RMR"},
            "house": {"initial_value": 500_000, "value_growth_rate": 0.0, "all_cash": True},
            "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.0,
                     "invested_down_payment": 120_000, "investment_return_rate": 0.03},
            "simulation": {"num_sims": 50, "random_seed": 42},
        }
        prior = load_scenario_prior(PRIOR_PATH, "MTL_RMR")
        note = solve_break_even(raw, "house.value_growth_rate", prior=prior)["note"]
        assert "/yr as quoted" in note and "composed with 2.1% inflation_rate" in note
        raw["rates"] = "real"
        note = solve_break_even(raw, "house.value_growth_rate", prior=prior)["note"]
        assert "as quoted" not in note


class TestTheStoryNamesTheQuotedFigure:
    def test_the_home_futures_sentence(self):
        from hde.story_page import growth_label
        assert growth_label(load_config_dict(_cfg()), "condo") == "1.9% real (4.0% as quoted)"
        assert growth_label(load_config_dict(_cfg(rates="real")), "condo") == "4.0%"

    def test_a_typed_figure_equal_to_the_one_printed_is_not_restated(self):
        from hde.serialization import rate_label
        spec = load_config_dict(_cfg(economic={"mode": "real", "inflation_rate": 0.0}))
        assert rate_label(spec, "condo.value_growth_rate", spec.condo.value_growth_rate) == "4.0%"
        spec = load_config_dict(_nominal())
        assert rate_label(spec, "discount_rate", spec.simulation.discount_rate) == "5.0%"

    def test_the_race_caption_names_the_discount_rate_both_ways(self):
        from hde.serialization import rate_label
        spec = load_config_dict(_cfg())
        assert rate_label(spec, "discount_rate", spec.simulation.discount_rate) == "2.8% real (5.0% as quoted)"
        assert rate_label(load_config_dict(_cfg(rates="real")), "discount_rate", 0.05) == "5.0%"

    def test_the_capital_spread_warning_names_both_rates_as_quoted(self):
        warns = [w for w in coherence_warnings(load_config_dict(_cfg())) if "invested capital" in w]
        assert len(warns) == 1
        assert "earns 3.8% real (6.0% as quoted) vs discount_rate 2.8% real (5.0% as quoted)" in warns[0]
        warns = [w for w in coherence_warnings(load_config_dict(_nominal())) if "invested capital" in w]
        assert len(warns) == 1
        assert "earns 6.0% vs discount_rate 5.0%" in warns[0]


class TestTheExamplesTeachTheDefault:
    CHEAPEST = {
        "advanced_config.yaml": "house",
        "basic_config.yaml": "house",
        "first_time_buyer_montreal.yaml": "rent",
        "income_shock.yaml": "condo",
        "mortgage_house_vs_rent.yaml": "house",
        "rent_vs_condo_vs_house.yaml": "house",
        "showcase_demographic_prior.yaml": "house",
    }

    @pytest.mark.parametrize("name", sorted(CHEAPEST))
    def test_every_example_is_as_quoted_and_its_cheapest_option_is_unchanged(self, name):
        import yaml
        raw = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
        assert "rates" not in raw, name
        spec = load_config(EXAMPLES / name)
        det = compute_deterministic(spec)
        priced = {k: getattr(det, k).total_pv for k in ("condo", "house", "rent")
                  if getattr(det, k) is not None}
        assert min(priced, key=priced.get) == self.CHEAPEST[name]

    def test_is_convertible_names_the_line_form(self):
        assert is_convertible("condo.other_recurring_costs.property tax.escalation_rate")
        assert is_convertible("discount_rate")
        assert not is_convertible("condo.mortgage_rate")
        assert not is_convertible("condo.other_recurring_costs.property tax.annual_amount")
