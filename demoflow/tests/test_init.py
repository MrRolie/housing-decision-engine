"""Persons->households initialization (spec §5 AS AMENDED by the steering-ruling-A balance-gate amendment, 2026-07-25).

THREE DIVERGENCES FROM THE PLAN'S TASK-18 BODY, all forced by ruling A (which post-dates the
plan text) or by this tranche's own codex-F7 precedent, all reported:

  1. **The 0.25 SAME-AGE band gate does not exist.** The plan's
     `test_match_couples_20_v_100_balance_breach_raises` asserts `CalibrationError`; spec §5 as
     amended retired that gate outright (probe P3 §4b: live Census breached it on 13/21 CORRECT
     rows — cross-age coupling is real population structure, not a calibration defect). The test
     is INVERTED here: same inputs, no raise, and the imbalance is RECORDED on the result. That
     inversion is the load-bearing regression — it is the one test that reds if the retired gate
     is ever reinstated.
  2. **The plan's `test_female_surplus_..._balances` premise is the retired one.** Its comment
     ("correctly-calibrated per-sex couple_share keeps coupled counts balanced") is exactly the
     "calibrate per-sex so coupled_m ≈ coupled_f" instruction ruling A killed — couple_share stays
     EXACTLY as cited. Replaced by
     `test_cited_rates_on_real_isq_pops_pass_direction_gate_despite_large_band_imbalance`, which
     runs the COMMITTED cited rates against the COMMITTED ISQ populations through both real
     loaders: the band imbalance is large (0.45 — the retired gate would have fired) and the
     surviving direction gate passes with measured headroom.
  3. **Person conservation is an explicit raise, not a bare `assert`.** Codex F7 + Task 17's
     `basis.py`: `assert` is stripped under `python -O`, so a conservation guard written as one
     is a check that cannot fail in the mode a deployment might actually run.
"""
import pytest

from demoflow.cohort.init import (
    HouseholdInit,
    assert_aggregate_coupled_direction,
    initialize_households,
    match_couples,
)
from demoflow.errors import CalibrationError
from demoflow.geography import Geography, Scenario
from demoflow.loaders.isq import load_population
from demoflow.loaders.living_arrangement import couple_share, living_alone_rate, load_living_arrangement


def _sex(v):  # convenience: same value for M and F
    return {"M": v, "F": v}


# --- min matching (spec §5: MINIMUM, never an average) ---------------------------------

def test_match_couples_100_v_80_min_and_excess_to_other():
    # 100 vs 80 coupled -> exactly 80 Couple + 20 excess (never 90 averaged).
    couple, excess_m, excess_f = match_couples(100.0, 80.0)
    assert couple == 80.0 and excess_m == 20.0 and excess_f == 0.0
    # spec §5 post-match conservation: `min + excess = coupled_larger`, per sex.
    assert couple + excess_m == 100.0
    assert couple + excess_f == 80.0


def test_match_couples_20_v_100_per_band_imbalance_is_recorded_not_gated():
    """RULING-A REGRESSION. The plan asserted `CalibrationError` here (|80|/100 = 0.8 > 0.25).
    Spec §5 as amended RETIRED that gate: per-band imbalance under the same-age approximation is
    expected, and min() matching + excess->Other is what absorbs it. Reinstating the gate reds
    this test."""
    couple, excess_m, excess_f = match_couples(20.0, 100.0)
    assert couple == 20.0 and excess_m == 0.0 and excess_f == 80.0
    assert couple + excess_f == 100.0   # nothing fabricated, nothing dropped


def test_match_couples_zero_zero_no_ratio_no_error():
    couple, em, ef = match_couples(0.0, 0.0)
    assert couple == 0.0 and em == 0.0 and ef == 0.0


def test_match_couples_negative_coupled_raises():
    """Surviving hard gate 1 (spec §5): `coupled_s >= 0`."""
    with pytest.raises(CalibrationError, match="negative"):
        match_couples(10.0, -1.0)


# --- three-bucket initialization (spec §10 fixtures a/b) -------------------------------

