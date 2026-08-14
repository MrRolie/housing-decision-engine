"""Demand side (spec §6, codex r2-F2/r4-F5/r6-F1/r6-F2/r7-F7/r10-F4).

Native formation = GROSS under-75 cohort-followed headship gains only (75+ dynamics belong
to S — structural D/S disjointness at the age-75 boundary, without which a 75+ headship
decline enters D as negative formation while the SAME dissolutions enter S and the senior
release is double-counted). Its ONLY population input is P_resident. The immigrant chain is
dimensionally explicit: persons -> households -> owner demand, with `p_imm = p_nonimm ×
ratio` asserted in [0,1].

MULTIPLICANDS, STATED AT EVERY USE SITE (run-6 carry — the three rate surfaces in this
package take three different operands and every mix-up is invisible in the numbers):

  * `headship_by_age(a)` multiplies **RAW ISQ persons — collective/institutional residents
    INCLUDED**. Its denominator is the ISQ published population by single year of age
    (census.py `derive_headship_from_sources`, and the artifact's own `multiplicand_note`),
    so the operand here is `resident_pop_*` = spec §6's P_resident = P_ISQ minus surviving
    arrival cohorts — still on the raw ISQ basis. `CONSTANTS['collective_share_75plus']` is
    NOT removed on this path: removing it would understate formations, because those
    residents sit in the denominator that produced the rate.
  * `living_arrangement`'s per-sex partition rates take the OTHER multiplicand — PRIVATE-
    household persons — so `cohort/init.py` strips the collective share before applying them.
    That difference is by design, not an inconsistency; the surfaces are not interchangeable.
    Nothing in this module touches those rates, and this is the sentence that says why.
  * `ownership_by_age(a)` and `p_imm` are HOUSEHOLD-denominated (owner-maintainer households
    / private households), so both legs convert to households FIRST — natively via headship,
    on the arrival leg via the immigrant headship rate. Persons never multiply a household
    rate directly (codex r2-F2); that is the units defect the dimensional test pins.

VINTAGE: this module is pure arithmetic over plain dicts and holds no provenance itself. A
production caller loads its rate surfaces through `census.load_ownership_rates` /
`load_headship_rates` and carries the matching `census.load_ownership_vintage()` /
`load_headship_vintage()` records from load to emit, which is what fills spec §7's
`data_vintage.source_hashes` with the vintage the run actually READ (rather than a hash of
whatever is on disk at emit time).

MISSING IS NOT ZERO, THROUGH BOTH DOORS. The plan body read every mapping with
`.get(·, 0.0)`. A hole then deletes demand (a rate absent at `a`) or INFLATES it (a rate or a
COHORT absent at `a−1`, which zeroes the stock the gain is measured against) while every
intermediate value stays a plausible float — the failure class this repo's loaders already
refuse. Both doors raise: `_households` for the rate, `_require_prior_cohort` for the
population, each scoped to terms that actually contribute, and each accepting a stated ZERO
while refusing an ABSENCE. The one documented exception is the Census ownership lattice's
floor (see `OWNERSHIP_LATTICE_FLOOR`), which is a convention landed upstream, not a local one.
"""
import math

from demoflow.errors import LoaderError
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite

AGE_MIN = 18        # household-formation floor (codex r7-F7 — a−1 must never leave the domain)
AGE_BOUNDARY = 75

# 98-10-0231-01 publishes no owner-maintainer rate below age 25, so `ownership(a)` is
# UNDEFINED there and an absent rate below this age contributes nothing. That convention is
# NOT decided here: it is census.py's `zero_support_note`, landed at T13b 2026-08-08 —
# "undefined, hence contributing nothing, below the ownership lattice's floor of 25". This
# module mirrors it; the floor is duplicated rather than imported (this module stays free of
# the Census band table, as `living_arrangement` stays free of `census._QC_CMAS`) and pinned
# equal to `min(census._AGE_BANDS)` by test.
#
# MEASURED CONSEQUENCE, stated in full rather than at its smallest instance: the pipeline
# builds its curve over `range(25, 101)`, so ALL SEVEN sub-floor terms of the spec §6
# summation — ages 18, 19, 20, 21, 22, 23, 24, not just the explicit a_min boundary term —
# evaluate to ZERO in every production run. Both arms are pinned by test at each of the seven.
#
# HOW MUCH THAT DROPS, measured 2026-08-14 on the real artifacts so a later reader is not left
# to guess. THE RECIPE, stated in full because the fan is a filter and not a default: MTL_RMR,
# the `Scenario.REFERENCE` rows of `pop-as-rmr-base.xlsx` (ISQ's central fan of THREE — the
# label is a scenario, never an edition), years 2025 -> 2026. On that reading: 59.5% of D_native
# at first sight — but 97.6% of that mass is ONE term, the age-20 gain of 21,353 households,
# which is an artifact of the pipeline sketch reusing the BANDED headship curve at single years
# of age (h jumps 0.0061 -> 0.3954 across the 0-19 -> 20-34 boundary). census.py's own
# `zero_support_note` forbids exactly that reuse: "a consumer multiplying a SINGLE age inside
# the band ... must land an age-resolved curve". Net of band-entry ages the sub-floor drop is
# 1.42%. The other two fans move none of this: re-run on LOW and HIGH the drop is 59.8% / 59.3%
# and the net 0.91% / 2.33%, so what is priced here is the convention, not the fan. The same
# probe found 100% of the computed D_native is itself band-entry mass — in all three fans — so
# NO number from that wiring prices this convention: the question reopens when the pipeline
# lands an age-resolved headship curve, and is reported to the seat rather than settled here.
#
# The a_min term still earns its place independently of all of the above: it exists so a_min
# entrants form against a zero prior stock BY EQUATION instead of against H(17) by array
# wraparound (codex r7-F7). A supplied sub-floor rate is still used, so an extended curve is
# never swallowed by this convention.
OWNERSHIP_LATTICE_FLOOR = 25


