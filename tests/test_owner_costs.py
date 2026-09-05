"""
2026-09-02 (user-model dogfood): purchase-time costs are a first-class owned-option
input, the discount rate has a cited default, and the warnings say by name what
an owned option leaves unmodelled.
"""

import pytest

from hde.anchors import ANCHORS
from hde.config import affordability_warnings, coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.rates import deflate
from hde.monte_carlo import run_monte_carlo
from hde.serialization import format_assumptions
from hde.story_plots import _cumulative_cost_curves

BASE = {
    "years": 10,
    "condo": {"monthly_fee": 300, "initial_value": 400_000, "all_cash": True,
              "value_growth_rate": 0.01, "purchase_costs": 12_000,
              "other_recurring_costs": [{"name": "tax", "annual_amount": 3_000, "escalation_rate": 0.0}]},
    "rent": {"monthly_rent": 1_800},
    "simulation": {"num_sims": 3, "random_seed": 1},
}


class TestPurchaseCosts:
    def test_charged_once_at_year_zero_in_breakdown_and_total(self):
        spec = load_config_dict(BASE)
        det = compute_deterministic(spec)
        assert det.condo.breakdown["purchase_costs_pv"] == 12_000
        without = load_config_dict({**BASE, "condo": {**BASE["condo"], "purchase_costs": 0}})
        assert det.condo.total_pv - compute_deterministic(without).condo.total_pv == pytest.approx(12_000)

    def test_monte_carlo_and_race_curve_agree(self):
        spec = load_config_dict(BASE)
        det = compute_deterministic(spec)
        assert run_monte_carlo(spec).condo.summary.mean == pytest.approx(det.condo.total_pv)
        curves = _cumulative_cost_curves(spec)
        assert curves["condo"]["net"][-1] == pytest.approx(det.condo.total_pv)
        assert curves["condo"]["paid"][0] == pytest.approx(400_000 + 12_000)

    def test_outside_the_affordability_ratio(self):
        cfg = {**BASE, "income": {"annual_income": 100_000}}
        with_costs = compute_deterministic(load_config_dict(cfg)).income_report.condo_ratios
        no_costs = compute_deterministic(load_config_dict(
            {**cfg, "condo": {**cfg["condo"], "purchase_costs": 0}})).income_report.condo_ratios
        assert with_costs == no_costs

    def test_negative_refused(self):
        with pytest.raises(Exception, match="purchase_costs must be non-negative"):
            load_config_dict({**BASE, "condo": {**BASE["condo"], "purchase_costs": -1}})


class TestDiscountRateDefault:
    def test_defaults_to_the_anchor_and_is_echoed_with_its_cite(self):
        spec = load_config_dict(BASE)
        assert spec.simulation.discount_rate == ANCHORS["simulation.discount_rate"].value == 0.03
        assert "simulation.discount_rate" in spec.defaults_applied
        joined = "\n".join(format_assumptions(spec))
        assert "simulation.discount_rate=3.0% [FP Canada 2026 PAG (60/40 real)]" in joined

    def test_explicit_value_is_not_echoed_as_a_default(self):
        spec = load_config_dict({**BASE, "discount_rate": 0.04})
        # typed as quoted, deflated by the planning inflation (2026-09-05)
        planning = ANCHORS["economic.inflation_rate.nominal_planning"].value
        assert spec.simulation.discount_rate == pytest.approx(deflate(0.04, planning))
        assert "simulation.discount_rate" not in spec.defaults_applied


class TestOwnerCostWarnings:
    def test_fully_specified_owned_option_is_quiet(self):
        assert not any("not modelled" in w for w in coherence_warnings(load_config_dict(BASE)))

    def test_missing_purchase_and_carrying_costs_named(self):
        cfg = {**BASE, "condo": {"monthly_fee": 300, "initial_value": 400_000, "all_cash": True,
                                 "value_growth_rate": 0.01}}
        warns = [w for w in coherence_warnings(load_config_dict(cfg)) if w.startswith("condo: not modelled")]
        assert len(warns) == 1
        assert "purchase_costs" in warns[0] and "other_recurring_costs" in warns[0]
        assert "toward buying" in warns[0]

    def test_zero_growth_warns_whether_defaulted_or_explicit(self):
        """The neutral warning fires on the defaulted zero and on a zero DECLARED
        real. A typed 0.0 under the as-quoted default (2026-09-05) is flat
        sticker prices — a real decline the `rates:` line shows, not the
        neutral zero — so it is a stated view and does not warn."""
        explicit = {**BASE, "rates": "real", "condo": {**BASE["condo"], "value_growth_rate": 0.0}}
        defaulted = {**BASE, "condo": {k: v for k, v in BASE["condo"].items() if k != "value_growth_rate"}}
        for cfg in (explicit, defaulted):
            assert any("value_growth_rate=0.0%" in w for w in coherence_warnings(load_config_dict(cfg)))
        quoted_zero = {**BASE, "condo": {**BASE["condo"], "value_growth_rate": 0.0}}
        assert load_config_dict(quoted_zero).condo.value_growth_rate < 0
        assert not any("value_growth_rate=0.0%" in w for w in coherence_warnings(load_config_dict(quoted_zero)))
        assert not any("value_growth_rate=0.0%" in w for w in coherence_warnings(load_config_dict(BASE)))


class TestAffordabilityWarning:
    def test_breach_reaches_the_warning_channel(self):
        cfg = {**BASE, "income": {"annual_income": 15_000}}  # fees 3.6k + tax 3k = 44% of income
        det = compute_deterministic(load_config_dict(cfg))
        warns = affordability_warnings(det)
        assert any(w.startswith("affordability: condo") and "exceeds 32%" in w for w in warns)

    def test_no_income_block_no_warning(self):
        assert affordability_warnings(compute_deterministic(load_config_dict(BASE))) == []
