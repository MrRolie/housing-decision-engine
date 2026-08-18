"""P11 — the OPERAND-ALIGNED ownership curve for HORS_RMR (reverses spec §6 amendment #12(B)).

WHAT IS BEING GATED. `census.derive_ownership_from_csv` measures HORS_RMR's ownership
propensity over the Québec province NET of the six wholly-Québec CMAs — a residual that
INCLUDES the Québec side of Ottawa-Gatineau, because 98-10-0231-01 parents that CMA to
Ontario and publishes no Québec-part row. The flows that rate multiplies come from ISQ's own
hors-RMR row, which EXCLUDES it. Amendment #12(B) cleared the ownership leg from correction
on the ground that a BAND-UNIFORM relative scaling of ρ cancels exactly in ED; probe P10
measured that premise FALSE (spread 1.202 pp across the four model bands, all same-signed,
and adversarially arranged — the most contaminated band is the one D_native is built from,
the least is the one S rides). The seat reversed #12(B) and ORDERED this extraction.

THE TESTS' OWN ORACLE. Every expected count and rate below is TEST-OWNED — re-declared here
rather than imported from `demoflow.loaders.hors_aligned`, following this suite's standing
convention (`test_census_ownership.py`'s TEST-OWNED oracle block, `living_arrangement._QC_CMAS`
vs `census._QC_CMAS`): a gate that imports the constant it is checking cannot catch the
constant moving. The band constituents, the 16 Québec-part SGC codes and the published cell
literals are therefore typed here a second time, and cross-gated against the module.

WHAT THIS FILE MAKES NO NETWORK CALL FOR. Nothing here fetches. The external published cells
are CITED literals retrieved live and recorded in `_PUBLISHED_CELLS`; a gate that re-fetched
would be an availability check, not an anchor.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census, hors_aligned, pins
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256

DEMOFLOW = Path(__file__).resolve().parent.parent
PROBES = DEMOFLOW / "probes"

# --- TEST-OWNED oracle -----------------------------------------------------------------
# The CD/CSD cube's OWN age members per model band. 98-10-0232-01 publishes a COARSER age
# axis than 98-10-0231-01 (9 members against 15): the band EDGES are the model's, the
# constituents are whatever each cube publishes.
_CD_BANDS = {
    "25-54": ("25 to 34 years", "35 to 44 years", "45 to 54 years"),
    "55-64": ("55 to 64 years",),
    "65-74": ("65 to 74 years",),
    "75+": ("75 to 84 years", "85 years and over"),
}
_BAND_ORDER = ("25-54", "55-64", "65-74", "75+")
# The band EDGES, typed here a second time rather than read off `CD_BAND_SPEC`: P11-17 gates the
# consumer lookup's band RESOLUTION, and a lookup gate that takes its own edges from the spec it
# is checking cannot catch the spec moving (the same argument the oracle block opens with).
_BAND_EDGES = {"25-54": (25, 54), "55-64": (55, 64), "65-74": (65, 74), "75+": (75, 200)}
_ALL_AGES = "Total - Age of primary household maintainer"
_TENURE_TOTAL = "Total - Tenure"
_TENURE_OWNER = "Owner"

# The Québec-side census subdivisions of the Ottawa-Gatineau CMA, by SGC code. P10 resolved
# this membership from 98-10-0003-01's own geography-dimension children of CMA member 594 —
# 25 children closing EXACTLY on the CMA's population (1,488,307), 16 Québec-side by SGC
# prefix AND by census-tree ancestry, the two agreeing on all 25.
_QC_PART_CSDS = ("2480050", "2480055", "2480060", "2480065", "2480085", "2480140", "2480145",
                 "2481017", "2482005", "2482010", "2482015", "2482020", "2482025", "2482030",
                 "2482035", "2483005")
_PROVINCE_CODE = "24"

# The SHIPPED residual, band by band — (owner, total) households. Recomputed here from the
# committed P2 extract by the test's own path, so these literals are a cross-check on the
# module's reuse of `census`, not the source of truth.
_SHIPPED_COUNTS = {
    "25-54": (355_560, 522_535),
    "55-64": (205_915, 275_450),
    "65-74": (175_595, 240_310),
    "75+": (99_915, 153_430),
}
_SHIPPED_ALL_AGES = (845_355, 1_223_585)

# The ALIGNED curve — measured. Published-counts-only subtraction (subtract LEAST) is the
# served value; `_ALIGNED_BOUND` is the same subtraction with every withheld field at its
# upper bound (subtract MOST). Only 75+ carries withheld cells, so only 75+ moves.
_ALIGNED_RATES = {
    "25-54": 0.6901488081776652,
    "55-64": 0.7499130078804626,
    "65-74": 0.732921103858926,
    "75+": 0.6526588753507868,
}
_ALIGNED_BOUND = {
    "25-54": 0.6901488081776652,
    "55-64": 0.7499130078804626,
    "65-74": 0.732921103858926,
    "75+": 0.6525956721031873,
}
# The ENVELOPE — the OFF-DIAGONAL corners of the feasible withheld-cell rectangle, which are
# the rate's actual extremes. `_ALIGNED_RATES` and `_ALIGNED_BOUND` are the two SUBTRACTION
# corners (least/most on BOTH fields) and do NOT bracket the rate: rate = (S_o-s_o)/(S_t-s_t)
# falls in subtracted owners and rises in subtracted households, so the maximum takes the least
# owner against the most household and the minimum takes the reverse. Both 75+ literals are
# typed rather than asserted as a relation, because a TRANSPOSED pair is still an interval, is
# still feasible-looking, and is merely narrower — the exact defect this oracle exists to catch
# (measured at run 25 review: the true max +0.251% sat ABOVE the published upper end +0.223%).
_ALIGNED_ENVELOPE_LOW = dict(_ALIGNED_RATES, **{"75+": 0.6524102163333452})
_ALIGNED_ENVELOPE_HIGH = dict(_ALIGNED_RATES, **{"75+": 0.652844401805067})
# The band spread, in percentage points, at the four corners of the feasible box. The figure
# #12(B)'s band-uniformity premise is refuted by — so what matters is that the NARROWEST is
# still strictly positive and still adversarially arranged.
_BAND_SPREAD_PP = {
    "at_served_corner": 1.2024094264527192,
    "at_subtract_most_corner": 1.2121149504272988,
    "narrowest_feasible": 1.1739198864635234,
    "widest_feasible": 1.2405936360769714,
}
_ALIGNED_ALL_AGES = 0.6972282443993753
# The 16 subdivisions' all-ages counts, which every one of them publishes in full.
_CSD_ALL_AGES_SUBTRACTION = (97_630, 151_160)

# --- the SUPPRESSION FOOTPRINT, by ADDRESS ---------------------------------------------
# 13 withheld cells, all in the 75+ band, at 7 of the 16 subdivisions. The COUNT alone is not
# the footprint: a 13-cell footprint that had moved to a different set of subdivisions would
# satisfy a count-only gate while the bound's own denominators changed underneath it. The
# subdivisions are small and rural but NOT a size prefix — 2482010 (380 households, 7th
# smallest) publishes every cell while 2480140 (495, 8th) withholds one — so "the smallest N"
# cannot stand in for the list either. Composition drift with the count held is exactly the
# error run 24 task 1 caught on the settled side, whose withheld 7 is a DIFFERENT set of
# subdivisions from this one.
_WITHHELD_ADDRESSES = frozenset({
    ("2480055", "85 years and over", _TENURE_OWNER),
    ("2480055", "85 years and over", _TENURE_TOTAL),
    ("2480060", "85 years and over", _TENURE_OWNER),
    ("2480060", "85 years and over", _TENURE_TOTAL),
    ("2480065", "75 to 84 years", _TENURE_OWNER),
    ("2480065", "85 years and over", _TENURE_OWNER),
    ("2480065", "85 years and over", _TENURE_TOTAL),
    ("2480085", "85 years and over", _TENURE_OWNER),
    ("2480085", "85 years and over", _TENURE_TOTAL),
    ("2480140", "85 years and over", _TENURE_OWNER),
    ("2480145", "85 years and over", _TENURE_OWNER),
    ("2480145", "85 years and over", _TENURE_TOTAL),
    ("2483005", "85 years and over", _TENURE_OWNER),
})
_WITHHELD_TOTAL = 13
# Typed SEPARATELY from the address list rather than derived from it, on this file's standing
# oracle convention. It is not redundant at the moment it matters: on a RE-PIN, the extract and
# the address list move together, and this independently-typed figure is what reds if the
# subdivision count moved with them — which is the narrative figure the module docstring states.
_WITHHELD_CSD_COUNT = 7
# The two subdivisions where the 75+ band withholds ONE field of the pair and publishes the
# other. This is what makes field-wise bounding load-bearing rather than hypothetical: at these
# two, dropping the published field would net a territory's households out of one denominator
# and its owners out of another. At the other five, both fields of the band are withheld.
_HALF_PAIR_CSDS = ("2480140", "2483005")
# Fields whose unpublished remainder is already ZERO or negative in the COMMITTED extract, so
# the withheld cell is bounded AT zero: 2480055/Owner (-5), 2480060/Owner (0),
# 2480085/Owner (-5), 2480140/Owner (0). A property of the pinned extract, not of the code.
_EMPTY_COMPLEMENT_BASELINE = 4

# --- EXTERNAL PUBLISHED ANCHORS --------------------------------------------------------
# Retrieved LIVE from the WDS and typed here as CITED literals. THE PROPERTY these have that
# no other gate in this file has: their expected values were never read from anything this
# repo commits, so a hand-cut extract plus a hand-edited pin cannot satisfy them.
_WDS_CITATION = (
    'Statistics Canada. Table 98-10-0232-01, "Age of primary household maintainer by tenure: '
    "Canada, provinces and territories, census divisions and census subdivisions\", 2021 "
    "Census, released 2022-09-23T12:50. Cells retrieved 2026-08-15 from "
    "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods "
    "(productId 98100232, latestN=1, every point refPer 2021-01-01). Member ids resolved "
    "from live getCubeMetadata by exact member name — Geography: 'Quebec'=884 (geoLevel 2, "
    "code 24), 'Gatineau'=1944 (geoLevel 5, code 2481017); Structural type of dwelling: "
    "'Total - Structural type of dwelling'=1; Household type including census family "
    "structure: 'Total - Household type including family structure'=1; Statistics: 'Number "
    "of private households'=1; Age of primary household maintainer: 'Total - Age of primary "
    "household maintainer'=1, '75 to 84 years'=8, '85 years and over'=9; Tenure: 'Total - "
    "Tenure'=1, 'Owner'=2. Dimension positions 1..6 in that order; coordinates are 10 slots "
    "with four trailing zeros."
)
# (SGC code, age member, tenure) -> published count.
_PUBLISHED_CELLS = {
    # Quebec province, coordinates 884.1.1.1.{1,8,9}.{1,2}.0.0.0.0
    (_PROVINCE_CODE, _ALL_AGES, _TENURE_TOTAL): 3_749_035,
    (_PROVINCE_CODE, _ALL_AGES, _TENURE_OWNER): 2_245_600,
    (_PROVINCE_CODE, "75 to 84 years", _TENURE_TOTAL): 336_170,
    (_PROVINCE_CODE, "75 to 84 years", _TENURE_OWNER): 202_825,
    (_PROVINCE_CODE, "85 years and over", _TENURE_TOTAL): 103_640,
    (_PROVINCE_CODE, "85 years and over", _TENURE_OWNER): 55_745,
    # CSD Gatineau (2481017) — the contaminant's whole mass, coordinates 1944.1.1.1.*.{1,2}
    ("2481017", _ALL_AGES, _TENURE_TOTAL): 126_480,
    ("2481017", _ALL_AGES, _TENURE_OWNER): 76_090,
    ("2481017", "75 to 84 years", _TENURE_TOTAL): 8_640,
    ("2481017", "75 to 84 years", _TENURE_OWNER): 5_345,
    ("2481017", "85 years and over", _TENURE_TOTAL): 2_140,
    ("2481017", "85 years and over", _TENURE_OWNER): 1_180,
}
# The SIBLING cube's published province cell — 98-10-0231-01's own all-ages row, already
# cited in `test_census_ownership.py`. One universe at two grains: the pair must be
# BIT-IDENTICAL here, which is the check that says these two cubes mean the same thing.
_SIBLING_PROVINCE_ALL_AGES = (2_245_600, 3_749_035)     # (owner, total)


# --- helpers ----------------------------------------------------------------------------

def _artifact() -> dict:
    return json.loads((DATA_DIR / hors_aligned.ARTIFACT).read_text(encoding="utf-8"))


def _extract() -> dict:
    return json.loads((DATA_DIR / hors_aligned.EXTRACT).read_text(encoding="utf-8"))


def _extract_cells() -> dict:
    """{(geography_code, age_member, tenure): value or None} from the committed extract."""
    return {(c["geography_code"], c["age_member"], c["tenure"]): c["value"]
            for c in _extract()["cells"]}


def _independent_shipped_counts() -> dict:
    """The shipped residual, recomputed by the TEST from the committed P2 extract."""
    cube = census._read_totals_cube(DATA_DIR / census.CENSUS_EXTRACT)
    out = {}
    for label, _lo, _hi, members in census._AGE_BAND_SPEC:
        owner = total = 0
        for geo, sign in [(census._PROVINCE, 1)] + [(c, -1) for c in census._QC_CMAS]:
            o, t = census._band_counts(cube, geo, members, "test")
            owner += sign * o
            total += sign * t
        out[label] = (owner, total)
    return out


# --- P11-1 --------------------------------------------------------------------------------

def test_p11_1_band_lattice_is_the_models_own_and_the_two_cubes_partition_it_alike():
    """The aligned curve must live on `census._AGE_BAND_SPEC`'s bands, not on a lookalike.

    The two cubes publish DIFFERENT age granularities of the same partition (15 members vs 9),
    so the constituents cannot be shared — only the EDGES can. A band spec that drifted an
    edge would produce a perfectly plausible curve measured over a different age domain.
    """
    census_edges = {label: (lo, hi) for label, lo, hi, _ in census._AGE_BAND_SPEC}
    module_edges = {label: (lo, hi) for label, lo, hi, _ in hors_aligned.CD_BAND_SPEC}
    assert module_edges == census_edges, (
        "the aligned band lattice is not the model's own — the curve would be measured over "
        f"different age bands than `ownership_rate` looks up: {module_edges} vs {census_edges}")
    assert {label: members for label, _lo, _hi, members in hors_aligned.CD_BAND_SPEC} == _CD_BANDS
    # Ordered, contiguous, and starting at the ownership lattice's floor of 25 — the sub-floor
    # question is NOT this task's (spec §7: age-resolved headship first, then the floor).
    edges = [module_edges[label] for label in _BAND_ORDER]
    assert edges[0][0] == 25, "the aligned curve must not extend below the shipped floor of 25"
    for (_lo, hi), (nlo, _nhi) in zip(edges, edges[1:]):
        assert nlo == hi + 1, f"band lattice is not contiguous at {hi}->{nlo}"


def test_p11_1b_the_pinned_territory_is_the_membership_p10_resolved():
    """The module's OWN territory constant, cross-gated against the test-owned tuple.

    Its own boundary, separate from the extract's lattice gate: a dropped code here would make
    the derivation ask for 15 subdivisions, which the extract-lattice check would then report
    as an EXTRACT defect — sending the reader to the pull instead of to the constant that
    actually moved.
    """
    assert hors_aligned.QC_PART_CSDS == _QC_PART_CSDS, (
        "the pinned Québec-part membership drifted from the territory P10 resolved")
    assert hors_aligned.SOURCE_GEOGRAPHIES == (_PROVINCE_CODE,) + _QC_PART_CSDS
    assert hors_aligned.ALIGNED_GEOGRAPHY is Geography.HORS_RMR


# --- P11-2 --------------------------------------------------------------------------------

def test_p11_2_the_extract_is_pinned_and_the_committed_file_matches_its_pin():
    assert hors_aligned.EXTRACT in WORKBOOK_SHA256, (
        f"{hors_aligned.EXTRACT} carries no sha256 pin — the PIT chain (live response -> "
        "committed extract -> derived rates) is unenforced")
    digest = hashlib.sha256((DATA_DIR / hors_aligned.EXTRACT).read_bytes()).hexdigest()
    assert digest == WORKBOOK_SHA256[hors_aligned.EXTRACT]


# --- P11-3 --------------------------------------------------------------------------------

def test_p11_3_the_extract_carries_exactly_the_declared_request_lattice():
    """17 geographies x 8 age members x 2 tenures = 272 addresses, no more and no fewer.

    An extract with a MISSING address is a hole the derivation would net around; an extract
    with an EXTRA one is a coordinate nobody asked for. Both are refused here rather than
    absorbed into a plausible rate.
    """
    cells = _extract_cells()
    geos = (_PROVINCE_CODE,) + _QC_PART_CSDS
    ages = (_ALL_AGES,) + tuple(m for band in _BAND_ORDER for m in _CD_BANDS[band])
    expected = {(g, a, t) for g in geos for a in ages for t in (_TENURE_TOTAL, _TENURE_OWNER)}
    assert len(ages) == 8 and len(geos) == 17 and len(expected) == 272
    assert set(cells) == expected, (
        f"extract lattice drifted: {len(set(cells) - expected)} unrequested, "
        f"{len(expected - set(cells))} missing")


# --- P11-4 --------------------------------------------------------------------------------

def test_p11_4_suppression_is_scoped_and_the_bounds_own_denominator_is_published():
    """StatCan withholds small counts — but only where the declared scope says it may.

    A withheld PROVINCE cell or a withheld CSD ALL-AGES cell is not suppression this
    derivation can bound: the all-ages row is the denominator of the unpublished-remainder
    bound, and an interval with no upper end is not one. Those refuse; CSD BAND cells are
    recorded with a null value and bounded.
    """
    cells = _extract_cells()
    withheld = [k for k, v in cells.items() if v is None]
    assert len(withheld) == _WITHHELD_TOTAL, f"withheld-cell count moved: {len(withheld)}"
    for code, age, _tenure in withheld:
        assert code != _PROVINCE_CODE, "a withheld province cell is outside the declared scope"
        assert age != _ALL_AGES, (
            f"{code} withholds its all-ages row — the unpublished remainder that bounds its "
            "withheld bands cannot be computed")
        assert age in _CD_BANDS["75+"], (
            f"a band cell outside 75+ is withheld ({code}/{age}) — the suppression footprint "
            "moved and the published envelope no longer describes it")


def test_p11_4c_the_suppression_footprint_is_pinned_by_ADDRESS_not_merely_by_count():
    """WHICH cells are withheld, against the test-owned address list.

    The count and the 75+ scoping above are both satisfied by a 13-cell footprint sitting at a
    DIFFERENT set of subdivisions — and the set is what the bound depends on, because each
    withheld field is bounded by its OWN subdivision's unpublished remainder. Composition drift
    with the count held is the error class run 24 task 1 caught on the settled side (whose
    withheld 7 is a different set of subdivisions from this one), so it is gated here rather
    than described in a comment.

    The extract's sha256 pin already makes silent drift impossible; what this gate is for is the
    RE-PIN, where the pin moves by intent and only an address-level oracle can say whether the
    suppression footprint moved with it.
    """
    cells = _extract_cells()
    withheld = frozenset(k for k, v in cells.items() if v is None)
    assert withheld == _WITHHELD_ADDRESSES, (
        "the suppression footprint moved: "
        f"{sorted(withheld - _WITHHELD_ADDRESSES)} newly withheld, "
        f"{sorted(_WITHHELD_ADDRESSES - withheld)} newly published")
    codes = {code for code, _age, _tenure in withheld}
    assert len(codes) == _WITHHELD_CSD_COUNT, (
        f"withheld cells sit at {len(codes)} of the 16 subdivisions, not "
        f"{_WITHHELD_CSD_COUNT} — the narrative figure and the data have parted")

    # FIELD-WISE bounding is load-bearing, not hypothetical: at these two subdivisions the 75+
    # band withholds one field of the pair and PUBLISHES the other, so a per-address (rather
    # than per-field) rule would discard a published count.
    half_pairs = tuple(sorted(
        code for code in codes
        if len({tenure for c, age, tenure in withheld
                if c == code and age in _CD_BANDS["75+"]}) == 1))
    assert half_pairs == _HALF_PAIR_CSDS, (
        f"the half-pair subdivisions moved: {half_pairs} vs {_HALF_PAIR_CSDS} — field-wise "
        "bounding is only load-bearing while some subdivision publishes one field of a pair")


@pytest.mark.parametrize("code,age,expected", [
    (_PROVINCE_CODE, _ALL_AGES, "the province .* cell is unpublished"),
    ("2481017", _ALL_AGES, "subdivision 2481017 withholds its all-ages"),
])
def test_p11_4b_suppression_outside_the_declared_scope_REFUSES(tmp_path, code, age, expected):
    """The refusal PATH, exercised — not merely present, and each on its OWN message.

    A guard whose failing branch no test ever reaches is a guard nobody has seen fire. Both
    out-of-scope suppressions are planted here: a withheld province cell (outside the scope
    entirely, where an outage would read as a publication rule) and a withheld CSD all-ages
    cell (the denominator of the unpublished-remainder bound — an interval with no upper end
    is not one).

    The match patterns DISCRIMINATE, they do not merely confirm a raise. Measured (mutation
    M14): with the province branch disabled, the CSD branch caught the same input and reported
    "subdivision 24 withholds its all-ages row" — a refusal for the right reason under the
    wrong name, which sends the reader to the subdivision list for a province-row fault. A
    loose `match=` would have passed that mutant green. Same lesson census.py records at
    `_raise_for_empty_slice`: diagnosis order follows the filter order.
    """
    payload = _extract()
    for cell in payload["cells"]:
        if cell["geography_code"] == code and cell["age_member"] == age:
            cell["value"] = None
            # The MEASURED withheld shape, not an invented third spelling: every one of the 13
            # withheld cells in the committed extract carries `status: FAILED` with a null
            # `status_code` and no data point (there is no SUCCESS-with-empty-points cell).
            cell["status"] = "FAILED"
            cell["status_code"] = None
    bad = tmp_path / hors_aligned.EXTRACT
    bad.write_text(json.dumps(payload), encoding="utf-8")
    # `match=expected` — the PARAMETRIZED discriminating pattern, not a shared alternation.
    # Re-measured at run 25: with `match="unpublished|withholds"` this test passed mutation M14
    # green, because the CSD branch raised "subdivision 24 withholds its all-ages row" and the
    # alternation accepted it. The docstring above described the discrimination; the assertion
    # did not implement it, and `expected` was bound and never read.
    with pytest.raises(LoaderError, match=expected):
        hors_aligned.derive_aligned_ownership(
            DATA_DIR / census.CENSUS_EXTRACT, bad, verify_extract_pin=False)


# --- P11-5 --------------------------------------------------------------------------------

def test_p11_5_committed_artifact_equals_a_fresh_derivation():
    """The no-drift gate: the shipped artifact IS what the derivation emits, or it is a
    hand-authored rate table wearing a provenance block (steering ruling B)."""
    fresh = hors_aligned.derive_aligned_ownership(
        DATA_DIR / census.CENSUS_EXTRACT, DATA_DIR / hors_aligned.EXTRACT)
    assert _artifact() == fresh


# --- P11-6 --------------------------------------------------------------------------------

def test_p11_6_the_generator_reproduces_the_committed_artifact_byte_for_byte(tmp_path):
    """Determinism, at the BYTES rather than at the parsed payload: band order comes from the
    spec tuple and geography order from the Geography enum, never from a set iteration whose
    order is per-process randomized."""
    out = tmp_path / hors_aligned.ARTIFACT
    result = subprocess.run(
        [sys.executable, str(DEMOFLOW / "scripts" / "gen_hors_aligned.py"), "--out", str(out)],
        capture_output=True, text=True, cwd=DEMOFLOW)
    assert result.returncode == 0, result.stderr
    assert out.read_bytes() == (DATA_DIR / hors_aligned.ARTIFACT).read_bytes()


# --- P11-7 --------------------------------------------------------------------------------

def test_p11_7_the_aligned_curve_reproduces_the_measured_contamination():
    """The rates themselves, against the TEST-OWNED oracle, at both consumer surfaces.

    These are the five figures the seat ruling rests on. `pytest.approx(rel=1e-12)` rather
    than a round-N form: a rounded comparison would be satisfied by a curve measured over a
    neighbouring territory.
    """
    fresh = hors_aligned.derive_aligned_ownership(
        DATA_DIR / census.CENSUS_EXTRACT, DATA_DIR / hors_aligned.EXTRACT)["rates"]
    loaded = hors_aligned.load_aligned_ownership_rates()
    for band in _BAND_ORDER:
        assert fresh[Geography.HORS_RMR.value][band] == pytest.approx(
            _ALIGNED_RATES[band], rel=1e-12), f"aligned {band} moved"
        assert loaded[Geography.HORS_RMR.value][band] == pytest.approx(
            _ALIGNED_RATES[band], rel=1e-12)

    # Every band moves in the SAME direction and by MORE than nothing — the finding the
    # reversal rests on. A band that stopped moving would mean the subtraction went missing.
    shipped = _independent_shipped_counts()
    for band in _BAND_ORDER:
        owner, total = shipped[band]
        assert (owner, total) == _SHIPPED_COUNTS[band], f"shipped {band} counts drifted"
        assert loaded[Geography.HORS_RMR.value][band] > owner / total, (
            f"{band} aligned {loaded[Geography.HORS_RMR.value][band]} does not exceed the "
            f"shipped {owner / total} — every measured band moved up")


def test_p11_7b_the_all_ages_evidence_row_reproduces_its_oracle():
    """The all-ages row — EVIDENCE, never served, and until now declared but never asserted.

    `_SHIPPED_ALL_AGES`, `_CSD_ALL_AGES_SUBTRACTION` and `_ALIGNED_ALL_AGES` were typed into
    this file's oracle block and referenced nowhere, so the +0.918% figure — the one P10's
    table publishes, the one the artifact's `all_ages` block carries, and the one the ruled
    immigrant cube independently corroborates — was the only headline number in this deliverable
    with no gate under it. A declared oracle that nothing compares against is not a check.

    Subtraction recomputed here from the extract's own all-ages cells rather than read from the
    provenance block, so this is a cross-check on the derivation and not a restatement of it.
    """
    cells = _extract_cells()
    sub_owner = sum(cells[(code, _ALL_AGES, _TENURE_OWNER)] for code in _QC_PART_CSDS)
    sub_total = sum(cells[(code, _ALL_AGES, _TENURE_TOTAL)] for code in _QC_PART_CSDS)
    assert (sub_owner, sub_total) == _CSD_ALL_AGES_SUBTRACTION, (
        f"the 16 subdivisions' all-ages subtraction moved: {(sub_owner, sub_total)}")

    cube = census._read_totals_cube(DATA_DIR / census.CENSUS_EXTRACT)
    shipped_owner, shipped_total = census.net_of_qc_cmas(cube, (_ALL_AGES,), "test")
    assert (shipped_owner, shipped_total) == _SHIPPED_ALL_AGES, (
        f"the shipped all-ages residual moved: {(shipped_owner, shipped_total)}")

    aligned = (shipped_owner - sub_owner) / (shipped_total - sub_total)
    assert aligned == pytest.approx(_ALIGNED_ALL_AGES, rel=1e-12)

    row = _artifact()["_provenance"]["all_ages"]
    assert (row["shipped_owner_households"], row["shipped_households"]) == _SHIPPED_ALL_AGES
    assert row["aligned_rate"] == pytest.approx(_ALIGNED_ALL_AGES, rel=1e-12)
    assert row["relative_delta_pct"] == pytest.approx(0.9183149592076177, rel=1e-12), (
        "the all-ages contamination is not the +0.918% P10 measured and the reversal cites")


# --- P11-8 --------------------------------------------------------------------------------

def test_p11_8_the_join_re_points_hors_rmr_and_nothing_else():
    """The SCOPE FENCE, executable. Every other geography's ownership territory was never
    contaminated; if any other row re-points, that is a FINDING, not a rounding artifact."""
    fresh = hors_aligned.derive_aligned_ownership(
        DATA_DIR / census.CENSUS_EXTRACT, DATA_DIR / hors_aligned.EXTRACT)
    # Both the committed bytes and the code path, for the reason P11-11 records: a join built
    # wrong would otherwise red only the no-drift gate.
    for source, payload in (("committed artifact", _artifact()),
                            ("fresh derivation", fresh),
                            ("load accessor", {"join": hors_aligned.load_aligned_ownership_join(),
                                               "rates": hors_aligned.load_aligned_ownership_rates()})):
        join = payload["join"]
        assert set(join) == {g.value for g in Geography}, (
            f"{source}: the join does not name every modeled geography exactly once: "
            f"{sorted(join)}")
        aligned = [g for g, row in join.items() if row["reads"] == "operand_aligned"]
        assert aligned == [Geography.HORS_RMR.value], (
            f"{source}: exactly one row may read the operand-aligned curve; these do: {aligned}")
        for geo, row in join.items():
            expected = ("operand_aligned" if geo == Geography.HORS_RMR.value else "shipped")
            assert row["reads"] == expected, f"{source}: {geo}"
            assert row["artifact"] == (hors_aligned.ARTIFACT if expected == "operand_aligned"
                                       else census.OWNERSHIP_ARTIFACT)
            assert row["why"].strip(), f"{source}: {geo}: the join states no reason"
        # The rate table carries ONLY the re-pointed row: a second geography here would be a
        # second curve served under a provenance block that describes one territory.
        assert set(payload["rates"]) == {Geography.HORS_RMR.value}, source

    # And the lookup REFUSES a geography this surface does not re-point, rather than quietly
    # handing back something plausible from the wrong territory.
    with pytest.raises(LoaderError, match="not re-pointed"):
        hors_aligned.aligned_ownership_rate(
            hors_aligned.load_aligned_ownership_rates(), Geography.MTL_RMR, age=40)


def test_p11_8b_the_qc_part_csds_are_disjoint_from_the_six_netted_cmas():
    """The 'changes ONLY HORS_RMR' proof at the SOURCE, not at the output.

    If any Québec-part CSD of Ottawa-Gatineau also sat inside one of the six wholly-Québec
    CMAs, subtracting it would net that territory out TWICE and would move a CMA's own
    denotation. Recorded live by the puller from 98-10-0003-01's own membership.
    """
    membership = _extract()["_pull"]["membership"]
    assert membership["shared_csd_codes"] == [], (
        f"a Québec-part CSD is also a constituent of a netted CMA: "
        f"{membership['shared_csd_codes']} — the subtraction would double-net")
    assert sorted(membership["netted_cmas_checked"]) == sorted(census._QC_CMAS), (
        "the disjointness check did not cover exactly the six netted CMAs")


# --- P11-9 --------------------------------------------------------------------------------

def test_p11_9_the_province_row_matches_the_published_cell_of_BOTH_cubes():
    """ANCHOR 1 — external, and a universe check in the same assertion.

    Cited: `_WDS_CITATION`. 98-10-0232-01's Québec province all-ages row must BE StatCan's
    published 3,749,035 / 2,245,600 — which is also 98-10-0231-01's own published province
    cell, already cited in `test_census_ownership.py`. Two cubes, one universe: if the pair
    disagreed here, the CSD counts subtracted from the 0231 residual would be measured in a
    different universe than the residual itself.
    """
    cells = _extract_cells()
    for tenure in (_TENURE_TOTAL, _TENURE_OWNER):
        assert cells[(_PROVINCE_CODE, _ALL_AGES, tenure)] == \
            _PUBLISHED_CELLS[(_PROVINCE_CODE, _ALL_AGES, tenure)], (
            f"the committed extract's province {tenure} cell is not StatCan's published "
            f"value ({_WDS_CITATION})")
    owner = cells[(_PROVINCE_CODE, _ALL_AGES, _TENURE_OWNER)]
    total = cells[(_PROVINCE_CODE, _ALL_AGES, _TENURE_TOTAL)]
    assert (owner, total) == _SIBLING_PROVINCE_ALL_AGES, (
        "98-10-0232-01's province row is not bit-identical to 98-10-0231-01's — the two "
        "cubes are not one universe at two grains")
    # And the derivation says so in its own provenance, measured rather than asserted here.
    assert _artifact()["_provenance"]["universe"]["province_all_ages"] == {
        "households": total, "owner_households": owner, "bit_identical_across_the_pair": True}


def test_p11_9b_a_province_row_that_is_not_bit_identical_REFUSES(tmp_path):
    """The universe guard's FAILING branch, exercised.

    Moved by ONE round-to-5 step — the smallest drift the cubes could legitimately show
    anywhere else, and the largest that a reader might wave through. If the two province rows
    can differ at all, subtracting cells of one cube from a residual of the other is a metric
    transport rather than arithmetic, so 5 must refuse exactly as 5,000 would.
    """
    payload = _extract()
    for cell in payload["cells"]:
        if cell["geography_code"] == _PROVINCE_CODE and cell["age_member"] == _ALL_AGES \
                and cell["tenure"] == _TENURE_OWNER:
            cell["value"] += 5
    bad = tmp_path / hors_aligned.EXTRACT
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="not one universe at two grains"):
        hors_aligned.derive_aligned_ownership(
            DATA_DIR / census.CENSUS_EXTRACT, bad, verify_extract_pin=False)


# --- P11-10 -------------------------------------------------------------------------------

def test_p11_10_the_contaminants_own_cells_match_the_published_ones():
    """ANCHOR 2 — CSD Gatineau (2481017), which carries the contaminant's whole mass.

    Cited: `_WDS_CITATION`. This is the one subdivision whose removal moves the curve
    materially, so an extract that got IT wrong would move every band while every rate stayed
    a plausible fraction.
    """
    cells = _extract_cells()
    for (code, age, tenure), published in _PUBLISHED_CELLS.items():
        if code != "2481017":
            continue
        assert cells[(code, age, tenure)] == published, (
            f"CSD Gatineau {age}/{tenure} is {cells[(code, age, tenure)]}, StatCan publishes "
            f"{published} ({_WDS_CITATION})")
    # Carried through to the subtraction the derivation actually forms.
    evidence = _artifact()["_provenance"]["bands"]["75+"]
    assert evidence["subtracted_households"] >= (
        _PUBLISHED_CELLS[("2481017", "75 to 84 years", _TENURE_TOTAL)]
        + _PUBLISHED_CELLS[("2481017", "85 years and over", _TENURE_TOTAL)])


# --- P11-11 -------------------------------------------------------------------------------

def test_p11_11_the_suppression_bound_is_field_wise_and_both_ends_are_feasible():
    """Suppressed cells are BOUNDED, never dropped and never assumed zero.

    FIELD-WISE because these subdivisions publish one field of a pair and withhold the other:
    dropping the published one would net a territory's households out of one denominator and
    its owners out of another.
    """
    fresh = hors_aligned.derive_aligned_ownership(
        DATA_DIR / census.CENSUS_EXTRACT, DATA_DIR / hors_aligned.EXTRACT)
    # BOTH surfaces: the committed bytes AND the code path that produces them. Reading only the
    # artifact would leave the bounding LOGIC ungated — a derivation that stopped bounding
    # would red only the no-drift gate, which reports "artifact != derivation" and sends the
    # reader to the generator rather than to the bound. (Measured: mutation M4.)
    for source, bands in (("committed artifact", _artifact()["_provenance"]["bands"]),
                          ("fresh derivation", fresh["_provenance"]["bands"])):
        for band in _BAND_ORDER:
            row = bands[band]
            assert row["aligned_rate"] == pytest.approx(_ALIGNED_RATES[band], rel=1e-12), source
            assert row["aligned_bound_rate"] == pytest.approx(
                _ALIGNED_BOUND[band], rel=1e-12), f"{source}: {band} bound moved"
            # Both ends inside the feasible region — an owner count above its own total, or a
            # negative residual, is an arithmetic pathology and not a rate.
            for key in ("aligned", "aligned_bound"):
                owner, total = row[f"{key}_owner_households"], row[f"{key}_households"]
                assert 0 <= owner <= total, f"{source}: {band}/{key} left the feasible region"
            if row["withheld_cells"]:
                assert row["aligned_bound_households"] < row["aligned_households"], (
                    f"{source}: {band} has withheld cells but the bound subtracts no more than "
                    "the published-only sum — the bound is not a bound")
            else:
                assert row["aligned_bound_rate"] == row["aligned_rate"], source
        assert sum(bands[b]["withheld_cells"] for b in _BAND_ORDER) == _WITHHELD_TOTAL, source

    # The committed extract's OWN zero-remainder count, pinned here so `_EMPTY_COMPLEMENT_BASELINE`
    # is an anchored measurement rather than a number the synthetic test asserts against itself.
    for source, payload in (("committed artifact", _artifact()), ("fresh derivation", fresh)):
        assert payload["_provenance"]["suppression"]["empty_complement_fields"] == \
            _EMPTY_COMPLEMENT_BASELINE, source


def test_p11_11b_an_empty_complement_clamps_the_bound_rather_than_estimating(tmp_path):
    """Where a subdivision publishes the same all-ages total as the sum of what it publishes,
    the unpublished remainder is ZERO — the withheld cell is bounded at zero, not estimated.

    The committed extract ALREADY exercises this at `_EMPTY_COMPLEMENT_BASELINE` fields (two of
    them at a round-to-5 NEGATIVE remainder, which is what the clamp is for). The synthetic
    extract is therefore not the only witness, and the assertion is written as
    `baseline + 1` rather than `>= 1`: `>= 1` was satisfied by the four committed fields alone,
    so it passed whether or not the construction below did anything — a check that could not
    fail. The construction's own contribution is what is gated.
    """
    payload = _extract()
    by_key = {(c["geography_code"], c["age_member"], c["tenure"]): c for c in payload["cells"]}
    # Zero out every published band cell of one CSD except a withheld one, and set its
    # all-ages row equal to the published sum -> remainder 0.
    code = "2481017"
    for band in _BAND_ORDER:
        for member in _CD_BANDS[band]:
            for tenure in (_TENURE_TOTAL, _TENURE_OWNER):
                by_key[(code, member, tenure)]["value"] = 0
                by_key[(code, member, tenure)]["status"] = "SUCCESS"
    by_key[(code, "85 years and over", _TENURE_OWNER)]["value"] = None
    by_key[(code, "85 years and over", _TENURE_OWNER)]["status"] = "FAILED"
    by_key[(code, "85 years and over", _TENURE_OWNER)]["status_code"] = None
    for tenure in (_TENURE_TOTAL, _TENURE_OWNER):
        by_key[(code, _ALL_AGES, tenure)]["value"] = 0
    out = tmp_path / hors_aligned.EXTRACT
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    derived = hors_aligned.derive_aligned_ownership(
        DATA_DIR / census.CENSUS_EXTRACT, out, verify_extract_pin=False)
    row = derived["_provenance"]["bands"]["75+"]
    # The clamped bound contributes nothing beyond the other CSDs' remainders; what is gated
    # here is that this CSD's zero remainder adds ZERO rather than an estimate.
    assert row["aligned_bound_households"] <= row["aligned_households"]
    assert derived["_provenance"]["suppression"]["empty_complement_fields"] == \
        _EMPTY_COMPLEMENT_BASELINE + 1, (
        "the constructed zero-remainder field did not register: the count is "
        f"{derived['_provenance']['suppression']['empty_complement_fields']}, and the committed "
        f"extract alone already carries {_EMPTY_COMPLEMENT_BASELINE}")


# --- P11-12 -------------------------------------------------------------------------------

def test_p11_12_a_stale_recorded_digest_is_refused_at_load_for_EITHER_source(tmp_path):
    """STEERING RULING L — identity is checked on every load, both sources.

    The no-drift gate compares CONTENT and cannot run at load time; this compares IDENTITY.
    TWO sources here, and an artifact derived from a stale CSD extract is exactly as wrong as
    one derived from a stale Census extract, so a single-digest check would leave one leg
    unexecuted.
    """
    for name in (census.CENSUS_EXTRACT, hors_aligned.EXTRACT):
        payload = _artifact()
        payload["_provenance"]["sources"][name] = "0" * 64
        d = tmp_path / name.replace(".", "_")
        d.mkdir()
        (d / hors_aligned.ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="STALE"):
            hors_aligned.load_aligned_ownership_rates(d)


def test_p11_12b_an_undated_or_uncited_artifact_is_refused_at_load(tmp_path):
    for field in ("as_of", "source"):
        payload = _artifact()
        payload["_provenance"][field] = ""
        d = tmp_path / field
        d.mkdir()
        (d / hors_aligned.ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(LoaderError, match="Anchor|as_of|source"):
            hors_aligned.load_aligned_ownership_rates(d)


def test_p11_12c_a_missing_band_is_refused_at_load_rather_than_serving_a_short_curve(tmp_path):
    payload = _artifact()
    del payload["rates"][Geography.HORS_RMR.value]["55-64"]
    (tmp_path / hors_aligned.ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="strict join"):
        hors_aligned.load_aligned_ownership_rates(tmp_path)


# --- P11-13 -------------------------------------------------------------------------------

def test_p11_13_the_derivation_refuses_an_unpinned_extract(tmp_path):
    """A derivation run on an unpinned or drifted vintage breaks the PIT chain while emitting
    perfectly plausible fractions — which is exactly how a retired typed curve once survived."""
    bad = tmp_path / hors_aligned.EXTRACT
    bad.write_text(json.dumps(_extract()) + "  ", encoding="utf-8")   # same payload, new bytes
    with pytest.raises(LoaderError, match="sha256 drift"):
        hors_aligned.derive_aligned_ownership(DATA_DIR / census.CENSUS_EXTRACT, bad)


def test_p11_13b_the_derivation_refuses_a_drifted_geography_set(tmp_path):
    """A dropped or added CSD changes what the residual DENOTES while every rate stays a
    plausible fraction — the same failure `census._read_totals_cube`'s GEO-set gate exists
    for, one grain down."""
    payload = _extract()
    payload["cells"] = [c for c in payload["cells"] if c["geography_code"] != "2482035"]
    bad = tmp_path / hors_aligned.EXTRACT
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match="geography set|missing"):
        hors_aligned.derive_aligned_ownership(
            DATA_DIR / census.CENSUS_EXTRACT, bad, verify_extract_pin=False)


def test_p11_13c_the_derivation_refuses_an_unpinned_census_extract(tmp_path):
    """THE SAME REFUSAL, ON THE OTHER LEG. P11-13 pins the CSD extract; this pins the 0231
    census CSV, which `census.read_totals_cube` is the derivation's ONLY reader of. That seam
    was added by this deliverable and carries its own `verify_pin` — ungated, the guard could
    be deleted and the whole suite would stay green, leaving the aligned path's PIT chain
    resting on the artifact's fixed rate literals instead of on the check that exists to catch
    a drifted vintage at the read.
    """
    pinned = DATA_DIR / census.CENSUS_EXTRACT
    raw = pinned.read_bytes()
    assert raw.endswith(b"\n")
    # Drift the LAST row's trailing `Symbol` field: a column the positional reader never reads,
    # on a row its `Total -` member filter skips outright. New bytes, IDENTICAL cube — so the
    # parser has nothing to object to and the pin is the only check left that can refuse it.
    drifted = tmp_path / census.CENSUS_EXTRACT
    drifted.write_bytes(raw[:-1] + b"x\n")
    assert census._read_totals_cube(drifted) == census._read_totals_cube(pinned), (
        "the drift must be value-neutral, or this test gates the parser rather than the pin")
    with pytest.raises(LoaderError, match="sha256 drift"):
        hors_aligned.derive_aligned_ownership(drifted, DATA_DIR / hors_aligned.EXTRACT)


# --- P11-14 -------------------------------------------------------------------------------

def test_p11_14_provenance_states_the_territory_the_rounding_and_the_reversal():
    """The record a reader needs and cannot infer: WHICH territory, at WHAT rounding cost, and
    WHY this row is re-pointed when no other is."""
    prov = _artifact()["_provenance"]
    territory = prov["territory"]
    for fragment in ("98-10-0231-01", "98-10-0232-01", "Ottawa", "NET"):
        assert fragment in territory, f"the territory sentence never names {fragment!r}"
    assert str(len(_QC_PART_CSDS)) in territory
    # The rounding envelope is DERIVED from the cell count, never a tuned literal.
    rounding = prov["rounding"]
    assert rounding["rounded_cells_per_field"]["25-54"] == 6 * 7 + 3 * 16
    assert rounding["envelope_per_field"]["25-54"] == 2.5 * (6 * 7 + 3 * 16)
    assert "5" in rounding["note"]
    # The reversal's lineage, so a future reader does not "restore" #12(B).
    assert "12(B)" in prov["supersedes"] and "band-uniform" in prov["supersedes"]
    # Multiplicand: a household-denominated rate never multiplies a person count.
    assert "household" in prov["multiplicand_note"].lower()


def test_p11_15_the_vintage_accessor_states_both_sources_and_the_upstream_anchor():
    """A consumer holding these rates must be able to fill spec §7's `data_vintage`."""
    vintage = hors_aligned.load_aligned_ownership_vintage()
    assert dict(vintage.sources) == {
        census.CENSUS_EXTRACT: WORKBOOK_SHA256[census.CENSUS_EXTRACT],
        hors_aligned.EXTRACT: WORKBOOK_SHA256[hors_aligned.EXTRACT]}
    assert vintage.raw_source_name == census.CENSUS_EXTRACT
    assert vintage.as_of == "2021"
    # The raw anchor belongs to the 0231 leg alone: the CSD extract is a coordinate pull and
    # IS its own raw response, so substituting an anchor for it would name a nonexistent
    # upstream member.
    assert vintage.source_hashes()[hors_aligned.EXTRACT]["sha256"] == \
        WORKBOOK_SHA256[hors_aligned.EXTRACT]