def _households(pop_by_age: dict[int, float], headship_by_age: dict[int, float],
                age: int, when: str) -> float:
    """H(age) = persons(age) × headship(age), on the RAW ISQ basis (see the module docstring).

    A missing rate RAISES where the population is nonzero, and the two legs fail in opposite
    directions: absent at `a` understates the gain, absent at `a−1` zeroes the prior stock so
    a whole standing cohort reads as newly formed. Where the population is zero the term is
    zero whatever the rate is, so no rate is demanded — that is what keeps the wraparound
    fixture's planted 17-year-old (never read by the equation) from needing one.
    """
    persons = pop_by_age.get(age, 0.0)
    if persons == 0.0:
        return 0.0
    if not math.isfinite(persons):
        # A NaN population would otherwise DISAPPEAR here rather than propagate: every
        # ordering against NaN is False (the property `cohort/decrements` relies on), so the
        # gain fails the `> 0` test and the term is dropped silently. Spec §7's emitter
        # refuses non-finite output (allow_nan=False), but only if the NaN survives to it.
        raise LoaderError(f"population at age {age} ({when}) is {persons} — not finite")
    if age not in headship_by_age:
        raise LoaderError(
            f"no headship rate for age {age} ({when}), where {persons:,.1f} persons are "
            "present — an absent rate is not a zero rate: it would silently "
            f"{'shrink' if when == 'year t' else 'inflate'} native formation")
    return persons * assert_fraction(f"headship[{age}]", headship_by_age[age])


def _require_prior_cohort(resident_pop_t: dict[int, float],
                          resident_pop_tm1: dict[int, float], age: int) -> None:
    """The POPULATION twin of `_households`'s missing-rate guard, on the inflating leg.

    The rate guard closed only half of "missing is not zero": an absent prior-year COHORT
    zeroes the stock the gain is measured against just as effectively as an absent prior-year
    RATE does, and in the same direction — a whole standing cohort reads as newly formed.
    Measured 2026-08-14 on a one-age fixture: 30.0 with the prior year present, 300.0 with it
    absent, every intermediate value a plausible float. The live door is the pipeline's
    `resident_tm1`, built from the projection frame at `t-1`, which yields `{}` for any year
    the frame does not carry — so an off-by-one in the horizon loop would inflate D silently.

    PRESENT-BUT-ZERO is deliberately accepted: that is a STATED empty cohort (a legitimate
    reading at the top of the lattice), not a hole. Absence is the only thing refused, which
    is precisely the distinction `.get(age, 0.0)` erases.
    """
    if resident_pop_t.get(age, 0.0) != 0.0 and (age - 1) not in resident_pop_tm1:
        raise LoaderError(
            f"no year t-1 population at age {age - 1}, where age {age} carries "
            f"{resident_pop_t[age]:,.1f} persons in year t — an absent prior cohort is not a "
            "zero prior cohort: it zeroes the stock the gain is measured against, so a whole "
            "standing cohort reads as newly formed and native formation INFLATES. Supply the "
            "prior year's cell (0.0 is accepted and means the cohort is genuinely empty)")


def _ownership(ownership_by_age: dict[int, float], age: int) -> float:
    """ownership(age) for a term that HAS a positive formation gain.

    Called only on contributing terms: a rate that multiplies nothing is not required (the
    pipeline's 25..100 curve legitimately carries no gain at most ages in a given year), while
    a rate absent where a real gain forms would delete that demand silently.
    """
    if age in ownership_by_age:
        return assert_fraction(f"ownership[{age}]", ownership_by_age[age])
    if age < OWNERSHIP_LATTICE_FLOOR:
        return 0.0          # undefined below the Census lattice — the documented convention
    raise LoaderError(
        f"no ownership rate for age {age}, where a positive formation gain gets multiplied — "
        f"the age is at or above the Census lattice floor ({OWNERSHIP_LATTICE_FLOOR}), so "
        "'undefined below the floor' does not explain it; the curve is holed and the demand "
        "would silently shrink")


