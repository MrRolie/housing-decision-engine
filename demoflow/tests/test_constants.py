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
)


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


def test_collective_share_is_fraction_and_refinable():
    a = CONSTANTS["collective_share_75plus"]
    assert 0.0 <= a.value <= 1.0 and a.flag == "borrowed_prior"   # probe-refinable, [0,1]-valid


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
    assert "Ryu" not in a.source and "JAPA" not in a.source
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
    assert "spec §7 closed enum" not in str(typo.value), (
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
    assert "ONLY key read from this dict" not in source
    # what the tree actually entails, asserted rather than described
    read_through = {"phi_voluntary", "estate_eventual_fraction", "estate_lag_years"}
    assert read_through <= set(CENTRAL_ASSUMPTIONS)
    assert (listings.PHI_VOLUNTARY, listings.ESTATE_EVENTUAL_FRACTION, listings.ESTATE_LAG_YEARS) == (
        CENTRAL_ASSUMPTIONS["phi_voluntary"], CENTRAL_ASSUMPTIONS["estate_eventual_fraction"],
        CENTRAL_ASSUMPTIONS["estate_lag_years"])


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
    for false_claim in ("§7's closed enum", "§7 closed enum"):
        assert false_claim not in doc, (
            f"module docstring attributes the anchor-flag vocabulary to spec §7 ({false_claim!r}); "
            f"ANCHOR_FLAGS is {sorted(ANCHOR_FLAGS)} — neither §7 emitter enum (spec:352-353 "
            f"ScenarioPrior rows, spec:434 rankings rows)")


# ---------------------------------- identity coverage: the two UNCITED money-path literals
#
# STRESS-GATE FINDING F2 (run 32): `pipeline.ROLL_AGE = 80` and `p_nonimm = read_ownership(geo,
# 40)` were bare literals on the money path — no anchor anywhere, and outside BOTH identity
# tokens, so editing either moved every emitted `mean_ed_*` number (measured: -55% and -66% at
# HORS_RMR) under a byte-identical envelope. Lifting them here closes both halves at once: the
# citation lands beside the value, and `assumptions_hash` covers it.
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
    assert set(MODEL_CHOICES) == {"p_nonimm_age", "roll_age"}
    for k, cite in MODEL_CHOICE_PROVENANCE.items():
        assert len(cite.strip()) > 20, f"{k}: provenance too thin: {cite!r}"


def test_the_model_choices_carry_the_same_values_the_pipeline_literals_did():
    """The lift changes IDENTITY COVERAGE, never a number: 40 and 80 are the shipped values,
    and the pipeline now READS them instead of re-declaring them."""
    import demoflow.pipeline as pipeline

    assert MODEL_CHOICES == {"p_nonimm_age": 40, "roll_age": 80}
    for key, value in MODEL_CHOICES.items():
        assert isinstance(value, int) and not isinstance(value, bool), f"{key} is not an age"
    assert pipeline.ROLL_AGE == MODEL_CHOICES["roll_age"]
    assert pipeline.P_NONIMM_AGE == MODEL_CHOICES["p_nonimm_age"]


def test_the_pipeline_holds_no_second_declaration_of_either_choice():
    """THE REVERT PIN over the two exact spellings this task removed. Read on the SOURCE —
    the binding above proves the names agree, not that the old literal is gone.

    IT IS NOT THE CHECK THAT MAKES THE SINGLE-SOURCE RULE BIND, and saying so here is the
    point: two frozen strings are spelling-bound by construction, so a second declaration
    spelled any other way walks straight past them (measured). The discriminating check is
    the read-through guard below. This one stays because a REVERT to either original line is
    the likeliest way the lift regresses, and a source read names that precisely."""
    from pathlib import Path

    import demoflow.pipeline as pipeline

    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    for gone in ("read_ownership(geo, 40)", "ROLL_AGE = 80"):
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

    THE CALL SITES RIDE THESE MODULE GLOBALS (`age=ROLL_AGE`, `read_ownership(geo,
    P_NONIMM_AGE)`), resolved at call time, so pinning the binding covers every use of the NAME.
    A future edit swapping a name for a bare literal AT a call site is outside any test of this
    shape — a new-diff defect, the same residual `test_listings.py` carries.
    """
    import demoflow.pipeline as pipeline

    sentinels = {"roll_age": 78, "p_nonimm_age": 33}
    for key, value in sentinels.items():
        monkeypatch.setitem(MODEL_CHOICES, key, value)
    try:
        moved = importlib.reload(pipeline)

        assert moved.ROLL_AGE == 78
        assert moved.P_NONIMM_AGE == 33
    finally:
        monkeypatch.undo()                # restore the dict BEFORE re-executing the module
        importlib.reload(pipeline)

    assert pipeline.ROLL_AGE == MODEL_CHOICES["roll_age"]
    assert pipeline.P_NONIMM_AGE == MODEL_CHOICES["p_nonimm_age"]


def test_the_model_choices_are_unbanded_and_stay_out_of_the_run_contract_dicts():
    """They are DISCRETE MODEL CHOICES WITH NOTHING TO SWEEP. Keeping them out of
    CENTRAL_ASSUMPTIONS/SWEEP_GRID is what keeps the run contract's strongest gate honest —
    "an unswept central assumption silently claims rank_stable it never tested". Being unbanded
    is NOT what disqualifies them (ruling V's `headship_shape` is unbanded, central and swept):
    these two carry no band AND no second admissible value, so there is nothing a sweep leg
    could move them to, and they must not pretend otherwise."""
    assert not set(MODEL_CHOICES) & set(CENTRAL_ASSUMPTIONS)
    assert not set(MODEL_CHOICES) & set(SWEEP_GRID)


def test_the_assumptions_hash_covers_the_model_choices(monkeypatch):
    """The identity half. Both literals moved every emitted number under an unchanged hash
    before this task; now either one moving RE-MINTS the artifact identity."""
    base = assumptions_hash()
    monkeypatch.setitem(MODEL_CHOICES, "roll_age", 85)
    assert assumptions_hash() != base
    monkeypatch.undo()
    monkeypatch.setitem(MODEL_CHOICES, "p_nonimm_age", 60)
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
    where finding F4 found them."""
    from demoflow.demand.immigrant_inputs import resolved_selection
    from demoflow.geography import Geography

    selection = resolved_selection()
    assert set(selection) == {g.value for g in Geography}
    for pair in selection.values():
        assert set(pair) == {"immigrant_headship", "ownership_ratio",
                             "headship_provenance", "ratio_provenance"}
