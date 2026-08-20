"""Task 13 contract gates — Census ownership (DERIVED, ruling B) + headship loaders.

The plan's six bodies are carried verbatim in intent. Four gates are ADDED, each for a
claim the plan's six cannot reach:

  test_hors_rmr_is_province_net_of_all_six_cmas
      codex r4-F2 is THE correction this task exists to honour, and nothing in the plan's
      six touches it: a derivation that nets only MTL+QC emits a HORS_RMR rate that is
      still in [0,1], still present for every enum member, and still equal to its own
      regenerated artifact — every one of the plan's gates stays green. This gate
      recomputes the residual straight from the CSV (deliberately NOT importing the
      producer's netting, the P2 content-gate pattern) AND asserts the wrong-netting
      value is materially different, so it cannot pass vacuously.

  test_registry_pins_the_census_extract
      the P2 extract was tracked-but-unpinned; the derivation reads its digest FROM the
      registry, so a dropped registry row must red here rather than silently unpinning
      the PIT chain.

  test_derivation_refuses_an_unpinned_extract / test_header_position_drift_raises
      the two DIV surfaces named in the re-triage debt (vintage identity, schema drift on
      the CSV's columns). Both are fail-loud paths with no other caller, so without a gate
      they are unexecuted claims. The schema gate re-pins its mutated copy (the repo's
      established monkeypatch pattern, test_isq_loader.py:394) — otherwise the pin gate
      fires first and the schema gate is never reached.

Three MORE gates were added 2026-08-08 after an adversarial mutation battery showed the
above still entailed only 2 of the 12 derived cells:

  test_full_rate_table_matches_an_independent_recompute
      the 75+ oracle anchors ONE cell and the HORS_RMR gate anchors ONE more; the other ten
      had only [0,1] (which `assert_fraction` already guarantees) and self-equality. Four
      producer mutations therefore shipped materially wrong rates, regenerated cleanly, and
      left every gate green — including QC_RMR sourced from the WRONG CMA, since QC_RMR had
      ZERO oracle coverage on all four bands. This extends the P2 gate-3 discipline from one
      cell to all of them.

  test_model_band_lattices_are_spec_labelled_and_partition_their_domain
      the lookup lattices had no gate at all: widening headship '20-34' to (20,44) left
      every gate green while age 40 silently returned the wrong rate.

  test_missing_headship_key_raises_rather_than_serving_an_empty_curve
      `load_headship_rates` degraded a renamed top-level key into an empty curve, which
      resurfaced downstream as a BAND error message.

Two MORE gates execute STEERING RULING L (2026-08-08):

  test_stale_artifact_sha_is_refused_at_load / test_unprovenanced_artifact_is_refused_at_load
      the no-drift gate defends the REPO, not a runtime load — it is a test, and cannot run
      when a caller loads rates. So `load_ownership_rates` now checks the artifact's recorded
      `_provenance.sha256` against the pins registry on every load and REFUSES a stale or
      unprovenanced one. The two legs are independent: CI compares CONTENT (artifact vs fresh
      derivation), the load path compares IDENTITY (recorded source digest vs the pin).

T13b (2026-08-08, DIV re-triage discharge docs/audits/dispatch/2026-08-08-div-retriage-t13-t14.md)
adds three blocks:

  PART 1 — headship is DERIVED, no longer typed (DIV F1, a live defect):
  test_headship_curve_matches_a_full_band_independent_recompute
  test_committed_headship_json_equals_generator_output
  test_headship_numerator_closes_against_the_published_maintainer_total
  test_headship_derivation_refuses_an_unpinned_source
  test_stale_headship_artifact_is_refused_at_load / test_unprovenanced_headship_artifact_is_refused_at_load
  test_headship_provenance_must_be_dated_and_cited
  test_headship_zero_support_band_records_why_it_is_kept
      the six shipped headship values did NOT reproduce from their stated source at their USE
      SITE (spec §7 `OwnerStock = Σ pop(a,g,t,s) × headship(a) × ownership(a)` multiplies ISQ
      scenario POPULATION, so the denominator is persons): 35-54 was −16.9%, the 65-74 → 75+
      shape was INVERTED, and the aggregate understated QC households by 9.5% (3,393,953 vs
      3,749,035). Every gate above them was green because nothing entailed a single value —
      `test_headship_curve_covers_all_ages_and_is_fraction` only re-read the literals the plan
      typed. Headship now follows the OWNERSHIP pattern exactly (ruling B derivation + ruling L
      load-path identity + regen equality + a full-band test-owned oracle), and the oracle's
      denominators reconcile against the workbook's OWN published grouped-age columns.

  PART 2 — the refresh path gets an EXTERNAL anchor (DIV F2, a regrade):
  test_ownership_artifact_records_and_checks_the_upstream_raw_anchor
  test_headship_artifact_records_and_checks_the_upstream_raw_anchor
      the disclosed on-disk-swap gap was benign alone, but the COMPOSITE legitimate-refresh
      motion (re-extract + re-pin + regen) passed 19/19 on a materially wrong table because
      every gate compared co-moving objects. The 850MB raw StatCan member cannot be committed,
      so its digest — recorded in probe-note prose since 2026-07-21 — is now a registry pin
      (pins.RAW_SOURCE_SHA256, gated in test_pins.py), embedded in both artifacts, and checked
      at derivation AND at load. NOT closed by this: an arbitrary hand re-extract that also
      edits the raw anchor (see the run report).

  PART 1 (run-9) — the FIRST anchors external to everything this repo commits:
  test_qc_cma_75plus_rate_matches_the_externally_published_statcan_cells
  test_hors_rmr_netting_identity_is_anchored_by_the_published_province_cell
      PART 2's raw anchor closed the co-moving-refresh gap only for a refresh that does NOT
      touch `pins.RAW_SOURCE_SHA256` — the residual DIV F2 left open in writing. Both gates
      below expect values FETCHED LIVE from StatCan's WDS (table 98-10-0231-01, the extract's
      own source cube) and typed as CITED literals: Québec CMA 75+ owner/total, and the
      province 75+ cell that the HORS_RMR netting identity is re-anchored on. A hand-cut
      extract with a hand-edited raw anchor cannot satisfy them, because satisfying them means
      agreeing with what StatCan publishes at those coordinates. Neither gate makes a network
      call — a re-fetching gate would be an availability check, not an anchor.

  PART 3 — the territory-note gate binds ROLE, not presence (DIV F3):
  test_isq_territory_note_binds_each_figure_to_its_role
  test_absent_statistic_or_total_member_names_the_member_and_not_the_geographies
      five bare `f"{value:,.0f}" in note` asserts pinned only that the digits appear SOMEWHERE,
      so swapping 2,740,546 <-> 2,384,575 (this rate's territory <-> the population it
      multiplies — the exact confusion the note exists to prevent) left every gate green. The
      figures are now asserted inside contiguous clauses that carry their role, and the gate
      re-runs itself against a swapped copy so it cannot pass vacuously (the ca_caveat pattern,
      lines ~372-379). The second gate covers two refusals that named the WRONG cause: a
      renamed statistic or `Total -` member empties the rate slice, and the loader reported
      "GEO set is []" — sending the reader to the geography map instead of to the absent member.
"""
import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census, pins
from demoflow.loaders.census import (
    CENSUS_EXTRACT,
    HEADSHIP_ARTIFACT,
    POP_QC_WORKBOOK,
    derive_headship_from_sources,
    derive_ownership_from_csv,
    headship_rate,
    load_headship_rates,
    load_ownership_rates,
    ownership_rate,
)
from demoflow.loaders.pins import DATA_DIR, RAW_SOURCE_SHA256


# --- the plan's six -----------------------------------------------------------------

def test_mtl_rmr_75plus_derivation_matches_spec_oracle():
    # The DERIVED MTL 75+ owner rate must reproduce the spec's provenance figure at its
    # stated precision: 56.2% = 113,730 / 202,535 = 0.56153...  (abs=1e-6 against a TYPED
    # 0.562 would FAIL the true derivation — the spec figure is 3 sig figs, so round to
    # compare, never hand-tune the CSV to hit an over-precise literal).
    rates = load_ownership_rates()
    assert round(ownership_rate(rates, Geography.MTL_RMR, age=78), 3) == 0.562


def test_every_enum_geography_has_a_rate():
    rates = load_ownership_rates()
    for geo in Geography:
        assert 0.0 <= ownership_rate(rates, geo, age=80) <= 1.0   # strict join + fraction


def test_unknown_age_band_raises():
    rates = load_ownership_rates()
    with pytest.raises(LoaderError, match="age band"):
        ownership_rate(rates, Geography.MTL_RMR, age=20)   # below the modeled 25+ bands


def test_out_of_unit_ownership_rate_raises():
    """The LOOKUP gate: `ownership_rate` refuses an out-of-unit rate in the table it is handed.

    RESHAPED 2026-08-13 (DIV carry), and the reshape is the finding, not a weakening. This
    test used to reach the lookup by loading a hand-built artifact — which only worked
    because the load path was PERMISSIVE about rate values. Ownership rates are now
    Anchor-typed at load (`test_an_out_of_unit_ownership_rate_is_refused_AT_LOAD`), so that
    route now refuses one step earlier and could no longer reach this gate. The lookup gate
    still has a job the load gate cannot do: `ownership_rate` also serves tables a caller
    assembled itself (fixtures, sweeps, a future consumer), which no loader ever validated.
    So the two gates are asserted on the two routes that actually reach them — the hand-built
    table here, the artifact there — and neither stands in for the other.
    """
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        ownership_rate({g.value: {"75+": 1.5} for g in Geography}, Geography.MTL_RMR, age=80)


def test_headship_curve_covers_all_ages_and_is_fraction():
    hs = load_headship_rates()
    for age in (10, 30, 45, 60, 70, 90):
        assert 0.0 <= headship_rate(hs, age) <= 1.0


def test_committed_ownership_json_equals_generator_output():
    # No-drift gate (steering ruling B): the committed JSON must equal a fresh derivation
    # from the pinned P2 CSV. A hand-edit, a stale vintage, or a schema drift fails here —
    # the P2 content-gate pattern applied to the ownership artifact.
    #
    # FULL-DICT equality, not `["rates"]` only (measured 2026-08-08: full equality holds).
    # `_provenance` is the durable record a downstream reader gets, and it carries the
    # extract's sha256 — comparing only `rates` left the whole subtree uncompared, so a
    # stale caveat, a stale vintage string, or a stale source digest could ship. This is the
    # CONTENT leg only; the load path independently checks IDENTITY on every load (steering
    # ruling L — see the two-leg statement in this module's docstring). Neither subsumes the
    # other, so neither comment may describe the other leg as absent.
    committed = json.loads((DATA_DIR / "ownership_by_geo_age.json").read_text(encoding="utf-8"))
    fresh = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)
    assert committed == fresh


# --- added gates --------------------------------------------------------------------

# --- TEST-OWNED oracle inputs -------------------------------------------------------
# NOTHING below is imported from census.py, and that is the whole point: an "independent"
# recompute that borrowed the producer's band membership, geography map, or band labels
# would move WITH a mutation to them and entail nothing. Every literal here is transcribed
# from the spec / probe note, so the two sides can only agree by both being right.
#   - _SPEC_AGE_BANDS      spec §8 model bands (25-54 / 55-64 / 65-74 / 75+)
#   - _BAND_MEMBERS        probe P2 §5's 15-member age list, allocated to those bands;
#                          75+ has NO single member (P2 §5) -> two constituents
#   - _GEO_SOURCE          spec §8 CMA<->RMR identity: MTL CMA ≡ MTL_RMR, QC CMA ≡ QC_RMR
#   - _ALL_QC_CMAS         probe P2 §3's six wholly-Québec CMAs (the netting set)
_PROVINCE = "Quebec"
_ALL_QC_CMAS = (
    "Drummondville (CMA), Que.",
    "Montréal (CMA), Que.",
    "Québec (CMA), Que.",
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
)
_SPEC_AGE_BANDS = ("25-54", "55-64", "65-74", "75+")
_SPEC_HEADSHIP_BANDS = ("0-19", "20-34", "35-54", "55-64", "65-74", "75+")
_BAND_MEMBERS = {
    "25-54": ("25 to 29 years", "30 to 34 years", "35 to 39 years",
              "40 to 44 years", "45 to 49 years", "50 to 54 years"),
    "55-64": ("55 to 59 years", "60 to 64 years"),
    "65-74": ("65 to 69 years", "70 to 74 years"),
    "75+": ("75 to 84 years", "85 years and over"),
}
_GEO_SOURCE = {
    Geography.MTL_RMR: "Montréal (CMA), Que.",
    Geography.QC_RMR: "Québec (CMA), Que.",
}
_BORROWERS = (Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13,
              Geography.LANAUDIERE_RA14_PROXY, Geography.LAURENTIDES_RA15_PROXY,
              Geography.MONTEREGIE_RA16_PROXY)


def _independent_band_counts(band_members=None) -> dict[str, dict[str, tuple[int, int]]]:
    """{GEO label: {model band: (owner, total)}}, recomputed from the committed CSV
    without importing any of the producer's logic (the P2 gate-3 discipline).

    `band_members` defaults to the OWNERSHIP bands; the headship oracle passes its own map
    (and its own one-member pseudo-band for the extract's published maintainer total), so the
    two oracles share the reader and share NOTHING with the producer.
    """
    band_members = _BAND_MEMBERS if band_members is None else band_members
    member_band = {m: band for band, members in band_members.items() for m in members}
    out: dict[str, dict[str, list[int]]] = {}
    with (DATA_DIR / CENSUS_EXTRACT).open(encoding="utf-8-sig", newline="") as fh:
        rows = csv.reader(fh)          # positional: duplicate `Symbol` headers collapse in a dict
        header = next(rows)
        i_geo = header.index("GEO")
        i_stat = header.index("Statistics (3C)")
        i_age = header.index("Age of primary household maintainer (15)")
        i_struct = header.index("Structural type of dwelling (10)")
        i_condo = header.index("Condominium status (3)")
        i_hh = header.index("Household type including census family structure (16)")
        i_total = header.index("Tenure (4):Total - Tenure[1]")
        i_owner = header.index("Tenure (4):Owner[2]")
        for row in rows:
            band = member_band.get(row[i_age])
            if (band is not None
                    and row[i_stat] == "Number of private households"
                    and row[i_struct] == "Total - Structural type of dwelling"
                    and row[i_condo] == "Total - Condominium status"
                    and row[i_hh] == "Total - Household type including census family structure"):
                acc = out.setdefault(row[i_geo], {}).setdefault(band, [0, 0])
                acc[0] += int(row[i_owner])
                acc[1] += int(row[i_total])
    return {g: {b: (o, t) for b, (o, t) in bands.items()} for g, bands in out.items()}


