"""Demand side (spec §6) — the plan's Task-25 contract tests, plus the gates this task's
carries add.

WHAT IS PLAN-VERBATIM AND WHAT IS ADDED, so a reviewer never has to guess:

  * The seven functions between `# --- the plan's contract tests ---` and
    `# --- added gates ---` are the plan's Task-25 bodies, unchanged. (The plan's Step 4
    says "8 PASS" over a body that defines SEVEN tests — a counting typo in the plan, not a
    missing case; reported as a divergence rather than padded here.)

  * Everything below `# --- added gates ---` is added, and each one names the silent
    failure it kills. The theme is the same one `census.py` and `listings.py` already
    argue: a rate that is ABSENT must not read as a rate that is ZERO — the arithmetic
    stays plausible and the demand quietly shrinks (or, at the a−1 leg, quietly grows).

  * THE VINTAGE BLOCK IS GONE (round-3 elegance audit, 2026-08-22). The run-6 carry answered
    "a consumer must be able to state the vintage it holds" with `loaders/vintage.py` and a
    typed accessor per rate surface, tested here at the consumer boundary. Nothing outside
    `tests/` ever called one: spec §7's envelope is filled by `pipeline._source_hashes`, off
    the artifact BYTES and each artifact's own recorded `extracted_at`. The module and its
    three accessors are deleted; what survives is the leg the accessors shared with the rate
    loaders — every refusal cause lives on the shared read path, so a hollowed artifact cannot
    serve one caller while refusing another (`test_the_rate_loader_refuses_every_cause_on_the_
    SHARED_path` below).
"""
import json
from pathlib import Path

import pytest

from demoflow.demand import formation
from demoflow.demand.formation import (
    AGE_MIN,
    OWNERSHIP_LATTICE_FLOOR,
    immigrant_formation,
    immigrant_households,
    native_formation,
    p_imm,
    total_owner_demand,
)
from demoflow.errors import LoaderError
from demoflow.loaders import census
from demoflow.loaders.census import (
    HEADSHIP_ARTIFACT,
    OWNERSHIP_ARTIFACT,
    load_headship_rates,
    load_ownership_rates,
)
from demoflow.loaders.pins import DATA_DIR

from ._prose_binding import says


# --- the plan's contract tests (Task 25, verbatim) -----------------------------------

def test_native_formation_gross_under75_gain():
    # H_t(40)=1000*0.5=500; H_tm1(39)=900*0.5=450; gain=50; x ownership 0.6 => 30.
    d = native_formation(
        resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
        headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6},
    )
    assert d == pytest.approx(30.0)


def test_native_ignores_75plus_changes_disjoint_from_S():
    base = dict(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                headship_by_age={39: 0.5, 40: 0.5, 79: 0.5, 80: 0.5}, ownership_by_age={40: 0.6, 80: 0.6})
    d0 = native_formation(**base)
    # add a 75+ cohort DECLINE (80 falls vs 79): D must be UNCHANGED (75+ dynamics belong to S).
    d1 = native_formation(
        resident_pop_t={40: 1000.0, 80: 500.0}, resident_pop_tm1={39: 900.0, 79: 2000.0},
        headship_by_age=base["headship_by_age"], ownership_by_age=base["ownership_by_age"])
    assert d1 == pytest.approx(d0)


def test_native_floors_negative_gain_at_zero():
    d = native_formation(resident_pop_t={40: 800.0}, resident_pop_tm1={39: 1000.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6})
    assert d == 0.0


def test_dimensional_headship_50_couples_vs_100_singles_differ():
    # 100 arriving persons as 50 two-person households (headship 0.5) vs 100 one-person (1.0).
    d_couples = immigrant_formation(100.0, immigrant_headship_rate=0.5, p_nonimm=0.6, ratio=1.0)
    d_singles = immigrant_formation(100.0, immigrant_headship_rate=1.0, p_nonimm=0.6, ratio=1.0)
    assert d_couples == pytest.approx(30.0) and d_singles == pytest.approx(60.0)
    assert d_couples != d_singles          # identical D would be the units defect


def test_p_imm_is_product_asserted_in_unit_interval():
    assert p_imm(0.6, 0.62) == pytest.approx(0.372)
    assert p_imm(0.6, 1.2) == pytest.approx(0.72)   # ratio > 1 valid; product still in [0,1]
    with pytest.raises(LoaderError):
        p_imm(0.9, 1.3)                    # 1.17 outside [0,1] -> raise (product binds, not ratio)


