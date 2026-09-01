"""Task 15 — versioned scalar anchors (spec §4) + the run contract's central/sweep
selection (spec §7 r8-F1).

The plan's seven contract tests are kept VERBATIM (test names 1-7 below). The tests after
them close gaps the plan's bodies left open, each named at its defect:

  * the plan asserted `collective_share` is "asserted ∈[0,1]" but its module carried NO
    assertion — the plan test only read back the literal the plan itself typed, so a later
    executor's bad edit (the plan explicitly schedules one: "the executor updates
    collective_share_75plus when P3 lands a firmer figure") could not be caught. The guard
    now lives in `Anchor.__post_init__`; these tests fire it.
  * the charter carry "every constant carries its documented anchor (source + figure +
    date); a constant without an anchor is a defect" had no enforcement anywhere.
  * the charter carry "the fresh-arrival (~0.21) vs settled (~0.91) fork lands HERE as
    documented constants with citations" was absent from the plan's module entirely.
  * probes/P4-immigrant-ownership-diff.md §4a instructs Task 15 by name: "Task 15's
    robustness sweep grid must span BOTH axes, not the fifth-year cross-province spread
    alone" — the plan's SWEEP_GRID carried no immigrant-ratio axis at all.
"""
import importlib
import json

import pytest

from demoflow.errors import LoaderError
from demoflow.loaders.constants import (
    ANCHOR_FLAGS,
    CENTRAL_ASSUMPTIONS,
    CENTRAL_PROVENANCE,
    CONSTANTS,
    MODEL_CHOICE_PROVENANCE,
    MODEL_CHOICES,
    SWEEP_GRID,
    Anchor,
    assumptions_hash,
    resolved_constants,
)

from ._prose_binding import says


# ---------------------------------------------------------------- plan contract tests

def test_cmhc_senior_sale_anchor():
    a = CONSTANTS["cmhc_senior_sale_5yr"]
    assert isinstance(a, Anchor)
    assert a.value == 0.36 and a.as_of and a.source


def test_myers_retention_envelope_and_reconciliation_band():
    assert CONSTANTS["myers_retention_envelope"].value == (0.26, 0.31)
    assert CONSTANTS["reconciliation_band"].value == (0.20, 0.40)


def test_couple_share_is_NOT_a_constant():
    # folded-spec blocker fix: no invented couple_share default (§5 per-sex, §11.3 cited-or-raise).
    assert "couple_share" not in CONSTANTS


def test_collective_share_is_pinned_to_its_OWN_BAND_and_still_refinable():
    """TIGHTENED FROM `0.0 <= value <= 1.0` TO THE ANCHOR'S OWN DECLARED BAND (spec amendment
    #20(D), 2026-08-22), and the reason the looser pin was right BEFORE that amendment is exactly
    why it is only half-right after it.

    The looseness was deliberate: this module's header SCHEDULES the edit ("the executor updates
    collective_share_75plus when P3 lands a firmer figure"), so a pin at 0.04 would close the
    refinement path the plan asks for. Run 49 kept it on that argument and added the hash
    coverage instead — the fix for an INVISIBLE move. Amendment #20(D) then ruled the anchor into
    the declared sweep, which changes what the pin has to do: the band `(0.02, 0.08)` is now the
    sweep's own endpoint pair, so a value OUTSIDE it is not a refinement at all — it is a central
    value the declared grid does not bracket, and `test_central_assumptions_and_hash`'s
    `lo <= central <= hi` leg would be the only thing in the tree to notice. The band pin refuses
    0.5 (which the old pin admitted) while admitting every in-band figure P3 could land, which is
    all the scheduled refinement needs. `Anchor.__post_init__` already refuses a value outside its
    own band; this is the leg that pins WHICH band, so widening the band to admit a wild value is
    a PR-visible act here rather than a silent one there."""
    a = CONSTANTS["collective_share_75plus"]
    assert a.band == (0.02, 0.08) and a.flag == "borrowed_prior"
    assert a.band[0] <= a.value <= a.band[1]        # in-band refinement stays open; 0.5 does not


def test_living_alone_vitrine_fallback_band():
    a = CONSTANTS["living_alone_vitrine"]
    assert a.value == 0.28 and a.band == (0.24, 0.34) and a.flag == "borrowed_prior"


def test_mifi_pr_plan_level():
    assert CONSTANTS["mifi_pr_annual_plan"].value == 45000


def test_central_assumptions_and_hash():
    assert CENTRAL_ASSUMPTIONS["q_live_per_year"] == 0.085
    assert CENTRAL_ASSUMPTIONS["estate_eventual_fraction"] == 0.725
    assert CENTRAL_ASSUMPTIONS["estate_lag_years"] == 2
    # Every central value is REACHABLE FROM ITS DECLARED GRID, and the two grid shapes are
    # checked as the different things they are (sharpened at ruling V). A BANDED axis declares
    # an ordered interval and its central value lies within it; a CATEGORICAL axis declares the
    # admissible set and its central value must be a MEMBER of it — an ordering assertion there
    # would be reading lexicographic accident as a band.
    for k, endpoints in SWEEP_GRID.items():
        central = CENTRAL_ASSUMPTIONS[k]
        if isinstance(central, str):
            assert central in endpoints, f"{k}: central {central!r} is not an admissible member"
        else:
            lo, hi = endpoints
            assert lo <= central <= hi
    assert isinstance(assumptions_hash(), str) and len(assumptions_hash()) == 16
    assert assumptions_hash() == assumptions_hash()   # deterministic


# ------------------------------------------- the anchor guard (charter carry, enforced)

def test_every_anchor_carries_a_documented_source_and_as_of():
    """Charter carry: a constant without an anchor is a DEFECT. Enforced over the whole
    registry, so a future entry cannot land undocumented."""
    for key, a in CONSTANTS.items():
        assert a.as_of.strip(), f"{key}: empty as_of"
        assert a.source.strip(), f"{key}: empty source"
        assert len(a.source) > 20, f"{key}: source too thin to be a citation: {a.source!r}"


def test_anchor_without_as_of_or_source_raises():
    with pytest.raises(LoaderError, match="as_of"):
        Anchor(0.5, "", "some documented source string that is long enough")
    with pytest.raises(LoaderError, match="source"):
        Anchor(0.5, "2021", "   ")


def test_fraction_unit_asserts_unit_interval_on_value_and_band():
    """The guard the plan's read-back test could not provide: a BAD EDIT raises at import."""
    with pytest.raises(LoaderError, match=r"fraction outside \[0,1\]"):
        Anchor(1.4, "2021", "a documented fraction-valued source", unit="fraction")
    with pytest.raises(LoaderError, match=r"fraction outside \[0,1\]"):
        Anchor(0.5, "2021", "a documented fraction-valued source",
               band=(0.4, 1.9), unit="fraction")


