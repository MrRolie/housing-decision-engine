"""The rankings table (spec §7b) — deterministic ordering, scenario-named fans, the CLOSED
flags enum, the typed rank_stable verdict and the emitted-row allowlist.

The first eight tests are the plan's Task-27 bodies, unchanged. Everything below
`# --- added guards` is added; each names the silent failure it kills, following
`balance/excess_demand.py`'s precedent for adding a guard beyond a plan body.

ONE DIVERGENCE FROM THE PLAN BODY IS DELIBERATE AND SPEC-RULED: the plan's
`RANKING_FLAGS_ALLOWED` carried TWO members; spec §7 (steering ruling K, 2026-08-07) closes the
rankings flags enum at THREE — `closed_cohort_exceedance` rides every ranking row of a geography
whose measured 75+ net-migration rate exceeded the 1 %/yr materiality cap. The plan body predates
the ruling; the spec rules. The plan's own assertion (`set(r.flags) <= RANKING_FLAGS_ALLOWED`)
holds either way, so no plan test needed changing.
"""
import json
import math

import pytest

from demoflow.geography import Geography, Scenario
from demoflow.output.rankings import (
    rank_geographies, refuse_cross_vintage, ranking_row, assert_rankings_row_valid,
    RANKINGS_ROW_FIELDS, RANKING_FLAGS_ALLOWED, GeoRanking,
    CLOSED_COHORT_EXCEEDANCE_MEMBERS, UNRESOLVED_INPUTS, exclude_from_rankings,
)
from demoflow.errors import CalibrationError


def _ed(ref, low, high):
    return {Scenario.REFERENCE: ref, Scenario.LOW: low, Scenario.HIGH: high}


# --- the plan's contract tests (Task 27, verbatim) ------------------------------------

def test_unique_ordering_with_exact_tie():
    ed = {
        Geography.MTL_RMR: _ed([-0.05, -0.03], [-0.08, -0.06], [-0.02, 0.00]),   # ref -0.04, Faible -0.07
        Geography.QC_RMR: _ed([-0.04, -0.04], [-0.05, -0.05], [-0.03, -0.01]),    # ref -0.04 (tie), Faible -0.05
        Geography.LANAUDIERE_RA14_PROXY: _ed([-0.03, -0.01], [-0.07, -0.05], [0.04, 0.02]),  # ref -0.02
        Geography.LAVAL_RA13: _ed([0.01, -0.01], [-0.02, -0.04], [0.03, 0.01]),   # ref 0.00
    }
    ranked = rank_geographies(ed)
    assert [r.geography for r in ranked] == [
        Geography.MTL_RMR,               # tie at -0.04 wins on Faible mean -0.07 < -0.05
        Geography.QC_RMR,
        Geography.LANAUDIERE_RA14_PROXY,
        Geography.LAVAL_RA13,
    ]
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_scenario_named_fan_fields_can_cross():
    # codex r6-F6: mean_ed_low is the FAIBLE mean, mean_ed_high the FORT mean — NOT min/max.
    # Faible +0.02, Fort -0.03 -> mean_ed_low (0.02) > mean_ed_high (-0.03): a legitimate crossing.
    ed = {Geography.MTL_RMR: _ed([-0.01], [0.02], [-0.03])}
    r = rank_geographies(ed)[0]
    assert r.mean_ed_low == pytest.approx(0.02)     # Faible, whatever the numeric order
    assert r.mean_ed_high == pytest.approx(-0.03)   # Fort
    assert r.mean_ed_low > r.mean_ed_high           # scenarios crossed; fields are scenario-named


def test_enum_order_final_tiebreak():
    ed = {
        Geography.QC_RMR: _ed([-0.04], [-0.05], [-0.03]),
        Geography.MTL_RMR: _ed([-0.04], [-0.05], [-0.03]),
    }
    assert [r.geography for r in rank_geographies(ed)] == [Geography.MTL_RMR, Geography.QC_RMR]


def test_ra_proxy_flagged_and_in_closed_enum():
    r = rank_geographies({Geography.LANAUDIERE_RA14_PROXY: _ed([-0.02], [-0.03], [-0.01])})[0]
    assert "ra_proxy" in r.flags and set(r.flags) <= RANKING_FLAGS_ALLOWED


