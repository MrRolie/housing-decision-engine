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
`load_headship_rates`, and spec §7's `data_vintage.source_hashes` is filled by
`pipeline._source_hashes`, which hashes each derived artifact's own bytes off disk and reads
that artifact's recorded `extracted_at` out of the bytes it hashed. NOTHING carries a vintage
RECORD from load to emit: the typed one this paragraph used to name was real code with no
production caller, and it went with `loaders/vintage.py` at the round-3 elegance audit
(2026-08-22).

MISSING IS NOT ZERO, THROUGH BOTH DOORS. The plan body read every mapping with
`.get(·, 0.0)`. A hole then deletes demand (a rate absent at `a`) or INFLATES it (a rate or a
COHORT absent at `a−1`, which zeroes the stock the gain is measured against) while every
intermediate value stays a plausible float — the failure class this repo's loaders already
refuse. Both doors raise: `_households` for the rate, `_require_prior_cohort` for the
population, each scoped to terms that actually contribute, and each accepting a stated ZERO
while refusing an ABSENCE. The one documented exception is the Census ownership lattice's
floor (see `OWNERSHIP_LATTICE_FLOOR`), which is a CHOICE landed upstream in
`census._AGE_BAND_SPEC` — not the data's silence, and not a local decision.
"""
import math

from demoflow.errors import LoaderError
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite

AGE_MIN = 18        # household-formation floor (codex r7-F7 — a−1 must never leave the domain)
AGE_BOUNDARY = 75

# `ownership(a)` is UNDEFINED below age 25 BECAUSE THE DERIVATION SPEC STARTS AT 25, not
# because the table is silent there — corrected 2026-08-15 under spec §7 amendment #12, and the
# distinction is the whole reason this block is long. 98-10-0231-01 PUBLISHES owner-maintainer
# counts below 25 (`15 to 19 years` and `20 to 24 years`, at all seven of its GEO rows; Québec
# 20-24 is 17,170 owners of 106,605 households), and census.py's own `_HEADSHIP_MEMBER_SPEC` reads
# both members off the same age dimension of the same extract while `_AGE_BAND_SPEC` drops them.
# The convention is still NOT decided here — it is census.py's `zero_support_note` (T13b
# 2026-08-08, re-attributed at amendment #12), which now names the omission as this module's
# upstream CHOICE. This module mirrors that; the floor is duplicated rather than imported (this
# module stays free of the Census band table, as `living_arrangement` stays free of
# `census._QC_CMAS`) and pinned equal to `min(census._AGE_BANDS)` by test.
#
# MEASURED CONSEQUENCE, stated in full rather than at its smallest instance: the pipeline
# builds its curve over `range(25, 101)`, so ALL SEVEN sub-floor terms of the spec §6
# summation — ages 18, 19, 20, 21, 22, 23, 24, not just the explicit a_min boundary term —
# evaluate to ZERO in every production run. Both arms are pinned by test at each of the seven.
#
# HOW MUCH THAT DROPS — AN ORDER-OF-MAGNITUDE BOUND, NEVER A MEASUREMENT, and the qualifier is
# load-bearing rather than modest. Measured 2026-08-14 on the real artifacts — WHICH CARRIED THE
# SIX-BAND HEADSHIP CURVE, retired by operator ruling V on 2026-08-19, so EVERY FIGURE IN THIS
# BLOCK IS PRE-RULING-V and none of them is a reading of the curve now shipped. They stand here
# unrestated on purpose: re-measuring them against the age-resolved curve is the ordered
# follow-on that must land BEFORE the ownership lattice moves below 25, and census.py's
# `zero_support_note` carries the binding copy of that requirement. THE RECIPE, stated
# in full because the fan is a filter and not a default: MTL_RMR, the `Scenario.REFERENCE` rows
# of `pop-as-rmr-base.xlsx` (ISQ's central fan of THREE — the label is a scenario, never an
# edition), years 2025 -> 2026. On that reading: 59.5% of D_native at first sight — but 97.6% of
# that mass was ONE term, the age-20 gain of 21,353 households, an artifact of the pipeline
# sketch AS WIRED ON THAT DATE, reusing the six-band curve at single years of age (h jumped
# 0.0061 -> 0.3954 across the 0-19 -> 20-34 boundary — a step that no longer exists; the
# resolved curve spreads that rise across 20..34, so the floor now discards a SLOPE, not a
# STEP). census.py's own `zero_support_note` forbade exactly that reuse — "a consumer
# multiplying a SINGLE age inside the band ... must land an age-resolved curve" — and ruling V
# is that curve landing, which is why the clause now reads as discharged rather than as a
# warning. Net of band-entry ages the sub-floor drop was 1.42%; on LOW and HIGH it was 59.8% /
# 59.3% and 0.91% / 2.33%, so what was priced is the convention and not the fan. 100% of the
# D_native computed on that wiring was itself band-entry mass in all three fans, so NO LEVEL
# from it is a measurement of this convention.
#
# WHAT RULING V DID MEASURE, AND IT IS NOT THE RE-MEASUREMENT ORDERED ABOVE. The acceptance
# metric for the age-resolved curve was the CONCENTRATION of D_native — the largest single-age
# share. THE COLLAPSE IS THE MEASURED PART; THE 14-18% BAND IT WAS READ AGAINST IS NOT A GATE
# THIS CURVE MET OR MISSED. That band is the design panel's ("The success criterion, measured";
# docs/research/2026-08-19-headship-curve-design-panel.md), and the panel states in the same
# document that ALL its magnitudes are PROBE-GRADE: raw ISQ populations in place of P_resident
# (~7% of scale), the committed `mean_ed_reference` in place of per-year ED, no immigrant leg.
# Its baseline for the committed curve — 65-77% at age 35 — does not reproduce: the live recipe
# below puts that same curve at 79.9%, and the run-34 review could not reproduce 65-77% under
# any convention it tried (run-record of the headship-curve review). So the
# band is CONVENTION-DEPENDENT and not commensurable with a live P_resident measurement; it is
# recorded here as the design's expectation and never as a threshold, which is the correction
# the run-34 review made to the mandate that set it.
# THE COLLAPSE, measured 2026-08-19 on the shipped artifacts, same recipe as above (MTL_RMR,
# `Scenario.REFERENCE`) with the §6 P_resident operand, the 26 projected years pooled: the
# RETIRED six-band curve peaked at age 35 with 79.9% (per-year 77.5-83.9%); the shipped
# `expo_cum_fc` peaks at age 26 with 26.1% (24.3-40.4%) and `expo_cum_fb` at 26 with 31.5%
# (29.4-46.0%). The band step is GONE — the per-age profile is smooth (h: 24 -> 0.30553,
# 25 -> 0.35090, 26 -> 0.40615, 27 -> 0.44563).
# THE RESIDUAL PEAK AT 26 IS THE OWNERSHIP LATTICE'S ENTRY STEP, NOT A CURVE DEFECT — and it is
# the NEXT ORDERED STEP (spec §7 amendment #12), not something to fix in the curve: ages 18-24
# contribute EXACTLY 0.0 because `_ownership` returns 0.0 below the floor, so the mass piles on
# the first ages the lattice admits, 25-27 (65.8% of the horizon total). The same run with the
# floor probed at 18 moves the peak to age 21, at 12.6% on `expo_cum_fc` and 16.5% on
# `expo_cum_fb`, against 26.1% / 31.5% at floor 25. That 13.5pp drop on fc is what ATTRIBUTES
# the residual to the lattice edge, and it is larger than the entire excess over the panel's
# expected band — which is why the attribution survives the band being convention-dependent.
# One proposal PREDICTED that attribution (the EWC-PCHIP submission's `age20_interaction`
# item 3, at its own probe's 16.1% — a DIFFERENT chassis and a probe-grade level, so it is a
# corroborating prediction and not a figure to carry); the counterfactual above is the
# measurement that was missing from it.
# THAT IS NOT A LICENCE TO MOVE THE FLOOR: the ordered re-measurement above is the sub-floor
# DROP against the age-resolved curve, it is still pending, and it is what the floor move
# waits on.
#
# ITS DIRECTION ON ED, IN ED's OWN UNIT — the part that survives the contamination above,
# because both legs carry the same band-entry artifact and it largely cancels in their RATIO
# (QFE 2026-08-15, ruled at spec §7 amendment #12). The convention hits BOTH sides:
#   * NUMERATOR: the zeroed 18-24 formation terms are an ADDITIVE hit worth 0.195-0.337% of
#     OwnerStock, and they SHRINK D.
#   * DENOMINATOR: the zeroed sub-25 stock terms are a MULTIPLICATIVE 0.96-1.65%, and they
#     shrink OwnerStock.
# The numerator leg DOMINATES by roughly 30x-200x. The two are equal only at |ED| ~ 19-21%/yr,
# against an ISQ-implied stock movement of 0.10-0.63%/yr — that separation IS the 30x-200x just
# stated and not a second fact (the leg ratio at an operating |ED| is exactly the crossover
# |ED| over it), which is what makes the crossover a statement and not a caveat. No larger gloss
# belongs here: both source documents stop at the ratio. SO: FOR ED < 0 — the
# decline regime this model exists to measure — BOTH LEGS PUSH PESSIMISTIC. Any sentence
# calling this convention's effect "optimistic" is priced on the smaller leg alone and is
# sign-wrong exactly where it matters. The denominator leg's near-uniformity across geographies
# does NOT transfer to the numerator either: an additive non-uniform shift can REORDER the
# rankings where a multiplicative near-uniform one cannot.
#
# THE FIX IS ORDERED, NOT OPTIONAL, ITS ORDER BINDS (spec §7 amendment #12) — AND THE ORDER IS
# NOW HALF DISCHARGED. The first half LANDED with the age-resolved headship curve
# (operator ruling V): this zero used to be
# the only thing suppressing the age-20 band-entry artifact, so extending the ownership curve
# below 25 while the curve was banded would have MULTIPLIED that artifact into demand instead of
# zeroing it — and that artifact is gone, replaced by the smooth 20..34 rise measured above. WHAT
# STILL BLOCKS THE SECOND HALF IS THE RE-MEASUREMENT, NOT THE CURVE: amendment #12's quantified
# floor-effect legs are pre-ruling-V (the floor counterfactual at 12.6% / 16.5% above is NOT that
# re-measurement — it is post-ruling-V and prices CONCENTRATION, not the sub-floor drop). So the
# order is now: age-resolved headship (DONE), then the re-measurement, then the floor. The floor
# literal below is pinned by
# test_the_ownership_LATTICE_FLOOR_IS_A_TRIPWIRE_that_reds_when_the_floor_moves
# (demoflow/tests/test_census_ownership.py), which reds on ANY move of it and names the
# re-measurement in its failure message — that tripwire is the only guard that reds on ANY move
# of the floor, and the only one whose message names the re-measurement. It is NOT the only guard
# that fires at all: `census._zero_support_note` RAISES when `_ownership_spec_omitted_members`
# comes back empty, but that one needs a FULL extension down to the youngest published member and
# it orders a clause rewrite rather than this measurement — which is why that note counts TWO
# guards on the move, and states the same limit this block does rather than implying the suite can
# check that the measurement itself was DONE.
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
    the population loader that could reach it. THE WIRING HAS LANDED, and
    the sentence that stood here claiming otherwise contradicted this module's own header:
    `pipeline._ed_series` calls this function once per (leg, geography, scenario, projected
    year) — 14 x 8 x 3 x 26 = 8,736 calls per run on the declared seven-axis grid, measured
    2026-08-22 and written as its factorization because a bare product is exactly what went
    stale twice on this quantity. WHAT A CALLER DOES NOT MAKE OBSERVED, said because "it is
    wired" is not "its guards fire": over that run `_households` is entered 987,168 times and
    `_require_prior_cohort` 489,216, and NO refusal branch below is reached once — the committed
    curves carry a rate at every age the sum reads and the projection frame carries every
    prior-year cohort. The refusals are therefore contracts whose violation path only
    `tests/test_demand.py` reaches. The unit assertions are NOT in that class and must not be
    read as covered by the same sentence: `assert_fraction` evaluates on all 987,168 production
    reads, and `_ownership`'s sub-floor `return 0.0` is production behaviour 61,149 times.
    ISQ populations are already refused non-finite and negative at load (`loaders/isq.py`).

    P_resident(a) ≥ 0 IS NOT CHECKED HERE, AND NOT PER CELL ANYWHERE — it holds by COMPOSITION,
    and the sentence that stood in this docstring pointed at a check no code performs at this
    operand's granularity (codex r12-F1). It read "P_resident ≥ 0 belongs UPSTREAM, asserted per
    cell before any consumer: `demand/i2.py`'s `assert_p_resident_nonneg` ... not re-checked here
    because the spec assigns the check upstream" — which is spec §6's own "asserted per cell",
    and it is false in the sense this function depends on: that assertion takes a SCALAR, has ONE
    production call site, and evaluates on the (geography, scenario, year) TOTAL — 27 times per
    geography-scenario against the 2,727 per-age cells the property quantifies over, with no call
    context carrying an age. The per-age operand is not representable there at all:
    `pipeline._surviving_arrivals` returns a flat list of YEAR flows with no age index, so there
    is no per-age arrivals term to subtract from P_ISQ(a). WHAT MAKES THE PROPERTY TRUE is the
    map the producer builds: every cell is `P_ISQ(a) × scale`, with `P_ISQ(a) ≥ 0` refused at
    load (the sentence above) and `scale = P_resident_total / P_ISQ_total ≥ 0` because the
    total-level gate refuses a negative numerator and `pipeline` refuses a non-positive
    denominator — nonneg × nonneg, and no per-cell check in it. NOTHING BELOW WOULD CATCH A
    NEGATIVE CELL: `_households` binds finiteness and rate PRESENCE, never the sign, so one would
    enter the formation sum as a plausible float. That is why the composition is bound by a test
    rather than left resting on this paragraph —
    `tests/test_pipeline.py::test_the_per_age_P_resident_operand_is_NONNEG_BY_COMPOSITION`.

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

    `p_nonimm` MUST ARRIVE CONVERTED, and this function cannot check it (amendment #24(A)). The
    ownership cube the wired caller reads has no immigrant dimension, so the rate it serves is
    ALL-maintainer while this `ratio`'s denominator is non-immigrants alone; multiplying them
    unconverted emits `p_imm_true x B`. `pipeline._ed_series` divides by the geography's measured
    `B` before calling here. Both an unconverted rate and a converted one are perfectly valid
    fractions, which is why the guard is at the call site and this docstring names it instead.

    THE PRODUCT STILL BINDS, and it is not the only thing that binds: each operand is asserted
    in its OWN units FIRST. `p_nonimm` is a fraction; `ratio` is nonneg-finite and may validly
    exceed 1 (immigrants can out-own non-immigrants in a cell — codex r7-F8, measured at 1.033
    in New Brunswick), which is why only the product carries the [0,1] rule.

    The earlier docstring claimed the product's [0,1] assertion alone stopped any negative or
    non-finite input. That was FALSE FOR A PAIR and is retired (run-21 carry, measured
    2026-08-15 — the sentence is paraphrased rather than quoted here, so the test that pins it
    gone reads a live claim and not a museum label):
    two negatives multiply into a perfectly valid-looking propensity — `p_imm(-0.5, -0.5)`
    returned 0.25 and `immigrant_formation(100.0, 0.5, p_nonimm=-0.5, ratio=-0.5)` returned
    12.5, neither raising — and `p_nonimm` above 1 against a small ratio passed just as
    quietly. THE ESCAPE WAS WIDER THAN THE RUN-21 CARRY RECORDED (re-measured run 24 against
    the verbatim old body, both legs): a SINGLE negative also escaped whenever its partner was
    0.0, because the product is -0.0 and `0.0 <= -0.0 <= 1.0` holds — `p_imm(-0.6, 0.0)` and
    `p_imm(0.0, -0.6)` each returned -0.0 unraised. Against a nonzero partner a single negative
    did raise, and every non-finite input did (nan × 0 is nan), but on the PRODUCT's message,
    which names the wrong quantity to whoever has to fix the input. Not a live bug:
    the wired path feeds `p_nonimm` from fraction-asserted ownership rates and `ratio` from the
    nonneg-asserted join table (and Task 29 is what wires it at all) — a defensive-guard gap
    and a false sentence, closed together.
    """
    return assert_fraction(
        "p_imm",
        assert_fraction("p_nonimm", p_nonimm)
        * assert_nonneg_finite("immigrant_ownership_ratio", ratio))


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