def test_ratio_unit_admits_above_one_and_rejects_negative():
    """codex r7-F8: the immigrant/non-immigrant ownership RATIO is NOT a fraction — it can
    validly exceed 1 (P4 measured New Brunswick at 1.033). Only the PRODUCT p_imm binds [0,1]."""
    assert Anchor(1.033, "2021", "a documented ratio-valued source", unit="ratio").value == 1.033
    with pytest.raises(LoaderError, match="negative"):
        Anchor(-0.1, "2021", "a documented ratio-valued source", unit="ratio")


def test_band_must_bracket_its_central_value_and_be_ordered():
    with pytest.raises(LoaderError, match="outside its own band"):
        Anchor(0.5, "2021", "a documented fraction-valued source", band=(0.6, 0.7))
    with pytest.raises(LoaderError, match="band endpoints out of order"):
        Anchor(0.5, "2021", "a documented fraction-valued source", band=(0.7, 0.6))


def test_myers_envelope_cites_the_paper_that_actually_carries_the_figure():
    """The 0.26-0.31 decade retention envelope belongs to Myers & Simmons (Fannie Mae), 'The
    Coming Exodus of Older Homeowners' (~2018) — the dossier's cohort-retention source
    (demo_literature.md:30, '75+ -> 85+ only ~26-31% remain after ten years'). Myers & Ryu,
    JAPA 74(1) Winter 2008 is a DIFFERENT paper (seller age-structure / senior:working-age
    ratio +67%, demo_literature.md:26) and carries NO retention figure. Attributing the
    envelope to it is a manufactured citation in the one module whose product IS provenance;
    the plan's honest-vague as_of='literature' must not be replaced by precise-and-unsupported."""
    a = CONSTANTS["myers_retention_envelope"]
    # `says` rather than `not in` (run 48's forbid census, applied to the second site it left
    # case-sensitive in this file). The forbidden subject is a CITATION — an author's name and a
    # journal acronym — written into prose whose house style is emphasis capitals, so
    # "Myers & RYU, JAPA 74(1)" satisfied the bare membership test while shipping exactly the
    # manufactured citation this gate exists to refuse.
    assert not says(a.source, "Ryu") and not says(a.source, "JAPA")
    assert "Simmons" in a.source and "Fannie Mae" in a.source
    assert "2018" in a.as_of


def test_anchor_flag_vocabulary_is_closed_to_provenance_flags_only():
    """The vocabulary an ANCHOR may carry is NOT either of spec §7's emitter enums, and the
    guard must not claim it is. §7 declares TWO different closed enums — ScenarioPrior rows
    {borrowed_prior, ra_proxy, never_relax_stress} (spec:352-353) and rankings rows
    {borrowed_prior, ra_proxy, closed_cohort_exceedance} (spec:434, third member by steering
    ruling K). A union of the two is NEITHER, so a raise attributing that union to spec §7
    ships a false statement about the spec, and an emitter importing it would admit a member
    its own enum forbids. Discriminator: an anchor flag says where this VALUE came from; the
    omitted members say what an output ROW means."""
    assert ANCHOR_FLAGS == frozenset({"borrowed_prior"})
    with pytest.raises(LoaderError, match="unknown flag") as typo:
        Anchor(0.5, "2021", "a documented fraction-valued source", flag="borowed_prior")
    # an output-row flag is not an anchor-provenance flag
    with pytest.raises(LoaderError, match="unknown flag"):
        Anchor(0.5, "2021", "a documented fraction-valued source", flag="ra_proxy")
    with pytest.raises(LoaderError, match="unknown flag"):
        Anchor(0.5, "2021", "a documented fraction-valued source", flag="never_relax_stress")
    # `says` rather than `not in` (the run-48 forbid census's own remedy, applied to the ONE
    # site it left case-sensitive in this file). This forbid's subject is a PROSE clause inside a
    # raise message, in a corpus whose house style is emphasis capitals — and the sibling gate 60
    # lines up already routes the SAME two literals through `says` for the docstring copy, so the
    # message copy was the un-widened half of one claim. "SPEC §7 CLOSED ENUM" satisfied the bare
    # membership test.
    assert not says(str(typo.value), "spec §7 closed enum"), (
        "the raise must not attribute this set to spec §7 — it is neither §7 enum")


# ---------------------------------------- the immigrant-ratio fork (binding charter carry)

def test_immigrant_ratio_fork_lands_both_readings_with_citations():
    """Charter carry: the fresh-arrival (~0.21) vs settled (~0.91) fork lands HERE as
    documented constants with citations. P4 rules between NONE of the tenure readings, so
    BOTH land; neither is silently promoted to the headline."""
    fresh = CONSTANTS["immigrant_ownership_ratio_fresh_arrival"]
    settled = CONSTANTS["immigrant_ownership_ratio_settled"]
    year3 = CONSTANTS["immigrant_ownership_ratio_year3"]

    assert (fresh.value, fresh.band) == (0.210, (0.155, 0.268))
    assert (settled.value, settled.band) == (0.911, (0.765, 1.033))
    assert (year3.value, year3.band) == (0.614, (0.451, 0.754))

    for a in (fresh, settled, year3):
        assert a.unit == "ratio"                 # r7-F8: >1 is valid, so NOT a fraction
        assert a.flag == "borrowed_prior"        # P4 §4c: geography + metric + tenure borrows
        assert "46-28-0001" in a.source          # the controller-verified catalogue


def test_immigrant_ratio_sweep_span_survives_the_axis_move_to_the_join_table():
    """P4 §4a/§4b instruct Task 15 by name: the sweep must span BOTH the tenure axis and the
    cross-province axis — [0.155, 1.033]. The AXIS MOVED at Task 25b (rulings S/T): the ratio
    is no longer one scalar in the run contract but a MEASURED PER-GEOGRAPHY value in
    `demand/immigrant_inputs.py`, so Task 29 perturbs it as a uniform join-table override
    rather than as a `SWEEP_GRID` member. The SPAN stays here and stays P4-sourced — culling
    it would break the sweep's own source, which is why P4's three anchors also stay."""
    span = CONSTANTS["immigrant_ownership_ratio_sweep_span"]
    assert span.value == (0.155, 1.033)
    fresh = CONSTANTS["immigrant_ownership_ratio_fresh_arrival"]
    settled = CONSTANTS["immigrant_ownership_ratio_settled"]
    assert span.value[0] == fresh.band[0] and span.value[1] == settled.band[1]
    # the endpoints Task 29's override must read — one source of truth, wherever it is applied
    assert SWEEP_GRID.get("immigrant_ratio_center") is None, (
        "the run contract must not carry an immigrant-ratio scalar beside the per-geography "
        "join table — two declarations of one quantity is the drift this dict's own comment "
        "forbids")


# --------------------------------------------------- run-contract completeness + coherence

