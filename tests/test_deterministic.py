"""
Tests for deterministic calculations.
"""

import pytest
from hde.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    EventConfig,
    RecurringOtherCost,
    ComparisonSpec,
)
from hde.deterministic import compute_deterministic
from hde.pv import pv_annuity, pv_growth_annuity, pv_single


class TestCondoDeterministic:
    """Tests for condo deterministic calculations."""
    
    def test_simple_condo_level_fee(self):
        """Test condo with level (no escalation) fees."""
        condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.0, all_cash=True)
        house = HouseParams(initial_value=0, annual_maintenance_rate=0.0, all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # Expected: PV of $4800/year for 20 years at 3%
        annual_fee = 400 * 12
        expected = pv_annuity(annual_fee, 0.03, 20)
        
        assert abs(result.condo.breakdown["fee_pv"] - expected) < 1.0
        assert result.condo.breakdown["events_pv"] == 0.0
        assert result.condo.breakdown["other_pv"] == 0.0
    
    def test_condo_with_escalation(self):
        """Test condo with fee escalation."""
        condo = CondoParams(monthly_fee=400, fee_escalation_rate=0.02, all_cash=True)
        house = HouseParams(initial_value=0, annual_maintenance_rate=0.0, all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # With escalation, PV should be higher than level
        annual_fee = 400 * 12
        level_pv = pv_annuity(annual_fee, 0.03, 20)
        
        assert result.condo.breakdown["fee_pv"] > level_pv
    
    def test_condo_with_event(self):
        """Test condo with a one-time event."""
        event = EventConfig(name="special_assessment", base_cost=5000, expected_year=10)
        condo = CondoParams(monthly_fee=400, events=[event], all_cash=True)
        house = HouseParams(initial_value=0, all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        expected_event_pv = pv_single(5000, 0.03, 10)
        assert abs(result.condo.breakdown["events_pv"] - expected_event_pv) < 0.01
    
    def test_condo_with_other_costs(self):
        """Test condo with other recurring costs."""
        other = RecurringOtherCost(name="insurance", annual_amount=1000, escalation_rate=0.0)
        condo = CondoParams(monthly_fee=0, other_recurring_costs=[other], all_cash=True)
        house = HouseParams(initial_value=0, all_cash=True)
        sim = SimulationParams(years=10, discount_rate=0.05)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        expected_other_pv = pv_annuity(1000, 0.05, 10)
        assert abs(result.condo.breakdown["other_pv"] - expected_other_pv) < 0.01
    
    def test_condo_reserves_offset_events(self):
        """Reserve contributions should reduce net event costs."""
        event = EventConfig(name="assessment", base_cost=10_000, expected_year=5)
        condo_no_reserve = CondoParams(monthly_fee=1000, events=[event], all_cash=True)
        condo_with_reserve = CondoParams(
            monthly_fee=1000,
            events=[event],
            reserve_contribution_rate=0.5,  # Save half the fee each year
            reserve_growth_rate=0.0,
            reserve_initial_balance=0.0,
            all_cash=True,
        )
        house = HouseParams(initial_value=0, all_cash=True)
        sim = SimulationParams(years=6, discount_rate=0.0)
        econ = EconomicParams()
        
        spec_no_reserve = ComparisonSpec(
            simulation=sim, economic=econ, condo=condo_no_reserve, house=house
        )
        spec_with_reserve = ComparisonSpec(
            simulation=sim, economic=econ, condo=condo_with_reserve, house=house
        )
        no_reserve_result = compute_deterministic(spec_no_reserve)
        reserve_result = compute_deterministic(spec_with_reserve)

        # With a 0% discount rate, reserve contributions (5 years * $6k) cover the $10k assessment.
        # Reserve coverage is stored as a negative `reserve_pv` offset (events_pv is gross),
        # so the offset lowers total_pv relative to the no-reserve case.
        assert reserve_result.condo.total_pv < no_reserve_result.condo.total_pv


class TestHouseDeterministic:
    """Tests for house deterministic calculations."""
    
    def test_simple_house_maintenance(self):
        """Test house with level maintenance (no value growth)."""
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(
            initial_value=400_000,
            value_growth_rate=0.0,
            annual_maintenance_rate=0.015,
            all_cash=True,
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # Expected: PV of $6000/year (0.015 * 400k) for 20 years at 3%
        annual_maint = 0.015 * 400_000
        expected = pv_annuity(annual_maint, 0.03, 20)

        assert abs(result.house.breakdown["maintenance_pv"] - expected) < 1.0
    
    def test_house_with_value_growth(self):
        """Test house with growing value (growing maintenance)."""
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(
            initial_value=400_000,
            value_growth_rate=0.02,
            annual_maintenance_rate=0.015,
            all_cash=True,
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # With value growth, maintenance PV should be higher
        annual_maint = 0.015 * 400_000
        level_pv = pv_annuity(annual_maint, 0.03, 20)

        assert result.house.breakdown["maintenance_pv"] > level_pv
    
    def test_house_with_events(self):
        """Test house with multiple events."""
        events = [
            EventConfig(name="roof", base_cost=12000, expected_year=15),
            EventConfig(name="hvac", base_cost=7000, expected_year=10),
        ]
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(initial_value=0, events=events, all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        expected = pv_single(12000, 0.03, 15) + pv_single(7000, 0.03, 10)
        assert abs(result.house.breakdown["events_pv"] - expected) < 0.01
    
    def test_house_maintenance_curve(self):
        """Maintenance should follow an age/condition curve."""
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(
            initial_value=100_000,
            value_growth_rate=0.0,
            annual_maintenance_rate=0.01,
            maintenance_curve=[(1, 0.01), (10, 0.02)],
            all_cash=True,
        )
        sim = SimulationParams(years=10, discount_rate=0.0)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # Curve rises from 1% to 2%, so PV should exceed flat 1% maintenance.
        flat_maint = pv_annuity(0.01 * 100_000, 0.0, 10)
        assert result.house.breakdown["maintenance_pv"] > flat_maint


class TestDiffCalculation:
    """Tests for difference calculation."""
    
    def test_diff_positive_house_more_expensive(self):
        """Test that positive diff means house is more expensive."""
        condo = CondoParams(monthly_fee=100, all_cash=True)  # Low fees
        house = HouseParams(initial_value=500_000, annual_maintenance_rate=0.02, all_cash=True)  # High maintenance
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        assert result.house.total_pv - result.condo.total_pv > 0
    
    def test_diff_negative_condo_more_expensive(self):
        """Test that negative diff means condo is more expensive."""
        condo = CondoParams(monthly_fee=1000, all_cash=True)  # High fees
        house = HouseParams(initial_value=100_000, annual_maintenance_rate=0.005, all_cash=True)  # Low maintenance
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        assert result.condo.total_pv - result.house.total_pv > 0
    
    def test_totals_sum_correctly(self):
        """Test that total equals sum of components."""
        event = EventConfig(name="roof", base_cost=10000, expected_year=10)
        other = RecurringOtherCost(name="insurance", annual_amount=1000)

        condo = CondoParams(monthly_fee=400, events=[event], other_recurring_costs=[other], all_cash=True)
        house = HouseParams(
            initial_value=400_000,
            annual_maintenance_rate=0.015,
            events=[event],
            other_recurring_costs=[other],
            all_cash=True,
        )
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        assert abs(result.condo.total_pv - sum(result.condo.breakdown.values())) < 0.01
        assert abs(result.house.total_pv - sum(result.house.breakdown.values())) < 0.01


class TestEventYearClamping:
    """Tests for event year clamping behavior."""
    
    def test_event_year_clamped_to_horizon(self):
        """Test that events beyond horizon are clamped."""
        event = EventConfig(name="far_future", base_cost=10000, expected_year=50)
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(initial_value=0, events=[event], all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # Event should be clamped to year 20
        expected = pv_single(10000, 0.03, 20)
        assert abs(result.house.breakdown["events_pv"] - expected) < 0.01
    
    def test_event_year_zero_clamped_to_one(self):
        """Test that events at year 0 are clamped to year 1."""
        event = EventConfig(name="immediate", base_cost=10000, expected_year=0)
        condo = CondoParams(monthly_fee=0, all_cash=True)
        house = HouseParams(initial_value=0, events=[event], all_cash=True)
        sim = SimulationParams(years=20, discount_rate=0.03)
        econ = EconomicParams()
        
        spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
        result = compute_deterministic(spec)
        
        # Event should be clamped to year 1
        expected = pv_single(10000, 0.03, 1)
        assert abs(result.house.breakdown["events_pv"] - expected) < 0.01


from hde.models import (
    ComparisonSpec, RentParams, IncomeParams, PayDropEvent,
    ComparisonDeterministicResult, CondoParams, HouseParams,
    SimulationParams, EconomicParams,
)


def _spec(condo=None, house=None, rent=None, income=None, years=10, dr=0.05):
    return ComparisonSpec(
        simulation=SimulationParams(years=years, discount_rate=dr),
        economic=EconomicParams(),
        condo=condo, house=house, rent=rent, income=income,
    )


class TestRentPV:
    def test_rent_pv_basic_no_dp(self):
        """Rent with zero invested_dp and no escalation = simple level annuity."""
        from hde.pv import pv_annuity
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.0, invested_down_payment=0.0)
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        expected = pv_annuity(2000.0 * 12, 0.05, 10)
        assert abs(result.rent.total_pv - expected) < 1.0

    def test_rent_pv_invested_dp_at_discount_rate(self):
        """When investment_return_rate == discount_rate, benefit PV == invested_dp."""
        rent = RentParams(
            monthly_rent=0.0,
            rent_escalation_rate=0.0,
            invested_down_payment=100_000.0,
            investment_return_rate=0.05,  # == discount_rate
        )
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        # invested_dp_benefit_pv is stored as negative; when r==dr benefit==100_000
        assert abs(result.rent.breakdown["invested_dp_benefit_pv"] + 100_000.0) < 10.0

    def test_rent_pv_invested_dp_higher_return(self):
        """When investment_return_rate > discount_rate, benefit > invested_dp."""
        rent = RentParams(
            monthly_rent=0.0,
            rent_escalation_rate=0.0,
            invested_down_payment=100_000.0,
            investment_return_rate=0.09,  # > discount_rate=0.05
        )
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        # benefit > 100_000 → invested_dp_benefit_pv more negative than -100_000
        assert result.rent.breakdown["invested_dp_benefit_pv"] < -100_000.0

    def test_rent_breakdown_keys_match_constant(self):
        from hde.models import RENT_BREAKDOWN_KEYS
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(rent=rent)
        result = compute_deterministic(spec)
        assert set(result.rent.breakdown.keys()) == RENT_BREAKDOWN_KEYS


class TestAffordabilityReport:
    def test_affordability_basic_income_trajectory(self):
        """Income trajectory with zero growth rate stays flat."""
        income = IncomeParams(annual_income=100_000.0, income_growth_rate=0.0)
        condo = CondoParams(monthly_fee=500.0, all_cash=True)
        spec = _spec(condo=condo, income=income, years=5)
        result = compute_deterministic(spec)
        assert len(result.income_report.annual_incomes) == 5
        assert all(abs(inc - 100_000.0) < 1.0 for inc in result.income_report.annual_incomes)

    def test_affordability_pay_drop_persists(self):
        """Pay drop in year 2 affects year 2 onward (permanent)."""
        income = IncomeParams(
            annual_income=100_000.0,
            income_growth_rate=0.0,
            pay_drop_events=[PayDropEvent(year=2, magnitude=0.8)],
        )
        condo = CondoParams(monthly_fee=500.0, all_cash=True)
        spec = _spec(condo=condo, income=income, years=5)
        result = compute_deterministic(spec)
        incomes = result.income_report.annual_incomes
        assert abs(incomes[0] - 100_000.0) < 1.0   # year 1: unaffected
        assert abs(incomes[1] - 80_000.0) < 1.0    # year 2: 20% cut applied
        assert abs(incomes[2] - 80_000.0) < 1.0    # year 3: persists (no growth)

    def test_affordability_threshold_flagging(self):
        """Years where ratio > threshold appear in years_exceeding list."""
        income = IncomeParams(annual_income=10_000.0, affordability_threshold=0.35)
        condo = CondoParams(monthly_fee=500.0, all_cash=True)  # 6000/yr / 10000 = 0.60 > 0.35
        spec = _spec(condo=condo, income=income, years=3)
        result = compute_deterministic(spec)
        assert len(result.income_report.years_condo_exceeds) == 3

    def test_no_income_no_report(self):
        """When income=None, income_report is None."""
        condo = CondoParams(monthly_fee=500.0, all_cash=True)
        spec = _spec(condo=condo)
        result = compute_deterministic(spec)
        assert result.income_report is None


def test_house_total_equals_sum_of_breakdown():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    h = HouseParams(initial_value=400_000, value_growth_rate=0.03,
                    annual_maintenance_rate=0.01, down_payment=80_000,
                    mortgage_rate=0.05, mortgage_term_years=25)
    sim = SimulationParams(years=10, discount_rate=0.04)
    econ = EconomicParams(mode="real")
    res = _compute_house_option(h, sim, econ)
    assert res.total_pv == pytest.approx(sum(res.breakdown.values()), rel=1e-12)
    for k in ("downpayment_pv", "mortgage_pv", "terminal_equity_pv"):
        assert k in res.breakdown
    assert res.breakdown["downpayment_pv"] == 80_000
    assert res.breakdown["terminal_equity_pv"] < 0  # equity is a benefit

def test_house_terminal_equity_oracle():
    """value_N = P0*(1+g)^N pinned; all-cash so equity = value_N*(1-sc)."""
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    from hde.pv import pv_single
    h = HouseParams(initial_value=500_000, value_growth_rate=0.03,
                    annual_maintenance_rate=0.0, all_cash=True, selling_cost_rate=0.05)
    sim = SimulationParams(years=10, discount_rate=0.05)
    res = _compute_house_option(h, sim, EconomicParams(mode="real"))
    value_N = 500_000 * (1.03 ** 10)
    assert res.breakdown["terminal_equity_pv"] == pytest.approx(
        -pv_single(value_N * 0.95, 0.05, 10), rel=1e-9)

def test_price_drop_makes_owning_costlier():
    """Sign check the whole point of S4b: lower appreciation -> higher net cost."""
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_house_option
    sim = SimulationParams(years=10, discount_rate=0.04)
    econ = EconomicParams(mode="real")
    base = dict(initial_value=400_000, annual_maintenance_rate=0.01, all_cash=True)
    high = _compute_house_option(HouseParams(value_growth_rate=0.05, **base), sim, econ)
    low = _compute_house_option(HouseParams(value_growth_rate=-0.02, **base), sim, econ)
    assert low.total_pv > high.total_pv  # a price crash makes owning more expensive

def test_condo_zero_value_all_cash_unchanged_total():
    """Condo with default initial_value=0 + all_cash -> zero equity -> carrying-cost total."""
    from hde.models import CondoParams, SimulationParams, EconomicParams
    from hde.deterministic import _compute_condo_option
    c = CondoParams(monthly_fee=400, fee_escalation_rate=0.02, all_cash=True)
    sim = SimulationParams(years=10, discount_rate=0.04)
    res = _compute_condo_option(c, sim, EconomicParams(mode="real"))
    assert res.breakdown["terminal_equity_pv"] == 0.0
    assert res.breakdown["downpayment_pv"] == 0.0
    assert res.breakdown["mortgage_pv"] == 0.0
    # carrying total == fee+events+other+reserve (financing terms are all 0)
    assert res.total_pv == pytest.approx(
        res.breakdown["fee_pv"] + res.breakdown["events_pv"]
        + res.breakdown["other_pv"] + res.breakdown["reserve_pv"], rel=1e-12)


def test_financing_pv_all_cash():
    from hde.deterministic import _financing_pv
    # all_cash: D = initial_value, no mortgage, terminal = value_N*(1-sc)
    dp, mort, term_eq = _financing_pv(
        initial_value=500_000, down_payment=None, mortgage_rate=None,
        mortgage_term_years=None, all_cash=True, selling_cost_rate=0.05,
        value_N=671_958.19, dr=0.05, n_years=10,
    )
    assert dp == 500_000
    assert mort == 0.0
    assert term_eq == pytest.approx(-391_897.84, abs=0.05)

def test_financing_pv_mortgage():
    from hde.deterministic import _financing_pv
    from hde.pv import mortgage_payment, pv_annuity, outstanding_balance, pv_single
    dp, mort, term_eq = _financing_pv(
        initial_value=500_000, down_payment=100_000, mortgage_rate=0.05,
        mortgage_term_years=25, all_cash=False, selling_cost_rate=0.05,
        value_N=671_958.19, dr=0.04, n_years=10,
    )
    M = mortgage_payment(400_000, 0.05, 25)
    assert dp == 100_000
    assert mort == pytest.approx(pv_annuity(M, 0.04, 10), rel=1e-9)
    B_N = outstanding_balance(400_000, 0.05, 25, 10, M)
    assert term_eq == pytest.approx(-pv_single(671_958.19 * 0.95 - B_N, 0.04, 10), rel=1e-9)

def test_financing_pv_guard_raises():
    from hde.deterministic import _financing_pv
    with pytest.raises(ValueError):
        _financing_pv(
            initial_value=500_000, down_payment=None, mortgage_rate=None,
            mortgage_term_years=None, all_cash=False, selling_cost_rate=0.05,
            value_N=600_000, dr=0.04, n_years=10,
        )


def test_affordability_house_cost_includes_mortgage():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _annual_costs_for_option
    from hde.pv import mortgage_payment
    h = HouseParams(initial_value=400_000, value_growth_rate=0.0,
                    annual_maintenance_rate=0.01, down_payment=80_000,
                    mortgage_rate=0.05, mortgage_term_years=25)
    sim = SimulationParams(years=5, discount_rate=0.04)
    costs = _annual_costs_for_option("house", h, sim, EconomicParams(mode="real"))
    M = mortgage_payment(320_000, 0.05, 25)
    # year 1 cost = maintenance(=0.01*400000) + mortgage payment
    assert costs[0] == pytest.approx(400_000 * 0.01 + M, rel=1e-9)


def test_affordability_all_cash_house_no_mortgage_term():
    from hde.models import HouseParams, SimulationParams, EconomicParams
    from hde.deterministic import _annual_costs_for_option
    h = HouseParams(initial_value=400_000, annual_maintenance_rate=0.01, all_cash=True)
    sim = SimulationParams(years=3, discount_rate=0.04)
    costs = _annual_costs_for_option("house", h, sim, EconomicParams(mode="real"))
    assert costs[0] == pytest.approx(400_000 * 0.01, rel=1e-9)  # no mortgage term


def test_report_mentions_financing_lines():
    """Report must surface terminal_equity and down_payment lines in the per-option breakdown."""
    from hde.models import HouseParams, SimulationParams, EconomicParams, ComparisonSpec
    from hde.deterministic import compute_deterministic
    from hde.reporting import format_text_report
    sim = SimulationParams(years=10, discount_rate=0.04)
    econ = EconomicParams(mode="real")
    spec = ComparisonSpec(
        simulation=sim,
        economic=econ,
        house=HouseParams(
            initial_value=400_000, value_growth_rate=0.03,
            annual_maintenance_rate=0.01, all_cash=True,
        ),
    )
    det = compute_deterministic(spec)
    # format_text_report(det, mc, sim, econ) — actual signature at reporting.py:27
    text = format_text_report(det, None, sim, econ)
    assert "terminal_equity_pv" in text
    assert "downpayment_pv" in text
    assert "mortgage_pv" in text


def test_nominal_mode_affordability_composes_inflation():
    """Nominal mode composes inflation into the cost NUMERATOR exactly as the PV
    engine does (readiness plan D.6) — and, since the 2026-09-02 review, into
    income too, so the ratio itself does not drift on inflation."""
    from hde.config import load_config_dict
    from hde.deterministic import _annual_costs_for_option, _compute_income_trajectory
    base = {"years": 6, "discount_rate": 0.03, "rates": "real",
            "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True,
                      "fee_escalation_rate": 0.01},
            "income": {"annual_income": 80_000, "income_growth_rate": 0.01}}
    real = load_config_dict(base)
    nominal = load_config_dict({**base, "economic": {"mode": "nominal", "inflation_rate": 0.02}})
    costs_r = _annual_costs_for_option("condo", real.condo, real.simulation, real.economic)
    costs_n = _annual_costs_for_option("condo", nominal.condo, nominal.simulation, nominal.economic)
    inc_r = _compute_income_trajectory(real.income, 6, real.economic)
    inc_n = _compute_income_trajectory(nominal.income, 6, nominal.economic)
    for t in range(6):
        assert costs_n[t] / costs_r[t] == pytest.approx(1.02 ** t)
        assert inc_n[t] / inc_r[t] == pytest.approx(1.02 ** t)


class TestNominalRentOtherCosts:
    """Readiness plan D (2026-09-01): in nominal mode the rent option's other
    recurring costs compose inflation like every other escalating flow, and
    the zero-vol Monte Carlo reproduces the deterministic figure."""

    CFG = {
        "years": 6,
        "discount_rate": 0.03,
        "rates": "real",
        "economic": {"mode": "nominal", "inflation_rate": 0.02},
        "rent": {
            "monthly_rent": 2000,
            "rent_escalation_rate": 0.0,
            "other_recurring_costs": [
                {"name": "insurance", "annual_amount": 1200, "escalation_rate": 0.01},
            ],
        },
        "simulation": {"num_sims": 3, "random_seed": 1},
    }

    def test_other_pv_composes_inflation(self):
        from hde.config import load_config_dict
        from hde.pv import pv_recurring_with_escalation
        spec = load_config_dict(self.CFG)
        det = compute_deterministic(spec)
        composed = (1 + 0.01) * (1 + 0.02) - 1
        # the typed 3% is a REAL rate and is composed too (2026-09-04); discount
        # at the rate the spec carries, which is the rate the engine uses
        dr = spec.simulation.discount_rate
        assert dr == pytest.approx(1.03 * 1.02 - 1)
        expected = pv_recurring_with_escalation(1200, composed, dr, 6)
        assert det.rent.breakdown["other_pv"] == pytest.approx(expected)
        assert det.rent.breakdown["other_pv"] > pv_recurring_with_escalation(1200, 0.01, dr, 6)

    def test_zero_vol_monte_carlo_matches_deterministic(self):
        from hde.config import load_config_dict
        from hde.monte_carlo import run_monte_carlo
        spec = load_config_dict(self.CFG)
        det = compute_deterministic(spec)
        mc = run_monte_carlo(spec)
        assert mc.rent.summary.mean == pytest.approx(det.rent.total_pv)


class TestRenterCapitalSymmetry:
    """2026-09-02 (user-model dogfood): the renter's invested capital must be
    charged at year 0 exactly as the buyer's down payment is; only the excess of
    its return over the discount rate may move the verdict."""

    def test_capital_charged_at_year_zero(self):
        rent = RentParams(monthly_rent=1.0, rent_escalation_rate=0.0,
                          invested_down_payment=100_000.0, investment_return_rate=0.05)
        result = compute_deterministic(_spec(rent=rent, years=10, dr=0.05))
        assert result.rent.breakdown["invested_capital_pv"] == 100_000.0
        # at r_inv == dr the capital leg nets to zero: total is the rent alone
        assert result.rent.total_pv == pytest.approx(result.rent.breakdown["rent_pv"], abs=1e-6)

    def test_null_case_gap_is_only_the_time_value_of_a_non_yielding_asset(self):
        """Buyer: all-cash V, no growth/fees/selling cost. Renter: ~no rent, D = V
        invested at dr. Truth: buyer cost = V(1 − (1+dr)^−N), renter cost ≈ 0."""
        from hde.config import load_config_dict
        cfg = {"years": 10, "discount_rate": 0.03,
               "condo": {"monthly_fee": 0, "initial_value": 100_000, "all_cash": True,
                         "value_growth_rate": 0.0, "selling_cost_rate": 0.0},
               "rent": {"monthly_rent": 0.01, "rent_escalation_rate": 0.0,
                        "invested_down_payment": 100_000, "investment_return_rate": 0.03}}
        det = compute_deterministic(load_config_dict(cfg))
        truth = 100_000 * (1 - 1.03 ** -10)
        assert det.condo.total_pv == pytest.approx(truth, rel=1e-9)
        assert det.rent.total_pv == pytest.approx(0.0, abs=2.0)

    def test_monte_carlo_books_the_same_capital_leg(self):
        from hde.config import load_config_dict
        from hde.monte_carlo import run_monte_carlo
        cfg = {"years": 10, "discount_rate": 0.03,
               "rent": {"monthly_rent": 1500, "invested_down_payment": 80_000,
                        "investment_return_rate": 0.04},
               "simulation": {"num_sims": 3, "random_seed": 1}}
        spec = load_config_dict(cfg)
        assert run_monte_carlo(spec).rent.summary.mean == pytest.approx(compute_deterministic(spec).rent.total_pv)


class TestReviewModifications:
    """Findings of the 2026-09-02 adversarial review of the capital-leg fix."""

    def test_f2_nominal_mode_keeps_the_capital_legs_symmetric(self):
        """House all-cash V at real growth g vs renter D = V at real return g:
        the capital gap is zero in real mode AND in nominal mode."""
        from hde.config import load_config_dict
        for econ in ({"mode": "real"}, {"mode": "nominal", "inflation_rate": 0.021}):
            cfg = {"years": 25, "discount_rate": 0.03, "economic": econ,
                   "house": {"initial_value": 480_000, "all_cash": True, "value_growth_rate": 0.02,
                             "annual_maintenance_rate": 0.0, "selling_cost_rate": 0.0,
                             "purchase_costs": 0},
                   "rent": {"monthly_rent": 0.01, "rent_escalation_rate": 0.0,
                            "invested_down_payment": 480_000, "investment_return_rate": 0.02}}
            det = compute_deterministic(load_config_dict(cfg))
            assert det.house.total_pv == pytest.approx(det.rent.total_pv, abs=5.0), econ

    def test_f2_nominal_mode_income_grows_with_the_numerator(self):
        """Affordability ratios do not drift on inflation: nominal == real when
        nothing is financed (the mortgage payment is nominal-as-entered by design)."""
        from hde.config import load_config_dict
        base = {"years": 8, "discount_rate": 0.03,
                "condo": {"monthly_fee": 400, "initial_value": 300_000, "all_cash": True,
                          "fee_escalation_rate": 0.01},
                "income": {"annual_income": 80_000, "income_growth_rate": 0.01}}
        real = compute_deterministic(load_config_dict(base)).income_report.condo_ratios
        nominal = compute_deterministic(load_config_dict(
            {**base, "economic": {"mode": "nominal", "inflation_rate": 0.02}})).income_report.condo_ratios
        assert real == pytest.approx(nominal)

    def test_f3_rent_events_honour_min_year(self):
        from hde.config import load_config_dict
        from hde.monte_carlo import run_monte_carlo
        from hde.pv import pv_single
        from hde.story_plots import _cumulative_cost_curves
        cfg = {"years": 10, "discount_rate": 0.03, "rates": "real",
               "rent": {"monthly_rent": 1_000, "rent_escalation_rate": 0.0,
                        "events": [{"name": "move", "base_cost": 10_000, "expected_year": 3, "min_year": 5}]},
               "simulation": {"num_sims": 2, "random_seed": 1}}
        spec = load_config_dict(cfg)
        det = compute_deterministic(spec)
        assert det.rent.breakdown["events_pv"] == pytest.approx(pv_single(10_000, 0.03, 5))
        assert run_monte_carlo(spec).rent.summary.mean == pytest.approx(det.rent.total_pv)
        assert _cumulative_cost_curves(spec)["rent"]["net"][-1] == pytest.approx(det.rent.total_pv)

    def test_f1_capital_spread_is_warned_in_dollars(self):
        from hde.config import coherence_warnings, load_config_dict
        cfg = {"years": 15, "discount_rate": 0.05,
               "rent": {"monthly_rent": 2_000, "invested_down_payment": 480_000, "investment_return_rate": 0.03}}
        # the spread warning, not the no-tax-block warning that shares its prefix (2026-09-05)
        warns = [w for w in coherence_warnings(load_config_dict(cfg))
                 if w.startswith("rent: invested capital") and "vs discount_rate" in w]
        assert len(warns) == 1 and "charged to the renter" in warns[0] and "$120," in warns[0]
        neutral = {**cfg, "rent": {**cfg["rent"], "investment_return_rate": 0.05}}
        assert not any(w.startswith("rent: invested capital") and "vs discount_rate" in w
                       for w in coherence_warnings(load_config_dict(neutral)))
