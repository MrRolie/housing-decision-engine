"""Combined marginal income-tax rates, read from the registry (2026-09-05).

The 2026 bracket schedules, the Québec abatement and the Ontario surtax live in
`anchors` as reference entries; this module reads them back so a rate has one
home and `--print-anchors` shows exactly the table these functions apply.
Nothing here runs by default — the engine charges no income tax until a config
opts into a tax block. This is the helper that block calls, and the figure an
assistant can cite for a user's marginal rate.

Definitions the functions commit to:

* the STATUTORY marginal rate: the bracket rate at the taxable income, upper
  edges inclusive as the tables print them ("$0 to $58,523", then
  "$58,523.01 to …"). Credits that phase out with income — the federal basic
  personal amount between $181,440 and $258,482, an implicit ~0.3-point
  marginal — are not in it, as they are not in the CRA table;
* Québec: federal tax is abated 16.5% (the refundable Québec abatement), so
  the federal component is the bracket rate × (1 − 0.165);
* Ontario: the surtax is 20% of basic Ontario tax over $5,818 plus 36% over
  $7,446, where basic Ontario tax is Ontario tax on taxable income LESS
  non-refundable credits. The registry knows one credit — 5.05% × the basic
  personal amount — so that is all `ontario_basic_tax` nets; every other
  credit moves the crossover income higher than this says (about $94,900 and
  $111,800 here). Inside a tier the marginal Ontario rate is the bracket rate
  × (1 + the stacked tier fractions).
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .anchors import ANCHORS

# province code -> registry family. Only what the registry holds: anything else
# is refused, never served a federal-only figure dressed as a combined one.
_PROVINCE_FAMILIES: Dict[str, str] = {"qc": "tax.qc", "on": "tax.on"}
_FEDERAL = "tax.federal"

Schedule = Tuple[Tuple[Optional[float], float], ...]


@dataclass(frozen=True)
class MarginalRateBreakdown:
    """The components of one combined marginal rate.

    `federal_rate` and `provincial_rate` are the statutory bracket rates;
    `quebec_abatement` is 0.165 in Québec and 0.0 elsewhere; `surtax_rate` is
    the stacked Ontario tier fraction at this income (0.0, 0.20 or 0.56) and
    0.0 elsewhere; the `_net_` rates carry those applied; `combined_rate` is
    their sum — what `marginal_rate` returns.
    """

    taxable_income: float
    province: str
    federal_rate: float
    quebec_abatement: float
    federal_net_rate: float
    provincial_rate: float
    surtax_rate: float
    provincial_net_rate: float
    combined_rate: float


def _family(jurisdiction: str) -> str:
    code = (jurisdiction or "").strip().lower()
    if code == "federal":
        return _FEDERAL
    if code not in _PROVINCE_FAMILIES:
        raise ValueError(
            f"no income-tax schedule for province {jurisdiction!r}: the registry "
            f"holds {sorted(_PROVINCE_FAMILIES)} (and 'federal')"
        )
    return _PROVINCE_FAMILIES[code]


def bracket_schedule(jurisdiction: str) -> Schedule:
    """The registered brackets for 'federal', 'qc' or 'on' as
    `((ceiling, rate), …)`, ceilings inclusive and the top bracket's `None`,
    read from the `tax.<jur>.bracket_<k>_ceiling` / `_rate` anchors."""
    family = _family(jurisdiction)
    rows = []
    k = 1
    while f"{family}.bracket_{k}_rate" in ANCHORS:
        ceiling = ANCHORS.get(f"{family}.bracket_{k}_ceiling")
        rows.append((None if ceiling is None else ceiling.value,
                     ANCHORS[f"{family}.bracket_{k}_rate"].value))
        k += 1
    if not rows or rows[-1][0] is not None or any(c is None for c, _ in rows[:-1]):
        raise ValueError(f"{family}: the registered brackets do not form a schedule")
    return tuple(rows)


def bracket_rate(jurisdiction: str, taxable_income: float) -> float:
    """The statutory bracket rate at `taxable_income` (edges inclusive)."""
    _check_income(taxable_income)
    for ceiling, rate in bracket_schedule(jurisdiction):
        if ceiling is None or taxable_income <= ceiling:
            return rate
    raise AssertionError("unreachable: the top bracket has no ceiling")


def progressive_tax(jurisdiction: str, taxable_income: float) -> float:
    """Tax on taxable income before any credit: each tranche at its own rate."""
    _check_income(taxable_income)
    tax = 0.0
    floor = 0.0
    for ceiling, rate in bracket_schedule(jurisdiction):
        top = taxable_income if ceiling is None else min(taxable_income, ceiling)
        if top > floor:
            tax += (top - floor) * rate
        if ceiling is None or taxable_income <= ceiling:
            break
        floor = ceiling
    return tax


def ontario_surtax_tiers() -> Tuple[Tuple[float, float], ...]:
    """`((threshold of basic Ontario tax, fraction of the excess), …)` from the
    `tax.on.surtax_<k>_threshold` / `_rate` anchors."""
    tiers = []
    k = 1
    while f"tax.on.surtax_{k}_threshold" in ANCHORS:
        tiers.append((ANCHORS[f"tax.on.surtax_{k}_threshold"].value,
                      ANCHORS[f"tax.on.surtax_{k}_rate"].value))
        k += 1
    return tuple(tiers)


def ontario_basic_tax(taxable_income: float) -> float:
    """Basic Ontario tax payable as the surtax base: Ontario tax on taxable
    income less the ONE credit the registry holds (the lowest rate × the basic
    personal amount), never below zero. Other credits are not netted — see the
    module docstring."""
    credit = bracket_schedule("on")[0][1] * ANCHORS["tax.on.basic_personal_amount"].value
    return max(0.0, progressive_tax("on", taxable_income) - credit)


def ontario_surtax_fraction(taxable_income: float) -> float:
    """The stacked surtax fraction at `taxable_income`: 0.0 below the first
    tier, 0.20 inside it, 0.56 above the second (the tiers stack)."""
    basic = ontario_basic_tax(taxable_income)
    return sum(fraction for threshold, fraction in ontario_surtax_tiers()
               if basic > threshold)


def marginal_rate_breakdown(taxable_income: float, province: str) -> MarginalRateBreakdown:
    """The combined federal + provincial marginal rate at `taxable_income`,
    with the Québec abatement or the Ontario surtax applied, by component."""
    code = (province or "").strip().lower()
    _family(code)  # refuses an unknown province
    federal = bracket_rate("federal", taxable_income)
    provincial = bracket_rate(code, taxable_income)
    abatement = ANCHORS["tax.federal.quebec_abatement"].value if code == "qc" else 0.0
    surtax = ontario_surtax_fraction(taxable_income) if code == "on" else 0.0
    federal_net = federal * (1.0 - abatement)
    provincial_net = provincial * (1.0 + surtax)
    return MarginalRateBreakdown(
        taxable_income=float(taxable_income),
        province=code,
        federal_rate=federal,
        quebec_abatement=abatement,
        federal_net_rate=federal_net,
        provincial_rate=provincial,
        surtax_rate=surtax,
        provincial_net_rate=provincial_net,
        combined_rate=federal_net + provincial_net,
    )


def marginal_rate(taxable_income: float, province: str) -> float:
    """The combined federal + provincial marginal rate at `taxable_income` in
    `province` ('qc' or 'on', any case): federal bracket rate × (1 − the Québec
    abatement) + provincial bracket rate × (1 + the Ontario surtax fraction)."""
    return marginal_rate_breakdown(taxable_income, province).combined_rate


def _check_income(taxable_income: float) -> None:
    if taxable_income is None or taxable_income < 0:
        raise ValueError(f"taxable income must be zero or more, got {taxable_income!r}")