def test_q_live_annual_is_the_annualized_cmhc_anchor_in_matching_units():
    """Plan-code defect: `q_live_five_year` carried the 5-YEAR value 0.36 with the ANNUAL
    band (0.06, 0.11) — mismatched units on one anchor. Spec §5 attaches that band to the
    ANNUALIZED rate. A tripwire (§4: 'tripwires compare realized values against them')
    comparing a refreshed CMHC 5-year rate against an annual band would fire CROSSED
    permanently. The anchor now carries the annualized value its band describes."""
    five = CONSTANTS["cmhc_senior_sale_5yr"]
    annual = CONSTANTS["q_live_annual"]
    assert round(1 - (1 - five.value) ** (1 / 5), 3) == annual.value       # the §5 arithmetic
    assert annual.band == SWEEP_GRID["q_live_per_year"]
    assert annual.value == CENTRAL_ASSUMPTIONS["q_live_per_year"]
    assert "q_live_five_year" not in CONSTANTS                             # duplicate removed


def test_every_central_assumption_has_a_declared_grid_entry():
    """spec §7 run contract (r8-F1): a Tranche-1 run evaluates EVERY central assumption at its
    central value, the declared alternatives entering ONLY the robustness sweep. The plan's grid
    omitted phi_voluntary (spec §5 band [0.7, 1.0]) and the immigrant ratio.

    NAMED FOR WHAT IT ENFORCES, sharpened at ruling V when the CATEGORICAL `headship_shape`
    joined both dicts: this gate is the KEYSET half of the membership rule, which is stated once
    — `loaders/constants.py`'s MODEL_CHOICES header — and is "is there something to sweep", not
    "is it a float". The SHAPE half (a banded axis declares an ordered interval, a categorical
    one an admissible set) is `test_central_assumptions_and_hash` above."""
    assert SWEEP_GRID["phi_voluntary"] == (0.7, 1.0)
    assert set(SWEEP_GRID) == set(CENTRAL_ASSUMPTIONS), (
        "an unswept central assumption silently claims rank_stable it never tested — banded "
        "or categorical (the rule: loaders/constants.py, MODEL_CHOICES header)")


def test_every_central_assumption_has_documented_provenance():
    """Charter carry applied to the run-contract dict too: CENTRAL_ASSUMPTIONS holds bare
    floats, so its anchors live in CENTRAL_PROVENANCE. Keysets must match — a new central
    value cannot land undocumented."""
    assert set(CENTRAL_PROVENANCE) == set(CENTRAL_ASSUMPTIONS)
    for k, cite in CENTRAL_PROVENANCE.items():
        assert len(cite.strip()) > 20, f"{k}: provenance too thin: {cite!r}"


def test_the_unruled_immigrant_ratio_center_is_GONE_from_the_run_contract():
    """0.62 was pinned by the plan PRE-P4, matched none of P4's tenure anchors (year-1 0.210 /
    year-3 0.614 / year-5 0.911), was read by no code, and is SUPERSEDED outright by rulings
    S/T: the ratio is measured PER GEOGRAPHY and lives in the join table. It must be gone from
    all THREE dicts at once — a half-deletion trips the keyset-equality gates below, and a
    surviving scalar is the second declaration `CENTRAL_ASSUMPTIONS`'s own comment forbids
    (`assumptions_hash` would then identify a selection nothing selects)."""
    for dictionary in (CENTRAL_ASSUMPTIONS, SWEEP_GRID, CENTRAL_PROVENANCE):
        assert "immigrant_ratio_center" not in dictionary

    # and the quantity it stood in for really is served, per geography, from the join table
    from demoflow.demand.immigrant_inputs import resolve_immigrant_inputs
    from demoflow.geography import Geography

    ratios = {g.value: resolve_immigrant_inputs(g).ownership_ratio for g in Geography}
    assert ratios["MTL_RMR"] == 0.9634 and ratios["QC_RMR"] == 0.8910
    assert len(set(ratios.values())) > 1, (
        "a single ratio for every geography would be the scalar this deletion removed, "
        "wearing the join table's clothes")


def test_the_fresh_arrival_anchor_points_at_the_ruling_that_refuted_its_reading():
    """Amendment #7 promised this pointer and nothing had yet made the edit. The anchor's own
    text argues the arrival-window reading is "right if p_imm captures arrival-window
    ownership" — §6 REFUSES that reading from its own equations (I2 subtracts the full
    surviving arrival stock every year while the demand chain credits each cohort once, so
    the arrival-year credit stands in for the cohort's whole residency and an arrival-window
    rate would systematically undercount it). The constant STAYS — it is the sweep span's
    floor and P4's measurement is untouched — but a reader meeting it must not meet only the
    half that recommends it."""
    cite = CONSTANTS["immigrant_ownership_ratio_fresh_arrival"].source
    assert "§6" in cite
    assert "REFUSED" in cite or "refuted" in cite.lower()
    assert "46-28-0001" in cite                       # the measurement itself is undisturbed


def test_the_central_dict_does_not_claim_a_single_reader_it_no_longer_has():
    """Run-15 staleness, of the class this file already guards for the flag vocabulary: the
    comment above CENTRAL_PROVENANCE said `q_live_per_year` was "the ONLY key read from this
    dict". `cohort/listings.py` has bound THREE keys read-through since run 15. A wrong why
    outdamages a missing one — and this one tells the next editor that deleting a member is
    safe because nothing reads it."""
    from pathlib import Path

    import demoflow.cohort.listings as listings
    import demoflow.loaders.constants as constants_module

    source = Path(constants_module.__file__).read_text(encoding="utf-8")
    # `says` rather than `not in` (run 48): the claim this pins GONE is a comment, and a
    # comment re-typed as "the ONLY KEY READ FROM THIS DICT" — or merely re-wrapped across two
    # `#` lines — walked past the bare membership test. Both axes, and nothing wider.
    assert not says(source, "ONLY key read from this dict")
    # what the tree actually entails, asserted rather than described
    read_through = {"phi_voluntary", "estate_eventual_fraction", "estate_lag_years"}
    assert read_through <= set(CENTRAL_ASSUMPTIONS)
    assert (listings.PHI_VOLUNTARY, listings.ESTATE_EVENTUAL_FRACTION, listings.ESTATE_LAG_YEARS) == (
        CENTRAL_ASSUMPTIONS["phi_voluntary"], CENTRAL_ASSUMPTIONS["estate_eventual_fraction"],
        CENTRAL_ASSUMPTIONS["estate_lag_years"])


