"""
Round-three dogfood fixes (2026-09-02). Two Opus/Sonnet persona runs and their
critics converged on the same engine gaps:

1. In nominal mode the default discount rate was the REAL anchor (3%) used as
   a nominal rate, so an omitted discount_rate silently priced the future at
   ~0.9% real and mis-fired the capital-spread warning. The default now
   composes with inflation_rate like every other real input in nominal mode.
2. In real mode the affordability ratio uses the level payment at the REAL
   mortgage rate; the lender collects the payment at the quoted NOMINAL rate,
   which is higher (the two persona runs: 27.9% vs 33.2%, 30.2% vs 35.8%
   against a 32% threshold). The engine now warns instead of staying silent.
3. When a price shock makes the Monte Carlo MEAN favour the other option, the
   verdict said nothing (Montréal run: deterministic condo −$4.7k, MC mean
   rent −$5.8k). The verdict now carries `mc_mean_best` and says so.
"""

import re

import numpy as np
import pytest

from hde.anchors import ANCHORS
from hde.config import coherence_warnings, load_config_dict
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloOptionResult,
    MonteCarloSummary,
    OptionResult,
    compute_verdict,
)
from hde.serialization import assumptions_to_dict, format_assumptions
from hde.story_plots import verdict_sentence
from hde.sweep import format_sweep

REAL_DR = ANCHORS["simulation.discount_rate"].value


