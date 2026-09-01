"""Competing-risk partition algebra (spec §5 "Pinned competing-risk algebra", codex F3).

THE THREE CLAIMS THE SPEC PINS, and where each becomes executable here:
  1. DEATH RESOLVES FIRST — a decrement's death mass is a property of q alone, never
     conditioned on the living-exit hazard (`..._death_mass_is_invariant_in_q_live`).
  2. LIVING EXIT IS SURVIVOR-CONDITIONAL — the q_live split rides ONLY the no-death branch
     (`..._widow_branch_is_retained_and_disjoint_...`).
  3. WIDOWHOOD RETAINS THE UNIT — a couple losing exactly one spouse becomes `Solo` of the
     SURVIVING sex; that unit is NOT an exit and is NOT living-exit-eligible in the
     transition year (eligible from the next year, which Task 22's roll-forward owns).

WHY THE ADDED BODIES EXIST (the plan's three do not reach these): the plan's fixtures
evaluate at ONE (q_m, q_f, q_live) triple each, so they pin VALUES but not the three
structural claims above — an implementation can match both fixtures while getting the
ordering semantics wrong off-fixture. The added bodies vary q_live against fixed q to make
"death first" and "widow disjoint from the q_live split" falsifiable, and fence the
`_check_unit` domain, which the plan's REDs probe only from outside [0,1].

KEY SCHEMA IS A CONTRACT, not an implementation detail: Task 22's roll-forward indexes these
exact strings (`pc["widow_to_solo_m"]`, `ps["death"]`, …). `test_key_schema...` locks them so
a rename fails HERE rather than as a KeyError inside the stock-flow equation.

MUTATION BATTERY, RUN — not asserted (9 mutants against this file and `decrements.py`; every
one KILLED, source restored byte-identical afterward). The plan's three bodies are stronger
than expected: SEVEN of the nine die to their exact-value asserts — widow made exit-eligible;
death made survivor-conditional, solo side and couple side (two mutants); widow sexes swapped;
`no_death` as the additive approximation `1−q_m−q_f`; unconditional `living_exit`; and solo's
`q_live` left out of the guard call. The TWO the plan bodies miss entirely — zero plan
failures each, killed only here — are both in the DOMAIN GUARD, because the plan's REDs only
ever pass values from OUTSIDE [0,1] and so never probe the boundary or the comparison's shape:
  • `not 0.0 <= q < 1.0` (strict upper bound — the "harmonize the two guards" mutant);
  • `if q < 0.0 or q > 1.0` (the natural De Morgan rewrite — opens a SILENT NaN hole).
That is the measured warrant for the added bodies; the structural ones (invariance in q_live,
orientation) restate single-point value matches as domain-wide claims, which is durability
against a future fixture edit rather than extra kill power today.
"""
import math

import pytest

from demoflow.cohort.decrements import partition_solo, partition_couple
from demoflow.errors import CalibrationError

# Grid spanning the closed domain including BOTH endpoints and near-endpoint values, reused
# by the property bodies. 0.0 and 1.0 are in-domain for `_check_unit` (inclusive by design —
# see `test_check_unit_domain_is_inclusive_and_rejects_nonfinite`).
Q_GRID = (0.0, 1e-6, 0.001, 0.01, 0.02, 0.05, 0.1, 0.2, 0.36, 0.5, 0.7, 0.85, 0.99, 1.0)


# ---------------------------------------------------------------- plan bodies (verbatim)

def test_solo_partition_fixture():
    # spec §5/§10: q_s=0.20, q_live=0.10 -> death 0.20, living-exit 0.08, remain 0.72; sum 1.
    p = partition_solo(0.20, 0.10)
    assert p["death"] == pytest.approx(0.20)
    assert p["living_exit"] == pytest.approx(0.08)
    assert p["remain"] == pytest.approx(0.72)
    assert sum(p.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in p.values())


