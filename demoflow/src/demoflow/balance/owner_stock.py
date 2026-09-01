"""OwnerStock — the ED DENOMINATOR's ONE defining equation (spec §7, codex r3-F3).

    OwnerStock(g,t,s) = Σ_over_all_ages pop(a,g,t,s) × headship(a) × ownership(a)

Annual re-estimation from ISQ scenario population with BASE-YEAR Census headship and ownership
rates held constant (PIT-fixed, a labeled assumption). This is a stock LEVEL estimate: the
ISQ-embedded mortality inside `pop(a,g,t,s)` is CORRECT here and does not conflict with I1,
which governs the 75+ exit FLOW model only. No carried-forward under-75 stock exists — the
denominator has exactly one defining equation, and this is it.

THE SUM RUNS OVER ALL AGES, 75+ INCLUDED. The neighbouring equation says the opposite:
`demand/formation.py` stops at 75 by design (D/S disjointness at the age boundary — every 75+
household dynamic lives in S). Carrying that rule one module over would truncate the
denominator and scale every |ED| away from zero, so it is stated here rather than left to be
inferred.

MULTIPLICAND, STATED AT THE USE SITE (run-6 carry — the rate surfaces in this tree take
different operands and every mix-up is invisible in the numbers): `pop_by_age` is the RAW ISQ
scenario population — P_ISQ, collective/institutional residents INCLUDED — and NOT §6's
P_resident. `headship_by_age`'s denominator is the ISQ published population by single year of
age (`census.derive_headship_from_sources`, and the artifact's own `multiplicand_note`), so the
raw basis is the one that reproduces the published maintainer count. The Task-29 pipeline
sketch passes `_pop_by_age(pop_g_s, t)` HERE and the scaled `resident_t` to
`native_formation` — that difference is deliberate: netting surviving arrival cohorts out of
this denominator would shrink the stock and scale |ED| away from zero, while §6's operand
binding (P_resident, never P_ISQ) governs the FORMATION equation alone.

MISSING IS NOT ZERO, AND HERE IT MOVES THE RANKED AXIS IN BOTH REGIMES. The plan body read both
rate curves with `.get(a, 0.0)`. `demand/formation.py` already resolved that for the SAME two
curves on the demand side, where a hole quietly SHRINKS demand; this is the DENOMINATOR, so a
hole quietly shrinks the stock and SCALES |ED| AWAY FROM ZERO, with every intermediate value
still a plausible float. State the direction that way and not as "optimistic" (corrected
2026-08-15): a shrunken denominator multiplies whatever sign ED already has, so it reads as more
excess demand when ED > 0 and as a DEEPER DEFICIT when ED < 0 — and since rank 1 is most-negative
ED, the decline regime this model exists to measure is moved toward MORE risk, not less.
"Optimistic" describes only the ED > 0 half of the ranked set. Both curves therefore raise,
scoped to terms that actually contribute, each accepting a stated ZERO while refusing an
ABSENCE. The one documented exception is the Census ownership lattice's floor, which is a CHOICE
landed upstream in `census._AGE_BAND_SPEC` (see `OWNERSHIP_LATTICE_FLOOR`) rather than the data's
silence — and whose OWN direction is a different question, priced on both sides of ED at that
constant and NOT by the sentence above.

THE FLOOR IS IMPORTED, NOT REDECLARED. `formation.py` duplicates the number instead of
importing it for a stated reason — keeping the demand package free of the Census BAND TABLE,
the same discipline as `living_arrangement._QC_CMAS` vs `census._QC_CMAS` — and that reason
does not extend here: balance→demand is model→model, in the direction this package already
consumes (ED's numerator IS `formation`'s D), so the import costs no loaders coupling and
closes no cycle. A third literal would be three drift sites held together by pairwise pins;
one import plus `formation`'s existing pin against `census._AGE_BANDS` is one chain, and
`tests/test_owner_stock.py` asserts that chain end to end.

THE PRODUCTION CALLER IS `pipeline._ed_series`, which evaluates this equation once per (leg,
geography, scenario, projected year) — 14 x 8 x 3 x 26 = 8,736 calls per run on the declared
seven-axis grid, measured 2026-08-22. The factorization is written out rather than the product
alone because the product is what goes stale: this module's grid has widened twice, and a
sentence carrying only the product would have to be re-derived by hand each time.

WHAT THAT DOES AND DOES NOT MAKE OBSERVED, because the sentence this replaced ("stated
contracts, not observed production behaviour") was read by a reviewer as licence not to check
whether the guards are REACHED — and every evaluation of ED's DENOMINATOR goes through them.
Measured over one declared run: `_headship` and `_ownership` are each entered 882,336 times
(8,736 x the 101 ages the population lattice carries) and NEITHER refusal branch is reached
once, because the committed curves carry a rate at every populated age. What IS observed
production behaviour is the rest of both guards: `_ownership`'s sub-floor `return 0.0` fires
218,400 times (8,736 x the 25 ages below `OWNERSHIP_LATTICE_FLOOR`), and the two
`assert_fraction` unit checks run on every one of the 882,336 (8,736 x the 101 ages) headship and
663,936 (8,736 x the 76 ages at or above that floor) ownership rate reads — the headship figure
carries its factorization here too, because a bare restatement is a stale product waiting for the
next grid widening and `tests/test_pipeline.py`'s occurrence census now refuses one. So the REFUSALS are contracts whose violation
path only `tests/test_owner_stock.py` reaches; the unit assertions and the sub-floor convention
are exercised by the run itself.
"""
from demoflow.demand.formation import OWNERSHIP_LATTICE_FLOOR
from demoflow.errors import LoaderError
from demoflow.loaders.validate import assert_fraction, assert_nonneg_finite