# --- P11-16 -------------------------------------------------------------------------------

def test_p11_16_the_membership_recorded_is_the_territory_p10_resolved():
    """The extract's own live re-derivation must land on P10's resolved membership.

    Re-derived by the puller from 98-10-0003-01 rather than re-discovered: the CMA's children
    close EXACTLY on its own population (a child list that did not close would make 'the
    Québec side of this CMA' a slice of an unknown whole), and each child is classified twice.
    """
    membership = _extract()["_pull"]["membership"]
    assert tuple(membership["quebec_side_codes"]) == _QC_PART_CSDS
    assert membership["children_count"] == 25
    assert membership["children_population_sum"] == membership["cma_population"], (
        "the CMA's children do not close on the CMA — the Québec side is a slice of an "
        "unknown whole")
    assert membership["classification_disagreements"] == []
    assert membership["quebec_side_population"] + membership["ontario_side_population"] == \
        membership["cma_population"]
    # Anchored to the probe that resolved it, so the two cannot drift apart silently.
    note = (PROBES / "P10-hors-operand-alignment.md").read_text(encoding="utf-8")
    assert f"{membership['cma_population']:,}" in note, (
        "the recorded CMA population is not the one P10's note records")
    for code in _QC_PART_CSDS:
        assert code in note, f"SGC {code} is not in P10's resolved membership table"