def _expected_rate_table() -> dict[str, dict[str, float]]:
    """The FULL 8-geography x 4-band table, built only from the test-owned literals above."""
    counts = _independent_band_counts()
    assert set(counts) == {_PROVINCE, *_ALL_QC_CMAS}, f"extract GEO set drifted: {sorted(counts)}"
    for geo, bands in counts.items():
        assert set(bands) == set(_SPEC_AGE_BANDS), f"{geo}: bands {sorted(bands)}"

    table: dict[str, dict[str, float]] = {}
    for geo, source in _GEO_SOURCE.items():
        table[geo.value] = {b: counts[source][b][0] / counts[source][b][1]
                            for b in _SPEC_AGE_BANDS}
    hors = {}
    for band in _SPEC_AGE_BANDS:
        owner = counts[_PROVINCE][band][0] - sum(counts[c][band][0] for c in _ALL_QC_CMAS)
        total = counts[_PROVINCE][band][1] - sum(counts[c][band][1] for c in _ALL_QC_CMAS)
        assert total > 0 and 0 <= owner <= total, f"{band}: residual left the feasible region"
        hors[band] = owner / total
    table[Geography.HORS_RMR.value] = hors
    for geo in _BORROWERS:          # spec §8: RA rows reuse the parent CMA rate, flagged
        table[geo.value] = dict(table[Geography.MTL_RMR.value], _flag="borrowed_prior")
    return table


def test_full_rate_table_matches_an_independent_recompute():
    """ENTAILMENT over the WHOLE table, not just the two anchored cells.

    Measured 2026-08-08 (mutation battery): with only the 75+ oracle and the 75+ HORS_RMR
    gate, four producer mutations shipped materially wrong rates, regenerated cleanly, and
    left every gate green — a band member added to 55-64 (+3.8pp on MTL 25-54 for the
    symmetric case), a member dropped from 65-74 or 25-54, and QC_RMR sourced from the
    WRONG CMA (QC_RMR had ZERO oracle coverage on all four of its bands). The fix is to
    apply the P2 gate-3 discipline at every cell instead of one: this recomputes all
    8 x 4 from the CSV using TEST-OWNED band members and a TEST-OWNED geography map, and
    pins BOTH surfaces — the committed artifact AND a fresh derivation, since asserting
    only the artifact leaves the PRODUCER uncovered once the artifact is regenerated under
    the mutation.
    """
    expected = _expected_rate_table()
    committed = json.loads(
        (DATA_DIR / "ownership_by_geo_age.json").read_text(encoding="utf-8"))["rates"]
    fresh = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)["rates"]

    assert set(committed) == {g.value for g in Geography}
    for surface, table in (("committed", committed), ("fresh", fresh)):
        assert set(table) == set(expected), f"{surface}: geography set drifted"
        for geo, bands in expected.items():
            assert set(table[geo]) == set(bands), f"{surface}[{geo}]: band set drifted"
            for band, value in bands.items():
                if band == "_flag":
                    assert table[geo][band] == value, f"{surface}[{geo}] lost its flag"
                else:
                    assert table[geo][band] == pytest.approx(value, rel=1e-12), (
                        f"{surface}[{geo}][{band}]")


def test_model_band_lattices_are_spec_labelled_and_partition_their_domain():
    """The band tuples are load-bearing lookup lattices with NO gate of their own.

    Measured 2026-08-08: widening headship '20-34' to (20,44) and '35-54' to (45,54) leaves
    every gate green while age 40 silently returns 0.40 instead of 0.48 — and headship is
    consumed multiplicatively by OwnerStock (spec §7). A contiguity/non-overlap check alone
    does NOT catch it ((20,44)+(45,54) is still a contiguous cover); neither does a pure
    label<->range parse catch a band RENAMED in step with its range. The discriminator is
    the SPEC-ANCHORED literal label tuple (transcribed above, not imported), and the three
    properties together: labels == spec, label agrees with its (lo, hi), and the bands
    partition their domain with no gap and no overlap.
    """
    for name, spec_labels, bands, floor in (
            ("ownership", _SPEC_AGE_BANDS, census._AGE_BANDS, 25),):
        assert tuple(label for label, _, _ in bands) == spec_labels, f"{name}: labels drifted"
        prev_hi = floor - 1
        for label, lo, hi in bands:
            if label.endswith("+"):
                assert lo == int(label[:-1]) and hi >= 200, f"{name}[{label}]: open band"
            else:
                lo_txt, hi_txt = label.split("-")
                assert (lo, hi) == (int(lo_txt), int(hi_txt)), (
                    f"{name}[{label}]: range ({lo}, {hi}) disagrees with its label")
            assert lo == prev_hi + 1, f"{name}[{label}]: gap or overlap below {lo}"
            prev_hi = hi

    # The derivation's band spec is the SAME lattice (one source of truth) and its members
    # are exactly the spec bands' constituents — a member moved between bands reds here too.
    assert {label: members for label, _, _, members in census._AGE_BAND_SPEC} == _BAND_MEMBERS

    # HEADSHIP NO LONGER HAS A BAND LATTICE (operator ruling V): it reads the 14 PUBLISHED
    # members and graduates them onto the single-year denominator, so the property to pin is
    # not "labels agree with ranges and partition a domain" but "the member spec IS the
    # published dimension, contiguous from the youngest published member to the denominator's
    # terminal age, and the six legacy bands DERIVE from it". The legacy lattice keeps the
    # partition check, against the SAME spec-anchored labels as before.
    assert tuple(label for label, _lo, _hi in census._HEADSHIP_LEGACY_BAND_SPEC) == _SPEC_HEADSHIP_BANDS
    prev_hi = -1
    for label, lo, hi in census._HEADSHIP_LEGACY_BAND_SPEC:
        assert lo == prev_hi + 1, f"legacy headship[{label}]: gap or overlap below {lo}"
        prev_hi = hi
    assert prev_hi == 100
    prev_hi = 14
    for label, lo, hi in census._HEADSHIP_MEMBER_SPEC:
        assert lo == prev_hi + 1, f"headship member {label!r}: gap or overlap below {lo}"
        prev_hi = hi
    assert prev_hi == 100, "the open member no longer closes at the denominator's terminal age"


# --- T13b PART 1: headship RE-DERIVED at its use site -------------------------------
# TEST-OWNED oracle inputs again, and again nothing is imported from census.py:
#   - _SPEC_HEADSHIP_BAND_MEMBERS  probe P2 §5's 15-member age list allocated to the SPEC's
#                                  headship bands. The youngest maintainer member published is
#                                  `15 to 19 years` (P2 §5) — there is no under-15 member,
#                                  which is why 0-19 carries one constituent and not four.
#   - _PUBLISHED_TOTAL_BAND        the extract's own `Total - Age …` member, read as a
#                                  one-member pseudo-band: an INDEPENDENT published aggregate
#                                  that a dropped/duplicated constituent cannot move with.
#   - _DIV_REFERENCE_HEADSHIP      the DIV discharge record's derived values
#                                  (docs/audits/dispatch/2026-08-08-div-retriage-t13-t14.md:22-25),
#                                  at the precision THAT RECORD CARRIES — 3 dp. "Verify, don't
#                                  trust": an anchor external to this repo's code, measured by a
#                                  different agent from the same two sources. Corrected run-9:
#                                  these were transcribed at 4 dp (0.3954 / 0.5779 / 0.5919),
#                                  but the cited lines publish 3 (0.395 / 0.578 / 0.592). The
#                                  4th digit could only have come from THIS repo's derivation,
#                                  so asserting it made a self-referential value look external —
#                                  precisely the co-moving-anchor failure DIV F2 is about. An
#                                  anchor is asserted at the precision of its citation.
#   - _RETIRED_TYPED_CURVE         the six values shipped until 2026-08-08 (plan:1922). Asserted
#                                  MATERIALLY DIFFERENT so the derivation cannot pass by
#                                  reproducing the curve it replaces.
_SPEC_HEADSHIP_BAND_MEMBERS = {
    "0-19": ("15 to 19 years",),
    "20-34": ("20 to 24 years", "25 to 29 years", "30 to 34 years"),
    "35-54": ("35 to 39 years", "40 to 44 years", "45 to 49 years", "50 to 54 years"),
    "55-64": ("55 to 59 years", "60 to 64 years"),
    "65-74": ("65 to 69 years", "70 to 74 years"),
    "75+": ("75 to 84 years", "85 years and over"),
}
_HEADSHIP_BAND_RANGE = {"0-19": (0, 19), "20-34": (20, 34), "35-54": (35, 54),
                        "55-64": (55, 64), "65-74": (65, 74), "75+": (75, 200)}
_PUBLISHED_TOTAL_BAND = "published maintainer total"
_PUBLISHED_MAINTAINER_TOTAL_MEMBER = "Total - Age of primary household maintainer"
_DIV_REFERENCE_HEADSHIP = {"20-34": 0.395, "35-54": 0.578, "55-64": 0.611,
                           "65-74": 0.640, "75+": 0.592}
_DIV_REFERENCE_DP = 3       # the precision the cited record publishes — see the note above
_RETIRED_TYPED_CURVE = {"0-19": 0.02, "20-34": 0.40, "35-54": 0.48,
                        "55-64": 0.52, "65-74": 0.56, "75+": 0.62}

# ISQ denominator selection (spec §7: base-year rates against the SCENARIO population) and the
# measured sheet geometry of THIS pinned workbook (the same offsets isq_ages.py's docstring
# table records for pop-as-qc-base.xlsx: group row 4, label row 5, units row 6, data row 7).
_ISQ_SHEET = "Années d'âge"
_ISQ_HEADER_ROW = 4
_ISQ_QC_LABEL = "Le Québec"
_ISQ_BASE_SCENARIO = "Référence (A2026)"
_ISQ_BASE_YEAR = 2021
_ISQ_SEX_TOTAL = 3
# The sheet's OWN published grouped-age columns — an aggregate the single-year block does not
# produce, so reconciling against them is a real check on the denominators, not a restatement.
_ISQ_GROUPED_COVER = {"0-19": ("0-19",), "20-64": ("20-34", "35-54", "55-64"),
                      "65+": ("65-74", "75+")}


def _independent_qc_maintainers() -> dict[str, int]:
    """{headship band: QC private-household primary maintainers}, plus the published total."""
    counts = _independent_band_counts(
        {**_SPEC_HEADSHIP_BAND_MEMBERS, _PUBLISHED_TOTAL_BAND: (_PUBLISHED_MAINTAINER_TOTAL_MEMBER,)})
    qc = counts[_PROVINCE]
    assert set(qc) == set(_SPEC_HEADSHIP_BAND_MEMBERS) | {_PUBLISHED_TOTAL_BAND}, (
        f"headship band coverage drifted in the extract: {sorted(qc)}")
    # index 1 is `Tenure (4):Total - Tenure[1]` = ALL private households in the cell, which
    # IS the maintainer count for that age band (the age dimension is the MAINTAINER's age).
    # Index 0 (owner households) is the ownership numerator and is deliberately not read here.
    return {band: counts_pair[1] for band, counts_pair in qc.items()}


def _independent_qc_persons_by_band() -> dict[str, float]:
    """{headship band: ISQ 2021 Référence Le Québec persons}, read straight off the pinned
    workbook with test-owned geometry, then RECONCILED against the sheet's own published
    grouped-age cells (0-19 / 20-64 / 65+ / TOTAL) so a mis-selected column cannot pass."""
    import pandas as pd

    workbook = DATA_DIR / POP_QC_WORKBOOK
    pins.verify_pin(workbook, workbook.name)
    raw = pd.read_excel(workbook, sheet_name=_ISQ_SHEET, header=None)
    groups = raw.iloc[_ISQ_HEADER_ROW].ffill()
    labels = raw.iloc[_ISQ_HEADER_ROW + 1]
    ids = {str(v).strip(): i for i, v in enumerate(raw.iloc[_ISQ_HEADER_ROW])
           if isinstance(v, str)}
    body = raw.iloc[_ISQ_HEADER_ROW + 3:]
    rows = body[(body[ids["Région"]] == _ISQ_QC_LABEL)
                & (body[ids["Scénario"]] == _ISQ_BASE_SCENARIO)
                & (body[ids["Année"]] == _ISQ_BASE_YEAR)
                & (body[ids["Sexe"]] == _ISQ_SEX_TOTAL)]
    assert len(rows) == 1, f"expected ONE base-year both-sexes QC row, got {len(rows)}"
    row = rows.iloc[0]
    assert str(row[ids["Statut"]]).strip() == "r", (
        "the base year is no longer 'r' (réel) in this workbook — the denominator's meaning "
        "changed, so the derived curve is no longer a base-year observation")

    single_year = {}
    for pos in range(raw.shape[1]):
        if str(groups.iloc[pos]).strip() != "Âge":
            continue
        label = str(labels.iloc[pos]).strip()
        age = 100 if label == "100+" else (int(float(label)) if label.replace(
            ".", "", 1).isdigit() else None)
        if age is not None:
            single_year[age] = float(row[pos])
    assert sorted(single_year) == list(range(0, 101)), (
        f"single-year span drifted: {len(single_year)} ages")

    persons = {band: sum(v for a, v in single_year.items() if lo <= a <= hi)
               for band, (lo, hi) in _HEADSHIP_BAND_RANGE.items()}

    published = {str(labels.iloc[pos]).strip(): float(row[pos])
                 for pos in range(raw.shape[1])
                 if str(groups.iloc[pos]).strip() in ("Groupe d'âge", "Sexe")
                 and str(labels.iloc[pos]).strip() in ("TOTAL", "0-19", "20-64", "65+")}
    assert set(published) == {"TOTAL", "0-19", "20-64", "65+"}, (
        f"published grouped-age anchor columns drifted: {sorted(published)}")
    for cell, bands in _ISQ_GROUPED_COVER.items():
        assert sum(persons[b] for b in bands) == pytest.approx(published[cell], rel=1e-12), (
            f"single-year band sum for {bands} does not reconcile with the workbook's own "
            f"published {cell!r} cell")
    assert sum(persons.values()) == pytest.approx(published["TOTAL"], rel=1e-12)
    return persons


def _expected_headship_curve() -> dict[str, float]:
    maintainers = _independent_qc_maintainers()
    persons = _independent_qc_persons_by_band()
    return {band: maintainers[band] / persons[band] for band in _SPEC_HEADSHIP_BAND_MEMBERS}


def _committed_headship() -> dict:
    return json.loads((DATA_DIR / HEADSHIP_ARTIFACT).read_text(encoding="utf-8"))


