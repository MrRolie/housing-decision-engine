"""Task 25b — the immigrant-input JOIN TABLE (rulings S/T + amendment #11) and the I2
decomposition gate (spec §6; codex r5-F3/r5-F4/r6-F1/r7-F3/r7-F8).

TWO HALVES, and they fail in different ways:

  * `demand/i2.py` is ARITHMETIC with a gate — `P_resident = P_ISQ − Σ surviving arrivals`,
    asserted per cell before any consumer. Its failure mode is a gate that cannot fire.
  * `demand/immigrant_inputs.py` is a table of MEASURED NUMBERS. Its failure mode is a value
    that reads as measured and was typed — which is why every literal it serves is coupled
    here to `probes/P8-immigrant-inputs.md`'s DECISION tokens ON THE DIGITS. The chain is
    spec §6 → P8 (already coupled to §6 by `test_probe_p8.py`) → this table. Break any link
    and the measurement chain that produced 0.9634 becomes decoration.

THE PLAN'S TEST BODIES ARE SUPERSEDED IN FIVE PLACES, each named at the ruling that moved it
(the plan predates amendments #7–#11; where they conflict, §6 wins):

  1. VALUES: the plan's 0.42/0.45/0.43 headships and 0.62/0.70/0.66 ratios are uncited and
     explicitly OUT (§6 "Binds Task 25b"). Ruling S/T's measured pairs replace them.
  2. `resolve_immigrant_inputs(MTL_RMR).flag is None` → per-field provenance, with `cited`
     as the AFFIRMATIVE member. §6 re-ruled MTL direct-and-cited and then required per-field
     provenance in the same paragraph; `None` cannot express "measured for this geography".
  3. `resolve_immigrant_inputs(LAVAL_RA13).flag == "borrowed_prior"` → LAVAL_RA13 is CITED
     with its OWN measured values (ruling T + the amendment-#11 territory gate, PASS at
     +0.611% against a 1.586% derived threshold). MTL_ISLAND_RA06 moves the same way.
  4. `resolve_immigrant_inputs(HORS_RMR).flag == "borrowed_prior"` → `computed_residual`:
     the province NET of the six wholly-QC CMAs — and, since amendment #13, NET of the
     Ottawa-Gatineau CMA's 16 Québec-side census subdivisions too. Nothing is borrowed, and
     its territory is constructed rather than measured, so neither existing member describes
     it. The flag is unmoved by #13; the TERRITORY under it is what moved.
  5. `p_resident(...) == pytest.approx(9_500.0)` → EXACT equality (the decomposition
     fixture's exact-oracle law; a subtraction of two exactly-representable floats has one
     right answer, and `approx` would hide a wiring change of a few ULP-sized terms).

ADDED beyond the plan, at defects measured in its bodies: NaN cannot pass either I2 gate
silently (every ordering against NaN is False — `abs(nan − x) > tol` and `nan < 0.0` are
both False, so the plan's two gates green-light a NaN); the no-unstated-default raise is
EXERCISED rather than left dead behind a total table; and the floor gate's coverage is
pinned against P8's own floor triples so a stand-in cannot be substituted for a geography
the source does not publish.
"""

import dataclasses
import re
from pathlib import Path

import pytest

import demoflow.demand.immigrant_inputs as ii
from demoflow.demand.i2 import assert_i2_identity, assert_p_resident_nonneg, p_resident
from demoflow.demand.immigrant_inputs import (
    INPUT_PROVENANCE,
    LIVING_ALONE_FLOOR,
    FLOOR_NOT_COVERED,
    ImmigrantInputs,
    resolve_immigrant_inputs,
)
from demoflow.errors import CalibrationError, LoaderError
from demoflow.geography import Geography
from demoflow.loaders.constants import ANCHOR_FLAGS

from ._probe_asserts import token as _token

NOTE = Path(__file__).resolve().parent.parent / "probes" / "P8-immigrant-inputs.md"

# The five geographies P8 MEASURES. RA14/15/16 are deliberately absent: nothing was measured
# for them, which is exactly what `borrowed_prior` records.
MEASURED = (Geography.MTL_RMR, Geography.QC_RMR, Geography.HORS_RMR,
            Geography.MTL_ISLAND_RA06, Geography.LAVAL_RA13)


