"""The tax treatment of the two sides' money (2026-09-05).

Until this module the engine taxed neither side: the renter's capital compounded
at `investment_return_rate` untouched and the owner's gain was credited at sale
untouched, with only the skill's not-modelled line naming the bias. The
renter-side drag is the size of served verdict margins. The design note is
docs/specs/2026-09-05-tax-treatment.md; this module is its arithmetic and its
sentences, and nothing here runs until a config states a `tax:` block.

What it owns:

* the marginal rate — typed as a fraction, or resolved from `income.annual_income`
  and the top-level `province` through the registry's 2026 brackets
  (`tax_rates.marginal_rate_breakdown`, imported inside the resolver so
  `import hde` never depends on it);
* the drag on the renter's TAXABLE share: gains are taxed in nominal terms, so
  the gross factor is composed to nominal, taxed at marginal × inclusion (or
  marginal × 1 for interest), and deflated back in real mode. Sheltered shares
  (TFSA, RRSP, FHSA) are untouched — the RRSP's pre-tax nature is symmetric
  across the two sides and is not modelled;
* the FHSA for a `first_time_buyer`: the deductible contributions over the
  saving years (annual limit, carry-forward, lifetime limit), the refunds — which
  accrue to BOTH sides, since the deduction does not depend on buying — and the
  renter's rollover haircut at the horizon at `retirement_marginal_rate`;
* the Home Buyers' Plan: the withdrawal joins the buyer's day-one cash (the
  existing capital legs price it — the renter earns the return on it, the
  buyer's down payment carries it) and the plan's own cost is its repayment
  schedule: fixed nominal outlays against the rebuilt RRSP credited at the
  horizon, zero when the return equals the discount rate;
* the owner's principal-residence exemption, named on the read-back — nothing in
  the owner's numbers changes.

Every figure is derived in the loader from the raw YAML, so `--sweep` and
`--break-even` re-derive it per grid point. Refusals are `TaxTreatmentError`,
a `ValueError`; the loader re-raises it as `ConfigValidationError`.

Import-light on purpose (anchors and rates only): `models` imports the record
types, so nothing here may import `models` or `config`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .anchors import ANCHORS

TREATMENTS: Tuple[str, ...] = ("capital_gains", "interest")
_PROVINCES = ("QC", "ON")
_SHARES = ("tfsa", "rrsp", "fhsa", "taxable")

# Entries read from the registry, by name. Read inside functions, never at
# import — a dataclass default reading one would tie `import hde` to the entry.
_INCLUSION = "tax.capital_gains_inclusion_rate"
_EXEMPT = "tax.principal_residence_exempt_fraction"
_FHSA = ("fhsa.annual_limit", "fhsa.lifetime_limit", "fhsa.carry_forward_max", "fhsa.max_years_open")
_HBP = ("hbp.withdrawal_limit", "hbp.repayment_years", "hbp.repayment_grace_years")
_TFSA_ROOM = "tfsa.cumulative_room_since_2009"


class TaxTreatmentError(ValueError):
    """A `tax:` block the engine cannot price honestly."""


def _anchor(name: str) -> float:
    value = ANCHORS[name].value
    assert value is not None, name
    return value


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    """A statutory rate as its page prints it: 20.5%, 19%, 9.15%, 16.5%."""
    text = f"{x * 100:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenterCapital:
    """Where the renter's capital sits at year 0, in dollars. `fhsa_derived`
    says the FHSA share came from the `fhsa` block (balance + contributions)
    rather than being stated."""

    tfsa: float
    rrsp: float
    fhsa: float
    taxable: float
    fhsa_derived: bool = False

    @property
    def total(self) -> float:
        return self.tfsa + self.rrsp + self.fhsa + self.taxable

    @property
    def sheltered(self) -> float:
        return self.tfsa + self.rrsp + self.fhsa


@dataclass(frozen=True)
class FhsaPlan:
    """The saving years before the purchase and what they produce."""

    balance: float
    stated_contributions: Tuple[float, ...]   # per saving year, as stated
    years_until_purchase: int
    contributions: Tuple[float, ...]          # per saving year, as the room allows
    refunds: float                            # Σ contributions × marginal rate
    share_at_year0: float                     # balance + Σ contributions
    lifetime_remaining: float                 # after the saving years
    annual_limit: float
    carry_forward_max: float
    lifetime_limit: float
    max_years_open: float

    @property
    def contributed(self) -> float:
        return sum(self.contributions)

    @property
    def capped(self) -> bool:
        return any(c < s for c, s in zip(self.contributions, self.stated_contributions))


@dataclass(frozen=True)
class HbpPlan:
    """The Home Buyers' Plan withdrawal and its repayment schedule. The first
    repayment falls in year `grace_years` (the anchor is first repayment year −
    withdrawal year); one tranche a year for `repayment_years` years."""

    withdrawal: float
    limit: float
    repayment_years: int
    grace_years: int

    @property
    def tranche(self) -> float:
        return self.withdrawal / self.repayment_years

    def repayment_years_within(self, n_years: int) -> Tuple[int, ...]:
        """τ_j = min(t_j, N) per tranche: a tranche due past the horizon
        returns at the horizon."""
        return tuple(min(self.grace_years + j, n_years) for j in range(self.repayment_years))


@dataclass(frozen=True)
class HbpLeg:
    """The repayment leg priced: outlays (PV), the RRSP rebuilt by the horizon
    and its PV, the net charged to the owned option."""

    outlays_pv: float
    rebuilt_at_horizon: float
    rebuilt_pv: float
    net_pv: float
    taus: Tuple[int, ...]


@dataclass(frozen=True)
class TaxParams:
    """The `tax:` block, resolved: every figure the engines and the read-back read."""

    marginal_rate: float
    marginal_rate_source: str                 # "typed" | "resolved"
    marginal_rate_detail: str                 # the bracket derivation, or "as typed"
    province: Optional[str]
    income: Optional[float]
    taxable_return_treatment: str
    treatment_stated: bool
    inclusion_rate: float
    retirement_marginal_rate: float
    retirement_rate_source: str               # "typed" | "default"
    renter_capital: Optional[RenterCapital]
    fhsa: Optional[FhsaPlan]
    hbp: Optional[HbpPlan]
    principal_residence_exempt_fraction: float

    @property
    def refunds(self) -> float:
        return self.fhsa.refunds if self.fhsa is not None else 0.0

    @property
    def hbp_withdrawal(self) -> float:
        return self.hbp.withdrawal if self.hbp is not None else 0.0

    @property
    def day_one_additions(self) -> float:
        """What joins a first-time buyer's down payment: the refunds and the HBP."""
        return self.refunds + self.hbp_withdrawal

    @property
    def inclusion(self) -> float:
        return self.inclusion_rate if self.taxable_return_treatment == "capital_gains" else 1.0