def test_headship_curve_matches_a_full_band_independent_recompute():
    """DIV F1 was a LIVE DEFECT: the typed curve did not reproduce at its use site.

    The use site defines the semantics — spec:395 `OwnerStock(g,t,s) = Σ_over_all_ages
    pop(a,g,t,s) × headship(a) × ownership(a)` multiplies ISQ scenario POPULATION — so
    headship(a) is maintainers per PERSON at a single year of age, whose band AGGREGATE is
    maintainers-in-band ÷ persons-in-band, and the denominator is the pinned ISQ workbook,
    not the Census cube. Both surfaces are asserted (committed artifact AND a
    fresh derivation) for the same reason the ownership gate does it: a producer mutation
    regenerated THROUGH the artifact moves both together, so pinning only the artifact would
    leave the producer uncovered.
    """
    expected = _expected_headship_curve()
    persons = _independent_persons_by_age()
    fresh = derive_headship_from_sources(DATA_DIR / CENSUS_EXTRACT, DATA_DIR / POP_QC_WORKBOOK)
    committed = _committed_headship()

    # Since ruling V the curve is age-resolved, so the band-level oracle is asserted through
    # the AGGREGATION the curve must reproduce — Σ_{a∈band} P(a)·h(a) / Σ_{a∈band} P(a) — on
    # EVERY carried shape. That is a strictly stronger statement than the old direct read: it
    # holds only if per-member closure holds, and it is what makes the six legacy provenance
    # figures below still derivable.
    for surface, payload in (("committed", committed), ("fresh", fresh)):
        for shape, curve in _curves(payload).items():
            for band, lo, hi in _SPEC_LEGACY_BANDS:
                num = sum(persons[a] * curve[a] for a in range(lo, hi + 1))
                den = sum(persons[a] for a in range(lo, hi + 1))
                assert num / den == pytest.approx(expected[band], rel=1e-12), (
                    f"{surface}[{shape}][{band}]")

    # External anchor: the DIV's independently measured values, at the precision the cited
    # record actually publishes (3 dp — see the note on _DIV_REFERENCE_HEADSHIP; a 4th digit
    # asserted against a 3-dp citation is this repo's own derivation wearing an external label).
    for band, reference in _DIV_REFERENCE_HEADSHIP.items():
        assert round(expected[band], _DIV_REFERENCE_DP) == reference, (
            f"{band}: derived {expected[band]:.6f} does not reproduce the DIV reference "
            f"{reference} (docs/audits/dispatch/2026-08-08-div-retriage-t13-t14.md:22-25)")

    # NON-VACUITY: the retired typed curve must be materially different in every band, else
    # this gate would be satisfied by the very values the re-derivation exists to replace.
    for band, typed in _RETIRED_TYPED_CURVE.items():
        assert abs(expected[band] - typed) > 1e-3, (
            f"{band}: derived value reproduces the retired typed {typed} — the DIV measured "
            "these as NOT reproducible from their stated source")
    # The SHAPE the typed curve inverted (DIV F1: the typed values rose monotonically into 75+,
    # peaking there at 0.62). The real maintainer propensity PEAKS at 65-74 and DIPS after it,
    # to below the 55-64 level — 75+ maintainership falls as seniors move into collective
    # dwellings or co-reside. Asserted as the full ordering, since the inversion the DIV caught
    # is exactly a pairwise-order defect.
    assert (expected["65-74"] > expected["55-64"] > expected["75+"]
            > expected["20-34"] > expected["0-19"]), f"headship shape drifted: {expected}"


def test_committed_headship_json_equals_generator_output():
    """Regen equality (steering ruling B), FULL dict — `_provenance` included, so a stale
    digest, a stale closure figure or a stale caveat cannot ship."""
    fresh = derive_headship_from_sources(DATA_DIR / CENSUS_EXTRACT, DATA_DIR / POP_QC_WORKBOOK)
    assert _committed_headship() == fresh


def test_headship_numerator_closes_against_the_published_maintainer_total():
    """The banded numerator must close against the extract's OWN published total.

    StatCan rounds every cell to the nearest 5, so the 14 banded constituents and the
    published total each carry ≤2.5 of rounding error: the closure bound is 2.5 × 15 = 37.5,
    DERIVED from the member count rather than tuned to today's Δ (a gate tuned to the observed
    5 would red on a legitimate re-extract). It still catches a dropped or duplicated
    constituent by three orders of magnitude — the smallest member (15-19) is 10,920.
    """
    maintainers = _independent_qc_maintainers()
    banded = sum(v for band, v in maintainers.items() if band != _PUBLISHED_TOTAL_BAND)
    published = maintainers[_PUBLISHED_TOTAL_BAND]
    n_members = sum(len(m) for m in _SPEC_HEADSHIP_BAND_MEMBERS.values())
    assert abs(banded - published) <= 2.5 * (n_members + 1), (
        f"banded maintainers {banded:,} vs published {published:,} exceeds the round-to-5 bound")

    # The provenance record must CITE both figures in role-bound form (a cited value is a
    # computed value in this package — the same discipline as the territory note).
    prov = _committed_headship()["_provenance"]
    assert (f"banded maintainers {banded:,} vs the extract's published "
            f"{_PUBLISHED_MAINTAINER_TOTAL_MEMBER!r} member {published:,}"
            in prov["numerator_closure"]), (
        f"numerator_closure does not bind both figures to their roles: "
        f"{prov['numerator_closure']!r}")


def test_headship_zero_support_band_records_why_it_is_kept():
    """The youngest PUBLISHED member starts at 15 — recorded, not silently averaged.

    The use-site rule keeps every age (spec:395 sums pop × headship × ownership over all ages,
    and the pipeline builds `{a: headship_rate(curve, a) for a in range(0, 101)}` — a dropped
    AGE would raise there). Since ruling V the curve IS age-resolved, so what the note records
    is no longer a band average carrying its whole numerator at 15-19: it is a CLOSURE BOUND
    on an unpublished under-15 member, and the clause stating it is asserted here.
    """
    maintainers = _independent_qc_maintainers()
    persons = _independent_persons_by_age()
    note = _committed_headship()["_provenance"]["zero_support_note"]
    under_15 = sum(persons[a] for a in range(0, 15))
    assert f"{maintainers['0-19']:,} households" in note, (
        f"zero_support_note lost the youngest published member's count: {note!r}")
    assert f"{under_15:,.0f} persons aged 0-14" in note, (
        f"zero_support_note lost its role-bound denominator: {note!r}")
    # The claim is a BOUND, in both directions: never an absence claim, never a proof of zero.
    assert "DECLARES ITS OWN CARDINALITY" in note and "only admissible value" in note
    assert "no published maintainer member under 15" not in note, (
        "the note reverted to the absence claim ruling V replaced with a closure bound")
    assert "not a proof of exact zero" in note


# --- amendment #12: the sub-25 floor's PREMISE, measured ------------------------------
# TEST-OWNED literals, transcribed from the QFE record (SUBJECT 2(a) of
# docs/audits/dispatch/2026-08-15-qfe-retriage-task-26.md) and never read from it at runtime —
# an oracle that re-derived them from the producer would move with a mutation to it.
_SUB_FLOOR_MEMBERS = ("15 to 19 years", "20 to 24 years")
_QFE_SUB_FLOOR_CELLS = {                      # GEO -> member -> (owner, total)
    "Quebec": {"15 to 19 years": (1150, 10920), "20 to 24 years": (17170, 106605)},
    "Montréal (CMA), Que.": {"15 to 19 years": (615, 5075), "20 to 24 years": (6080, 52120)},
    "Québec (CMA), Que.": {"15 to 19 years": (90, 1225), "20 to 24 years": (1585, 13270)},
}
# Every maintainer-age member 98-10-0231-01 publishes (probe P2 §5's 15-member list). The SET
# is the discriminator for both halves of the finding at once: nothing under 15 exists (the
# `zero_support_note`'s separate claim, which SURVIVES), and the two youngest published bands
# are exactly the pair `_AGE_BAND_SPEC` drops.
_PUBLISHED_AGE_MEMBERS = frozenset((
    "Total - Age of primary household maintainer",
    "15 to 19 years", "20 to 24 years", "25 to 29 years", "30 to 34 years",
    "35 to 39 years", "40 to 44 years", "45 to 49 years", "50 to 54 years",
    "55 to 59 years", "60 to 64 years", "65 to 69 years", "70 to 74 years",
    "75 to 84 years", "85 years and over"))


def _independent_published_age_members() -> set[str]:
    """Every value the extract's age dimension takes on the `Total -` slice, read positionally
    with test-owned column names — the enumeration `_independent_band_counts` cannot give,
    because that reader can only report members it was already told to look for."""
    members: set[str] = set()
    with (DATA_DIR / CENSUS_EXTRACT).open(encoding="utf-8-sig", newline="") as fh:
        rows = csv.reader(fh)
        header = next(rows)
        i_stat = header.index("Statistics (3C)")
        i_age = header.index("Age of primary household maintainer (15)")
        i_struct = header.index("Structural type of dwelling (10)")
        i_condo = header.index("Condominium status (3)")
        i_hh = header.index("Household type including census family structure (16)")
        for row in rows:
            if (row[i_stat] == "Number of private households"
                    and row[i_struct] == "Total - Structural type of dwelling"
                    and row[i_condo] == "Total - Condominium status"
                    and row[i_hh] == "Total - Household type including census family structure"):
                members.add(row[i_age])
    return members


def test_the_extract_DOES_publish_owner_maintainer_counts_below_25():
    """THE FLOOR IS A CHOICE IN `_AGE_BAND_SPEC`, NOT THE DATA'S SILENCE (QFE 2026-08-15).

    The convention shipped with a stated premise — "98-10-0231-01 publishes no owner-maintainer
    rate below 25, so the rate is UNDEFINED there" — carried in `census._zero_support_note` and
    mirrored into `formation.OWNERSHIP_LATTICE_FLOOR`, `owner_stock._ownership` and both of
    their test files. It is FALSE for the committed extract, and nothing in this suite could
    see that: every oracle here was pointed at the four bands the derivation reads, so the two
    the derivation drops were outside every gate's field of view. This is the arc's fourth
    absence-claim-that-was-a-property-of-the-search and the first inside our own code, so the
    gate is written as the enumeration it needed to be, not as another band lookup.

    WHAT DOES NOT MOVE: no rate, no band, no floor. The premise is corrected; the behaviour
    stands under spec §7's binding ordering constraint (age-resolved headship first, then the
    floor) because the sub-25 zero is currently the only thing suppressing the age-20
    band-entry artifact in D_native.

    THE UNDER-15 CLAIM SURVIVES and is asserted here too, from the same enumeration: the two
    facts differ only in where the line is drawn, so a reader who learns the first is false
    must be able to see in one place that the second is true.
    """
    counts = _independent_band_counts({m: (m,) for m in _SUB_FLOOR_MEMBERS})

    # 1. BOTH members carry real owner AND household counts at EVERY geography the ownership
    #    derivation reads — not at a corner, and not only in the province row.
    assert set(counts) == {_PROVINCE, *_ALL_QC_CMAS}, f"extract GEO set drifted: {sorted(counts)}"
    for geo, bands in counts.items():
        assert set(bands) == set(_SUB_FLOOR_MEMBERS), f"{geo}: sub-25 member coverage drifted"
        for member, (owner, total) in bands.items():
            assert 0 < owner < total, (
                f"{geo}[{member}]: {owner} owners of {total} households — a published "
                f"owner-maintainer rate below 25 is what the floor's premise denies exists")

    # 2. The QFE's own cited cells, exactly (an external anchor: measured by a different agent
    #    from the same extract, and the numbers the spec's amendment #12 quotes).
    for geo, cells in _QFE_SUB_FLOOR_CELLS.items():
        for member, expected in cells.items():
            assert counts[geo][member] == expected, (
                f"{geo}[{member}]: {counts[geo][member]} does not reproduce the QFE's "
                f"{expected} (docs/audits/dispatch/2026-08-15-qfe-retriage-task-26.md)")

    # 3. The published member set, enumerated: nothing under 15 (the surviving claim), and the
    #    two youngest published bands are exactly the sub-floor pair above.
    published = _independent_published_age_members()
    assert published == set(_PUBLISHED_AGE_MEMBERS), (
        f"the extract's age dimension drifted: {sorted(published)}")

    # 4. THE ASYMMETRY, which is the finding: one module, one age dimension of one extract, two
    #    band specs — and the ONLY members the headship spec reads that the ownership spec does
    #    not are the two youngest published bands. That is the assertion this file needed.
    headship_members = {m for m, _lo, _hi in census._HEADSHIP_MEMBER_SPEC}
    ownership_members = {m for *_, members in census._AGE_BAND_SPEC for m in members}
    assert headship_members - ownership_members == set(_SUB_FLOOR_MEMBERS), (
        "the two specs no longer differ by exactly the sub-25 pair: "
        f"headship-only = {sorted(headship_members - ownership_members)}")
    assert not (ownership_members - headship_members), (
        "the ownership spec reads a member the headship spec does not — the asymmetry this "
        "gate describes has reversed and the note above is stale")


def test_zero_support_note_calls_the_sub_25_zero_a_CHOICE_and_cites_what_is_published():
    """The corrected sentence, pinned on BOTH surfaces (amendment #12).

    The retired clause attributed the sub-25 zero to the table's silence. It is paraphrased
    rather than quoted anywhere in this file on purpose (the `p_imm` precedent): a test that
    matched the dead string would keep reading a museum label long after the note moved. What
    is asserted instead is the LIVE claim — the note names `_AGE_BAND_SPEC` as the omitting
    choice, cites a published sub-25 cell in role-bound form, and records why the omission
    stands for now.

    Committed artifact AND fresh derivation, for the reason the rest of this file gives: a
    producer mutation regenerated THROUGH the artifact moves both together, so pinning only
    the artifact would leave the producer uncovered.
    """
    owner, total = _independent_band_counts(
        {"20-24": ("20 to 24 years",)})[_PROVINCE]["20-24"]
    fresh = derive_headship_from_sources(DATA_DIR / CENSUS_EXTRACT, DATA_DIR / POP_QC_WORKBOOK)

    for surface, provenance in (("committed", _committed_headship()["_provenance"]),
                                ("fresh", fresh["_provenance"])):
        note = provenance["zero_support_note"]
        assert "_AGE_BAND_SPEC" in note and "_HEADSHIP_MEMBER_SPEC" in note, (
            f"{surface}: the note does not name the two band specs whose asymmetry IS the "
            f"choice it now describes: {note!r}")
        assert f"{owner:,} owners of {total:,} households" in note, (
            f"{surface}: the note does not cite a published sub-25 cell in role-bound form "
            f"(expected {owner:,} owners of {total:,} households): {note!r}")
        assert "age-resolved headship FIRST, then the floor" in note, (
            f"{surface}: the note states the omission without spec §7's binding ordering "
            f"constraint, which is the only thing that makes it a standing choice: {note!r}")
        assert "MUST BE RE-MEASURED" in note, (
            f"{surface}: amendment #12's quantified-floor-effect legs were measured on the "
            f"BANDED curve; the note must say they do not survive this one: {note!r}")


def test_the_sub_25_clause_RETIRES_ITSELF_loudly_when_the_ownership_lattice_is_extended(
        monkeypatch):
    """The clause's own expiry, pinned — because a self-retiring sentence that retires SILENTLY
    is just a malformed record shipped inside a green suite.

    `_zero_support_note` cites the omitted members and their counts from the two band specs, so
    the day `_AGE_BAND_SPEC` reaches the youngest published member the clause has no subject.
    Both halves are asserted: the derivation of the omission goes EMPTY under an extended spec,
    and the note REFUSES to render an empty one. Extending the lattice is a supervised change
    (spec §7's ordering constraint gates it), so the stop costs a rewrite that was due anyway.
    """
    cube = census.read_totals_cube(DATA_DIR / CENSUS_EXTRACT)
    assert census._ownership_spec_omitted_members(cube), (
        "the ownership spec already omits nothing — this gate's premise is gone")

    extended = census._AGE_BAND_SPEC + (
        ("15-24", 15, 24, ("15 to 19 years", "20 to 24 years")),)
    monkeypatch.setattr(census, "_AGE_BAND_SPEC", extended)
    assert census._ownership_spec_omitted_members(cube) == ()

    with pytest.raises(LoaderError, match="retired itself"):
        census._zero_support_note(1_364_340.0, ("15 to 19 years", 10_920), (),
                                  members=14, tolerance=37.5, delta=5)


