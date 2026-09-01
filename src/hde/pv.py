"""
Present Value (PV) calculation utilities.

This module provides pure functions for computing present values of
various cash flow patterns. All functions are deterministic and have
no side effects.
"""

from typing import Dict


def pv_single(cost: float, rate: float, year: int) -> float:
    """
    Calculate the present value of a single future cash flow.
    
    Args:
        cost: The future cost amount
        rate: The discount rate (annual)
        year: The year when the cost occurs (1 = one year from now)
    
    Returns:
        Present value of the cost
    
    Example:
        >>> pv_single(1000, 0.05, 5)  # $1000 in 5 years at 5%
        783.5261664684589
    """
    if year <= 0:
        return cost
    return cost / ((1 + rate) ** year)


def pv_annuity(payment: float, rate: float, n_years: int) -> float:
    """
    Calculate the present value of a constant annuity.
    
    Assumes payments occur at the end of each year (ordinary annuity),
    starting at year 1 through year n_years.
    
    Args:
        payment: The constant annual payment amount
        rate: The discount rate (annual)
        n_years: Number of years of payments
    
    Returns:
        Present value of the annuity
    
    Example:
        >>> pv_annuity(1000, 0.05, 10)  # $1000/year for 10 years at 5%
        7721.734929184815
    """
    if n_years <= 0:
        return 0.0
    if rate == 0:
        return payment * n_years
    factor = (1 - (1 + rate) ** -n_years) / rate
    return payment * factor


def pv_growth_annuity(payment: float, rate: float, growth: float, n_years: int) -> float:
    """
    Calculate the present value of a growing annuity.
    
    The first payment occurs at year 1 and equals `payment`.
    Subsequent payments grow at `growth` rate annually.
    Year t payment = payment * (1 + growth)^(t-1)
    
    Args:
        payment: The payment in year 1 (first payment)
        rate: The discount rate (annual)
        growth: The annual growth rate of payments
        n_years: Number of years of payments
    
    Returns:
        Present value of the growing annuity
    
    Example:
        >>> pv_growth_annuity(1000, 0.05, 0.02, 10)  # Growing at 2%, discounted at 5%
        8505.956739...
    """
    if n_years <= 0:
        return 0.0
    if rate == 0 and growth == 0:
        return payment * n_years
    
    # Handle degenerate case where discount rate equals growth rate
    if abs(rate - growth) < 1e-12:
        # PV = n * payment / (1 + rate)
        return n_years * payment / (1 + rate)
    
    # Standard growing annuity formula
    # PV = payment * [1 - ((1+g)/(1+r))^n] / (r - g)
    factor = (1 - ((1 + growth) / (1 + rate)) ** n_years) / (rate - growth)
    return payment * factor


def pv_series(costs_by_year: Dict[int, float], rate: float) -> float:
    """
    Calculate the present value of a series of costs occurring at specific years.
    
    Args:
        costs_by_year: Dictionary mapping year -> cost amount
        rate: The discount rate (annual)
    
    Returns:
        Present value of all costs
    
    Example:
        >>> pv_series({5: 1000, 10: 2000}, 0.05)  # $1000 year 5, $2000 year 10
        2010.1148...
    """
    total_pv = 0.0
    for year, cost in costs_by_year.items():
        total_pv += pv_single(cost, rate, year)
    return total_pv


def pv_recurring_with_escalation(
    annual_amount: float,
    escalation_rate: float,
    discount_rate: float,
    n_years: int
) -> float:
    """
    Calculate PV of a recurring cost with escalation.
    
    This is a convenience wrapper that chooses between pv_annuity and
    pv_growth_annuity based on whether there's escalation.
    
    Year 1 cost = annual_amount * (1 + escalation_rate)
    
    Args:
        annual_amount: Base annual amount (at year 0)
        escalation_rate: Annual growth rate (0.0 = level payments)
        discount_rate: The discount rate (annual)
        n_years: Number of years
    
    Returns:
        Present value of the recurring costs
    """
    if n_years <= 0:
        return 0.0
    
    if escalation_rate == 0:
        return pv_annuity(annual_amount, discount_rate, n_years)
    else:
        # First year payment includes one year of escalation
        first_payment = annual_amount * (1 + escalation_rate)
        return pv_growth_annuity(first_payment, discount_rate, escalation_rate, n_years)


def mortgage_payment(principal: float, rate: float, term_years: int) -> float:
    """
    Level (constant) ANNUAL mortgage payment that amortizes `principal` over
    `term_years` at EFFECTIVE ANNUAL `rate`. M = P*r / (1 - (1+r)^-T); P/T when r == 0.

    Convention: one payment per year, annual compounding. A Canadian posted
    mortgage rate is quoted with semi-annual compounding and monthly payments;
    convert before use: r_eff = (1 + r_posted/2)^2 − 1 (the difference on the
    annual outlay is ≈ 1.7% at 5%). Stated in the schema note for
    mortgage_rate and in the figure glossary (docs/reference/ARCHITECTURE.md).
    """
    if term_years <= 0:
        raise ValueError(f"term_years must be positive, got {term_years}")
    if principal <= 0:
        return 0.0
    if rate == 0:
        return principal / term_years
    return principal * rate / (1 - (1 + rate) ** -term_years)


def outstanding_balance(
    principal: float, rate: float, term_years: int, year: int, payment: float
) -> float:
    """
    Remaining mortgage balance at the END of `year`, closed form (no loop).
    Zero at/after the term. B = L0*(1+r)^y - M*[(1+r)^y - 1]/r; L0 - M*y when r==0.
    """
    if year >= term_years:
        return 0.0
    if year <= 0:
        return principal
    if rate == 0:
        return max(0.0, principal - payment * year)
    return principal * (1 + rate) ** year - payment * ((1 + rate) ** year - 1) / rate


def pv_to_monthly_savings(pv: float, rate: float, n_years: int) -> float:
    """
    The level MONTHLY payment whose present value over n_years equals `pv`
    (the report's "≈ $/month equivalent" line): an amortizing annuity, not a
    sinking fund.

    Convention (readiness plan D.4, 2026-09-01): the monthly rate is the
    effective-annual rate converted exactly, m = (1 + rate)^(1/12) − 1, so the
    monthly line decomposes the SAME present value the rest of the report
    discounts at (1 + rate)^-t. (Before 2026-09-01 this used rate/12, which
    disagreed with the annual figures by ~1%.)

    PMT = pv · m / (1 − (1 + m)^−12n); pv / (12n) when rate == 0.

    Example:
        >>> round(pv_to_monthly_savings(100_000, 0.03, 20), 2)
        551.6
    """
    if n_years <= 0 or pv == 0:
        return 0.0
    n_months = n_years * 12
    if rate == 0:
        return pv / n_months
    monthly_rate = (1 + rate) ** (1 / 12) - 1
    return pv * monthly_rate / (1 - (1 + monthly_rate) ** -n_months)

