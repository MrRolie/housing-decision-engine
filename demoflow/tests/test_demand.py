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

  * The vintage block is the run-6 carry: the rate loaders return their rate sub-tree and
    DROP `_provenance` at the boundary, and demand is the first production consumer of
    those surfaces. A consumer that cannot state the vintage it holds cannot put one in the
    §7 artifact envelope, so the accessor is tested HERE, at the consumer boundary that
    needed it.
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
    CENSUS_EXTRACT,
    HEADSHIP_ARTIFACT,
    OWNERSHIP_ARTIFACT,
    POP_QC_WORKBOOK,
    load_headship_rates,
    load_headship_vintage,
    load_ownership_rates,
    load_ownership_vintage,
)
from demoflow.loaders.pins import DATA_DIR, RAW_SOURCE_SHA256, WORKBOOK_SHA256
from demoflow.loaders.vintage import RateVintage, vintage_from_provenance


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

    98-10-0231-01 publishes no owner-maintainer rate below 25 (census.py `_AGE_BAND_SPEC`),
    and the pipeline builds its curve over `range(25, 101)` — so in every production run
    EVERY term of the spec §6 summation at ages 18..24 multiplies an UNDEFINED rate and
    contributes zero, not merely the age-18 boundary term. That is census.py's own
    `zero_support_note`, landed at T13b 2026-08-08 and quoted verbatim in `formation`:
    "undefined, hence contributing nothing, below the ownership lattice's floor of 25".

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


# --- the vintage carry: the first production consumer must be able to state it ---------

def test_a_demand_consumer_can_state_the_vintage_of_the_rate_surfaces_it_holds():
    """Run-6 carry: the loaders return rates and DROP `_provenance` at the boundary.

    Demand is the first production consumer of ownership × headship, and spec §7's artifact
    envelope has to publish `data_vintage.source_hashes` for exactly these surfaces — so a
    consumer holding rates must be able to say which vintage produced them, per surface, in
    the shape the envelope wants.
    """
    own = load_ownership_vintage()
    hs = load_headship_vintage()
    assert isinstance(own, RateVintage) and isinstance(hs, RateVintage)

    # Ownership derives from ONE source; headship from TWO (the extract AND the ISQ QC pop
    # workbook that is its person denominator) — the vintage must carry each surface's own
    # sources, not a single shared digest.
    assert dict(own.sources) == {CENSUS_EXTRACT: WORKBOOK_SHA256[CENSUS_EXTRACT]}
    assert dict(hs.sources) == {CENSUS_EXTRACT: WORKBOOK_SHA256[CENSUS_EXTRACT],
                                POP_QC_WORKBOOK: WORKBOOK_SHA256[POP_QC_WORKBOOK]}
    for v, artifact in ((own, OWNERSHIP_ARTIFACT), (hs, HEADSHIP_ARTIFACT)):
        assert v.artifact == artifact
        assert v.as_of.strip() and v.extracted_at.strip()
        assert v.raw_source_sha256 == RAW_SOURCE_SHA256[CENSUS_EXTRACT]
        assert v.raw_source_name == CENSUS_EXTRACT
        # §7 shape: {source: {sha256, extracted_at}} — ready for the envelope, no reshaping.
        # The VALUE is spec §7's "sha256-of-raw-response" (codex r3-F6), which for the Census
        # extract is the pinned UPSTREAM member digest, NOT the committed extract's own — the
        # extract is one link further down pins.py's chain (raw response -> filter predicate ->
        # committed extract -> derived rates), so publishing it would name an object a reader
        # cannot re-derive the artifact from and that a re-cut moves with.
        assert v.source_hashes()[CENSUS_EXTRACT] == {
            "sha256": RAW_SOURCE_SHA256[CENSUS_EXTRACT], "extracted_at": v.extracted_at}

    # The other half of r3-F6's parenthetical — "(ISQ files are already byte-pinned)": the
    # committed workbook IS the raw response, so its own digest is already the raw-response
    # digest and it is emitted unchanged. Without this arm the two semantics are
    # indistinguishable, which is why the mixed map read as correct for a whole run.
    assert hs.source_hashes()[POP_QC_WORKBOOK] == {
        "sha256": WORKBOOK_SHA256[POP_QC_WORKBOOK], "extracted_at": hs.extracted_at}
    assert POP_QC_WORKBOOK not in RAW_SOURCE_SHA256   # no separate upstream member to anchor