def test_the_seventh_sweep_axis_is_bound_READ_THROUGH_to_its_anchor():
    """Spec amendment #20(D) made `collective_share_75plus` a declared robustness axis, and BOTH
    halves of its declaration are read through from `CONSTANTS` — the central value from
    `.value`, the sweep endpoints from `.band`.

    EQUALITY IS NOT THE CHECK. A literal `0.04` typed into `CENTRAL_ASSUMPTIONS` beside a
    `(0.02, 0.08)` typed into `SWEEP_GRID` passes every equality read while the ANCHOR is free to
    move away from both — the second-declaration defect this module's own header forbids ("a
    consumer that REDECLARES one of these values as its own literal moves the run's numbers while
    the hash stays byte-identical").

    SO THE CHECK IS A SOURCE MUTATION, EXECUTED IN AN ISOLATED NAMESPACE. `cohort/listings.py`'s
    read-through gate reloads ITS module under a mutated `CENTRAL_ASSUMPTIONS`; that shape is not
    available here because the dict under test lives in THIS module, and `importlib.reload`ing it
    rebinds the objects every other test in this file holds. Executing the mutated SOURCE in a
    fresh namespace is the same discriminator with no global effect: only a read-through binding
    moves when the anchor's own literals do."""
    import pathlib as _pathlib

    import demoflow.loaders.constants as constants_module

    source = _pathlib.Path(constants_module.__file__).read_text(encoding="utf-8")
    value_decl = '"collective_share_75plus": Anchor(\n        0.04, "2021",'
    band_decl = 'band=(0.02, 0.08), flag="borrowed_prior"),'
    for decl in (value_decl, band_decl):
        assert source.count(decl) == 1, (
            f"the anchor declaration {decl!r} is not a unique span of constants.py — this "
            "mutation would land somewhere else and prove nothing")
    mutated = source.replace(value_decl, value_decl.replace("0.04", "0.05")).replace(
        band_decl, 'band=(0.03, 0.07), flag="borrowed_prior"),')

    namespace = {"__name__": "constants_readthrough_probe",
                 "__file__": constants_module.__file__}
    exec(compile(mutated, constants_module.__file__, "exec"), namespace)   # noqa: S102

    assert namespace["CONSTANTS"]["collective_share_75plus"].value == 0.05   # the edit landed
    assert namespace["CENTRAL_ASSUMPTIONS"]["collective_share_75plus"] == 0.05, (
        "the central value did NOT follow the anchor — `CENTRAL_ASSUMPTIONS` is carrying a "
        "redeclared literal, so an anchor edit would move the sweep and not the headline")
    assert namespace["SWEEP_GRID"]["collective_share_75plus"] == (0.03, 0.07), (
        "the sweep endpoints did NOT follow the anchor's band — the declared grid is carrying a "
        "redeclared pair, so an anchor edit would move the headline and not the sweep")
    # ...and the leg vocabulary the emitted `rows_moved` map is bound to moves WITH the grid, so
    # a published count can never key off a leg the declared grid no longer carries.
    assert "collective_share_75plus=0.07" in namespace["sweep_leg_labels"]()

    # UNMUTATED, the live module agrees with its anchor — the green half of the same claim.
    assert CENTRAL_ASSUMPTIONS["collective_share_75plus"] == \
        CONSTANTS["collective_share_75plus"].value
    assert SWEEP_GRID["collective_share_75plus"] == CONSTANTS["collective_share_75plus"].band


def test_the_declared_grid_and_its_leg_vocabulary_agree_in_BOTH_directions():
    """`declared_sweep_grid()` is the ONE declaration the producer sweeps and the emitter binds
    (`output/artifacts.py` keys the emitted `rows_moved` map to `sweep_leg_labels()`), so the two
    must not be able to disagree — a leg with no admissible key could not be published, and an
    admissible key for no declared leg is a position a run could smuggle a count into."""
    from demoflow.loaders.constants import declared_sweep_grid, sweep_leg_label, sweep_leg_labels

    grid = declared_sweep_grid()
    assert set(grid) == set(SWEEP_GRID) | {"immigrant_ownership_ratio"}
    expected = {sweep_leg_label(a, e) for a, eps in grid.items() for e in eps}
    assert sweep_leg_labels() == expected
    assert len(sweep_leg_labels()) == 2 * len(grid) == 14, (
        "seven declared axes at both declared endpoints is fourteen legs — a collision in the "
        "label spelling would silently merge two legs into one published count")


def test_module_docstring_does_not_misattribute_the_flag_vocabulary_to_spec_7():
    """Regression, r2 finding: the accepted F2 fix (ANCHOR_FLAGS is NOT a spec §7 enum)
    landed in the runtime raise and the vocabulary comment but the identical false statement
    survived VERBATIM in the module docstring, 24 lines above the comment that denies it.
    test_anchor_flag_vocabulary_is_closed_to_provenance_flags_only above reads the EXCEPTION
    message only, so it stayed green straight through the defect — this test discriminates
    the docstring site. It matters here specifically because provenance IS this module's
    product: a provenance module that misstates the spec on its own first screen teaches
    every reader the wrong thing before they reach the correction."""
    import demoflow.loaders.constants as constants_module

    doc = constants_module.__doc__
    # CASE-FOLDED and whitespace-collapsed (run 48). This docstring is hard-wrapped at 96
    # columns, so the false attribution is one reflow away from spanning a line break — the
    # exact defect this test was written for survived VERBATIM once already, which is why the
    # forbid must not also depend on where the line happens to end or on which letters are
    # capitalised.
    for false_claim in ("§7's closed enum", "§7 closed enum"):
        assert not says(doc, false_claim), (
            f"module docstring attributes the anchor-flag vocabulary to spec §7 ({false_claim!r}); "
            f"ANCHOR_FLAGS is {sorted(ANCHOR_FLAGS)} — neither §7 emitter enum (spec:352-353 "
            f"ScenarioPrior rows, spec:434 rankings rows)")


# ---------------------------------- identity coverage: the two UNCITED decision-critical literals
#
# STRESS-GATE FINDING F2 (run 32): `pipeline.ROLL_AGE = 80` and `p_nonimm = read_ownership(geo,
# 40)` were bare literals on the money path — no anchor anywhere, and outside BOTH identity
# tokens, so editing either moved every emitted `mean_ed_*` number (measured: -55% and -66% at
# HORS_RMR) under a byte-identical envelope. Lifting them here closes both halves at once: the
# citation lands beside the value, and `assumptions_hash` covers it.
#
# THE SECOND MEMBER IS A SPAN SINCE OPERATOR RULING X2 (2026-08-21): `p_nonimm_age = 40` became
# `p_nonimm_range = (25, 54)`, because the immigrant leg now reads the span's household-weighted
# aggregate instead of the band an age landed in. The KEY changed and the coverage claim did
# not: the span is still a discrete uncited model choice on the money path, so it still belongs
# in this dict and still has to move `assumptions_hash`. Dropping it from the dict rather than
# renaming it would have re-opened exactly the F2 hole above — an uncovered literal reachable
# from `pipeline.P_NONIMM_RANGE`.
#
# THEY ARE DELIBERATELY NOT `CENTRAL_ASSUMPTIONS` MEMBERS. That dict's contract is a central
# value WITH A DECLARED ALTERNATIVE — `test_every_central_assumption_has_a_declared_grid_entry`
# holds its keyset EQUAL to `SWEEP_GRID`'s — and neither of these has one: no spec §5 band, and
# no second admissible value either. Inventing a band would be a fabricated anchor; adding a
# sweep axis would silently widen the robustness sweep's declared grid, which is a modelling
# decision and not an identity fix. (The rule this reads off lives in the module under test,
# `loaders/constants.py`'s MODEL_CHOICES header; it is not restated here.)