# ============================================================ the note-coupling machinery

def _note_text() -> str:
    text = NOTE.read_text(encoding="utf-8")
    assert text.strip(), f"{NOTE} is empty — a coupling gate over an empty note passes vacuously"
    return text


def _parse_geography_values(text: str, token_name: str) -> dict[Geography, float]:
    """`{Geography: value}` parsed from one DECISION token, KEYED ON THE DIGITS.

    The key is the geography's enum VALUE followed by its number — never a prose prefix,
    which a reworded sentence would silently detach (and never `str(geo)`, which under
    py3.12 str-Enum yields `'Geography.MTL_RMR'`). An absent or renamed token is a FAILURE,
    not an empty result: absence discipline — a parser that returns `{}` makes every
    comparison below vacuous.
    """
    value = _token(text, token_name)
    assert value, f"{NOTE.name} carries no resolvable `{token_name}` token (got {value!r})"
    found = {}
    for geo in Geography:
        hit = re.search(rf"\b{re.escape(geo.value)}\s+([0-9]*\.?[0-9]+)", value)
        if hit:
            found[geo] = float(hit.group(1))
    assert found, f"`{token_name}` names no modeled geography with a value: {value!r}"
    return found


def _parse_floor_triples(text: str) -> dict[Geography, tuple[float, float]]:
    """`{Geography: (headship, living_alone_floor)}` from `DECISION-FLOOR-GATE`.

    Keyed on the numeric TRIPLE `GEO <headship> > <floor>`, so the covered SET is read off
    the digits too: a geography the note does not floor cannot appear here by rewording.
    """
    value = _token(text, "DECISION-FLOOR-GATE")
    assert value, f"{NOTE.name} carries no resolvable `DECISION-FLOOR-GATE` token"
    found = {}
    for geo in Geography:
        hit = re.search(rf"\b{re.escape(geo.value)}\s+([0-9]*\.?[0-9]+)\s*>\s*([0-9]*\.?[0-9]+)", value)
        if hit:
            found[geo] = (float(hit.group(1)), float(hit.group(2)))
    assert found, f"`DECISION-FLOOR-GATE` names no floored geography: {value!r}"
    return found


def _mismatches(text: str) -> list[str]:
    """Every disagreement between the served table and the note's measured digits.

    Runs BOTH directions: a note value the table does not serve, and a table entry claiming
    a measured provenance that the note does not back. One direction alone lets a value
    drift in whichever half the gate does not read.
    """
    headship = _parse_geography_values(text, "DECISION-HEADSHIP")
    ratio = _parse_geography_values(text, "DECISION-RATIO")
    bad = []
    for geo, measured in headship.items():
        served = resolve_immigrant_inputs(geo).immigrant_headship
        if served != measured:
            bad.append(f"headship[{geo.value}]: table {served} != note {measured}")
    for geo, measured in ratio.items():
        served = resolve_immigrant_inputs(geo).ownership_ratio
        if served != measured:
            bad.append(f"ratio[{geo.value}]: table {served} != note {measured}")
    for geo in Geography:
        row = resolve_immigrant_inputs(geo)
        if row.headship_provenance != "borrowed_prior" and geo not in headship:
            bad.append(f"headship[{geo.value}] claims {row.headship_provenance} but the note "
                       f"publishes no measurement for it")
        if row.ratio_provenance != "borrowed_prior" and geo not in ratio:
            bad.append(f"ratio[{geo.value}] claims {row.ratio_provenance} but the note "
                       f"publishes no measurement for it")
    return bad


# A PLAUSIBLE defect, not a nonsense one: MTL_RMR's ratio overwritten with the 0.9600 that
# still sits in the note as HORS_RMR's SUPERSEDED row (amendment #13 moved the served value
# to 1.0248 and P8 §2 keeps the superseded one printed beside it) — the copy slip a
# hand-transcribed table produces, and MORE plausible now that a stale digit for a real
# geography is published in the same note.
_DEFECT = ("0.9634", "0.9600")