def test_all_coupled_100_100_60pct_ownership():
    # §10 fixture (a): 100 M + 100 F all coupled, 60% ownership -> 60 Couple, 0 Solo, 0 Other.
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.0), couple_share_by_sex=_sex(1.0),
        collective_share=0.0, ownership_rate=0.60,
    )
    assert isinstance(h, HouseholdInit)
    assert h.owner_couple == 60.0
    assert h.total_couple == 100.0
    assert h.total_solo_m == 0.0 and h.total_solo_f == 0.0
    assert h.total_other_m == 0.0 and h.total_other_f == 0.0


def test_general_case_three_buckets_and_person_conservation():
    # §10 fixture (b): 200 persons (100 M + 100 F), living_alone 0.25, couple_share 0.80
    # -> 50 Solo + 60 Couple + 30 Other; persons reconcile 50 + 120 + 30 = 200.
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.25), couple_share_by_sex=_sex(0.80),
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.total_solo_m + h.total_solo_f == pytest.approx(50.0)
    assert h.total_couple == pytest.approx(60.0)
    assert h.total_other_m + h.total_other_f == pytest.approx(30.0)
    persons = h.total_solo_m + h.total_solo_f + 2 * h.total_couple + h.total_other_m + h.total_other_f
    assert persons == pytest.approx(200.0)


def test_excess_routes_to_other_and_conserves_persons_per_sex():
    """The spec's excess->Other routing, at the level where it actually happens.

    MEASURED HOLE (mutation battery, 2026-08-08): BOTH §10 fixtures have zero excess
    (coupled_m == coupled_f), so deleting `+ excess_m` / `+ excess_f` from the Other buckets
    left the whole suite green. The routing is what makes person conservation survive min()
    matching, so it gets an unbalanced case of its own.

    100 M + 100 F, living_alone 0.25 -> 75 not-alone each; couple_share M 1.0 / F 0.2 ->
    coupled 75 vs 15, so Couple = 15 and 60 unmatched men route to Other.
    """
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.25), couple_share_by_sex={"M": 1.0, "F": 0.2},
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.total_couple == pytest.approx(15.0)          # min(75, 15), never the 45 average
    assert h.total_other_m == pytest.approx(60.0)         # 0 residual + 60 routed excess
    assert h.total_other_f == pytest.approx(60.0)         # 60 residual + 0 routed excess
    # POST-ROUTING per-sex person conservation: each sex contributes exactly one person to a
    # Couple, so Solo_s + Couple + Other_s must equal that sex's private-household pool.
    assert h.total_solo_m + h.total_couple + h.total_other_m == pytest.approx(h.private_pop_m)
    assert h.total_solo_f + h.total_couple + h.total_other_f == pytest.approx(h.private_pop_f)


def test_other_is_excluded_from_the_owner_unit_stock():
    """Spec §5's labeled conservative assumption: persons living with others are presumptive
    NON-MAINTAINERS and never enter the owner-unit stock.

    MEASURED HOLE (same battery): with Other == 0 in fixture (a) and the owner fields unchecked
    in fixture (b), folding Other into an owner field left the suite green — the exclusion that
    the whole undercount claim rests on was unpinned.
    """
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(0.25), couple_share_by_sex={"M": 1.0, "F": 0.2},
        collective_share=0.0, ownership_rate=0.60,
    )
    assert h.total_other_m > 0.0 and h.total_other_f > 0.0     # the premise: Other is non-empty
    assert h.owner_couple == pytest.approx(9.0)                # 15 * 0.60, Other contributes 0
    assert h.owner_solo_m == pytest.approx(15.0)               # 25 * 0.60
    assert h.owner_solo_f == pytest.approx(15.0)               # 25 * 0.60
    # And no owner-side field exists for Other at all — an `owner_other` would invite exactly
    # the addition the exclusion forbids.
    assert not any(f.startswith("owner_other") for f in HouseholdInit.__dataclass_fields__)


