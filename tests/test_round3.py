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
from hde.config import affordability_warnings, coherence_warnings, load_config_dict
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    MonteCarloOptionResult,
    MonteCarloSummary,
    OptionResult,
    compute_verdict,
)
from hde.deterministic import compute_deterministic
from hde.pv import mortgage_payment
from hde.reporting import format_text_report
from hde.serialization import assumptions_to_dict, det_to_dict, format_assumptions
from hde.story_plots import verdict_sentence
from hde.sweep import format_sweep, run_sweep

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

    def test_nominal_mode_explicit_is_composed_too(self):
        """Under `rates: real` a typed discount_rate is the household's REAL
        opportunity cost and follows the rule every other real rate follows in
        nominal mode (2026-09-04): composed with inflation_rate. (Under the
        default as-quoted convention a typed rate is used as typed there —
        test_rates.py, 2026-09-05.)"""
        spec = load_config_dict(_base(rates="real", discount_rate=0.045,
                                      economic={"mode": "nominal", "inflation_rate": 0.021}))
        assert spec.simulation.discount_rate == pytest.approx(1.045 * 1.021 - 1)
        assert "simulation.discount_rate" not in spec.defaults_applied

    def test_real_mode_explicit_is_the_typed_figure(self):
        spec = load_config_dict(_base(rates="real", discount_rate=0.045))
        assert spec.simulation.discount_rate == pytest.approx(0.045)

    def test_composed_default_is_named_in_the_echo(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        text = "\n".join(format_assumptions(spec))
        assert "discount_rate 3.0% real default → 5.2% nominal (incl. 2.1% inflation)" in text

    def test_composed_typed_rate_is_named_in_the_echo(self):
        spec = load_config_dict(_base(rates="real", discount_rate=0.045,
                                      economic={"mode": "nominal", "inflation_rate": 0.021}))
        text = "\n".join(format_assumptions(spec))
        assert "discount_rate 4.5% real → 6.7% nominal (incl. 2.1% inflation)" in text
        assert "default" not in text.split("\n")[0]
        assert ("growth, escalation, investment-return and discount-rate inputs are REAL "
                "and composed with inflation_rate; mortgage_rate is used as entered") in text

    def test_real_mode_echo_is_unchanged(self):
        spec = load_config_dict(_base(rates="real", discount_rate=0.05))
        assert format_assumptions(spec)[0] == "mode: real terms · discount_rate 5.0%"

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

    def test_typed_discount_rate_is_reconcilable_with_the_source_echo(self):
        """`sources` keeps the figure as typed (real); `discount_rate` is the
        composed value in use; `discount_rate_note` says how the two relate,
        in the words the composed default already uses."""
        spec = load_config_dict(_base(rates="real", discount_rate=0.045,
                                      sources={"discount_rate": "user"},
                                      economic={"mode": "nominal", "inflation_rate": 0.021}))
        block = assumptions_to_dict(spec)
        assert block["discount_rate"] == pytest.approx(1.045 * 1.021 - 1)
        assert block["sources"]["user"] == [
            {"key": "discount_rate", "value": 0.045, "formatted": "4.5%"}]
        assert block["discount_rate_note"] == (
            "composed at parse: (1 + 4.5% real)(1 + 2.1% inflation_rate) − 1 = 6.69% nominal")

    def test_default_discount_rate_note_matches_its_entry(self):
        spec = load_config_dict(_base(economic={"mode": "nominal", "inflation_rate": 0.021}))
        block = assumptions_to_dict(spec)
        entry = {e["key"]: e for e in block["defaults_applied"]}["simulation.discount_rate"]
        assert block["discount_rate_note"] == entry["note"]

    def test_real_mode_carries_no_discount_rate_note(self):
        assert assumptions_to_dict(load_config_dict(_base()))["discount_rate_note"] is None

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


class TestFinancedPremiumIsNotReportedMissing:
    def test_premium_dropped_from_the_warning_when_financed(self):
        cfg = _base()
        cfg["condo"]["purchase_costs"] = 0
        cfg["condo"]["financed_purchase_costs"] = 9_520
        warns = [w for w in coherence_warnings(load_config_dict(cfg)) if w.startswith("condo: not modelled")]
        assert len(warns) == 1
        assert "land-transfer tax, notary)" in warns[0] and "premium" not in warns[0]

    def test_premium_listed_when_nothing_is_financed(self):
        cfg = _base()
        cfg["condo"]["purchase_costs"] = 0
        warns = [w for w in coherence_warnings(load_config_dict(cfg)) if w.startswith("condo: not modelled")]
        assert len(warns) == 1 and "mortgage-insurance premium" in warns[0]


class TestYearOneCashLine:
    """A sticker-cash user reads the $/month PV equivalent as out-of-pocket;
    the engine now prints year-1 cash (undiscounted) and the principal repaid
    so the answer can say 'the owner pays $X/month MORE in cash; the PV win is
    equity at sale' from an engine line, not hand arithmetic."""

    def test_condo_and_rent_year1_cash_and_principal(self):
        spec = load_config_dict(_base())
        det = compute_deterministic(spec)
        loan = 400_000 - 80_000
        pay = mortgage_payment(loan, 0.04, 25)
        assert det.condo.cash_year1 == pytest.approx(300 * 12 + 3_000 + pay)
        assert det.condo.principal_year1 == pytest.approx(pay - loan * 0.04)
        assert det.rent.cash_year1 == pytest.approx(2000 * 12)
        assert det.rent.principal_year1 == 0.0

    def test_all_cash_has_no_principal(self):
        cfg = _base()
        cfg["condo"] = {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True,
                        "value_growth_rate": 0.0, "purchase_costs": 5_000,
                        "other_recurring_costs": cfg["condo"]["other_recurring_costs"]}
        det = compute_deterministic(load_config_dict(cfg))
        assert det.condo.cash_year1 == pytest.approx(300 * 12 + 3_000)
        assert det.condo.principal_year1 == 0.0

    def test_json_and_report_carry_it(self):
        spec = load_config_dict(_base())
        det = compute_deterministic(spec)
        d = det_to_dict(det)
        assert {"cash_year1", "principal_year1"} <= set(d["condo"]) and {"cash_year1", "principal_year1"} <= set(d["rent"])
        text = format_text_report(det, None, spec.simulation, spec.economic, spec)
        assert "Year-1 cash (undiscounted" in text
        assert "principal repaid" in text


class TestSweepTracksTheMonteCarloMean:
    """Opus persona critic: flips tracked only the deterministic cheapest, so a
    sweep whose Monte Carlo mean changed sides printed 'no flip'."""

    def test_mc_mean_flips_are_detected_and_printed(self):
        rows = [
            {"value": 5, "totals": {"condo": 1.0, "rent": 2.0}, "best": "condo", "runner_up": "rent",
             "margin_pv": 1.0, "margin_frac": 0.5, "decisive": False, "rule": "mc_floor",
             "prob_best": 0.5, "mc_mean_best": "rent", "reason": "", "monte_carlo": None},
            {"value": 10, "totals": {"condo": 1.0, "rent": 2.0}, "best": "condo", "runner_up": "rent",
             "margin_pv": 1.0, "margin_frac": 0.5, "decisive": False, "rule": "mc_floor",
             "prob_best": 0.6, "mc_mean_best": "condo", "reason": "", "monte_carlo": None},
        ]
        from hde.sweep import find_flips
        det_flips, mean_flips = find_flips(rows)
        assert det_flips == []
        assert mean_flips == [{"from_value": 5, "from_best": "rent", "to_value": 10, "to_best": "condo"}]
        text = format_sweep({"key": "years", "values": [5, 10], "rows": rows,
                             "flips": det_flips, "mc_mean_flips": mean_flips})
        assert "no flip along years" in text and "mean flip years: Monte Carlo mean favours rent (years=5) then condo (years=10)" in text

    def test_run_sweep_carries_both_flip_lists(self):
        raw = _base()
        out = run_sweep(raw, "years", [5, 10], monte_carlo=False)
        assert "flips" in out and "mc_mean_flips" in out and out["mc_mean_flips"] == []


class TestYearOneAppreciation:
    def test_owner_expected_appreciation_in_nominal_mode(self):
        spec = load_config_dict(_base(rates="real",
                                      economic={"mode": "nominal", "inflation_rate": 0.021},
                                      condo={**_base()["condo"], "value_growth_rate": 0.01}))
        det = compute_deterministic(spec)
        assert det.condo.appreciation_year1 == pytest.approx(400_000 * ((1.01 * 1.021) - 1))
        assert det.rent.appreciation_year1 == 0.0
        assert "appreciation_year1" in det_to_dict(det)["condo"]
        text = format_text_report(det, None, spec.simulation, spec.economic, spec)
        assert "expected appreciation" in text and "composed with inflation" in text


class TestRoundFiveWarningsAndNotes:
    """Dogfood round 5 (Duvernay threshold): the persona reached for the TDS cap,
    inferred the prior's base-growth convention from an example comment, and
    compared a stochastic owner to a point-mass renter without a warning."""

    PRIOR = {"path": "tests/fixtures/scenario_prior_golden.json", "geography": "LAVAL_RA13"}

    def test_one_sided_uncertainty_warns_with_a_prior_and_no_return_vol(self):
        cfg = _base(market_scenario=self.PRIOR,
                    rent={"monthly_rent": 2000, "rent_escalation_rate": 0.0, "invested_down_payment": 85_000})
        assert any(w.startswith("one-sided uncertainty") for w in coherence_warnings(load_config_dict(cfg)))
        quiet = {**cfg, "simulation": {"investment_return_vol": 0.1}}
        assert not any(w.startswith("one-sided uncertainty") for w in coherence_warnings(load_config_dict(quiet)))
        no_prior = _base(rent=cfg["rent"])
        assert not any(w.startswith("one-sided uncertainty") for w in coherence_warnings(load_config_dict(no_prior)))

    def test_affordability_warning_names_the_ratio_shape_and_the_gds_cap(self):
        spec = load_config_dict(_base(income={"annual_income": 40_000}))
        det = compute_deterministic(spec)
        warns = affordability_warnings(det)
        assert warns and "GDS-shaped" in warns[0] and "39% GDS" in warns[0] and "44% TDS" in warns[0]

    def test_schema_states_the_prior_base_convention_and_the_shipped_geographies(self):
        import json
        from hde.input_schema import input_schema
        schema = input_schema()
        for section in ("condo", "house"):
            assert "ADDED to this base" in schema[section]["value_growth_rate"]["note"]
        note = schema["market_scenario"]["geography"]["note"]
        fixture = json.load(open("tests/fixtures/scenario_prior_golden.json"))
        for geo in sorted({r["geography"] for r in fixture["scenario_priors"]}):
            assert geo in note, geo


class TestVerdictNamesTheOtherSideAsADisagreement:
    """Round 5: at $1,900 a served run read P(house)=66.4% as 'not decisive'
    because decisiveness keyed to the deterministic best (rent, 33.6%). Ruled
    2026-09-04: that is a named DISAGREEMENT — both figures, never decisive —
    whether or not the other side clears the floor."""

    def test_other_side_above_floor_is_a_disagreement(self):
        det = _det({"condo": 156_000.0, "rent": 155_000.0})  # rent is the deterministic best
        mc = _mc({"condo": 150_000.0, "rent": 160_000.0}, {"condo": 0.664, "rent": 0.336})
        v = compute_verdict(det, mc, years=9, discount_rate=0.05)
        assert v.best == "rent" and v.mc_best == "condo"
        assert v.state == "disagreement" and not v.decisive
        assert v.reason.startswith(
            "best guess says rent by $1,000 (0.6% of rent PV); most futures say condo "
            "(66% cheapest) — the two disagree, not decisive [hde verdict rule]")

    def test_other_side_below_floor_is_the_same_disagreement(self):
        det = _det({"condo": 156_000.0, "rent": 155_000.0})
        mc = _mc({"condo": 150_000.0, "rent": 160_000.0}, {"condo": 0.60, "rent": 0.40})
        v = compute_verdict(det, mc, years=9, discount_rate=0.05)
        assert v.state == "disagreement"
        assert "most futures say condo (60% cheapest)" in v.reason and "floor" not in v.reason


class TestPriorSaysWhatItEncodes:
    def test_describe_and_provenance_carry_the_reference_drift(self):
        from hde.market_scenario import load_scenario_prior
        prior = load_scenario_prior("tests/fixtures/scenario_prior_golden.json", "LAVAL_RA13")
        text = prior.describe()
        assert "encoded REAL drift by band" in text and "reference 2030" in text and "scenarios" in text
        block = prior.provenance_block()
        ref = next(iter(block["encoded_drift"].values()))["reference_by_band"]
        assert set(ref) >= {2030, 2035}
        # the clause quotes the fixture's own reference rows
        ref_row = next(r for (d, h, s), r in prior.rows.items() if s == "reference" and h == 2030)
        assert f"2030 {ref_row.demo_drift_mean:+.2%}/yr" in text


class TestAssumptionsLineCarriesTheHorizonDrift:
    def test_eight_year_run_quotes_2030_and_2035_bands_only(self):
        from hde.market_scenario import load_scenario_prior
        from hde.serialization import assumptions_to_dict
        cfg = _base(years=8, market_scenario={"path": "tests/fixtures/scenario_prior_golden.json",
                                              "geography": "LAVAL_RA13"})
        spec = load_config_dict(cfg)
        prior = load_scenario_prior(cfg["market_scenario"]["path"], "LAVAL_RA13")
        line = next(l for l in assumptions_to_dict(spec, prior)["lines"] if l.startswith("demographic prior:"))
        assert "reference REAL drift over this 8-year run" in line
        assert "(2030 band)" in line and "(2035 band)" in line and "2050" not in line


class TestFinancingLineAndAffordabilityHeader:
    """Round 6 (restructured-skill serves on Sonnet and Opus): both personas computed
    the loan-to-value and the distance to the 20% insurance line by hand and landed
    $250 over it; the report's affordability header named only the 32% figure."""

    def test_assumptions_carry_the_financing_line_for_a_mortgage(self):
        from hde.serialization import assumptions_to_dict
        spec = load_config_dict(_base(condo={**_base()["condo"], "down_payment": 80_250, "purchase_costs": 9_750}))
        line = next(l for l in assumptions_to_dict(spec, None)["lines"] if l.startswith("condo financing:"))
        assert "down payment $80,250 = 20.06% of price" in line
        assert "$250 above the 20% mortgage-insurance line ($80,000)" in line
        assert "year-0 cash $90,000 (down payment + purchase_costs)" in line

    def test_financing_line_says_below_when_insured(self):
        from hde.serialization import assumptions_to_dict
        spec = load_config_dict(_base(condo={**_base()["condo"], "down_payment": 60_000,
                                              "financed_purchase_costs": 9_520}))
        line = next(l for l in assumptions_to_dict(spec, None)["lines"] if l.startswith("condo financing:"))
        assert "$20,000 below the 20% mortgage-insurance line" in line
        assert "financed_purchase_costs $9,520 on the loan" in line

    def test_all_cash_has_no_financing_line(self):
        from hde.serialization import assumptions_to_dict
        spec = load_config_dict({"years": 10, "rent": {"monthly_rent": 2000},
                                 "condo": {"initial_value": 400_000, "monthly_fee": 300, "all_cash": True}})
        assert not any(l.startswith("condo financing:") for l in assumptions_to_dict(spec, None)["lines"])

    def test_affordability_header_names_the_three_thresholds(self):
        spec = load_config_dict(_base(income={"annual_income": 90_000}))
        det = compute_deterministic(spec)
        text = format_text_report(det, None, spec.simulation, spec.economic, spec)
        assert "Affordability (threshold: 32% — a GDS-shaped ratio" in text
        assert "legacy guideline, CMHC caps GDS at 39%, TDS at 44%" in text

    def test_schema_states_the_like_for_like_sizing(self):
        from hde.input_schema import input_schema
        assert "down_payment + purchase_costs" in input_schema()["rent"]["invested_down_payment"]["note"]


class TestUnderTwentyPercentWarnsAndSweepRowsCarryAffordability:
    def test_under_twenty_with_nothing_financed_warns(self):
        cfg = _base(condo={**_base()["condo"], "down_payment": 60_000})
        warns = coherence_warnings(load_config_dict(cfg))
        assert any(w.startswith("condo: down payment 15.00% of price is under the 20%") for w in warns)
        quiet = _base(condo={**_base()["condo"], "down_payment": 60_000, "financed_purchase_costs": 9_520})
        assert not any("under the 20%" in w for w in coherence_warnings(load_config_dict(quiet)))
        at_line = _base()  # 80,000 on 400,000 = 20.00%
        assert not any("under the 20%" in w for w in coherence_warnings(load_config_dict(at_line)))

    def test_sweep_rows_carry_the_affordability_ratio(self):
        from hde.sweep import run_sweep
        out = run_sweep(_base(income={"annual_income": 90_000}), "condo.monthly_fee", [300, 900], monte_carlo=False)
        rows = out["rows"]
        assert rows[0]["affordability"]["condo"]["max_ratio"] < rows[1]["affordability"]["condo"]["max_ratio"]
        assert "years_exceeding" in rows[1]["affordability"]["condo"]
        cfg = _base(); del cfg["income"]
        no_income = run_sweep(cfg, "condo.monthly_fee", [300], monte_carlo=False)
        assert no_income["rows"][0]["affordability"] is None