# Rewordings that touch PROSE only — no digit, no geography token. The second one sits
# INSIDE the `DECISION-RATIO` value the parser captures, so the green-on-rewording proof is
# not merely a proof about text the gate never reads.
_REWORDS = (
    ("## 2. The ruled inputs, RECOMPUTED", "## 2. The ruled inputs, RE-DERIVED HERE"),
    ("settled owner-maintainer propensity ÷ non-immigrant, same member, same universe",
     "the settled owner-maintainer propensity over the non-immigrant one, one member, one universe"),
    ("headship exceeds the settled living-alone share at",
     "headship sits strictly above the settled living-alone share at"),
)


def _with_defect(text: str) -> str:
    old, new = _DEFECT
    assert old in text, f"{old} is not in the note — the defect proof would be vacuous"
    return text.replace(old, new)


def _reworded(text: str) -> str:
    for old, new in _REWORDS:
        assert old in text, f"rewording target absent — the proof would be vacuous: {old!r}"
        text = text.replace(old, new)
    return text


# ================================================================= the join table's values

def test_the_table_serves_the_ruled_values_per_field():
    """Rulings S and T, as the table must serve them. Written out geography by geography so
    a reader sees the ruled pair, not a loop over the module's own dict (which would assert
    the table equals itself)."""
    ruled = {
        Geography.MTL_RMR: (0.5259, 0.9634, "cited", "cited"),
        Geography.QC_RMR: (0.5054, 0.8910, "cited", "cited"),
        Geography.HORS_RMR: (0.5234, 1.0248, "computed_residual", "computed_residual"),
        Geography.MTL_ISLAND_RA06: (0.5555, 1.0757, "cited", "cited"),
        Geography.LAVAL_RA13: (0.4816, 1.1112, "cited", "cited"),
        # RA proxies borrow the PARENT CMA (MTL_RMR) on both fields — §6 "RA members borrow
        # their parent CMA, borrowed_prior"; deliberately NOT extended to census divisions.
        Geography.LANAUDIERE_RA14_PROXY: (0.5259, 0.9634, "borrowed_prior", "borrowed_prior"),
        Geography.LAURENTIDES_RA15_PROXY: (0.5259, 0.9634, "borrowed_prior", "borrowed_prior"),
        Geography.MONTEREGIE_RA16_PROXY: (0.5259, 0.9634, "borrowed_prior", "borrowed_prior"),
    }
    assert set(ruled) == set(Geography), "the ruled table must cover every modeled member"
    for geo, (headship, ratio, h_prov, r_prov) in ruled.items():
        row = resolve_immigrant_inputs(geo)
        assert isinstance(row, ImmigrantInputs)
        assert row.immigrant_headship == headship, geo.value
        assert row.ownership_ratio == ratio, geo.value
        assert (row.headship_provenance, row.ratio_provenance) == (h_prov, r_prov), geo.value
        assert len(row.source.strip()) > 20, f"{geo.value}: source too thin to be a citation"


def test_the_plans_uncited_literals_are_gone():
    """§6 "Binds Task 25b": the plan's 0.42/0.45/0.43 and 0.62/0.70/0.66 are OUT. They are
    checked as ABSENT rather than merely not-asserted, because a superseded literal left in
    the module would keep serving some geography quietly."""
    served = {v for geo in Geography
              for v in (resolve_immigrant_inputs(geo).immigrant_headship,
                        resolve_immigrant_inputs(geo).ownership_ratio)}
    for voided in (0.42, 0.45, 0.43, 0.62, 0.70, 0.66):
        assert voided not in served, f"{voided} is a voided plan literal (§6 Binds Task 25b)"


def test_ra_proxies_carry_the_parent_cma_value():
    """Both fields, both provenances, and the VALUES identical to MTL_RMR's — so a parent
    value that moves under a P8 re-run moves the proxies with it. They are coupled to the
    note THROUGH the parent; the note publishes no token of their own, which is precisely
    what `borrowed_prior` records."""
    parent = resolve_immigrant_inputs(Geography.MTL_RMR)
    for geo in (Geography.LANAUDIERE_RA14_PROXY, Geography.LAURENTIDES_RA15_PROXY,
                Geography.MONTEREGIE_RA16_PROXY):
        row = resolve_immigrant_inputs(geo)
        assert row.immigrant_headship == parent.immigrant_headship
        assert row.ownership_ratio == parent.ownership_ratio
        assert row.headship_provenance == row.ratio_provenance == "borrowed_prior"
        assert "MTL_RMR" in row.source, f"{geo.value}: source must name the parent it borrows"