# --- P11-17 -------------------------------------------------------------------------------

def test_p11_17_the_consumer_lookup_resolves_every_band_to_the_artifacts_own_rate():
    """The SERVING path of the module's only consumer-facing accessor.

    CLASS CENSUS of `aligned_ownership_rate`: one serving path and three refusal siblings —
    a geography this surface does not re-point (P11-8), an age outside the modeled lattice,
    and a band the loaded table does not carry. Only the first was gated; the SERVING path had
    no gate at all, so the accessor's whole band-lookup body ran in no test. Measured at run 25
    review: `lo <= age <= hi` weakened to `lo <= age < hi`, and the band test replaced by
    `if True` (every age served the FIRST band's rate), BOTH survived the suite green. The
    T13b sibling gates the analogous `census.ownership_rate` at six sites; this is that pattern
    applied here rather than generic coverage.

    Both EDGES of every band, because an off-by-one at a boundary is the failure this class
    actually produces — an interior-only probe passes it.
    """
    rates = hors_aligned.load_aligned_ownership_rates()
    table = rates[Geography.HORS_RMR.value]
    for band in _BAND_ORDER:
        lo, hi = _BAND_EDGES[band]
        for age in (lo, hi):
            served = hors_aligned.aligned_ownership_rate(rates, Geography.HORS_RMR, age)
            assert served == pytest.approx(table[band], rel=1e-12), (
                f"age {age} resolved to a rate that is not the artifact's own {band} entry: "
                f"{served} vs {table[band]}")
    # The bands are DISTINCT, so "every age serves the first band" cannot pass the loop above
    # by accident — asserted rather than assumed, because the loop's discriminating power is
    # exactly the spread between them.
    assert len({table[band] for band in _BAND_ORDER}) == len(_BAND_ORDER), (
        "two bands carry the same rate — the edge sweep above would not discriminate a "
        "lookup that resolved every age to one band")