def test_headship_provenance_states_WHICH_population_its_rate_multiplies():
    """Run-6 carry (2026-08-13), the sibling of `living_arrangement`'s `multiplicand_note`.

    Two adjacent rate surfaces in this package take DIFFERENT multiplicands by design, and
    the difference is invisible in every number: headship's denominator is RAW ISQ published
    persons (collective/institutional residents INCLUDED, because ISQ publishes them), while
    the living-arrangement partition's denominator is PRIVATE-HOUSEHOLD persons, whose
    consumer must strip `collective_share_75plus` FIRST (cohort/init.py does). Applying the
    collective correction to headship understates households; omitting it on the partition
    double-counts collectives — and the first production consumer of headship (demand §6)
    landed in this run, so the rule is recorded ON the artifact rather than in a reader's
    head. The contrast clause is asserted, not just the word "collective": a note that says
    only "collectives are included" leaves the reader to guess whether the OTHER surface
    behaves the same way, which is the confusion itself.

    THE FOURTH ARM IS RULING V's (design panel §5.2). Age-resolving this curve made the two
    surfaces LOOK more alike — the tail is now single-year across 75-100, finer than
    `living_arrangement.json`'s 75+ cohort — so the note must state that the increased
    temptation to unify them is REFUSED, and refused on the DENOMINATOR rather than on
    granularity. Without that clause the note's contrast reads as an artefact of the old
    six-band coarseness, which the very next reader would be right to think this change had
    dissolved. Asserted on the committed bytes because the note rides the artifact digest.
    """
    note = _committed_headship()["_provenance"]["multiplicand_note"]
    lowered = note.casefold()
    assert "raw isq" in lowered and "includes collective" in lowered
    assert "must not be removed" in lowered, (
        f"multiplicand_note does not forbid the collective correction outright: {note!r}")
    assert "private-household persons" in lowered and "living_arrangement" in lowered, (
        f"multiplicand_note does not contrast the OTHER surface's multiplicand: {note!r}")
    assert "tempting" in lowered and "75-100" in lowered, (
        "multiplicand_note does not state that the age-resolved 75-100 tail makes unification "
        f"with living_arrangement.json MORE tempting: {note!r}")
    assert "still refused" in lowered, (
        f"multiplicand_note states the temptation without refusing it: {note!r}")


def test_ownership_provenance_must_be_dated_and_cited(tmp_path):
    """DIV carry (2026-08-13): ownership was the ONE rate surface without Anchor typing.

    Headship has enforced constants.py's charter rule since T13b — every rate instantiated as
    a `constants.Anchor` built from the artifact's OWN `as_of`/`source`, at derivation and
    again at load — while ownership recorded a `ref_date` that nothing read and typed
    nothing, so a de-dated or uncited ownership artifact still served rates. Same rule, same
    two legs, same message. (`as_of` REPLACED `ref_date` here rather than joining it: one
    date, spelled the way `Anchor` spells it — two spellings of one field is a second
    declaration site, and only one of them would have been load-bearing.)
    """
    for field in ("as_of", "source"):
        for value in ("", "   "):
            payload = _committed_artifact()
            payload["_provenance"][field] = value
            (tmp_path / census.OWNERSHIP_ARTIFACT).write_text(json.dumps(payload),
                                                              encoding="utf-8")
            with pytest.raises(LoaderError, match=f"empty {field}"):
                load_ownership_rates(data_dir=tmp_path)


def test_an_out_of_unit_ownership_rate_is_refused_AT_LOAD(tmp_path):
    """Anchor typing's unit leg on the ownership surface, at the load path.

    The committed artifact carries `_flag: borrowed_prior` markers inside `rates`; typing
    must skip them and still type every RATE (a typing pass that tripped on the flag, or one
    that skipped whole borrowed geographies, would leave five of eight surfaces unchecked —
    so the fixture below mutates a rate under a DERIVED geography and the flags stay put).
    """
    payload = _committed_artifact()
    payload["rates"][Geography.MTL_RMR.value]["75+"] = 1.5
    (tmp_path / census.OWNERSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        load_ownership_rates(data_dir=tmp_path)


def test_headship_derivation_refuses_an_unpinned_source(tmp_path):
    """Both sources, each naming ITSELF — the census extract and the ISQ pop workbook.

    A single "sha256" match would accept either message, so a swapped-argument derivation
    could pass; each leg asserts its own filename in the raised text.
    """
    for name, other in ((CENSUS_EXTRACT, POP_QC_WORKBOOK), (POP_QC_WORKBOOK, CENSUS_EXTRACT)):
        drifted_dir = tmp_path / f"drift-{name}"
        drifted_dir.mkdir()
        for source in (CENSUS_EXTRACT, POP_QC_WORKBOOK):
            shutil.copyfile(DATA_DIR / source, drifted_dir / source)
        with (drifted_dir / name).open("ab") as fh:
            fh.write(b"\n")
        with pytest.raises(LoaderError, match="sha256 drift") as exc:
            derive_headship_from_sources(drifted_dir / CENSUS_EXTRACT,
                                         drifted_dir / POP_QC_WORKBOOK)
        assert name in str(exc.value) and other not in str(exc.value), (
            f"the refusal does not name the drifted source {name}: {exc.value}")


def test_stale_headship_artifact_is_refused_at_load(tmp_path):
    """RULING L for headship — THREE digests, and each one must be checked.

    Headship has two committed sources plus the upstream raw anchor, so a single-digest check
    (ownership's shape) would leave two of the three unexecuted: an artifact derived from a
    stale POP workbook is exactly as wrong as one derived from a stale extract.
    """
    for field, mutate in (
            (CENSUS_EXTRACT, lambda p: p["_provenance"]["sources"].__setitem__(CENSUS_EXTRACT, "0" * 64)),
            (POP_QC_WORKBOOK, lambda p: p["_provenance"]["sources"].__setitem__(POP_QC_WORKBOOK, "0" * 64)),
            ("raw_source_sha256", lambda p: p["_provenance"].__setitem__("raw_source_sha256", "0" * 64))):
        payload = _committed_headship()
        mutate(payload)
        (tmp_path / HEADSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="sha256") as exc:
            load_headship_rates(data_dir=tmp_path)
        assert field in str(exc.value), (
            f"the refusal does not name the stale digest {field}: {exc.value}")


def test_unprovenanced_headship_artifact_is_refused_at_load(tmp_path):
    """Absence refuses too, at every shape that reaches the guard by a DIFFERENT operand."""
    shapes = (
        ("block absent", lambda p: p.pop("_provenance")),
        ("sources map absent", lambda p: p["_provenance"].pop("sources")),
        ("one source stripped", lambda p: p["_provenance"]["sources"].pop(POP_QC_WORKBOOK)),
        ("raw anchor stripped", lambda p: p["_provenance"].pop("raw_source_sha256")),
    )
    for shape, strip in shapes:
        payload = _committed_headship()
        strip(payload)
        (tmp_path / HEADSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="sha256") as exc:
            load_headship_rates(data_dir=tmp_path)
        assert "_provenance" in str(exc.value), f"{shape}: message does not name the block"


def test_headship_provenance_must_be_dated_and_cited(tmp_path):
    """constants.py's charter rule — "an undated constant is a defect" — ENFORCED, not stated.

    Every rate is instantiated as a `constants.Anchor` built from the artifact's OWN `as_of`
    and `source`, at derivation and again at load. So an artifact whose provenance loses its
    date or its citation serves NOTHING, and the rule is structural rather than a comment.
    """
    for field in ("as_of", "source"):
        for value in ("", "   "):
            payload = _committed_headship()
            payload["_provenance"][field] = value
            (tmp_path / HEADSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
            with pytest.raises(LoaderError, match=f"empty {field}"):
                load_headship_rates(data_dir=tmp_path)


def test_headship_artifact_records_and_checks_the_upstream_raw_anchor():
    """PART 2 / DIV F2: headship's numerator comes from the same extract, so it carries the
    same upstream anchor. Recorded in the artifact, and checked against the registry at
    derivation — a derivation whose extract has no registered raw member REFUSES.
    """
    prov = _committed_headship()["_provenance"]
    assert prov["raw_source_sha256"] == RAW_SOURCE_SHA256[CENSUS_EXTRACT]
    assert prov["raw_source_member"] == "98100231.csv"


def test_missing_headship_key_raises_rather_than_serving_an_empty_curve(tmp_path):
    """A renamed/absent top-level key must fail as a FILE error, not resurface downstream
    as 'no headship rate for age 35' — a message that reads as a holed curve."""
    (tmp_path / "headship_by_age.json").write_text(json.dumps({"headship_rates": {"75+": 0.62}}))
    with pytest.raises(LoaderError, match="headship"):
        load_headship_rates(data_dir=tmp_path)


def test_hors_rmr_is_province_net_of_all_six_cmas():
    """codex r4-F2: the residual is province NET OF ALL QC CMAs, not merely MTL+QC.

    Owner and total are netted separately THEN divided — never a difference of rates.
    The FINAL assertion is the discriminator: it pins that the two nettings give
    materially different answers, so this gate cannot pass under the wrong one.
    """
    counts = {geo: bands["75+"] for geo, bands in _independent_band_counts().items()}
    assert set(counts) == {_PROVINCE, *_ALL_QC_CMAS}, (
        f"extract GEO set drifted: {sorted(counts)}")

    prov_o, prov_t = counts[_PROVINCE]
    all_o = prov_o - sum(counts[c][0] for c in _ALL_QC_CMAS)
    all_t = prov_t - sum(counts[c][1] for c in _ALL_QC_CMAS)
    assert all_t > 0 and 0 <= all_o <= all_t, "residual counts left the feasible region"
    expected = all_o / all_t

    # BOTH surfaces: the committed artifact AND a fresh derivation. Asserting only the
    # artifact would leave the PRODUCER uncovered — a netting mutation REGENERATED THROUGH
    # moves the artifact with it, so the no-drift gate goes green and cannot be the backstop.
    # Measured 2026-08-08 (regenerate-through battery): the `fresh` leg below and
    # test_full_rate_table_matches_an_independent_recompute BOTH assert the fresh
    # derivation, so either one holds such a mutation.
    rates = load_ownership_rates()
    assert ownership_rate(rates, Geography.HORS_RMR, age=80) == pytest.approx(expected, rel=1e-12)
    fresh = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)["rates"]
    assert fresh[Geography.HORS_RMR.value]["75+"] == pytest.approx(expected, rel=1e-12)

    two_cma_o = prov_o - sum(counts[c][0] for c in ("Montréal (CMA), Que.", "Québec (CMA), Que."))
    two_cma_t = prov_t - sum(counts[c][1] for c in ("Montréal (CMA), Que.", "Québec (CMA), Que."))
    assert abs(two_cma_o / two_cma_t - expected) > 1e-3, (
        "netting only MTL+QC must give a MATERIALLY different rate, else this gate is vacuous")


def test_ra_members_borrow_the_parent_cma_rate_and_are_flagged():
    """spec §8: RA-level rows reuse their parent CMA rate, carrying `borrowed_prior`.

    The flag lives INSIDE `rates` deliberately — that is the sub-tree
    `load_ownership_rates` RETURNS, so a flag recorded only in `_provenance` prose would be
    invisible to every caller. (The no-drift gate compares the WHOLE payload, `_provenance`
    included, so it is not what scopes this.)
    """
    payload = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)
    rates = payload["rates"]
    borrowers = (Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13,
                 Geography.LANAUDIERE_RA14_PROXY, Geography.LAURENTIDES_RA15_PROXY,
                 Geography.MONTEREGIE_RA16_PROXY)
    for geo in borrowers:
        assert rates[geo.value]["_flag"] == "borrowed_prior", f"{geo.value} lost its flag"
        for band, value in rates[Geography.MTL_RMR.value].items():
            if band != "_flag":
                assert rates[geo.value][band] == value
    for geo in (Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR):
        assert "_flag" not in rates[geo.value], f"{geo.value} is derived, not borrowed"


def _committed_artifact() -> dict:
    return json.loads((DATA_DIR / "ownership_by_geo_age.json").read_text(encoding="utf-8"))


def _committed_provenance() -> dict:
    return _committed_artifact()["_provenance"]


def test_ca_caveat_carries_the_probe_note_denotation_in_full():
    """The caveat is the DURABLE record of what HORS_RMR denotes; a partial one misleads.

    Probe P2 §4 denotes the residual as 'Québec outside the six wholly-Québec CMAs —
    INCLUDING all 23 Census Agglomerations AND the Québec side of Ottawa-Gatineau', plus the
    two cross-border CAs. The shipped caveat named only the Census Agglomerations, dropping
    the one clause that matters for the downstream population join (below).

    The denotation clause is asserted CONTIGUOUSLY, not as bare tokens, and that is the
    whole gate. Measured 2026-08-08: `ottawa-gatineau` and `census agglomerations` each
    occur TWICE in the caveat — once in the denotation sentence and once in a later
    sentence that says nothing about what the residual contains ('Ottawa-Gatineau is
    parented to Ontario…', 'would EXCLUDE the Census Agglomerations'). So a bare-token
    check is satisfied by the WRONG sentence: dropping either half of the denotation
    clause regenerated cleanly and left all 19 gates green, reviving exactly the r5-F7
    defect this gate exists for. `campbellton` / `hawkesbury` / `wholly-québec` occur
    ONCE each, inside the denotation sentence, so those three are positionally safe as
    tokens — that measured split is why the loop keeps three and not five.
    """
    caveat = _committed_provenance()["ca_caveat"].casefold()
    assert ("including all 23 census agglomerations and the québec side of ottawa-gatineau"
            in caveat), (
        "ca_caveat no longer denotes the residual IN FULL — the clause naming the 23 Census "
        "Agglomerations and Ottawa-Gatineau's Québec side as INSIDE the residual is absent "
        "or fragmented (r5-F7). This clause drives the downstream rate x population join.")
    for token in ("campbellton", "hawkesbury", "wholly-québec"):
        assert token in caveat, f"ca_caveat dropped {token!r}"


def _territory_note_role_clauses(province, netted, census_territory, isq_hors_rmr, gap):
    """The four clauses that bind each figure to the ROLE it plays in the note.

    Each is asserted as a CONTIGUOUS substring, which is the whole gate (DIV F3): the two
    person counts are 2,740,546 (this rate's territory) and 2,384,575 (the population the
    rate multiplies), and SWAPPING them is precisely the confusion the note exists to
    prevent — yet five bare `f"{value:,.0f}" in note` asserts passed under the swap, because
    both digit strings were still present somewhere. Role-bound clauses cannot.
    """
    return (
        f"Le Québec {province:,.0f} minus the six wholly-QC RMRs {netted:,.0f} = "
        f"{census_territory:,.0f} persons (this rate's territory)",
        f"vs the ISQ literal row {isq_hors_rmr:,.0f} persons (the population the rate multiplies)",
        f"the {gap:,.0f}-person gap is exactly the ISQ Ottawa-Gatineau Québec-part row",
        f"= {gap / census_territory * 100:.2f}% of the Census residual territory / "
        f"{gap / isq_hors_rmr * 100:.2f}% of the ISQ hors-RMR population",
    )