def test_cross_vintage_comparison_refused():
    with pytest.raises(CalibrationError, match="vintage"):
        refuse_cross_vintage({"vintageA", "vintageB"})
    refuse_cross_vintage({"vintageA"})


def test_row_allowlist_exact_and_flag_enum_reject_crash_probability():
    r = rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])})[0]
    row = ranking_row(r)
    assert set(row) == RANKINGS_ROW_FIELDS
    assert_rankings_row_valid(row)                          # clean row: no raise
    with pytest.raises(ValueError, match="allowlist"):      # RED: extra forbidden field
        assert_rankings_row_valid({**row, "crash_probability": 0.35})
    with pytest.raises(ValueError, match="flag"):           # RED: smuggled through flags[]
        assert_rankings_row_valid({**row, "flags": ["crash_probability=0.35"]})


def test_rank_stable_is_typed_bool_not_a_flag_string():
    # codex r8-F1/r9-F1: the robustness-sweep verdict has a TYPED schema home, never a flag string.
    r = rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])},
                         rank_stable={Geography.MTL_RMR: False})[0]
    assert r.rank_stable is False
    row = ranking_row(r)
    assert row["rank_stable"] is False and isinstance(row["rank_stable"], bool)


def test_ordering_reverses_all_years_vs_projected_only():
    # codex r8-F3: the ranking domain (projected years only) is load-bearing — a pair whose order
    # REVERSES between an all-years average and a projected-only average. rank_geographies averages
    # whatever series it is given; the pipeline supplies the projected-only slice.
    all_years = {   # includes leading "estimation-year" values that pull the mean
        Geography.MTL_RMR: _ed([0.10, -0.06], [0.0], [0.0]),   # all-years ref mean +0.02
        Geography.QC_RMR: _ed([-0.01, -0.02], [0.0], [0.0]),   # all-years ref mean -0.015 -> QC rank 1
    }
    projected_only = {   # only the later projected values
        Geography.MTL_RMR: _ed([-0.06], [0.0], [0.0]),          # proj ref mean -0.06 -> MTL rank 1
        Geography.QC_RMR: _ed([-0.02], [0.0], [0.0]),           # proj ref mean -0.02
    }
    order_all = [r.geography for r in rank_geographies(all_years)]
    order_proj = [r.geography for r in rank_geographies(projected_only)]
    assert order_all[0] is Geography.QC_RMR and order_proj[0] is Geography.MTL_RMR   # reversed


# --- added guards ---------------------------------------------------------------------

def test_faible_tiebreak_decides_against_enum_order_and_against_the_fort_mean():
    # Spec §7b collapse rule: an exact REFERENCE tie breaks by the scenario-named FAIBLE mean,
    # and only then by enum order. The plan's tie fixture is CONFOUNDED on that clause — its
    # winner (MTL_RMR, enum index 0) wins by the Faible mean AND by enum order, so deleting the
    # Faible component from the sort key leaves the whole plan suite green (measured: 18 passed
    # with `key=(ref, enum)`). This fixture puts every candidate ordering rule AGAINST the specified one, so
    # only the specified one produces the asserted order:
    #   * enum order alone   -> MTL first (index 0 < 3)
    #   * insertion order    -> MTL first (inserted first below; sort is stable)
    #   * the FORT mean      -> MTL first (-0.03 < +0.01)
    #   * the FAIBLE mean    -> QC  first (-0.07 < -0.05)   <- the spec's rule
    # Silent failure this kills: the tiebreak silently degrading to enum order (or to the wrong
    # scenario's mean), which reorders the Tranche-1 core output's rows on every exact tie while
    # every existing test stays green.
    ed = {Geography.MTL_RMR: _ed([-0.04], [-0.05], [-0.03]),
          Geography.QC_RMR: _ed([-0.04], [-0.07], [0.01])}
    ranked = rank_geographies(ed)
    assert [r.geography for r in ranked] == [Geography.QC_RMR, Geography.MTL_RMR]
    assert [r.rank for r in ranked] == [1, 2]
    assert ranked[0].mean_ed_reference == ranked[1].mean_ed_reference   # the tie is exact



