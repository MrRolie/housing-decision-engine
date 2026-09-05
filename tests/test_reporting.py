"""
Reporting tests (src/hde/reporting.py): the assumption echo block (audit U1).
"""

import numpy as np

from hde.config import load_config_dict
from hde.models import (
    ComparisonDeterministicResult,
    ComparisonMonteCarloResult,
    EconomicParams,
    MonteCarloOptionResult,
    MonteCarloSummary,
    SimulationParams,
    Verdict,
)
from hde.reporting import format_assumptions, format_text_report, verdict_line


FULL_CONFIG = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "initial_value": 350_000, "all_cash": True,
              "value_growth_rate": 0.01, "selling_cost_rate": 0.05,
              "fee_escalation_rate": 0.02},
    "house": {"initial_value": 400_000, "all_cash": True,
              "value_growth_rate": 0.01, "selling_cost_rate": 0.05,
              "annual_maintenance_rate": 0.01},
    "rent": {"monthly_rent": 2_000, "rent_escalation_rate": 0.025,
             "invested_down_payment": 50_000, "investment_return_rate": 0.05},
}

MINIMAL_CONFIG = {
    "years": 20, "discount_rate": 0.03,
    "house": {"initial_value": 400_000, "all_cash": True},
    "rent": {"monthly_rent": 2_000},
}


class TestFormatAssumptions:
    def test_full_config_echoes_mode_discount_and_per_option(self):
        lines = format_assumptions(load_config_dict(FULL_CONFIG))
        joined = "\n".join(lines)
        assert "mode: real terms" in joined
        assert "discount_rate 3.0%" in joined
        assert "condo: value growth +1.0%/yr" in joined
        assert "fee escalation +2.0%/yr" in joined
        assert "house: value growth +1.0%/yr" in joined
        assert "selling_cost_rate 5.0%" in joined
        assert "rent: escalation +2.5%/yr" in joined
        assert "invested capital $50,000 at +5.0%/yr" in joined

    def test_defaults_applied_line_lists_missing_assumptions(self):
        lines = format_assumptions(load_config_dict(MINIMAL_CONFIG))
        defaults = [ln for ln in lines if ln.startswith("defaults applied:")]
        assert len(defaults) == 1
        assert "rent.rent_escalation_rate=1.0% [FP Canada 2026 PAG]" in defaults[0]
        assert "rent.investment_return_rate=3.0% [FP Canada 2026 PAG]" in defaults[0]
        assert "house.selling_cost_rate=5.0% [WOWA 2026]" in defaults[0]
        assert "economic.mode='real'" in defaults[0]

    def test_no_defaults_line_when_all_provided(self):
        lines = format_assumptions(load_config_dict(FULL_CONFIG))
        assert not any(ln.startswith("defaults applied:") for ln in lines)


class TestVerdictLines:
    """B.4: the text report quotes the runner-up margin (the decision figure)
    and states which decisiveness rule applied; a single-path Monte Carlo is
    stamped 'not a forecast' instead of printing P(x cheapest): 100%."""

    def test_report_quotes_runner_up_margin_and_decisiveness(self):
        from hde.deterministic import compute_deterministic
        spec = load_config_dict(FULL_CONFIG)
        det = compute_deterministic(spec)
        report = format_text_report(det, None, spec.simulation, spec.economic, spec=spec)
        pvs = sorted(o.total_pv for o in (det.condo, det.house, det.rent))
        assert f"${pvs[1] - pvs[0]:,.0f}" in report          # runner-up gap, not costliest
        assert f"${pvs[2] - pvs[0]:,.0f}" not in report.split("decisiveness")[0]
        assert "decisiveness:" in report and "hde verdict rule" in report

    def test_single_path_monte_carlo_is_stamped_not_certain(self):
        from hde.deterministic import compute_deterministic
        from hde.monte_carlo import run_monte_carlo
        spec = load_config_dict({**FULL_CONFIG, "simulation": {"num_sims": 30}})
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        report = format_text_report(det, mc, spec.simulation, spec.economic, spec=spec)
        assert "not a forecast" in report
        assert "100.0%" not in report
        assert "single-path" in report.split("decisiveness:")[1].split("\n")[0]