def _headship(headship_by_age: dict[int, float], age: int, persons: float) -> float:
    """headship(age) at an age carrying population. ABSENT is a hole at EVERY age.

    Unlike ownership, headship has no undefined region to point at: since operator ruling V the
    committed curve is AGE-RESOLVED at every single year 0-100 (`census._HEADSHIP_MEMBER_SPEC`
    graduated onto the ISQ single-year denominator) and the pipeline materialises it over
    `range(0, 101)`, so a missing rate can only mean a holed or partially-built curve.

    THE REACH AT SUB-FLOOR AGES COMES FROM THE CALL BEING UNCONDITIONAL, not from where it
    sits in the loop: `owner_stock` asks for headship at EVERY populated age, and `_ownership`
    RETURNS 0.0 sub-floor rather than skipping the term, so it can never bypass this check.
    That is the deliberate refusal of the "the term is zero anyway, so don't ask" reading,
    which would make this guard's reach depend on the OTHER curve's silence. Swapping the two
    calls changes nothing about which inputs raise (measured on a swapped replica, run 23);
    see `owner_stock` for the one thing the order does decide.
    """
    if age not in headship_by_age:
        raise LoaderError(
            f"no headship rate for age {age}, where {persons:,.1f} persons are present — an "
            "absent rate is not a zero rate: the committed curve is age-resolved over 0..100 "
            "and has no undefined region, so this is a holed curve, and it would silently shrink "
            "the ED DENOMINATOR, scaling |ED| AWAY FROM ZERO — more excess demand where ED > 0, "
            "a DEEPER DEFICIT where ED < 0, the half rank 1 selects")
    return assert_fraction(f"headship[{age}]", headship_by_age[age])