@pytest.mark.parametrize("artifact,mutate,rate_loader,vintage_loader,match", [
    (OWNERSHIP_ARTIFACT, lambda p: p["_provenance"].__setitem__("sha256", "0" * 64),
     load_ownership_rates, load_ownership_vintage, "STALE"),
    (OWNERSHIP_ARTIFACT, lambda p: p["rates"].pop(sorted(p["rates"])[0]),
     load_ownership_rates, load_ownership_vintage, "strict join"),
    (OWNERSHIP_ARTIFACT, lambda p: p.pop("rates"),
     load_ownership_rates, load_ownership_vintage, "strict join"),
    (HEADSHIP_ARTIFACT, lambda p: p["headship"].pop("65-74"),
     load_headship_rates, load_headship_vintage, "strict join"),
], ids=["stale-digest", "dropped-geography", "dropped-rates-key", "dropped-headship-band"])
def test_the_vintage_accessor_refuses_exactly_what_the_rate_loader_refuses(
        tmp_path, artifact, mutate, rate_loader, vintage_loader, match):
    """A vintage that can be stated where the rates would be REFUSED is worse than none.

    Both accessors read through the SAME verified helper, so the two legs cannot disagree —
    otherwise an emitter could publish a confident `data_vintage` for a surface no run may
    use. Parametrized over every refusal CAUSE rather than the staleness one alone: measured
    2026-08-14, with the completeness checks sitting in `load_*_rates` instead of the shared
    helper, three of these four causes refused the rates and handed back a `RateVintage`
    anyway — the exact split census.py's shared-read rationale claims cannot happen. The
    causes deliberately straddle the helper's two stages (digest verification, then the
    strict join) because that boundary is where the legs came apart.
    """
    payload = json.loads((DATA_DIR / artifact).read_text(encoding="utf-8"))
    mutate(payload)
    (tmp_path / artifact).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match=match):
        vintage_loader(data_dir=tmp_path)
    with pytest.raises(LoaderError, match=match):
        rate_loader(data_dir=tmp_path)


@pytest.mark.parametrize("strip,match", [
    ("as_of", "as_of"),
    ("extracted_at", "extracted_at"),
    ("sources", "source"),
])
def test_an_undated_or_uncited_provenance_states_no_vintage(strip, match):
    """The charter rule at the vintage boundary: an undated or unsourced record is a defect.

    An envelope field that silently becomes `""` or `{}` is the failure this kills — it
    publishes an artifact that LOOKS provenanced.
    """
    provenance = {"as_of": "2021", "extracted_at": "2026-07-21",
                  "sources": {CENSUS_EXTRACT: WORKBOOK_SHA256[CENSUS_EXTRACT]}}
    provenance.pop(strip)
    with pytest.raises(LoaderError, match=match):
        vintage_from_provenance("x.json", provenance)


def test_vintage_reads_the_single_source_provenance_shape_too():
    """Ownership records `source` + `sha256`; headship records a `sources` map. One builder
    covers both SHAPES, so neither of the two surfaces with a vintage accessor needs a
    bespoke reader."""
    v = vintage_from_provenance("x.json", {"as_of": "2021", "extracted_at": "2026-07-21",
                                           "source": "a.csv", "sha256": "a" * 64})
    assert dict(v.sources) == {"a.csv": "a" * 64}
    assert v.raw_source_sha256 is None      # optional: not every surface has an upstream anchor
    assert v.raw_source_name is None
    # With no upstream anchor the committed digest IS what §7 publishes — the byte-pinned case.
    assert v.source_hashes() == {"a.csv": {"sha256": "a" * 64, "extracted_at": "2026-07-21"}}


@pytest.mark.parametrize("name,raw,match", [
    (None, "b" * 64, "names no source"),        # a digest anchoring nothing identifiable
    ("missing.csv", "b" * 64, "not among"),     # a name that is not one of the sources
    ("a.csv", None, "no `raw_source_sha256`"),  # a name with no digest behind it
], ids=["digest-without-name", "name-not-a-source", "name-without-digest"])
def test_a_raw_anchor_must_name_WHICH_source_it_anchors(name, raw, match):
    """The half the record was missing: an upstream digest with no source attached.

    `source_hashes()` must substitute the raw-response digest for exactly ONE key, so the
    record has to say which. Ownership has a single source and reads unambiguously either
    way; headship has TWO, and there the association was carried only by convention — the
    shape in which the map silently emitted a committed-extract digest under a field spec §7
    defines as the raw-response one. Half-recorded provenance refuses (vintage.py's own rule
    for a malformed anchor) rather than defaulting, because a wrong association publishes a
    confident hash of the wrong object.
    """
    provenance = {"as_of": "2021", "extracted_at": "2026-07-21",
                  "source": "a.csv", "sha256": "a" * 64}
    if raw is not None:
        provenance["raw_source_sha256"] = raw
    with pytest.raises(LoaderError, match=match):
        vintage_from_provenance("x.json", provenance, raw_source_name=name)