# ============================================ citation coupling — the digits, proven 3 ways

def test_the_served_values_are_coupled_to_P8s_decision_tokens():
    """The gate itself, on the committed note: zero disagreements, and it really read the
    five measured geographies (a gate that parsed nothing would report zero too)."""
    text = _note_text()
    assert set(_parse_geography_values(text, "DECISION-HEADSHIP")) == set(MEASURED)
    assert set(_parse_geography_values(text, "DECISION-RATIO")) == set(MEASURED)
    assert _mismatches(text) == []


def test_the_coupling_reds_on_a_perturbed_digit_alone():
    """Proof 1 of 3: the note's value moves, its prose does not — the table must RED. This is
    the regenerated-note case the coupling exists for."""
    bad = _mismatches(_with_defect(_note_text()))
    assert bad, "a perturbed DECISION-RATIO digit did not RED the join table"
    assert any("MTL_RMR" in m and "0.9634" in m for m in bad), bad


def test_the_coupling_reds_on_a_perturbed_digit_under_a_reworded_note():
    """Proof 2 of 3: rewording must not LAUNDER the defect. A gate keyed on a prose prefix
    passes here — it stops finding the sentence and reports nothing wrong."""
    bad = _mismatches(_reworded(_with_defect(_note_text())))
    assert bad, "a perturbed digit escaped the gate once the surrounding prose was reworded"
    assert any("MTL_RMR" in m and "0.9634" in m for m in bad), bad


def test_the_coupling_stays_green_when_only_the_prose_is_reworded():
    """Proof 3 of 3: the gate binds the MEASUREMENT, not the note's wording. Without this a
    coupling that RED on any edit would be re-typed into a literal at the first P8 re-run."""
    reworded = _reworded(_note_text())
    assert reworded != _note_text(), "the rewording did not change the note"
    assert _mismatches(reworded) == []


def test_the_coupling_refuses_a_note_it_could_not_read():
    """A coupling over a missing or renamed token must FAIL, never pass vacuously — the
    can't-fail check this repo's probe gates already refuse elsewhere."""
    text = _note_text()
    with pytest.raises(AssertionError, match="DECISION-HEADSHIP"):
        _mismatches(text.replace("DECISION-HEADSHIP", "DECISION-HEADSHIP-RATE"))
    with pytest.raises(AssertionError, match="DECISION-RATIO"):
        _mismatches(text.replace("DECISION-RATIO:", "DECISION-RATIOS:"))
    with pytest.raises(AssertionError):
        _mismatches("")


def test_a_geography_the_note_does_not_measure_cannot_claim_a_measured_provenance():
    """The other direction of the coupling: `cited` / `computed_residual` are claims ABOUT
    the note. Dropping MTL_ISLAND_RA06 from the token must RED, because the table still
    claims that geography was measured."""
    text = _note_text().replace("MTL_ISLAND_RA06 0.5555; ", "").replace("MTL_ISLAND_RA06 1.0757; ", "")
    bad = _mismatches(text)
    assert any("MTL_ISLAND_RA06" in m and "publishes no measurement" in m for m in bad), bad


def test_each_measured_geographys_provenance_matches_the_notes_own_source_token():
    """P8 records HOW each geography was obtained, per geography, in its own token. The
    table's per-field vocabulary must agree with it: four `cited`, one COMPUTED residual.
    Matched case-insensitively on the classification word — the note's own vocabulary — so a
    capitalisation change in a re-run does not RED a correct table."""
    text = _note_text()
    for geo in MEASURED:
        value = _token(text, f"DECISION-SOURCE-{geo.value}")
        assert value, f"{NOTE.name} carries no DECISION-SOURCE-{geo.value} token"
        row = resolve_immigrant_inputs(geo)
        for field in (row.headship_provenance, row.ratio_provenance):   # checked per FIELD
            if field == "cited":
                assert "cited" in value.lower(), f"{geo.value}: {value!r}"
            else:
                assert field == "computed_residual", f"{geo.value}: {field}"
                assert "computed" in value.lower() and "residual" in value.lower(), (
                    f"{geo.value}: {value!r}")