def test_couple_partition_sums_to_one_and_widow_retained():
    # death resolves first; living exit survivor-conditional; branches partition to 1.
    p = partition_couple(q_m=0.02, q_f=0.01, q_live=0.10)
    assert sum(p.values()) == pytest.approx(1.0)
    # both-die (estate), widow->Solo_m, widow->Solo_f, living_exit, remain
    assert p["both_die"] == pytest.approx(0.02 * 0.01)
    assert p["widow_to_solo_f"] == pytest.approx(0.02 * (1 - 0.01))   # male dies, female survives
    assert p["widow_to_solo_m"] == pytest.approx(0.01 * (1 - 0.02))   # female dies, male survives
    no_death = (1 - 0.02) * (1 - 0.01)
    assert p["living_exit"] == pytest.approx(no_death * 0.10)
    assert p["remain"] == pytest.approx(no_death * 0.90)
    # widows are RETAINED (own the unit), not counted as exits
    assert p["widow_to_solo_m"] > 0 and p["widow_to_solo_f"] > 0


def test_q_outside_unit_raises():
    with pytest.raises(CalibrationError):
        partition_solo(1.2, 0.10)
    with pytest.raises(CalibrationError):
        partition_couple(q_m=-0.1, q_f=0.01, q_live=0.10)
    with pytest.raises(CalibrationError):
        partition_solo(0.2, 1.5)


# ------------------------------------------------- ADDED: the three structural spec claims

def test_partition_sums_to_one_and_stays_nonnegative_across_the_domain():
    """Spec §5: "all branches ≥0, sum exactly 1" — asserted over the domain, not one point.

    "Exactly 1" is an ALGEBRAIC claim; in IEEE-754 it holds to rounding. MEASURED over this
    grid (196 solo pairs, 2744 couple triples): worst |sum − 1| = 2.220446049250313e-16 (one
    ULP at 1.0), with 184/196 solo and 2419/2744 couple sums bit-exactly 1.0 — so `== 1.0` on
    the bare float would fail on ~12% of the grid and `abs=1e-15` (~4 ULP) is the tight-but-
    portable pin. Headroom costs no kill power: MEASURED, the widow-made-exit-eligible mutant
    leaves a residual of 1.98e-3 at the plan's own fixture triple — twelve orders of magnitude
    above the tolerance. The plan's `pytest.approx(1.0)` default is RELATIVE 1e-6; this is the
    tighter of the two on purpose.
    """
    for q_s in Q_GRID:
        for q_live in Q_GRID:
            p = partition_solo(q_s, q_live)
            assert sum(p.values()) == pytest.approx(1.0, abs=1e-15), (q_s, q_live)
            assert all(v >= 0.0 for v in p.values()), (q_s, q_live, p)

    for q_m in Q_GRID:
        for q_f in Q_GRID:
            for q_live in Q_GRID:
                p = partition_couple(q_m, q_f, q_live)
                assert sum(p.values()) == pytest.approx(1.0, abs=1e-15), (q_m, q_f, q_live)
                assert all(v >= 0.0 for v in p.values()), (q_m, q_f, q_live, p)


def test_death_resolves_first_so_death_mass_is_invariant_in_q_live():
    """Claim 1 made falsifiable: death is unconditional, so sweeping q_live across its whole
    domain must not move ANY death-branch mass. The plan's fixtures cannot see this — they
    hold q_live at 0.10 and only check the death value at that one point.

    MEASURED (battery): both wrong-order mutants — `"death": q_s * (1.0 - q_live)` and
    `both_die = q_m * q_f * (1.0 - q_live)` — die here at every q with q > 0 and q_live > 0.
    HONEST SCOPE: the plan's fixtures kill them too (its solo and couple value asserts
    respectively), so this body adds no kill power against these two today. What it adds is
    the STATEMENT: "death mass does not depend on q_live" is checked as an invariance over the
    whole domain, so it still holds if a later edit moves the fixture triple, and it names the
    ordering claim a reader has to satisfy rather than leaving it implicit in three numbers.
    """
    for q_s in Q_GRID:
        deaths = {partition_solo(q_s, q_live)["death"] for q_live in Q_GRID}
        assert deaths == {q_s}, (q_s, deaths)

    for q_m in Q_GRID:
        for q_f in Q_GRID:
            ps = [partition_couple(q_m, q_f, q_live) for q_live in Q_GRID]
            assert {p["both_die"] for p in ps} == {q_m * q_f}, (q_m, q_f)


