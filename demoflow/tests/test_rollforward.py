import pytest

from demoflow.cohort.basis import q_at
from demoflow.cohort.gates import RECONCILIATION_BAND, check_reconciliation
from demoflow.cohort.init import initialize_households
from demoflow.cohort.rollforward import Stock, roll_cohort_decade, roll_one_year
from demoflow.errors import CalibrationError
from demoflow.geography import Geography, Scenario
from demoflow.loaders.census import load_ownership_rates, ownership_rate
from demoflow.loaders.constants import CENTRAL_ASSUMPTIONS, CONSTANTS, SWEEP_GRID
from demoflow.loaders.isq import load_population
from demoflow.loaders.living_arrangement import (
    couple_share, living_alone_rate, load_living_arrangement,
)

# --- spec §5's PINNED reconciliation cohort ------------------------------------------
# "roll a 75-year-old owner cohort forward one decade, where the cohort's household-state
# and sex composition is the one the INITIALIZATION EQUATIONS produce on the committed data
# vintage for MTL_RMR" (spec:241-250). Every coordinate below is that sentence; none is a
# free knob. START_YEAR and SCENARIO are the two the spec sentence does NOT fix — see
# `test_decade_retention_in_band_gross_backstop` for why each is what it is.
RECON_GEOGRAPHY = Geography.MTL_RMR
RECON_AGE = 75                      # band entry — the cohort ENTERS the modelled band here
RECON_START_YEAR = 2035
RECON_SCENARIO = Scenario.REFERENCE
RECON_POP_WORKBOOK = "pop-as-rmr-base.xlsx"


def _flat_qx(qm, qf):
    return lambda age, gender, year: qm if gender == "M" else qf


def _spec_pinned_entry_cohort() -> Stock:
    """The age-75 MTL_RMR owner cohort spec §5 pins the reconciliation band against, DERIVED
    from the committed vintage — never chosen.

    Every input is cited: single-year ISQ population at age 75 (REFERENCE scenario), the
    per-sex living-arrangement rates from `living_arrangement.json`, the 75+ collective share
    anchor, and the maintainer-denominated ownership rate from `ownership_by_geo_age.json`.
    They run through Task 18's `initialize_households` unchanged, so the band assertion
    downstream cannot be made to pass by picking a mix — moving it means moving cited data.

    THE OWNER FIELDS, not the totals: spec §5 excludes `Other` (persons living with others)
    from the owner-unit stock as presumptive non-maintainers, and `HouseholdInit` carries no
    `owner_other` for exactly that reason.

    BUILT HERE RATHER THAN IN `demoflow.cohort`, on `init.py`'s own recorded precedent — that
    module EXPORTS its aggregate gate rather than inventing a caller for it. Production's
    cohort builder is Task 29's pipeline `_init_stock` (plan:4677-4687), which assembles the
    same call from the same loaders over the 75+ AGGREGATE; until it exists, this is where
    the reconciliation gate's caller obligation (gates.py, codex r9-F4) is discharged. When
    Task 29 lands, this helper is the thing that folds into it, not a second builder to keep.
    """
    pop = load_population(RECON_POP_WORKBOOK)
    rows = pop[(pop["geography"] == RECON_GEOGRAPHY)
               & (pop["scenario"] == RECON_SCENARIO)
               & (pop["year"] == RECON_START_YEAR)
               & (pop["age"] == RECON_AGE)]
    # The scenario filter is LOAD-BEARING and stated: the workbook carries all three ISQ
    # scenarios on the same lattice, so an unfiltered slice sums three populations. It would
    # leave the MIX (and therefore the retention) untouched while tripling the counts — a
    # defect no band assertion can see, which is why it is filtered rather than trusted.
    assert not rows.empty, f"no ISQ rows for {RECON_GEOGRAPHY.value} {RECON_SCENARIO.value} " \
                           f"{RECON_START_YEAR} age {RECON_AGE}"
    pop_by_sex = {s: float(rows[rows["sex"] == s]["population"].sum()) for s in ("M", "F")}

    la = load_living_arrangement()
    h = initialize_households(
        pop_by_sex,
        living_alone_rate_by_sex={s: living_alone_rate(la, RECON_GEOGRAPHY, RECON_AGE, s)
                                  for s in ("M", "F")},
        couple_share_by_sex={s: couple_share(la, RECON_GEOGRAPHY, RECON_AGE, s)
                             for s in ("M", "F")},
        collective_share=CONSTANTS["collective_share_75plus"].value,
        ownership_rate=ownership_rate(load_ownership_rates(), RECON_GEOGRAPHY, RECON_AGE),
    )
    return Stock(couple=h.owner_couple, solo_m=h.owner_solo_m, solo_f=h.owner_solo_f)