# ---------------------------------------------------------------------------
# The drag
# ---------------------------------------------------------------------------

def after_tax_factor(gross_factor: float, mode: str, inflation_rate: float,
                     marginal_rate: float, inclusion: float) -> float:
    """One year's growth factor on the taxable share after tax. Gains are taxed
    in NOMINAL terms: the factor is composed to nominal in real mode, the gain
    taxed at marginal × inclusion, and the result deflated back. Linear on a
    loss year (a negative drag — losses assumed usable against gains), and
    exact for the Monte Carlo's shocked factor as for the deterministic one."""
    nominal = gross_factor * (1 + inflation_rate) if mode == "real" else gross_factor
    after = 1 + (nominal - 1) * (1 - marginal_rate * inclusion)
    return after / (1 + inflation_rate) if mode == "real" else after


def terminal_from_growth(tax: Optional[TaxParams], capital: float,
                         sheltered_growth: float, taxable_growth: float) -> float:
    """V_N from the two cumulative growth factors — the sheltered shares at the
    gross factor (the FHSA share haircut at the retirement rate), the taxable
    share and the refunds at the after-tax factor. Without a block, or without
    renter capital in it, the whole capital compounds at the gross factor
    exactly as before."""
    if tax is None or tax.renter_capital is None:
        return capital * sheltered_growth  # `capital` already carries any refunds
    rc = tax.renter_capital
    return ((rc.tfsa + rc.rrsp) * sheltered_growth
            + rc.fhsa * sheltered_growth * (1 - tax.retirement_marginal_rate)
            + (rc.taxable + tax.refunds) * taxable_growth)