def test_native_at_a_min_18_forms_against_zero_prior_no_wraparound():
    # codex r7-F7: at a_min=18 the prior stock is ZERO by equation (never H(17) via wraparound).
    # A huge planted 17-yo prior would leak in only through a negative-index bug -> assert it does NOT.
    d = native_formation(
        resident_pop_t={18: 100.0}, resident_pop_tm1={17: 9999.0},
        headship_by_age={17: 0.5, 18: 0.5}, ownership_by_age={18: 0.6},
    )
    assert d == pytest.approx(100.0 * 0.5 * 0.6)   # 30.0: H(18,t)=50, prior=0 -> gain 50 x 0.6


def test_total_demand_sums():
    assert total_owner_demand(native=30.0, immigrant=30.0) == pytest.approx(60.0)


# --- added gates ----------------------------------------------------------------------

def test_missing_ownership_where_a_gain_FORMS_raises_rather_than_deleting_the_demand():
    """A hole in the ownership curve must be LOUD, not a silently deleted term.

    `.get(a, 0.0)` (the plan body's read) turns a partially-built or holed curve into
    demand that is simply smaller — every intermediate number stays a plausible float and
    nothing downstream can notice. The gain at 40 below is real; the rate that multiplies
    it is absent from a curve that demonstrably HAS rates at that lattice height (50), so
    "undefined below the Census floor" cannot explain it.
    """
    with pytest.raises(LoaderError, match="ownership"):
        native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={50: 0.6})


def test_an_ownership_rate_that_multiplies_a_ZERO_gain_is_not_required():
    """The mirror of the gate above, and the reason it is scoped to forming ages.

    Production hands this function a 25..100 curve and a 19..74 sum, so most ages carry no
    gain in a given year; requiring a rate for a term that contributes nothing would red on
    perfectly good input. The requirement is exactly "a rate that multiplies a real gain".
    """
    d = native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6})
    assert d == pytest.approx(30.0)        # ages 25..74 other than 40 are absent and unneeded


@pytest.mark.parametrize("age", list(range(AGE_MIN, OWNERSHIP_LATTICE_FLOOR)))
def test_ownership_absent_BELOW_the_census_lattice_floor_contributes_nothing(age):
    """ALL SEVEN sub-floor ages under the REAL ownership lattice, as a measured fact.

    `census._AGE_BAND_SPEC` starts the ownership lattice at 25 (lowest band `25-34` since
    operator ruling W, 2026-08-20; `25-54` before it) and the pipeline builds its
    curve over `range(25, 101)` — so in every production run EVERY term of the spec §6
    summation at ages 18..24 multiplies an UNDEFINED rate and contributes zero, not merely the
    age-18 boundary term. UNDEFINED BY THAT SPEC, NOT BY THE TABLE (corrected 2026-08-15, spec
    §7 amendment #12): 98-10-0231-01 does publish owner-maintainer counts below 25, and
    `_HEADSHIP_MEMBER_SPEC` reads them — see
    `test_census_ownership.test_the_extract_DOES_publish_owner_maintainer_counts_below_25`.
    The convention is census.py's own `zero_support_note`, landed at T13b 2026-08-08 and
    mirrored in `formation`: ownership(a) "contributes nothing below 25", by a choice the note
    now attributes to `_AGE_BAND_SPEC`.

    Parametrized over all seven rather than pinned at a_min because the convention and the
    silence it buys are identical at each, and a test that pins only 18 leaves 19..24 free to
    change under it. The a_min term still earns its place independently: it exists to stop
    entrants forming against H(17) by array wraparound (codex r7-F7), not to claim 18-year-old
    buyers. The second arm pins that a rate which IS supplied at a sub-floor age is still USED,
    so the convention can never swallow a curve someone extended downward.
    """
    headship_by_age = {a: 0.5 for a in range(AGE_MIN - 1, OWNERSHIP_LATTICE_FLOOR + 1)}
    # a_min forms against a zero prior BY EQUATION; 19..24 need a real prior cohort to gain on.
    supplied = dict(resident_pop_t={age: 1000.0},
                    resident_pop_tm1={} if age == AGE_MIN else {age - 1: 800.0},
                    headship_by_age=headship_by_age)
    gain = 500.0 if age == AGE_MIN else 100.0          # 1000×0.5, or 1000×0.5 − 800×0.5

    assert native_formation(**supplied, ownership_by_age={40: 0.6}) == 0.0
    assert native_formation(**supplied, ownership_by_age={age: 0.55}) == pytest.approx(
        gain * 0.55)