def test_every_model_choice_has_documented_provenance():
    """The charter carry over the third dict too: keysets match, and a bare value cannot land.
    Both entries are honestly marked UNCITED today — an honest absence beats an invented
    anchor, and it is the marker a future citation replaces."""
    assert set(MODEL_CHOICE_PROVENANCE) == set(MODEL_CHOICES)
    assert set(MODEL_CHOICES) == {"p_nonimm_range", "roll_age"}
    for k, cite in MODEL_CHOICE_PROVENANCE.items():
        assert len(cite.strip()) > 20, f"{k}: provenance too thin: {cite!r}"


def test_the_model_choices_carry_the_same_values_the_pipeline_literals_did():
    """The lift changed IDENTITY COVERAGE, never a number, and the SHAPE pin below is what keeps
    that true across a ruling: `roll_age` is still one age, and `p_nonimm_range` is the ordered
    age SPAN ruling X2 put in place of an age (`(25, 54)`, not 40). Both are still read
    through, never re-declared."""
    import demoflow.pipeline as pipeline

    assert MODEL_CHOICES == {"p_nonimm_range": (25, 54), "roll_age": 80}

    def is_age(v):
        return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 200

    assert is_age(MODEL_CHOICES["roll_age"]), "roll_age is not an age"
    lo, hi = MODEL_CHOICES["p_nonimm_range"]
    assert is_age(lo) and is_age(hi) and lo < hi, "p_nonimm_range is not an ordered age span"
    assert pipeline.ROLL_AGE == MODEL_CHOICES["roll_age"]
    assert pipeline.P_NONIMM_RANGE == MODEL_CHOICES["p_nonimm_range"]


def test_the_pipeline_holds_no_second_declaration_of_either_choice():
    """THE REVERT PIN over the two exact spellings this task removed. Read on the SOURCE —
    the binding above proves the names agree, not that the old literal is gone.

    IT IS NOT THE CHECK THAT MAKES THE SINGLE-SOURCE RULE BIND, and saying so here is the
    point: three frozen strings are spelling-bound by construction, so a second declaration
    spelled any other way walks straight past them (measured). The discriminating check is
    the read-through guard below. This one stays because a REVERT to one of these exact lines
    is the likeliest way the lift regresses, and a source read names that precisely.

    THE FIRST ENTRY WAS DEAD AND IS REPOINTED (2026-08-21 audit). `read_ownership(geo, 40)` was
    the pre-ruling-X2 immigrant-leg read; ruling X2 removed the AGE from `MODEL_CHOICES`, so no
    edit could put that literal back without also re-adding a key this file's other pins would
    red on — the string had become unreachable and the grep unfalsifiable. It is replaced by
    `read_ownership(geo, ROLL_AGE)`, which IS reachable: it is the exact spelling of the ruling
    X1 revert — `_standing_stock` valuing the whole lumped 75+ bucket at one band read again —
    and that revert leaves the pre-re-mint suite otherwise green (measured).

    THIS GREP IS A REVERT TRIPWIRE, NOT THE GATE. A mutant spelled any other way
    (`read_ownership(geo, MODEL_CHOICES["roll_age"])`) walks past it. The gates that catch the
    behaviour whatever it is spelled as are the X1/X2 wiring pins in `tests/test_pipeline.py`
    and the union value pins in `tests/test_census_ownership.py`; both were verified to red under
    the mutants this string only happens to name."""
    from pathlib import Path

    import demoflow.pipeline as pipeline

    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    for gone in ("read_ownership(geo, ROLL_AGE)", "ROLL_AGE = 80", "P_NONIMM_AGE"):
        assert gone not in source, f"pipeline.py still declares {gone!r} as its own literal"


def test_the_model_choices_are_bound_read_through_not_redeclared(monkeypatch):
    """THE DISCRIMINATING CHECK — what makes constants.py's "the rule above binds each of them
    identically" materially true for this dict and not just claimed.

    EVERY OTHER INSTRUMENT HERE IS VALUE-BLIND. `pipeline.ROLL_AGE == MODEL_CHOICES["roll_age"]`
    reads the same dict twice, so a consumer that redeclares its own literal EQUAL to today's
    value passes it; the grep above holds two frozen strings. Measured on a scratchpad copy: a
    plain appended second declaration, and one spelled to evade the grep, each left the whole
    suite's failure set byte-identical — the exact hash-bypass this section exists to close,
    since `assumptions_hash` would then cover a dict the run no longer reads.

    Same shape and same reason as `tests/test_listings.py`'s guard over `CENTRAL_ASSUMPTIONS`:
    mutate the dict, RE-EXECUTE the consumer, assert the values MOVED. A module holding its own
    literal re-executes to the shipped number and REDs here.

    THE CALL SITES RIDE THESE MODULE GLOBALS (`age=ROLL_AGE`, and `P_NONIMM_RANGE` unpacked
    where `_ownership_reader` forms the span's aggregate), resolved at call time, so pinning the
    binding covers every use of the NAME.
    A future edit swapping a name for a bare literal AT a call site is outside any test of this
    shape — a new-diff defect, the same residual `test_listings.py` carries.
    """
    import demoflow.pipeline as pipeline

    sentinels = {"roll_age": 78, "p_nonimm_range": (30, 44)}
    for key, value in sentinels.items():
        monkeypatch.setitem(MODEL_CHOICES, key, value)
    try:
        moved = importlib.reload(pipeline)

        assert moved.ROLL_AGE == 78
        assert moved.P_NONIMM_RANGE == (30, 44)
    finally:
        monkeypatch.undo()                # restore the dict BEFORE re-executing the module
        importlib.reload(pipeline)

    assert pipeline.ROLL_AGE == MODEL_CHOICES["roll_age"]
    assert pipeline.P_NONIMM_RANGE == MODEL_CHOICES["p_nonimm_range"]


def test_the_model_choices_are_unbanded_and_stay_out_of_the_run_contract_dicts():
    """They are DISCRETE MODEL CHOICES WITH NOTHING TO SWEEP. Keeping them out of
    CENTRAL_ASSUMPTIONS/SWEEP_GRID is what keeps the run contract's strongest gate honest —
    "an unswept central assumption silently claims rank_stable it never tested". Being unbanded
    is NOT what disqualifies them (ruling V's `headship_shape` is unbanded, central and swept):
    these two carry no band AND no second admissible value, so there is nothing a sweep leg
    could move them to, and they must not pretend otherwise."""
    assert not set(MODEL_CHOICES) & set(CENTRAL_ASSUMPTIONS)
    assert not set(MODEL_CHOICES) & set(SWEEP_GRID)