def _ownership(ownership_by_age: dict[int, float], age: int, persons: float) -> float:
    """ownership(age) at an age carrying population — the one place a silence is legitimate.

    The rate is UNDEFINED below 25 and the term contributes nothing. THE SILENCE IS THE
    DERIVATION SPEC'S, NOT THE TABLE'S (corrected 2026-08-15, spec §7 amendment #12): the
    committed extract PUBLISHES owner-maintainer counts below 25 — Québec `20 to 24 years` is
    17,170 owners of 106,605 households, at all seven of its GEO rows — and `census.py` reads
    those same members for HEADSHIP while `census._AGE_BAND_SPEC` starts the ownership lattice
    at 25 — its lowest band is `25-34` since operator ruling W (2026-08-20), `25-54` before it;
    the FLOOR is 25 either way and ruling W did not move it. So the convention is a CHOICE
    upstream of this module, recorded in `census.py`'s
    `zero_support_note` (T13b 2026-08-08, re-attributed at amendment #12), which names THIS
    equation as its consumer — "spec:395 sums pop(a) x headship(a) x ownership(a) over ages ...
    every consumer today pairs it with ownership(a), which contributes nothing below 25". The
    choice STANDS, on the ordering constraint stated at `OWNERSHIP_LATTICE_FLOOR`, which is also
    where its cost on BOTH sides of ED is priced — the effect is NOT "optimistic": for ED < 0
    both legs push pessimistic. A supplied sub-floor rate is still USED, so an extended curve is
    never swallowed by the convention — and still ASSERTED: the check below runs on whatever
    rate it is handed, at any age. The convention therefore excuses an ABSENCE and never a bad
    value, which is why a sub-floor age can be defective on BOTH curves at once (see
    `owner_stock`'s note on what the call order decides).
    """
    if age in ownership_by_age:
        return assert_fraction(f"ownership[{age}]", ownership_by_age[age])
    if age < OWNERSHIP_LATTICE_FLOOR:
        return 0.0          # undefined below the Census lattice — the documented convention
    raise LoaderError(
        f"no ownership rate for age {age}, where {persons:,.1f} persons are present — the age "
        f"is at or above the Census lattice floor ({OWNERSHIP_LATTICE_FLOOR}), so 'undefined "
        "below the floor' does not explain it; the curve is holed and the ED DENOMINATOR "
        "would silently shrink, scaling |ED| AWAY FROM ZERO — more excess demand where ED > 0, "
        "a DEEPER DEFICIT where ED < 0, the half rank 1 selects")


def owner_stock(pop_by_age: dict[int, float], headship_by_age: dict[int, float],
                ownership_by_age: dict[int, float]) -> float:
    """The §7 defining equation, evaluated over whatever ages the population dict carries.

    INPUT CONTRACT (it RAISES, so a caller should read it here): every age with a NONZERO
    population must carry a headship rate, and an ownership rate unless it is below
    `OWNERSHIP_LATTICE_FLOOR`; both rates are asserted in [0,1]; population cells are asserted
    nonneg-finite. A rate of 0.0 satisfies this — an ABSENT rate does not.

    Where the population is ZERO the term is zero whatever the rates are, so no rate is
    demanded (the carve-out `formation._households` already makes: an empty cell at the top of
    the lattice is a legitimate reading, not a hole). An age simply ABSENT from `pop_by_age`
    likewise contributes nothing and needs nothing — unlike `formation`'s a−1 leg, nothing is
    measured against a prior stock here, so absence carries no direction.

    POPULATION CELLS ARE ASSERTED NONNEG-FINITE, which diverges from `formation`'s "P_resident
    ≥ 0 is assigned upstream" stance, deliberately and for a positional reason. NaN does not
    vanish from this sum the way it can from a gain comparison — it propagates to a NaN
    OwnerStock, and `NaN < MIN_OWNER_STOCK` is False, so the r9-F5 denominator guard passes it
    through and a NaN ED reaches the emitter. A negative cell shrinks the denominator and so
    scales |ED| — the ranked quantity — away from zero, deepening the deficit in exactly the
    ED < 0 regime rank 1 selects; `validate.assert_nonneg_finite` names stocks in its own
    docstring, and ISQ populations are already refused negative at load — this refuses one
    arriving by any other door.
    """
    total = 0.0
    for age, population in pop_by_age.items():
        persons = assert_nonneg_finite(f"population[{age}]", population)
        if persons == 0.0:
            continue
        # BOTH calls are unconditional at a populated age, and THAT — not their order — is
        # what gives each guard its reach: `_ownership` returns 0.0 sub-floor rather than
        # skipping the term, so it can never bypass `_headship`. The order decides exactly one
        # thing: WHICH of the two messages surfaces whenever both guards would independently
        # raise at the SAME populated age (measured run 24 on a swapped replica — the raising
        # SET is order-invariant, only the message moves). That set is NOT confined to ages at
        # or above the floor, which is what the run-23 sentence here got wrong: sub-floor an
        # ABSENT ownership rate is the convention and no defect, but a PRESENT out-of-unit one
        # is asserted at every age, so it collides with a holed headship at 10 exactly as at
        # 40. Headship goes first because it is the curve with no legitimate excuse at any age;
        # both arms pinned in `test_owner_stock.py`.
        headship = _headship(headship_by_age, age, persons)
        ownership = _ownership(ownership_by_age, age, persons)
        total += persons * headship * ownership
    return total
