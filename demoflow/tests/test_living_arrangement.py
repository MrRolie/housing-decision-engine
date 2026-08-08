"""Task 15b contract gates — per-sex living-arrangement rates (spec §5, §11.3; ruling A).

The plan's three bodies are carried verbatim IN INTENT; two of them are rebuilt on a
different fixture mechanism, for a reason the plan could not have known. The plan wrote
`load_living_arrangement(data_dir=tmp_path)` over a hand-typed `{"_default": ...}` payload —
but the generated-artifact discipline (steering rulings B + L, carried into this task) makes
`load_*` STRICT: it verifies the artifact's recorded source digest and joins every
`Geography` member before returning. A hand-typed `_default`-only payload now dies at LOAD,
so `pytest.raises(..., match="couple_share")` would never reach `couple_share` and the gate
would pass for the wrong reason. Same collision `test_out_of_unit_ownership_rate_raises`
already resolved in test_census_ownership.py, and the same resolution: the fixture is the
REAL committed artifact with ONE cell mutated, so the only reachable failure is the one
under test. The three CONTRACT BEHAVIOURS are unchanged:

  1. per-sex `living_alone` and `couple_share` resolve for both sexes and are fractions;
  2. a cell missing `couple_share` RAISES LoaderError naming `couple_share` (§11.3 —
     no invented default);
  3. an out-of-unit fraction RAISES LoaderError.
"""
import copy
import hashlib
import importlib.util
import json
import sys

import pytest

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census, living_arrangement, pins
from demoflow.loaders.living_arrangement import (
    ARTIFACT,
    EXTRACT,
    couple_share,
    derive_living_arrangement,
    living_alone_rate,
    load_living_arrangement,
)
from demoflow.loaders.pins import DATA_DIR


def _committed_artifact() -> dict:
    return json.loads((DATA_DIR / ARTIFACT).read_text(encoding="utf-8"))


def _committed_extract() -> dict:
    return json.loads((DATA_DIR / EXTRACT).read_text(encoding="utf-8"))