# ------------------------------- identity coverage: the FIRST TWO payload members, which had none
#
# MEASURED GAP (run 52). `assumptions_hash` hashes five selections and THREE of them had a direct
# regression: `model_choices`, `immigrant_inputs` and `constants` (below). `central` and `sweep` —
# the two ORIGINAL members, the ones every other test's `base = assumptions_hash()` silently
# assumes are live — had NONE. Measured: repoint either key at an import-time literal snapshot
# (`def assumptions_hash(_central=dict(CENTRAL_ASSUMPTIONS), _sweep=dict(SWEEP_GRID))`, then read
# the defaults) and the shipped token stays EQUAL at `16d6c13342c8c335`, the member's own move
# goes INERT, and the FULL 1226-test suite passes. Nothing at HEAD is false; this is the gate that
# was missing.
#
# WHAT RIDES ON IT. `CENTRAL_ASSUMPTIONS` carries BARE LITERALS for `q_live_per_year`,
# `phi_voluntary`, `estate_eventual_fraction`, `estate_lag_years` and `headship_shape` — only
# `collective_share_75plus` reads through `CONSTANTS` — and `SWEEP_GRID` is the same shape. So
# five central values and ten sweep endpoints have these two members as their ONLY hash coverage.
#
# THE FAILURE SCENARIO, spelled out because the perturbation is otherwise unmotivated: a refactor
# snapshots one of the keys, undetected because nothing checks it. Later an editor moves
# `CENTRAL_ASSUMPTIONS["phi_voluntary"]` to 0.7 — its OWN declared sweep endpoint, an in-band edit
# needing no new citation. The emitted `rows_moved` prices that leg at 3 of 8 published ranks, so
# the golden reds, and the attribution cascade routes the reader to "the CODE moved — the envelope
# is IDENTICAL", which `artifacts/README.md`'s own reading table calls the default-defect case.
#
# THE PERTURBED KEYS ARE BARE LITERALS ON PURPOSE. `collective_share_75plus` reads through
# `CONSTANTS`, so moving IT would re-mint the token through the `constants` member even with
# `central` snapshotted — a green that proves nothing about the member this test names.

def test_the_assumptions_hash_covers_a_moved_CENTRAL_assumption(monkeypatch):
    """The `central` payload member, asserted live rather than assumed."""
    base = assumptions_hash()
    assert CENTRAL_ASSUMPTIONS["phi_voluntary"] != 0.7                  # a real move, not a no-op
    assert 0.7 in SWEEP_GRID["phi_voluntary"], (
        "0.7 is chosen because it is this axis' OWN declared endpoint — the cheapest legitimate "
        "edit there is, and the one that needs no citation")
    monkeypatch.setitem(CENTRAL_ASSUMPTIONS, "phi_voluntary", 0.7)
    assert assumptions_hash() != base, (
        "a HEADLINE banded assumption moved to its own sweep endpoint and re-minted nothing — "
        "the `central` payload member is not reading the live dict, so the golden's red would be "
        "attributed to a code change")


def test_the_assumptions_hash_covers_a_moved_SWEEP_endpoint(monkeypatch):
    """The `sweep` payload member. A moved endpoint is a moved `rank_stable` verdict.

    `estate_lag_years` is perturbed rather than `q_live_per_year` because the latter's endpoints
    are pinned EQUAL to `CONSTANTS["q_live_annual"].band` by `tests/test_q_live.py`, so a move
    there could re-mint through the `constants` member instead of this one. The point of the test
    is WHICH member carries it."""
    base = assumptions_hash()
    assert SWEEP_GRID["estate_lag_years"] != (1, 4)                     # a real move, not a no-op
    monkeypatch.setitem(SWEEP_GRID, "estate_lag_years", (1, 4))
    assert assumptions_hash() != base, (
        "a declared sweep ENDPOINT moved and re-minted nothing — the `sweep` payload member is "
        "not reading the live grid, and a narrowed or widened endpoint is exactly the edit that "
        "legitimately flips an emitted `rank_stable` boolean")


def test_the_assumptions_hash_covers_the_model_choices(monkeypatch):
    """The identity half. Both literals moved every emitted number under an unchanged hash
    before this task; now either one moving RE-MINTS the artifact identity."""
    base = assumptions_hash()
    monkeypatch.setitem(MODEL_CHOICES, "roll_age", 85)
    assert assumptions_hash() != base
    monkeypatch.undo()
    monkeypatch.setitem(MODEL_CHOICES, "p_nonimm_range", (25, 44))
    assert assumptions_hash() != base


# ------------------------------- identity coverage: the RULED immigrant join-table selection
#
# QUANT-GATE FINDING F4 (run 32): the headship and ownership-ratio pairs that amendments
# #13/#14 exist to govern sat outside BOTH identity tokens — being source literals they are
# not in `data_vintage.source_hashes`, and `assumptions_hash` hashed CENTRAL_ASSUMPTIONS +
# SWEEP_GRID only. So a RULED value could move and re-mint nothing, which is the
# citation-coupling chain failing at the artifact boundary. Measured consequence: a ratio
# change of that class reorders up to 7 of 8 geographies.

def test_the_assumptions_hash_covers_a_moved_ruled_immigrant_value(monkeypatch):
    import dataclasses

    from demoflow.demand import immigrant_inputs
    from demoflow.geography import Geography

    base = assumptions_hash()
    row = immigrant_inputs._TABLE[Geography.MTL_RMR]
    monkeypatch.setitem(immigrant_inputs._TABLE, Geography.MTL_RMR,
                        dataclasses.replace(row, ownership_ratio=0.5))
    assert assumptions_hash() != base, "a ruled ratio moved and re-minted nothing"
    monkeypatch.undo()
    monkeypatch.setitem(immigrant_inputs._TABLE, Geography.MTL_RMR,
                        dataclasses.replace(row, immigrant_headship=0.60))
    assert assumptions_hash() != base, "a ruled headship moved and re-minted nothing"


def test_the_assumptions_hash_covers_a_join_table_provenance_relabel(monkeypatch):
    """The provenance TOKENS ride the hash beside the digits, deliberately: they are CONSUMED —
    `pipeline._borrowed_inputs` reads them and a `borrowed_prior` on either field puts a flag
    on the emitted row — so a relabel moves artifact bytes. A closed three-member vocabulary
    costs no reword noise, unlike the `source` citation (next test)."""
    import dataclasses

    from demoflow.demand import immigrant_inputs
    from demoflow.geography import Geography

    base = assumptions_hash()
    row = immigrant_inputs._TABLE[Geography.MTL_RMR]
    monkeypatch.setitem(immigrant_inputs._TABLE, Geography.MTL_RMR,
                        dataclasses.replace(row, ratio_provenance="borrowed_prior"))
    assert assumptions_hash() != base