def test_the_hors_rmr_source_states_the_construction_that_makes_it_a_residual():
    """HORS_RMR is the one CONSTRUCTED territory, and WHICH construction is load-bearing —
    amendment #13 moved it. The row must state the ALIGNED territory: the province net of the
    six wholly-QC CMAs AND net of the Ottawa-Gatineau CMA's 16 Québec-side census
    subdivisions, counts read from the census-division sibling, membership carried from P10.

    Pinned on the SUPERSEDED reading too, in the negative: this row used to say Gatineau stays
    INSIDE the residual and that ISQ's same-named row must never be substituted for it. Both
    halves reversed — the whole point of #13 is that the rate's territory now MATCHES the
    ISQ flow territory it multiplies. A source left at the old text would read as a citation
    for digits it no longer describes, which is exactly the silent-decay this coupling exists
    to prevent, so the old ruling's marker `P2` is asserted ABSENT rather than merely
    unasserted."""
    row = resolve_immigrant_inputs(Geography.HORS_RMR)
    source = row.source
    # the aligned construction, stated in the row itself
    assert "six" in source.lower() and "98-10-0621-01" in source
    assert "Ottawa-Gatineau" in source and "16" in source
    assert "98-10-0622-01" in source, "the sibling cube the netted counts are read from"
    assert "P10" in source, "the note the 16-member census-subdivision list is carried from"
    assert "#13" in source, "the amendment that ruled this territory"
    assert "aligned" in source.lower()
    # the old ruling's CITATION MARKER is gone; the superseded construction stays stated
    # above it, as the row's own record of what moved
    assert "P2" not in source, (
        "the source still cites P2's Gatineau-INSIDE definition, which amendment #13 "
        "superseded — a citation for a territory this row no longer measures")


# ==================================================== the provenance vocabulary (seat ruling)

def test_input_provenance_is_closed_and_is_this_tables_own_vocabulary():
    """Three members, and the set is NEITHER `constants.ANCHOR_FLAGS` NOR either of spec §7's
    emitter enums (ScenarioPrior rows {borrowed_prior, ra_proxy, never_relax_stress},
    spec:352-353; rankings rows {borrowed_prior, ra_proxy, closed_cohort_exceedance},
    spec:434). The discriminator: an anchor flag says where a CONSTANT came from, a §7 member
    says what an output ROW means, these say how THIS GEOGRAPHY'S INPUT was obtained."""
    assert INPUT_PROVENANCE == frozenset({"cited", "borrowed_prior", "computed_residual"})
    assert INPUT_PROVENANCE != ANCHOR_FLAGS
    assert INPUT_PROVENANCE != frozenset({"borrowed_prior", "ra_proxy", "never_relax_stress"})
    assert INPUT_PROVENANCE != frozenset({"borrowed_prior", "ra_proxy", "closed_cohort_exceedance"})
    # the members the EMITTER enums own are not admissible here, and vice versa
    for foreign in ("ra_proxy", "never_relax_stress", "closed_cohort_exceedance"):
        assert foreign not in INPUT_PROVENANCE


def test_the_module_docstring_states_why_the_vocabulary_is_distinct():
    """The discriminator has to be READABLE where the set is defined, not only in a test.
    Same defect class as constants.py's docstring regression: a rule enforced in code and
    unstated (or misstated) on the module's first screen teaches every reader the wrong thing."""
    doc = ii.__doc__
    assert "ANCHOR_FLAGS" in doc and "§7" in doc
    assert "computed_residual" in doc and "constructed" in doc.lower()


@pytest.mark.parametrize("field", ["headship_provenance", "ratio_provenance"])
def test_an_unknown_provenance_raises_at_construction(field):
    kwargs = dict(geography=Geography.MTL_RMR, immigrant_headship=0.5, ownership_ratio=1.0,
                  headship_provenance="cited", ratio_provenance="cited",
                  source="a source string long enough to be a citation")
    kwargs[field] = "measured"                      # plausible synonym, NOT in the closed set
    with pytest.raises(LoaderError, match="unknown provenance"):
        ImmigrantInputs(**kwargs)