def test_owner_fields_are_not_sex_transposed():
    """Every other case here is SEX-SYMMETRIC (solo_m == solo_f), so transposing the two owner
    solo fields left the suite green (mutation battery, 2026-08-08). The transposition is the
    invisible class — both values stay plausible household counts — and it is load-bearing
    downstream: `Stock(solo_m=..., solo_f=...)` feeds SEX-SPECIFIC mortality, so a swap applies
    female q to male stock without a single number looking wrong. `living_arrangement` already
    carries a Men/Women transposition gate on the SOURCE side for the same reason.

    100 M + 200 F, living_alone M 0.20 / F 0.50 -> Solo 20 vs 100 (asymmetric on purpose).
    """
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 200.0},
        living_alone_rate_by_sex={"M": 0.20, "F": 0.50},
        couple_share_by_sex={"M": 0.90, "F": 0.30},
        collective_share=0.0, ownership_rate=0.50,
    )
    assert h.total_solo_m == pytest.approx(20.0) and h.total_solo_f == pytest.approx(100.0)
    assert h.owner_solo_m == pytest.approx(10.0)     # 20 * 0.50 — NOT 50.0
    assert h.owner_solo_f == pytest.approx(50.0)     # 100 * 0.50 — NOT 10.0
    assert h.coupled_m == pytest.approx(72.0) and h.coupled_f == pytest.approx(30.0)
    assert h.owner_couple == pytest.approx(15.0)     # min(72, 30) * 0.50
    # and the routed excess keeps per-sex conservation on an asymmetric population too
    assert h.total_solo_m + h.total_couple + h.total_other_m == pytest.approx(100.0)
    assert h.total_solo_f + h.total_couple + h.total_other_f == pytest.approx(200.0)


def test_collective_share_excluded_first():
    """MULTIPLICAND ORDER. living_arrangement.json's denominators are PRIVATE-HOUSEHOLD persons
    (its `multiplicand_note`), so the collective share comes off BEFORE the rates apply."""
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 0.0},
        living_alone_rate_by_sex=_sex(1.0), couple_share_by_sex=_sex(1.0),
        collective_share=0.10, ownership_rate=1.0,
    )
    assert h.total_solo_m == 90.0   # 100 * (1-0.10) * 1.0, all solo
    assert h.private_pop_m == 90.0  # the multiplicand is RECORDED, not just implied
    assert h.private_pop_f == 0.0


# --- surviving hard gates (spec §5 as amended; the retired band gate is NOT among them) --

def test_coupled_above_sex_pool_raises():
    """Surviving hard gate 2 (spec §5): `coupled_s <= its sex pool`. Reached by a couple_share
    outside [0,1] — the loaders' `assert_fraction` blocks that on every real path, so this gate
    is the second line, and it fires for a DIFFERENT reason than gate 1."""
    with pytest.raises(CalibrationError, match="exceeds"):
        initialize_households(
            pop_by_sex={"M": 100.0, "F": 100.0},
            living_alone_rate_by_sex=_sex(0.0), couple_share_by_sex=_sex(1.2),
            collective_share=0.0, ownership_rate=1.0,
        )


def test_gate_2_fires_on_the_F_ARM_ALONE():
    """MIRROR ARM of gate 2. The case above drives BOTH sexes past the pool, so the loop reds on
    M and never reaches F: replacing its body with a hardcoded `coupled["M"] > private_pop["M"]`
    left the whole suite green (mutation battery, 2026-08-08) — the F arm was dead code to 307
    tests. Same invisible class as the owner-field transposition: only F breaches here, and the
    message must NAME the arm that fired, so the match is sex-labeled rather than `"exceeds"`.
    """
    with pytest.raises(CalibrationError, match="coupled_F"):
        initialize_households(
            pop_by_sex={"M": 100.0, "F": 100.0},
            living_alone_rate_by_sex=_sex(0.0),
            couple_share_by_sex={"M": 0.5, "F": 1.2},   # M stays inside its pool; F does not
            collective_share=0.0, ownership_rate=1.0,
        )