@dataclass(frozen=True)
class RenterTerminal:
    """The renter's capital at the horizon, decomposed for the read-back."""

    capital: float                 # D + R, charged at year 0
    value: float                   # V_N
    untaxed_value: float           # (D + R)(1 + r)^N
    drag: float                    # (T + R)[(1 + r)^N − A^N]
    haircut: float                 # t_ret · F (1 + r)^N
    fhsa_grown: float              # F (1 + r)^N
    after_tax_factor: float        # A, in the run's terms
    after_tax_factor_nominal: float
    blended_rate: float            # (V_N / capital)^(1/N) − 1


def renter_terminal(capital: float, r: float, n_years: int, mode: str,
                    inflation_rate: float, tax: Optional[TaxParams]) -> RenterTerminal:
    """The deterministic V_N of the design note §4.3 with its diagnostics. `r`
    is the return as the engines hold it (real in real mode, composed in
    nominal mode); the after-tax factor composes it to nominal itself."""
    gross = (1 + r) ** n_years
    total = capital + (tax.refunds if tax is not None else 0.0)
    if tax is None or tax.renter_capital is None:
        value = total * gross
        rate = (value / total) ** (1 / n_years) - 1 if total > 0 and n_years > 0 else r
        return RenterTerminal(total, value, value, 0.0, 0.0, 0.0, 1 + r, 1 + r, rate)
    a = after_tax_factor(1 + r, mode, inflation_rate, tax.marginal_rate, tax.inclusion)
    a_nom = after_tax_factor(1 + r, "nominal", 0.0, tax.marginal_rate, tax.inclusion) \
        if mode == "nominal" else a * (1 + inflation_rate)
    value = terminal_from_growth(tax, total, gross, a ** n_years)
    rc = tax.renter_capital
    drag = (rc.taxable + tax.refunds) * (gross - a ** n_years)
    fhsa_grown = rc.fhsa * gross
    haircut = tax.retirement_marginal_rate * fhsa_grown
    rate = (value / total) ** (1 / n_years) - 1 if total > 0 and n_years > 0 else r
    return RenterTerminal(total, value, total * gross, drag, haircut, fhsa_grown, a, a_nom, rate)


# ---------------------------------------------------------------------------
# The FHSA
# ---------------------------------------------------------------------------

def _contribution_schedule(annual_contribution: Any, years: int) -> Tuple[float, ...]:
    """A scalar applies to every saving year; a list is per year, its last
    value carried forward when short."""
    if isinstance(annual_contribution, (list, tuple)):
        stated = [float(c) for c in annual_contribution]
        if not stated:
            stated = [0.0]
        while len(stated) < years:
            stated.append(stated[-1])
        return tuple(stated[:years])
    return tuple(float(annual_contribution) for _ in range(years))


def fhsa_plan(balance: float, annual_contribution: Any, years_until_purchase: int,
              marginal_rate: float) -> FhsaPlan:
    """The saving-years schedule of the design note §4.4: each year's deductible
    contribution is the lesser of the stated one and the room — the annual limit
    plus the carry-forward, capped by the lifetime room; today's balance stands
    in for the contributions to date and no unused room is assumed on entry."""
    annual, lifetime, cf_max, max_open = (_anchor(n) for n in _FHSA)
    stated = _contribution_schedule(annual_contribution, years_until_purchase)
    contributions: List[float] = []
    carry = 0.0
    paid = float(balance)
    for wanted in stated:
        room = min(annual + carry, max(lifetime - paid, 0.0))
        c = min(wanted, room)
        contributions.append(c)
        carry = min(cf_max, carry + annual - c)
        paid += c
    total = sum(contributions)
    return FhsaPlan(
        balance=float(balance), stated_contributions=stated,
        years_until_purchase=int(years_until_purchase),
        contributions=tuple(contributions), refunds=marginal_rate * total,
        share_at_year0=float(balance) + total,
        lifetime_remaining=max(lifetime - paid, 0.0),
        annual_limit=annual, carry_forward_max=cf_max, lifetime_limit=lifetime,
        max_years_open=max_open,
    )


# ---------------------------------------------------------------------------
# The HBP
# ---------------------------------------------------------------------------

