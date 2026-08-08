"""Persons->households conversion (spec §5 AS AMENDED at 91884dc, steering ruling A).

Per (geography, age, SEX), private-household persons partition into exactly THREE buckets
using SEX-SPECIFIC rates (a pooled couple rate is not sex-conserving — 20 men + 100 women at
couple_share=1 fabricates 40 husbands). Couples form by MINIMUM matching, never an average;
the excess `max − min` routes to `Other`, which keeps per-sex person conservation exact and
keeps those persons conservatively OUT of the owner-unit stock.

WHICH MULTIPLICAND (recorded because getting it wrong is invisible — every value stays a
plausible number either way): these three buckets multiply the PRIVATE-HOUSEHOLD population,
`pop_by_sex × (1 − collective_share)`, because `living_arrangement.json`'s denominators are
private-household persons (its own `multiplicand_note`). ISQ's projected population includes
collective/institutional residents and at 75+ that is exactly where collectives concentrate,
so applying the rates to the raw ISQ stock double-counts collective residents into
Solo/Couple/Other. `headship_by_age.json` carries a DIFFERENT denominator — RAW ISQ persons
(spec:395 vs :162) — by design; it is never a substitute multiplicand here. The variable is
named `private_pop` and echoed on the result so the claim travels with the numbers.

Ownership rates are HOUSEHOLD-MAINTAINER-denominated (Census tenure tables) and therefore
multiply HOUSEHOLD counts, never person counts.

GATES — steering ruling A retired the 0.25 SAME-AGE band gate, so what remains is exactly the
set of invariants reality preserves:

  1. `coupled_s >= 0`                    (`match_couples`)
  2. `coupled_s <= its sex pool`         (`initialize_households`)
  3. at the 75+ AGGREGATE, `coupled_m >= coupled_f`, a reversal beyond |Δ|/max > 0.25 raising
     (`assert_aggregate_coupled_direction`)

Gates 1 and 2 are second-line and fire for DIFFERENT reasons (a rate above 1 on `living_alone`
drives coupled negative; one on `couple_share` drives it past the pool). They are NOT a general
out-of-range detector: that job belongs to the loaders' `assert_fraction`, which every rate on
every real path already cleared. Each catches its case only under its own PRECONDITION — both
holes measured 2026-08-08 against this module:

  * gate 1 catches `living_alone_s > 1` only when `couple_share_s > 0`. At `couple_share_s == 0`
    the product is the SIGNED ZERO `-0.0` and `-0.0 < 0.0` is False, so nothing fires — e.g.
    `living_alone 1.2, couple_share 0.0` on a pool of 100 returns Solo 120 (above its own pool)
    and Other −20;
  * gate 2 catches `couple_share_s > 1` only when `(1 − living_alone_s) · couple_share_s > 1`.
    At `living_alone 0.5, couple_share 1.2` coupled is 60 against a pool of 100 — under the
    pool, so nothing fires, and Other is −10.

Both holes return SILENTLY with a negative `Other` because per-sex conservation still balances
(that identity is algebraic in the three expressions, so it holds for any rate). NO FOURTH GATE:
spec §5 as amended enumerates exactly three, and steering ruling A's content is that the gate set
was NARROWED — widening it back here would be fork-class. The two preconditions are therefore
RECORDED, not closed; `assert_fraction` at the loader boundary is what closes them in practice.

Gate 3 is AGGREGATE-SCOPED and is deliberately NOT called from `initialize_households`:
§5's per-cell equations are per (age, sex), and the direction claim is stated at the 75+
aggregate only. CARRY — its call site is Task 29's pipeline `_init_stock` (plan:4677-4687), which
sums `age >= 75` per sex and hands exactly that aggregate in; that task must call
`assert_aggregate_coupled_direction(h.coupled_m, h.coupled_f, ctx=f"{geo.value} 75+")` on the
result. It does not exist as code yet, so this module EXPORTS the gate rather than inventing the
caller — which means the gate is inert until Task 29 wires it. Same shape
`living_arrangement._assert_coupled_direction` uses for the SOURCE-side version of this check
(different error class there on purpose: that one detects a source/junction transposition and
raises `LoaderError`; this one gates MODELLED counts and raises `CalibrationError`).

Per-band imbalance is a RECORDED DIAGNOSTIC, never a gate: probe P3 §4b measured live Census
breaching the retired band gate on 13 of 21 CORRECT rows — cross-age coupling (older men
partner younger; women outlive men) is real population structure, and min() matching plus
excess->Other is what absorbs it. `HouseholdInit.coupled_imbalance` is that record.
"""
import math
from dataclasses import dataclass