class TestTextReportEchoHeader:
    def test_report_with_spec_carries_assumption_header(self):
        spec = load_config_dict(FULL_CONFIG)
        report = format_text_report(
            ComparisonDeterministicResult(), None,
            spec.simulation, spec.economic, spec=spec,
        )
        assert report.startswith("Assumptions")
        assert "mode: real terms" in report

    def test_report_without_spec_unchanged(self):
        # backward-compatible signature: no spec, no echo header
        report = format_text_report(ComparisonDeterministicResult(), None,
                                    SimulationParams(years=10, discount_rate=0.03),
                                    EconomicParams())
        assert not report.startswith("Assumptions")


class TestThreeStateVerdictLine:
    """2026-09-04: served answers showed a table reading "rent, not decisive"
    beside a 66% house column. The console verdict line has the verdict's
    three states, and a disagreement names both figures — the central-case
    margin and the majority's probability. One builder (`verdict_line`) feeds
    the report and the -q summary line."""

    def _verdict(self, **kw):
        base = dict(best="rent", runner_up="house", margin_pv=4_551.0, margin_frac=0.011,
                    monthly_equivalent=30.0, prob_best=0.39, decisive=False, state="tie",
                    rule="mc_floor", reason="", mc_mean_best=None, mc_best="rent",
                    mc_prob_best=0.39)
        base.update(kw)
        return Verdict(**base)

    def test_option(self):
        v = self._verdict(decisive=True, state="option", prob_best=0.8, mc_prob_best=0.8)
        assert verdict_line(v) == "Cheapest: Rent saves $4,551 vs House (runner-up)"

    def test_tie(self):
        assert verdict_line(self._verdict()) == "Too close to call: Rent edges House by $4,551 (1.1%)"

    def test_disagreement_names_both_figures(self):
        v = self._verdict(state="disagreement", mc_best="house", mc_prob_best=0.61)
        assert verdict_line(v) == (
            "Best guess says Rent by $4,551 (1.1%) vs House; most futures say House "
            "(61% cheapest) — the two disagree, not decisive")

    def test_nothing_to_compare_has_no_line(self):
        v = self._verdict(runner_up=None, state="option", decisive=True, rule="single_option")
        assert verdict_line(v) is None and verdict_line(None) is None

    def test_the_report_carries_the_disagreement_line_and_its_reason(self):
        from hde.deterministic import compute_deterministic
        spec = load_config_dict({**FULL_CONFIG, "simulation": {"num_sims": 30, "investment_return_vol": 0.1}})
        det = compute_deterministic(spec)
        ranked = sorted(("condo", "house", "rent"), key=lambda k: getattr(det, k).total_pv)
        probs = {ranked[0]: 0.34, ranked[1]: 0.60, ranked[2]: 0.06}

        def opt(k):
            pv = getattr(det, k).total_pv
            return MonteCarloOptionResult(np.full(30, pv), MonteCarloSummary(pv, 0.0, pv, pv, pv))

        mc = ComparisonMonteCarloResult(
            condo=opt("condo"), house=opt("house"), rent=opt("rent"),
            prob_condo_cheapest=probs["condo"], prob_house_cheapest=probs["house"],
            prob_rent_cheapest=probs["rent"])
        report = format_text_report(det, mc, spec.simulation, spec.economic, spec=spec)
        assert f"\nBest guess says {ranked[0].capitalize()} by $" in report
        assert f"most futures say {ranked[1].capitalize()} (60% cheapest) — the two disagree, not decisive" in report
        assert f"decisiveness: best guess says {ranked[0]} by $" in report
        assert "Cheapest:" not in report and "Too close to call:" not in report
