"""Spec §10's HAND-COMPUTED cohort oracle: 2 cohorts, 3 years, full arithmetic in comments.

WHAT AN ORACLE FIXTURE IS FOR, and why every assertion below is an EQUALITY rather than a
band: spec §5 (codex r7-F5) records that the reconciliation ENVELOPE cannot carry
exactly-once — a doubled decrement lands inside [0.20, 0.40] at every leg of the q_live axis
(measured 0.3900 / 0.3001 / 0.2293, ruling O). The exactly-once guarantee therefore lives in
the stock-flow equation plus EXACT pinned values. An inequality here would inherit the
envelope's blindness at fixture scale, so this file pins numbers, never ranges.

EVERY LITERAL BELOW WAS DERIVED INDEPENDENTLY of the code under test — exact `fractions.Fraction`
arithmetic run off spec §5's branch algebra written out from the spec text, then transcribed
here with the derivation in comments. A literal cannot be produced by the implementation it
checks; that is the point of transcribing rather than computing in-test.

THE SYNTHETIC-qx FIXTURES ARE DETERMINISTIC, not measured: every hazard and q_live is a stated
constant, so their values are exact arithmetic and hold on any machine and any data vintage —
"exact" is a structural claim about them, not a reading. Only
`test_absorbing_bucket_decrements_at_the_age_100_hazard` reads the live engine, and its figures
are labelled as MEASURED with their date and calendar years.

WHY THE SYNTHETIC FIXTURES DO NOT USE THE RUN-CONTRACT q_live: ruling N Q4 is a NEGATIVE rule — a
pipeline or gate discharge reads `CENTRAL_ASSUMPTIONS["q_live_per_year"]`, never raw
`annualize_q_live` output, because the raw value moves the run's numbers while
`assumptions_hash()` stays byte-identical. Neither applies to a synthetic hand-oracle: 0.10 and
0.09 here are neither the run contract nor the raw anchor, they are round numbers chosen so the
arithmetic is checkable by hand, and they are what produces the 19.6 / 864.36 figures spec §5
and the plan name. The run-contract value IS read where it is meaningful — the one live-basis
test at the bottom, which is also this file's only engine boundary.

RED-CHECKED 2026-08-08 on EIGHT mutants, all applied probe-side (a pytest plugin rebinding
`partition_couple` / `partition_solo` / `_add` / `min` inside `demoflow.cohort.rollforward` —
no module was edited to make a RED, the motion recorded in test_rollforward.py). 8/8 caught:
solo-never-living-exits (5 tests), widow-eligible-in-transition (6), swapped-widow-sex (1),
pooled-Solo-widow (1), blended-couple-curve (2), doubled-hazard (7), absorbing-overwrite (2),
no-age-cap (3). The two single-catch mutants are the reason the full-state oracle carries
sex-distinct hazards: under a flat q they are numerically invisible and NOTHING here sees them.

TWO OF THESE ASSERTIONS REPLACE PLAN ASSERTIONS THAT MEASURE BLIND, and the replacement is
justified by measurement rather than taste (both measured 2026-08-08 under the mutant named):
  * the plan's `exits2["living"] > 19.6*(1-0.02)*0.10` — under solo-never-living-exits the
    living exits fall to 83.0131344 and the assertion STAYS GREEN, because the 2036 couple
    block clears the 1.9208 bound on its own. It cannot see widow eligibility, the property
    its comment names. Replaced by the exact total plus the widow leg stated separately.
  * the plan's monotone `total(2035) > total(2036) > total(2037) > total(2038)` — under an
    overwriting 100+ bucket the totals become 100 / 45.3625 / 40.9069 / 36.6990 and the
    assertion STAYS GREEN: a bucket that drops half its mass still declines. Replaced by the
    exact totals, which go RED.

STATE-KEY MAPPING (T20 review pinned the producer contract): the partition dicts name
dissolution BY CAUSE (`death`, `both_die`) and widowhood BY BRANCH (`widow_to_solo_m/f`).
Spec §10's canonical {remain, widowed, dissolved, exited} partition is the CONSUMER's mapping
onto those names: remain -> the surviving same-state stock, widowed -> the `Solo_{surviving
sex}` transitions, dissolved -> `exits["estate"]`, exited -> `exits["living"]`. The mass
conservation tests assert that mapping is total (nothing falls between the four).
"""
import pytest