def test_closed_cohort_exceedance_rides_every_row_of_the_measured_geography():
    # Spec §7 steering ruling K (2026-08-07): the flag rides EVERY ranking row of a geography whose
    # measured 75+ net-migration rate exceeded the 1 %/yr cap — currently LAVAL_RA13 alone
    # (probes/closed-cohort-migration.md: max 1.6722 %/yr, LAVAL_RA13 2007/08). Silent failure this
    # kills: Laval's rank ships at full confidence while the closed-cohort omission is known
    # material there — the exceedance was measured and then lost on the way to the artifact.
    ed = {Geography.LAVAL_RA13: _ed([-0.02], [-0.03], [-0.01]),
          Geography.MTL_RMR: _ed([-0.05], [-0.06], [-0.04])}
    ranked = {r.geography: r for r in rank_geographies(ed)}
    assert "closed_cohort_exceedance" in ranked[Geography.LAVAL_RA13].flags
    assert "closed_cohort_exceedance" not in ranked[Geography.MTL_RMR].flags   # not a blanket flag
    assert CLOSED_COHORT_EXCEEDANCE_MEMBERS == frozenset({Geography.LAVAL_RA13})
    assert "closed_cohort_exceedance" in RANKING_FLAGS_ALLOWED                 # closed enum, 3 members
    assert_rankings_row_valid(ranking_row(ranked[Geography.LAVAL_RA13]))       # passes the emitter gate


def test_flag_emission_order_is_canonical():
    # Silent failure this kills: flag order varying by construction path would churn the Task-30
    # golden artifact diff without any modeled change.
    r = rank_geographies({Geography.LAVAL_RA13: _ed([-0.02], [-0.03], [-0.01])},
                         borrowed={Geography.LAVAL_RA13})[0]
    assert r.flags == ("borrowed_prior", "closed_cohort_exceedance")
    assert isinstance(r.flags, tuple)     # frozen row: a list default is mutable post-construction


def test_geography_serializes_as_value_never_the_enum_repr():
    # Measured twice in this arc: str(Geography.MTL_RMR) == 'Geography.MTL_RMR' under py3.12
    # str-Enum. Silent failure this kills: the shipped artifact carries a Python repr where the
    # consumer expects the enum value, and every downstream string match misses.
    row = ranking_row(rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])})[0])
    assert row["geography"] == "MTL_RMR"
    assert not row["geography"].startswith("Geography.")
    assert json.loads(json.dumps(row))["geography"] == "MTL_RMR"
    # the sibling trap: str-Enum hash equality lets a BARE STRING key rank successfully and then
    # die at emit (`.value` on a str) — refuse it where the key enters.
    with pytest.raises(CalibrationError, match="Geography"):
        rank_geographies({"MTL_RMR": _ed([-0.02], [-0.03], [-0.01])})


def test_partial_ed_is_refused_never_defaulted():
    # Spec §7/§8: "never a partial ED, never an unstated default". Silent failure this kills: a
    # missing scenario or an empty year slice reaching the ranking as a KeyError/ZeroDivisionError
    # far from its cause, or worse, as an implicit 0.0.
    with pytest.raises(CalibrationError, match="scenario"):
        rank_geographies({Geography.MTL_RMR: {Scenario.REFERENCE: [-0.02], Scenario.LOW: [-0.03]}})
    with pytest.raises(CalibrationError, match="empty"):
        rank_geographies({Geography.MTL_RMR: _ed([], [], [])})


def test_non_finite_ed_is_refused():
    # Silent failure this kills: every comparison against NaN is False, so a NaN mean sorts into a
    # position that depends on input order — two conforming runs emit DIFFERENT rankings from
    # identical data, which is exactly what spec §7's determinism contract forbids.
    with pytest.raises(CalibrationError, match="finite"):
        rank_geographies({Geography.MTL_RMR: _ed([math.nan], [-0.03], [-0.01])})
    with pytest.raises(CalibrationError, match="finite"):
        rank_geographies({Geography.MTL_RMR: _ed([-0.02], [math.inf], [-0.01])})