def test_a_mixed_pair_is_EXPRESSIBLE_which_is_why_provenance_is_per_field():
    """The seat ruling's reason, made checkable: a geography may hold a cited ratio beside a
    borrowed headship. NO row in today's table mixes — so without this test the per-field
    carrier is untested structure, and the next editor collapses it back to one flag."""
    mixed = ImmigrantInputs(
        geography=Geography.LANAUDIERE_RA14_PROXY, immigrant_headship=0.5259,
        ownership_ratio=1.0757, headship_provenance="borrowed_prior", ratio_provenance="cited",
        source="a hypothetical mixed-provenance row: parent-CMA headship, own measured ratio")
    assert mixed.headship_provenance != mixed.ratio_provenance
    assert not any(resolve_immigrant_inputs(g).headship_provenance
                   != resolve_immigrant_inputs(g).ratio_provenance for g in Geography), (
        "a served row now mixes provenance — update the docstring's 'no row mixes today'")


def test_the_single_pair_flag_is_superseded():
    """The plan's `ImmigrantInputs.flag` cannot describe RA/HORS honestly (§6). It must be
    GONE, not merely unused: a surviving field is the one a future emitter reads."""
    row = resolve_immigrant_inputs(Geography.MTL_RMR)
    assert not hasattr(row, "flag")
    assert {f.name for f in dataclasses.fields(ImmigrantInputs)} == {
        "geography", "immigrant_headship", "ownership_ratio",
        "headship_provenance", "ratio_provenance", "source"}


# ================================================================= value validation + total join

def test_ratio_is_nonneg_finite_not_fraction():
    # codex r7-F8: the ownership ratio can validly exceed 1 (immigrants out-own non-immigrants).
    assert resolve_immigrant_inputs(Geography.QC_RMR).ownership_ratio >= 0.0
    assert ii._validate_ratio(1.2) == 1.2               # >1 accepted
    with pytest.raises(LoaderError):
        ii._validate_ratio(-0.1)                        # negative -> raise
    with pytest.raises(LoaderError):
        ii._validate_ratio(float("nan"))                # non-finite -> raise
    # and the ruled table really exercises the carve-out: THREE geographies measure above 1.
    # HORS_RMR joined at amendment #13 and its crossing is the ruling's own headline — at the
    # operand-aligned territory the ratio moves 0.9600 → 1.0248, so settled immigrants in
    # hors-RMR OUT-own non-immigrants rather than under-owning them, with BOTH suppression
    # envelope ends (1.0228, 1.0264) above 1.0 (a verdict inside its own uncertainty is not a
    # verdict). Asserted as an exact SET rather than a count: a carve-out that silently gained
    # a member would be a ratio inversion nobody was told about.
    above_one = [g.value for g in Geography if resolve_immigrant_inputs(g).ownership_ratio > 1.0]
    assert set(above_one) == {"MTL_ISLAND_RA06", "LAVAL_RA13", "HORS_RMR"}, above_one


def test_a_headship_outside_the_unit_interval_raises():
    """Headship is a FRACTION (households formed per person) — spec §4's [0,1] rule."""
    with pytest.raises(LoaderError, match=r"fraction outside \[0,1\]"):
        ImmigrantInputs(geography=Geography.MTL_RMR, immigrant_headship=1.4, ownership_ratio=1.0,
                        headship_provenance="cited", ratio_provenance="cited",
                        source="a source string long enough to be a citation")


@pytest.mark.parametrize("ratio,message", [(-0.1, "negative value"),
                                           (float("nan"), "non-finite value")])
def test_a_ratio_outside_nonneg_finite_raises_AT_CONSTRUCTION(ratio, message):
    """The WIRING, not the helper. `test_ratio_is_nonneg_finite_not_fraction` above calls
    `_validate_ratio` directly, which proves the rule and NOT that `__post_init__` applies it:
    measured 2026-08-14, deleting the `_validate_ratio(self.ownership_ratio)` line left the
    whole 540-test suite green, so the ratio was the one construction guard of five with no
    firing test while the class docstring advertised "units on BOTH numbers" at import.

    The carve-out stays intact — this asserts the two ways a ratio can be INVALID (negative,
    non-finite), never an upper bound; >1 is valid and two ruled geographies measure there."""
    with pytest.raises(LoaderError, match=message):
        ImmigrantInputs(geography=Geography.MTL_RMR, immigrant_headship=0.5, ownership_ratio=ratio,
                        headship_provenance="cited", ratio_provenance="cited",
                        source="a source string long enough to be a citation")