def test_the_assumptions_hash_ignores_a_reworded_join_table_citation(monkeypatch):
    """The stated RESIDUAL, asserted rather than described: the hash covers the SELECTION, not
    the prose. Coupling identity to citation text would re-mint every artifact on a reworded
    note — and the prose is already bound where it belongs, on the digits, by
    `tests/test_i2.py`'s coupling to P8's DECISION tokens."""
    import dataclasses

    from demoflow.demand import immigrant_inputs
    from demoflow.geography import Geography

    base = assumptions_hash()
    row = immigrant_inputs._TABLE[Geography.MTL_RMR]
    monkeypatch.setitem(immigrant_inputs._TABLE, Geography.MTL_RMR,
                        dataclasses.replace(row, source=row.source + " (reworded, same digits)"))
    assert assumptions_hash() == base


def test_the_assumptions_hash_selection_names_every_modeled_geography():
    """The join table resolves EVERY modeled member or raises (§6), so the covered selection
    must span the same set — a partial payload would leave the un-named geographies exactly
    where finding F4 found them.

    THE POOLED COUNTS ARE DERIVED FROM `PooledOwnership`'s OWN FIELDS, never re-typed here
    (amendment #24(A)). Those counts are CONSUMED — `B` is computed from them and the immigrant
    leg divides by it — so a member that joined the class without joining this payload would be a
    live input outside the identity token, which is verbatim the F4 finding this test exists for.
    Deriving the expected keys means a fourth population group lands in the token or reds here."""
    import dataclasses as dc

    from demoflow.demand.immigrant_inputs import PooledOwnership, resolved_selection
    from demoflow.geography import Geography

    selection = resolved_selection()
    assert set(selection) == {g.value for g in Geography}
    expected = ({"immigrant_headship", "ownership_ratio",
                 "headship_provenance", "ratio_provenance"}
                | {f"pooled_{field.name}" for field in dc.fields(PooledOwnership)})
    assert len(dc.fields(PooledOwnership)) > 1, "the pooled payload derivation would be vacuous"
    for pair in selection.values():
        assert set(pair) == expected


# ----------------------------------- identity coverage: THIS MODULE'S OWN ANCHOR REGISTRY
#
# ROUND-3 AUDIT HIGH FINDING (2026-08-22): `CONSTANTS` sat outside BOTH identity tokens, and one
# of its members is a LIVE HEADLINE INPUT — `pipeline._household_stock` reads
# `CONSTANTS["collective_share_75plus"].value` into `initialize_households` for EVERY 75+ stock
# slice. Measured by full-pipeline execution: setting that anchor to 0.08 — its OWN declared band
# high, an in-band move needing no new citation — REORDERS the published ranking (HORS_RMR 4->5,
# MTL_RMR 5->4; LAVAL_RA13's ED +82.9%, HORS_RMR's +304%) while `assumptions_hash` stayed
# `fe7c631104c5182b` and `data_vintage` stayed byte-identical, which routes a consumer to the
# reading table's "the code moved" bucket — a WRONG verdict. THAT MEASUREMENT IS DATED AT
# the forbid-casing hardening commit, BEFORE the identity-envelope widening, and `fe7c631104c5182b` is the hash OF THOSE
# BYTES — a historical token, not this tree's. On these bytes the anchor is inside the payload
# (below) and inside the declared sweep, so a reader who finds the hash MOVING has found the fix.
#
# THE HASH IS THE FIX FOR THE INVISIBLE MOVE; THE PIN IS THE FIX FOR THE OUT-OF-BAND ONE, AND
# THEY ARE DIFFERENT DEFECTS. This module's header RECORDS the edit as scheduled ("the executor
# updates collective_share_75plus when P3 lands a firmer figure"), so an EXACT pin at 0.04 is
# still refused here — it would close the path the plan schedules and leave the next uncovered
# anchor exactly where this one was. What run 49 left, and amendment #20(D) then made only
# half-right, was the WIDTH: `0.0 <= value <= 1.0` admitted 0.5, which since the amendment is not
# a refinement at all but a central value the declared grid does not bracket. So the sibling
# `test_collective_share_is_pinned_to_its_OWN_BAND_and_still_refinable` above now pins the
# anchor's OWN band (0.02, 0.08) — every in-band figure P3 could land still passes — and this
# payload leg covers the move the pin cannot see, an in-band edit that re-mints nothing.

def _replaced_anchor(monkeypatch, key, **changes):
    import dataclasses
    monkeypatch.setitem(CONSTANTS, key, dataclasses.replace(CONSTANTS[key], **changes))


def test_the_assumptions_hash_covers_a_moved_anchor_VALUE(monkeypatch):
    """The measured finding, as a gate: the in-band move that reordered the ranking now moves
    the token. 0.08 is the anchor's OWN band high — the cheapest legitimate edit there is."""
    base = assumptions_hash()
    _replaced_anchor(monkeypatch, "collective_share_75plus", value=0.08)
    assert CONSTANTS["collective_share_75plus"].value == 0.08          # the edit really landed
    assert assumptions_hash() != base, (
        "a LIVE headline input moved inside its own declared band and re-minted nothing — the "
        "artifact's reading table would then attribute the moved ED values to a code change")


def test_the_assumptions_hash_covers_a_moved_anchor_BAND(monkeypatch):
    """The BAND is covered too, and it is not decoration: `tests/test_q_live.py` binds
    `Q_LIVE_BAND == CONSTANTS["q_live_annual"].band == SWEEP_GRID["q_live_per_year"]`, so a band
    IS the robustness sweep's endpoint pair — and `immigrant_ownership_ratio_sweep_span` feeds
    the emitted `rank_stable` verdict directly. A band that moved under a byte-identical token
    would flip an emitted boolean into the "the code moved" bucket."""
    base = assumptions_hash()
    _replaced_anchor(monkeypatch, "q_live_annual", band=(0.05, 0.11))
    assert assumptions_hash() != base, "a moved sweep-endpoint band re-minted nothing"
    monkeypatch.undo()
    _replaced_anchor(monkeypatch, "immigrant_ownership_ratio_sweep_span", value=(0.3, 0.9))
    assert assumptions_hash() != base, (
        "the robustness sweep's own span moved and re-minted nothing — this is the residual "
        "`pipeline._sweep_legs`' section note named, and it feeds the EMITTED rank_stable")