@pytest.mark.parametrize("age", [0, 24, 201, 1000])
def test_p11_17b_an_age_outside_the_modeled_lattice_REFUSES(age):
    """Below the 25 floor and above the 200 ceiling, exactly as `census.ownership_rate` does.

    The floor is load-bearing: this curve does NOT extend below 25 (spec §7 rules the sub-floor
    question separately), so an age-20 lookup that quietly served the 25-54 rate would answer a
    question this surface has not measured.
    """
    rates = hors_aligned.load_aligned_ownership_rates()
    with pytest.raises(LoaderError, match="no modeled age band"):
        hors_aligned.aligned_ownership_rate(rates, Geography.HORS_RMR, age)


def test_p11_17c_a_band_absent_from_the_loaded_table_REFUSES_rather_than_serving():
    """The third refusal sibling, on a THINNED table handed straight to the accessor.

    Distinct from P11-12c, which proves the LOAD path refuses a short curve: this proves the
    accessor itself refuses rather than KeyError-ing or falling through to a neighbouring
    band, for a caller that assembled a table by some other route.
    """
    thinned = {Geography.HORS_RMR.value: {"25-54": 0.69}}
    assert hors_aligned.aligned_ownership_rate(
        thinned, Geography.HORS_RMR, 30) == pytest.approx(0.69)
    with pytest.raises(LoaderError, match="no aligned ownership rate .* band 75\\+"):
        hors_aligned.aligned_ownership_rate(thinned, Geography.HORS_RMR, 80)
    # And an EMPTY table for the re-pointed geography refuses on the same branch rather than
    # dereferencing None (`rates.get(...) or {}`).
    with pytest.raises(LoaderError, match="no aligned ownership rate"):
        hors_aligned.aligned_ownership_rate({}, Geography.HORS_RMR, 30)