def _base(**over):
    cfg = {
        "years": 10,
        "rent": {"monthly_rent": 2000, "rent_escalation_rate": 0.0},
        "condo": {
            "initial_value": 400_000, "monthly_fee": 300, "value_growth_rate": 0.0,
            "down_payment": 80_000, "mortgage_rate": 0.04, "mortgage_term_years": 25,
            "purchase_costs": 5_000,
            "other_recurring_costs": [
                {"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}],
        },
        "income": {"annual_income": 90_000},
    }
    cfg.update(over)
    return cfg


class TestNominalDiscountDefault:
    def test_real_mode_default_is_the_anchor(self):
        spec = load_config_dict(_base())
        assert spec.simulation.discount_rate == pytest.approx(REAL_DR)
        assert "simulation.discount_rate" in spec.defaults_applied

    def test_nominal_mode_default_composes_with_inflation(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        assert spec.simulation.discount_rate == pytest.approx((1 + REAL_DR) * 1.021 - 1)
        assert "simulation.discount_rate" in spec.defaults_applied

    def test_nominal_mode_explicit_is_used_as_entered(self):
        spec = load_config_dict(_base(discount_rate=0.045,
                                      economic={"mode": "nominal", "inflation_rate": 0.021}))
        assert spec.simulation.discount_rate == pytest.approx(0.045)
        assert "simulation.discount_rate" not in spec.defaults_applied

    def test_composed_default_is_named_in_the_echo(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        text = "\n".join(format_assumptions(spec))
        assert "discount_rate 5.2%" in text
        assert "3.0% real default composed with inflation" in text

    def test_no_spurious_capital_spread_warning_in_nominal_mode(self):
        # Defaulted discount rate and defaulted investment return must land on
        # the same composed rate: the renter's capital is a wash by construction.
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021},
                                      rent={"monthly_rent": 2000, "rent_escalation_rate": 0.0,
                                            "invested_down_payment": 85_000}))
        assert not any("invested capital" in w and "earns" in w for w in coherence_warnings(spec))


class TestRealModeMortgageAffordabilityWarning:
    def test_fires_with_income_and_a_mortgage_in_real_mode(self):
        warns = coherence_warnings(load_config_dict(_base()))
        hit = [w for w in warns if w.startswith("affordability:") and "NOMINAL" in w]
        assert len(hit) == 1, warns
        assert "condo" in hit[0] and "4.00%" in hit[0] and "mode: nominal" in hit[0]

    def test_silent_for_all_cash(self):
        cfg = _base()
        cfg["condo"] = {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True,
                        "value_growth_rate": 0.0, "purchase_costs": 5_000,
                        "other_recurring_costs": cfg["condo"]["other_recurring_costs"]}
        assert not any("NOMINAL" in w for w in coherence_warnings(load_config_dict(cfg)))

    def test_silent_without_income(self):
        cfg = _base()
        del cfg["income"]
        assert not any("NOMINAL" in w for w in coherence_warnings(load_config_dict(cfg)))

    def test_silent_in_nominal_mode(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        assert not any("NOMINAL" in w for w in coherence_warnings(spec))


def _det(pvs):
    return ComparisonDeterministicResult(
        condo=OptionResult(total_pv=pvs["condo"], breakdown={}),
        house=None,
        rent=OptionResult(total_pv=pvs["rent"], breakdown={}),
    )


def _mc(means, probs):
    def opt(mean):
        pvs = np.full(100, mean)
        return MonteCarloOptionResult(pvs=pvs, summary=MonteCarloSummary(mean, 0.0, mean, mean, mean))
    return ComparisonMonteCarloResult(
        condo=opt(means["condo"]), rent=opt(means["rent"]),
        prob_condo_cheapest=probs["condo"], prob_rent_cheapest=probs["rent"])


class TestVerdictMonteCarloMean:
    def test_mean_disagreement_is_carried_and_said(self):
        det = _det({"condo": 152_000.0, "rent": 156_700.0})
        mc = _mc({"condo": 162_955.0, "rent": 157_128.0}, {"condo": 0.504, "rent": 0.496})
        v = compute_verdict(det, mc, years=7, discount_rate=0.03)
        assert v.best == "condo" and v.mc_mean_best == "rent"
        assert "Monte Carlo mean favours rent ($157,128 vs $162,955)" in v.reason

    def test_agreement_carries_the_field_without_a_clause(self):
        det = _det({"condo": 150_000.0, "rent": 170_000.0})
        mc = _mc({"condo": 151_000.0, "rent": 171_000.0}, {"condo": 0.9, "rent": 0.1})
        v = compute_verdict(det, mc, years=7, discount_rate=0.03)
        assert v.mc_mean_best == "condo" and "mean favours" not in v.reason

    def test_none_without_monte_carlo_or_on_a_single_path(self):
        det = _det({"condo": 150_000.0, "rent": 170_000.0})
        assert compute_verdict(det, None, years=7).mc_mean_best is None
        mc = _mc({"condo": 150_000.0, "rent": 170_000.0}, {"condo": 1.0, "rent": 0.0})
        assert compute_verdict(det, mc, years=7, single_path=True).mc_mean_best is None


class TestComposedDefaultsAreReconcilableInJson:
    def test_discount_rate_entry_says_composed(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        entries = {e["key"]: e for e in assumptions_to_dict(spec)["defaults_applied"]}
        e = entries["simulation.discount_rate"]
        assert e["value"] == pytest.approx((1 + REAL_DR) * 1.021 - 1)
        assert e["anchor"]["value"] == pytest.approx(REAL_DR)
        assert e["note"].startswith("composed at parse") and "5.16%" in e["note"]

    def test_compute_time_composition_is_named(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        entries = {e["key"]: e for e in assumptions_to_dict(spec)["defaults_applied"]}
        e = entries["rent.investment_return_rate"]
        assert e["value"] == pytest.approx(0.03)
        assert "REAL rate" in e["note"] and "5.16%" in e["note"]

    def test_real_mode_entries_carry_no_note(self):
        spec = load_config_dict(_base())
        assert all(e["note"] is None for e in assumptions_to_dict(spec)["defaults_applied"])


class TestMeanDisagreementReachesTheStoryAndTheSweep:
    def test_story_headline_names_the_mean_winner(self):
        det = _det({"condo": 152_000.0, "rent": 156_700.0})
        mc = _mc({"condo": 162_955.0, "rent": 157_128.0}, {"condo": 0.504, "rent": 0.496})
        s = verdict_sentence(det, 7, mc, num_sims=100)
        assert s.startswith("Too close to call") and s.endswith("— the Monte Carlo mean favours renting")

    def test_story_headline_silent_when_they_agree(self):
        det = _det({"condo": 150_000.0, "rent": 170_000.0})
        mc = _mc({"condo": 151_000.0, "rent": 171_000.0}, {"condo": 0.9, "rent": 0.1})
        assert "mean favours" not in verdict_sentence(det, 7, mc, num_sims=100)

    def test_sweep_table_carries_the_mean_column(self):
        rows = [{"value": 5, "totals": {"condo": 1.0, "rent": 2.0}, "best": "condo", "runner_up": "rent",
                 "margin_pv": 1.0, "margin_frac": 0.5, "decisive": False, "prob_best": 0.5,
                 "mc_mean_best": "rent", "reason": "", "monte_carlo": None}]
        text = format_sweep({"key": "years", "values": [5], "rows": rows, "flips": []})
        assert "MC-mean best" in text
        assert any(re.search(r"\|\s+rent$", l) for l in text.splitlines())