from demoflow.cohort.basis import q_at
from demoflow.cohort.rollforward import Stock, roll_cohort_multi_year, roll_one_year
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS


def _flat_qx(q=0.02):
    return lambda age, gender, year: q


def _sexed_qx(q_m, q_f):
    """A SEX-DISTINGUISHING provider, for the fixtures whose claim is about sex.

    Every fixture above the full-state oracle uses `_flat_qx`, where q_m = q_f: those pin
    timing, accumulation and mass, and a single q keeps their arithmetic hand-checkable. But
    a flat q makes the two widow branches NUMERICALLY EQUAL (q_m(1-q_f) = q_f(1-q_m)), so
    routing a widow to the wrong sex, or pooling the two Solo states, is invisible under it —
    the fixture cannot see the property. Spec §5's per-sex claims therefore get a provider
    that separates the curves, and the full-state oracle uses it.
    """
    return lambda age, gender, year: q_m if gender == "M" else q_f


# --- the flat-q transition factors, written once (spec §5 branch algebra) -------------------
# At q_m = q_f = 0.02 and q_live = 0.10:
#   couple remain      = (1-0.02)(1-0.02)(1-0.10) = 0.98*0.98*0.90 = 0.86436
#   couple -> Solo_m   = q_f(1-q_m)               = 0.02*0.98      = 0.0196   (female dies)
#   couple -> Solo_f   = q_m(1-q_f)               = 0.02*0.98      = 0.0196   (male dies)
#   couple both-die    = q_m*q_f                  = 0.0004
#   couple living exit = (1-0.02)(1-0.02)*0.10    = 0.09604
#   solo remain        = (1-0.02)(1-0.10)         = 0.882
#   solo death         = 0.02 ;  solo living exit = 0.98*0.10 = 0.098
# The five couple branches sum to 0.86436+0.0196+0.0196+0.0004+0.09604 = 1 exactly;
# the three solo branches sum to 0.882+0.02+0.098 = 1 exactly.