from demoflow.errors import CalibrationError

_SEXES = ("M", "F")

# Spec §5's 75+ AGGREGATE reversal bound — the ONLY 0.25 that survived steering ruling A.
# The SAME VALUE is defined independently at `living_arrangement.py:191` for the SOURCE-side
# check: no shared symbol, and not to be deduped by importing across the loader/cohort boundary.
# Changing this number is FORK-CLASS; `test_aggregate_direction_reversal_beyond_bound_raises`
# plus the exact-0.25 tolerance case pin it to [0.25, 0.26) so it cannot move silently.
_REVERSAL_BOUND = 0.25


@dataclass(frozen=True)
class HouseholdInit:
    """Household counts for one (geography, age-band, year) cell, plus the inputs and the
    diagnostic a caller needs to audit them.

    `total_*` are HOUSEHOLD counts (a Couple is one household holding two persons); `owner_*`
    are those counts times the maintainer-denominated ownership rate. `Other` carries NO owner
    field by design — spec §5 excludes persons living with others from the owner-unit stock as
    presumptive non-maintainers, and an `owner_other` field would invite exactly the addition
    the exclusion forbids.
    """

    total_couple: float
    total_solo_m: float
    total_solo_f: float
    total_other_m: float
    total_other_f: float
    owner_couple: float
    owner_solo_m: float
    owner_solo_f: float
    # Pre-match coupled PERSONS per sex, and the multiplicand they were computed on — recorded
    # so the aggregate direction gate has inputs and so the private-household claim is checkable.
    coupled_m: float
    coupled_f: float
    private_pop_m: float
    private_pop_f: float
    # |coupled_m − coupled_f| / max, or None at the zero-zero branch where spec §5 evaluates NO
    # RATIO. None rather than 0.0: 0.0 asserts "perfectly balanced", a different claim than
    # "undefined". RECORDED, NEVER GATED (steering ruling A).
    coupled_imbalance: float | None


def coupled_imbalance(coupled_m: float, coupled_f: float) -> float | None:
    """|Δ|/max, or None when both sides are zero (spec §5: no ratio evaluated)."""
    mx = max(coupled_m, coupled_f)
    if mx <= 0.0:
        return None
    return abs(coupled_m - coupled_f) / mx


def match_couples(coupled_m: float, coupled_f: float) -> tuple[float, float, float]:
    """Return (Couple, excess_m, excess_f). `Couple = min(coupled_m, coupled_f)`; the excess
    `max − min` routes to `Other`.

    MINIMUM, never an average (spec §5, codex r4-F1): averaging 100 vs 80 coupled persons emits
    90 couples when at most 80 matched pairs exist. The excess are real coupled persons whose
    partners fall outside the same-age band; routing them to Other keeps them excluded
    conservatively and preserves person conservation BY SEX exactly.

    NO BALANCE GATE. The 0.25 same-age band gate the plan body carried was retired by steering
    ruling A — its premise ("per-sex Census rates should nearly balance") was refuted by live
    Census, which breached it on 13/21 correct rows. Only `coupled_s >= 0` survives here.
    """
    for name, value in (("coupled_m", coupled_m), ("coupled_f", coupled_f)):
        if not math.isfinite(value):
            raise CalibrationError(f"{name} is non-finite ({value!r}) — coupled counts are persons")
        if value < 0.0:
            raise CalibrationError(
                f"{name} is negative ({value}) — spec §5 hard gate `coupled_s >= 0`; a negative "
                "coupled count means a living-alone or couple rate arrived outside [0,1]")
    couple = min(coupled_m, coupled_f)
    return couple, coupled_m - couple, coupled_f - couple