# --- P11-18 -------------------------------------------------------------------------------

def _artifact_in(tmp_path, mutate) -> Path:
    """A copy of the committed artifact with one field broken, in its own directory."""
    payload = _artifact()
    mutate(payload)
    (tmp_path / hors_aligned.ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_p11_18_the_load_path_refuses_every_shape_that_cannot_prove_its_identity(tmp_path):
    """CLASS CENSUS of `_verify_artifact_provenance` / `_read_verified`, exercised.

    P11-12 gates the STALE-digest branch on both sources; the siblings around it — a
    `_provenance` block absent entirely, a `sources` map absent, a source with no recorded
    digest, and an artifact file that is not there — were present but unexecuted. A guard whose
    failing branch no test reaches is a guard nobody has seen fire, and each of these refusals
    carries a DIFFERENT instruction to the reader, so the messages are discriminated rather
    than merely counted as raises.
    """
    cases = {
        "no provenance": (lambda p: p.pop("_provenance"), "no `_provenance` block"),
        "no sources map": (lambda p: p["_provenance"].pop("sources"),
                           "no `_provenance.sources` map"),
        "census digest dropped": (
            lambda p: p["_provenance"]["sources"].pop(census.CENSUS_EXTRACT),
            "records no sha256"),
        "csd digest dropped": (
            lambda p: p["_provenance"]["sources"].pop(hors_aligned.EXTRACT),
            "records no sha256"),
    }
    for name, (mutate, expected) in cases.items():
        d = tmp_path / name.replace(" ", "_")
        d.mkdir()
        with pytest.raises(LoaderError, match=expected):
            hors_aligned.load_aligned_ownership_rates(_artifact_in(d, mutate))

    missing = tmp_path / "empty"
    missing.mkdir()
    with pytest.raises(LoaderError, match="aligned ownership artifact not found"):
        hors_aligned.load_aligned_ownership_rates(missing)


def test_p11_18b_an_unpinned_source_refuses_rather_than_comparing_against_nothing(
        tmp_path, monkeypatch):
    """If a source name carries no registry pin, there is nothing to check the artifact
    against — and `WORKBOOK_SHA256.get(...)` would otherwise compare `None` to `None` for a
    `sources` map that also dropped it. The PIT chain is unpinned, and that refuses."""
    monkeypatch.delitem(pins.WORKBOOK_SHA256, hors_aligned.EXTRACT)
    with pytest.raises(LoaderError, match="no sha256 pin registered"):
        hors_aligned.load_aligned_ownership_rates(DATA_DIR)


def test_p11_18c_the_load_path_records_and_checks_the_upstream_raw_anchor(tmp_path):
    """THE ONE ANCHOR A RE-EXTRACT CANNOT MOVE, ported from the T13b sibling.

    Every other gate on this artifact compares CO-MOVING objects: the extract's pin, the
    artifact's recorded digest and a fresh derivation all move together when the extract is
    re-cut. The raw StatCan member's digest is a REGISTRY pin that does not. It was recorded
    here and checked at load, but nothing exercised the branch — measured at run 25 review,
    deleting the check entirely left the suite green. `test_census_ownership.py`'s
    `test_ownership_artifact_records_and_checks_the_upstream_raw_anchor` is this test's sibling;
    hors_aligned copied that gate's defensive `.get`-not-raising-accessor comment without
    copying its test.
    """
    prov = _artifact()["_provenance"]
    assert prov["raw_source_sha256"] == pins.RAW_SOURCE_SHA256[census.CENSUS_EXTRACT]
    assert prov["raw_source_member"] == pins.RAW_SOURCE_MEMBER[census.CENSUS_EXTRACT]
    # The CSD leg carries NO raw anchor by design: it is a WDS coordinate pull and IS its own
    # raw response, so an anchor row for it would name a nonexistent upstream member.
    assert hors_aligned.EXTRACT not in pins.RAW_SOURCE_SHA256

    with pytest.raises(LoaderError, match="raw_source_sha256"):
        hors_aligned.load_aligned_ownership_rates(_artifact_in(
            tmp_path, lambda p: p["_provenance"].__setitem__("raw_source_sha256", "0" * 64)))


def test_p11_18d_a_half_registered_raw_anchor_refuses_instead_of_crashing(
        tmp_path, monkeypatch):
    """The raw anchor has TWO hand-maintained halves and the refusal message reads BOTH.

    The digest half stays registered here on purpose: drop it and `raw_anchor` raises first,
    which tests the registry gate rather than this branch. With the digest present, a stale
    recorded digest AND a dropped member name is the state that turns an informative drift
    refusal into `KeyError` — a class no `except LoaderError` catches. The message must
    degrade the member to '?' and keep the vintage information that is the whole reason the
    reader is being stopped, exactly as the T13b sibling asserts.
    """
    monkeypatch.delitem(pins.RAW_SOURCE_MEMBER, census.CENSUS_EXTRACT)
    d = _artifact_in(tmp_path,
                     lambda p: p["_provenance"].__setitem__("raw_source_sha256", "0" * 64))
    with pytest.raises(LoaderError, match="raw_source_sha256") as exc:
        hors_aligned.load_aligned_ownership_rates(d)
    assert "?" in str(exc.value), (
        "the half-registered member did not degrade to '?' — the drift refusal lost its "
        "message (or crashed out of the loader taxonomy)")


def test_p11_18e_a_second_geography_in_rates_is_refused_at_load(tmp_path):
    """The strict-join fence ON THE SHARED PATH: `rates` carries the re-pointed row and
    nothing else. P11-8 proves the COMMITTED bytes carry one row; this proves the LOAD refuses
    a second one, which is the branch that survived deletion at run 25 review. A second row
    here would be a second curve served under a provenance block describing one territory."""
    def plant(p):
        p["rates"][Geography.MTL_RMR.value] = dict(p["rates"][Geography.HORS_RMR.value])
    with pytest.raises(LoaderError, match="strict join"):
        hors_aligned.load_aligned_ownership_rates(_artifact_in(tmp_path, plant))


def test_p11_18f_a_rates_row_that_is_not_a_band_map_refuses_at_load(tmp_path):
    """`_assert_anchor_typed`'s shape branch: a `rates` row that is not an object at all would
    otherwise fall through the Anchor loop and serve whatever it is."""
    with pytest.raises(LoaderError, match="expected an object"):
        hors_aligned.load_aligned_ownership_rates(_artifact_in(
            tmp_path, lambda p: p["rates"].__setitem__(Geography.HORS_RMR.value, 0.69)))


# --- P11-19 -------------------------------------------------------------------------------

def test_p11_19_the_band_lattice_guard_fires_when_the_models_bands_move(monkeypatch):
    """`assert_band_lattice` is the drift vector's only tripwire, and it was never seen fire.

    Two lattices spelled in two modules drift invisibly: a curve measured over 25-49 instead
    of 25-54 is still a plausible fraction at every band. The model's spec is moved here (not
    this module's), because that is the direction the drift actually runs — `census` owns the
    lattice and this surface must follow it.
    """
    drifted = tuple((label, lo, 49 if label == "25-54" else hi, members)
                    for label, lo, hi, members in census._AGE_BAND_SPEC)
    monkeypatch.setattr(census, "_AGE_BAND_SPEC", drifted)
    with pytest.raises(LoaderError, match="not the model's"):
        hors_aligned.assert_band_lattice()
    # And the derivation refuses on the same guard rather than emitting a mis-banded curve.
    with pytest.raises(LoaderError, match="not the model's"):
        hors_aligned.derive_aligned_ownership(
            DATA_DIR / census.CENSUS_EXTRACT, DATA_DIR / hors_aligned.EXTRACT)


@pytest.mark.parametrize("name,mutate,expected", [
    ("duplicate cell address",
     lambda cells: cells.append(dict(cells[0])), "duplicate cell"),
    ("a negative count",
     lambda cells: cells[0].__setitem__("value", -5), "non-count value"),
    ("a non-integer count",
     lambda cells: cells[0].__setitem__("value", 12.5), "non-count value"),
])
def test_p11_19b_the_extract_reader_refuses_a_malformed_cell(tmp_path, name, mutate, expected):
    """The extract reader's own shape guards, exercised rather than merely present.

    A duplicated dimension address (a payload copied, or a coordinate builder that collided)
    would double-count a subdivision into the subtraction; a non-count value would flow
    straight into the arithmetic. Both survived deletion at run 25 review.
    """
    payload = _extract()
    mutate(payload["cells"])
    bad = tmp_path / hors_aligned.EXTRACT
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LoaderError, match=expected):
        hors_aligned.derive_aligned_ownership(
            DATA_DIR / census.CENSUS_EXTRACT, bad, verify_extract_pin=False)