def test_widow_not_exit_eligible_in_transition_year_then_eligible_next():
    """Widow timing, both halves pinned EXACTLY (spec §5: 'the new widow is NOT
    living-exit-eligible in the transition year — eligible from the next year').

    YEAR ONE pins non-eligibility: the transition delivers the FULL 19.6, because the widow
    branch is DISJOINT from the no-death branch that q_live splits. A model that ran the new
    widow through q_live in her transition year would deliver 19.6*0.90 = 17.64.

    YEAR TWO pins the converse — that she IS eligible from the next year — and this is where
    the plan's assertion was replaced. The plan asserted only
    `exits2["living"] > 19.6*(1-0.02)*0.10`, an ENVELOPE that the 2036 couple block satisfies
    on its own (83.0131344 alone clears the 1.9208 bound), so it would stay GREEN with the
    widows contributing nothing — it could not see the property it names. The binding carry
    rules exact values over envelope checks here (T21's exact-oracle mutation law), so the
    year-two living exits are pinned as a TOTAL and DECOMPOSED into the two legs that make it:
    the couple block's own exits and the widows' own, each a separate assertion.

    FULL ARITHMETIC.  s1 = (couple 864.36, solo_m 19.6, solo_f 19.6), rolled at age 76:
      couple leg  864.36 * 0.09604                    =  83.0131344
      widow leg   (19.6 + 19.6) * 0.98 * 0.10         =   3.8416     = 2 * 1.9208
      total living                                     =  86.8547344
      estate      864.36*0.0004 + 39.2*0.02           =   1.129744
      couple'     864.36 * 0.86436                    = 747.1182096  (= 1000 * 0.86436**2)
      solo_m'     19.6*0.882 + 864.36*0.0196          =  34.228656   (remain + NEW widows)
    Mass: 747.1182096 + 2*34.228656 + 1.129744 + 86.8547344 = 903.56 = s1.owner_units.
    """
    s0 = Stock(couple=1000.0)
    s1, exits1 = roll_one_year(s0, age=75, year=2035, q_live=0.10, qx=_flat_qx())
    assert s1.solo_m == pytest.approx(19.6)   # FULL 19.6, no q_live applied in transition year
    assert s1.solo_f == pytest.approx(19.6)
    assert s1.couple == pytest.approx(864.36)
    assert exits1["estate"] == pytest.approx(0.4)      # 1000 * 0.0004, both-die only
    assert exits1["living"] == pytest.approx(96.04)    # 1000 * 0.09604, no widow contribution

    s2, exits2 = roll_one_year(s1, age=76, year=2036, q_live=0.10, qx=_flat_qx())
    couple_leg = 864.36 * 0.09604              # 83.0131344 — the 2036 couple block's own exits
    widow_leg = 2 * 19.6 * (1 - 0.02) * 0.10   #  3.8416    — the widows, NOW eligible
    assert exits2["living"] == pytest.approx(86.8547344)
    assert exits2["living"] == pytest.approx(couple_leg + widow_leg)
    # The widow leg stated on its own: the year-two living exits EXCEED the couple block's by
    # exactly the widows' contribution. Zero here is the "still not eligible" mutant.
    assert exits2["living"] - couple_leg == pytest.approx(3.8416)
    assert s2.couple == pytest.approx(747.1182096)
    assert s2.solo_m == pytest.approx(34.228656)   # 19.6 remain + 864.36 new widows
    assert s2.solo_f == pytest.approx(34.228656)
    assert exits2["estate"] == pytest.approx(1.129744)


def test_band_entry_added_exactly_once():
    """Spec §5 stock-flow discipline: ISQ population enters the roll-forward EXACTLY ONCE per
    cohort, at band entry; post-entry the stock evolves ONLY by our decrements and is NEVER
    re-anchored. Two directions, both pinned exactly:

      (i) the age-75 slot holds ONLY that year's entrants — never entrants PLUS a survivor
          remnant, and never a re-anchored ISQ stock;
      (ii) the previous occupants actually AGED OUT and are still carried at their new ages —
          the 1000-couple base cohorts appear at 76 and 77 in 2036 at exactly 864.36, and the
          2036 entrants (500) appear at 76 in 2037 at exactly 432.18 = 500 * 0.86436.

    (ii) is what separates "entered once" from "silently dropped": an implementation that
    overwrote the whole next-year state with entrants would satisfy (i) alone.

    ARITHMETIC. base 1000 couples at each of 75 and 76; entrants 500/yr; q=0.02, q_live=0.10.
      2036: 75 -> 500 (entrants)          76 <- base-75 : 1000*0.86436 = 864.36, widows 19.6 ea
                                          77 <- base-76 : 1000*0.86436 = 864.36, widows 19.6 ea
      2037: 75 -> 500 (entrants)          76 <- 2036 entrants: 500*0.86436 = 432.18, widows 9.8
                                          77 <- 864.36*0.86436 = 747.1182096, widows 34.228656
                                          78 <- same lineage from the base-76 cohort
    """
    states = roll_cohort_multi_year(
        base={75: Stock(couple=1000.0), 76: Stock(couple=1000.0)},
        entrants_per_year=500.0, start_year=2035, n_years=2, q_live=0.10, qx=_flat_qx(),
    )
    # (i) the entrant slot: exactly the entrants, in both years, with no survivor remnant.
    assert states[2036][75].couple == pytest.approx(500.0)   # entrants once
    assert states[2037][75].couple == pytest.approx(500.0)   # entrants once again (new cohort)
    assert states[2036][75].solo_m == 0.0 and states[2036][75].solo_f == 0.0
    assert states[2037][75].solo_m == 0.0 and states[2037][75].solo_f == 0.0

    # (ii) the previous occupants aged out and are carried, decremented EXACTLY ONCE.
    assert states[2036][76].couple == pytest.approx(864.36)
    assert states[2036][77].couple == pytest.approx(864.36)
    assert states[2036][76].solo_m == pytest.approx(19.6)
    assert states[2037][76].couple == pytest.approx(432.18)          # the 2036 entrants, aged
    assert states[2037][76].solo_m == pytest.approx(9.8)             # 500 * 0.0196
    assert states[2037][77].couple == pytest.approx(747.1182096)     # 1000 * 0.86436**2
    assert states[2037][78].couple == pytest.approx(747.1182096)
    assert states[2037][77].solo_m == pytest.approx(34.228656)


