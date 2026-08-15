"""Excess-demand fraction (spec §7, codex F4). All terms annual, household-
denominated, per (geography g, year t, scenario s):

    ED(g,t,s) = [ D(g,t,s) - S(g,t,s) ] / OwnerStock(g,t,s)

    D = native owner-household formation + immigrant-cohort formation   (demand/formation.py)
    S = sum_cause exits(cause) * phi_market(cause), estate lagged L      (cohort/listings.py)
    OwnerStock = the §7 defining equation                               (balance/owner_stock.py)

ED is scale-invariant (households/households). Denominator guard has a NUMERIC boundary
(codex r9-F5): OwnerStock < 1,000 households -> raise (no modeled geography legitimately
carries fewer; never leave "near-zero" to implementation taste, never emit an unbounded
fraction). Tranche 1 stops at the raw fraction; the ED->drift mapping (beta) is Tranche 2.

A NEGATIVE ED IS A READING, NOT AN ERROR, and nothing here clamps it: S > D means more owner
households are listing than forming, and §7's Tranche-2 mapping handles the sign explicitly
("reversed for ED < 0"). A floor at zero would delete the entire downside half of the signal a
demographic-decline model exists to measure.

THE FINITENESS CHECKS ARE ADDED BEYOND THE PLAN BODY, on `cohort/listings.py`'s precedent (its
lag and fraction guards, added for the same reason): the rejected shapes are silently wrong
rather than loudly wrong, and the r9-F5 guard as written cannot see them.

  * DENOMINATOR. Every ordering against NaN is False, so `owner_stock < MIN_OWNER_STOCK`
    passes a NaN straight through and the fraction the guard exists to bound comes out NaN.
    An INFINITE stock passes the compare honestly and divides to a flat 0.0 — a perfectly
    balanced market, reported with no trace of the input that produced it. A separate
    finiteness check is therefore ADDED, and it is UNCONDITIONAL — that, not its position
    ahead of the magnitude compare, is what catches both shapes: neither NaN nor +inf can trip
    `< MIN_OWNER_STOCK`, so the magnitude compare could not preempt it whichever ran first
    (measured, run 23 — only `-inf` changes WHICH of the two messages surfaces, and it is
    refused either way). The 999 / 1,000 / 1,001 boundary is untouched by it.
  * NUMERATOR. `market_listings` asserts its lag and its eventual-listing fraction but never
    the exit COUNTS, so a NaN estate count convolves into a NaN S and arrives here as an
    ordinary float. Spec §7's emitter does refuse non-finite output (`allow_nan=False`) — but
    only if the NaN survives to it, and ED is the last arithmetic before the artifact. Caught
    here, the error can still name WHICH term was bad; downstream all that is left is a NaN row.

This module deliberately stays a pure leaf (`math` + the error taxonomy): its guards are
scalar, so nothing here needs `loaders.validate`, which pulls pandas transitively.
"""
import math

from demoflow.errors import CalibrationError

MIN_OWNER_STOCK = 1000.0


def _finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise CalibrationError(
            f"excess-demand term {name} is {value!r} — not finite; the emitter refuses "
            "non-finite output (allow_nan=False) but only if the value survives to it, and "
            "this is the last arithmetic that can still name which term was bad")
    return value


def excess_demand(D: float, S: float, owner_stock: float) -> float:
    if not math.isfinite(owner_stock):
        raise CalibrationError(
            f"OwnerStock is {owner_stock!r} — not finite: the magnitude guard below cannot see "
            "it (every ordering against NaN is False, and an infinite stock divides to a flat "
            "0.0), so an unbounded fraction would be emitted with no trace of the input")
    if owner_stock < MIN_OWNER_STOCK:
        raise CalibrationError(
            f"OwnerStock {owner_stock} < {MIN_OWNER_STOCK} households — no modeled geography "
            f"legitimately carries fewer (denominator guard)")
    return (_finite("D", D) - _finite("S", S)) / owner_stock