@pytest.mark.parametrize("owner,total,expected", [
    (10, 0, "non-positive household total"),
    (10, -5, "non-positive household total"),
    (-1, 100, "negative owner count"),
    (150, 100, "exceed total"),
])
def test_p11_19c_a_subtraction_that_left_the_feasible_region_REFUSES(owner, total, expected):
    """`_rate`'s three degeneracies, each on its OWN message.

    A subtraction that carried the residual out of the feasible region is the failure mode
    this whole construction risks — subtracting one cube's cells from another's residual can
    in principle overshoot. It must surface as a named LoaderError, never as a
    ZeroDivisionError (a class no `except LoaderError` catches) and never as a rate above 1.
    All three refusals survived deletion at run 25 review.
    """
    with pytest.raises(LoaderError, match=expected):
        hors_aligned._rate(owner, total, "test-ctx")


# --- P11-8c -------------------------------------------------------------------------------

@pytest.mark.parametrize("name,mutate,expected", [
    ("join dropped entirely", lambda p: p.pop("join"), "must name every modeled geography"),
    ("join names only the re-pointed row",
     lambda p: p.__setitem__("join", {Geography.HORS_RMR.value: p["join"][
         Geography.HORS_RMR.value]}),
     "must name every modeled geography"),
    ("join re-points a SECOND geography",
     lambda p: p["join"][Geography.MTL_RMR.value].update(
         {"reads": "operand_aligned", "artifact": hors_aligned.ARTIFACT}),
     "exactly one geography may read"),
    ("join re-points NOTHING",
     lambda p: p["join"][Geography.HORS_RMR.value].__setitem__("reads", "shipped"),
     "exactly one geography may read"),
    ("join points a row at the wrong artifact",
     lambda p: p["join"][Geography.MTL_RMR.value].__setitem__("artifact", hors_aligned.ARTIFACT),
     "artifact.*does not match"),
    ("join states no reason for a row",
     lambda p: p["join"][Geography.QC_RMR.value].__setitem__("why", "   "),
     "states no reason"),
    # Planted on a NON-re-pointed row on purpose: a malformed HORS_RMR row would trip the
    # "exactly one geography may read" check first and never reach these two branches.
    ("a join row is not an object at all",
     lambda p: p["join"].__setitem__(Geography.MTL_RMR.value, "shipped"),
     "is not an object"),
    ("a join row reads something that is neither curve",
     lambda p: p["join"][Geography.MTL_RMR.value].__setitem__("reads", "some_third_curve"),
     "expected 'operand_aligned' or 'shipped'"),
])
def test_p11_8c_a_broken_join_refuses_on_the_SHARED_path(tmp_path, name, mutate, expected):
    """THE SCOPE FENCE AT RUNTIME — validated for CONTENT, and on the path all three accessors
    share.

    Two defects, both measured at run 25 review. (1) The join was validated for its KEY SET
    only, so an artifact whose join declared MTL_RMR reads the operand-aligned curve LOADED
    CLEAN — a check that could not catch the thing it exists for. (2) The validation lived in
    the join accessor alone, so an artifact with `join` dropped or gutted still SERVED rates
    and still handed back a confident `RateVintage`. That is precisely the split-legs incident
    `census._read_verified_ownership` records as measured on 2026-08-14 and fixed by moving the
    completeness check onto the shared path — the rationale `_read_verified`'s own docstring
    cites while not, until now, implementing it.

    P11-8 gates the join on the COMMITTED bytes; a test defends the repo, not a runtime load.
    All three accessors must refuse, or one of them states a confident answer about a curve no
    run may use.
    """
    d = tmp_path / name.replace(" ", "_")
    d.mkdir()
    _artifact_in(d, mutate)
    for accessor in (hors_aligned.load_aligned_ownership_rates,
                     hors_aligned.load_aligned_ownership_vintage,
                     hors_aligned.load_aligned_ownership_join):
        with pytest.raises(LoaderError, match=expected):
            accessor(d)