def hbp_repayment_leg(plan: HbpPlan, r: float, dr: float, n_years: int, mode: str,
                      inflation_rate: float) -> HbpLeg:
    """The design note §4.5: tranche outlays at their years (fixed nominal
    dollars — deflated in real mode) against the RRSP they rebuild, credited at
    the horizon at the renter's return, sheltered. Zero when r = dr."""
    taus = plan.repayment_years_within(n_years)
    outlays_pv = 0.0
    rebuilt = 0.0
    for tau in taus:
        out = plan.tranche / (1 + inflation_rate) ** tau if mode == "real" else plan.tranche
        outlays_pv += out / (1 + dr) ** tau
        rebuilt += out * (1 + r) ** (n_years - tau)
    rebuilt_pv = rebuilt / (1 + dr) ** n_years
    return HbpLeg(outlays_pv=outlays_pv, rebuilt_at_horizon=rebuilt, rebuilt_pv=rebuilt_pv,
                  net_pv=outlays_pv - rebuilt_pv, taus=taus)


# ---------------------------------------------------------------------------
# Resolution (the loader's entry)
# ---------------------------------------------------------------------------

def _fraction(block: Dict[str, Any], key: str, what: str) -> Optional[float]:
    if key not in block:
        return None
    value = float(block[key])
    if not 0.0 <= value < 1.0:
        raise TaxTreatmentError(
            f"tax.{key}={block[key]} — {what} is a fraction of income in [0, 1) "
            f"(0.3612 = 36.12%), never a percentage and never converted")
    return value


def _resolve_rate(income: Optional[Dict[str, Any]], province: Optional[str]) -> Tuple[float, str, str, float]:
    """(rate, detail, province code, taxable income) from the registry's brackets,
    or a refusal naming both paths — typing the rate, or income + QC/ON."""
    annual = income.get("annual_income") if isinstance(income, dict) else None
    code = province.strip().upper() if isinstance(province, str) and province.strip() else None
    fix = "type tax.marginal_rate, or state income.annual_income with a top-level province of QC or ON"
    if annual is None:
        raise TaxTreatmentError(
            f"tax: no marginal_rate typed and none resolvable — income.annual_income is missing; {fix}")
    if code not in _PROVINCES:
        where = f"province {province!r}" if code else "no top-level province"
        raise TaxTreatmentError(
            f"tax: no marginal_rate typed and none resolvable — {where} has no anchored brackets "
            f"(QC or ON); {fix}")
    from .tax_rates import marginal_rate_breakdown  # the registry's brackets; lazy on purpose
    breakdown = marginal_rate_breakdown(float(annual), code)
    return breakdown.combined_rate, marginal_rate_detail(breakdown), code, float(annual)


def marginal_rate_detail(breakdown: Any) -> str:
    """The derivation in one clause: `federal 20.5% × (1 − 16.5% Québec
    abatement) + QC 19% [tax.federal.*, tax.qc.* 2026]`."""
    code = breakdown.province.upper()
    federal = f"federal {_pct(breakdown.federal_rate)}"
    if breakdown.quebec_abatement:
        federal += f" × (1 − {_pct(breakdown.quebec_abatement)} Québec abatement)"
    provincial = f"{code} {_pct(breakdown.provincial_rate)}"
    if breakdown.surtax_rate:
        provincial += f" × (1 + {_pct(breakdown.surtax_rate)} surtax)"
    return f"{federal} + {provincial} [tax.federal.*, tax.{code.lower()}.* 2026]"