def test_the_floor_is_a_hard_numeric_edge_at_24_vs_25_ON_THE_FORMATION_LEG():
    """The FORMATION-side twin of `test_owner_stock.py::test_the_floor_is_a_hard_numeric_edge_
    at_24_vs_25` — adjacent ages, identical shapes, 24 is silence and 25 is a hole.

    IT EXISTS BECAUSE THE TWO LEGS WERE NOT SYMMETRICALLY GUARDED, measured at the round-3 audit
    (2026-08-22): mutating `formation._ownership`'s `if age < OWNERSHIP_LATTICE_FLOOR:` to `<=`
    SURVIVED the full 1190-green suite, while the identical mutation on the twin at
    `balance/owner_stock.py` is KILLED by that test. The root cause is coverage geometry, not
    arithmetic: the parametrized test above ranges 18..24, ALL of them below the floor, and this
    module's absent-rate refusal is exercised at age 40 — so nothing in the suite put 24 and 25
    side by side on this leg.

    IT IS INERT TODAY AND THAT IS NOT A REASON TO SKIP IT. `pipeline._ed_series` materializes
    `ownership = {a: ... for a in range(25, 101)}`, so age 25 always HAS a rate in production and
    the mutated guard never reaches its `return 0.0`. Under a HOLED curve it does: the mutant
    returns 0.0 at 25 and silently DELETES demand at the lattice's lowest band — the exact
    direction `_ownership`'s own docstring names ("a rate absent where a real gain forms would
    delete that demand silently"), at the one age where "undefined below the floor" is false.
    """
    below = dict(resident_pop_t={24: 1000.0}, resident_pop_tm1={23: 800.0},
                 headship_by_age={23: 0.5, 24: 0.5}, ownership_by_age={})
    at = dict(resident_pop_t={25: 1000.0}, resident_pop_tm1={24: 800.0},
              headship_by_age={24: 0.5, 25: 0.5}, ownership_by_age={})

    # NON-VACUITY: both legs carry a POSITIVE gain, so both really do read the ownership curve.
    # A zero gain would make the `at` leg pass for the wrong reason (see
    # `test_an_ownership_rate_that_multiplies_a_ZERO_gain_is_not_required`).
    assert native_formation(**{**below, "ownership_by_age": {24: 0.55}}) == pytest.approx(55.0)
    assert native_formation(**{**at, "ownership_by_age": {25: 0.55}}) == pytest.approx(55.0)

    assert native_formation(**below) == 0.0
    with pytest.raises(LoaderError, match="ownership"):
        native_formation(**at)


def test_the_ownership_floor_matches_the_census_loaders_own_lattice():
    """Two modules, one lattice floor, asserted rather than imported.

    The repo's own precedent (`living_arrangement._QC_CMAS` vs `census._QC_CMAS`, whose
    equality is a TEST and not an import) applied here: `formation` stays pure arithmetic
    over dicts and does not import the Census band table, so the number it uses for
    "undefined below here" is pinned against the table that defines it.
    """
    assert OWNERSHIP_LATTICE_FLOOR == min(lo for _label, lo, _hi in census._AGE_BANDS)


@pytest.mark.parametrize("headship_by_age,leg", [
    ({39: 0.5}, "a"),          # the CURRENT-year rate is missing  -> gain understated
    ({40: 0.5}, "a-1"),        # the PRIOR-year rate is missing    -> gain OVERstated
])
def test_missing_headship_at_an_age_the_equation_READS_raises(headship_by_age, leg):
    """Missing ≠ zero on both legs, and the a−1 leg is the sharper one.

    A missing rate at `a` zeroes H(a,t) and shrinks the gain — bad but conservative. A
    missing rate at `a−1` zeroes the PRIOR stock, so the whole cohort reads as newly formed
    and demand is INFLATED. Both are invisible in the output. The guard fires only at ages
    the equation actually reads with a nonzero population, so the planted 17-year-old of the
    wraparound test above still never needs a rate.
    """
    with pytest.raises(LoaderError, match="headship"):
        native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                         headship_by_age=headship_by_age, ownership_by_age={40: 0.6})
    assert leg in ("a", "a-1")


