"""Dogfood round two (2026-09-02): the renter's return can lose, financed purchase
costs ride the loan, act 6 respects the tie band, sweeps carry percentiles."""

import numpy as np
import pytest

from hde.config import coherence_warnings, load_config_dict
from hde.deterministic import compute_deterministic
from hde.monte_carlo import run_monte_carlo
from hde.pv import mortgage_payment, pv_annuity
from hde.story_plots import _sweep_axis, find_break_evens, market_line_sentence, sweep_rent_totals
from hde.sweep import run_sweep


class TestInvestmentReturnVol:
    CFG = {"years": 10, "discount_rate": 0.03,
           "rent": {"monthly_rent": 1500, "invested_down_payment": 100_000, "investment_return_rate": 0.03},
           "simulation": {"num_sims": 4000, "random_seed": 7}}

    def test_zero_vol_equals_deterministic(self):
        spec = load_config_dict(self.CFG)
        assert run_monte_carlo(spec).rent.summary.mean == pytest.approx(compute_deterministic(spec).rent.total_pv)

    def test_annual_shocks_are_mean_preserving_and_can_lose(self):
        spec = load_config_dict({**self.CFG, "simulation": {**self.CFG["simulation"], "investment_return_vol": 0.15}})
        det = compute_deterministic(spec).rent.total_pv
        mc = run_monte_carlo(spec)
        assert mc.rent.summary.mean == pytest.approx(det, rel=0.03)       # E[Π(1+r)·shock] = (1+r)^N
        # a bad decade exists: some paths end with capital below principal, i.e.
        # rent total above rent_pv + D − D (the deterministic benefit at r = dr nets to 0)
        rent_only = compute_deterministic(load_config_dict(
            {**self.CFG, "rent": {"monthly_rent": 1500}})).rent.total_pv
        assert float(np.max(mc.rent.pvs)) > rent_only + 10_000

    def test_asymmetric_tail_warning(self):
        cfg = {**self.CFG, "condo": {"monthly_fee": 300, "initial_value": 400_000, "all_cash": True,
                                     "value_growth_rate": 0.01, "purchase_costs": 5000,
                                     "other_recurring_costs": [{"name": "tax", "annual_amount": 3000, "escalation_rate": 0.0}],
                                     "price_shock": {"annual_hazard": 0.02}}}
        assert any(w.startswith("asymmetric tails") for w in coherence_warnings(load_config_dict(cfg)))
        quiet = {**cfg, "simulation": {**cfg["simulation"], "investment_return_vol": 0.1}}
        assert not any(w.startswith("asymmetric tails") for w in coherence_warnings(load_config_dict(quiet)))


class TestFinancedPurchaseCosts:
    BASE = {"years": 10, "discount_rate": 0.03,
            "house": {"initial_value": 400_000, "down_payment": 40_000, "mortgage_rate": 0.04,
                      "mortgage_term_years": 25, "value_growth_rate": 0.01, "annual_maintenance_rate": 0.01,
                      "purchase_costs": 6_000,
                      "other_recurring_costs": [{"name": "tax", "annual_amount": 3400, "escalation_rate": 0.0}]}}

    def test_premium_rides_the_loan(self):
        with_p = load_config_dict({**self.BASE, "house": {**self.BASE["house"], "financed_purchase_costs": 12_000}})
        det = compute_deterministic(with_p)
        payment = mortgage_payment(400_000 - 40_000 + 12_000, 0.04, 25)
        assert det.house.breakdown["mortgage_pv"] == pytest.approx(pv_annuity(payment, 0.03, 10))
        assert det.house.breakdown["downpayment_pv"] == 40_000          # never year-0 cash
        assert run_monte_carlo(load_config_dict({**self.BASE, "house": {**self.BASE["house"], "financed_purchase_costs": 12_000},
                                                 "simulation": {"num_sims": 2}})).house.summary.mean == pytest.approx(det.house.total_pv)

    def test_all_cash_refuses_financing(self):
        cfg = {**self.BASE, "house": {"initial_value": 400_000, "all_cash": True, "financed_purchase_costs": 1}}
        with pytest.raises(Exception, match="requires a mortgage block"):
            load_config_dict(cfg)


class TestActSixTieBand:
    def test_on_the_break_even_reads_as_a_tie(self):
        cfg = {"years": 10, "discount_rate": 0.03,
               "condo": {"monthly_fee": 300, "initial_value": 400_000, "all_cash": True, "value_growth_rate": 0.01,
                         "purchase_costs": 5000, "other_recurring_costs": [{"name": "tax", "annual_amount": 3000, "escalation_rate": 0.0}]},
               "rent": {"monthly_rent": 1200, "invested_down_payment": 405_000, "investment_return_rate": 0.03}}
        spec = load_config_dict(cfg)
        xs = _sweep_axis(1200)
        be = find_break_evens(xs, *(lambda t: (t["rent"], t["condo"]))(sweep_rent_totals(spec, xs)))
        assert be, "fixture must cross break-even inside the sweep window"
        near = load_config_dict({**cfg, "rent": {**cfg["rent"], "monthly_rent": round(be[0] * 1.04)}})
        sentence = market_line_sentence(near, compute_deterministic(near))
        assert "inside the tie band" in sentence and "too close to call" in sentence


class TestSweepPercentiles:
    def test_rows_carry_monte_carlo_when_it_ran(self):
        raw = {"years": 10, "rent": {"monthly_rent": 1500, "invested_down_payment": 50_000},
               "simulation": {"num_sims": 5, "investment_return_vol": 0.1}}
        rows = run_sweep(raw, "years", [5, 10], monte_carlo=True)["rows"]
        assert rows[0]["monte_carlo"]["rent"]["p95"] >= rows[0]["monte_carlo"]["rent"]["p5"]
        assert run_sweep(raw, "years", [5], monte_carlo=False)["rows"][0]["monte_carlo"] is None