def test_isq_territory_note_binds_each_figure_to_its_role():
    """Every figure cited in the artifact is RECOMPUTED here, never trusted as typed, and
    every figure is bound to its ROLE, never merely present (DIV F3).

    The note records that this Census rate's territory (province net of the six
    wholly-Québec CMAs, which INCLUDES the Québec side of Ottawa-Gatineau) is not the
    territory of the ISQ population it will multiply (`Territoire hors des RMR`, which
    EXCLUDES it — ISQ publishes Ottawa-Gatineau Québec-part-only, workbook footnote 2). The
    generated-artifact discipline says a cited value must be computed, so this reads the
    pinned ISQ workbook, then asserts the four role clauses AND re-runs itself against a
    figure-swapped copy of the note so the gate cannot pass vacuously.
    """
    import pandas as pd

    from demoflow.geography import normalize_label

    workbook = DATA_DIR / "pop-as-rmr-base.xlsx"
    pins.verify_pin(workbook, workbook.name)
    raw = pd.read_excel(workbook, sheet_name="Groupes d'âge", header=None)
    hdr = next(i for i, v in enumerate(raw[0]) if str(v).strip() == "Scénario")
    labels = {normalize_label(v): i for i, v in enumerate(raw.iloc[hdr]) if isinstance(v, str)}
    i_total = next(i for i, v in enumerate(raw.iloc[hdr + 1]) if str(v).strip() == "TOTAL")
    body = raw.iloc[hdr + 3:]
    rows = body[(body[labels["Scénario"]] == "Référence (A2026)")
                & (body[labels["Année"]] == 2021)
                & (body[labels["Sexe"]] == 3)]
    pop = {normalize_label(r[labels["Région"]]): float(r[i_total])
           for _, r in rows.iterrows()}

    six = ("RMR de Montréal", "RMR de Québec", "RMR de Saguenay", "RMR de Sherbrooke",
           "RMR de Trois-Rivières", "RMR de Drummondville")
    province = pop["Le Québec"]
    netted = sum(pop[r] for r in six)
    census_territory = province - netted
    isq_hors_rmr = pop["Territoire hors des RMR"]
    gap = census_territory - isq_hors_rmr

    # The gap is EXACTLY the ISQ Ottawa-Gatineau row — that identity is what makes the
    # mismatch structural rather than a rounding artifact.
    assert gap == pop["RMR d'Ottawa-Gatineau"]

    note = _committed_provenance()["isq_territory_note"]
    clauses = _territory_note_role_clauses(province, netted, census_territory, isq_hors_rmr, gap)
    for clause in clauses:
        assert clause in note, f"isq_territory_note does not carry the role clause: {clause!r}"

    # NON-VACUITY, measured: swap the two person counts — the rate's territory for the
    # population it multiplies — and at least one clause must fail. Under the retired
    # bare-token loop the swapped note passed every assert.
    swapped = (note.replace(f"{census_territory:,.0f}", "\x00")
                   .replace(f"{isq_hors_rmr:,.0f}", f"{census_territory:,.0f}")
                   .replace("\x00", f"{isq_hors_rmr:,.0f}"))
    assert swapped != note, "the figure-swap mutation did not apply — the leg below is vacuous"
    assert any(clause not in swapped for clause in clauses), (
        "the swapped-figure note still satisfies every clause — this gate pins PRESENCE, not "
        "ROLE, and the 2,740,546 <-> 2,384,575 confusion would ship (DIV F3)")


def test_stale_artifact_sha_is_refused_at_load(tmp_path):
    """STEERING RULING L — the load path itself must refuse a stale artifact.

    The fixture carries the REAL, complete `rates` block, so the strict-join leg cannot fire:
    the only reachable failure is the provenance leg, and a green here would mean the gate is
    absent rather than that the fixture was malformed.
    """
    payload = _committed_artifact()
    payload["_provenance"]["sha256"] = "0" * 64
    (tmp_path / "ownership_by_geo_age.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="sha256"):
        load_ownership_rates(data_dir=tmp_path)


def test_unprovenanced_artifact_is_refused_at_load(tmp_path):
    """RULING L, second leg: ABSENT `_provenance.sha256` refuses too.

    Absence is the more dangerous case — a mismatch announces itself, whereas an artifact
    with no recorded source digest is indistinguishable from a hand-authored rate table
    (exactly what ruling B forbids) and would otherwise load silently.

    BOTH absent shapes are fed, because they reach the guard through DIFFERENT operands and
    only the first was executed. Measured 2026-08-08: dropping just the
    `"sha256" not in provenance` operand left all 19 gates GREEN — so the digest-stripped
    shape was an unexecuted claim — and the artifact then died at `provenance["sha256"]` on a
    bare `KeyError`, a class no `except LoaderError` catches (the taxonomy argument `_count`
    makes in this same module). Asserting LoaderError on both shapes pins the guard AND its
    error class. The stripped shape is also the likelier real-world one (a hand-trimmed or
    partially-copied provenance block) and is the one the error message actually names.
    """
    for shape, strip in (("block absent", lambda p: p.pop("_provenance")),
                         ("digest stripped", lambda p: p["_provenance"].pop("sha256"))):
        payload = _committed_artifact()
        strip(payload)
        (tmp_path / "ownership_by_geo_age.json").write_text(
            json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="_provenance") as exc:
            load_ownership_rates(data_dir=tmp_path)
        # The message must NAME the missing digest, else the reader is told an artifact is
        # bad without being told which field to restore.
        assert "sha256" in str(exc.value), f"{shape}: message does not name the digest"


def test_ownership_artifact_records_and_checks_the_upstream_raw_anchor(tmp_path, monkeypatch):
    """PART 2 / DIV F2 — the refresh path's only external anchor.

    Every gate on this artifact compares CO-MOVING objects: the extract's own pin, the
    artifact's recorded digest, and a fresh derivation all move together when the extract is
    re-cut, so the composite legitimate-refresh motion (re-extract + re-pin + regen) passed
    19/19 on a materially different vintage. The 850,971,474-byte raw StatCan member cannot be
    committed, so its digest — recorded in probes/P2-census-tenure-age.md:16 since the pull — is
    now a REGISTRY pin that does NOT move with a re-extract: embedded in the artifact, checked
    at load, and required at derivation (an unregistered raw member refuses).
    """
    prov = _committed_provenance()
    assert prov["raw_source_sha256"] == RAW_SOURCE_SHA256[CENSUS_EXTRACT]
    assert prov["raw_source_member"] == "98100231.csv"

    payload = _committed_artifact()
    payload["_provenance"]["raw_source_sha256"] = "0" * 64
    (tmp_path / "ownership_by_geo_age.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="raw_source_sha256"):
        load_ownership_rates(data_dir=tmp_path)

    monkeypatch.delitem(pins.RAW_SOURCE_SHA256, CENSUS_EXTRACT)
    with pytest.raises(LoaderError, match="no raw-source anchor registered"):
        derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)


def test_a_half_registered_raw_anchor_refuses_instead_of_crashing(tmp_path, monkeypatch):
    """The raw anchor has TWO hand-maintained halves, and only one of them was gated.

    Found in review (2026-08-08): `RAW_SOURCE_SHA256` got a raising accessor (`raw_anchor`)
    plus a pins gate, while its twin `RAW_SOURCE_MEMBER` — keyed by the SAME extract name —
    was read by bare subscript at all four consumer sites. Measured before the fix, with the
    digest key present and only the member key dropped: `derive_ownership_from_csv` and
    `derive_headship_from_sources` both died on `KeyError('census_tenure_age_98100231.csv')`,
    a class no `except LoaderError` catches (the taxonomy argument `_count` makes in this same
    module) — the half-registered state escaped the loader taxonomy at precisely the sites
    whose job is to refuse. The worse leg was the two refusal-message f-strings: a
    SIMULTANEOUS digest drift + missing member turned an informative drift refusal into that
    same crash, so the reader lost the finding along with the message.

    The asymmetry asserted below is deliberate. The two PRODUCERS raise, because a
    `_provenance` block naming no upstream member is a half-provenanced artifact — the same
    argument `raw_anchor` makes for the digest. The two REFUSAL messages instead degrade the
    member to '?' (the pattern `verify_raw_anchor` already uses): routing them through a
    raiser would replace a DRIFT refusal with a registry refusal and destroy the vintage
    information that is the whole reason the reader is being stopped.
    """
    monkeypatch.delitem(pins.RAW_SOURCE_MEMBER, CENSUS_EXTRACT)
    assert CENSUS_EXTRACT in pins.RAW_SOURCE_SHA256, (
        "this gate must exercise the HALF-registered state — with the digest half absent the "
        "`raw_anchor` guard fires first and the member half is never reached")

    for label, produce in (
            ("ownership", lambda: derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)),
            ("headship", lambda: derive_headship_from_sources(
                DATA_DIR / CENSUS_EXTRACT, DATA_DIR / POP_QC_WORKBOOK))):
        with pytest.raises(LoaderError, match="no raw-source member registered") as exc:
            produce()
        assert CENSUS_EXTRACT in str(exc.value), (
            f"{label}: the refusal does not name the extract whose member is unregistered")

    for name, payload, load in (
            (census.OWNERSHIP_ARTIFACT, _committed_artifact(), load_ownership_rates),
            (HEADSHIP_ARTIFACT, _committed_headship(), load_headship_rates)):
        payload["_provenance"]["raw_source_sha256"] = "0" * 64
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="raw_source_sha256") as exc:
            load(data_dir=tmp_path)
        assert "0" * 64 in str(exc.value), (
            f"{name}: the missing member name cost the reader the DRIFT reason")


def test_registry_pins_the_census_extract():
    """The extract was tracked-but-unpinned; the derivation reads its digest FROM pins."""
    assert CENSUS_EXTRACT in pins.WORKBOOK_SHA256, (
        f"{CENSUS_EXTRACT} is not in the pins registry — the PIT chain is unpinned")
    digest = hashlib.sha256((DATA_DIR / CENSUS_EXTRACT).read_bytes()).hexdigest()
    assert digest == pins.WORKBOOK_SHA256[CENSUS_EXTRACT]


def test_derivation_refuses_an_unpinned_extract(tmp_path):
    """DIV surface 1 — vintage identity: a byte-drifted extract must never derive rates."""
    drifted = tmp_path / CENSUS_EXTRACT
    shutil.copyfile(DATA_DIR / CENSUS_EXTRACT, drifted)
    with drifted.open("a", encoding="utf-8") as fh:
        fh.write("2021,Quebec,2021A000224,x,x,x,x,x,9.9.9,1,,1,,0,,0,\n")
    with pytest.raises(LoaderError, match="sha256 drift"):
        derive_ownership_from_csv(drifted)


def test_new_upstream_cma_raises_rather_than_going_un_netted(tmp_path, monkeypatch):
    """DIV surface 3 — blast radius: HORS_RMR nets province against EVERY QC CMA, so the
    netted-CMA list is load-bearing. A CMA appearing upstream that the list does not carry
    would leave that CMA's households INSIDE the residual, silently changing the geography
    HORS_RMR denotes while every rate stays in [0,1] and every other gate stays green.
    The GEO-set equality gate must red instead — this fires it.
    """
    src = (DATA_DIR / CENSUS_EXTRACT).read_text(encoding="utf-8")
    added = tmp_path / CENSUS_EXTRACT
    with added.open("w", encoding="utf-8", newline="") as fh:
        fh.write(src)
        csv.writer(fh, lineterminator="\n").writerow([
            "2021", "Gatineau (CMA), Que.", "2021S0503505",
            "Total - Structural type of dwelling", "Total - Condominium status",
            "Total - Household type including census family structure",
            "Number of private households", "75 to 84 years", "99.1.1.1.1.14",
            "100", "", "50", "", "50", "", "0", "",
        ])
    monkeypatch.setitem(pins.WORKBOOK_SHA256, CENSUS_EXTRACT,
                        hashlib.sha256(added.read_bytes()).hexdigest())
    with pytest.raises(LoaderError, match="GEO set"):
        derive_ownership_from_csv(added)


def test_header_position_drift_raises(tmp_path, monkeypatch):
    """DIV surface 2 — schema drift: the positional bindings are asserted against the live
    header, so a renamed/reordered tenure column raises instead of reading the wrong column.

    The copy is RE-PINNED first (test_isq_loader.py:394 pattern) — otherwise the pin gate
    fires and this gate never reaches the code it exists to cover.
    """
    src = (DATA_DIR / CENSUS_EXTRACT).read_text(encoding="utf-8")
    head, rest = src.split("\n", 1)
    drifted_header = head.replace("Tenure (4):Owner[2]", "Tenure (4):Owner-occupied[2]")
    assert drifted_header != head, "header mutation did not apply"
    mutated = tmp_path / CENSUS_EXTRACT
    mutated.write_text(drifted_header + "\n" + rest, encoding="utf-8")
    monkeypatch.setitem(pins.WORKBOOK_SHA256, CENSUS_EXTRACT,
                        hashlib.sha256(mutated.read_bytes()).hexdigest())
    with pytest.raises(LoaderError, match="header"):
        derive_ownership_from_csv(mutated)


def test_absent_statistic_or_total_member_names_the_member_and_not_the_geographies(
        tmp_path, monkeypatch):
    """PART 3 / DIV F3 second half: two refusals that named the WRONG cause.

    A renamed `Statistics (3C)` member or a renamed `Total -` member empties the rate slice —
    every row is skipped by the slice predicate — and the only surviving check was the GEO-set
    equality gate, which then raised "GEO set is [], expected [the seven geographies…]". The
    reader is sent to the geography map and the netting rule (codex r4-F2) for a fault that is
    in a DIFFERENT dimension's member label. Each mutant must now name the absent member, and
    must NOT mention the geographies at all.
    """
    src = (DATA_DIR / CENSUS_EXTRACT).read_text(encoding="utf-8")
    mutants = (
        ("Number of private households", "Number of private households (2021)"),
        ("Total - Condominium status", "All condominium statuses"),
    )
    for original, renamed in mutants:
        mutated = tmp_path / f"{original[:12]}-{CENSUS_EXTRACT}"
        text = src.replace(original, renamed)
        assert text != src, f"the {original!r} rename did not apply"
        mutated.write_text(text, encoding="utf-8")
        monkeypatch.setitem(pins.WORKBOOK_SHA256, mutated.name,
                            hashlib.sha256(mutated.read_bytes()).hexdigest())
        with pytest.raises(LoaderError) as exc:
            derive_ownership_from_csv(mutated)
        message = str(exc.value)
        assert original in message, (
            f"the refusal does not name the absent member {original!r}: {message}")
        assert "GEO set" not in message and _GEO_SOURCE[Geography.MTL_RMR] not in message, (
            f"the refusal still blames the geographies for an absent {original!r}: {message}")