def test_an_absent_prior_year_cohort_raises_rather_than_INFLATING_the_formation():
    """MISSING IS NOT ZERO through the POPULATION door too — the twin of the guard above.

    The rate guard closes only half of this failure. An absent prior-year cohort zeroes the
    stock the gain is measured against just as effectively as an absent prior-year RATE does,
    and in the same inflating direction: a whole standing cohort reads as newly formed.
    Measured on the fixture below, the same call returns 30.0 with the prior year present and
    300.0 without it — a 10× overstatement in which every intermediate value stays a plausible
    float. The live door is real: the pipeline sketch builds `resident_tm1` from the projection
    frame at `t-1`, which yields `{}` for any year the frame does not carry.

    PRESENT-BUT-ZERO is accepted and must stay accepted — that is a stated empty cohort, not a
    hole — which is exactly the distinction `.get(age, 0.0)` cannot make.
    """
    dense = dict(headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6})
    assert native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                            **dense) == pytest.approx(30.0)

    for prior in ({}, {38: 900.0}):        # frame wholly absent, and a hole at the read age
        with pytest.raises(LoaderError, match="year t-1 population"):
            native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1=prior,
                             headship_by_age={38: 0.5, 39: 0.5, 40: 0.5},
                             ownership_by_age={40: 0.6})

    assert native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 0.0},
                            **dense) == pytest.approx(300.0)


def test_out_of_unit_rates_in_a_hand_built_curve_raise():
    """A curve assembled by hand (fixtures, sweeps, a future caller) is not loader-checked.

    `headship_rate` / `ownership_rate` assert [0,1] when the curve comes from the loaders,
    but `native_formation` takes plain dicts and a >1 rate would silently manufacture
    demand, so the read sites assert too. The fixtures carry a real prior-year cohort so the
    rate assertion is what fires, not the prior-cohort guard above.
    """
    with pytest.raises(LoaderError, match="fraction|headship"):
        native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                         headship_by_age={39: 0.5, 40: 1.4}, ownership_by_age={40: 0.6})
    with pytest.raises(LoaderError, match="fraction|ownership"):
        native_formation(resident_pop_t={40: 1000.0}, resident_pop_tm1={39: 900.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 1.4})


def test_a_non_finite_population_raises_instead_of_vanishing_from_the_sum():
    """NaN must not be swallowed by the sign rule.

    `max(0, gain)` — and the `gain > 0` form of it — silently DROPS a NaN term, because every
    ordering against NaN is False (the property `cohort/decrements` leans on). Spec §7's
    emitter refuses non-finite output, but only for a NaN that survives to it; one erased here
    just makes the demand smaller. The upstream loaders assert finite populations, which is
    why this is a backstop rather than the primary gate — and backstops that cost two lines
    are worth having where the failure is invisible.
    """
    with pytest.raises(LoaderError, match="not finite"):
        native_formation(resident_pop_t={40: float("nan")}, resident_pop_tm1={39: 900.0},
                         headship_by_age={39: 0.5, 40: 0.5}, ownership_by_age={40: 0.6})


def test_immigrant_households_is_persons_times_households_per_person():
    """The dimensional step on its own (the plan pins it only through `immigrant_formation`)."""
    assert immigrant_households(100.0, 0.5) == pytest.approx(50.0)
    assert immigrant_households(0.0, 0.5) == 0.0        # a stated empty flow is a datum


@pytest.mark.parametrize("arrivals, match", [
    (-100.0, "negative"),
    (float("nan"), "non-finite"),
    (float("inf"), "non-finite"),
])
def test_a_negative_or_non_finite_ARRIVAL_COUNT_is_a_defect_not_a_datum(arrivals, match):
    """The immigrant leg asserted NOTHING: `immigrant_households(-100, 0.5)` returned -50.0
    and a NaN propagated to the emitter, while the NATIVE leg on the same page refuses both.
    Arrivals are a gross INFLOW — the §4 signed-flow carve-out (natural increase, net
    migration) does not reach them, so the stock/rate rule binds: nonneg and finite.

    A negative arrival count would SUBTRACT owner demand, which no equation in §6 produces;
    a NaN would be dropped or serialized, depending on which downstream form it met first."""
    with pytest.raises(LoaderError, match=match):
        immigrant_households(arrivals, 0.5)
    with pytest.raises(LoaderError, match=match):
        immigrant_formation(arrivals, immigrant_headship_rate=0.5, p_nonimm=0.6, ratio=1.0)