def test_the_assumptions_hash_ignores_an_anchors_PROSE_AND_PROVENANCE(monkeypatch):
    """The scope of the payload, asserted rather than described — value and band, nothing else
    off the `Anchor`.

    The discriminator is the immigrant join table's: a field rides the payload when an emitter
    CONSUMES it. `source` is prose and coupling identity to prose re-mints every artifact on a
    reworded note (`assumptions_hash`'s own stated residual). `as_of` is a VINTAGE claim, which
    spec §7a parks in the Tranche-2 `data_vintage` shape — the other token. `flag` and `unit`
    are read by NOTHING outside `Anchor.__post_init__`: the `borrowed_prior` markers on an
    emitted rankings row come from the join table's per-field provenance, which
    `pipeline._borrowed_inputs` does read, and never from an anchor.

    IF AN EMITTER EVER CONSUMES AN ANCHOR `flag`, THIS ASSERT MUST INVERT — the join-table
    provenance tokens are inside the payload for exactly that reason, so the rule is already
    written down; what would change is which side of it `flag` falls on.
    """
    base = assumptions_hash()
    for changes in ({"source": CONSTANTS["q_live_annual"].source + " (reworded, same digits)"},
                    {"as_of": "2021 (re-dated, same figure)"},
                    {"flag": "borrowed_prior"},
                    {"unit": "ratio"}):
        monkeypatch.undo()
        _replaced_anchor(monkeypatch, "q_live_annual", **changes)
        assert assumptions_hash() == base, f"a non-consumed anchor field re-minted: {changes}"


def test_the_hashed_constants_payload_spans_the_WHOLE_registry_as_json_native_data():
    """Registry-wide, not an allowlist — and the reason is the finding itself.

    An allowlist of "the anchors that are live today" would be a SECOND declaration of which
    anchors matter, which is the shape that let `collective_share_75plus` sit outside; its
    failure mode is silent, because the next anchor added defaults to UNCOVERED. Registry-wide
    is fail-safe: a new anchor is covered with no edit to `assumptions_hash`. So the keyset
    equality below is the gate, and it is what a future anchor addition cannot walk past.
    """
    payload = resolved_constants()
    assert set(payload) == set(CONSTANTS)
    assert list(payload) == sorted(CONSTANTS), "the resolved payload is not sorted"
    for key, entry in payload.items():
        assert set(entry) == {"value", "band"}, f"{key}: payload shape moved"
    # JSON-NATIVE: `assumptions_hash` serializes this, and a tuple would hash as a list anyway —
    # the conversion is explicit so the "plain data" claim is literally true and a test can
    # compare it without tuple/list confusion.
    round_tripped = json.loads(json.dumps(payload, sort_keys=True))
    assert round_tripped == payload
    # the band-valued anchors really are the ones that arrive as sequences (non-vacuity)
    assert isinstance(payload["myers_retention_envelope"]["value"], list)
    assert payload["q_live_annual"]["band"] == [0.06, 0.11]
    assert payload["cmhc_senior_sale_5yr"]["band"] is None


def test_the_hash_stays_OUT_of_the_tripwire_and_generator_ledgers():
    """THE SCOPE DECISION ON THE THREE SELECTIONS THAT STAY OUTSIDE, recorded as a check.

    The round-3 audit enumerated six selections outside `assumptions_hash`. Three are `CONSTANTS`
    members and the registry-wide payload covers them. The other three stay out, and each for a
    reason that is about the LEDGER, not about convenience:

      * `pipeline.TRIPWIRE_BANDS` — every band is PUBLISHED per row as `band_low`/`band_high` in
        `tripwire_baseline.json`, so a move is self-announcing in the diff; the identity token
        exists for selections the output does NOT show. And hashing it would re-mint the
        RANKINGS' token for a verification-gate ruling that cannot touch a single ED — the
        mis-attribution `_run_identity` refuses in the other direction ("one token that moved
        for either cause answers neither question"), since both documents carry the same token.
      * `pipeline._TRIPWIRE_DECLARATIONS` — same ledger, AND SINCE SPEC AMENDMENT #21
        (2026-08-22) FOR THE SAME REASON RATHER THAN BESIDE IT. When run 49 ruled it out, its
        `freshness_years` / `source_kind` halves were emitted NOWHERE, so one ledger was excluded
        because it is published and the other was excluded alongside it while being published
        nowhere: the second exclusion rested on nothing, and an unsound reason left standing in
        the code is the class this module keeps re-finding. The amendment ruled PUBLISH, not hash
        — hashing a tripwire-only declaration would re-mint the RANKINGS' identity for a
        verification-gate ruling that cannot move a single ED, because both documents carry the
        same `assumptions_hash`. Both members now ride the row they govern
        (`tests/test_pipeline.py::test_the_published_tripwire_declarations_ARE_the_declarations`),
        which makes this bullet's argument TRUE for both ledgers instead of one.
      * `golden.GOLDEN_NOW_YEAR` / `GOLDEN_NOW_MONTH` — the GENERATOR's pin, not the run's
        selection. `run_pipeline` takes `now` as a parameter, so hashing the golden's constant
        would stamp the golden's clock into EVERY run's token: a CLI run at a different `now`
        would publish an identical token (a lie), and moving the golden pin would re-mint runs
        that never read it (a lie the other way). Covering the run's actual clock needs an
        envelope field — spec §7 closes the envelope, `output/artifacts.py` raises on an
        undeclared position, and `golden.py` already names the amendment. `constants` importing
        `golden` is also a hard cycle (`golden` -> `pipeline` -> `constants`).
    """
    import demoflow.golden as golden
    import demoflow.pipeline as pipeline

    base = assumptions_hash()
    for mutate in (
        lambda: pipeline.TRIPWIRE_BANDS.__setitem__("cmhc_senior_sale_5yr", (0.10, 0.90)),
        lambda: pipeline._TRIPWIRE_DECLARATIONS.__setitem__(
            "cmhc_senior_sale_5yr", (2021, 99, pipeline._TRIPWIRE_DECLARATIONS[
                "cmhc_senior_sale_5yr"][2])),
        lambda: setattr(golden, "GOLDEN_NOW_YEAR", 2099),
    ):
        saved_bands = dict(pipeline.TRIPWIRE_BANDS)
        saved_decls = dict(pipeline._TRIPWIRE_DECLARATIONS)
        saved_now = golden.GOLDEN_NOW_YEAR
        try:
            mutate()
            assert assumptions_hash() == base, (
                "a tripwire threshold or the golden's clock moved the RANKING's assumption "
                "token — that is the wrong ledger; see this test's docstring")
        finally:
            pipeline.TRIPWIRE_BANDS.clear(); pipeline.TRIPWIRE_BANDS.update(saved_bands)
            pipeline._TRIPWIRE_DECLARATIONS.clear()
            pipeline._TRIPWIRE_DECLARATIONS.update(saved_decls)
            golden.GOLDEN_NOW_YEAR = saved_now
    # the mutations really were mutations (non-vacuity), and the restore really restored
    assert pipeline.TRIPWIRE_BANDS["cmhc_senior_sale_5yr"] == (0.30, 0.42)
    assert golden.GOLDEN_NOW_YEAR == 2026