def test_gate_2_fires_on_the_M_ARM_ALONE():
    """THE OTHER MIRROR ARM of gate 2 — the residual of the F-arm hole above.

    MEASURED HOLE (mutation battery, 2026-08-08): closing the F arm left the M arm unpinned.
    Reducing gate 2's loop to `for s in ("F",):` survived the FULL demoflow suite AS IT STOOD
    BEFORE THIS CASE — 309 tests, all green (harness proven on the same runs by a min->max
    positive control at `match_couples`, which reds 7, and by an identity injection, which
    stays at 309). Those counts are the pre-fix RECORD, not today's. Neither existing case
    discriminates: `test_coupled_above_sex_pool_raises` drives BOTH sexes past the pool and
    matches the sex-agnostic `"exceeds"`, which the F-arm message satisfies just as well, and
    the F-arm case above breaches on F only.

    Same silent class the module docstring's two disclosed holes have. With the M arm gone,
    pop M 100 / F 1000, living_alone 0, couple_share M 1.2 / F 0.5 (coupled_m = 120 is the MIN,
    so `min()` cannot mask it) returns 120 COUPLE HOUSEHOLDS against a 100-person male pool,
    `total_other_m` = -20 (a negative household count), and `owner_couple` = 120 — while per-sex
    conservation still balances (0 + 120 - 20 = 100), so nothing downstream flags it.

    LOOP ORDER IS DELIBERATELY NOT PINNED. The sibling both-breach case keeps its sex-agnostic
    `"exceeds"` match on purpose: when both arms breach, which one is named first is loop order,
    and no spec claim rides on it (swapping `_SEXES` to `("F", "M")` returns identical values and
    is measured green at 309). Tightening that match instead of adding this case would red an
    order-only mutant — a false positive. This case names the arm because ONLY M breaches here.
    """
    with pytest.raises(CalibrationError, match="coupled_M"):
        initialize_households(
            pop_by_sex={"M": 100.0, "F": 100.0},
            living_alone_rate_by_sex=_sex(0.0),
            couple_share_by_sex={"M": 1.2, "F": 0.5},   # M breaches its pool; F does not
            collective_share=0.0, ownership_rate=1.0,
        )


def test_living_alone_above_one_makes_coupled_negative_and_raises():
    """Gate 1 reached through `initialize_households`: living_alone > 1 drives
    `(1 - living_alone) < 0`, so coupled goes negative WITHOUT ever exceeding the pool."""
    with pytest.raises(CalibrationError, match="negative"):
        initialize_households(
            pop_by_sex={"M": 100.0, "F": 100.0},
            living_alone_rate_by_sex=_sex(1.2), couple_share_by_sex=_sex(0.8),
            collective_share=0.0, ownership_rate=1.0,
        )


def test_gate_1_fires_on_the_M_ARM_ALONE():
    """MIRROR ARM of gate 1. Every other gate-1 case is F-side (`match_couples(10.0, -1.0)`) or
    sex-symmetric (`_sex(1.2)` drives both negative), so dropping `("coupled_m", coupled_m)` from
    the loop left the whole suite green (mutation battery, 2026-08-08). Sex-labeled match for the
    same reason as gate 2's mirror: a gate that fires under the wrong sex's name is a silent
    mis-diagnosis of which rate arrived broken."""
    with pytest.raises(CalibrationError, match="coupled_m is negative"):
        match_couples(-1.0, 10.0)


# --- the RECORDED per-band diagnostic (ruling A: recorded, never gated) -----------------

def test_coupled_imbalance_is_recorded_on_the_result():
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex={"M": 0.0, "F": 0.0}, couple_share_by_sex={"M": 1.0, "F": 0.2},
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.coupled_m == pytest.approx(100.0) and h.coupled_f == pytest.approx(20.0)
    assert h.coupled_imbalance == pytest.approx(0.80)   # |100-20|/100 — recorded, no raise
    assert h.total_couple == pytest.approx(20.0)