@pytest.mark.parametrize("rate", [1.4, -0.1, float("nan")])
def test_an_out_of_unit_immigrant_headship_RATE_raises(rate):
    """Headship is a FRACTION (§4's [0,1] rule lists it by name). The join table already
    refuses a bad table value at import; this closes the arithmetic door a caller could pass
    one through — the same both-doors treatment `native_formation` got."""
    with pytest.raises(LoaderError):
        immigrant_households(100.0, rate)


@pytest.mark.parametrize("p_nonimm,ratio,match", [
    (-0.5, -0.5, "p_nonimm"),                    # THE PAIR — the measured gap (see below)
    (-0.6, 0.0, "p_nonimm"),                     # negative × 0.0 partner: product -0.0, ESCAPED
    (0.0, -0.6, "immigrant_ownership_ratio"),    # the same escape, mirrored onto the ratio leg
    (0.6, -0.5, "immigrant_ownership_ratio"),    # single negative on the ratio leg
    (float("nan"), 0.5, "p_nonimm"),
    (0.6, float("inf"), "immigrant_ownership_ratio"),
    (1.4, 0.5, "p_nonimm"),                      # a fraction out of [0,1] before any product
])
def test_p_imm_asserts_BOTH_OPERANDS_because_a_NEGATIVE_PAIR_survives_the_product(
        p_nonimm, ratio, match):
    """The run-21 review's carry, measured before the fix: `p_imm(-0.5, -0.5)` returned 0.25
    and `immigrant_formation(100.0, 0.5, p_nonimm=-0.5, ratio=-0.5)` returned 12.5, neither
    raising. Two negatives multiply into a perfectly valid-looking propensity, so the
    docstring's claim that "a negative or non-finite input cannot pass the product's own [0,1]
    assertion" was FALSE for the pair.

    IT WAS FALSE MORE WIDELY THAN THAT CARRY RECORDED, and cases 2-3 are the correction
    (run-24 review; re-measured against the verbatim old body). A SINGLE negative escaped too
    whenever its partner was 0.0 — the product is -0.0 and `0.0 <= -0.0 <= 1.0` holds — on
    EITHER leg, which is why the mirrored case is here rather than left as a symmetry someone
    assumes. The split, so no case is misread as one that already raised: cases 1-3 and 7 were
    let STRAIGHT THROUGH by the old body (0.25, -0.0, -0.0, 0.7); cases 4-6 did raise, on the
    product's message, and for those the fix changes nothing but WHICH quantity is named. Every
    non-finite input raised pre-fix (nan × 0 is nan), which is what puts 5-6 in that group.

    NOT a live bug — the wired path feeds `p_nonimm` from fraction-asserted ownership rates and
    `ratio` from the nonneg-asserted join table, and Task 29 is what wires it at all. It is a
    defensive-guard gap plus a false sentence, closed together: each operand is asserted in its
    OWN units before the product (r7-F8: the ratio is nonneg-finite and may validly exceed 1;
    only the product binds [0,1]), and the docstring now says what the code does.
    """
    with pytest.raises(LoaderError, match=match):
        p_imm(p_nonimm, ratio)
    with pytest.raises(LoaderError, match=match):
        immigrant_formation(100.0, immigrant_headship_rate=0.5,
                            p_nonimm=p_nonimm, ratio=ratio)


def test_the_p_imm_docstring_no_longer_claims_the_product_alone_catches_a_negative():
    """The false sentence itself, pinned gone — a guard added while the prose that motivated
    its absence survives is how the next reader concludes the guard is redundant."""
    text = Path(formation.__file__).read_text(encoding="utf-8")
    # `says` (run 48): this reads RAW source, so the forbidden sentence is evaded by BOTH a
    # capitalisation and a hard wrap — and the required legs below already say why short
    # unbroken fragments are used on the positive side. The forbid needs the same protection.
    assert not says(text, "cannot pass the product's own")
    # Short unbroken fragments only: a longer phrase spans a line wrap and would red on a
    # reflow rather than on the claim (the coupling `test_i2.py` makes on DIGITS, not prose).
    assert "exceed 1" in text and "codex r7-F8" in text, (
        "the r7-F8 ratio carve-out — the ratio may validly exceed 1, only the PRODUCT binds "
        "[0,1] — must SURVIVE the narrowing; asserting each operand must not have quietly "
        "turned the ratio into a fraction")