def test_state_mass_conservation_every_household_ends_in_one_state():
    """Spec §10's transition identity: every household ends in EXACTLY ONE of
    {remain, widowed, dissolved, exited} — the partition is total (nothing lost) and
    disjoint (nothing counted twice). Asserted on a mixed-state cohort so all three
    initial states contribute, and with every destination pinned exactly, so the identity
    cannot be satisfied by an offsetting pair of errors.

    ARITHMETIC.  (couple 137, solo_m 11, solo_f 23) at q_m=q_f=0.03, q_live=0.09:
      couple remain = 0.97*0.97*0.91 = 0.856219 ; couple->solo each = 0.03*0.97 = 0.0291
      couple both-die = 0.0009 ; couple living exit = 0.9409*0.09 = 0.084681
      solo remain = 0.97*0.91 = 0.8827 ; solo death = 0.03 ; solo living exit = 0.97*0.09 = 0.0873
      couple'  = 137*0.856219                        = 117.302003
      solo_m'  = 11*0.8827  + 137*0.0291             =  13.6964    ( 9.7097 + 3.9867 )
      solo_f'  = 23*0.8827  + 137*0.0291             =  24.2888    (20.3021 + 3.9867 )
      estate   = 137*0.0009 + 11*0.03 + 23*0.03      =   1.1433
      living   = 137*0.084681 + 34*0.97*0.09         =  14.569497  (11.601297 + 2.9682)
      total    = 117.302003+13.6964+24.2888+1.1433+14.569497 = 171.0 = 137+11+23
    """
    s0 = Stock(couple=137.0, solo_m=11.0, solo_f=23.0)
    s1, exits = roll_one_year(s0, age=80, year=2040, q_live=0.09, qx=_flat_qx(0.03))
    assert s1.couple == pytest.approx(117.302003)
    assert s1.solo_m == pytest.approx(13.6964)
    assert s1.solo_f == pytest.approx(24.2888)
    assert exits["estate"] == pytest.approx(1.1433)
    assert exits["living"] == pytest.approx(14.569497)
    total_out = s1.couple + s1.solo_m + s1.solo_f + exits["estate"] + exits["living"]
    assert total_out == pytest.approx(s0.owner_units)   # {remain,widowed,dissolved,exited} partition
    assert total_out == pytest.approx(171.0)