def test_an_uncited_row_raises():
    """Charter carry, applied to this table too: a constant without an anchor is a defect."""
    with pytest.raises(LoaderError, match="source"):
        ImmigrantInputs(geography=Geography.MTL_RMR, immigrant_headship=0.5, ownership_ratio=1.0,
                        headship_provenance="cited", ratio_provenance="cited", source="   ")


def test_every_modeled_geography_resolves_to_a_row_that_knows_itself():
    """§6: "every modeled member must resolve or the run raises". Each row also carries its
    OWN geography, asserted equal to the key it is filed under — a row filed under the wrong
    key would otherwise be floored against the wrong geography's living-alone share."""
    for geo in Geography:
        row = resolve_immigrant_inputs(geo)
        assert isinstance(row, ImmigrantInputs)
        assert row.geography is geo


def test_an_unresolved_modeled_member_raises_no_unstated_default(monkeypatch):
    """The join is TOTAL today, which makes its own raise dead code — and dead code is where
    an unstated default hides. Deleting one entry proves the branch is live and that the
    failure names the geography instead of returning a plausible default pair."""
    monkeypatch.delitem(ii._TABLE, Geography.HORS_RMR)
    with pytest.raises(LoaderError, match="HORS_RMR"):
        resolve_immigrant_inputs(Geography.HORS_RMR)


# ================================================================== the floor gate (coverage)

def test_the_floored_set_is_exactly_the_one_the_note_publishes_a_floor_for():
    """Coverage read off P8's own numeric triples, so flooring a geography the source does
    not publish (e.g. RA14 against MTL's 0.154) REDs, and so does quietly dropping one."""
    triples = _parse_floor_triples(_note_text())
    assert set(LIVING_ALONE_FLOOR) == set(triples) == {Geography.MTL_RMR, Geography.QC_RMR}
    for geo, (headship, floor) in triples.items():
        assert LIVING_ALONE_FLOOR[geo] == floor
        assert resolve_immigrant_inputs(geo).immigrant_headship == headship


def test_headship_clears_the_floor_where_the_source_publishes_one():
    """Each person living alone maintains exactly one household, so headship must EXCEED the
    settled living-alone share (§6 FLOOR GATE). 0.5259 > 0.154, 0.5054 > 0.164."""
    for geo, floor in LIVING_ALONE_FLOOR.items():
        assert resolve_immigrant_inputs(geo).immigrant_headship > floor


def test_a_headship_at_or_below_the_floor_is_a_defect_not_a_datum():
    """The gate fires on construction, so a bad edit lands at import rather than in a run."""
    for headship in (0.154, 0.10):
        with pytest.raises(LoaderError, match="living-alone floor"):
            ImmigrantInputs(geography=Geography.MTL_RMR, immigrant_headship=headship,
                            ownership_ratio=0.9634, headship_provenance="cited",
                            ratio_provenance="cited",
                            source="a source string long enough to be a citation")


def test_floor_coverage_is_TOTAL_over_the_modeled_enum_with_a_reason_each():
    """NOT-COVERED is RECORDED, never inferred from silence: every modeled geography is
    either floored or carries a written reason it is not. P8 searched all 63 geography
    members of 43-10-0060-01 — 0 at geoLevel 3, 0 carrying SGC 2466/2465."""
    assert set(LIVING_ALONE_FLOOR) | set(FLOOR_NOT_COVERED) == set(Geography)
    assert not set(LIVING_ALONE_FLOOR) & set(FLOOR_NOT_COVERED)
    for geo, reason in FLOOR_NOT_COVERED.items():
        assert len(reason.strip()) > 20, f"{geo.value}: reason too thin: {reason!r}"