def assert_aggregate_coupled_direction(
    coupled_m: float, coupled_f: float, ctx: str = "75+ aggregate",
) -> None:
    """Spec §5's ONLY surviving direction gate, at the 75+ AGGREGATE: `coupled_m >= coupled_f`,
    with a reversal beyond |Δ|/max > 0.25 raising `CalibrationError` — that DIRECTION is
    invariant even though the per-band MAGNITUDE is not.

    Scope is the point: call this on 75+ aggregate counts, not per band. Ruling A's whole content
    is that a per-band magnitude gate is wrong, and a direction gate applied per band would be a
    different overreach in the same family. Correct direction never raises, at any magnitude.

    Measured headroom on the committed vintage (source-side counts, 2021 Census): every published
    Québec geography runs M > F at 75+ — MTL_RMR 86,445 vs 57,585; QC_RMR 19,790 vs 14,005;
    HORS_RMR 69,810 vs 47,395 — so a reversal this large means a Men/Women transposition or a
    rate junction defect, not a population that changed shape.
    """
    mx = max(coupled_m, coupled_f)
    if mx <= 0.0:            # zero-zero: no ratio evaluated
        return
    if coupled_f <= coupled_m:
        return
    imbalance = (coupled_f - coupled_m) / mx
    if imbalance > _REVERSAL_BOUND:
        raise CalibrationError(
            f"{ctx}: 75+ aggregate coupled-count direction reversed: coupled_F={coupled_f:,.4g} > "
            f"coupled_M={coupled_m:,.4g} by |Δ|/max={imbalance:.4f} > {_REVERSAL_BOUND} (spec §5). "
            "At 75+ the male coupled count exceeds the female one in every published Québec "
            "geography (older men partner younger; women outlive men) — a reversal this large is a "
            "sex junction or rate defect, not population structure.")


def initialize_households(
    pop_by_sex: dict[str, float],
    living_alone_rate_by_sex: dict[str, float],
    couple_share_by_sex: dict[str, float],
    collective_share: float,
    ownership_rate: float,
) -> HouseholdInit:
    """Partition private-household persons into Solo / Couple / Other and apply the ownership rate.

    `collective_share` comes off FIRST (see the module docstring's multiplicand note); the
    living-arrangement rates then apply to the private-household population they were denominated
    on. Removing the share twice undercounts; not removing it double-counts collective residents
    into the three buckets.
    """
    private_pop = {s: pop_by_sex.get(s, 0.0) * (1.0 - collective_share) for s in _SEXES}
    solo = {s: private_pop[s] * living_alone_rate_by_sex[s] for s in _SEXES}
    coupled = {s: private_pop[s] * (1.0 - living_alone_rate_by_sex[s]) * couple_share_by_sex[s]
               for s in _SEXES}
    other_base = {s: private_pop[s] * (1.0 - living_alone_rate_by_sex[s])
                  * (1.0 - couple_share_by_sex[s]) for s in _SEXES}

    # Hard gate 2 (spec §5): `coupled_s <= its sex pool`. Checked BEFORE match_couples so a rate
    # above 1 is named as an overflow rather than surfacing as whatever the matching does next.
    for s in _SEXES:
        if coupled[s] > private_pop[s] + 1e-9:
            raise CalibrationError(
                f"coupled_{s} ({coupled[s]}) exceeds its private-household sex pool "
                f"({private_pop[s]}) — spec §5 hard gate `coupled_s <= sex pool`; a coupled count "
                "above its own pool means a living-alone or couple rate arrived outside [0,1]")

    couple, excess_m, excess_f = match_couples(coupled["M"], coupled["F"])
    other_m = other_base["M"] + excess_m
    other_f = other_base["F"] + excess_f

    # Per-sex person conservation: `Solo_s + coupled_s + Other_s = private pop_s`. Explicit raise,
    # NOT `assert` (codex F7, Task 17's basis.py): `assert` is stripped under `python -O`, and a
    # conservation guard that vanishes in the mode a deployment might run is not a guard. Its
    # firing condition is a FORMULA EDIT, not a bad input — the identity is algebraic in the three
    # expressions above — which is exactly what makes it worth keeping: it is the tripwire under
    # any future change to one bucket that forgets the other two.
    for s in _SEXES:
        total = solo[s] + coupled[s] + other_base[s]
        if not math.isclose(total, private_pop[s], rel_tol=1e-9, abs_tol=1e-9):
            raise CalibrationError(
                f"person conservation broken for sex {s}: Solo({solo[s]}) + coupled({coupled[s]}) + "
                f"Other({other_base[s]}) = {total} != private pop {private_pop[s]}")

    return HouseholdInit(
        total_couple=couple, total_solo_m=solo["M"], total_solo_f=solo["F"],
        total_other_m=other_m, total_other_f=other_f,
        owner_couple=couple * ownership_rate,          # Other EXCLUDED from owner stock
        owner_solo_m=solo["M"] * ownership_rate,
        owner_solo_f=solo["F"] * ownership_rate,
        coupled_m=coupled["M"], coupled_f=coupled["F"],
        private_pop_m=private_pop["M"], private_pop_f=private_pop["F"],
        coupled_imbalance=coupled_imbalance(coupled["M"], coupled["F"]),
    )