def test_100plus_is_absorbing_bucket_accumulates_age_ins():
    """Spec §8 terminal-bucket semantics (codex r5-F6): 100+ is an ABSORBING bucket — the
    age-99 age-ins AND the surviving prior 100+ stock BOTH land in age 100 and ACCUMULATE,
    never overwritten or reinitialized, each decremented exactly once.

    Pinned two ways, and the pair is not redundant. The `roll_one_year` comparison states the
    ACCUMULATION (bucket == age-in contribution + prior-stock contribution) and would survive
    an arithmetic error common to both legs; the transcribed literals state the ARITHMETIC and
    would survive nothing.

    ARITHMETIC. base 100 couples at 99 + 200 couples at 100, q=0.05, q_live=0.10:
      couple remain = 0.95*0.95*0.90 = 0.81225 ; couple -> Solo each = 0.05*0.95 = 0.0475
      from 99  : couple 100*0.81225 =  81.225 ; solo_m = solo_f = 100*0.0475 =  4.75
      from 100 : couple 200*0.81225 = 162.450 ; solo_m = solo_f = 200*0.0475 =  9.50
      bucket   : couple 243.675 ; solo_m = solo_f = 14.25
    An OVERWRITING bucket would hold 162.450 (prior stock last) or 81.225 (age-ins last).
    """
    base = {99: Stock(couple=100.0), 100: Stock(couple=200.0)}
    states = roll_cohort_multi_year(base, entrants_per_year=0.0, start_year=2035, n_years=1,
                                    q_live=0.10, qx=_flat_qx(0.05))
    from_99, _ = roll_one_year(Stock(couple=100.0), age=99, year=2035, q_live=0.10, qx=_flat_qx(0.05))
    from_100, _ = roll_one_year(Stock(couple=200.0), age=100, year=2035, q_live=0.10, qx=_flat_qx(0.05))
    b = states[2036][100]
    assert b.couple == pytest.approx(from_99.couple + from_100.couple)
    assert b.solo_m == pytest.approx(from_99.solo_m + from_100.solo_m)
    assert b.solo_f == pytest.approx(from_99.solo_f + from_100.solo_f)
    # The same claim as transcribed literals, independent of `roll_one_year`.
    assert b.couple == pytest.approx(243.675)
    assert b.solo_m == pytest.approx(14.25)
    assert b.solo_f == pytest.approx(14.25)
    assert max(states[2036].keys()) == 100   # age capped at the absorbing bucket


def test_absorbing_bucket_mass_reconciles_over_three_years():
    """Spec §8's three-year fixture: the absorbing bucket reconciles mass with each decrement
    applied ONCE. The plan asserted a monotone decline; the binding carry rules exact values
    over envelope checks, and exactness strictly implies the decline while also catching the
    re-initialization defects a decline cannot see — a bucket that dropped its age-ins would
    ALSO decline monotonically, just from the wrong mass.

    ARITHMETIC. base 50 couples at 99 + 50 at 100, no entrants, q=0.05, q_live=0.10.
    Per-unit factors: couple remain 0.81225, couple -> Solo 0.0475 each, solo remain 0.855.
    Couple owner-units retention is 0.81225 + 2*0.0475 = 0.90725; solo units retain 0.855.
      2035  couple 100.0                                              total 100.0
      2036  bucket = (81.225, 4.75, 4.75)                             total  90.725
              couple 100*0.81225 ; solos 100*0.0475 each
      2037  couple 81.225*0.81225                    = 65.97500625
            solo_s 4.75*0.855 + 81.225*0.0475        =  7.9194375     total  81.81388125
      2038  couple 65.97500625*0.81225               = 53.5881988265625
            solo_s 7.9194375*0.855 + 65.97500625*0.0475 = 9.904931859375
                                                                      total  73.3980625453125
    No entrants, so nothing enters after 2035: the totals are pure decrement paths.
    """
    base = {99: Stock(couple=50.0), 100: Stock(couple=50.0)}
    states = roll_cohort_multi_year(base, entrants_per_year=0.0, start_year=2035, n_years=3,
                                    q_live=0.10, qx=_flat_qx(0.05))

    def total(yr):
        return sum(s.owner_units for s in states[yr].values())

    assert total(2035) == pytest.approx(100.0)
    assert total(2036) == pytest.approx(90.725)
    assert total(2037) == pytest.approx(81.81388125)
    assert total(2038) == pytest.approx(73.3980625453125)
    b = states[2038][100]
    assert b.couple == pytest.approx(53.5881988265625)
    assert b.solo_m == pytest.approx(9.904931859375)
    assert b.solo_f == pytest.approx(9.904931859375)
    assert max(states[2038].keys()) == 100


