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
"""
import csv
import hashlib
import json
import shutil

import pytest

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census, pins
from demoflow.loaders.census import (
    CENSUS_EXTRACT,
    derive_ownership_from_csv,
    headship_rate,
    load_headship_rates,
    load_ownership_rates,
    ownership_rate,
)
from demoflow.loaders.pins import DATA_DIR


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


def test_out_of_unit_ownership_rate_raises(tmp_path):
    # `_provenance.sha256` added 2026-08-08 for steering ruling L (the load path now refuses an
    # unprovenanced artifact). It is scaffolding to REACH this gate, not the gate itself: the
    # assertion below is unchanged — an out-of-unit rate must raise at `ownership_rate`, and it
    # must raise THERE and not at load, which is exactly what a valid provenance block pins.
    (tmp_path / "ownership_by_geo_age.json").write_text(json.dumps(
        {"_provenance": {"sha256": pins.WORKBOOK_SHA256[CENSUS_EXTRACT]},
         "rates": {g.value: {"75+": 1.5} for g in Geography}}))
    rates = load_ownership_rates(data_dir=tmp_path)
    with pytest.raises(LoaderError, match=r"\[0, ?1\]|fraction"):
        ownership_rate(rates, Geography.MTL_RMR, age=80)


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


def _independent_band_counts() -> dict[str, dict[str, tuple[int, int]]]:
    """{GEO label: {model band: (owner, total)}}, recomputed from the committed CSV
    without importing any of the producer's logic (the P2 gate-3 discipline)."""
    member_band = {m: band for band, members in _BAND_MEMBERS.items() for m in members}
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
            ("ownership", _SPEC_AGE_BANDS, census._AGE_BANDS, 25),
            ("headship", _SPEC_HEADSHIP_BANDS, census._HEADSHIP_BANDS, 0)):
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


def test_missing_headship_key_raises_rather_than_serving_an_empty_curve(tmp_path):
    """A renamed/absent top-level key must fail as a FILE error, not resurface downstream
    as 'no headship rate for band 35-54' — a message that reads as a band bug."""
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


def test_isq_territory_note_figures_are_recomputable():
    """Every figure cited in the artifact is RECOMPUTED here, never trusted as typed.

    The note records that this Census rate's territory (province net of the six
    wholly-Québec CMAs, which INCLUDES the Québec side of Ottawa-Gatineau) is not the
    territory of the ISQ population it will multiply (`Territoire hors des RMR`, which
    EXCLUDES it — ISQ publishes Ottawa-Gatineau Québec-part-only, workbook footnote 2). The
    generated-artifact discipline says a cited value must be computed, so this reads the
    pinned ISQ workbook and asserts each figure appears in the note verbatim.
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
    for value in (province, netted, census_territory, isq_hors_rmr, gap):
        assert f"{value:,.0f}" in note, f"note does not cite {value:,.0f}"
    assert f"{gap / census_territory * 100:.2f}%" in note
    assert f"{gap / isq_hors_rmr * 100:.2f}%" in note


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
