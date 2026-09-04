"""
The land-transfer tax, computed in the engine (round 8, 2026-09-04).

In Québec the droits sur les mutations immobilières — the "welcome tax" — are
the largest one-time cost of a purchase after the down payment. They are a
published bracket schedule, and in eight of eight real answers in the week to
2026-09-04 they were priced inside a 1.5%-of-price guess labelled "no source".
On a $650,000 Montréal house that guess reads $9,750 against a published
$8,349: a $1,400 error in the buy side's year-0 cash, invented rather than
looked up, in an answer whose own honesty contract says every number carries
its source class.

What this module owns:

* the anchored schedules, built FROM `anchors.py` (every bracket is a
  registered anchor, so `--print-anchors` shows the tables the engine applies);
* which schedules a jurisdiction levies — Montréal REPLACES the Québec
  provincial table, Toronto ADDS to Ontario's (toronto.ca: the MLTT applies
  "in addition to the Provincial Land Transfer Tax");
* the bracket arithmetic, and the first-time-buyer rebate, capped both at its
  published maximum and at the leg's own tax — a rebate never becomes a payment
  to the buyer.

The tax is CASH at closing. The loader adds it to `purchase_costs` before the
`cash_available` netting, so it comes out of the buyer's pile the way the
notary's bill does, and `purchase_costs` / `purchase_costs_rate` keep covering
what they always covered — notary, inspection, the rest.

Everything is derived in the loader from the raw YAML, so `--sweep` and
`--break-even` — which re-run the loader at every grid point — re-derive the
tax per point. A price scan across Montréal's $552,300 knee moves the marginal
rate from 1.5% to 2%; a tax frozen at the seed price would misplace the
threshold the whole answer turns on.

Eligibility is the USER's assertion: `first_time_buyer: true` says they meet
the conditions the source states (age, principal residence within nine months,
never having owned anywhere in the world, a spouse's history). The engine
applies the published maximum; it cannot check any of that.

Refusals are `LandTransferTaxError`, a `ValueError`; the config loader re-raises
it as `ConfigValidationError` and the scan paths record the point as refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .anchors import ANCHORS, TRANSFER_TAX_SCHEDULES

# Which schedules a jurisdiction levies, in the order they are charged.
# Montréal REPLACES the provincial table (montreal.ca publishes one complete
# schedule and its own worked example balances only that way); Toronto ADDS to
# Ontario's. Reading either backwards halves or doubles the largest one-time
# cost in the answer, so the structure is data here rather than a branch.
_JURISDICTIONS: Dict[Tuple[str, Optional[str]], Tuple[str, ...]] = {
    ("QC", None): ("land_transfer_tax.qc",),
    ("QC", "montreal"): ("land_transfer_tax.montreal",),
    ("ON", None): ("land_transfer_tax.ontario",),
    ("ON", "toronto"): ("land_transfer_tax.ontario", "land_transfer_tax.toronto"),
}

# family -> the registry key holding its first-time-buyer maximum. An entry
# whose anchor is `unsourced` holds no figure: the flag then applies nothing
# and the read-back says so.
_REBATE_ANCHORS: Dict[str, str] = {
    "land_transfer_tax.qc": "land_transfer_tax.qc.first_time_buyer_rebate",
    "land_transfer_tax.montreal": "land_transfer_tax.montreal.first_time_buyer_rebate",
    "land_transfer_tax.ontario": "land_transfer_tax.ontario.first_time_buyer_refund_max",
    "land_transfer_tax.toronto": "land_transfer_tax.toronto.first_time_buyer_rebate_max",
}

_PROVINCES_WITH_SCHEDULES = ("QC", "ON")


def option_province(province: Optional[str], municipality: Optional[str]) -> Optional[str]:
    """The province an owned option sits in, spelled as the registry spells it
    (upper case): the stated `province`, else the one its `municipality`
    belongs to — `municipality: montreal` alone places an option in Québec,
    `toronto` in Ontario. None when neither is stated. ONE resolver, shared by
    the loader's coherence checks and the read-back's other-costs line, so the
    two can never disagree about where an option is."""
    if isinstance(province, str) and province.strip():
        return province.strip().upper()
    if isinstance(municipality, str):
        wanted = municipality.strip().lower()
        for prov, city in _JURISDICTIONS:
            if city == wanted:
                return prov
    return None


class LandTransferTaxError(ValueError):
    """A config the transfer-tax schedules cannot price (no province, a
    municipality outside its province, a malformed explicit schedule)."""


@dataclass(frozen=True)
class Bracket:
    """One row: everything up to `up_to` (inclusive) pays `rate` at the margin.
    `up_to = None` is the uncapped top band."""

    up_to: Optional[float]
    rate: float


@dataclass(frozen=True)
class TransferTaxSchedule:
    """One levied schedule: its brackets and its first-time-buyer maximum."""

    name: str
    brackets: Tuple[Bracket, ...]
    # None when no rebate figure is anchored — distinct from 0.0, which would
    # claim the jurisdiction has none.
    first_time_buyer_rebate: Optional[float] = None

    def tax(self, base: float) -> float:
        """The duty on a base, summed over the brackets it reaches."""
        if base <= 0:
            return 0.0
        total = 0.0
        lower = 0.0
        for bracket in self.brackets:
            top = base if bracket.up_to is None else min(base, bracket.up_to)
            if top > lower:
                total += (top - lower) * bracket.rate
            if bracket.up_to is None or base <= bracket.up_to:
                break
            lower = bracket.up_to
        return total


@dataclass(frozen=True)
class TransferTaxLeg:
    """What one schedule charged, and what it refunded."""

    schedule: str
    gross: float
    rebate: float
    # False when the schedule has no anchored first-time-buyer figure at all:
    # `rebate == 0` then means "none anchored", not "none owed".
    rebate_anchored: bool
    rebate_max: Optional[float]


@dataclass(frozen=True)
class LandTransferTax:
    """What the loader derived for one owned option."""

    legs: Tuple[TransferTaxLeg, ...]
    first_time_buyer: bool
    # The option's `purchase_costs` BEFORE the tax was added, so the read-back
    # can decompose the figure it prints.
    stated_purchase_costs: float = 0.0

    @property
    def gross(self) -> float:
        return sum(leg.gross for leg in self.legs)

    @property
    def rebate(self) -> float:
        return sum(leg.rebate for leg in self.legs)

    @property
    def total(self) -> float:
        return self.gross - self.rebate

    @property
    def unrebated_maximum(self) -> float:
        """What a first-time buyer would have saved, for an option that did not
        claim it — the read-back names the figure rather than staying silent."""
        return sum(min(leg.rebate_max, leg.gross)
                   for leg in self.legs if leg.rebate_max is not None)


def anchored_schedule(family: str) -> TransferTaxSchedule:
    """One fetched schedule, built FROM the registry so the rates have exactly
    one home and `--print-anchors` shows the table the engine applies."""
    label, _url, _source, _unit, rows, _cite = TRANSFER_TAX_SCHEDULES[family]
    return TransferTaxSchedule(
        name=label,
        brackets=tuple(Bracket(up_to=edge, rate=ANCHORS[f"{family}.{key}"].value)
                       for key, edge, _rate, _quoted in rows),
        first_time_buyer_rebate=ANCHORS[_REBATE_ANCHORS[family]].value,
    )


def anchored_schedules(province: Optional[str],
                       municipality: Optional[str] = None,
                       name: str = "land_transfer_tax") -> Tuple[TransferTaxSchedule, ...]:
    """Every schedule levied on a purchase in this jurisdiction, in order."""
    return tuple(anchored_schedule(family)
                 for family in _families(province, municipality, name))


def anchor_families(province: Optional[str],
                    municipality: Optional[str] = None) -> Tuple[str, ...]:
    """The registry prefixes an `auto` tax was derived from — what the source
    echo cites when it calls the derived tax anchor-sourced."""
    try:
        return _families(province, municipality, "land_transfer_tax")
    except LandTransferTaxError:
        return ()


def _families(province: Optional[str], municipality: Optional[str],
              name: str) -> Tuple[str, ...]:
    if province is None:
        raise LandTransferTaxError(
            f"{name}: land_transfer_tax: auto needs a province — the transfer tax is "
            f"the largest one-time cost after the down payment and its schedule is "
            f"provincial. Set province: QC | ON on the option or at the top level "
            f"(add municipality: montreal | toronto for a city that levies its own), "
            f"or state your own {{brackets, first_time_buyer_rebate}} schedule")
    key = (province, municipality)
    if key in _JURISDICTIONS:
        return _JURISDICTIONS[key]
    if municipality is not None:
        allowed = sorted(m for (p, m) in _JURISDICTIONS if p == province and m)
        if province in _PROVINCES_WITH_SCHEDULES:
            raise LandTransferTaxError(
                f"{name}: municipality {municipality!r} does not levy a transfer tax in "
                f"province {province} — the engine has anchored city schedules for "
                f"{', '.join(allowed) or 'none in this province'}. Drop municipality to "
                f"charge the provincial schedule alone, or state an explicit schedule")
    raise LandTransferTaxError(
        f"{name}: land_transfer_tax: auto has no anchored schedule for province "
        f"{province!r} — only {', '.join(_PROVINCES_WITH_SCHEDULES)} were fetched. "
        f"State an explicit {{brackets, first_time_buyer_rebate}} schedule rather than "
        f"be charged $0 of a tax that is really owed")


def _parse_explicit(setting: Dict[str, Any], name: str) -> Tuple[TransferTaxSchedule, ...]:
    """A schedule the user quoted: their own municipality, or a province the
    engine has no anchor for. Nothing here is inferred."""
    raw = setting.get("brackets")
    if not isinstance(raw, list) or not raw:
        raise LandTransferTaxError(
            f"{name}.land_transfer_tax: an explicit schedule needs a non-empty "
            f"brackets list of {{up_to, rate}} (dollars and a decimal rate: "
            f"{{up_to: 62900, rate: 0.005}}); omit up_to on the last bracket for the "
            f"uncapped top band")
    brackets: List[Bracket] = []
    for entry in raw:
        if not isinstance(entry, dict) or "rate" not in entry:
            raise LandTransferTaxError(
                f"{name}.land_transfer_tax: each bracket must be {{up_to, rate}} "
                f"(up_to omitted on the top band), got {entry!r}")
        up_to = entry.get("up_to")
        brackets.append(Bracket(up_to=None if up_to is None else float(up_to),
                                rate=float(entry["rate"])))
    if any(b.up_to is None for b in brackets[:-1]):
        raise LandTransferTaxError(
            f"{name}.land_transfer_tax: only the LAST bracket may omit up_to — a "
            f"bracket with no ceiling ends the schedule")
    edges = [b.up_to for b in brackets if b.up_to is not None]
    if edges != sorted(edges) or len(set(edges)) != len(edges):
        raise LandTransferTaxError(
            f"{name}.land_transfer_tax: brackets must be in increasing up_to order "
            f"with no repeats, got {edges}")
    rebate = setting.get("first_time_buyer_rebate")
    return (TransferTaxSchedule(
        name="schedule stated in the config",
        brackets=tuple(brackets),
        first_time_buyer_rebate=None if rebate is None else float(rebate),
    ),)


def resolve(
    data: Dict[str, Any],
    name: str,
    *,
    top_province: Optional[str],
    initial_value: float,
    purchase_costs: float = 0.0,
) -> Tuple[float, Optional[LandTransferTax]]:
    """
    Derive the transfer tax for one owned option.

    Returns `(tax_to_add_to_purchase_costs, record)`; `record` is None when no
    schedule is active. The caller adds the dollars to `purchase_costs` BEFORE
    the `cash_available` netting, so the tax leaves the buyer's pile.
    """
    setting = data.get("land_transfer_tax", "none")
    if setting is None or (isinstance(setting, str) and setting.strip().lower() == "none"):
        return 0.0, None

    first_time_buyer = _parse_flag(data.get("first_time_buyer", False),
                                   f"{name}.first_time_buyer")
    if isinstance(setting, str) and setting.strip().lower() == "auto":
        province = data.get("province", top_province)
        if isinstance(province, str):
            province = province.strip().upper()
        municipality = data.get("municipality")
        if isinstance(municipality, str):
            municipality = municipality.strip().lower()
        elif municipality is not None:
            raise LandTransferTaxError(
                f"{name}.municipality must be a string (montreal | toronto), "
                f"got {municipality!r}")
        schedules = anchored_schedules(province, municipality, name)
    elif isinstance(setting, dict):
        schedules = _parse_explicit(setting, name)
    else:
        raise LandTransferTaxError(
            f"{name}.land_transfer_tax must be 'auto' (the anchored schedule for the "
            f"option's province and municipality), 'none' (default), or an explicit "
            f"{{brackets, first_time_buyer_rebate}} schedule — got {setting!r}")

    base = max(0.0, float(initial_value))
    legs = []
    for schedule in schedules:
        gross = schedule.tax(base)
        maximum = schedule.first_time_buyer_rebate
        # Capped BOTH at the published maximum and at this leg's own tax: a
        # refund of a duty cannot exceed the duty.
        rebate = min(maximum, gross) if (first_time_buyer and maximum is not None) else 0.0
        legs.append(TransferTaxLeg(
            schedule=schedule.name,
            gross=gross,
            rebate=rebate,
            rebate_anchored=maximum is not None,
            rebate_max=maximum,
        ))
    record = LandTransferTax(
        legs=tuple(legs),
        first_time_buyer=first_time_buyer,
        stated_purchase_costs=float(purchase_costs),
    )
    return record.total, record


def _parse_flag(value: Any, where: str) -> bool:
    if isinstance(value, bool):
        return value
    raise LandTransferTaxError(f"{where} must be true or false, got {value!r}")


def purchase_costs_clause(record: LandTransferTax, purchase_costs: float,
                          premium_tax: float = 0.0) -> str:
    """The assumption-echo clause: the tax, the schedules that charged it, the
    rebate applied — and the decomposition of the `purchase_costs` figure the
    financing line quotes, so the two lines reconcile by eye.

    This is its own line rather than a clause on `<option> financing:` because
    the financing line is skipped for an all-cash purchase, and an all-cash
    buyer pays the welcome tax like everyone else.
    """
    legs = record.legs
    if len(legs) == 1:
        charged = f"{legs[0].schedule}"
    else:
        charged = " + ".join(f"{leg.schedule} ${leg.gross:,.0f}" for leg in legs)
    head = f"land transfer tax ${record.total:,.0f}"
    if record.rebate:
        applied = ", ".join(
            f"{leg.schedule} −${leg.rebate:,.0f}" for leg in legs if leg.rebate)
        head += (f" = ${record.gross:,.0f} ({charged}) − first-time-buyer "
                 f"rebate ${record.rebate:,.0f} ({applied})")
    else:
        head += f" ({charged})"
    # What the rebate did NOT do is as load-bearing as what it did: a buyer
    # who never learns a $4,475 rebate exists cannot claim it, and a buyer
    # told nothing about Québec might assume one was quietly applied.
    unanchored = [leg.schedule for leg in legs if not leg.rebate_anchored]
    # Naming a single schedule twice in one sentence is noise; with two legs
    # the reader needs to know WHICH one has no rebate.
    where = "this schedule" if len(legs) == 1 else ", ".join(unanchored)
    if record.first_time_buyer and not record.rebate:
        head += ("; first_time_buyer: true applied nothing — no first-time-buyer "
                 f"rebate is anchored for {where}" if unanchored
                 else "; first_time_buyer: true applied nothing")
    elif not record.first_time_buyer:
        if record.unrebated_maximum:
            head += (f"; first_time_buyer is false — up to "
                     f"${record.unrebated_maximum:,.0f} of rebate not applied")
        if unanchored:
            head += f"; no first-time-buyer rebate is anchored for {where}"
    stated = f"${record.stated_purchase_costs:,.0f} stated"
    parts = f"{stated} + transfer tax ${record.total:,.0f}"
    if premium_tax:
        parts += f" + premium tax ${premium_tax:,.0f}"
    return (f"{head} · purchase_costs ${purchase_costs:,.0f} in cash at closing "
            f"({parts})")
