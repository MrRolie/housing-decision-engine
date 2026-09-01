"""
Reporting tests (src/hde/reporting.py): the assumption echo block (audit U1).
"""

from hde.config import load_config_dict
from hde.models import (
    ComparisonDeterministicResult,
    EconomicParams,
    SimulationParams,
)
from hde.reporting import format_assumptions, format_text_report


FULL_CONFIG = {
    "years": 20, "discount_rate": 0.03,
    "economic": {"mode": "real", "inflation_rate": 0.0},
    "condo": {"monthly_fee": 450, "initial_value": 350_000, "all_cash": True,
              "value_growth_rate": 0.01, "selling_cost_rate": 0.05,
              "fee_escalation_rate": 0.02},
    "house": {"initial_value": 400_000, "all_cash": True,
              "value_growth_rate": 0.01, "selling_cost_rate": 0.05},
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
        assert "rent.rent_escalation_rate=3.0%" in defaults[0]
        assert "rent.investment_return_rate=7.0%" in defaults[0]
        assert "house.selling_cost_rate=5.0%" in defaults[0]
        assert "economic.mode='real'" in defaults[0]

    def test_no_defaults_line_when_all_provided(self):
        lines = format_assumptions(load_config_dict(FULL_CONFIG))
        assert not any(ln.startswith("defaults applied:") for ln in lines)


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
