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