# --- T13b PART 1 (run-9): EXTERNAL PUBLISHED ANCHORS --------------------------------
# THE PROPERTY these two gates have that no other gate in this file has: their expected
# values were never read from anything this repo commits. Every other check compares
# CO-MOVING objects — the extract, its own pin, the raw anchor, the derived artifacts and a
# fresh derivation all move together under a hand re-cut plus a hand-edited
# `pins.RAW_SOURCE_SHA256`, which is the residual DIV F2 explicitly left open ("NOT closed by
# this: an arbitrary hand re-extract that also edits the raw anchor"). A hand-cut extract
# CANNOT satisfy the two literals below, because satisfying them requires agreeing with what
# StatCan itself publishes at those coordinates.
#
# The cells were retrieved LIVE from the WDS on 2026-08-08 — the same coordinate path
# `scripts/pull_living_arrangement.py` uses — and typed here as CITED literals. They are NOT
# read from `data/census_tenure_age_98100231.csv` at any point, and this test makes no network
# call: a gate that re-fetched would be an availability check, not an anchor.
#
# THREE live traps this fetch was written against, all confirmed:
#   - the 7 non-age dimensions must EACH be addressed by a resolved member id; a slot left 0
#     or guessed as 1 returns a different, entirely plausible number. Ids were resolved from
#     live `getCubeMetadata` by exact member NAME, with ambiguity raising.
#   - this cube has NO census-year dimension (unlike 98-10-0134-01) — its period axis is
#     TIME, so `latestN: 1` is only safe behind a refPer guard. Every returned point carried
#     `refPer` 2021-01-01.
#   - `75+` is NOT a published member (probe P2 §5), so each 75+ figure below is the sum of
#     the two published constituents, each fetched as its own cell.
#
# The built coordinates were cross-checked against the COMMITTED extract's own `Coordinate`
# column before any value was read: all six addresses agree on slots 1-6 (e.g. province
# 75-84 = `24.1.1.1.1.14`, Québec CMA 85+ = `36.1.1.1.1.15`), the extract carrying no 7th
# slot because tenure is WIDE in its columns. That is what pins the ADDRESS; the two
# `Total - Age of primary household maintainer` cells below pin the GEOGRAPHY (the dimension
# has 166 members and "Québec" is name-ambiguous in a way "Quebec" is not).
_WDS_CITATION = (
    'Statistics Canada. Table 98-10-0231-01, "Age of primary household maintainer by tenure: '
    'Canada, provinces and territories, census metropolitan areas and census agglomerations", '
    "2021 Census, released 2022-09-21T08:30. Cells retrieved 2026-08-08 from "
    "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods "
    "(productId 98100231, latestN=1, every point refPer 2021-01-01, status SUCCESS, "
    "statusCode 0, symbolCode 0). Member ids resolved from live getCubeMetadata by exact "
    "member name — Geography: 'Quebec'=24, 'Québec (CMA), Que.'=36; Structural type of "
    "dwelling: 'Total - Structural type of dwelling'=1; Condominium status: 'Total - "
    "Condominium status'=1; Household type including census family structure: 'Total - "
    "Household type including census family structure'=1; Statistics: 'Number of private "
    "households'=1; Age of primary household maintainer: '75 to 84 years'=14, '85 years and "
    "over'=15, 'Total - Age of primary household maintainer'=1; Tenure: 'Total - Tenure'=1, "
    "'Owner'=2. Dimension positions 1..7 in that order; coordinates are 10 slots with three "
    "trailing zeros."
)
# Both names ALIAS the test-owned literals already transcribed above rather than re-typing
# them: two spellings of one member label in one file is a drift vector, and re-pointing
# either alias still reds these gates (the published counts would then be compared against a
# different geography's / a different member's committed cell).
_QC_CMA_LABEL = _GEO_SOURCE[Geography.QC_RMR]
_ALL_AGES = _PUBLISHED_MAINTAINER_TOTAL_MEMBER
# (GEO, age member, tenure) -> published count. The full 2 x 3 x 2 fetch, verbatim.
_PUBLISHED_CELLS = {
    # Québec CMA — coordinates 36.1.1.1.1.{14,15,1}.{1,2}.0.0.0
    (_QC_CMA_LABEL, "75 to 84 years", "Total - Tenure"): 36_005,
    (_QC_CMA_LABEL, "75 to 84 years", "Owner"): 20_155,
    (_QC_CMA_LABEL, "85 years and over", "Total - Tenure"): 10_000,
    (_QC_CMA_LABEL, "85 years and over", "Owner"): 4_405,
    (_QC_CMA_LABEL, _ALL_AGES, "Total - Tenure"): 387_955,
    (_QC_CMA_LABEL, _ALL_AGES, "Owner"): 226_070,
    # Quebec province — coordinates 24.1.1.1.1.{14,15,1}.{1,2}.0.0.0
    (_PROVINCE, "75 to 84 years", "Total - Tenure"): 336_170,
    (_PROVINCE, "75 to 84 years", "Owner"): 202_830,
    (_PROVINCE, "85 years and over", "Total - Tenure"): 103_640,
    (_PROVINCE, "85 years and over", "Owner"): 55_745,
    (_PROVINCE, _ALL_AGES, "Total - Tenure"): 3_749_035,
    (_PROVINCE, _ALL_AGES, "Owner"): 2_245_600,
}


def _published_75plus(geo: str) -> tuple[int, int]:
    """(owner, total) for the 75+ band, summed from the two PUBLISHED constituents."""
    members = ("75 to 84 years", "85 years and over")
    return (sum(_PUBLISHED_CELLS[(geo, m, "Owner")] for m in members),
            sum(_PUBLISHED_CELLS[(geo, m, "Total - Tenure")] for m in members))


def _committed_all_ages_totals() -> dict[str, tuple[int, int]]:
    """{GEO: (owner, total)} at the extract's own published all-ages maintainer member."""
    counts = _independent_band_counts({_PUBLISHED_TOTAL_BAND: (_ALL_AGES,)})
    return {geo: bands[_PUBLISHED_TOTAL_BAND] for geo, bands in counts.items()}


def test_qc_cma_75plus_rate_matches_the_externally_published_statcan_cells():
    """ANCHOR 1 — Québec CMA 75+, against StatCan's own published cells.

    Cited: _WDS_CITATION. Québec (CMA), Que., `Total -` member of every non-age dimension, at
    statistic `Number of private households`: 75-84 owner 20,155 / total 36,005 and 85+ owner
    4,405 / total 10,000, so the 75+ band is 24,560 / 46,005 = 0.5338550... -> 0.534.

    WHY THIS CELL. QC_RMR is the geography the mutation battery caught shipping green from the
    WRONG CMA (module docstring), and until now its only coverage was
    `test_full_rate_table_matches_an_independent_recompute`, which recomputes from the
    COMMITTED extract — so a hand re-cut extract with a hand-edited raw anchor moved that gate
    with it. These literals do not move: they are what StatCan publishes.

    NON-VACUITY is asserted, not assumed. The discriminator has to survive the round-3
    tolerance, so the gate proves at run time that MTL's 75+ rate does NOT round to the same
    three decimals (0.562 vs 0.534) — otherwise the mandated round-3 form would be satisfied
    by exactly the wrong-CMA mutation it exists to catch. The exact COUNT identity below is
    the second, rounding-immune leg.
    """
    owner, total = _published_75plus(_QC_CMA_LABEL)

    # Leg 1 — exact counts. Immune to any rounding coincidence: the committed extract's own
    # QC CMA 75+ cell must BE the published pair, digit for digit.
    counts = _independent_band_counts()
    assert counts[_QC_CMA_LABEL]["75+"] == (owner, total), (
        f"the committed extract's Québec CMA 75+ cell {counts[_QC_CMA_LABEL]['75+']} is not "
        f"StatCan's published {(owner, total)} — the extract was cut from a different vintage "
        f"or a different address ({_WDS_CITATION})")

    # Leg 2 — the mandated round-3 rate form, at both consumer surfaces (loader + producer).
    rates = load_ownership_rates()
    assert round(ownership_rate(rates, Geography.QC_RMR, age=78), 3) == round(owner / total, 3)
    fresh = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)["rates"]
    assert fresh[Geography.QC_RMR.value]["75+"] == pytest.approx(owner / total, rel=1e-12)

    # Leg 3 — the round-3 tolerance actually DISCRIMINATES the wrong-CMA mutation.
    mtl_owner, mtl_total = counts[_GEO_SOURCE[Geography.MTL_RMR]]["75+"]
    assert round(mtl_owner / mtl_total, 3) != round(owner / total, 3), (
        "MTL and QC 75+ round to the same three decimals, so the round-3 anchor above cannot "
        "discriminate the wrong-CMA mutation — this gate needs a tighter tolerance")

    # Leg 4 — GEOGRAPHY resolution: the published all-ages cell for this member. The dimension
    # carries 166 members; agreeing here is what says id 36 is the geography we mean.
    assert _committed_all_ages_totals()[_QC_CMA_LABEL] == (
        _PUBLISHED_CELLS[(_QC_CMA_LABEL, _ALL_AGES, "Owner")],
        _PUBLISHED_CELLS[(_QC_CMA_LABEL, _ALL_AGES, "Total - Tenure")])


def test_hors_rmr_netting_identity_is_anchored_by_the_published_province_cell():
    """ANCHOR 2 — the HORS_RMR residual, with its province term taken from StatCan.

    Cited: _WDS_CITATION. Quebec (province), same slice: 75-84 owner 202,830 / total 336,170
    and 85+ owner 55,745 / total 103,640, so the 75+ band is 258,575 / 439,810.

    HORS_RMR is `province NET OF all six wholly-Québec CMAs` (codex r4-F2), and the province
    term is the whole residual's scale — it is ~74% larger than the six CMAs combined, so a
    wrong province cell moves HORS_RMR more than any other single input while leaving the rate
    a perfectly plausible fraction. `test_hors_rmr_is_province_net_of_all_six_cmas` pins the
    NETTING but reads the province row from the committed extract, so a hand re-cut extract
    plus a hand-edited raw anchor moves it. This gate replaces that term with the published
    one: the netting identity must reproduce the derivation's residual denominator (and its
    numerator) from a number this repo does not own.

    Equivalently — and stated plainly so the gate is not read as stronger than it is — the
    count identity holds iff the extract's province row IS the published province cell. That
    is exactly the claim a hand re-cut extract cannot fake, and the rate legs then carry it
    through to the producer.
    """
    prov_owner, prov_total = _published_75plus(_PROVINCE)

    counts = _independent_band_counts()
    assert set(counts) == {_PROVINCE, *_ALL_QC_CMAS}, f"extract GEO set drifted: {sorted(counts)}"
    cma_owner = sum(counts[c]["75+"][0] for c in _ALL_QC_CMAS)
    cma_total = sum(counts[c]["75+"][1] for c in _ALL_QC_CMAS)

    # The netting identity, with the province term EXTERNAL and the six CMA terms committed.
    hors_owner = prov_owner - cma_owner
    hors_total = prov_total - cma_total
    assert hors_total > 0 and 0 <= hors_owner <= hors_total, "residual left the feasible region"

    # Leg 1 — it must reproduce the residual the derivation actually forms, count for count.
    committed_prov_owner, committed_prov_total = counts[_PROVINCE]["75+"]
    assert (hors_owner, hors_total) == (committed_prov_owner - cma_owner,
                                       committed_prov_total - cma_total), (
        f"the published province cell {(prov_owner, prov_total)} does not reproduce the "
        f"derivation's HORS_RMR residual: the committed extract's province row is "
        f"{(committed_prov_owner, committed_prov_total)} ({_WDS_CITATION})")

    # Leg 2 — carried through to both consumer surfaces (loader + producer), so a netting
    # mutation regenerated THROUGH the artifact cannot pass this gate either.
    rates = load_ownership_rates()
    assert ownership_rate(rates, Geography.HORS_RMR, age=80) == pytest.approx(
        hors_owner / hors_total, rel=1e-12)
    fresh = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)["rates"]
    assert fresh[Geography.HORS_RMR.value]["75+"] == pytest.approx(
        hors_owner / hors_total, rel=1e-12)

    # Leg 3 — GEOGRAPHY resolution AND the headship numerator's independent aggregate. The
    # published all-ages province total (3,749,035) is the very figure
    # `test_headship_numerator_closes_against_the_published_maintainer_total` closes the
    # banded maintainer sum against — until now read from the committed extract, i.e. a
    # co-moving aggregate. Anchoring it here gives the HEADSHIP side an external term too.
    assert _committed_all_ages_totals()[_PROVINCE] == (
        _PUBLISHED_CELLS[(_PROVINCE, _ALL_AGES, "Owner")],
        _PUBLISHED_CELLS[(_PROVINCE, _ALL_AGES, "Total - Tenure")])


# ===========================================================================================
# OPERATOR RULING V (2026-08-19): the AGE-RESOLVED headship curve
# ===========================================================================================
#
# TEST-OWNED oracle inputs, transcribed from the PUBLISHED dimension and never imported from
# `census.py` — the same discipline `_SPEC_HEADSHIP_BAND_MEMBERS` carried for the six bands it
# replaces. The point of the ruling is that the extract publishes FOURTEEN maintainer-age
# members and the loader was consuming six; an oracle that read the member list off the code
# under test could not tell those two apart.
#
# THE MEMBERS ARE NOT ALL FIVE-YEAR. Twelve are (15-19 … 70-74); `75 to 84 years` is TEN-year
# and `85 years and over` is open-ended, closing at 100 only because the ISQ denominator does
# (`_POP_TERMINAL_AGE`). Every classical graduation multiplier (Sprague, Beers,
# Karup-King-Newton) is defined for UNIFORM five-year panels and is refused here for that
# reason — the granularity degrades exactly where the supply side lives.
_SPEC_HEADSHIP_MEMBERS = (
    ("15 to 19 years", 15, 19), ("20 to 24 years", 20, 24), ("25 to 29 years", 25, 29),
    ("30 to 34 years", 30, 34), ("35 to 39 years", 35, 39), ("40 to 44 years", 40, 44),
    ("45 to 49 years", 45, 49), ("50 to 54 years", 50, 54), ("55 to 59 years", 55, 59),
    ("60 to 64 years", 60, 64), ("65 to 69 years", 65, 69), ("70 to 74 years", 70, 74),
    ("75 to 84 years", 75, 84), ("85 years and over", 85, 100),
)
# The six LEGACY bands, kept for provenance and for the C3 identity gate only — never a lookup
# path. Each is an EXACT union of published members, which is why per-member closure SUBSUMES
# the band identity rather than merely being compatible with it.
_SPEC_LEGACY_BANDS = (("0-19", 0, 19), ("20-34", 20, 34), ("35-54", 35, 54),
                      ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 100))
# The published Owner column at GEO=Quebec for the whole age dimension and for the two members
# the ownership lattice drops. Their difference is the base-year OwnerStock every member-closed
# curve produces, shape-invariantly — see the identity test below.
_QC_OWNERS_ALL_AGES = 2245600
_QC_OWNERS_15_19 = 1150
_QC_OWNERS_20_24 = 17170