# --- P11-11c ------------------------------------------------------------------------------

def test_p11_11c_the_published_envelope_actually_BRACKETS_the_rate():
    """THE ENVELOPE IS AN ENVELOPE — the corners published are the rate's, not the
    subtraction's.

    Measured at run 25 review: the module formed only the two DIAGONAL corners of the
    withheld-cell rectangle (subtract-LEAST on both fields, subtract-MOST on both) and
    published them as the bracket. Because rate = (S_o - s_o)/(S_t - s_t) FALLS in the
    subtracted owners and RISES in the subtracted households, the rate's extremes sit at the
    OFF-DIAGONAL corners, which nothing computed — and a fully feasible configuration (every
    withheld owner at 0, every withheld household at its remainder) put the 75+ rate at
    +0.251%, ABOVE the published upper end of +0.223%. The true value could sit outside the
    published interval, which is the one thing an envelope may not permit.

    The corners are re-derived HERE from the artifact's own counts, so this gate does not
    merely re-read the two fields it is checking.
    """
    for source, bands in (("committed artifact", _artifact()["_provenance"]["bands"]),
                          ("fresh derivation", hors_aligned.derive_aligned_ownership(
                              DATA_DIR / census.CENSUS_EXTRACT,
                              DATA_DIR / hors_aligned.EXTRACT)["_provenance"]["bands"])):
        for band in _BAND_ORDER:
            row = bands[band]
            assert row["aligned_envelope_low_rate"] == pytest.approx(
                _ALIGNED_ENVELOPE_LOW[band], rel=1e-12), f"{source}: {band} envelope low"
            assert row["aligned_envelope_high_rate"] == pytest.approx(
                _ALIGNED_ENVELOPE_HIGH[band], rel=1e-12), f"{source}: {band} envelope high"

            # Re-derived from the counts: least owner subtracted over most household
            # subtracted is the MAXIMUM, and the reverse is the minimum. A transposition of the
            # two lines in the module reds here as well as against the literals above.
            s_o, s_t = row["shipped_owner_households"], row["shipped_households"]
            sub_o, sub_t = row["subtracted_owner_households"], row["subtracted_households"]
            hi_o = s_o - row["aligned_bound_owner_households"]
            hi_t = s_t - row["aligned_bound_households"]
            assert row["aligned_envelope_high_rate"] == pytest.approx(
                (s_o - sub_o) / (s_t - hi_t), rel=1e-12), f"{source}: {band} high corner"
            assert row["aligned_envelope_low_rate"] == pytest.approx(
                (s_o - hi_o) / (s_t - sub_t), rel=1e-12), f"{source}: {band} low corner"

            # THE BRACKET: both subtraction corners — the served rate among them — lie inside
            # the envelope. This is the assertion the module previously could not satisfy.
            lo, hi = row["aligned_envelope_low_rate"], row["aligned_envelope_high_rate"]
            assert lo <= hi, f"{source}: {band} envelope is inverted (corners transposed?)"
            for key in ("aligned_rate", "aligned_bound_rate"):
                assert lo <= row[key] <= hi, (
                    f"{source}: {band} {key} {row[key]} sits OUTSIDE the published envelope "
                    f"[{lo}, {hi}] — the envelope does not bracket the rate")

            # A band with no withheld cells is a POINT, not an interval: nothing is uncertain.
            if not row["withheld_cells"]:
                assert lo == hi == row["aligned_rate"], (
                    f"{source}: {band} withholds nothing yet publishes a non-degenerate "
                    "envelope — the interval is being manufactured")
            else:
                assert lo < row["aligned_rate"] < hi, (
                    f"{source}: {band} withholds {row['withheld_cells']} cells but its "
                    "envelope is degenerate at the served value")

    # THE HIGH CORNER'S ATTAINABILITY, which the module docstring asserts and which is a
    # property of THIS extract rather than of the code: it holds because no cell withholds its
    # household field while publishing its owner field, so "every withheld owner at 0, every
    # withheld household at its remainder" satisfies owner <= total everywhere. A re-pin could
    # break it — the envelope would stay a valid OUTER bound but would stop being tight, and
    # the docstring's "exactly ATTAINABLE" would become false without anything else reddening.
    withheld_by_cell = {}
    for (code, age, tenure), value in _extract_cells().items():
        if value is None:
            withheld_by_cell.setdefault((code, age), set()).add(tenure)
    half_total = sorted(cell for cell, fields in withheld_by_cell.items()
                        if _TENURE_TOTAL in fields and _TENURE_OWNER not in fields)
    assert half_total == [], (
        "a cell withholds its household field while publishing its owner field "
        f"({half_total}) — the envelope's HIGH corner is no longer exactly attainable, so the "
        "module docstring's attainability claim needs re-measuring (the bracket itself still "
        "holds as an outer bound)")