def _mutated(tmp_path, mutate) -> dict:
    """Write the committed artifact with one mutation applied, and load it back."""
    payload = copy.deepcopy(_committed_artifact())
    mutate(payload)
    (tmp_path / ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return load_living_arrangement(data_dir=tmp_path)


def _derive_mutated_extract(tmp_path, monkeypatch, mutate):
    """Derive from the committed extract with one mutation applied.

    The copy is RE-PINNED (test_census_ownership.py's `test_header_position_drift_raises`
    pattern) — otherwise the sha256 gate fires first and the gate under test is never
    reached, which would make the mutation prove nothing.
    """
    payload = copy.deepcopy(_committed_extract())
    mutate(payload)
    path = tmp_path / EXTRACT
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(pins.WORKBOOK_SHA256, EXTRACT,
                        hashlib.sha256(path.read_bytes()).hexdigest())
    return derive_living_arrangement(path)


def _cell_of(payload: dict, geography: str, gender: str, age_group: str, arrangement: str) -> dict:
    for cell in payload["cells"]:
        if (cell["geography"], cell["gender"], cell["age_group"], cell["arrangement"]) == (
                geography, gender, age_group, arrangement):
            return cell
    raise AssertionError(f"no cell {(geography, gender, age_group, arrangement)} in the extract")


# --- the plan's three ---------------------------------------------------------------

def test_per_sex_rates_present_and_fractions():
    la = load_living_arrangement()
    for sex in ("M", "F"):
        lar = living_alone_rate(la, Geography.MTL_RMR, age=80, sex=sex)
        cs = couple_share(la, Geography.MTL_RMR, age=80, sex=sex)
        assert 0.0 <= lar <= 1.0 and 0.0 <= cs <= 1.0


def test_missing_couple_share_raises_no_invented_default(tmp_path):
    # A cell with living_alone but NO couple_share must RAISE (spec §11.3): couple_share has
    # no invented default. The cell is emptied of exactly that key and nothing else, so a
    # green here cannot come from a malformed payload dying earlier.
    la = _mutated(tmp_path, lambda p: p["rates"]["MTL_RMR"]["75-84"]["M"].pop("couple_share"))
    with pytest.raises(LoaderError, match="couple_share"):
        couple_share(la, Geography.MTL_RMR, age=80, sex="M")


def test_out_of_unit_fraction_raises(tmp_path):
    la = _mutated(tmp_path,
                  lambda p: p["rates"]["MTL_RMR"]["75-84"]["M"].update(living_alone=1.4))
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        living_alone_rate(la, Geography.MTL_RMR, age=80, sex="M")


# --- added gates ----------------------------------------------------------------------

# --- TEST-OWNED oracle inputs ---------------------------------------------------------
# NOTHING below is imported from living_arrangement.py, and that is the whole point: an
# "independent" recompute that borrowed the producer's geography map, member names or band
# labels would move WITH a mutation to them and entail nothing. Every literal here is
# transcribed from probe P3 (probes/P3-living-arrangement.md) and the spec, not from the
# module under test.
_P_TOTAL = "Total - Census family status and household living arrangements"
_P_ALONE = "Persons living alone"
_P_COUPLED = "Married spouses and common-law partners"
_P_PROVINCE = "Quebec"
_P_CMAS = ("Drummondville (CMA), Que.", "Montréal (CMA), Que.", "Québec (CMA), Que.",
           "Saguenay (CMA), Que.", "Sherbrooke (CMA), Que.", "Trois-Rivières (CMA), Que.")
_P_BANDS = {"75-84": "75 to 84 years", "85+": "85 years and over"}
_P_SEX = {"M": "Men+", "F": "Women+"}
_P_BORROWERS = ("MTL_ISLAND_RA06", "LAVAL_RA13", "LANAUDIERE_RA14_PROXY",
                "LAURENTIDES_RA15_PROXY", "MONTEREGIE_RA16_PROXY")

# P3 §4 / DECISION-COUPLE-SHARE-CITATION, 4 dp as the committed note publishes them. These
# ARE the "exactly as cited" values steering ruling A protects.
_P3_CITED = {
    ("MTL_RMR", "75-84", "M"): (0.2150, 0.9077),
    ("MTL_RMR", "75-84", "F"): (0.4344, 0.7295),
    ("MTL_RMR", "85+", "M"): (0.2797, 0.8441),
    ("MTL_RMR", "85+", "F"): (0.5549, 0.4012),
    ("QC_RMR", "75-84", "M"): (0.2289, 0.9396),
    ("QC_RMR", "75-84", "F"): (0.4662, 0.8416),
    ("QC_RMR", "85+", "M"): (0.3216, 0.8875),
    ("QC_RMR", "85+", "F"): (0.6286, 0.5222),
}


def _extract_cube() -> dict:
    """{(geo, gender, age member, arrangement): count} — a TEST-OWNED parse of the extract."""
    return {(c["geography"], c["gender"], c["age_group"], c["arrangement"]): c["value"]
            for c in _committed_extract()["cells"]}


def _expected_rate_table() -> dict:
    """Recompute all 8 geographies x 2 bands x 2 sexes straight from the extract."""
    cube = _extract_cube()

    def rates(source: str, gender: str, member: str) -> dict:
        def net(arrangement: str) -> int:
            if source != "HORS_RMR":
                return cube[(source, gender, member, arrangement)]
            return (cube[(_P_PROVINCE, gender, member, arrangement)]
                    - sum(cube[(c, gender, member, arrangement)] for c in _P_CMAS))
        pop, alone, coupled = net(_P_TOTAL), net(_P_ALONE), net(_P_COUPLED)
        return {"living_alone": alone / pop, "couple_share": coupled / (pop - alone)}

    table = {
        geo: {label: {sex: rates(source, _P_SEX[sex], member) for sex in _P_SEX}
              for label, member in _P_BANDS.items()}
        for geo, source in (("MTL_RMR", "Montréal (CMA), Que."),
                            ("QC_RMR", "Québec (CMA), Que."),
                            ("HORS_RMR", "HORS_RMR"))
    }
    for borrower in _P_BORROWERS:
        table[borrower] = dict(copy.deepcopy(table["MTL_RMR"]), _flag="borrowed_prior")
    return table


def test_committed_artifact_equals_generator_output():
    """No-drift gate (steering ruling B): the committed JSON must equal a fresh derivation.

    FULL-DICT equality, not `["rates"]` only — `_provenance` carries the extract's sha256, the
    vintage, the caveats and the couple-balance diagnostic, and comparing only `rates` would
    leave that whole subtree free to go stale. This is the CONTENT leg; the load path
    independently checks IDENTITY on every load (steering ruling L). Neither subsumes the other.
    """
    assert _committed_artifact() == derive_living_arrangement(DATA_DIR / EXTRACT)


def test_full_rate_table_matches_an_independent_recompute():
    """ENTAILMENT over the WHOLE table, on BOTH surfaces.

    Pins the committed artifact AND a fresh derivation: asserting only the artifact leaves the
    PRODUCER uncovered the moment the artifact is regenerated under a producer mutation (the
    lesson test_census_ownership.py records for the ownership table).
    """
    expected = _expected_rate_table()
    fresh = derive_living_arrangement(DATA_DIR / EXTRACT)["rates"]
    for surface, table in (("committed", _committed_artifact()["rates"]), ("fresh", fresh)):
        assert set(table) == {g.value for g in Geography}, f"{surface}: geography set drifted"
        assert set(table) == set(expected), f"{surface}: geography set drifted"
        for geo, bands in expected.items():
            assert set(table[geo]) == set(bands), f"{surface}[{geo}]: band set drifted"
            for label, cells in bands.items():
                if label == "_flag":
                    assert table[geo][label] == cells, f"{surface}[{geo}] lost its flag"
                    continue
                assert set(table[geo][label]) == set(cells), f"{surface}[{geo}][{label}]: sexes"
                for sex, rates in cells.items():
                    assert set(table[geo][label][sex]) == set(rates)
                    for name, value in rates.items():
                        assert table[geo][label][sex][name] == pytest.approx(value, rel=1e-12), (
                            f"{surface}[{geo}][{label}][{sex}][{name}]")


def test_rates_are_exactly_the_cited_census_values():
    """STEERING RULING A: couple_share (and living_alone) stay EXACTLY as cited.

    The retired 0.25 same-age balance gate was satisfiable from either side within [0,1], so
    a "calibrated" table would still have been all-fractions, still regenerated cleanly, and
    still passed the recompute gate above (which recomputes from the same extract). Only a
    comparison against the EXTERNALLY published figures — P3's committed note, transcribed
    here, never imported — can tell a cited rate from a nudged one.
    """
    la = load_living_arrangement()
    for (geo, label, sex), (cited_alone, cited_couple) in _P3_CITED.items():
        age = 80 if label == "75-84" else 90
        got = (living_alone_rate(la, Geography(geo), age=age, sex=sex),
               couple_share(la, Geography(geo), age=age, sex=sex))
        assert (round(got[0], 4), round(got[1], 4)) == (cited_alone, cited_couple), (
            f"{geo} {label} {sex}: {got} is not the cited {(cited_alone, cited_couple)}")


def test_hors_rmr_is_province_net_of_all_six_cmas():
    """The residual nets ALL SIX wholly-Québec CMAs, not merely MTL+QC (codex r4-F2).

    Two arms, and their strengths are DELIBERATELY UNEQUAL — stated, because a gate whose
    power is overclaimed is worse than one whose power is small:

      STRONG arm — every served HORS_RMR rate equals the six-CMA residual recomputed here
      from the extract with a test-owned CMA list, to 1e-12. A producer that netted a
      different set fails this outright.

      WEAK arm — the wrong-netting (MTL+QC-only) value is merely SEPARABLE. Measured
      2026-08-08 on the committed extract, the smallest separation across the eight
      (band × sex × rate) pairs is 0.001637 (75-84 Men+ living_alone: 0.24433 vs 0.24269);
      the largest is 0.0115. That is thin because the four small CMAs happen to carry
      living-arrangement rates close to the residual's — netting them or not barely moves
      the RATE even though it changes the TERRITORY materially. So this arm proves only that
      the strong arm is not vacuous; it is NOT the defense against a mis-netted residual.

    The load-bearing defense against r4-F2 is a CMA-set gate at THREE distinct sites, and they
    are not interchangeable — an earlier revision of this docstring collapsed them into one
    claim and overclaimed the middle one:

      APPEARS upstream (a CA promoted to a CMA) — caught at ACQUISITION by
      `assert_netted_cma_universe`, which reads the cube's full Geography member list before
      any data call (`test_acquisition_refuses_a_newly_promoted_wholly_quebec_cma`). It CANNOT
      be caught later: the puller requests only `SOURCE_GEOGRAPHIES`, so the newcomer never
      reaches the extract.

      VANISHES upstream (or is re-spelled) — caught at ACQUISITION too, by `_member_id`, which
      refuses to guess a member id, and by the same universe gate's ABSENT arm.

      HAND-EDITED or foreign extract — caught by `_read_cells`'s geography-set equality gate
      (`test_new_upstream_geography_raises_rather_than_going_un_netted`). That is the whole of
      what it defends: every extract the committed puller can write already carries exactly
      `set(SOURCE_GEOGRAPHIES)`.
    """
    cube = _extract_cube()
    la = load_living_arrangement()
    separations = []
    for label, member in _P_BANDS.items():
        for sex, gender in _P_SEX.items():
            def net(arrangement, cmas, member=member, gender=gender):
                return (cube[(_P_PROVINCE, gender, member, arrangement)]
                        - sum(cube[(c, gender, member, arrangement)] for c in cmas))
            age = 80 if label == "75-84" else 90
            got = (living_alone_rate(la, Geography.HORS_RMR, age=age, sex=sex),
                   couple_share(la, Geography.HORS_RMR, age=age, sex=sex))
            for cmas, arm in ((_P_CMAS, "six"),
                              (("Montréal (CMA), Que.", "Québec (CMA), Que."), "mtl+qc")):
                pop, alone, coupled = (net(_P_TOTAL, cmas), net(_P_ALONE, cmas),
                                       net(_P_COUPLED, cmas))
                candidate = (alone / pop, coupled / (pop - alone))
                if arm == "six":
                    assert got == pytest.approx(candidate, rel=1e-12), f"{label}/{sex}"
                else:
                    separations += [abs(got[i] - candidate[i]) for i in (0, 1)]
    # The floor is the MEASUREMENT, not a hope: 0.001637 is the observed minimum, and 1e-3 is
    # the largest round floor below it. A re-pull that shrinks the smallest separation under
    # this floor should red HERE and be read as "this arm lost its power", never as a
    # derivation bug — the strong arm above and the geography-set gate are what carry r4-F2.
    assert min(separations) > 1e-3, (
        f"MTL+QC-only netting is no longer separable from the six-CMA residual "
        f"(smallest gap {min(separations):.6f}); this arm no longer proves the strong arm "
        "is non-vacuous")
    assert min(separations) == pytest.approx(0.001637, abs=5e-6), (
        f"the recorded separation moved to {min(separations):.6f} — the docstring's measured "
        "figures are stale")


def test_netted_cma_set_denotes_the_same_territory_as_the_ownership_loader():
    """The HORS_RMR ownership rate and the HORS_RMR living-arrangement rate multiply the SAME
    population in the cohort initialization. If the two residuals netted different CMA sets
    they would denote different territories, and the product would mix them while every
    factor stayed a plausible fraction. The two modules keep their own tuples (the label
    spellings belong to two different upstream products and may drift independently); this
    asserts the DENOTATION equality that makes the join legitimate.
    """
    assert set(living_arrangement._QC_CMAS) == set(census._QC_CMAS)
    assert living_arrangement._PROVINCE == census._PROVINCE


def test_ra_members_borrow_mtl_and_are_flagged():
    """The CMA-level cube carries no RA rows, so five members borrow MTL_RMR. The borrow must
    be VISIBLE to a consumer (`_flag` inside `rates`, not prose in `_provenance`) and must be
    the parent's rates, not a lookalike."""
    rates = load_living_arrangement()
    for borrower in _P_BORROWERS:
        assert rates[borrower].get("_flag") == "borrowed_prior", f"{borrower} is unflagged"
        assert {k: v for k, v in rates[borrower].items() if k != "_flag"} == rates["MTL_RMR"]
    for direct in ("MTL_RMR", "QC_RMR", "HORS_RMR"):
        assert "_flag" not in rates[direct], f"{direct} is derived, not borrowed"


def test_every_enum_geography_carries_both_bands_for_both_sexes():
    """Spec §5 needs SEX-SPECIFIC rates for every modeled geography; the strict join is what
    makes a silently thinned artifact impossible."""
    la = load_living_arrangement()
    for geo in Geography:
        for age in (75, 80, 84, 85, 90, 105):
            for sex in ("M", "F"):
                assert 0.0 <= living_alone_rate(la, geo, age=age, sex=sex) <= 1.0
                assert 0.0 <= couple_share(la, geo, age=age, sex=sex) <= 1.0


def test_load_refuses_a_thinned_artifact(tmp_path):
    """A missing geography, band or sex must surface at the FILE, not downstream as a lookup
    miss on one cell (which reads as a bad age and sends the reader to the band lattice)."""
    for name, mutate, match in (
            ("geography", lambda p: p["rates"].pop("QC_RMR"), "QC_RMR"),
            ("band", lambda p: p["rates"]["MTL_RMR"].pop("85+"), "85"),
            ("sex", lambda p: p["rates"]["MTL_RMR"]["75-84"].pop("F"), "SEX-SPECIFIC")):
        payload = copy.deepcopy(_committed_artifact())
        mutate(payload)
        (tmp_path / ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(LoaderError, match=match):
            load_living_arrangement(data_dir=tmp_path)


def test_renamed_rates_key_is_a_file_level_fault_not_a_missing_geography(tmp_path):
    """A renamed or absent top-level `rates` key is a FILE fault and must read as one.

    `payload.get("rates", {})` degrades it into an empty table, which the strict join then
    reports as `no living-arrangement rates for MTL_RMR` — sending the reader to the geography
    map for a fault that is in the file's shape. census.py's `load_headship_rates` names this
    exact degradation and deliberately avoids it; the carry belongs here too. Fail-closed
    either way — this is about which surface the message points at.
    """
    payload = copy.deepcopy(_committed_artifact())
    payload["rate_table"] = payload.pop("rates")
    (tmp_path / ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LoaderError, match="no 'rates' key") as exc:
        load_living_arrangement(data_dir=tmp_path)
    assert "MTL_RMR" not in str(exc.value), (
        "a file-level fault reported as a missing geography")
    assert "rate_table" in str(exc.value), "the message does not show what the file carries"


def test_band_labels_partition_75_plus_and_do_not_collide_with_the_ownership_bands():
    """The plan labelled the 75-84 band `"75+"`. census.py ALSO publishes a `"75+"` band, and
    it really is 75-200 — two adjacent loaders whose identically-spelled band means different
    domains is a silent miscompose. The labels here agree with their own ranges, partition
    75..200 with no gap or overlap, and the collision is asserted absent.
    """
    spec = living_arrangement._AGE_BAND_SPEC
    assert tuple(label for label, _, _, _ in spec) == ("75-84", "85+")
    prev_hi = 74
    for label, lo, hi, member in spec:
        if label.endswith("+"):
            assert lo == int(label[:-1]) and hi >= 200, f"{label}: open band"
        else:
            lo_txt, hi_txt = label.split("-")
            assert (lo, hi) == (int(lo_txt), int(hi_txt)), f"{label}: range disagrees with label"
        assert lo == prev_hi + 1, f"{label}: gap or overlap below {lo}"
        assert str(lo) in member, f"{label}: cube member {member!r} is not this band"
        prev_hi = hi
    mine = {label for label, _, _, _ in spec}
    theirs = {label for label, _, _ in census._AGE_BANDS} | {
        label for label, _, _ in census._HEADSHIP_BANDS}
    assert mine & theirs == set(), (
        f"a band label is shared with census.py's lattices while denoting a DIFFERENT domain "
        f"(theirs: 75+ = 75..200): {mine & theirs}")
    assert "75+" in theirs and "75+" not in mine, (
        "the plan's `75+` label for the 75-84 band would collide with census.py's 75..200 band")

    la = load_living_arrangement()
    with pytest.raises(LoaderError, match="75\\+ only"):
        living_alone_rate(la, Geography.MTL_RMR, age=74, sex="M")
    with pytest.raises(LoaderError, match="75\\+ only"):
        couple_share(la, Geography.MTL_RMR, age=74, sex="M")


def test_vitrine_fallback_is_measured_unneeded_and_never_applied_silently(tmp_path):
    """Spec §11.3 gives living_alone a vitrine fallback (0.28); probe P3 measured it unneeded
    (DECISION-FOUND-AT-CMA: YES). This module therefore makes BOTH rates cited-or-raise.
    Two claims, both executable: no served rate equals the vitrine constant by accident of a
    fallback path, and a cell stripped of living_alone RAISES instead of quietly returning it.
    """
    vitrine = 0.28
    la = load_living_arrangement()
    for geo in Geography:
        for age in (80, 90):
            for sex in ("M", "F"):
                assert living_alone_rate(la, geo, age=age, sex=sex) != vitrine

    stripped = _mutated(tmp_path, lambda p: p["rates"]["MTL_RMR"]["75-84"]["M"].pop("living_alone"))
    with pytest.raises(LoaderError, match="living_alone missing"):
        living_alone_rate(stripped, Geography.MTL_RMR, age=80, sex="M")


# --- provenance / vintage identity ----------------------------------------------------

def test_registry_pins_the_living_arrangement_extract():
    """The PIT chain (live WDS response -> committed extract -> derived rates) is only pinned
    if the registry actually carries this extract's digest."""
    assert EXTRACT in pins.WORKBOOK_SHA256, f"{EXTRACT} is not pinned — the PIT chain is open"
    assert hashlib.sha256((DATA_DIR / EXTRACT).read_bytes()).hexdigest() == \
        pins.WORKBOOK_SHA256[EXTRACT]


def test_derivation_refuses_an_unpinned_extract(tmp_path):
    """A byte-drifted extract must never derive rates — vintage identity before arithmetic."""
    drifted = tmp_path / EXTRACT
    payload = _committed_extract()
    payload["cells"][0]["value"] += 5
    drifted.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LoaderError, match="sha256 drift"):
        derive_living_arrangement(drifted)


def test_stale_artifact_sha_is_refused_at_load(tmp_path):
    """STEERING RULING L — the load path itself refuses a stale artifact.

    The fixture carries the REAL, complete `rates` block, so the strict-join leg cannot fire:
    the only reachable failure is the provenance leg, and a green here would mean the gate is
    absent rather than that the fixture was malformed.
    """
    payload = copy.deepcopy(_committed_artifact())
    payload["_provenance"]["sha256"] = "0" * 64
    (tmp_path / ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LoaderError, match="sha256"):
        load_living_arrangement(data_dir=tmp_path)


def test_unprovenanced_artifact_is_refused_at_load(tmp_path):
    """RULING L, second leg: an ABSENT digest refuses too — and it is the more dangerous case,
    since a mismatch announces itself while a missing digest is indistinguishable from a
    hand-authored rate table (exactly what ruling B forbids). BOTH absent shapes are fed
    because they reach the guard through DIFFERENT operands.
    """
    for shape, strip in (("block absent", lambda p: p.pop("_provenance")),
                         ("digest stripped", lambda p: p["_provenance"].pop("sha256"))):
        payload = copy.deepcopy(_committed_artifact())
        strip(payload)
        (tmp_path / ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(LoaderError, match="_provenance") as exc:
            load_living_arrangement(data_dir=tmp_path)
        assert "sha256" in str(exc.value), f"{shape}: message does not name the digest"


# --- source-contract gates (mutations of the extract) ---------------------------------

def test_gender_transposition_is_refused_at_derivation(tmp_path, monkeypatch):
    """A transposed Men+/Women+ junction leaves every rate a plausible fraction and leaves the
    gender-additivity identity EXACTLY satisfied (the two counts merely swap sides), so nothing
    but the 75+ aggregate direction check can see it. At 75+ the male coupled count exceeds the
    female one in every published Québec geography, so the swap reverses that difference far
    beyond spec §5's 0.25 reversal bound.
    """
    def swap(payload):
        for cell in payload["cells"]:
            if cell["gender"] == "Men+":
                cell["gender"] = "Women+"
            elif cell["gender"] == "Women+":
                cell["gender"] = "Men+"
    with pytest.raises(LoaderError, match="direction reversed"):
        _derive_mutated_extract(tmp_path, monkeypatch, swap)


def test_gender_additivity_gate_catches_a_mis_resolved_member(tmp_path, monkeypatch):
    """The direction check cannot see a member resolved to the WRONG gender entirely (e.g.
    `Total - Gender` read as `Men+` after a cube re-index): the male/female direction survives
    and every rate stays a fraction. The additivity identity is what fires. The mutation is a
    realistic re-index — Men+ carrying the Total-Gender count — not an arbitrary number.
    """
    def reindex(payload):
        for age in ("75 to 84 years", "85 years and over"):
            for arrangement in (_P_TOTAL, _P_ALONE, _P_COUPLED):
                total = _cell_of(payload, "Montréal (CMA), Que.", "Total - Gender", age,
                                 arrangement)["value"]
                _cell_of(payload, "Montréal (CMA), Que.", "Men+", age, arrangement)["value"] = total
    with pytest.raises(LoaderError, match="gender junction broken"):
        _derive_mutated_extract(tmp_path, monkeypatch, reindex)


def test_base5_rounding_alone_never_reds_the_additivity_gate():
    """The tolerance must be wide enough for real Census rounding and narrow enough to catch a
    junction error. Measured on the committed extract, so the choice is a fact, not a hope."""
    cube = _extract_cube()
    worst = max(
        abs(cube[(g, "Total - Gender", a, m)]
            - cube[(g, "Men+", a, m)] - cube[(g, "Women+", a, m)])
        for g in (_P_PROVINCE, *_P_CMAS) for a in _P_BANDS.values()
        for m in (_P_TOTAL, _P_ALONE, _P_COUPLED))
    assert worst <= 5, f"worst gender-additivity deviation is {worst} persons"
    assert worst < living_arrangement._GENDER_ADDITIVITY_TOLERANCE


def test_new_upstream_geography_raises_rather_than_going_un_netted(tmp_path, monkeypatch):
    """The netted-CMA list is load-bearing: a CMA in the extract that the list does not carry
    stays INSIDE the residual, silently changing what HORS_RMR denotes while every rate stays
    in [0,1]. The geography-set equality gate must red instead.

    SCOPE, stated because this gate's reach was once overclaimed: what reaches it is a
    HAND-EDITED or foreign extract, which is exactly what this fixture is. It cannot see a CMA
    promoted UPSTREAM — the puller requests only `SOURCE_GEOGRAPHIES`, so such a member never
    lands in an extract at all; `assert_netted_cma_universe` catches that one at acquisition.
    """
    def add_cma(payload):
        extra = []
        for cell in payload["cells"]:
            if cell["geography"] == "Saguenay (CMA), Que.":
                clone = dict(cell, geography="Gatineau (CMA), Que.")
                extra.append(clone)
        payload["cells"].extend(extra)
    with pytest.raises(LoaderError, match="geography set"):
        _derive_mutated_extract(tmp_path, monkeypatch, add_cma)


# --- acquisition-path gate (the newly-promoted-CMA hole) ------------------------------
#
# `_read_cells`'s geography-set equality gate above defends a HAND-EDITED or foreign extract,
# and only that: the puller builds its request set from `SOURCE_GEOGRAPHIES`, refuses any
# coordinate it did not request and refuses any it never got back, so every extract the
# committed acquisition path can produce carries exactly `set(SOURCE_GEOGRAPHIES)` — the gate
# is structurally unable to fire on one. A wholly-Québec CMA PROMOTED upstream (a CA becoming
# a CMA at the next census, which is Drummondville's own 2021 history) is therefore never
# requested, never missed, and lands silently inside the HORS_RMR residual. The fact is
# observable exactly once, in the live cube metadata the puller already holds, so that is
# where it is checked.

_PULLER = "pull_living_arrangement.py"

# Transcribed from a LIVE `getCubeMetadata` read of cube 98100134 (166 Geography members,
# 2026-08-08) — the member SHAPES the gate must tell apart. Test-owned literals: importing the
# module's own tuple would make this move with the thing it is checking.
_LIVE_GEOGRAPHY_SHAPES = (
    "Canada", "Quebec", "Ontario",
    "Drummondville (CMA), Que.", "Montréal (CMA), Que.", "Québec (CMA), Que.",
    "Saguenay (CMA), Que.", "Sherbrooke (CMA), Que.", "Trois-Rivières (CMA), Que.",
    # CROSS-BORDER: parented to Ontario, no separable Québec-part row, so its Québec side is
    # inside the residual by design (`_CA_CAVEAT`). The gate must NOT claim it.
    "Ottawa - Gatineau (CMA), Ont./Que.",
    "Campbellton (CA), N.B./Que.",
    # Census agglomerations and out-of-province CMAs: inside the residual / irrelevant.
    "Granby (CA), Que.", "Rimouski (CA), Que.", "Toronto (CMA), Ont.",
)


class _ReachedAcquisition(Exception):
    """The puller got past the metadata gate and started asking for DATA."""


def _puller():
    """Import the COMMITTED acquisition script (it lives outside the package)."""
    path = DATA_DIR.parent / "scripts" / _PULLER
    spec = importlib.util.spec_from_file_location("_pull_living_arrangement_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_cube_metadata(extra_geography: str | None = None) -> dict:
    """The REAL cube's dimension shape, rebuilt from what the committed extract RECORDED.

    Not a hand-invented cube: the dimension names, positions and member ids are the ones the
    live pull wrote into `_pull`, so a puller that resolves members correctly against the real
    WDS resolves them here too. `extra_geography` is the only injected difference.
    """
    pull = _committed_extract()["_pull"]
    positions, ids = pull["dimension_positions"], pull["member_ids"]
    dimension = []
    for short, prefix in (("Geography", "Geography"), ("Gender", "Gender"),
                          ("Age group", "Age group"), ("Census year", "Census year"),
                          ("Arrangement", "Census family status"),
                          ("Household type", "Household type of person")):
        full = next(n for n in positions if n.lower().startswith(prefix.lower()))
        members = dict(ids[short])
        if short == "Geography" and extra_geography:
            members[extra_geography] = max(members.values()) + 1
        dimension.append({
            "dimensionNameEn": full, "dimensionPositionId": positions[full],
            "member": [{"memberNameEn": n, "memberId": i} for n, i in members.items()]})
    return {"productId": pull["product_id"], "cubeTitleEn": pull["cube_title"],
            "releaseTime": pull["release_time"], "dimension": dimension}


def _fake_post(meta: dict):
    """A WDS that answers metadata and refuses to be asked for data. Reaching the data
    endpoint is how the POSITIVE control proves the gate did not false-positive."""
    def post(url, payload):
        if url.endswith("getCubeMetadata"):
            return [{"object": meta}]
        raise _ReachedAcquisition(url)
    return post


def test_netted_cma_universe_gate_separates_a_promotion_from_the_residual_members():
    """The gate claims exactly the WHOLLY-Québec CMAs and nothing else.

    Both directions matter and they mean different things: an unexpected member is a promotion
    (both `_QC_CMAS` tuples must grow, or the residual silently shrinks); an expected member
    gone is a re-spelling (this tuple alone). A gate that also claimed Ottawa-Gatineau or the
    CAs would red on every legitimate re-pull, which is worse than no gate — so the residual
    members are fed in explicitly.
    """
    living_arrangement.assert_netted_cma_universe(_LIVE_GEOGRAPHY_SHAPES)

    promoted = (*_LIVE_GEOGRAPHY_SHAPES, "Gatineau (CMA), Que.")
    with pytest.raises(LoaderError, match="Gatineau \\(CMA\\), Que\\."):
        living_arrangement.assert_netted_cma_universe(promoted)

    respelled = tuple(n for n in _LIVE_GEOGRAPHY_SHAPES if n != "Saguenay (CMA), Que.")
    with pytest.raises(LoaderError, match="Saguenay") as exc:
        living_arrangement.assert_netted_cma_universe(respelled)
    assert "Gatineau" not in str(exc.value), "an absent member reported as an arrival"


def test_acquisition_refuses_a_newly_promoted_wholly_quebec_cma(tmp_path, monkeypatch):
    """THE REGRESSION: the committed puller, run against a cube that has gained a seventh
    wholly-Québec CMA, must REFUSE and write nothing.

    Before this gate it exited 0 and wrote a 126-cell extract whose geography set was exactly
    `set(SOURCE_GEOGRAPHIES)` — so `_read_cells` passed, every rate stayed a plausible
    fraction, and the newcomer sat un-netted inside HORS_RMR. The non-write assertion is not
    decoration: a clean rc=0 PLUS a written extract was the defect's whole signature.
    """
    puller = _puller()
    out = tmp_path / EXTRACT
    monkeypatch.setattr(sys, "argv", [_PULLER, "--out", str(out)])

    # POSITIVE CONTROL: on the real cube's member shape the gate must not fire. Reaching the
    # data endpoint is the proof it passed rather than the proof it is absent.
    monkeypatch.setattr(puller, "_post", _fake_post(_fake_cube_metadata()))
    with pytest.raises(_ReachedAcquisition):
        puller.main()
    assert not out.exists()

    monkeypatch.setattr(puller, "_post",
                        _fake_post(_fake_cube_metadata("Gatineau (CMA), Que.")))
    with pytest.raises(LoaderError, match="Gatineau"):
        puller.main()
    assert not out.exists(), (
        "the puller wrote an extract whose HORS_RMR residual silently absorbed a new CMA")


def test_degenerate_counts_raise_before_any_division(tmp_path, monkeypatch):
    """Every division in the derivation is guarded, and the guard PRECEDES it: a zero or
    inverted denominator must surface as LoaderError, never ZeroDivisionError and never a
    nonsense fraction that assert_fraction happens to accept."""
    cases = (
        ("non-positive private-household population", _P_TOTAL, 0),
        ("exceed the population", _P_ALONE, 10 ** 7),
        ("exceed the not-living-alone population", _P_COUPLED, 10 ** 7),
    )
    for match, arrangement, value in cases:
        def mutate(payload, arrangement=arrangement, value=value):
            _cell_of(payload, "Montréal (CMA), Que.", "Men+", "75 to 84 years",
                     arrangement)["value"] = value
            _cell_of(payload, "Montréal (CMA), Que.", "Total - Gender", "75 to 84 years",
                     arrangement)["value"] = value + _cell_of(
                         payload, "Montréal (CMA), Que.", "Women+", "75 to 84 years",
                         arrangement)["value"]
        with pytest.raises(LoaderError, match=match):
            _derive_mutated_extract(tmp_path, monkeypatch, mutate)


def test_duplicate_extract_cell_raises(tmp_path, monkeypatch):
    """A duplicated address would be silently absorbed into a rate that stays a fraction."""
    with pytest.raises(LoaderError, match="duplicate cell"):
        _derive_mutated_extract(tmp_path, monkeypatch,
                                lambda p: p["cells"].append(dict(p["cells"][0])))


# --- the SOURCE-GEOGRAPHY arm of the direction gate -----------------------------------
#
# The direction check first saw only the three DERIVED geographies, and a Men+/Women+
# transposition confined to ONE SMALL published CMA slipped through every gate:
#   * the swap is internally consistent (pop, alone and coupled move together), so no rate
#     leaves [0,1] and no degenerate guard fires;
#   * gender additivity is untouched — the two counts merely change sides;
#   * the derived geographies' 75+ direction survives, because one small CMA cannot reverse a
#     province-net residual.
# It DOES move the served HORS_RMR rates (measured below), which is the defect.
#
# WHAT THE SOURCE ARM ADDS, EXACTLY — measured 2026-08-08, and stated narrowly because this
# file's own history punishes overclaiming a gate's reach: the FOUR SMALL CMAs, and nothing else.
# The other three published geographies already refused, by DIFFERENT gates:
#   Quebec (province) only, and Montréal (CMA) only: `_rates_from_counts`' degenerate guards —
#     the residual then nets Men+ counts out of a Women+ province total and coupled persons
#     exceed the not-living-alone population. They REFUSE, but the message points at the
#     residual, not at the transposed junction. Recorded rather than fixed: the rates-before-
#     direction ordering that produces it is itself a measured choice (see the derivation's own
#     note — a degenerate published cell reaches the aggregate as a fake reversal, so a
#     direction-first pass misdirects the other way).
#   Québec (CMA) only: the PRE-EXISTING derived arm — QC_RMR IS that CMA, so the reversal is in
#     the derived counts too. (The MESSAGE now names the published row, because the published arm
#     is checked first inside the merged mapping; coverage is therefore asserted on the derived
#     counts, not on which arm's message wins.)
# All three facts are asserted below, so the scope claim is executable, not prose.

_SMALL_CMAS = ("Drummondville (CMA), Que.", "Saguenay (CMA), Que.",
               "Sherbrooke (CMA), Que.", "Trois-Rivières (CMA), Que.")

# 75+ AGGREGATE coupled counts (coupled_M, coupled_F) per PUBLISHED geography, transcribed from
# probe P3 §4b's per-band rows (`75 to 84 years` + `85 years and over`) — TEST-OWNED, never
# imported. A transposition confined to ONE geography turns that geography's OWN margin into the
# reversal the gate measures, so this table IS the gate's power, geography by geography.
_P3_75PLUS_COUPLED = {
    "Quebec": (160_525 + 31_905, 115_760 + 14_905),
    "Montréal (CMA), Que.": (70_150 + 16_295, 50_195 + 7_390),
    "Québec (CMA), Que.": (16_870 + 2_920, 12_535 + 1_470),
    "Saguenay (CMA), Que.": (3_665 + 645, 2_745 + 325),
    "Sherbrooke (CMA), Que.": (4_680 + 885, 3_475 + 445),
    "Trois-Rivières (CMA), Que.": (3_620 + 620, 2_745 + 325),
    "Drummondville (CMA), Que.": (1_985 + 285, 1_480 + 140),
}
# Spec §5's own reversal bound, transcribed rather than imported so a change to the module's
# constant reds here instead of moving this test with it.
_SPEC_REVERSAL_BOUND = 0.25


def _swap_genders(payload: dict, geographies) -> None:
    """Transpose Men+/Women+ inside the named PUBLISHED geographies, and nowhere else."""
    swap = {_P_SEX["M"]: _P_SEX["F"], _P_SEX["F"]: _P_SEX["M"]}
    targets = set(geographies)
    for cell in payload["cells"]:
        if cell["geography"] in targets and cell["gender"] in swap:
            cell["gender"] = swap[cell["gender"]]


def _derived_counts_from(payload: dict) -> dict:
    """{derived geography: {sex: {cube member: (pop, alone, coupled)}}} — TEST-OWNED netting.

    The producer's own view of the three derived geographies, rebuilt here so a claim about what
    the DERIVED arm can and cannot see is checkable without disabling the code under test, and
    without depending on which arm's message wins the race inside the merged mapping.
    """
    cube = {(c["geography"], c["gender"], c["age_group"], c["arrangement"]): c["value"]
            for c in payload["cells"]}

    def net(source: str, gender: str, member: str, arrangement: str) -> int:
        if source != "HORS_RMR":
            return cube[(source, gender, member, arrangement)]
        return (cube[(_P_PROVINCE, gender, member, arrangement)]
                - sum(cube[(c, gender, member, arrangement)] for c in _P_CMAS))

    return {
        name: {sex: {member: tuple(net(source, _P_SEX[sex], member, a)
                                   for a in (_P_TOTAL, _P_ALONE, _P_COUPLED))
                     for member in _P_BANDS.values()}
               for sex in _P_SEX}
        for name, source in (("MTL_RMR", "Montréal (CMA), Que."),
                             ("QC_RMR", "Québec (CMA), Que."),
                             ("HORS_RMR", "HORS_RMR"))
    }


def _derived_75plus_coupled(payload: dict, geography: str) -> tuple[int, int]:
    per_sex = _derived_counts_from(payload)[geography]
    return tuple(sum(per_sex[sex][member][2] for member in _P_BANDS.values())
                 for sex in ("M", "F"))


def test_a_transposition_confined_to_one_small_cma_is_refused_at_derivation(
        tmp_path, monkeypatch):
    """THE HOLE: each of the four small CMAs, transposed alone, must red — and name itself.

    Naming matters here: the message sends a reader to the geography whose junction is
    suspect, and a source-level reversal is a claim about ONE published row, not about the
    derived residual that happens to contain it.
    """
    for cma in _SMALL_CMAS:
        with pytest.raises(LoaderError, match="direction reversed") as exc:
            _derive_mutated_extract(tmp_path, monkeypatch,
                                    lambda p, cma=cma: _swap_genders(p, {cma}))
        assert cma in str(exc.value), (
            f"the message does not name {cma}, the geography whose junction is transposed")


def test_the_published_geographies_the_source_arm_does_not_add_are_covered_elsewhere(
        tmp_path, monkeypatch):
    """The scope claim above, executable — measured, not assumed. Two arms, two DIFFERENT gates.

    A gate credited with coverage it does not supply is worse than a missing one, so the
    province-wide and big-CMA transpositions are fed in and the arm that refuses each is
    identified. The degenerate arm is asserted by what the message is NOT rather than by the
    guard's exact wording (which would be brittle for no gain), and by the fact that it points
    at the RESIDUAL — the honest cost of keeping the recorded rates-before-direction ordering.
    """
    for geo in (_P_PROVINCE, "Montréal (CMA), Que."):
        with pytest.raises(LoaderError) as exc:
            _derive_mutated_extract(tmp_path, monkeypatch,
                                    lambda p, geo=geo: _swap_genders(p, {geo}))
        # This negative also pins ARM ORDER, deliberately: the published arm WOULD red on either
        # of these (Quebec's own margin is 0.3210), so what keeps the degenerate guards in front
        # is the rates-before-direction ordering the derivation records as a measured choice.
        # Read a failure here as "that ordering moved", not as a missing gate.
        assert "direction reversed" not in str(exc.value), (
            f"a {geo}-only transposition is refused by the degenerate-count guards (the residual "
            "nets Men+ out of a Women+ total), not by the direction gate")
        assert "exceed" in str(exc.value) and "HORS_RMR" in str(exc.value), (
            "the message points at the residual rather than at the transposed junction — "
            "recorded, not fixed")

    # Québec (CMA) only: refused BEFORE this task too, because QC_RMR IS that CMA — so the
    # reversal is present in the DERIVED counts. Asserted THERE rather than through the message,
    # which now names the published row: the merged mapping checks the published arm first, so a
    # message assertion would be reading arm ORDER, not coverage.
    payload = copy.deepcopy(_committed_extract())
    _swap_genders(payload, {"Québec (CMA), Que."})
    m, f = _derived_75plus_coupled(payload, "QC_RMR")
    assert f > m and (f - m) / f > _SPEC_REVERSAL_BOUND, (
        f"the DERIVED arm no longer sees a Québec-CMA transposition (coupled_M={m:,} "
        f"coupled_F={f:,}) — this geography's coverage would rest on the new arm alone")
    with pytest.raises(LoaderError, match="direction reversed") as exc:
        _derive_mutated_extract(tmp_path, monkeypatch,
                                lambda p: _swap_genders(p, {"Québec (CMA), Que."}))
    assert "Québec (CMA), Que." in str(exc.value)


def test_the_derived_arm_is_blind_to_a_small_cma_transposition():
    """WHY THE SOURCE ARM IS NOT DECORATION: under a small-CMA transposition every DERIVED cell
    stays non-degenerate and every derived 75+ direction stays M>F, so the whole pre-existing
    battery — the degenerate guards, `assert_fraction`, and the derived direction arm — sees
    nothing. Checked on the derived counts themselves rather than by disabling a gate."""
    for cma in _SMALL_CMAS:
        payload = copy.deepcopy(_committed_extract())
        _swap_genders(payload, {cma})
        for name, per_sex in _derived_counts_from(payload).items():
            for sex, bands in per_sex.items():
                for member, (pop, alone, coupled) in bands.items():
                    assert pop > 0 and alone <= pop and coupled <= pop - alone, (
                        f"{cma} transposed: {name} {sex} {member} is degenerate — a different "
                        "guard would fire and this mutant would prove nothing about the new arm")
            m, f = _derived_75plus_coupled(payload, name)
            assert m > f, (
                f"{cma} transposed: the DERIVED arm already sees a reversal at {name} "
                f"(coupled_M={m:,} coupled_F={f:,}) — the source arm is not what catches this")


def test_the_source_direction_gate_has_measured_power_at_every_published_geography():
    """The gate's power is a MEASUREMENT per geography, and the weakest one is recorded.

    A transposition confined to geography X reds iff X's own 75+ coupled margin exceeds spec
    §5's bound — the swap makes the observed reversal EQUAL that margin. So a re-pull that
    narrows the weakest margin under the bound does not false-positive; it goes BLIND, silently.
    Pinning the weakest margin here is what turns that into a red: read a failure as "the source
    arm lost its power at this geography", never as a derivation bug.
    """
    cube = _extract_cube()
    margins = {}
    for geo, cited in _P3_75PLUS_COUPLED.items():
        m, f = (sum(cube[(geo, gender, member, _P_COUPLED)] for member in _P_BANDS.values())
                for gender in (_P_SEX["M"], _P_SEX["F"]))
        assert (m, f) == cited, f"{geo}: the extract disagrees with probe P3 §4b's coupled counts"
        assert m > f, (
            f"{geo}: coupled_M {m:,} no longer exceeds coupled_F {f:,} at 75+ — the direction "
            "this gate asserts is a property of the DATA (P3 §4: M>F at 75+ in every published "
            "Québec geography); if it has changed, the gate's premise has changed")
        margins[geo] = (m - f) / max(m, f)

    assert set(margins) == set(living_arrangement.SOURCE_GEOGRAPHIES), (
        "this table no longer covers every geography the derivation reads — the power claim "
        "would be silently partial")
    assert set(living_arrangement.SOURCE_GEOGRAPHIES).isdisjoint(
        {geo.value for geo in Geography}), (
        "a published geography label now collides with a Geography value — the published and "
        "derived arms are handed to the gate as ONE mapping, so a collision drops the published "
        "arm silently and this whole gate loses that geography")
    weakest = min(margins, key=margins.get)
    assert margins[weakest] > _SPEC_REVERSAL_BOUND, (
        f"the weakest 75+ margin is {weakest} at {margins[weakest]:.4f}, at or under the "
        f"{_SPEC_REVERSAL_BOUND} reversal bound — a transposition confined to that geography no "
        "longer reds, and the source arm is blind there")
    assert (weakest, round(margins[weakest], 4)) == ("Trois-Rivières (CMA), Que.", 0.2759), (
        f"the recorded weakest margin moved to {weakest} @ {margins[weakest]:.4f}; the headroom "
        "over the bound was 0.0259 when this was measured")
    assert living_arrangement._REVERSAL_BOUND == _SPEC_REVERSAL_BOUND, (
        "the module's reversal bound is no longer spec §5's — a threshold change, not a refactor")


def test_the_small_cma_transposition_moves_a_served_hors_rmr_rate():
    """The mutant is CONSEQUENTIAL, so the gate above is not defending a distinction without a
    difference. Recomputed test-side (the derivation now refuses to produce it): a Saguenay-only
    transposition moves the served HORS_RMR 75-84 Men living_alone rate 0.244332 -> 0.230552.
    That is 0.01378 — an order of magnitude above the 0.001637 separation the six-CMA netting
    arm rests on, and it is a rate the model multiplies by a population."""
    payload = copy.deepcopy(_committed_extract())
    _swap_genders(payload, {"Saguenay (CMA), Que."})
    cube = {(c["geography"], c["gender"], c["age_group"], c["arrangement"]): c["value"]
            for c in payload["cells"]}

    def net(arrangement: str) -> int:
        member = _P_BANDS["75-84"]
        return (cube[(_P_PROVINCE, _P_SEX["M"], member, arrangement)]
                - sum(cube[(c, _P_SEX["M"], member, arrangement)] for c in _P_CMAS))

    transposed = net(_P_ALONE) / net(_P_TOTAL)
    served = living_alone_rate(load_living_arrangement(), Geography.HORS_RMR, age=80, sex="M")
    assert served == pytest.approx(0.244332, abs=5e-6)
    assert transposed == pytest.approx(0.230552, abs=5e-6)
    assert abs(served - transposed) == pytest.approx(0.013780, abs=5e-6)
    assert abs(served - transposed) > 1e-3, (
        "the transposition no longer moves the served rate more than the netting arm's floor")


def test_borrow_map_is_the_same_as_the_ownership_loaders():
    """Same DRIFT CLASS as the `_QC_CMAS` equality above, and green on arrival for the same
    reason: the fact is true today and nothing enforces it.

    The two loaders' rates multiply the same population under one geography label. A member that
    borrowed MTL_RMR for ownership but derived its own living-arrangement rates (or borrowed a
    DIFFERENT parent) would pair a borrowed prior with a measured rate inside a single product,
    with both still plausible fractions and both artifacts still regenerating cleanly. The two
    modules keep their own maps deliberately (each is written against its own upstream table);
    this asserts the equality that makes the join legitimate — at the CONSTANT and, because a
    matching map flagged differently would be just as wrong, on the two shipped ARTIFACTS.
    """
    assert living_arrangement._BORROWS_FROM == census._BORROWS_FROM

    borrowers = {geo.value for geo in living_arrangement._BORROWS_FROM}
    assert borrowers == set(_P_BORROWERS)
    flagged = {
        name: {geo for geo, cells in table.items() if isinstance(cells, dict) and cells.get("_flag")}
        for name, table in (("living_arrangement", load_living_arrangement()),
                            ("ownership", census.load_ownership_rates()))
    }
    assert flagged["living_arrangement"] == flagged["ownership"] == borrowers, (
        f"the two shipped artifacts flag different geographies as borrowed: {flagged}")


def test_a_cell_the_acquisition_path_did_not_verify_is_refused_at_derivation(
        tmp_path, monkeypatch):
    """SIBLING OF THE PULLER'S TRAP 2, at the derivation.

    The puller refuses a cell that came back with an EMPTY `vectorDataPoint`. A cell that came
    back WITH a data point but a non-SUCCESS request status, or with a point-level `statusCode`
    that is not 0, is written to the extract — and before this gate it divided straight into a
    rate that stayed a plausible fraction (measured 2026-08-08). All 126 committed cells carry
    `SUCCESS` / `0`, asserted first: that is what makes the committed artifact unaffected AND
    makes the gate's expectation a fact about the source rather than a hope.

    Four shapes, because they reach the guard through different operands — a failed request, a
    flagged data point, and each field ABSENT. Absent is refused deliberately, and it is the
    more dangerous case: a bad status announces itself, while an unrecorded one is
    indistinguishable from a verified cell. Same posture `_verify_artifact_provenance` takes on
    a missing digest.
    """
    cells = _committed_extract()["cells"]
    assert len(cells) == 126
    assert {(c["status"], c["status_code"]) for c in cells} == {("SUCCESS", 0)}

    address = tuple(cells[0][k] for k in ("geography", "gender", "age_group", "arrangement"))
    cases = (
        ("failed request", lambda c: c.update(status="FAILED", status_code=0), "FAILED"),
        ("flagged point", lambda c: c.update(status="SUCCESS", status_code=7), "7"),
        ("status absent", lambda c: c.pop("status"), "None"),
        ("status_code absent", lambda c: c.pop("status_code"), "None"),
    )
    for shape, mutate, needle in cases:
        with pytest.raises(LoaderError, match="status") as exc:
            _derive_mutated_extract(tmp_path, monkeypatch, lambda p: mutate(p["cells"][0]))
        message = str(exc.value)
        assert needle in message, f"{shape}: the message does not show what the cell recorded"
        assert all(part in message for part in address), (
            f"{shape}: the message does not name the cell — {address} is where to look")
        assert str(cells[0]["value"]) in message, (
            f"{shape}: a PRESENT value is exactly what makes this cell dangerous; show it")


# --- recorded diagnostic (steering ruling A) -------------------------------------------

def test_couple_balance_imbalance_is_recorded_and_not_gated():
    """STEERING RULING A retired the 0.25 SAME-AGE balance gate; the imbalance is RECORDED.

    Both halves are asserted, and the first is what makes the second non-vacuous: the cited
    data really does breach 0.25 per band (probe P3 §4b: 13 of 21 rows), so a loader that
    still carried that gate could not have loaded at all. The recorded figures are recomputed
    from the extract here, so a hand-edited diagnostic reds.
    """
    diagnostic = _committed_artifact()["_provenance"]["couple_balance_diagnostic"]
    assert set(diagnostic) - {"_what"} == {"MTL_RMR", "QC_RMR", "HORS_RMR"}, (
        "borrowed geographies must not repeat their parent's profile as if it were their own")

    cube = _extract_cube()

    def coupled(geo, gender, member):
        if geo != "HORS_RMR":
            src = {"MTL_RMR": "Montréal (CMA), Que.", "QC_RMR": "Québec (CMA), Que."}[geo]
            return cube[(src, gender, member, _P_COUPLED)]
        return (cube[(_P_PROVINCE, gender, member, _P_COUPLED)]
                - sum(cube[(c, gender, member, _P_COUPLED)] for c in _P_CMAS))

    breaches = 0
    for geo, rows in diagnostic.items():
        if geo == "_what":
            continue
        assert set(rows) == {"75-84", "85+", "75+"}
        for label, member in _P_BANDS.items():
            m, f = coupled(geo, "Men+", member), coupled(geo, "Women+", member)
            assert rows[label]["coupled_M"] == m and rows[label]["coupled_F"] == f
            assert rows[label]["imbalance"] == pytest.approx(abs(m - f) / max(m, f), abs=5e-7)
            breaches += rows[label]["imbalance"] > 0.25
        m_tot = sum(coupled(geo, "Men+", member) for member in _P_BANDS.values())
        f_tot = sum(coupled(geo, "Women+", member) for member in _P_BANDS.values())
        assert rows["75+"]["coupled_M"] == m_tot and rows["75+"]["coupled_F"] == f_tot
        assert rows["75+"]["direction"] == "M>=F"
    assert breaches >= 5, (
        f"only {breaches} bands breach the retired 0.25 same-age gate — if the cited data no "
        "longer breaches it, the ruling that retired it should be re-examined, and this gate "
        "is no longer evidence for anything")


def test_provenance_records_the_vintage_and_the_cited_table():
    """The artifact is the durable record a downstream reader gets. It must name the table, the
    vintage, the universe and the citation — a rate table whose provenance is prose-free is
    indistinguishable from one somebody typed."""
    provenance = _committed_artifact()["_provenance"]
    assert provenance["statcan_table"] == "98-10-0134-01"
    assert provenance["product_id"] == 98100134
    assert provenance["ref_date"] == "2021"
    assert provenance["source"] == EXTRACT
    assert provenance["sha256"] == pins.WORKBOOK_SHA256[EXTRACT]
    assert "9810013401" in provenance["citation"]
    assert "PRIVATE households" in provenance["universe"]
    assert "no invented default" in provenance["couple_share_rule"].lower() or \
        "NO invented default" in provenance["couple_share_rule"]
    assert set(provenance["netted_cmas"]) == set(_P_CMAS)


def test_uncited_extract_is_refused_at_derivation(tmp_path, monkeypatch):
    """The charter carry — an uncited figure is a defect — applied to a rate TABLE. A `.get`-only
    read of `_pull` would ship an artifact whose citation and vintage are `null` while every rate
    stayed correct. Three shapes: the block absent, one field emptied, and the WRONG cube pulled
    into this filename and dutifully re-pinned (which no digest check can see).
    """
    cases = (
        ("block absent", lambda p: p.pop("_pull"), "no `_pull` block"),
        ("field empty", lambda p: p["_pull"].update(citation=""), "citation"),
        ("wrong cube", lambda p: p["_pull"].update(product_id=98100137), "not the cited cube"),
    )
    for _shape, mutate, match in cases:
        with pytest.raises(LoaderError, match=match):
            _derive_mutated_extract(tmp_path, monkeypatch, mutate)


def test_provenance_names_the_private_household_multiplicand_constraint():
    """These rates are CONDITIONAL on private-household membership, so the population they
    multiply must have collectives removed first (spec §5). Getting that wrong in either
    direction — applying them to the raw ISQ stock, or removing the collective share twice —
    leaves every rate and every product a plausible number. The constraint is recorded on the
    artifact so a downstream reader meets it without reading this module."""
    note = _committed_artifact()["_provenance"]["multiplicand_note"]
    assert "collective_share_75plus" in note and "PRIVATE-HOUSEHOLD" in note