def test_no_stand_in_floor_is_substituted_for_an_uncovered_geography():
    """The province figure (0.156, measured in P8 §5) is the stand-in a hurried edit reaches
    for. Substituting it would be a geography transport the ruling does not make."""
    assert 0.156 not in set(LIVING_ALONE_FLOOR.values())
    assert set(LIVING_ALONE_FLOOR.values()) == {0.154, 0.164}


def test_the_ra_proxies_reason_does_not_claim_a_floor_it_never_ran():
    """A borrowed value clears its PARENT's floor at the PARENT. Saying it clears one at
    Lanaudière would claim a measurement 43-10-0060-01 does not publish there."""
    for geo in (Geography.LANAUDIERE_RA14_PROXY, Geography.LAURENTIDES_RA15_PROXY,
                Geography.MONTEREGIE_RA16_PROXY):
        reason = FLOOR_NOT_COVERED[geo]
        assert "MTL_RMR" in reason and "borrow" in reason.lower()


# ============================================================== I2 decomposition + its gates

def test_p_resident_subtracts_surviving_arrivals():
    """EXACT, not approx (the decomposition fixture's exact-oracle law): 10_000 − 300 − 200
    is exactly representable, so any drift is a wiring change, not float noise."""
    assert p_resident(p_isq=10_000.0, surviving_arrivals=[300.0, 200.0]) == 9_500.0
    assert p_resident(p_isq=10_000.0, surviving_arrivals=[]) == 10_000.0   # no arrivals: identity


def test_p_resident_nonnegativity_per_cell():
    # codex r7-F3: arrivals exceeding P_ISQ in a cell = CalibrationError BEFORE any consumer.
    assert assert_p_resident_nonneg(0.0, ctx="cell") == 0.0        # zero ok
    with pytest.raises(CalibrationError, match="negative|nonneg"):
        assert_p_resident_nonneg(-5.0, ctx="MTL/2035/ref/age40")


def test_p_resident_nonneg_refuses_a_NON_FINITE_cell():
    """ADDED beyond the plan's body, at a measured defect in it: `nan < 0.0` is False, so the
    plan's guard PASSES a NaN cell straight into native formation, where `max(0, ·)` drops it
    silently. A guard that greens on the one value it cannot compare is the cheap all-clear."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(CalibrationError, match="finite"):
            assert_p_resident_nonneg(bad, ctx="MTL/2035/ref/age40")


def test_i2_identity_gate_passes_on_consistent_and_fails_on_mutation():
    assert_i2_identity(native_input=9_500.0, p_isq=10_000.0, surviving_arrivals=[300.0, 200.0])
    with pytest.raises(CalibrationError, match="I2"):
        assert_i2_identity(native_input=10_000.0, p_isq=10_000.0, surviving_arrivals=[300.0, 200.0])


def test_i2_identity_refuses_NON_FINITE_operands():
    """Same class on the other gate: `abs(nan − expected) > tol` is False, so a NaN operand
    reads as a satisfied identity — the double-entry check would certify a NaN pipeline."""
    with pytest.raises(CalibrationError, match="finite"):
        assert_i2_identity(native_input=float("nan"), p_isq=10_000.0, surviving_arrivals=[500.0])
    with pytest.raises(CalibrationError, match="finite"):
        assert_i2_identity(native_input=9_500.0, p_isq=float("nan"), surviving_arrivals=[500.0])
    with pytest.raises(CalibrationError, match="finite"):
        assert_i2_identity(native_input=9_500.0, p_isq=10_000.0, surviving_arrivals=[float("nan")])


def test_the_i2_gate_is_a_DIFFERENT_symbol_from_the_cohort_reconciliation_gate():
    """Measured distinct at the run-12 fold and kept distinct here: `check_reconciliation` is
    I1's decade retention band (supply side, central run only, ruling O); `assert_i2_identity`
    is I2's demand-side double-entry check. Conflating them would put a demand mutation under
    a gate that only ever measured mortality."""
    from demoflow.cohort import gates

    assert hasattr(gates, "check_reconciliation")
    assert not hasattr(gates, "assert_i2_identity")
    import demoflow.demand.i2 as i2_mod
    assert not hasattr(i2_mod, "check_reconciliation")
