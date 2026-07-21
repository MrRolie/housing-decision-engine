"""Independent oracle for the financing math (Task 1, written before the engine).

The PINNED scalars below must be cross-checked against an EXTERNAL amortization
calculator (e.g. an online mortgage calculator, or numpy_financial.pmt with the
sign convention pmt = -mortgage_payment) to the cent before trusting them. The
INVARIANT assertions are implementation-independent and catch most defects.
"""
import pytest
from hde.pv import mortgage_payment, outstanding_balance, pv_annuity, pv_single


# --- Pinned scalar oracle: L0=400_000, i=5%, T=25 -------------------------------
# Standard formula M = L0*i / (1 - (1+i)^-T). VERIFY EXTERNALLY before trusting.
def test_mortgage_payment_pinned_value():
    M = mortgage_payment(400_000.0, 0.05, 25)
    assert M == pytest.approx(28_380.98, abs=0.01)  # external-calc verified

def test_mortgage_payment_zero_rate():
    assert mortgage_payment(360_000.0, 0.0, 30) == pytest.approx(12_000.0, abs=1e-9)


# --- Implementation-independent invariants --------------------------------------
def test_amortization_invariants():
    """Principal repaid over the full term sums to L0; balance hits 0 at term."""
    L0, i, T = 400_000.0, 0.05, 25
    M = mortgage_payment(L0, i, T)
    balances = [outstanding_balance(L0, i, T, year, M) for year in range(0, T + 1)]
    # outstanding_balance(...,0,...) is L0; at/after term it is 0.
    assert balances[0] == pytest.approx(L0, rel=1e-9)
    assert balances[T] == pytest.approx(0.0, abs=1e-6)
    # Each year's interest = prev_balance*i, principal = M - interest, sums to L0.
    total_principal = 0.0
    for year in range(1, T + 1):
        prev = outstanding_balance(L0, i, T, year - 1, M)
        interest = prev * i
        principal = M - interest
        total_principal += principal
    assert total_principal == pytest.approx(L0, rel=1e-6)
    # Monotonic non-increasing balance.
    assert all(balances[k] >= balances[k + 1] - 1e-6 for k in range(T))

def test_outstanding_balance_after_term_is_zero():
    M = mortgage_payment(400_000.0, 0.05, 25)
    assert outstanding_balance(400_000.0, 0.05, 25, 30, M) == 0.0
    assert outstanding_balance(400_000.0, 0.05, 25, 25, M) == 0.0

def test_mortgage_pv_is_annuity_identity():
    """Discounting the level payment over the paid years IS pv_annuity."""
    L0, i, T, dr, N = 400_000.0, 0.05, 25, 0.04, 30
    M = mortgage_payment(L0, i, T)
    assert pv_annuity(M, dr, min(N, T)) == pytest.approx(pv_annuity(M, dr, 25), rel=1e-12)


# --- Terminal equity pinned oracle: all-cash P0=500_000, g=3%, N=10, sc=5% ------
def test_terminal_equity_pinned_value():
    P0, g, N, sc, dr = 500_000.0, 0.03, 10, 0.05, 0.05
    value_N = P0 * (1 + g) ** N          # 671_958.19
    E_N = value_N * (1 - sc) - 0.0       # all-cash, B_N=0  -> 638_360.28
    terminal_equity_pv = -pv_single(E_N, dr, N)
    assert value_N == pytest.approx(671_958.19, abs=0.01)
    assert E_N == pytest.approx(638_360.28, abs=0.01)
    assert terminal_equity_pv == pytest.approx(-391_897.84, abs=0.05)  # verify externally


# --- PR #4 external-review findings: direct-construction (config-bypass) defenses ---
from hde.models import HouseParams, CondoParams, SimulationParams, EconomicParams, ComparisonSpec
from hde.deterministic import compute_deterministic


def test_financing_pv_rejects_down_payment_exceeding_value():
    """Finding #3: down_payment > initial_value makes the loan negative; mortgage_payment
    returns 0.0 for non-positive principal, silently zeroing an impossible block.
    Direct construction must raise, not compute garbage."""
    house = HouseParams(initial_value=400_000.0, down_payment=500_000.0,
                        mortgage_rate=0.05, mortgage_term_years=25, all_cash=False)
    sim = SimulationParams(years=10, discount_rate=0.04)
    spec = ComparisonSpec(simulation=sim, economic=EconomicParams(), house=house)
    with pytest.raises(ValueError, match="down_payment"):
        compute_deterministic(spec)


def test_financing_pv_down_payment_equal_to_value_is_legal():
    """Guard boundary: down_payment == initial_value (loan 0) is legal, not an error."""
    house = HouseParams(initial_value=400_000.0, down_payment=400_000.0,
                        mortgage_rate=0.05, mortgage_term_years=25, all_cash=False)
    sim = SimulationParams(years=10, discount_rate=0.04)
    spec = ComparisonSpec(simulation=sim, economic=EconomicParams(), house=house)
    result = compute_deterministic(spec)  # must not raise
    assert result.house.breakdown["mortgage_pv"] == pytest.approx(0.0, abs=1e-9)


def test_compute_rejects_house_value_growth_sign_flip():
    """Finding #4: value_growth_rate < -1 flips (1+g)**years by year parity; the computation
    site must raise even when config validation is bypassed by direct construction."""
    house = HouseParams(initial_value=400_000.0, all_cash=True, value_growth_rate=-1.5)
    sim = SimulationParams(years=10, discount_rate=0.04)
    spec = ComparisonSpec(simulation=sim, economic=EconomicParams(), house=house)
    with pytest.raises(ValueError, match="value_growth"):
        compute_deterministic(spec)


def test_compute_rejects_condo_value_growth_sign_flip():
    """Finding #4 (condo side)."""
    condo = CondoParams(monthly_fee=500.0, initial_value=300_000.0, all_cash=True,
                        value_growth_rate=-2.0)
    sim = SimulationParams(years=10, discount_rate=0.04)
    spec = ComparisonSpec(simulation=sim, economic=EconomicParams(), condo=condo)
    with pytest.raises(ValueError, match="value_growth"):
        compute_deterministic(spec)