def _independent_member_counts() -> dict[str, tuple[int, int]]:
    """{published member: (owner, total)} at GEO=Quebec, through this file's OWN reader —
    one pseudo-band per member, so the oracle shares the reader and nothing else."""
    per_member = {label: (label,) for label, _lo, _hi in _SPEC_HEADSHIP_MEMBERS}
    return _independent_band_counts(per_member)[_PROVINCE]


def _independent_member_maintainers() -> dict[str, int]:
    return {label: total for label, (_owner, total) in _independent_member_counts().items()}


def _independent_persons_by_age() -> dict[int, float]:
    return dict(census._qc_persons_by_age(DATA_DIR / POP_QC_WORKBOOK))


def _fresh_headship() -> dict:
    return derive_headship_from_sources(DATA_DIR / CENSUS_EXTRACT, DATA_DIR / POP_QC_WORKBOOK)


def _curves(payload) -> dict[str, dict[int, float]]:
    return {shape: {int(a): v for a, v in curve.items()}
            for shape, curve in payload["headship"].items()}


def test_the_member_spec_is_the_published_dimension_and_the_legacy_bands_derive_from_it():
    """The 14 published members, in published order, with the two non-five-year members
    carried as they are published. The legacy band members are DERIVED by containment from
    this one spec, so a member cannot exist for the curve and be absent from the provenance."""
    assert census._HEADSHIP_MEMBER_SPEC == _SPEC_HEADSHIP_MEMBERS
    assert census._HEADSHIP_LEGACY_BAND_SPEC == _SPEC_LEGACY_BANDS
    assert census._legacy_band_members() == _SPEC_HEADSHIP_BAND_MEMBERS
    # the granularity claim itself, asserted rather than commented
    widths = [hi - lo + 1 for _l, lo, hi in _SPEC_HEADSHIP_MEMBERS]
    assert widths.count(5) == 12 and widths[-2] == 10 and widths[-1] == 16


def test_per_member_closure_holds_on_every_published_member_for_both_arms():
    """G1, the contract. Σ_{a∈m} P(a)·h(a) = M_m for all 14 published members AND the declared
    (0, 14, 0) member, on BOTH arms. The construction makes this ALGEBRAIC — the member
    endpoints ARE interpolation knots, so the single-year counts telescope to the knot
    difference independently of the tangent rule — which is why it is asserted at an absolute
    household tolerance and not at a relative epsilon someone has to tune."""
    persons = _independent_persons_by_age()
    members = _independent_member_maintainers()
    for shape, curve in _curves(_fresh_headship()).items():
        for label, lo, hi in _SPEC_HEADSHIP_MEMBERS:
            got = sum(persons[a] * curve[a] for a in range(lo, hi + 1))
            assert abs(got - members[label]) <= 1e-6, f"{shape}[{label}]: closure {got}"
        assert sum(persons[a] * curve[a] for a in range(0, 15)) == 0.0


def test_the_legacy_six_band_maintainers_and_rates_reproduce_from_the_fine_curve():
    """G3 / falsifier F3. Every legacy band is an exact union of published members, so a
    member-closed curve reproduces `band_maintainers`, `band_persons` and the six band RATES
    with nothing deleted to dodge a mismatch. The rates are asserted BIT-IDENTICAL because
    that is what is measured; the generator's own gate is the honest 1e-6 absolute."""
    persons = _independent_persons_by_age()
    members = _independent_member_maintainers()
    payload = _fresh_headship()
    for shape, curve in _curves(payload).items():
        for band, lo, hi in _SPEC_LEGACY_BANDS:
            expected_n = sum(members[m] for m in _SPEC_HEADSHIP_BAND_MEMBERS[band])
            band_persons = sum(persons[a] for a in range(lo, hi + 1))
            got = sum(persons[a] * curve[a] for a in range(lo, hi + 1))
            assert abs(got - expected_n) <= 1e-6, f"{shape}[{band}]"
            assert got / band_persons == expected_n / band_persons, f"{shape}[{band}] rate"
    prov = payload["_provenance"]
    assert prov["band_maintainers"] == {
        band: sum(members[m] for m in _SPEC_HEADSHIP_BAND_MEMBERS[band])
        for band, _lo, _hi in _SPEC_LEGACY_BANDS}


def test_headship_is_EXACTLY_zero_below_fifteen_on_both_arms():
    """G6 / falsifier F2, and the claim is a POSITIVE BOUND, never an absence claim: the
    dimension declares its own cardinality (15) = one total + 14 members with none under 15,
    and the closure residual bounds any unpublished member at |5 + X| ≤ 2.5 × 16 = 40, so
    X ≤ 35 households against 1,364,340 persons — below rounding scale. Identity, not
    `== 0.0` on a rounded value."""
    for shape, curve in _curves(_fresh_headship()).items():
        for age in range(0, 15):
            assert curve[age] == 0.0 and repr(curve[age]) == "0.0", f"{shape}[{age}]"


def test_support_is_exactly_the_101_integer_ages_on_every_carried_shape():
    """G5. A holed `expo_cum_fb` curve would break the sweep leg silently — the class
    `owner_stock._headship`'s message exists to prevent — so the strict join runs over BOTH
    carried shapes, not only the central one."""
    payload = _fresh_headship()
    assert set(payload["headship"]) == set(census.HEADSHIP_SHAPES)
    assert payload["central_shape"] == census.HEADSHIP_CENTRAL_SHAPE
    for shape, curve in _curves(payload).items():
        assert sorted(curve) == list(range(0, 101)), shape


def test_the_range_certificate_is_a_computed_supremum_below_one():
    """G4. `0 ≤ h` is true by construction (a monotone cumulative cannot difference negative);
    `h ≤ 1` is NOT a theorem of the method — the monotonicity filter bounds the tangent only by
    3× the largest member rate — so it is CERTIFIED: the closed-form maximum of the derivative
    quadratic on every Hermite segment, asserted ≤ 1, raising rather than shipping."""
    payload = _fresh_headship()
    cert = payload["_provenance"]["range_certificate"]
    assert set(cert) == set(census.HEADSHIP_SHAPES)
    for shape, curve in _curves(payload).items():
        assert 0.0 < cert[shape] <= 1.0
        assert max(curve.values()) <= cert[shape] + 1e-12, shape
        assert all(0.0 <= v <= 1.0 for v in curve.values()), shape


def test_the_tail_is_NOT_monotone_and_the_terminal_end_rule_is_PINNED():
    """Falsifier F5 plus the one defect closure cannot catch.

    Global monotonicity is REFUTED by the committed bytes: the published members peak at 70-74
    (0.6476) and fall through 75-84 (0.6300) to 85+ (0.4948). The first two assertions pin that.

    THE THIRD PINS THE END RULE, and it is the only assertion here that can see it. Closure
    telescopes independently of the tangent rule, so an under-specified terminal slope passes
    every gate in this file. A PLAIN LAST-SECANT terminal slope produces `h(90) → h(100)`
    RISING — demographically backwards, and the pathology the design panel's own winner listed
    as its risk. The pinned one-sided three-point rule refuses it."""
    for shape, curve in _curves(_fresh_headship()).items():
        assert curve[85] < curve[72], shape
        assert curve[100] < curve[75], shape
        assert curve[100] < curve[90], f"{shape}: the terminal rule reverted to a plain secant"


def test_the_osculatory_overshoot_at_74_75_EXISTS_and_is_PINNED_rather_than_clamped():
    """THE ONE MEASURED CURVE DEFECT, pinned so it cannot be silently removed.

    Closure telescopes independently of the tangent rule — that is the winning chassis's whole
    point — so a future rule that flattened the ten-year member, or an unanchored hull clamp
    bolted on after construction, would leave every OTHER gate in this file green. This is the
    only assertion that sees it. It is deliberately a pin on a DEFECT: the overshoot is what
    the alternative costs, and the design measured that a hull clamp buys its removal with
    `h(15) = -0.0061`, a NEGATIVE rate.

    STRUCTURE, NOT BIT-EXACT FLOATS, and per carried arm rather than the central one alone:
    the excess is asserted strictly positive and the peak inside the ten-year member, because
    those are the properties a clamp or a flattening rule destroys; the magnitudes are
    recomputed by the generator on every vintage and pinning them would gate the run on a
    figure a legitimate re-extract moves.
    """
    persons = _independent_persons_by_age()
    members = _independent_member_maintainers()
    hull = max(members[label] / sum(persons[a] for a in range(lo, hi + 1))
               for label, lo, hi in _SPEC_HEADSHIP_MEMBERS)
    payload = _fresh_headship()
    prov = payload["_provenance"]
    overshoot = prov["osculatory_overshoot"]
    assert set(overshoot) == set(census.HEADSHIP_SHAPES)
    for shape, curve in _curves(payload).items():
        inside = max(curve[a] for a in range(75, 85))
        assert inside > hull, (
            f"{shape}: the 74/75 osculatory overshoot is GONE — the ten-year member peaks at "
            f"{inside} against the member-rate hull {hull}. Either a hull clamp was added "
            "(measured to produce a negative rate at 15) or the tangent rule flattened the "
            "wide member; both are refused, and the defect is recorded rather than papered "
            "over (see `shape_note`)")
        record = overshoot[shape]
        assert 75 <= record["peak_age"] <= 84, f"{shape}: peak left the ten-year member"
        assert record["peak_rate"] == curve[record["peak_age"]], shape
        assert record["excess_over_hull_pct"] > 0.0, shape
        assert record["hull_max"] == max(prov["member_rates"].values()), shape
        assert record["hull_max"] == pytest.approx(hull, rel=1e-12), shape
    note = prov["shape_note"]
    assert "osculatory overshoot" in note and "74/75" in note


def test_base_year_owner_stock_is_the_published_owner_count_for_maintainers_25_plus():
    """THE CHEAPEST SIMULTANEOUS VALIDATION OF CLOSURE, and it is an identity rather than a
    tolerance. The ownership lattice's bands are themselves exact unions of published members,
    so Σ_a P(a)·h(a)·own(a) collapses to Σ_bands owner_b — the published Owner column, netted
    of the two members the lattice drops. It is therefore SHAPE-INVARIANT among member-closed
    curves and is the number the committed six-band curve misses by 2.207%."""
    persons = _independent_persons_by_age()
    counts = _independent_band_counts()[_PROVINCE]
    own = {(lo, min(hi, 100)): counts[band][0] / counts[band][1]
           for band, lo, hi, _members in census._AGE_BAND_SPEC}
    members = _independent_member_counts()
    assert members["15 to 19 years"][0] == _QC_OWNERS_15_19
    assert members["20 to 24 years"][0] == _QC_OWNERS_20_24
    target = _QC_OWNERS_ALL_AGES - _QC_OWNERS_15_19 - _QC_OWNERS_20_24
    assert target == 2227280
    for shape, curve in _curves(_fresh_headship()).items():
        stock = 0.0
        for age, p in persons.items():
            rate = next((r for (lo, hi), r in own.items() if lo <= age <= hi), 0.0)
            stock += p * curve[age] * rate
        assert stock == pytest.approx(target, abs=1e-6), shape


def test_both_arms_pass_the_IDENTICAL_gate_set_and_neither_is_a_step_curve():
    """The sweep endpoint is not a second-class citizen: `expo_cum_fb` clears every gate the
    central arm clears, and NEITHER is piecewise-constant at member scale — the 14-member step
    curve satisfies per-member closure exactly and is the WORST design measured, so closure
    alone does not discriminate. The discriminator is that the rate MOVES inside every member."""
    curves = _curves(_fresh_headship())
    assert set(curves) == set(census.HEADSHIP_SHAPES)
    for shape, curve in curves.items():
        for _label, lo, hi in _SPEC_HEADSHIP_MEMBERS:
            inside = {curve[a] for a in range(lo, hi + 1)}
            assert len(inside) == hi - lo + 1, f"{shape}[{lo}-{hi}] is flat — a step curve"
    assert curves["expo_cum_fc"] != curves["expo_cum_fb"]


def test_the_shape_note_declares_the_assumption_and_carries_its_OWN_measured_refutation():
    """Falsifier F6's honesty clause, written INTO the artifact so it rides the artifact digest.

    Per-member closure pins ONE linear functional per member and leaves 4, 9 or 15 degrees of
    freedom: the level is published, the shape is ASSUMED. The anchor for the abscissa choice
    must be COMPUTED BY THE GENERATOR on this vintage — the design panel's judge could not
    reproduce one of the figures the proposal quoted for it, so a transcribed anchor here would
    be a citation this repo cannot re-derive."""
    prov = _fresh_headship()["_provenance"]
    note = prov["shape_note"]
    assert "assumed" in note.lower() and "degrees of freedom" in note
    assert "2.059" not in note, "the shape_note transcribed an unreproducible figure"
    ref = prov["abscissa_refutation"]
    assert set(ref) == set(census.HEADSHIP_SHAPES)
    assert ref["expo_cum_fb"]["max_rate"] > 1.0, (
        "the age-abscissa variant did not reproduce its out-of-range failure — the refutation "
        "that anchors the exposure abscissa is no longer measured")
    for shape in census.HEADSHIP_SHAPES:
        assert ref[shape]["rate_step_at_56"] < 0.0
        assert ref[shape]["persons_ratio_56_over_55"] > 1.0


def test_the_zero_support_note_keeps_THREE_claims_distinct():
    """Falsifier F11. The clause that ORDERED this work is DISCHARGED, not deleted — and the
    other two claims it carried are different claims about different lines and both survive."""
    note = _fresh_headship()["_provenance"]["zero_support_note"]
    # (i) under-15: a positive bound, never an absence claim and never a proof of zero
    assert "only admissible value" in note
    assert "the table is silent" not in note and "proved exactly zero" not in note
    assert "1,364,340" in note and "2.6e-05" in note.replace("2.6E-05", "2.6e-05")
    # (ii) the age-resolved warning, explicitly retired
    assert "DISCHARGED" in note and "age-resolved" in note
    # (iii) the sub-25 ownership clause, still standing, with its computed figures
    assert "17,170 owners of 106,605 households" in note
    assert "amendment #12" in note and "re-measure" in note.lower()


def test_the_DISCHARGED_clause_names_the_retired_SENTENCE_and_the_COMMIT_that_retired_it():
    """Falsifier F11's second half, on BOTH surfaces: a discharge that does not say what
    discharged it is indistinguishable from a deletion to the next reader.

    Three things are pinned, because the clause makes three separable claims: the retired
    sentence is QUOTED (so a reader can tell which sentence went), the commit that retires it
    is NAMED, and what now SATISFIES it is stated in the terms that satisfy it — per-single-year
    rates under per-member closure, so a consumer multiplying ONE age is no longer reusing a
    band rate. The commit id could not be written by the commit that made it; this gate is the
    reason the follow-up run wrote it instead of leaving "the commit that lands this curve",
    which is not a reference a reader can resolve.
    """
    for surface, provenance in (("committed", _committed_headship()["_provenance"]),
                                ("fresh", _fresh_headship()["_provenance"])):
        note = provenance["zero_support_note"]
        assert "DISCHARGED" in note, f"{surface}: the discharge marker is gone: {note!r}"
        assert "must land an age-resolved curve rather than reuse this one" in note, (
            f"{surface}: the discharge no longer quotes the sentence it retires, so the reader "
            f"cannot tell WHICH claim was retired: {note!r}")
        assert "c83595e" in note, (
            f"{surface}: the discharge does not name the commit that retired the clause: "
            f"{note!r}")
        assert "no longer reusing a band rate" in note, (
            f"{surface}: the discharge states the retirement without stating what SATISFIES "
            f"the retired requirement: {note!r}")