def test_two_cohort_three_year_oracle_full_state_table():
    """SPEC §10's named anchor: the hand-computed 2-cohort, 3-year example, with the full
    arithmetic in comments and EVERY state of EVERY year pinned.

    The five fixtures above each isolate one mechanism on a near-degenerate stock. This one
    runs them together — two adjacent base cohorts whose aging paths interleave, all three
    household states populated from the start, and entrants refilling the band-entry slot every
    year — because a cross-term defect (widows landing in the wrong sex's Solo, an age-in
    overwriting an existing slot, entrants added before rather than after the roll) can hide in
    every isolated fixture and only shows where the paths meet.

    THE HAZARDS ARE SEX-DISTINCT HERE, and that is the point of this fixture over the five
    above: q_m = 0.03, q_f = 0.02. Under a flat q the two widow branches are numerically equal
    and the routing claim is unpinnable; separating the curves makes `couple -> Solo_m` (0.0194)
    and `couple -> Solo_f` (0.0294) distinguishable, which is what lets this table see a widow
    routed to the DECEASED spouse's sex, the two Solo states pooled, or the couple decremented
    on ONE BLENDED CURVE rather than per sex (spec §5: q_m off the male curve, q_f off the
    female curve). All three are measured RED against this table.

    SETUP. base 75: (couple 1000, solo_m 100, solo_f 200); 76: (couple 500, solo_m 50, solo_f 80).
    Entrants 400 age-75 couples per year. q_m = 0.03, q_f = 0.02, q_live = 0.10.
      couple remain      = 0.97*0.98*0.90 = 0.85554
      couple -> Solo_m   = q_f(1-q_m) = 0.02*0.97 = 0.0194   (the FEMALE dies, male survives)
      couple -> Solo_f   = q_m(1-q_f) = 0.03*0.98 = 0.0294   (the MALE dies, female survives)
      couple both-die    = 0.0006 ; couple living exit = 0.9506*0.10 = 0.09506
      solo_m remain      = 0.97*0.90 = 0.873 ; solo_f remain = 0.98*0.90 = 0.882
    Couple branches sum to 0.85554+0.0194+0.0294+0.0006+0.09506 = 1 exactly.

    2035 -> 2036  (age 75 -> 76, age 76 -> 77, entrants -> 75)
      76  couple 1000*0.85554              = 855.54
          solo_m 100*0.873 + 1000*0.0194   = 106.7      ( 87.3  + 19.4)
          solo_f 200*0.882 + 1000*0.0294   = 205.8      (176.4  + 29.4)
      77  couple  500*0.85554              = 427.77
          solo_m  50*0.873 +  500*0.0194   =  53.35     ( 43.65 +  9.7)
          solo_f  80*0.882 +  500*0.0294   =  85.26     ( 70.56 + 14.7)
      75  couple 400 (entrants), solos 0            TOTAL 2134.42

    2036 -> 2037
      76  from the 400 entrants: couple 342.216 ; solo_m 400*0.0194 = 7.76 ; solo_f 400*0.0294 = 11.76
      77  couple 855.54*0.85554            = 731.9486916            (= 1000*0.85554**2)
          solo_m 106.7*0.873 + 855.54*0.0194 = 109.746576  ( 93.1491 + 16.597476)
          solo_f 205.8*0.882 + 855.54*0.0294 = 206.668476  (181.5156 + 25.152876)
      78  couple 427.77*0.85554            = 365.9743458            (=  500*0.85554**2)
          solo_m  53.35*0.873 + 427.77*0.0194 =  54.873288  ( 46.57455 +  8.298738)
          solo_f  85.26*0.882 + 427.77*0.0294 =  87.775758  ( 75.19932 + 12.576438)
      75  couple 400 (entrants)                     TOTAL 2318.7231354

    2037 -> 2038
      76  from the 400 entrants again: couple 342.216 ; solo_m 7.76 ; solo_f 11.76
      77  couple 342.216*0.85554          = 292.77947664            (=  400*0.85554**2)
          solo_m 7.76*0.873  + 342.216*0.0194 =  13.4134704  ( 6.77448 +  6.6389904)
          solo_f 11.76*0.882 + 342.216*0.0294 =  20.4334704  (10.37232 + 10.0611504)
      78  couple 731.9486916*0.85554      = 626.211383611464        (= 1000*0.85554**3)
          solo_m 109.746576*0.873 + 731.9486916*0.0194 = 110.00856546504
          solo_f 206.668476*0.882 + 731.9486916*0.0294 = 203.80088736504
      79  couple 365.9743458*0.85554      = 313.105691805732        (=  500*0.85554**3)
          solo_m  54.873288*0.873 + 365.9743458*0.0194 =  55.00428273252
          solo_f  87.775758*0.882 + 365.9743458*0.0294 =  88.17786432252
      75  couple 400 (entrants)                     TOTAL 2484.671092742316

    The 79-slot's 55.00428273252 vs 88.17786432252 is where the sex claims land: unequal
    inflows onto unequal stocks, three years deep, with the widow inflow being the LARGER one
    on the female side precisely because the male hazard is the higher of the two.
    """
    states = roll_cohort_multi_year(
        base={75: Stock(couple=1000.0, solo_m=100.0, solo_f=200.0),
              76: Stock(couple=500.0, solo_m=50.0, solo_f=80.0)},
        entrants_per_year=400.0, start_year=2035, n_years=3, q_live=0.10,
        qx=_sexed_qx(0.03, 0.02),
    )
    expected = {
        2035: {75: (1000.0, 100.0, 200.0),
               76: (500.0, 50.0, 80.0)},
        2036: {75: (400.0, 0.0, 0.0),
               76: (855.54, 106.7, 205.8),
               77: (427.77, 53.35, 85.26)},
        2037: {75: (400.0, 0.0, 0.0),
               76: (342.216, 7.76, 11.76),
               77: (731.9486916, 109.746576, 206.668476),
               78: (365.9743458, 54.873288, 87.775758)},
        2038: {75: (400.0, 0.0, 0.0),
               76: (342.216, 7.76, 11.76),
               77: (292.77947664, 13.4134704, 20.4334704),
               78: (626.211383611464, 110.00856546504, 203.80088736504),
               79: (313.105691805732, 55.00428273252, 88.17786432252)},
    }
    assert set(states) == set(expected)
    for year, table in expected.items():
        assert set(states[year]) == set(table), f"age slots differ in {year}"
        for age, (c, sm, sf) in table.items():
            got = states[year][age]
            assert got.couple == pytest.approx(c), f"{year} age {age} couple"
            assert got.solo_m == pytest.approx(sm), f"{year} age {age} solo_m"
            assert got.solo_f == pytest.approx(sf), f"{year} age {age} solo_f"

    totals = {yr: sum(s.owner_units for s in states[yr].values()) for yr in states}
    assert totals[2035] == pytest.approx(1930.0)
    assert totals[2036] == pytest.approx(2134.42)
    assert totals[2037] == pytest.approx(2318.7231354)
    assert totals[2038] == pytest.approx(2484.671092742316)