def test_unresolved_geography_is_excluded_entirely_with_a_typed_record():
    # Spec §8 resolution branch (iii): an unresolvable component-flow input EXCLUDES the geography
    # from rankings ENTIRELY — no partial ED row — and the run names it in a typed record.
    # Branch (i) fired for the committed vintage (compo-rmr-base.xlsx carries its own hors-RMR
    # row), so this PATH is currently unexercised by real data and must be tested to exist.
    ed = {Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01]),
          Geography.HORS_RMR: _ed([-0.05], [-0.06], [-0.04])}
    rankable, exclusions = exclude_from_rankings(ed, {Geography.HORS_RMR: "immigrant_component_flows"})
    assert set(rankable) == {Geography.MTL_RMR}
    assert [r.geography for r in rank_geographies(rankable)] == [Geography.MTL_RMR]
    assert [e.as_row() for e in exclusions] == [
        {"geography": "HORS_RMR", "unresolved_input": "immigrant_component_flows"}]
    # the normal shape: no ED was ever COMPUTED for the unresolved geography, so it is absent
    # from `ed` — the record is still emitted.
    rankable2, exclusions2 = exclude_from_rankings(
        {Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])},
        {Geography.HORS_RMR: "immigrant_component_flows"})
    assert set(rankable2) == {Geography.MTL_RMR} and len(exclusions2) == 1
    # the committed vintage: branch (i) fired, nothing excluded, every geography ranks.
    assert exclude_from_rankings(ed, {}) == (ed, [])
    # closed vocabulary: no free-text channel on the exclusion record either.
    assert UNRESOLVED_INPUTS == frozenset({"immigrant_component_flows"})
    with pytest.raises(ValueError, match="unresolved_input"):
        exclude_from_rankings(ed, {Geography.HORS_RMR: "crash_probability=0.35"})
    with pytest.raises(ValueError, match="Geography"):     # the same str-Enum key trap, at the record
        exclude_from_rankings(ed, {"HORS_RMR": "immigrant_component_flows"})


def test_empty_vintage_set_is_refused_no_vacuous_green():
    # Silent failure this kills: a run that recorded NO identity at all passes a >1 check
    # vacuously — a same-vintage gate that cannot fail is not a gate.
    with pytest.raises(CalibrationError, match="vintage"):
        refuse_cross_vintage(set())


def test_rank_stable_mapping_must_cover_every_ranked_geography():
    # Silent failure this kills: a sweep mapping that omits a geography silently reports it
    # STABLE — the cheap all-clear on the one field that carries a verification verdict.
    ed = {Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01]),
          Geography.QC_RMR: _ed([-0.01], [-0.02], [0.0])}
    with pytest.raises(CalibrationError, match="rank_stable"):
        rank_geographies(ed, rank_stable={Geography.MTL_RMR: True})
    with pytest.raises(CalibrationError, match="rank_stable"):
        rank_geographies(ed, rank_stable={Geography.MTL_RMR: True, Geography.QC_RMR: "stable"})


def test_row_validator_binds_field_types_and_the_geography_registry():
    # The row validator is the EMITTER gate (Task 29 calls it per row). Spec §7 r9-F3: every
    # string position is registry/enum-bound or format-validated. Silent failure this kills: a
    # well-formed-looking row whose values are the wrong TYPE — the allowlist binds vocabulary,
    # so without these the enum repr, a stringly-typed sweep verdict, or a NaN mean all ship.
    row = ranking_row(rank_geographies({Geography.MTL_RMR: _ed([-0.02], [-0.03], [-0.01])})[0])
    with pytest.raises(ValueError, match="geography"):
        assert_rankings_row_valid({**row, "geography": "Geography.MTL_RMR"})
    with pytest.raises(ValueError, match="rank_stable"):
        assert_rankings_row_valid({**row, "rank_stable": "unstable"})
    with pytest.raises(ValueError, match="rank must be"):
        assert_rankings_row_valid({**row, "rank": 0})
    with pytest.raises(ValueError, match="finite"):
        assert_rankings_row_valid({**row, "mean_ed_reference": math.nan})
    with pytest.raises(ValueError, match="duplicate"):
        assert_rankings_row_valid({**row, "flags": ["ra_proxy", "ra_proxy"]})


def test_georanking_is_frozen_and_carries_the_declared_fields():
    r = GeoRanking(rank=1, geography=Geography.MTL_RMR, mean_ed_reference=-0.02,
                   mean_ed_low=-0.03, mean_ed_high=-0.01)
    assert r.rank_stable is True and r.flags == ()
    with pytest.raises(Exception):
        r.rank = 2          # frozen: the emitted row cannot be edited after ranking