def test_widow_branch_is_retained_and_disjoint_from_the_living_exit_split():
    """Claims 2 + 3 together — the load-bearing semantic of codex F3.

    DISJOINTNESS: the widow branch must be invariant in q_live (a new widow is NOT
    living-exit-eligible in the transition year). MEASURED (battery): the
    `widow_to_solo_f = q_m * (1.0 - q_f) * (1.0 - q_live)` mutant — the most plausible
    misreading of the spec, being what "everyone faces the sale hazard" would produce — dies
    here. It also dies at the plan's couple fixture (residual 1.98e-3 on the branch value AND
    on the sum), so the plan is NOT blind to it; the plan's `p["widow_to_solo_m"] > 0`
    retention assert alone, however, passes it clean — a `> 0` check cannot distinguish
    "retained" from "retained then partly resold", which is precisely the spec's distinction.

    RETENTION as mass conservation (spec §10's transition identity, {remain, widowed,
    dissolved, exited}): the couple's mass splits into units that STILL OWN
    (widow_to_solo_m + widow_to_solo_f + remain) and units that LEAVE the owner stock
    (both_die → estate, living_exit → voluntary sale). Widowhood sits on the retained side.
    """
    for q_m in Q_GRID:
        for q_f in Q_GRID:
            ps = [partition_couple(q_m, q_f, q_live) for q_live in Q_GRID]
            # disjoint from the q_live split: widow mass does not move with q_live at all
            assert {p["widow_to_solo_f"] for p in ps} == {q_m * (1.0 - q_f)}, (q_m, q_f)
            assert {p["widow_to_solo_m"] for p in ps} == {q_f * (1.0 - q_m)}, (q_m, q_f)

            for q_live, p in zip(Q_GRID, ps):
                retained = p["widow_to_solo_m"] + p["widow_to_solo_f"] + p["remain"]
                exited = p["both_die"] + p["living_exit"]
                assert retained + exited == pytest.approx(1.0, abs=1e-15)
                # the widowed unit is on the RETAINED side, never counted out
                assert retained >= p["widow_to_solo_m"] + p["widow_to_solo_f"]

    # and the exit mass DOES move with q_live (the split is real, not a dead branch)
    lo = partition_couple(0.02, 0.01, 0.0)
    hi = partition_couple(0.02, 0.01, 0.11)
    assert lo["living_exit"] == 0.0 and hi["living_exit"] > 0.0
    assert lo["widow_to_solo_f"] == hi["widow_to_solo_f"]   # unchanged across the sweep


def test_sex_orientation_of_the_widow_branches():
    """Which sex SURVIVES names the branch: male dies → surviving female → `widow_to_solo_f`.

    Degenerate-q pins make the orientation unmistakable independent of arithmetic near-misses:
    with q_f = 0 the female cannot die, so no male can be widowed. MEASURED (battery): the
    swapped-assignment mutant dies here — and at the plan's fixture too, but ONLY because that
    fixture happens to use q_m ≠ q_f; a later edit to symmetric q would silently disarm the
    plan's assert and leave this body as the sole guard. Orientation is load-bearing
    downstream: Task 22 routes `widow_to_solo_m` into the Solo_m stock, and male/female
    mortality differ materially at 75+, so a swap biases the surviving-owner sex mix.
    """
    p = partition_couple(q_m=0.30, q_f=0.0, q_live=0.10)
    assert p["widow_to_solo_m"] == 0.0          # female cannot die → no widowed male
    assert p["widow_to_solo_f"] == pytest.approx(0.30)   # every male death widows a female
    assert p["both_die"] == 0.0

    p = partition_couple(q_m=0.0, q_f=0.30, q_live=0.10)
    assert p["widow_to_solo_f"] == 0.0
    assert p["widow_to_solo_m"] == pytest.approx(0.30)
    assert p["both_die"] == 0.0


# -------------------------------------------------------- ADDED: domain guard + key schema