def test_absorbing_bucket_decrements_at_the_age_100_hazard():
    """THE LIVE-ENGINE LEG of this file, and the only one: every fixture above supplies a
    synthetic `qx`, so without this test the roller's contract with the mortality engine —
    WHICH AGE the absorbing bucket is evaluated at — would never be hit.

    THE CLAIM: the 100+ bucket decrements at q(100) forever, because `roll_cohort_multi_year`
    caps `dest` at 100 and then hands that same age back to `roll_one_year` each year. Spec §8's
    Age junction pins this — `100+` capped at the CPM table max, '≥100 verified live, skeleton
    q₁₀₀ returned'. It is NOT the engine's terminal age: `basis.py` records 120 as the engine's
    SYNTHESIZED terminal, where q is exactly 1.0 and the bucket would empty in one year, and
    ages 116-119 interpolate to 0.968517 — those are the values a roller that pushed the bucket
    up the age axis would eventually reach.

    ASSERTION (1) IS THE LOAD-BEARING ONE, and the other two are labelled for what they are.
      (1) the surviving mass equals the product of the LIVE per-year factors at age 100 — a
          positional pin, and also a pin that the CALENDAR YEAR advances while the age does
          not (CPM-B improvement makes q(100) fall year over year, so a frozen year gives a
          different product). This is the assertion that MOVES: measured RED 2026-08-08 under
          a no-age-cap mutant (the bucket climbs to 101/102 and the age-100 slot is gone) and
          under a blended-curve mutant (70.450 against the per-sex 70.176).
      (2) the bucket does not empty, and (3) the capped roll retains strictly more than the
          same roll at ages 101/102. These are LIVE-MEASURED DISCRIMINATIONS, not mutation-
          detectors: they read `q_at` directly, so no mutant of the roll-forward moves them,
          and none was found that does. They are here to record WHY 100 is the right age for
          (1) to expect — that q(100) is a real hazard near 0.35 rather than the terminal
          1.0, and that 101 is strictly worse — so a future reader can check the premise
          instead of taking (1)'s expectation on faith.

    MEASURED 2026-08-08 on the committed vintage, CPM2014_combined + CPM-B, q read live rather
    than transcribed so a basis change surfaces as a RED here rather than a stale literal:
    q(100,'M') = 0.353429 / 0.352368 / 0.351311 and q(100,'F') = 0.304851 / 0.303936 / 0.303024
    across 2035 / 2036 / 2037; q(101,'M') = 0.374370 at 2035, strictly above q(100).

    q_live IS THE RUN CONTRACT, `CENTRAL_ASSUMPTIONS["q_live_per_year"]` = 0.085 (ruling N Q4) —
    the one place in this file where a run-contract value is the meaningful choice, because this
    is the one roll evaluated against the live basis the run itself uses.
    """
    q_live = CENTRAL_ASSUMPTIONS["q_live_per_year"]
    states = roll_cohort_multi_year({100: Stock(couple=1000.0)}, entrants_per_year=0.0,
                                    start_year=2035, n_years=3, q_live=q_live, qx=q_at)

    # (1) the exact surviving couple mass, from the live hazards at age 100 in each year.
    expected = 1000.0
    for year in (2035, 2036, 2037):
        expected *= (1.0 - q_at(100, "M", year)) * (1.0 - q_at(100, "F", year)) * (1.0 - q_live)
    assert states[2038][100].couple == pytest.approx(expected)

    # (2) the bucket survives: this is q(100)~0.35, never the terminal age's exact 1.0.
    assert states[2038][100].couple > 0.0
    assert q_at(120, "M", 2035) == 1.0 and q_at(120, "F", 2035) == 1.0
    assert q_at(100, "M", 2035) < 0.5 and q_at(100, "F", 2035) < 0.5

    # (3) the cap fires: an uncapped roller would climb to 101 then 102, where q is strictly
    #     higher, so it would retain strictly less than the absorbing bucket does.
    uncapped = 1000.0
    for age, year in ((100, 2035), (101, 2036), (102, 2037)):
        uncapped *= (1.0 - q_at(age, "M", year)) * (1.0 - q_at(age, "F", year)) * (1.0 - q_live)
    assert q_at(101, "M", 2035) > q_at(100, "M", 2035)
    assert states[2038][100].couple > uncapped