def native_formation(resident_pop_t: dict[int, float], resident_pop_tm1: dict[int, float],
                     headship_by_age: dict[int, float], ownership_by_age: dict[int, float]) -> float:
    """D_native = max(0, H_res(18,t))×ownership(18)  +  Σ_{19≤a<75} max(0, H_res(a,t) −
    H_res(a−1,t−1))×ownership(a)  (codex r10 — the explicit a_min=18 boundary term is INCLUDED;
    the earlier strict `a_min < a < 75` form wrongly dropped it). At a_min entrants form against
    ZERO prior stock, by equation, never by array wraparound (r7-F7). `resident_pop_*` is
    P_resident (§6 operand binding) — never total ISQ pop, and this module has no code path to
    the population loader that could reach it. P_resident ≥ 0 belongs UPSTREAM, asserted per
    cell before any consumer: `demand/i2.py`'s `assert_p_resident_nonneg` (codex r7-F3). It is
    not re-checked here because the spec assigns the check upstream. WHAT IS STILL PENDING is
    the WIRING, not the guard: the pipeline that calls it lands at Task 29, so no production
    caller runs it today — this module's only callers are its tests, and ISQ populations are
    already refused non-finite and negative at load (`loaders/isq.py`).

    GROSS under-75 formations only: negative gains floor at zero because ALL 75+ stock dynamics
    — dissolution, downsizing, estate release — live exclusively in S via the cohort engine.

    INPUT CONTRACT (it RAISES, so a caller should read it here and not only in the module
    docstring): wherever `resident_pop_t` carries a nonzero cohort at 19≤a<75, `resident_pop_tm1`
    must carry a cell at `a−1` and both curves must carry a rate at the ages the sum reads. A
    cell of 0.0 satisfies this; an ABSENT cell does not.
    """
    entrants = max(0.0, _households(resident_pop_t, headship_by_age, AGE_MIN, "year t"))
    total = entrants * _ownership(ownership_by_age, AGE_MIN) if entrants > 0.0 else 0.0
    for a in range(AGE_MIN + 1, AGE_BOUNDARY):                  # 19 <= a < 75
        # `h_t` FIRST: it carries the finite check, so a NaN population still reports as a NaN
        # rather than as whatever the prior-cohort guard would make of it.
        h_t = _households(resident_pop_t, headship_by_age, a, "year t")
        _require_prior_cohort(resident_pop_t, resident_pop_tm1, a)
        gain = h_t - _households(resident_pop_tm1, headship_by_age, a - 1, "year t-1")
        if gain > 0.0:                                          # max(0, ·): the sign rule (r6-F2)
            total += gain * _ownership(ownership_by_age, a)
    return total


def immigrant_households(arrival_persons: float, immigrant_headship_rate: float) -> float:
    """Persons -> households (households per person). Encodes household size, so 100
    persons as 50 two-person households (rate 0.5) != 100 one-person households (rate 1.0).

    BOTH OPERANDS ARE GATED, in the same class as `native_formation`'s guards — this leg
    asserted nothing until Task 25b, so `immigrant_households(-100, 0.5)` returned -50.0 and a
    NaN rode straight through. Arrivals are a gross INFLOW: §4's signed-flow carve-out covers
    natural increase and net-migration COMPONENTS, never this, so the stock rule binds
    (nonneg + finite); a negative arrival count would SUBTRACT owner demand, which no equation
    in §6 produces. The rate is a FRACTION (§4 names headship in its [0,1] list) — the join
    table refuses a bad TABLE value at import, and this refuses one arriving by any other door.
    """
    return (assert_nonneg_finite("immigrant_arrival_persons", arrival_persons)
            * assert_fraction("immigrant_headship_rate", immigrant_headship_rate))


def p_imm(p_nonimm: float, ratio: float) -> float:
    """p_imm(a) = p_nonimm(a) × ratio, asserted ∈ [0,1] (codex r4-F5 — never a bare ratio).

    The PRODUCT binds, not the ratio: `ratio` > 1 is valid (immigrants can out-own
    non-immigrants in a cell — codex r7-F8, measured at 1.033 in New Brunswick), and a
    negative or non-finite input cannot pass the product's own [0,1] assertion.
    """
    return assert_fraction("p_imm", p_nonimm * ratio)


def immigrant_formation(arrival_persons: float, immigrant_headship_rate: float,
                        p_nonimm: float, ratio: float) -> float:
    """Arriving PERSONS -> immigrant HOUSEHOLDS -> immigrant owner-household demand.

    The intermediate step is the whole point (codex r2-F2): without it a person count
    multiplies a household-denominated propensity and household size vanishes from the model.
    """
    return immigrant_households(arrival_persons, immigrant_headship_rate) * p_imm(p_nonimm, ratio)


def total_owner_demand(native: float, immigrant: float) -> float:
    """D = D_native + D_immigrant — a SUM, never a union: the immigrant channel decomposes the
    projected population (invariant I2), it does not add demand on top. What keeps the sum
    honest is upstream — native reads P_resident, i.e. P_ISQ net of surviving arrivals."""
    return native + immigrant
