"""Rates as quoted — the one convention for every rate a user types (2026-09-05).

A person quotes rates the way they see them: "rent goes up 3%", "prices grow
4%", "my portfolio makes 6%". The engine's own defaults are REAL figures (the
anchors registry), and until this ruling a typed rate was read as real too — so
served answers converted sticker numbers to real by hand, and in nominal mode
the engine composed inflation back on top: one figure, inflated twice.

The rule now: a typed growth, escalation, return or discount rate is AS QUOTED
and the engine converts it ONCE, at load. The spec keeps real figures inside
(the anchored defaults stay real and the engines compose inflation on top in
nominal mode exactly as before), so:

    real mode     r_real = (1 + r_quoted) / (1 + inflation_rate) − 1     (deflated)
    nominal mode  the engine composes that real figure back: used as typed

A config that states real figures says so with a top-level ``rates: real``.
``inflation_rate`` is therefore the deflator in real mode too; omitted, it is
the FP Canada planning figure (echoed under `defaults applied`). A mortgage
rate is a quoted contract rate in both modes and never converted.

Import-light on purpose (anchors only): `sources` and `models` both read this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .anchors import ANCHORS

RATE_CONVENTIONS: Tuple[str, ...] = ("as_quoted", "real")
DEFAULT_CONVENTION = "as_quoted"

# Dotted keys, as the YAML states them, whose typed figure is converted. Every
# one of these is a rate the engines compose with inflation in nominal mode
# (`_effective_growth_rate`) or, for the discount rate, the rate the run
# discounts at. `mortgage_rate` is deliberately absent: a contract rate.
CONVERTIBLE_ORDER: Tuple[str, ...] = (
    "discount_rate",
    "condo.fee_escalation_rate", "condo.value_growth_rate", "condo.reserve_growth_rate",
    "house.value_growth_rate",
    "rent.rent_escalation_rate", "rent.investment_return_rate",
    "income.income_growth_rate",
)
CONVERTIBLE_KEYS = frozenset(CONVERTIBLE_ORDER)
_SECTIONS = ("discount_rate", "condo", "house", "rent", "income")
_LINE_LIST = ".other_recurring_costs."
_LINE_LEAF = ".escalation_rate"


def _rank(key: str) -> Tuple[int, int, int]:
    """Read-back order: by section, an option's own rates before its cost
    lines, the named keys in `CONVERTIBLE_ORDER`; lines keep config order."""
    section = key.split(".", 1)[0]
    named = key in CONVERTIBLE_KEYS
    return (_SECTIONS.index(section) if section in _SECTIONS else len(_SECTIONS),
            0 if named else 1,
            CONVERTIBLE_ORDER.index(key) if named else 0)


def is_convertible(dotted: str) -> bool:
    """True for a typed key the convention converts — a named key above or an
    `other_recurring_costs` line's `escalation_rate` (named-line form)."""
    if dotted in CONVERTIBLE_KEYS:
        return True
    return _LINE_LIST in dotted and dotted.endswith(_LINE_LEAF)


def deflate(rate: float, inflation_rate: float) -> float:
    """A quoted (nominal) rate in real terms: (1 + r)/(1 + π) − 1."""
    return (1 + rate) / (1 + inflation_rate) - 1


def compose(rate: float, inflation_rate: float) -> float:
    """A real rate in nominal terms: (1 + r)(1 + π) − 1 — the engines' own composition."""
    return (1 + rate) * (1 + inflation_rate) - 1


def inflation_anchor_name(mode: str, rates: str) -> str:
    """Which registry entry supplies an OMITTED `inflation_rate`: the planning
    figure when it is the deflator of as-quoted rates in real mode, else the
    real-mode inert zero (nominal mode keeps that zero and its warning)."""
    if mode == "real" and rates == "as_quoted":
        return "economic.inflation_rate.nominal_planning"
    return "economic.inflation_rate"


def default_inflation_rate(mode: str, rates: str) -> float:
    return ANCHORS[inflation_anchor_name(mode, rates)].value


class RateConventionError(ValueError):
    """A `rates:` value outside as_quoted | real."""


def convention_of(data: Dict[str, Any]) -> str:
    rates = data.get("rates", DEFAULT_CONVENTION)
    if rates not in RATE_CONVENTIONS:
        raise RateConventionError(
            f"rates: {rates!r} — must be 'as_quoted' (the default: every typed rate is "
            f"the figure as quoted and the engine converts it once at load) or 'real' "
            f"(every typed rate is already a real figure)")
    return rates


def resolve_convention(data: Dict[str, Any]) -> Tuple[str, str, float]:
    """(rates, mode, inflation_rate) as the loader will read them from a raw
    YAML mapping — the same three facts `sources:` needs to compare a typed
    figure with an anchor in the anchor's convention."""
    rates = convention_of(data)
    econ = data.get("economic")
    econ = econ if isinstance(econ, dict) else {}
    mode = econ.get("mode", "real")
    if "inflation_rate" in econ:
        inflation_rate = float(econ["inflation_rate"])
    else:
        inflation_rate = default_inflation_rate(mode, rates)
    return rates, mode, inflation_rate


@dataclass(frozen=True)
class ConvertedRate:
    """One typed rate the loader converted: the figure as quoted and the figure
    the run uses, in the run's terms — the deflated real rate in real mode, the
    quoted rate itself in nominal mode (where the engine composes the stored
    real figure back to it)."""
    key: str
    quoted: float
    effective: float


class RateConverter:
    """Reads typed rates for one load under one convention and records each
    conversion for the read-back."""

    def __init__(self, rates: str, mode: str, inflation_rate: float) -> None:
        self.rates = rates
        self.mode = mode
        self.inflation_rate = inflation_rate
        self._converted: List[ConvertedRate] = []

    @property
    def converted(self) -> List[ConvertedRate]:
        """Every conversion this load made, in read-back order (`_rank`)."""
        return sorted(self._converted, key=lambda c: _rank(c.key))

    def real(self, data: Dict[str, Any], key: str, dotted: str, default: float) -> float:
        """The REAL figure the spec stores for `key`: the anchored default when
        the config omits it, the typed figure as is under `rates: real`, else
        the typed figure deflated by inflation_rate — recorded as converted."""
        if key not in data:
            return default
        typed = float(data[key])
        if self.rates == "real":
            return typed
        real = deflate(typed, self.inflation_rate)
        self._converted.append(ConvertedRate(
            dotted, typed, typed if self.mode == "nominal" else real))
        return real

    def discount_rate(self, data: Dict[str, Any], anchor_value: float) -> float:
        """The discount rate IN USE (the spec holds it in the run's own terms):
        the anchored real default composed in nominal mode; a typed figure as
        quoted — used as typed in nominal mode, deflated in real mode — or, under
        `rates: real`, composed like the default."""
        if "discount_rate" not in data:
            real = anchor_value
        elif self.rates == "real":
            real = float(data["discount_rate"])
        else:
            typed = float(data["discount_rate"])
            in_use = typed if self.mode == "nominal" else deflate(typed, self.inflation_rate)
            self._converted.append(ConvertedRate("discount_rate", typed, in_use))
            return in_use
        return compose(real, self.inflation_rate) if self.mode == "nominal" else real


def converted_for(converted: List[ConvertedRate], dotted: str) -> Optional[ConvertedRate]:
    for entry in converted:
        if entry.key == dotted:
            return entry
    return None