def test_roll_one_year_conserves_mass_and_routes_widows():
    s = Stock(couple=1000.0, solo_m=0.0, solo_f=0.0)
    nxt, exits = roll_one_year(s, age=75, year=2035, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    # widows (one-dies) retained as Solo, NOT exited; both-die + living_exit are exits.
    assert nxt.solo_m == pytest.approx(1000 * 0.02 * 0.98)   # 19.6
    assert nxt.solo_f == pytest.approx(1000 * 0.02 * 0.98)   # 19.6
    assert nxt.couple == pytest.approx(1000 * 0.98 * 0.98 * 0.90)  # 864.36
    total_out = nxt.couple + nxt.solo_m + nxt.solo_f + exits["estate"] + exits["living"]
    assert total_out == pytest.approx(1000.0)


def test_decade_retention_in_band_gross_backstop():
    """Spec §5's reconciliation gate, discharged on the composition the gate REQUIRES and
    cannot itself check. Retention is STATE-DEPENDENT, so the band judges a bare float only
    against a pinned mix (gates.py's caller obligation, codex r9-F4) — this is that discharge,
    and the tranche's only live `check_reconciliation` call on real rolled output.

    THE ENVELOPE IS A GROSS-ERROR BACKSTOP, never the exactly-once proof — and the blindness is
    WIDER than the ≈0.25 figure the spec originally carried. Spec §5's FIGURE CORRECTION (ruling
    O, 2026-08-08) is the first line below; it is reproduced here on this cohort rather than
    quoted, and the two neighbouring readings are recorded with it because "applying the
    decrement twice" admits three arithmetics and a reader who assumes the wrong one mis-reads
    the margin. All measured 2026-08-08, start year 2035, retention at q_live 0.06 / 0.085 / 0.11:
      * THE SPEC'S FIGURE — the per-sex hazard DOUBLED (q_x → 2·q_x, q_live untouched): 0.3900 /
        0.3001 / 0.2293. INSIDE [0.20, 0.40] at EVERY q_live in the band, and ≈0.25 is where the
        axis's HIGH end lands, not its low end. Spec §5:193 states exactly the 0.3900 / 0.2293
        endpoints of this row.
      * THE SEQUENTIAL READING — the CPM decrement applied twice as survival (1-q_x)² per year:
        0.3920 / 0.3016 / 0.2305. Second order apart from the row above (2q - q² vs 2q) and it
        changes no verdict; recorded so the ≈0.002 gap is not mistaken for a discrepancy.
      * THE WHOLE TRANSITION twice — what `test_double_decrement_mutation_changes_pinned_oracle`
        below actually performs, q_live doubled along with mortality — 0.2111 / 0.1241 / 0.0719:
        in band ONLY at the low end, which is where ≈0.25 is recognizable.
    THE SPEC'S OTHER PAIR (§5:195, ruling O's inversion evidence: correct 0.4565 vs doubled
    0.3724 at q_live = 0.06) is the SAME doubled-hazard mutant at START YEAR 2021, not 2035 —
    re-measured here, 2021 gives exactly 0.4565 / 0.3724 and 2035 gives 0.4655 / 0.3900. Both
    spec sites reproduce; only the start year differs, and it is unstated there.
    The conclusion the sentence serves is unchanged and strengthened under every reading: a gross
    mortality double-count hides inside this band. Exactly-once lives in the stock-flow equation
    plus that mutation test, never here.

    q_live IS THE RUN CONTRACT VALUE, `CENTRAL_ASSUMPTIONS["q_live_per_year"]` = 0.085, not
    `annualize_q_live(0.36)`'s raw 0.0853899. decrements.py records why: the raw return moves
    the run's numbers while `assumptions_hash()` stays byte-identical, so a gate discharged on
    it would certify a cohort the run never rolls.

    THE TWO COORDINATES SPEC §5 DOES NOT FIX, and why neither is a cherry-pick:
      * START YEAR 2035 — the plan body's start year, kept. Measured 2026-08-08 on the
        committed vintage, the derived-composition decade retention runs 0.3505 (start 2021),
        0.3529 (2025), 0.3552 (2030), 0.3571 (2035), 0.3589 (2040), 0.3593 (2041) — every
        start year in band, and the whole span sits ≈0.04 clear of the upper edge. The pin
        selects a number, not a verdict.
      * SCENARIO REFERENCE — the headline run's scenario; LOW/HIGH are the sweep's axis, not
        this gate's. Stated at `_spec_pinned_entry_cohort`, where it is also the filter that
        stops three scenarios summing into one cohort.

    MEASURED 2026-08-08: retention 0.357114 on a mix of 39.6% Couple / 18.6% Solo_m / 41.7%
    Solo_f owner units — each figure the 1-dp rounding of its OWN measurement (39.6485 /
    18.6177 / 41.7338, which sum to exactly 100.0), so the row reading 99.9 is that rounding
    and never a missing state: the row is NOT sum-adjusted. Couple previously read 39.7 here by
    rounding twice (39.6485 → 39.65 → 39.7). Asserted as BAND MEMBERSHIP, not as that
    value — the value belongs to Task 23's oracle fixture, and pinning it twice makes two sites
    that can drift.
    """
    retention = roll_cohort_decade(
        start_age=RECON_AGE, start_year=RECON_START_YEAR,
        q_live=CENTRAL_ASSUMPTIONS["q_live_per_year"], qx=q_at,
        initial=_spec_pinned_entry_cohort(),
    )
    lo, hi = RECONCILIATION_BAND
    assert lo <= retention <= hi
    check_reconciliation(retention)   # no raise


def test_pure_couple_decade_retention_exceeds_band_hi():
    """NEGATIVE CONTROL for the band above — the pin on why the composition is load-bearing
    rather than a formality.

    A PURE-COUPLE age-75 cohort rolled the same decade at the same q_live on the same live QC
    basis retains MORE than the band's upper edge: 0.4050 vs 0.40, measured 2026-08-08.

    MECHANISM: a couple unit is lost to mortality only when BOTH spouses die in the same year
    (q_m·q_f, second-order), while a Solo unit is lost on a single death — the widow branch
    RETAINS the unit as Solo of the surviving sex. The band is calibrated on the ALL-CAUSE MIX
    (Myers 0.26-0.31, widened), so an all-couple cohort sits above it. Same-day measurement of
    the three pure states: Couple 0.4050, Solo_f 0.3334, Solo_m 0.3084 — the derived mix lands
    at 0.3571 between them.

    THE BAND-HI COMPARISON IS A MEASURED MARGIN, NOT A STRUCTURAL INEQUALITY, and the docstring
    says so because a reader who assumes otherwise will misdiagnose a RED here. Measured
    2026-08-08 along q_live's OWN declared axis (`SWEEP_GRID["q_live_per_year"]` = (0.06, 0.11),
    test_q_live.py), pure-couple decade retention runs 0.5249 (q=0.06) / 0.4050 (0.085, the run
    contract) / 0.3103 (0.11): it clears band-hi by +0.005 at the run contract and falls BELOW
    band-hi at the band's high endpoint. Across start years 2021-2041 the margin runs +0.0014
    (2021, thinnest) to +0.0062 (2041). Move q_live along that axis and this line goes RED —
    that is the margin closing on a stated axis, never the mechanism breaking.

    THE STRUCTURAL CLAIM THE MECHANISM DOES SUPPORT is the second assert, ADDED ALONGSIDE the
    first (never in place of it) because the margin assert alone would leave the mechanism pinned
    only where the margin happens to hold: pure-couple retention EXCEEDS the derived mix's,
    everywhere. FINAL owner units are LINEAR in the initial stock — `roll_one_year` maps every
    state through coefficients fixed by (age, year, q_live, qx) and never by the stock — so in
    exact arithmetic retention(mix) = Σ w_i · retention(pure_i) over the mix's initial shares w_i.
    (Retention itself is a RATIO of two such functionals: degree-0 homogeneous, NOT linear.) That
    identity is measured through `roll_cohort_decade` and holds to float64 rounding, not
    bit-exactly — the span is stated in ULP COUNTS rather than a decimal render, because at this
    magnitude the render rounds BELOW the span it would bound: |Δ| = 1 ULP at start 2035 /
    q_live 0.085, and ≤ 2 ULP across start years 2021-2041 (exactly 0.0 at 9 of the 21, 1 ULP at
    8, and 2 ULP at 4 — starts 2023, 2024, 2039, 2040 — where max |Δ| is exactly 2**-53). Every
    retention lies in [0.25, 0.5), so one ULP is 2**-54 throughout; the residual is float64
    rounding in the weighted sum, never a modelling gap. The mix is therefore
    a CONVEX COMBINATION of the three pure states, of which Couple MEASURES as the strict maximum
    (0.4050 vs Solo_f 0.3334 / Solo_m 0.3084, above) — the inequality holds wherever the mix
    carries any non-couple weight. It is asserted at THREE LEGS — both
    `SWEEP_GRID["q_live_per_year"]` endpoints plus the run contract (0.06 / 0.085 / 0.11) — which
    is precisely the axis along which the FIRST assert's margin closes and inverts, so the
    mechanism stays pinned where the margin no longer is. Measured over
    26 q_live values × 21 start years: 546/546, no exceptions.

    RED-CHECKED 2026-08-08 on THREE mutants, all applied probe-side (a pytest plugin rebinding the
    `partition_*` names inside `demoflow.cohort.rollforward` — no module was edited to make a RED).
    (a) and (b) are shown non-redundant IN BOTH DIRECTIONS:
      * one-dies routed to an ESTATE EXIT instead of a retained Solo — the widow branch this
        docstring's MECHANISM paragraph names — inverts the (b) inequality at every q_live in the
        band, measured THROUGH `roll_cohort_decade` with the mutant live: pure-couple 0.3272 /
        0.2499 / 0.1894 against mix 0.3871 / 0.2956 / 0.2241 at q_live 0.06 / 0.085 / 0.11.
        IN-TEST it surfaces as an (a) failure instead — pure-couple collapses to 0.2499 and (a)
        is evaluated first. Both asserts hold the mutant; only the earlier one gets to report it,
        which is why the bullet below is the one that actually separates them.
      * Solo units never take a living exit (`partition_solo` living_exit → remain) — (b) is NOT
        redundant with (a): pure-couple rises to 0.4719 so (a) stays GREEN, while the mix rises to
        0.7075 (q=0.06) / 0.6649 (run contract) and (b) fires — reported at q_live = 0.06, a leg
        the single-leg form of this assert never evaluated.
      * the new widow made LIVING-EXIT-ELIGIBLE in the transition year (spec §5 forbids exactly
        this) — the converse case: (a) fires at 0.3918 while (b) HOLDS at all three legs
        (pure-couple 0.5130 / 0.3918 / 0.2970 vs mix 0.4608 / 0.3519 / 0.2667). (a) is not
        redundant with (b) either; the band-hi margin is the only thing that sees this one.
    NOT DEMONSTRATED, recorded so the loop is not over-claimed: no mutant was found for which (b)
    fires ONLY at a sweep endpoint (four tried, including two q_live-coupled ones). The three legs
    widen the pin along the declared axis; they are not known to add a catch the run-contract leg
    misses. The inequality's robustness is the convexity argument above, not a leg count.

    THIS ASSERTION REPLACES A FALSE ONE (steering ruling N). The plan body asserted
    `lo <= retention <= hi` on THIS pure-couple cohort; at the run-contract q_live it measures
    out of band — ABOVE hi — at every start year 2021-2041, because it read a
    composition-sensitive band against the one composition the band does not describe. The
    false test becomes the mechanism pin.

    NO `check_reconciliation` HERE, deliberately, and now on TWO grounds: ruling N makes the
    discharge above the tranche's only live gate call on real rolled output, and ruling O (spec
    §5 amendment #6) rules the gate onto the CENTRAL-ASSUMPTION run ONLY — the second assert
    below rolls at both sweep-grid endpoints, exactly the legs the gate must not judge. Wrapping
    the gate in a `pytest.raises` here would read as a second discharge — and the claim being
    pinned is about the MECHANISM's direction, which the bare comparison states exactly.
    """
    mix = _spec_pinned_entry_cohort()      # built ONCE: the loaders, not the roll, are the cost
    pure_couple = Stock(couple=1000.0)
    q_contract = CENTRAL_ASSUMPTIONS["q_live_per_year"]

    def decade(initial: Stock, q_live: float) -> float:
        return roll_cohort_decade(
            start_age=RECON_AGE, start_year=RECON_START_YEAR,
            q_live=q_live, qx=q_at, initial=initial,
        )

    # (a) MEASURED MARGIN — the run contract ONLY (+0.005). It closes along q_live's own axis.
    assert decade(pure_couple, q_contract) > RECONCILIATION_BAND[1]
    # (b) STRUCTURAL — convex-combination maximum, at both sweep endpoints AND the run contract,
    #     so the mechanism stays pinned on the legs where (a) has already inverted.
    q_lo, q_hi = SWEEP_GRID["q_live_per_year"]
    for q in (q_lo, q_contract, q_hi):
        assert decade(pure_couple, q) > decade(mix, q), f"pure-couple <= mix at q_live={q}"


def test_double_decrement_mutation_changes_pinned_oracle():
    # codex r7-F5: exactly-once is proven by ORACLE EXACTNESS, not the envelope. Flat q -> the
    # correct single transition pins couple=864.36 / owner_units=903.56; applying the transition
    # TWICE (the re-anchor double-count) STRICTLY changes those pinned values -> detectable.
    once, _ = roll_one_year(Stock(couple=1000.0), age=80, year=2040, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    assert once.couple == pytest.approx(864.36) and once.owner_units == pytest.approx(903.56)
    twice, _ = roll_one_year(once, age=80, year=2040, q_live=0.10, qx=_flat_qx(0.02, 0.02))
    assert twice.couple < once.couple                     # exact inequality: couple strictly shrinks
    assert twice.owner_units < once.owner_units           # the pinned oracle CHANGES under the mutation


def test_roll_one_year_guards_its_own_age_domain():
    """Run-10 carry, re-measured live here: the mortality engine does NOT refuse an
    out-of-domain age — ages 0-17 return a SILENT 0.0 and negatives clamp into that same
    range, so an under-75 call yields a zero-mortality roll-forward that looks like a
    plausible number. Spec §5 applies the CPM decrement to 75+ ONLY (pre-75 mortality is
    ISQ-embedded and disjoint), so the roll-forward guards its own domain rather than
    relying on the engine to raise. The live asserts are the guard's REASON, kept
    executable so a future engine that starts refusing shows up here as a change.

    THE UPPER END IS PINNED HERE TOO, and for the opposite reason: `roll_one_year` deliberately
    does NOT bound above (spec §8's 100+ absorbing bucket is the multi-year roller's design), so
    the engine's TERMINAL age is reachable through this function. It returns EXACTLY 1.0 there,
    which `partition_couple`/`partition_solo` accept only because `_check_unit`'s domain is the
    INCLUSIVE [0,1]. test_q_live.py::test_boundary_and_monotonicity argues from that measurement
    that the two decrements.py guards must differ; this is the assertion under the argument, so
    the necessity claim is executable rather than prose.
    """
    assert q_at(17, "M", 2035) == 0.0    # live boundary: silent zero, no raise
    assert q_at(-5, "F", 2035) == 0.0    # negatives clamp to age 0 -> same silent zero
    for bad_age in (-5, 0, 17, 74):
        with pytest.raises(CalibrationError):
            roll_one_year(Stock(couple=1000.0), age=bad_age, year=2035, q_live=0.10, qx=q_at)
    # 75 is band entry and IS in domain -- the guard must not swallow the first modeled age.
    nxt, _ = roll_one_year(Stock(couple=1000.0), age=75, year=2035, q_live=0.10, qx=q_at)
    assert nxt.couple > 0.0
    # Terminal age: a REAL q of exactly 1.0, reached through the unbounded upper end.
    assert q_at(120, "M", 2035) == 1.0 and q_at(120, "F", 2035) == 1.0
    end, exits = roll_one_year(Stock(couple=1000.0), age=120, year=2035, q_live=0.10, qx=q_at)
    assert end.owner_units == 0.0                          # no raise, and no survivors
    assert exits["estate"] == pytest.approx(1000.0)        # every unit to estate, mass conserved
    assert exits["living"] == 0.0                          # nobody survives to take a living exit