def test_the_i2_forward_reference_caveat_is_GONE_now_that_25b_HAS_LANDED():
    """The caveat said P_resident's per-cell guard was "a FORWARD REFERENCE, not a live
    guard: as of 2026-08-14 `demand/i2.py` does not exist ... When 25b lands, this
    parenthetical becomes plain fact and this caveat gets deleted." 25b landing is exactly
    what makes the sentence true, so the stale half must go — while the honest half stays:
    nothing CALLS the guard until Task 29 wires the pipeline, and the docstring must not
    claim production coverage it does not have."""
    from demoflow.demand import i2                     # the module the caveat said was absent

    text = Path(formation.__file__).read_text(encoding="utf-8")
    assert not says(text, "does not exist")
    assert not says(text, "this caveat gets deleted")
    assert "demand/i2.py" in text, "the pointer to WHERE the guard lives must survive"
    assert callable(i2.assert_p_resident_nonneg)


def test_native_formation_has_no_import_path_to_the_population_loader():
    """Operand binding, spec §6 (codex r6-F1) — the half that is checkable HERE.

    Native formation's ONLY population parameter is P_resident "by construction (single code
    path, no access to P_ISQ)". The behavioural half of that binding is a PIPELINE mutation
    (Task 25b/29: feeding P_ISQ changes the emitted number). What this level can assert is
    the structural half: the module cannot reach the ISQ population loader at all, so no
    future edit can quietly read total population from inside the demand equation.
    """
    text = Path(formation.__file__).read_text(encoding="utf-8")
    assert "loaders.isq" not in text and "load_population" not in text, (
        "demand.formation reached the ISQ population loader — spec §6 binds its population "
        "operand to P_resident with no code path to P_ISQ")


# --- the SHARED read path: a refusal must be TOTAL ---------------------------------------
#
# THE VINTAGE ACCESSORS THIS BLOCK USED TO TEST ARE DELETED (see the module docstring). What
# survives is the property they were the second half of: every refusal cause lives on the
# artifact's SHARED read+verify path, so a hollowed artifact cannot be refused by one caller
# and served to another. Measured 2026-08-14 with the strict join sitting inside the rate
# accessor: three of these four causes served the second caller a confident answer.

@pytest.mark.parametrize("artifact,mutate,rate_loader,match", [
    (OWNERSHIP_ARTIFACT, lambda p: p["_provenance"].__setitem__("sha256", "0" * 64),
     load_ownership_rates, "STALE"),
    (OWNERSHIP_ARTIFACT, lambda p: p["rates"].pop(sorted(p["rates"])[0]),
     load_ownership_rates, "strict join"),
    (OWNERSHIP_ARTIFACT, lambda p: p.pop("rates"),
     load_ownership_rates, "strict join"),
    # Since ruling V the headship curve is age-resolved and carried at TWO shapes, so the
    # strict join has two ways to be holed: a dropped AGE inside a carried shape, and a
    # dropped SHAPE the robustness sweep declares. The second is the one a headline-only
    # completeness check would miss, because the headline reads the central arm and the sweep
    # leg reads the other.
    # `shape` is REQUIRED on the headship loader (the retired `shape=None` default was a
    # second, unhashed selection site), so the leg states the central arm explicitly. Both
    # mutations must refuse BEFORE the shape is looked up — that is the point of the shared path.
    (HEADSHIP_ARTIFACT, lambda p: p["headship"]["expo_cum_fc"].pop("70"),
     lambda data_dir: load_headship_rates(data_dir=data_dir,
                                          shape=census.HEADSHIP_CENTRAL_SHAPE), "strict join"),
    (HEADSHIP_ARTIFACT, lambda p: p["headship"].pop("expo_cum_fb"),
     lambda data_dir: load_headship_rates(data_dir=data_dir,
                                          shape=census.HEADSHIP_CENTRAL_SHAPE), "strict join"),
], ids=["stale-digest", "dropped-geography", "dropped-rates-key", "dropped-headship-age",
        "dropped-headship-shape"])
def test_the_rate_loader_refuses_every_cause_on_the_SHARED_path(
        tmp_path, artifact, mutate, rate_loader, match):
    """Each refusal CAUSE is reached through the accessor, and the causes straddle the shared
    helper's two stages — digest verification, then the strict join — because that boundary is
    where the legs came apart when a second accessor existed."""
    payload = json.loads((DATA_DIR / artifact).read_text(encoding="utf-8"))
    mutate(payload)
    (tmp_path / artifact).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match=match):
        rate_loader(data_dir=tmp_path)
