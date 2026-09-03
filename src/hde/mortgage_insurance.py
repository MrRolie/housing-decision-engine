"""
The mortgage loan insurance premium, computed in the engine (round 7, 2026-09-03).

A Canadian purchase with less than 20% down must be insured, and the premium is
a STEP function of loan-to-value: 2.80% at 85% LTV, 3.10% a dollar past it. Five
of five insured serves in round 7 computed that premium by hand from recalled
tiers, applied the wrong provincial tax rate in two of them, and held one premium
fixed while a price scan walked the loan-to-value across a band edge. None of
that is arithmetic a person should do beside an engine that already knows the
price, the down payment and the amortization.

What this module owns:

* the anchored schedule, built FROM `anchors.py` (the bands are registered
  anchors, so `--print-anchors` shows the table the engine applies);
* tier selection on the loan-to-value BEFORE the premium is financed;
* the premium, which is ADDED TO THE LOAN (CMHC: the premium "may be added onto
  the mortgage"), and the provincial tax on it, which is NOT — CMHC: "The sales
  tax can't be added to the loan amount" — so the tax is paid in cash at closing.

Everything is derived in the loader from the raw YAML, so `--sweep` and
`--break-even` — which re-run the loader at every grid point — re-derive the
tier per point instead of freezing the base config's premium.

Refusals are `MortgageInsuranceError`, a `ValueError`: the scan paths catch it,
record the point under "refused" and shrink the search, rather than crashing.
The config loader re-raises it as `ConfigValidationError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .anchors import ANCHORS, PREMIUM_TAX_UNANCHORED, _CMHC_PREMIUM_BANDS

# A purchase at or under 80% loan-to-value is conventional: no insurance is
# required and none is priced, whatever the schedule's sub-80% rows say (those
# belong to CMHC's other products). This is the same 20% line the assumption
# echo and the coherence warning already speak in.
INSURED_LTV_THRESHOLD = 0.80

# Loan-to-value comparisons are exact-edge decisions on a step function, so a
# band edge reached by division needs a floating-point cushion: 85.00000000001%
# is 85%, not the next tier up.
_LTV_TOL = 1e-9

# province -> the registry key holding its tax on insurance premiums.
_PREMIUM_TAX_ANCHORS = {
    "QC": "mortgage_insurance.premium_tax_rate.qc",
    "ON": "mortgage_insurance.premium_tax_rate.on",
    "OTHER": None,          # no provincial tax on the premium
}


class MortgageInsuranceError(ValueError):
    """A config the premium schedule cannot price (over the maximum
    loan-to-value, a double-counted premium, an unanchored province)."""


@dataclass(frozen=True)
class PremiumBand:
    """One row of a premium schedule: everything up to `ltv_max` pays `rate`."""

    ltv_max: float
    rate: float
    label: str = ""


@dataclass(frozen=True)
class PremiumSchedule:
    """A premium schedule: the bands, the provincial tax on the premium, and the
    maximum insurable loan-to-value (the top band's edge)."""

    bands: Tuple[PremiumBand, ...]
    premium_tax_rate: float
    surcharge_rate: float = 0.0
    surcharge_above_years: int = 25
    province: Optional[str] = None
    cite: str = ""

    @property
    def max_ltv(self) -> float:
        return self.bands[-1].ltv_max

    def band_for(self, ltv: float) -> Optional[PremiumBand]:
        """The band a loan-to-value falls in — None at or under the 20%-down
        line, where the mortgage is conventional and uninsured."""
        if ltv <= INSURED_LTV_THRESHOLD + _LTV_TOL:
            return None
        for band in self.bands:
            if ltv <= band.ltv_max + _LTV_TOL:
                return band
        return None       # above the maximum; the caller refuses with the figure


@dataclass(frozen=True)
class MortgageInsurance:
    """What the loader derived for one owned option.

    `ltv` is the tier basis — the loan BEFORE the premium is financed. `loan`
    and `ltv_after` are the result: an insured loan routinely exceeds 95% of
    price once the premium rides on it, which is by design and never a refusal.
    """

    ltv: float
    required: bool
    band_label: str
    band_rate: float
    surcharge_rate: float
    rate: float
    premium: float
    premium_tax_rate: float
    premium_tax: float
    loan: float
    ltv_after: float
    max_ltv: float
    province: Optional[str]
    cite: str


def _rate_anchor(key_suffix: str) -> float:
    return ANCHORS[f"mortgage_insurance.premium_rate.{key_suffix}"].value


def anchored_schedule(province: Optional[str]) -> PremiumSchedule:
    """The CMHC schedule as fetched 2026-09-03, with the province's tax on the
    premium. Built from the registry so the rates have exactly one home."""
    bands = tuple(
        PremiumBand(ltv_max=edge, rate=_rate_anchor(key), label=label)
        for key, edge, _rate, label in _CMHC_PREMIUM_BANDS
    )
    tax_key = _PREMIUM_TAX_ANCHORS[province] if province else None
    return PremiumSchedule(
        bands=bands,
        premium_tax_rate=ANCHORS[tax_key].value if tax_key else 0.0,
        surcharge_rate=ANCHORS["mortgage_insurance.amortization_surcharge"].value,
        surcharge_above_years=25,
        province=province,
        cite=ANCHORS["mortgage_insurance.max_ltv"].short_cite,
    )


def _resolve_province(data: Dict[str, Any], name: str, top_province: Optional[str]) -> str:
    """The province whose tax applies. Stated on the option, else at the top
    level: an Ottawa-vs-Gatineau comparison prices two provinces in one config,
    so the option wins, and a single-province config states it once."""
    raw = data.get("province", top_province)
    if raw is None:
        raise MortgageInsuranceError(
            f"{name}: mortgage_insurance: auto needs a province — the provincial tax on "
            f"the premium is paid in cash at closing and assuming 0% would understate "
            f"the buy side. Set province: QC | ON | other on the option or at the top "
            f"level, or state your own schedule with a premium_tax_rate")
    if not isinstance(raw, str):
        raise MortgageInsuranceError(f"{name}: province must be a string, got {raw!r}")
    province = raw.strip().upper()
    if province in PREMIUM_TAX_UNANCHORED:
        raise MortgageInsuranceError(
            f"{name}: province {raw!r} taxes the mortgage-insurance premium (CMHC names "
            f"Ontario, Québec and Saskatchewan) but the engine has no anchor for its "
            f"rate — state the schedule explicitly with its premium_tax_rate rather than "
            f"be charged 0%")
    if province not in _PREMIUM_TAX_ANCHORS:
        raise MortgageInsuranceError(
            f"{name}: province {raw!r} is not one of QC, ON, other — 'other' means no "
            f"provincial tax on the mortgage-insurance premium")
    return province


def _parse_explicit(setting: Dict[str, Any], name: str) -> PremiumSchedule:
    """A schedule the user quoted: their lender's sheet, or a jurisdiction the
    engine has no anchor for. Nothing here is inferred."""
    raw_bands = setting.get("bands")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise MortgageInsuranceError(
            f"{name}.mortgage_insurance: an explicit schedule needs a non-empty bands "
            f"list of {{ltv_max, rate}} (decimals: ltv_max 0.95, rate 0.04)")
    if "premium_tax_rate" not in setting:
        raise MortgageInsuranceError(
            f"{name}.mortgage_insurance: an explicit schedule needs premium_tax_rate "
            f"(0 where the province does not tax the premium) — an explicit schedule "
            f"infers nothing")
    bands = []
    for entry in raw_bands:
        if not isinstance(entry, dict) or "ltv_max" not in entry or "rate" not in entry:
            raise MortgageInsuranceError(
                f"{name}.mortgage_insurance: each band must be {{ltv_max, rate}}, "
                f"got {entry!r}")
        bands.append(PremiumBand(ltv_max=float(entry["ltv_max"]),
                                 rate=float(entry["rate"]),
                                 label=f"up to {float(entry['ltv_max']):.2%}"))
    bands.sort(key=lambda band: band.ltv_max)
    return PremiumSchedule(
        bands=tuple(bands),
        premium_tax_rate=float(setting["premium_tax_rate"]),
        surcharge_rate=float(setting.get("amortization_surcharge", 0.0)),
        surcharge_above_years=int(setting.get("surcharge_above_years", 25)),
        province=None,
        cite="schedule stated in the config",
    )


def _rate_for(schedule: PremiumSchedule, ltv: float, term_years: Optional[int],
              name: str) -> Tuple[Optional[PremiumBand], float, float]:
    """(band, band_rate, surcharge) for a loan-to-value, refusing over the max."""
    if ltv > schedule.max_ltv + _LTV_TOL:
        raise MortgageInsuranceError(
            f"{name}: loan-to-value {ltv:.2%} exceeds the maximum insurable "
            f"{schedule.max_ltv:.2%} — no insurer writes this loan. Raise the down "
            f"payment or lower the price")
    band = schedule.band_for(ltv)
    if band is None:
        return None, 0.0, 0.0
    surcharge = (schedule.surcharge_rate
                 if term_years is not None and term_years > schedule.surcharge_above_years
                 else 0.0)
    return band, band.rate, surcharge


def _solve_with_cash(schedule: PremiumSchedule, price: float, base_loan: float,
                     term_years: Optional[int], name: str) -> float:
    """The loan when the premium tax is paid OUT OF the cash pile.

    Paying the tax shrinks the down payment, which raises the loan, which can
    raise the tier, which raises the tax: `loan = base / (1 − t·r(loan/price))`.
    r is a non-decreasing step function of the loan, so iterating from the
    zero-tax loan is non-decreasing and reaches the least self-consistent tier
    in at most one pass per band.
    """
    loan = base_loan
    for _ in range(len(schedule.bands) + 2):
        _band, band_rate, surcharge = _rate_for(schedule, loan / price, term_years, name)
        rate = band_rate + surcharge
        divisor = 1.0 - schedule.premium_tax_rate * rate
        if divisor <= 0:
            raise MortgageInsuranceError(
                f"{name}: the premium tax cannot be netted out of cash_available "
                f"(tax rate {schedule.premium_tax_rate:.2%} × premium rate {rate:.2%})")
        candidate = base_loan / divisor
        _b2, band_rate2, surcharge2 = _rate_for(schedule, candidate / price, term_years, name)
        loan = candidate
        if band_rate2 + surcharge2 == rate:
            break
    return loan


def resolve(
    data: Dict[str, Any],
    name: str,
    *,
    top_province: Optional[str],
    initial_value: float,
    down_payment: Optional[float],
    cash_available: Optional[float],
    purchase_costs: float,
    financed_purchase_costs: float,
    all_cash: bool,
    mortgage_term_years: Optional[int],
) -> Tuple[Optional[float], float, float, Optional[MortgageInsurance]]:
    """
    Derive the insured mortgage for one owned option.

    Returns `(down_payment, purchase_costs, financed_purchase_costs, record)`:
    the premium joins `financed_purchase_costs` so the rest of the engine
    finances it with no further change, and the tax is netted out of
    `cash_available` when the buyer stated a pile, otherwise added to
    `purchase_costs`. `record` is None when no schedule is active.
    """
    setting = data.get("mortgage_insurance", "none")
    if setting is None or (isinstance(setting, str) and setting.strip().lower() == "none"):
        return down_payment, purchase_costs, financed_purchase_costs, None

    if all_cash:
        raise MortgageInsuranceError(
            f"{name}: mortgage_insurance is set with all_cash: true — an unmortgaged "
            f"purchase carries no insurance premium; drop one of the two")
    if financed_purchase_costs:
        raise MortgageInsuranceError(
            f"{name}: financed_purchase_costs ${financed_purchase_costs:,.0f} beside "
            f"mortgage_insurance would double count the premium — the engine computes "
            f"it and rolls it into the loan. Drop financed_purchase_costs, or set "
            f"mortgage_insurance: none and keep computing it by hand")

    if isinstance(setting, str) and setting.strip().lower() == "auto":
        schedule = anchored_schedule(_resolve_province(data, name, top_province))
    elif isinstance(setting, dict):
        schedule = _parse_explicit(setting, name)
    else:
        raise MortgageInsuranceError(
            f"{name}.mortgage_insurance must be 'auto' (the anchored CMHC schedule), "
            f"'none' (default), or an explicit {{bands, premium_tax_rate}} schedule — "
            f"got {setting!r}")

    # Incomplete or degenerate capital structures are somebody else's refusal:
    # the mortgage-block validator says it better than a premium calculation can.
    if initial_value <= 0 or (down_payment is None and cash_available is None):
        return down_payment, purchase_costs, financed_purchase_costs, None
    if cash_available is not None and cash_available - purchase_costs < 0:
        return down_payment, purchase_costs, financed_purchase_costs, None

    if cash_available is None:
        loan = initial_value - float(down_payment)
    else:
        loan = _solve_with_cash(
            schedule, initial_value, initial_value - cash_available + purchase_costs,
            mortgage_term_years, name)

    ltv = loan / initial_value
    band, band_rate, surcharge = _rate_for(schedule, ltv, mortgage_term_years, name)
    rate = band_rate + surcharge
    premium = rate * loan
    premium_tax = schedule.premium_tax_rate * premium

    if cash_available is None:
        purchase_costs = purchase_costs + premium_tax
    else:
        down_payment = cash_available - purchase_costs - premium_tax
    financed_purchase_costs = premium

    record = MortgageInsurance(
        ltv=ltv,
        required=band is not None,
        band_label=band.label if band is not None else "",
        band_rate=band_rate,
        surcharge_rate=surcharge,
        rate=rate,
        premium=premium,
        premium_tax_rate=schedule.premium_tax_rate if band is not None else 0.0,
        premium_tax=premium_tax,
        loan=loan + premium,
        ltv_after=(loan + premium) / initial_value,
        max_ltv=schedule.max_ltv,
        province=schedule.province,
        cite=schedule.cite,
    )
    return down_payment, purchase_costs, financed_purchase_costs, record


def financing_clause(record: MortgageInsurance) -> str:
    """The assumption-echo clause: the tier, the premium, the tax and the result.

    Reads back exactly what the engine did, so the figure the user checks is the
    figure the engine used — the hand-computation this feature replaces.
    """
    if not record.required:
        return (f"mortgage_insurance: auto → none required "
                f"({record.ltv:.2%} ≤ {INSURED_LTV_THRESHOLD:.0%})")
    tier = f"{record.band_rate:.2%} tier"
    if record.surcharge_rate:
        tier += (f" +{record.surcharge_rate:.2%} (amortization over "
                 f"25 years) = {record.rate:.2%}")
    tax = "no provincial tax on the premium"
    if record.premium_tax_rate:
        where = f" ({record.province})" if record.province else ""
        tax = (f"premium tax {record.premium_tax_rate * 100:g}%{where} = "
               f"${record.premium_tax:,.0f} cash")
    return (f"insured: {record.ltv:.2%} LTV → {tier} = ${record.premium:,.0f} financed; "
            f"{tax} → loan ${record.loan:,.0f} = {record.ltv_after:.2%} LTV")