def _first_time_buyers(owned: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """(options flagged first_time_buyer, those of them bought all-cash)."""
    flagged: List[str] = []
    all_cash: List[str] = []
    for name, block in owned.items():
        if not isinstance(block, dict):
            continue
        flag = block.get("first_time_buyer", False)
        if flag is True or (isinstance(flag, str) and flag.strip().lower() == "true"):
            flagged.append(name)
            cash = block.get("all_cash", False)
            if cash is True or (isinstance(cash, str) and cash.strip().lower() == "true"):
                all_cash.append(name)
    return flagged, all_cash


def resolve(data: Dict[str, Any], *, rent: Optional[Dict[str, Any]],
            income: Optional[Dict[str, Any]], province: Optional[str],
            owned: Dict[str, Dict[str, Any]]) -> Optional[TaxParams]:
    """The `tax:` block of a raw config as `TaxParams`; None when absent."""
    if "tax" not in data:
        return None
    block = data["tax"]
    if not isinstance(block, dict):
        raise TaxTreatmentError(f"tax: must be a mapping, got {type(block).__name__}")

    treatment = block.get("taxable_return_treatment", "capital_gains")
    if treatment not in TREATMENTS:
        raise TaxTreatmentError(
            f"tax.taxable_return_treatment must be capital_gains | interest, got {treatment!r}")

    typed = _fraction(block, "marginal_rate", "a marginal rate")
    if typed is not None:
        rate, detail, code, annual = typed, "as typed", (
            province.strip().upper() if isinstance(province, str) else None), None
        source = "typed"
    else:
        rate, detail, code, annual = _resolve_rate(income, province)
        source = "resolved"
    retirement = _fraction(block, "retirement_marginal_rate", "a retirement marginal rate")

    renter_stated = "renter_capital" in block
    fhsa_stated = "fhsa" in block
    hbp_stated = "hbp_withdrawal" in block
    renter_capital_total = float(rent.get("invested_down_payment", 0.0)) if isinstance(rent, dict) else 0.0

    if (renter_stated or fhsa_stated or hbp_stated) and rent is None:
        what = "tax.renter_capital" if renter_stated else ("tax.fhsa" if fhsa_stated else "tax.hbp_withdrawal")
        raise TaxTreatmentError(
            f"{what} without a rent: block — the block prices the two sides' money against each "
            f"other; add rent: (with invested_down_payment) or drop {what}")
    if not renter_stated and renter_capital_total > 0:
        raise TaxTreatmentError(
            f"tax.renter_capital is required when rent.invested_down_payment > 0 — where do the "
            f"renter's {_money(renter_capital_total)} sit: {{tfsa, rrsp, fhsa, taxable}} in dollars, "
            f"summing to that figure")

    plan: Optional[FhsaPlan] = None
    hbp: Optional[HbpPlan] = None
    if fhsa_stated or hbp_stated:
        flagged, all_cash = _first_time_buyers(owned)
        what = "tax.fhsa" if fhsa_stated else "tax.hbp_withdrawal"
        if not flagged:
            raise TaxTreatmentError(
                f"{what} needs an owned option with first_time_buyer: true — the FHSA withdrawal "
                f"and the Home Buyers' Plan are first-home programs")
        if all_cash:
            raise TaxTreatmentError(
                f"{what} with all_cash: true on {', '.join(all_cash)} — nothing to add to an "
                f"all-cash purchase; drop one of the two")
    if fhsa_stated:
        plan = _parse_fhsa(block["fhsa"], rate)
    if hbp_stated:
        hbp = _parse_hbp(block["hbp_withdrawal"])

    capital: Optional[RenterCapital] = None
    if renter_stated:
        capital = _parse_renter_capital(block["renter_capital"], renter_capital_total, plan)
        if hbp is not None and hbp.withdrawal > capital.rrsp + 0.005:
            raise TaxTreatmentError(
                f"tax.hbp_withdrawal={_money(hbp.withdrawal)} exceeds the RRSP share "
                f"tax.renter_capital.rrsp={_money(capital.rrsp)} — the plan withdraws RRSP money "
                f"the household holds")

    return TaxParams(
        marginal_rate=rate, marginal_rate_source=source, marginal_rate_detail=detail,
        province=code, income=annual,
        taxable_return_treatment=treatment, treatment_stated="taxable_return_treatment" in block,
        inclusion_rate=_anchor(_INCLUSION),
        retirement_marginal_rate=rate if retirement is None else retirement,
        retirement_rate_source="default" if retirement is None else "typed",
        renter_capital=capital, fhsa=plan, hbp=hbp,
        principal_residence_exempt_fraction=_anchor(_EXEMPT),
    )


def _parse_fhsa(block: Any, marginal_rate: float) -> FhsaPlan:
    if not isinstance(block, dict):
        raise TaxTreatmentError("tax.fhsa must be a mapping {balance, annual_contribution, years_until_purchase}")
    balance = float(block.get("balance", 0.0))
    years = int(block.get("years_until_purchase", 0))
    contribution = block.get("annual_contribution", 0.0)
    if balance < 0 or years < 0:
        raise TaxTreatmentError("tax.fhsa: balance and years_until_purchase must be zero or more")
    values = contribution if isinstance(contribution, (list, tuple)) else [contribution]
    if any(float(c) < 0 for c in values):
        raise TaxTreatmentError("tax.fhsa.annual_contribution must be zero or more (a figure, or one per saving year)")
    return fhsa_plan(balance, contribution, years, marginal_rate)


def _parse_hbp(value: Any) -> HbpPlan:
    withdrawal = float(value)
    limit, years, grace = (_anchor(n) for n in _HBP)
    if withdrawal < 0:
        raise TaxTreatmentError("tax.hbp_withdrawal must be zero or more")
    if withdrawal > limit + 0.005:
        raise TaxTreatmentError(
            f"tax.hbp_withdrawal={_money(withdrawal)} exceeds the Home Buyers' Plan limit "
            f"{_money(limit)} [hbp.withdrawal_limit]")
    return HbpPlan(withdrawal=withdrawal, limit=limit, repayment_years=int(years), grace_years=int(grace))


def _parse_renter_capital(block: Any, total: float, plan: Optional[FhsaPlan]) -> RenterCapital:
    if not isinstance(block, dict):
        raise TaxTreatmentError("tax.renter_capital must be a mapping {tfsa, rrsp, fhsa, taxable} in dollars")
    shares = {}
    for key in _SHARES:
        value = float(block.get(key, 0.0))
        if value < 0:
            raise TaxTreatmentError(f"tax.renter_capital.{key} must be zero or more, got {value}")
        shares[key] = value
    derived = plan is not None
    if derived:
        if "fhsa" in block:
            raise TaxTreatmentError(
                "tax.renter_capital.fhsa is stated beside tax.fhsa — the FHSA share is derived from "
                "the fhsa block (balance + contributions over the saving years); drop one")
        shares["fhsa"] = plan.share_at_year0
    capital = RenterCapital(fhsa_derived=derived, **shares)
    if abs(capital.total - total) > 1.0:
        parts = " + ".join(f"{k.upper() if k != 'taxable' else k} {_money(shares[k])}"
                           + (" (derived)" if k == "fhsa" and derived else "") for k in _SHARES)
        raise TaxTreatmentError(
            f"tax.renter_capital sums to {_money(capital.total)} ({parts}); "
            f"rent.invested_down_payment is {_money(total)} — the shares must add up to the "
            f"capital the engine credits the renter")
    return capital


# ---------------------------------------------------------------------------
# Sentences (the read-back)
# ---------------------------------------------------------------------------

def rate_source_clause(tax: TaxParams) -> str:
    if tax.marginal_rate_source == "typed":
        return f"marginal rate {tax.marginal_rate:.2%} as typed"
    return (f"marginal rate {tax.marginal_rate:.2%} resolved from income {_money(tax.income or 0)} "
            f"in {tax.province} — {tax.marginal_rate_detail}")


def tax_line(tax: TaxParams, terminal: Optional[RenterTerminal], r: Optional[float],
             n_years: int, dr: float, mode: str, inflation_rate: float, owned: bool) -> str:
    """The `tax:` assumptions line — the rate and its source, the split, the
    drag applied, the FHSA rollover haircut, the owner's exemption."""
    parts = [rate_source_clause(tax)]
    rc = tax.renter_capital
    if rc is not None and terminal is not None and r is not None:
        parts.append(
            f"renter capital {_money(rc.total)} = sheltered {_money(rc.sheltered)} "
            f"(TFSA {_money(rc.tfsa)} + RRSP {_money(rc.rrsp)} + FHSA {_money(rc.fhsa)}) "
            f"+ taxable {_money(rc.taxable)} (+ FHSA refunds {_money(tax.refunds)})")
        r_nom = (1 + r) * (1 + inflation_rate) - 1 if mode == "real" else r
        if tax.taxable_return_treatment == "capital_gains":
            how = (f"(1 − {tax.marginal_rate:.2%} × {tax.inclusion_rate:.0%} inclusion, capital gains"
                   f"{'' if tax.treatment_stated else ' — default'})")
            cite = " [tax.capital_gains_inclusion_rate]"
        else:
            how = f"(1 − {tax.marginal_rate:.2%}, interest — every dollar of return taxed)"
            cite = ""
        a_nom = terminal.after_tax_factor_nominal - 1
        if mode == "real":
            result = (f"{a_nom:.2%} nominal, {terminal.after_tax_factor - 1:.2%} real after tax{cite} "
                      f"(gains are taxed in nominal terms)")
            rate_text = f"{r_nom:.2%} nominal"
        else:
            result = f"{a_nom:.2%} after tax{cite}"
            rate_text = f"{r_nom:.2%}"
        pv = terminal.drag / (1 + dr) ** n_years
        parts.append(
            f"taxable share: {rate_text} × {how} = {result}; blended {terminal.blended_rate:.2%}; "
            f"drag {_money(terminal.drag)} at year {n_years} (PV {_money(pv)}) charged to rent")
    if owned:
        parts.append("owner: principal-residence exemption — no tax on the equity gain at sale "
                     "[tax.principal_residence_exempt_fraction]")
    if rc is not None and rc.fhsa > 0 and terminal is not None:
        source = "= current, default" if tax.retirement_rate_source == "default" else "as typed"
        max_open = tax.fhsa.max_years_open if tax.fhsa is not None else _anchor("fhsa.max_years_open")
        pv = terminal.haircut / (1 + dr) ** n_years
        parts.append(
            f"FHSA share {_money(rc.fhsa)} rolls to an RRSP for the renter (within {max_open:.0f} years "
            f"of opening [fhsa.max_years_open]) — haircut {tax.retirement_marginal_rate:.2%} retirement "
            f"marginal rate ({source}) on {_money(terminal.fhsa_grown)} at year {n_years} = "
            f"{_money(terminal.haircut)} (PV {_money(pv)}) charged to rent [tax.retirement_marginal_rate]")
    return "tax: " + " · ".join(parts)


def financing_additions(tax: Optional[TaxParams], first_time_buyer: bool) -> str:
    """` + FHSA refunds $R + HBP $H` for the financing line's head."""
    if tax is None or not first_time_buyer:
        return ""
    text = ""
    if tax.fhsa is not None and tax.refunds:
        text += f" + FHSA refunds {_money(tax.refunds)}"
    if tax.hbp is not None and tax.hbp.withdrawal:
        text += f" + HBP {_money(tax.hbp.withdrawal)}"
    return text


def fhsa_clause(tax: TaxParams) -> str:
    plan = tax.fhsa
    assert plan is not None
    if plan.years_until_purchase == 0:
        return f"fhsa: balance {_money(plan.balance)}, no saving years — no refunds to add"
    capped = ""
    if plan.capped:
        stated = plan.stated_contributions
        shown = (_money(stated[0]) + "/yr" if len(set(stated)) == 1
                 else ", ".join(_money(s) for s in stated))
        capped = f" (stated {shown}, capped by room)"
    years = "saving year" if plan.years_until_purchase == 1 else "saving years"
    return (f"fhsa: balance {_money(plan.balance)} + {_money(plan.contributed)} contributed over "
            f"{plan.years_until_purchase} {years}{capped} (room {_money(plan.annual_limit)}/yr + "
            f"carry-forward ≤ {_money(plan.carry_forward_max)}, lifetime {_money(plan.lifetime_limit)}, "
            f"{_money(plan.lifetime_remaining)} remaining [fhsa.annual_limit, fhsa.carry_forward_max, "
            f"fhsa.lifetime_limit]) → refunds {_money(plan.refunds)} at {tax.marginal_rate:.2%}, "
            f"added to both sides' capital")


def hbp_line(name: str, tax: TaxParams, leg: HbpLeg, n_years: int, mode: str) -> str:
    plan = tax.hbp
    assert plan is not None
    at_horizon = sum(1 for t in leg.taus if t == n_years)
    horizon = ""
    if at_horizon:
        horizon = (f"; {at_horizon} tranche{'s' if at_horizon != 1 else ''} fall{'s' if at_horizon == 1 else ''} "
                   f"at or past year {n_years} and return{'s' if at_horizon == 1 else ''} at the horizon")
    side = "charged to" if leg.net_pv >= 0 else "credited to"
    deflated = " (fixed nominal dollars, deflated)" if mode == "real" else ""
    return (f"{name} hbp: {_money(plan.withdrawal)} withdrawn from the RRSP into the down payment "
            f"(≤ {_money(plan.limit)} [hbp.withdrawal_limit]) · repaid {_money(plan.tranche)}/yr over "
            f"{plan.repayment_years} years from year {plan.grace_years} [hbp.repayment_years, "
            f"hbp.repayment_grace_years]{horizon} · the RRSP is rebuilt to {_money(leg.rebuilt_at_horizon)} "
            f"by year {n_years} (repayments PV {_money(leg.outlays_pv)}{deflated} against the rebuilt "
            f"RRSP's PV {_money(leg.rebuilt_pv)}) — net PV {_money(abs(leg.net_pv))} {side} {name} "
            f"(hbp_repayment_pv)")


def tax_to_dict(tax: TaxParams, terminal: Optional[RenterTerminal], n_years: int, dr: float,
                hbp_legs: Dict[str, HbpLeg]) -> Dict[str, Any]:
    """`assumptions.tax` in the --json document."""
    discount = (1 + dr) ** n_years
    rc = tax.renter_capital
    return {
        "marginal_rate": tax.marginal_rate,
        "marginal_rate_source": tax.marginal_rate_source,
        "marginal_rate_detail": tax.marginal_rate_detail,
        "province": tax.province,
        "income": tax.income,
        "taxable_return_treatment": tax.taxable_return_treatment,
        "inclusion_rate": tax.inclusion_rate,
        "inclusion_applied": tax.inclusion,
        "retirement_marginal_rate": tax.retirement_marginal_rate,
        "retirement_rate_source": tax.retirement_rate_source,
        "renter_capital": (
            {"tfsa": rc.tfsa, "rrsp": rc.rrsp, "fhsa": rc.fhsa, "taxable": rc.taxable,
             "fhsa_derived": rc.fhsa_derived, "total": rc.total, "refunds_added": tax.refunds}
            if rc is not None else None),
        "after_tax_factor": terminal.after_tax_factor if terminal is not None else None,
        "blended_rate": terminal.blended_rate if terminal is not None else None,
        "drag_at_horizon": terminal.drag if terminal is not None else None,
        "drag_pv": terminal.drag / discount if terminal is not None else None,
        "haircut_at_horizon": terminal.haircut if terminal is not None else None,
        "haircut_pv": terminal.haircut / discount if terminal is not None else None,
        "fhsa": (
            {"balance": tax.fhsa.balance, "years_until_purchase": tax.fhsa.years_until_purchase,
             "contributions": list(tax.fhsa.contributions), "refunds": tax.fhsa.refunds,
             "share_at_year0": tax.fhsa.share_at_year0, "lifetime_remaining": tax.fhsa.lifetime_remaining}
            if tax.fhsa is not None else None),
        "hbp": (
            {"withdrawal": tax.hbp.withdrawal, "limit": tax.hbp.limit, "tranche": tax.hbp.tranche,
             "repayment_years": tax.hbp.repayment_years, "first_repayment_year": tax.hbp.grace_years,
             "legs": {name: {"outlays_pv": leg.outlays_pv, "rebuilt_at_horizon": leg.rebuilt_at_horizon,
                             "rebuilt_pv": leg.rebuilt_pv, "hbp_repayment_pv": leg.net_pv}
                      for name, leg in hbp_legs.items()}}
            if tax.hbp is not None else None),
        "principal_residence_exempt_fraction": tax.principal_residence_exempt_fraction,
    }


def tfsa_room_warning(tax: Optional[TaxParams]) -> Optional[str]:
    """A TFSA share above the cumulative room since 2009 — a check, not a
    refusal: growth can outrun contributions."""
    if tax is None or tax.renter_capital is None:
        return None
    room = _anchor(_TFSA_ROOM)
    if tax.renter_capital.tfsa <= room:
        return None
    return (f"tax.renter_capital.tfsa={_money(tax.renter_capital.tfsa)} exceeds the cumulative TFSA "
            f"room since 2009 ({_money(room)}) [tfsa.cumulative_room_since_2009] — possible when "
            f"growth outran contributions; check the share")