def test_check_unit_domain_is_inclusive_and_rejects_nonfinite():
    """The `_check_unit` domain is `[0,1]` CLOSED — deliberately unlike `annualize_q_live`'s
    `[0,1)`, whose strict upper bound rejects a certain-sale rate as a data defect. A
    probability of exactly 1 is a legitimate (if degenerate) decrement; `test_q_live.py`'s
    `test_boundary_and_monotonicity` fences that contrast from its side, this fences it from
    THIS side, so a future "harmonization" of the two guards fails on one of the pair.

    MEASURED (battery): these are THE TWO mutants of the nine that the plan's three bodies do
    not kill at all — zero plan failures each, because those bodies only ever pass values from
    OUTSIDE [0,1] and so never probe the boundary or the comparison's shape:
      • `not 0.0 <= q < 1.0` (strict upper, the harmonization mutant) → the q=1.0 asserts fail.
      • `if q < 0.0 or q > 1.0` (the natural De Morgan rewrite) → NaN SILENTLY PASSES, because
        every ordering comparison against NaN is False. It then propagates a NaN "probability"
        into the roll-forward instead of raising at the calibration boundary where the bad
        input entered. MEASURED: this body is its ONLY failure in the file — not because the
        other bodies are weak (a NaN branch does fail both the sum-to-1 and the `v >= 0.0`
        asserts, VERIFIED: `sum([nan]*3) == approx(1.0)` is False and `nan >= 0.0` is False)
        but because none of them ever FEEDS a non-finite q. Nonfinite inputs must be supplied
        deliberately, which is what the loop below exists to do.
    """
    # closed domain: both endpoints accepted, and the degenerate partitions still sum to 1
    for p in (partition_solo(0.0, 0.0), partition_solo(1.0, 1.0),
              partition_couple(0.0, 0.0, 0.0), partition_couple(1.0, 1.0, 1.0)):
        assert sum(p.values()) == pytest.approx(1.0, abs=1e-15)
        assert all(v >= 0.0 for v in p.values())
    assert partition_solo(1.0, 0.5)["death"] == 1.0          # certain death, no survivors
    assert partition_couple(1.0, 1.0, 1.0)["both_die"] == 1.0

    # nonfinite must RAISE, never propagate — NaN is the silent one
    for bad in (float("nan"), float("inf"), float("-inf")):
        for call in (lambda b: partition_solo(b, 0.10),
                     lambda b: partition_solo(0.10, b),
                     lambda b: partition_couple(b, 0.01, 0.10),
                     lambda b: partition_couple(0.02, b, 0.10),
                     lambda b: partition_couple(0.02, 0.01, b)):
            with pytest.raises(CalibrationError):
                call(bad)

    # every argument slot is guarded, and the message names the offender
    with pytest.raises(CalibrationError, match="1.5"):
        partition_couple(q_m=0.02, q_f=0.01, q_live=1.5)
    with pytest.raises(CalibrationError, match=r"-0\.1"):
        partition_couple(q_m=0.02, q_f=-0.1, q_live=0.10)

    # a valid partition never contains a non-finite value
    assert all(math.isfinite(v) for v in partition_couple(0.02, 0.01, 0.10).values())


def test_key_schema_is_the_one_the_roll_forward_indexes():
    """Task 22's stock-flow equation indexes these exact strings; a rename here would surface
    downstream as a KeyError inside the roll-forward (or, worse, as a silently dropped branch
    if a consumer ever used `.get`). Locked at the producer so the failure lands at the source.

    The two dicts deliberately SHARE `living_exit` and `remain` — those branches mean the same
    thing whatever the household state, and Task 22 sums them across states — while the
    dissolution branch is named for its cause (`death` solo, `both_die` couple) and the widow
    branches exist only on the couple side.
    """
    solo_keys = set(partition_solo(0.20, 0.10))
    couple_keys = set(partition_couple(0.02, 0.01, 0.10))
    assert solo_keys == {"death", "living_exit", "remain"}
    assert couple_keys == {
        "both_die", "widow_to_solo_f", "widow_to_solo_m", "living_exit", "remain",
    }
    assert solo_keys & couple_keys == {"living_exit", "remain"}