def test_coupled_imbalance_is_none_when_no_ratio_is_evaluated():
    """Spec §5 zero-zero branch: `Couple = 0`, NO RATIO EVALUATED. `None` rather than 0.0 —
    0.0 would claim 'perfectly balanced', which is a different statement than 'undefined'."""
    h = initialize_households(
        pop_by_sex={"M": 100.0, "F": 100.0},
        living_alone_rate_by_sex=_sex(1.0), couple_share_by_sex=_sex(1.0),
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.coupled_m == 0.0 and h.coupled_f == 0.0
    assert h.coupled_imbalance is None
    assert h.total_couple == 0.0


# --- the ONE surviving 0.25: the 75+ AGGREGATE direction gate ---------------------------

def test_aggregate_direction_reversal_beyond_bound_raises():
    """Spec §5: at the 75+ AGGREGATE, `coupled_m >= coupled_f`; a reversal beyond
    |diff|/max > 0.25 is a CalibrationError — THAT direction is invariant."""
    with pytest.raises(CalibrationError, match="direction reversed"):
        assert_aggregate_coupled_direction(60.0, 100.0, ctx="MTL_RMR")   # 0.40 > 0.25
    # ...and JUST above the bound. MEASURED HOLE (mutation battery, 2026-08-08): with only the
    # 0.40 breach here and the exact-0.25 tolerance below, moving `_REVERSAL_BOUND` to 0.30 left
    # the whole suite green — the file's only threshold was unpinned, while the sibling copy of
    # the same value in `living_arrangement` IS pinned by measured live-source headroom. This
    # case plus the exact-0.25 tolerance pins the bound to [0.25, 0.26): a threshold change is
    # FORK-CLASS, so it must not be silently movable.
    with pytest.raises(CalibrationError, match="direction reversed"):
        assert_aggregate_coupled_direction(74.0, 100.0, ctx="unit")      # 26/100 = 0.26 > 0.25


def test_aggregate_direction_tolerates_correct_direction_and_mild_reversal():
    # Correct direction at any magnitude: never a raise (that is the retired band gate's job).
    assert_aggregate_coupled_direction(100.0, 20.0, ctx="unit")
    # Mild reversal inside the bound: tolerated exactly as the spec rules.
    assert_aggregate_coupled_direction(90.0, 100.0, ctx="unit")          # 0.10 <= 0.25
    # Exactly at the bound is NOT a breach (the spec's comparator is strict `>`).
    assert_aggregate_coupled_direction(75.0, 100.0, ctx="unit")          # 0.25


def test_aggregate_direction_zero_zero_no_ratio_no_error():
    assert_aggregate_coupled_direction(0.0, 0.0, ctx="unit")


# --- real committed vintage, both loaders hit live --------------------------------------

def test_cited_rates_on_real_isq_pops_pass_direction_gate_despite_large_band_imbalance():
    """THE MEASURED CASE ruling A was written for, on the committed vintage, through the real
    loaders — no calibrated rates anywhere.

    MTL_RMR 85+ at the base year: the female surplus is real, the cited per-sex rates are used
    EXACTLY as published, and the result is a large per-band imbalance that the RETIRED gate
    would have raised on, with the direction invariant intact (coupled_m > coupled_f) so the
    surviving aggregate gate passes.

    MEASURED on the committed vintage 2026-08-08 (base_year 2021, reference scenario): pop
    35,480 M vs 66,020 F (F/M 1.8608) -> coupled 21,572.6 M vs 11,789.0 F -> imbalance 0.4535.
    Those figures are the RECORD, not the contract: the assertions below bind the BOUND
    (> 0.25) and the DIRECTION, so a pin bump that moves the magnitude re-reads here as the
    same claim rather than as a stale number nobody recomputed.
    """
    la = load_living_arrangement()
    pop = load_population("pop-as-rmr-base.xlsx")
    rows = pop[(pop["geography"] == Geography.MTL_RMR) & (pop["scenario"] == Scenario.REFERENCE)]
    base_year = int(rows["year"].min())
    rows = rows[(rows["year"] == base_year) & (rows["age"] >= 85)]
    pop_by_sex = {s: float(rows[rows["sex"] == s]["population"].sum()) for s in ("M", "F")}
    assert pop_by_sex["F"] > pop_by_sex["M"], pop_by_sex   # the premise: a real female surplus

    h = initialize_households(
        pop_by_sex=pop_by_sex,
        living_alone_rate_by_sex={s: living_alone_rate(la, Geography.MTL_RMR, 90, s) for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(la, Geography.MTL_RMR, 90, s) for s in ("M", "F")},
        collective_share=0.0, ownership_rate=1.0,
    )
    assert h.coupled_m > h.coupled_f                       # direction invariant holds on real data
    assert h.coupled_imbalance > 0.25                      # the RETIRED band gate would have fired
    assert h.total_couple == pytest.approx(h.coupled_f)    # min() matching, not an average
    assert_aggregate_coupled_direction(h.coupled_m, h.coupled_f, ctx="MTL_RMR 85+")  # no raise