def _assert_lattice_floor_unmoved(spec_floor: int, mirrored_floor: int) -> None:
    """The tripwire's ONE assertion, factored out so it can be EXERCISED rather than described.

    A tripwire nobody has ever seen fire is an untested tripwire, and this one exists precisely
    because the failure it guards against is a FUTURE edit. Keeping the assertion in a callable
    lets the gate below fire it on a moved floor without anyone editing this file.
    """
    assert spec_floor == mirrored_floor == 25, (
        "the ownership lattice floor MOVED. Spec §7 amendment #12 orders this SECOND, and its "
        "first half (the age-resolved headship curve) landed at c83595e. Before the floor moves, "
        "amendment #12's quantified floor-effect legs — every one of them measured on the "
        "RETIRED six-band curve — must be RE-MEASURED against the age-resolved curve: they are "
        "the warrant for an irreversible ordering decision and a stale measurement cannot serve "
        "as one. Do NOT update this pin without the re-measured figures landing in the same "
        "diff: `demand/formation.py`'s OWNERSHIP_LATTICE_FLOOR block still carries the "
        "pre-ruling-V figures, and `census._zero_support_note` carries the obligation to "
        "re-measure them. This assertion is the only guard that reds on ANY move of the floor, "
        "and the only one whose message names the re-measurement: the derive-time RAISE — the "
        "one that fires when `_ownership_spec_omitted_members` comes back empty — needs a FULL "
        "extension, and it orders a clause rewrite rather than this measurement.")


def test_the_ownership_LATTICE_FLOOR_IS_A_TRIPWIRE_that_reds_when_the_floor_moves():
    """THE re-measurement trigger — the instrument that replaces "a human notices the milestone".

    Run 15 recorded the sub-25 question as reopening "when Task 29 lands an age-resolved headship
    curve". Task 29 landed WITHOUT one, nothing reopened, and the defect survived three review
    rounds until a pre-PR gate caught it. The lesson binds here because the SECOND half of spec
    §7 amendment #12's ordering constraint carries the same shape of obligation: the floor may
    move only after the floor-effect legs are re-measured against the curve that landed at
    c83595e, and no runtime check can express "was this measured".

    So the floor is PINNED, and the pin's failure message carries the obligation. It is a
    tripwire, not a proof: whoever moves the floor must edit this test, and the edit IS the
    point — it puts the obligation in a PR-visible diff instead of in a reader's memory. What it
    cannot do is verify the re-measurement happened, and `census._zero_support_note` says exactly
    that rather than implying the suite checks it.

    It is deliberately NOT the same assertion as the `OWNERSHIP_LATTICE_FLOOR ==
    min(census._AGE_BANDS)` pins in `test_owner_stock.py` / `test_demand.py`: those two catch the
    two literals PARTING, and stay green on a downward extension that moves both together —
    which is the very edit that must not pass quietly.
    """
    # Imported HERE rather than at module scope: this is the loaders' test module, and the
    # mirrored literal belongs to the demand package — the coupling belongs to the assertion,
    # not to this file's import surface.
    from demoflow.demand.formation import OWNERSHIP_LATTICE_FLOOR

    _assert_lattice_floor_unmoved(min(lo for _label, lo, _hi in census._AGE_BANDS),
                                  OWNERSHIP_LATTICE_FLOOR)


def test_the_sub_25_reopening_trigger_FIRES_MECHANICALLY_and_names_what_it_cannot_check():
    """RUN-15's LESSON, encoded as a gate. Run 15's record wrote "it reopens when Task 29 lands
    an age-resolved headship curve". Task 29 landed WITHOUT one, nothing reopened, and the
    defect survived three review rounds until the pre-PR gate caught it: A CONDITION WHOSE
    TRIGGER NOBODY CHECKS IS NOT A CONDITION.

    So prose alone is not enough here. This gate pins that the note names BOTH mechanical
    triggers by identifier, EXERCISES each one to prove it fires, and pins that the note states
    the one thing neither trigger can observe. The last assertion is the load-bearing one: a
    trigger that fires on the EXTENSION cannot verify the RE-MEASUREMENT that must precede it,
    and a note implying otherwise reads as a guarantee it cannot make.
    """
    # Imported HERE rather than at module scope: this is the loaders' test module, and the pin
    # under test is the demand package's mirror of the loaders' spec — the coupling belongs to
    # the assertion, not to this file's import surface.
    from demoflow.demand.formation import OWNERSHIP_LATTICE_FLOOR

    note = _fresh_headship()["_provenance"]["zero_support_note"]

    # 1. TRIGGER (a) IS CITED BY THE NAME OF A TEST THAT EXISTS — asserted through the function
    #    OBJECT, so renaming or deleting the tripwire reds this gate instead of leaving the note
    #    pointing at a test nobody has.
    tripwire = test_the_ownership_LATTICE_FLOOR_IS_A_TRIPWIRE_that_reds_when_the_floor_moves
    assert tripwire.__name__ in note, (
        f"the note does not cite the tripwire that actually reds on a floor move: {note!r}")
    assert "OWNERSHIP_LATTICE_FLOOR" in note and "_ownership_spec_omitted_members" in note, (
        f"the note describes a reopening trigger without naming either guard: {note!r}")
    for cited in ("tests/test_owner_stock.py", "tests/test_demand.py"):
        assert cited in note, f"the note does not cite the twin pin's home {cited}: {note!r}"
    here = Path(__file__).parent
    for cited in ("test_owner_stock.py", "test_demand.py"):
        assert "min(lo for _label, lo, _hi in census._AGE_BANDS)" in (
            here / cited).read_text(encoding="utf-8"), (
            f"{cited} no longer carries the twin pin the note cites — a guard the note "
            "advertises has left the file it points at")

    # 2. TRIGGER (a), EXERCISED — the tripwire reds on ANY move of the floor, made consistently
    #    or not, which is what an "OWNERSHIP_LATTICE_FLOOR == min(_AGE_BANDS)" pin alone does NOT
    #    do: a downward extension that moves BOTH sides keeps that identity true. Both readings
    #    are asserted here so the note's split between the tripwire and the twin pins is the
    #    measured one.
    assert OWNERSHIP_LATTICE_FLOOR == min(lo for _label, lo, _hi in census._AGE_BANDS)
    extended = census._AGE_BAND_SPEC + (("20-24", 20, 24, ("20 to 24 years",)),)
    moved_floor = min(lo for _label, lo, _hi, _members in extended)
    assert moved_floor != OWNERSHIP_LATTICE_FLOOR, (
        "a band below the floor no longer moves min(_AGE_BANDS) — the twin pins are dead")
    with pytest.raises(AssertionError, match="ownership lattice floor MOVED"):
        _assert_lattice_floor_unmoved(moved_floor, moved_floor)

    # 3. TRIGGER (b), EXERCISED — the narrower one: it fires only on a move that REACHES the
    #    youngest published member, at derive time, before an empty clause can ship. The full
    #    end-to-end path is
    #    `test_the_sub_25_clause_RETIRES_ITSELF_loudly_when_the_ownership_lattice_is_extended`.
    with pytest.raises(LoaderError, match="retired itself"):
        census._zero_support_note(1_364_340.0, ("15 to 19 years", 10_920), (),
                                  members=14, tolerance=37.5, delta=5)

    # 4. THE HONEST HALF, and the whole reason this gate exists rather than a green checkmark:
    #    every guard above fires on the EXTENSION, none observes whether amendment #12's legs
    #    were re-measured first — the tripwire can be satisfied by editing the tripwire. The
    #    note must say so in its own words rather than reading as a guarantee.
    assert "NEITHER GUARD CHECKS" in note, (
        f"the note advertises mechanical triggers without stating their limit: {note!r}")
    assert "UNENFORCED by construction" in note, (
        f"the note does not admit that the re-measurement obligation is unenforced: {note!r}")


def _tripwire_message() -> str:
    """The tripwire's failure message, obtained by FIRING it rather than transcribed.

    Whitespace-normalized because the message is assembled from wrapped string literals, so a
    phrase-level assertion on the raw text would depend on where the source happens to break."""
    with pytest.raises(AssertionError) as tripped:
        _assert_lattice_floor_unmoved(20, 20)
    return " ".join(str(tripped.value).split())


def _formation_comment_text() -> str:
    """`demand/formation.py`'s prose, with the COMMENT MARKERS REMOVED before normalization.

    The `#` strip is load-bearing, not cosmetic: that block wraps mid-phrase, so plain
    whitespace normalization leaves the marker INSIDE phrases ("only mechanical # trigger") and
    every phrase-level assertion against this surface then passes or fails for the wrong reason.
    The same wrap is why a one-line `grep` for such a phrase reports the surface as clean."""
    from demoflow.demand import formation

    return " ".join(Path(formation.__file__).read_text(encoding="utf-8").replace("#", " ").split())


def test_the_tripwire_MESSAGE_routes_each_surface_to_WHAT_IT_ACTUALLY_CARRIES():
    """The tripwire message sends a future floor-mover to TWO surfaces for the re-measurement,
    and this gate reads both surfaces to pin that each carries what the message says it carries.

    That message is where the obligation is written down, so misrouting it costs what a lying
    note costs: a reader sent to `_zero_support_note` for pre-ruling-V figures finds none — the
    figures are `demand/formation.py`'s, and what the note carries is the OBLIGATION to
    re-measure them. The assertions are split by surface for that reason, and the NEGATIVE half
    is the load-bearing one: if a later edit moves a floor-effect figure into the note, this reds
    instead of letting the message become quietly right about the wrong surface.
    """
    message = _tripwire_message()
    note = _fresh_headship()["_provenance"]["zero_support_note"]
    formation_prose = _formation_comment_text()

    # Amendment #12's quantified floor-effect legs — the figures the re-measurement is FOR, every
    # one of them measured on the retired six-band curve and none of them re-stated since.
    for leg in ("0.195-0.337%", "0.96-1.65%", "30x-200x", "19-21%/yr", "1.42%"):
        assert leg in formation_prose, (
            f"the message routes the pre-ruling-V figures to `demand/formation.py`'s "
            f"OWNERSHIP_LATTICE_FLOOR block, but the leg {leg!r} is not there — either the "
            "figures moved or they were restated, and the routing is stale either way")
        assert leg not in note, (
            f"`census._zero_support_note` now carries the floor-effect figure {leg!r}. The "
            "tripwire message routes FIGURES to formation.py and only the OBLIGATION to this "
            "note; a figure landing here has to be reflected in that message or it misroutes")
    assert "MUST BE RE-MEASURED" in note, (
        f"the note no longer carries the obligation the tripwire message routes the reader here "
        f"for: {note!r}")
    assert "still carries the pre-ruling-V figures" in message, (
        f"the message no longer names formation.py as the FIGURE carrier: {message!r}")
    assert "carries the obligation" in message, (
        f"the message no longer distinguishes the obligation carrier from the figure carrier, "
        f"which is the distinction that makes it a usable instruction: {message!r}")


def test_the_SOLE_TRIGGER_claim_is_SCOPED_on_every_surface_that_makes_it():
    """THREE surfaces state how many guards fire when the floor moves, and a count they disagree
    on is a count the next reader cannot use. `census._zero_support_note` counts TWO GUARDS (the
    floor tripwire, and the derive-time RAISE which the gate above actually FIRES), so a bare
    "the only mechanical trigger" on either other surface is a claim this suite refutes.

    It is SCOPED rather than deleted, because the narrow reading is true and is the operative
    one: the tripwire is the only guard that reds on ANY move of the floor — the RAISE needs a
    FULL extension — and the only one whose message names the re-measurement, since the RAISE
    orders a clause rewrite instead. Both surfaces must carry the qualifier that makes it true.
    """
    note = _fresh_headship()["_provenance"]["zero_support_note"]
    assert "TWO GUARDS" in note, (
        f"the note no longer states the guard count, so the other two surfaces have nothing to "
        f"agree with: {note!r}")
    for surface, text in (("the tripwire's failure message", _tripwire_message()),
                          ("demand/formation.py", _formation_comment_text())):
        assert "only mechanical trigger" not in text, (
            f"{surface} calls the tripwire the obligation's ONLY mechanical trigger, while the "
            "note counts TWO GUARDS and the gate above fires the second one on a full extension. "
            "Scope the claim to what holds instead of dropping it")
        assert "only guard that reds on ANY move" in text, (
            f"{surface} no longer scopes its sole-trigger claim to what this suite measures: the "
            "tripwire reds on ANY move of the floor, the derive-time RAISE only at FULL extension")


def test_the_generator_is_still_the_only_writer_and_the_artifact_is_byte_reproducible():
    """Falsifier F13, and it is what makes every figure above a DERIVATION rather than a
    transcription: member order and age order come from the spec, never from set iteration."""
    first = json.dumps(_fresh_headship(), indent=2, ensure_ascii=False)
    second = json.dumps(_fresh_headship(), indent=2, ensure_ascii=False)
    assert first == second


def test_headship_rate_reads_a_single_age_and_a_hole_RAISES(tmp_path):
    """Falsifier F15. `headship_rate` is now a direct per-age read — the band lookup is gone —
    and an absent age must still RAISE (never a bare KeyError, never a silent zero): a holed
    curve shrinks the ED DENOMINATOR and scales |ED| AWAY FROM ZERO."""
    curve = load_headship_rates()
    assert set(curve) == set(range(0, 101))
    assert headship_rate(curve, 30) == curve[30]
    with pytest.raises(LoaderError, match="age 30"):
        headship_rate({a: v for a, v in curve.items() if a != 30}, 30)

    payload = _committed_headship()
    del payload["headship"]["expo_cum_fb"]["57"]
    (tmp_path / HEADSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="57"):
        load_headship_rates(data_dir=tmp_path)


def test_a_non_integer_or_out_of_range_age_key_is_refused_at_load(tmp_path):
    """The JSON-string / in-memory-int asymmetry, closed at the boundary: `"07"` and `"3.0"`
    would both cast into an age that already exists and collide silently."""
    for bad in ("07", "3.0", "101"):
        payload = _committed_headship()
        payload["headship"][census.HEADSHIP_CENTRAL_SHAPE][bad] = 0.5
        out = tmp_path / bad.replace(".", "_")
        out.mkdir()
        (out / HEADSHIP_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError):
            load_headship_rates(data_dir=out)


def test_load_headship_rates_selects_the_shape_and_refuses_an_unknown_one():
    """The sweep's read path. The default is the artifact's own `central_shape`; the pipeline
    NEVER relies on that default — it passes the shape explicitly, so the selection lives in
    one place that `assumptions_hash` covers."""
    central = load_headship_rates()
    assert central == load_headship_rates(shape=census.HEADSHIP_CENTRAL_SHAPE)
    other = load_headship_rates(shape="expo_cum_fb")
    assert other != central
    with pytest.raises(LoaderError, match="shape"):
        load_headship_rates(shape="expo_cum_nope")