def test_p11_11d_the_band_spread_survives_every_corner_of_the_feasible_box():
    """WHAT THE REVERSAL RESTS ON, measured across the suppression rather than at a point.

    #12(B)'s premise is band-UNIFORMITY of the contamination, so the refutation IS the spread.
    If a feasible configuration of the withheld cells could collapse that spread, the
    suppression would be carrying the reversal. It cannot: the spread stays strictly positive,
    same-signed and adversarially arranged (25-54 the most contaminated, 75+ the least) at
    every corner of the box.
    """
    prov = _artifact()["_provenance"]
    env = prov["suppression"]["envelope"]
    assert env["band_spread_pp"] == pytest.approx(_BAND_SPREAD_PP, rel=1e-12)
    assert env["all_bands_same_signed_across_the_box"] is True

    spread = env["band_spread_pp"]
    assert spread["narrowest_feasible"] > 1.0, (
        "the band spread's WORST feasible case has collapsed below a percentage point — "
        "#12(B)'s band-uniformity premise would need re-measuring, not restoring")
    assert spread["narrowest_feasible"] <= spread["at_served_corner"] <= \
        spread["widest_feasible"], "the served corner is outside the box it is meant to sit in"
    assert spread["narrowest_feasible"] <= spread["at_subtract_most_corner"] <= \
        spread["widest_feasible"]

    # ADVERSARIAL ARRANGEMENT, at the worst corner: the band D_native is built from must remain
    # the most contaminated and the band S rides must remain the least, or the sign of
    # (δ_D − δ_S) — not just its size — would be a function of the suppression.
    bands = prov["bands"]
    worst_for_d = min(bands["25-54"]["relative_delta_envelope_low_pct"],
                      bands["25-54"]["relative_delta_envelope_high_pct"])
    best_for_s = max(bands["75+"]["relative_delta_envelope_low_pct"],
                     bands["75+"]["relative_delta_envelope_high_pct"])
    assert worst_for_d > best_for_s, (
        "at the corner least favourable to the finding, 25-54 is no longer more contaminated "
        f"than 75+ ({worst_for_d} vs {best_for_s}) — the adverse arrangement is not robust "
        "to the suppression")
    # And every band's contamination stays STRICTLY POSITIVE at its own low corner.
    for band in _BAND_ORDER:
        assert min(bands[band]["relative_delta_envelope_low_pct"],
                   bands[band]["relative_delta_envelope_high_pct"]) > 0, band


def test_p11_11e_the_provenance_names_the_envelope_as_the_bracket_and_the_diagonal_as_not():
    """The narrative a future reader will act on. `suppression.bound` must not claim to bracket
    the rate, and the reversal record must say the spread survives the whole box — otherwise a
    reader meets the same 'both ends are published' claim that was measured false."""
    prov = _artifact()["_provenance"]
    bound = prov["suppression"]["bound"]
    assert "do NOT bracket the rate" in bound or "not bracket" in bound.lower(), (
        "`suppression.bound` still presents the subtraction corners as the rate's bracket")
    note = prov["suppression"]["envelope"]["note"]
    for fragment in ("OFF-DIAGONAL", "ATTAINABLE", "OUTER"):
        assert fragment in note, f"the envelope note never states {fragment!r}"
    assert "every corner" in prov["supersedes"], (
        "the reversal record does not say the spread survives the whole feasible box")

    # The MODULE DOCSTRING's own figures, traced to the computed ones. It states the box range
    # in prose, and prose does not move when the extract is re-pinned — this is the gate that
    # makes it move.
    doc = hors_aligned.__doc__
    spread = prov["suppression"]["envelope"]["band_spread_pp"]
    for key in ("narrowest_feasible", "widest_feasible"):
        assert f"{spread[key]:.3f}" in doc, (
            f"the module docstring does not state the computed {key} "
            f"({spread[key]:.3f} pp) — a narrative figure has parted from the measurement")
    hi_75 = _artifact()["_provenance"]["bands"]["75+"]["relative_delta_envelope_high_pct"]
    served_75 = _artifact()["_provenance"]["bands"]["75+"]["relative_delta_pct"]
    assert f"+{hi_75:.3f}%" in doc and f"+{served_75:.3f}%" in doc, (
        "the docstring's worked example of the envelope defect no longer quotes the "
        "computed 75+ figures")
