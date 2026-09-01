"""P11 — the OPERAND-ALIGNED ownership curve for HORS_RMR (reverses spec §6 amendment #12(B)).

WHAT IS BEING GATED. `census.derive_ownership_from_csv` measures HORS_RMR's ownership
propensity over the Québec province NET of the six wholly-Québec CMAs — a residual that
INCLUDES the Québec side of Ottawa-Gatineau, because 98-10-0231-01 parents that CMA to
Ontario and publishes no Québec-part row. The flows that rate multiplies come from ISQ's own
hors-RMR row, which EXCLUDES it. Amendment #12(B) cleared the ownership leg from correction
on the ground that a BAND-UNIFORM relative scaling of ρ cancels exactly in ED; probe P10
measured that premise FALSE (spread 1.202 pp across the FOUR model bands the lattice then had,
all same-signed, and adversarially arranged — the most contaminated band is the one D_native is
built from, the least is the one S rides). The seat reversed #12(B) and ORDERED this extraction.

THE FIGURES IN THE PARAGRAPH ABOVE ARE HISTORICAL, and are kept because they are the reversal's
WARRANT rather than a current reading. They were measured by P10 on 2026-08-15 against the
four-band lattice `25-54 / 55-64 / 65-74 / 75+`. Operator ruling W (2026-08-20) refined that
lattice to SEVEN bands, and the current-lattice figures are carried by the regenerated artifact
and pinned in the oracle block below — the spread WIDENS to 3.318 pp and the arrangement stays
adverse, so the refinement strengthens the reversal rather than disturbing it. Do not read the
1.202 as a live number, and do not delete it: a reversal whose warrant has been overwritten
cannot be audited.

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
import re
import subprocess
import sys
from pathlib import Path

import pytest

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders import census, hors_aligned, pins
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256

from ._prose_binding import PCT_SIGNED, PP_ABS, bound_map, flat, says

DEMOFLOW = Path(__file__).resolve().parent.parent
PROBES = DEMOFLOW / "probes"

# --- TEST-OWNED oracle -----------------------------------------------------------------
# The CD/CSD cube's OWN age members per model band. 98-10-0232-01 publishes a COARSER age
# axis than 98-10-0231-01 (9 dimension members against 15): the band EDGES are the model's, the
# constituents are whatever each cube publishes.
#
# SEVEN BANDS SINCE OPERATOR RULING W (2026-08-20; spec §8 amendment #18). This cube is WHY the
# refined lattice is ten-year and not five-year: every one of its age members at or above 25 is
# ten-year or a published tail member, so the 7-band partition below is the FINEST ONE BOTH
# CUBES CAN EXPRESS. A five-year CMA-side refinement would have left HORS_RMR the only
# geography still carrying a thirty-year 25-54 band — a non-common-mode artifact on exactly the
# one row this surface exists to correct.
_CD_BANDS = {
    "25-34": ("25 to 34 years",),
    "35-44": ("35 to 44 years",),
    "45-54": ("45 to 54 years",),
    "55-64": ("55 to 64 years",),
    "65-74": ("65 to 74 years",),
    "75-84": ("75 to 84 years",),
    "85+": ("85 years and over",),
}
_BAND_ORDER = ("25-34", "35-44", "45-54", "55-64", "65-74", "75-84", "85+")
# The band EDGES, typed here a second time rather than read off `CD_BAND_SPEC`: P11-17 gates the
# consumer lookup's band RESOLUTION, and a lookup gate that takes its own edges from the spec it
# is checking cannot catch the spec moving (the same argument the oracle block opens with).
_BAND_EDGES = {"25-34": (25, 34), "35-44": (35, 44), "45-54": (45, 54), "55-64": (55, 64),
               "65-74": (65, 74), "75-84": (75, 84), "85+": (85, 200)}
# The band `D_native` is built from and the bands `S` reads, BY NAME — the adverse arrangement
# that refutes #12(B) is a claim about these specific bands, so they are typed rather than
# inferred. D reads the youngest band (formation runs from the lattice floor up).
#
# S READS BOTH TAIL BANDS, NOT ONE (operator ruling X1, 2026-08-21), AND THAT IS WHY THIS IS A
# TUPLE. `_standing_stock` used to read ownership at `pipeline.ROLL_AGE = 80`; ruling X1 stopped
# it reading at any age and values the lumped 75+ bucket at the POPULATION-WEIGHTED mean of the
# per-age rates over the ages it holds, which spans `75-84` and `85+`. A band-name constant
# would now name a read that does not exist.
#
# WHAT MAKES THE ARRANGEMENT CLAIM SURVIVE THE CHANGE WITHOUT A WEIGHT PIN. S's rate is a convex
# combination of the two tail band rates (per-age rates are constant inside a band), and a
# weighted mean of two rates is a MEDIANT of them:
#     (w·a1 + (1−w)·a2) / (w·s1 + (1−w)·s2)
# is the a/s mediant with weights w·s1 and (1−w)·s2, so it lies between a1/s1 and a2/s2 for
# every w in [0,1]. δ_S therefore lies between the two tail bands' relative contaminations at
# EVERY feasible population weighting — which is what `test_p11_11d` asserts, instead of pinning
# one blend. (Measured for the record at this artifact's own aligned household weights,
# 110,150 / 30,605: +0.2441105582854595%, inside [+0.2415689768%, +0.2532579263%] and below the
# next-lowest band, 45-54 at +0.2731774182%.)
_D_NATIVE_BAND = "25-34"
_S_RIDES_BANDS = ("75-84", "85+")
# The two PUBLISHED TAIL MEMBERS — one model band each since ruling W, and the only members
# the committed extract withholds anything at. Named once so the suppression-scope gate does not
# have to spell either the retired union or the two new bands.
_TAIL_MEMBERS = ("75 to 84 years", "85 years and over")
_ALL_AGES = "Total - Age of primary household maintainer"
# The cube's age dimension, by the name its own metadata uses. `dimension_positions` spells it
# with the member COUNT in parentheses (`... (9)`) and `member_ids` without — P11-1 reads both.
_AGE_DIMENSION = "Age of primary household maintainer"
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
    "25-34": (85_585, 147_205),
    "35-44": (131_690, 187_830),
    "45-54": (138_285, 187_500),
    "55-64": (205_915, 275_450),
    "65-74": (175_595, 240_310),
    "75-84": (80_360, 120_345),
    "85+": (19_555, 33_085),
}
# The retired four-band counts, kept as a PARTITION CHECK and not as a lattice: the refinement
# is exact, so the new bands must re-aggregate to the counts the four-band lattice published.
# A split that leaked or double-counted a cube member reds here while every rate stays a
# plausible fraction — which is the whole failure class this file was built against.
_RETIRED_FOUR_BAND_COUNTS = {
    "25-54": (355_560, 522_535),
    "55-64": (205_915, 275_450),
    "65-74": (175_595, 240_310),
    "75+": (99_915, 153_430),
}
_RETIRED_PARTITION = {"25-54": ("25-34", "35-44", "45-54"), "55-64": ("55-64",),
                      "65-74": ("65-74",), "75+": ("75-84", "85+")}
_SHIPPED_ALL_AGES = (845_355, 1_223_585)

# The ALIGNED curve — measured. Published-counts-only subtraction (subtract LEAST) is the
# served value; `_ALIGNED_BOUND` is the same subtraction with every withheld field at its
# upper bound (subtract MOST). The withheld cells are all TAIL cells, so since ruling W split
# the tail BOTH `75-84` and `85+` move where one `75+` band moved before — and they move
# differently, which is the point: `75-84`'s only withheld field is an OWNER field (one cell,
# at 2480065), while `85+` withholds both fields. The five younger bands withhold nothing and
# are therefore POINTS, not intervals.
_ALIGNED_RATES = {
    "25-34": 0.6020927601809954,
    "35-44": 0.7091195463852575,
    "45-54": 0.7395347380944927,
    "55-64": 0.7499130078804626,
    "65-74": 0.732921103858926,
    "75-84": 0.6693599636858829,
    "85+": 0.5925502368893971,
}
_ALIGNED_BOUND = {
    "25-34": 0.6020927601809954,
    "35-44": 0.7091195463852575,
    "45-54": 0.7395347380944927,
    "55-64": 0.7499130078804626,
    "65-74": 0.732921103858926,
    "75-84": 0.6692691783931003,
    "85+": 0.5921805987240307,
}
# The ENVELOPE — the OFF-DIAGONAL corners of the feasible withheld-cell rectangle, which are
# the rate's actual extremes. `_ALIGNED_RATES` and `_ALIGNED_BOUND` are the two SUBTRACTION
# corners (least/most on BOTH fields) and do NOT bracket the rate: rate = (S_o-s_o)/(S_t-s_t)
# falls in subtracted owners and rises in subtracted households, so the maximum takes the least
# owner against the most household and the minimum takes the reverse. Both 75+ literals are
# typed rather than asserted as a relation, because a TRANSPOSED pair is still an interval, is
# still feasible-looking, and is merely narrower — the exact defect this oracle exists to catch
# (measured at run 25 review: the true max +0.251% sat ABOVE the published upper end +0.223%).
# NOTE THE ONE-SIDED BAND, which the refinement exposed and the four-band lattice could not:
# `75-84` withholds an OWNER field and no HOUSEHOLD field, so its HIGH corner (least owner
# subtracted, MOST household subtracted) has no extra household to subtract and coincides
# EXACTLY with the served rate. Its envelope is [low, served], open on one side only. That is
# the correct envelope for one-sided suppression, not a degenerate one — and it is typed here
# rather than asserted as `low < served < high`, which was true only while the sole suppressed
# band withheld both fields.
_ALIGNED_ENVELOPE_LOW = dict(_ALIGNED_RATES, **{"75-84": 0.6692691783931003,
                                               "85+": 0.5914066329031205})
_ALIGNED_ENVELOPE_HIGH = dict(_ALIGNED_RATES, **{"75-84": 0.6693599636858829,
                                                 "85+": 0.5933256993292982})
# The band spread, in percentage points, at the four corners of the feasible box. The figure
# #12(B)'s band-uniformity premise is refuted by — so what matters is that the NARROWEST is
# still strictly positive and still adversarially arranged.
# WIDER UNDER THE REFINED LATTICE, and that is the finding rather than a side effect: the
# retired 25-54 band averaged a steep gradient, so splitting it exposes a 25-34 contamination
# of +3.559% against the +0.242% / +0.253% the two bands S reads carry (ruling X1 made S's read
# a population-weighted blend of both — see `_S_RIDES_BANDS`). `narrowest_feasible` now EQUALS
# `at_served_corner` because the most-contaminated band (25-34) withholds nothing at all — its
# interval is a point, so no feasible configuration can narrow the spread from that end.
_BAND_SPREAD_PP = {
    "at_served_corner": 3.3175415711008696,
    "at_subtract_most_corner": 3.368391505306024,
    "narrowest_feasible": 3.3175415711008696,
    "widest_feasible": 3.4993383689460975,
}
# P10's measurement on the RETIRED four-band lattice, kept as the reversal's warrant (see the
# module docstring). Asserted STRICTLY SMALLER than the served spread above, so "the refinement
# strengthened the reversal" is a checked claim and not a sentence.
_P10_FOUR_BAND_SPREAD_PP = 1.2024094264527192
_ALIGNED_ALL_AGES = 0.6972282443993753
# The 16 subdivisions' all-ages counts, which every one of them publishes in full.
_CSD_ALL_AGES_SUBTRACTION = (97_630, 151_160)

# --- the SUPPRESSION FOOTPRINT, by ADDRESS ---------------------------------------------
# 13 withheld cells, every one a TAIL cell (`75-84` / `85+` since ruling W split the retired
# `75+`), at 7 of the 16 subdivisions. The COUNT alone is not
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
# The subdivisions where a TAIL band withholds ONE field of the pair and publishes the other.
# This is what makes field-wise bounding load-bearing rather than hypothetical: at these,
# dropping the published field would net a territory's households out of one denominator and its
# owners out of another. At the other five of the seven, both fields of `85+` are withheld.
# PER BAND since ruling W split the tail: 2480065 withholds its `75 to 84 years` OWNER field
# while PUBLISHING that band's household field, so it is a half-pair inside `75-84` — a
# subdivision that was NOT a half-pair under the four-band lattice, because there its 85+
# household field was withheld too and the union's household field was therefore incomplete.
# The refinement moves one subdivision into the half-pair set and that is exactly why
# field-wise bounding has to be re-derived rather than carried.
_HALF_PAIR_CSDS = {"75-84": ("2480065",), "85+": ("2480140", "2483005")}
# Which FIELDS each suppressed band withholds — the property that decides whether its envelope
# is open above, below, or both. Derived from `_WITHHELD_ADDRESSES` by the gates, typed here as
# the oracle they check against.
_WITHHELD_FIELDS_BY_BAND = {"75-84": (_TENURE_OWNER,),
                            "85+": (_TENURE_OWNER, _TENURE_TOTAL)}
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

    The two cubes publish DIFFERENT age granularities of the same partition (15 dimension
    members vs 9), so the constituents cannot be shared — only the EDGES can. A band spec that
    drifted an edge would produce a perfectly plausible curve measured over a different age
    domain.

    THE FLOOR AND THE CEILING ARE ALSO GATED HERE, and since ruling W (2026-08-20) the lattice
    is SEVEN bands rather than four.

    "SEVEN IS THE FINEST COMMON PARTITION" IS MEASURED HERE, on this cube's own age-dimension
    member index, and until the 2026-08-21 audit it was NOT: this body advertised that check in
    its docstring and never read the cube's members at all — it compared two hand-typed band
    maps, which cannot tell a ten-year cube from a five-year one. `hors_aligned.py`'s own
    "of this cube's 9 age dimension members ... every one at or above 25 is TEN-year" and
    `census.py`'s "the CSD cube publishes only EIGHT age members and is TEN-YEAR inside 25-54"
    both stated the conclusion as verified fact with no gate under either. The gate is the third
    block below, and it reds on the case that matters: a re-pin whose cube publishes a five-year
    member inside the modeled span.

    HOW A MEMBER INDEX CAN CARRY THAT CLAIM AT ALL, given the extract is a PROJECTION (only the
    coordinates the pull asked for). Two facts the pull records make it total: the dimension's
    DECLARED member count, which `dimension_positions` spells in the dimension name itself
    (`... (9)`), and each requested member's own id. The seven modeled members hold ids that are
    CONSECUTIVE and run up to the declared last member, so no unrequested member can sit inside
    or above the modeled span: every id the pull did not request is strictly BELOW the first
    modeled id. A five-year re-cut of 25-54 would raise the declared count and break the run; a
    member inserted anywhere in the span would break consecutiveness.

    WHAT THAT DOES *NOT* SAY, weakened here on 2026-08-21 from a claim this body cannot support.
    It said the one unrequested id "IS the sub-25 member `census.OWNERSHIP_LATTICE_FLOOR`
    excludes" — two errors in one clause: that constant lives in `demand/formation.py`, not
    `census`, and NOTHING in the committed pull records what member id 2 denotes. The pull is a
    projection; it carries the ids it asked for, the declared total, and no label for the member
    it skipped. What is actually established is POSITIONAL — id 2 lies below the first modeled id
    and therefore below the modeled span — and "so it must be a sub-25 age member" is an
    inference from the lattice floor plus the cube's ascending age order, not a checked fact.
    That inference is not needed by anything: the legs below use only the positional statement,
    which is what makes the ten-year claim total over the span. Closing the label claim would
    take a re-pull that requests the member; it is not worth a network dependency for a fact
    nothing consumes.
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

    # --- the CUBE'S OWN age members, read from the committed pull.
    pull = _extract()["_pull"]
    spelled = [name for name in pull["dimension_positions"] if name.startswith(_AGE_DIMENSION)]
    assert len(spelled) == 1, f"the age dimension is spelled {spelled} in dimension_positions"
    declared = re.fullmatch(rf"{re.escape(_AGE_DIMENSION)} \((\d+)\)", spelled[0])
    assert declared, (
        f"the pull no longer records the age dimension's member COUNT ({spelled[0]!r}) — without "
        "it an unrequested member could sit above the modeled span unseen, and the ten-year "
        "claim below has no total to close against")
    declared_members = int(declared.group(1))

    ids = pull["member_ids"][_AGE_DIMENSION]
    assert set(ids) == {_ALL_AGES} | {m for band in _BAND_ORDER for m in _CD_BANDS[band]}, (
        f"the pull's age-member index is {sorted(ids)}, not the total plus this lattice's own "
        "seven members — the extract and the band spec are describing different cubes")

    banded = sorted((ids[m], m) for band in _BAND_ORDER for m in _CD_BANDS[band])
    assert [i for i, _ in banded] == list(range(banded[0][0], declared_members + 1)), (
        f"the modeled members hold ids {[i for i, _ in banded]} inside a {declared_members}-"
        "member dimension — they are no longer a CONSECUTIVE run ending at the dimension's last "
        "member, so this cube publishes an age member inside or above 25+ that the model does "
        "not read. Re-derive the finest COMMON partition before trusting the seven-band lattice")
    assert [m for _i, m in banded] == [m for band in _BAND_ORDER for m in _CD_BANDS[band]], (
        "the cube's member ids do not ascend with the model's band order — the id run above "
        "would then prove nothing about which ages lie between two bands")
    # POSITIONAL ONLY — see the docstring: the pull records no label for an id it did not
    # request, so this asserts where the unread member SITS and never what it denotes.
    unrequested = set(range(1, declared_members + 1)) - set(ids.values())
    assert all(i < banded[0][0] for i in unrequested), (
        f"member id(s) {sorted(unrequested)} were not pulled and do not sit below the modeled "
        f"floor (first modeled id {banded[0][0]}) — an unread member inside the span makes the "
        "seven bands a SELECTION rather than the cube's finest partition")

    # TEN-YEAR, member by member: every closed member spans exactly ten single years and the
    # one open member is the lattice's own open band. This is the claim `hors_aligned.py` and
    # `census.py` both state in prose, asserted on the labels the cube publishes.
    for label, lo, hi, members in hors_aligned.CD_BAND_SPEC:
        assert len(members) == 1, f"{label}: {members} — this cube publishes one member per band"
        member = members[0]
        closed = re.fullmatch(r"(\d+) to (\d+) years", member)
        if closed:
            m_lo, m_hi = int(closed.group(1)), int(closed.group(2))
            assert (m_lo, m_hi) == (lo, hi), (
                f"{label}: cube member {member!r} spans {(m_lo, m_hi)}, not the band's own "
                f"{(lo, hi)} — the rate would be measured over a different population")
            assert m_hi - m_lo + 1 == 10, (
                f"{label}: cube member {member!r} spans {m_hi - m_lo + 1} single years, not ten "
                "— this cube can express a finer partition than the model's, so `census.py`'s "
                "'ten-year is the finest COMMON partition' no longer holds and the lattice "
                "choice has to be re-derived rather than inherited")
        else:
            open_ended = re.fullmatch(r"(\d+) years and over", member)
            assert open_ended and int(open_ended.group(1)) == lo, (
                f"{label}: cube member {member!r} is neither a closed ten-year member nor this "
                f"band's open tail at {lo}")
            assert label == _BAND_ORDER[-1] and hi >= 200, (
                f"{label}: an open cube member on a band that is not the lattice's last")


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
        assert age in _TAIL_MEMBERS, (
            f"a band cell outside the tail is withheld ({code}/{age}) — the suppression "
            "footprint moved and the published envelope no longer describes it")


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

    # FIELD-WISE bounding is load-bearing, not hypothetical: at these subdivisions a suppressed
    # band withholds one field of the pair and PUBLISHES the other, so a per-address (rather
    # than per-field) rule would discard a published count.
    #
    # PER BAND since ruling W split the tail (2026-08-20). Under the four-band lattice this was
    # one set over the `75+` union; the split MOVES one subdivision into it — 2480065 publishes
    # its `75 to 84 years` household field while withholding that band's owner field, which the
    # union hid because its 85+ household field was withheld as well. A carried-forward literal
    # would have looked plausible and been wrong, so it is re-derived per band.
    per_band = {}
    for band in _BAND_ORDER:
        members = _CD_BANDS[band]
        in_band = [k for k in withheld if k[1] in members]
        if not in_band:
            continue
        codes_here = {code for code, _age, _tenure in in_band}
        per_band[band] = tuple(sorted(
            code for code in codes_here
            if len({tenure for c, _age, tenure in in_band if c == code}) == 1))
    assert per_band == _HALF_PAIR_CSDS, (
        f"the half-pair subdivisions moved: {per_band} vs {_HALF_PAIR_CSDS} — field-wise "
        "bounding is only load-bearing while some subdivision publishes one field of a pair")

    # WHICH FIELDS each suppressed band withholds. This decides the SHAPE of that band's
    # envelope (open above, below, or both), so it is pinned rather than left implicit — see
    # P11-11c, where a one-sided band makes `low < served < high` the wrong assertion.
    fields = {band: tuple(sorted({t for c, age, t in withheld if age in _CD_BANDS[band]}))
              for band in _BAND_ORDER if any(age in _CD_BANDS[band] for _c, age, _t in withheld)}
    assert fields == {b: tuple(sorted(f)) for b, f in _WITHHELD_FIELDS_BY_BAND.items()}, (
        f"the withheld FIELDS per band moved: {fields} vs {_WITHHELD_FIELDS_BY_BAND}")


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

    # THE REFINEMENT IS EXACT, asserted rather than assumed (operator ruling W, 2026-08-20).
    # The seven bands must re-aggregate, COUNT FOR COUNT, to the four the lattice published
    # before the split. This is the leg that catches a member leaking between two new bands or
    # being counted in both: every individual rate stays a plausible fraction under that
    # mutation, and the shipped-counts literals above would move with it only if the mutation
    # happened to change a band the test names.
    for retired, parts in _RETIRED_PARTITION.items():
        agg = (sum(shipped[b][0] for b in parts), sum(shipped[b][1] for b in parts))
        assert agg == _RETIRED_FOUR_BAND_COUNTS[retired], (
            f"the refined bands {parts} sum to {agg}, not the retired {retired} band's "
            f"{_RETIRED_FOUR_BAND_COUNTS[retired]} — the split is not a partition")


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
    # Carried through to the subtraction the derivation actually forms — PER TAIL BAND since
    # ruling W split `75+` (2026-08-20). Asserting only the union would let a subtraction that
    # put Gatineau's whole tail mass in ONE of the two bands pass, and the two bands are exactly
    # what the model now reads separately.
    bands = _artifact()["_provenance"]["bands"]
    for band, member in zip(("75-84", "85+"), ("75 to 84 years", "85 years and over")):
        assert bands[band]["subtracted_households"] >= \
            _PUBLISHED_CELLS[("2481017", member, _TENURE_TOTAL)], (
            f"{band}: the subtraction does not even contain CSD Gatineau's own published "
            f"{member} household count")
    # THE UNION FORM OF THE SAME CLAIM IS DELETED, entailment recorded (2026-08-21 audit). It
    # asserted the two bands' subtractions SUM to at least the two published cells' sum, which
    # follows termwise from the per-band `>=` loop three lines above: a >= c and b >= d give
    # a + b >= c + d for every value the fields can take. It could not red while the loop was
    # green (200k random states, 0 counterexamples), so it was a restatement, not a second check.
    # The per-band form is the STRONGER one and is what the model reads separately since ruling W
    # split the tail — which is exactly why the loop above replaced a union assert in the first
    # place.


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
            # THE BOUND MOVES ON EXACTLY THE FIELDS THAT ARE WITHHELD, and per field rather
            # than per band. Ruling W's tail split made that distinction load-bearing: `75-84`
            # withholds an OWNER field and no HOUSEHOLD field, so its bound subtracts more
            # owners and the SAME households — the old `aligned_bound_households <
            # aligned_households` form asserted a household move that cannot exist there and
            # would have failed a correct bound.
            if row["withheld_cells"]:
                fields = _WITHHELD_FIELDS_BY_BAND[band]
                assert (row["aligned_bound_owner_households"]
                        < row["aligned_owner_households"]) is (_TENURE_OWNER in fields), (
                    f"{source}: {band} withholds owner fields {_TENURE_OWNER in fields} but its "
                    "bound's owner subtraction does not follow")
                assert (row["aligned_bound_households"]
                        < row["aligned_households"]) is (_TENURE_TOTAL in fields), (
                    f"{source}: {band} withholds household fields {_TENURE_TOTAL in fields} but "
                    "its bound's household subtraction does not follow")
                # KEPT, and the reason is a CORRECTION of a 2026-08-21 audit finding that
                # reported this as entailed by the two implications above. It is entailed only
                # where exactly ONE field is withheld: with the owner field alone moving the
                # rate strictly falls, with the household field alone it strictly rises. `85+`
                # withholds BOTH (`_WITHHELD_FIELDS_BY_BAND`), and two simultaneous downward
                # moves CAN leave the rate fixed — (7254, 12242) has the same rate as the served
                # (18135, 30605) and satisfies both implications — so for that band this is a
                # live check, not a restatement. It stays for both bands rather than being
                # conditioned on the footprint: the condition would itself have to track which
                # fields are withheld, which is the thing under test.
                assert row["aligned_bound_rate"] != row["aligned_rate"], (
                    f"{source}: {band} withholds cells but its bound RATE equals the served rate "
                    f"({row['aligned_rate']}) — the owner and household subtractions cancelled "
                    "each other exactly, so the bound corner is indistinguishable from the "
                    "served point and this band's envelope has collapsed to a point. Reachable "
                    "only where BOTH fields are withheld (see the note above): with one field "
                    "alone the rate moves strictly, so at `75-84` this cannot be the cause. "
                    "MESSAGE CORRECTED 2026-08-21 — it read 'the bound subtracts no more than "
                    "the published-only sum', which belonged to the deleted "
                    "`aligned_bound_households < aligned_households` assert beside it and named "
                    "a household move rather than the rate identity this leg tests.")
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
    # `85+` is the band the constructed withheld cell sits in (the loop above withholds
    # `85 years and over`/Owner); under the retired four-band lattice this was `75+`.
    row = derived["_provenance"]["bands"]["85+"]
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
    # DERIVED from the two cubes' own member counts per band, never a tuned literal. Since
    # ruling W the lattice is seven bands, so this is checked at EVERY band rather than at one:
    # n_cma members x (province + 6 netted CMAs) + n_csd members x 16 subdivisions.
    for band in _BAND_ORDER:
        n_cma = len(next(m for lbl, _l, _h, m in census._AGE_BAND_SPEC if lbl == band))
        expected = n_cma * 7 + len(_CD_BANDS[band]) * len(_QC_PART_CSDS)
        assert rounding["rounded_cells_per_field"][band] == expected, band
        assert rounding["envelope_per_field"][band] == 2.5 * expected, band
    # The younger bands are two-member on the CMA side and one-member here; the tail bands are
    # one-member on both. A band that lost a constituent would move these counts.
    assert rounding["rounded_cells_per_field"]["25-34"] == 2 * 7 + 1 * 16 == 30
    assert rounding["rounded_cells_per_field"]["85+"] == 1 * 7 + 1 * 16 == 23
    assert "5" in rounding["note"]
    # The reversal's lineage, so a future reader does not "restore" #12(B).
    assert "12(B)" in prov["supersedes"] and "band-uniform" in prov["supersedes"]
    # Multiplicand: a household-denominated rate never multiplies a person count.
    assert "household" in prov["multiplicand_note"].lower()


# P11-15's vintage-accessor gate is DELETED with the accessor it tested (round-3 elegance
# audit, 2026-08-22): `loaders/vintage.py` and all three `load_*_vintage` readers had zero
# non-test callers, and spec §7's `data_vintage` is filled by `pipeline._source_hashes` off the
# artifact's own bytes. The two sources this artifact derives from are still asserted — as the
# provenance block's own recorded digests, in P11-14 above.


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
    note = flat((PROBES / "P10-hors-operand-alignment.md").read_text(encoding="utf-8"))
    assert f"{membership['cma_population']:,}" in note, (
        "the recorded CMA population is not the one P10's note records")
    # AND THE SPLIT, EACH SIDE BOUND TO ITS SIDE (2026-08-21 class sweep). The arithmetic
    # (Québec + Ontario == CMA) is asserted above; what was NOT asserted is that the NOTE
    # attaches each figure to the right side, and swapping them there is the whole confusion
    # this surface exists to remove — the Québec side is the slice being subtracted.
    assert (f"with the Québec side at {membership['quebec_side_population']:,} and the Ontario "
            f"side at {membership['ontario_side_population']:,}") in note, (
        f"P10's note does not bind each side of the CMA to its own population — expected the "
        f"Québec side at {membership['quebec_side_population']:,} and the Ontario side at "
        f"{membership['ontario_side_population']:,}, in that order")
    # AND ONE POPULATION PER SIDE. The clause above closes the swap and the drop; this closes
    # the addition, which no contiguous-substring check can see.
    for side, pattern in (("the Québec side", r"Québec side at ([\d,]+)"),
                          ("the Ontario side", r"Ontario side at ([\d,]+)")):
        # IGNORECASE (run 48): the ADDITION this leg exists for is exactly what a
        # case-sensitive pattern cannot see — "the QUÉBEC SIDE AT 9,999,999" beside the true
        # clause left this set a singleton and shipped.
        found = set(re.findall(pattern, note, re.IGNORECASE))
        assert len(found) == 1, (
            f"P10's note attaches {sorted(found)} to {side} — one population per side, or the "
            "subtraction this surface performs has two candidate operands")
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
    question separately), so an age-20 lookup that quietly served the lattice's lowest band
    (`25-34`, and `25-54` before ruling W) would answer a question this surface has not measured.
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
    thinned = {Geography.HORS_RMR.value: {"25-34": 0.69}}
    assert hors_aligned.aligned_ownership_rate(
        thinned, Geography.HORS_RMR, 30) == pytest.approx(0.69)
    with pytest.raises(LoaderError, match="no aligned ownership rate .* band 75-84"):
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
    # `25-34` -> `25-29`: the youngest band's upper edge, which is the drift the four-band
    # docstring illustrated as "25-49 instead of 25-54". The edge moved is still invisible in
    # every rate — that is the point of the guard.
    drifted = tuple((label, lo, 29 if label == "25-34" else hi, members)
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
    and still handed back a confident vintage record. That is precisely the split-legs incident
    `census._read_verified_ownership` records as measured on 2026-08-14 and fixed by moving the
    completeness check onto the shared path — the rationale `_read_verified`'s own docstring
    cites while not, until now, implementing it.

    P11-8 gates the join on the COMMITTED bytes; a test defends the repo, not a runtime load.
    EVERY accessor must refuse, or one of them states a confident answer about a curve no run
    may use — and the set below is the live one: the vintage accessor that used to be its third
    member is deleted, and the union accessor was never in it.
    """
    d = tmp_path / name.replace(" ", "_")
    d.mkdir()
    _artifact_in(d, mutate)
    for accessor in (hors_aligned.load_aligned_ownership_rates,
                     hors_aligned.load_aligned_ownership_join,
                     lambda dd: hors_aligned.aligned_ownership_union(25, 54, data_dir=dd)):
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
                # WHICH SIDE IS OPEN IS DECIDED BY WHICH FIELD IS WITHHELD, and the four-band
                # lattice could not see the difference: its one suppressed band withheld BOTH
                # fields, so `low < served < high` held and looked like the general rule.
                # Ruling W's tail split produced `75-84`, whose only withheld field is an OWNER
                # field — there is no withheld household to subtract MORE of, so its HIGH corner
                # coincides with the served rate and the envelope is [low, served]. Asserting
                # strict two-sidedness there would red a CORRECT bound. The real invariant is
                # the implication, and it is asserted in both directions so a bound that moved
                # the wrong corner cannot pass either.
                fields = _WITHHELD_FIELDS_BY_BAND[band]
                assert (lo < row["aligned_rate"]) is (_TENURE_OWNER in fields), (
                    f"{source}: {band} withholds owner fields {_TENURE_OWNER in fields}, so the "
                    f"LOW corner {lo} must sit strictly below the served {row['aligned_rate']} "
                    "iff it does")
                assert (row["aligned_rate"] < hi) is (_TENURE_TOTAL in fields), (
                    f"{source}: {band} withholds household fields {_TENURE_TOTAL in fields}, so "
                    f"the HIGH corner {hi} must sit strictly above the served "
                    f"{row['aligned_rate']} iff it does")
                assert lo < hi, (
                    f"{source}: {band} withholds {row['withheld_cells']} cells but its "
                    "envelope is degenerate — an uncertain band with no interval")

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
    same-signed and adversarially arranged at every corner of the box.

    THE ARRANGEMENT IS NAMED BY ROLE, NOT BY LABEL, since ruling W (2026-08-20). The claim is
    "the band D_native is built from is more contaminated than what S reads" — a statement about
    two model reads, not about two spellings. Under the retired four-band lattice those were
    `25-54` and `75+`; they are now `_D_NATIVE_BAND` and `_S_RIDES_BANDS`, and the refinement
    made the gap WIDER (3.318 pp against P10's 1.202), which is asserted below so that "the
    refinement strengthened the reversal" is checked rather than narrated.

    S READS BOTH TAIL BANDS SINCE RULING X1 (2026-08-21), so the S half of the arrangement is
    asserted over the PAIR rather than at one label — `_standing_stock` values the lumped 75+
    bucket at the population-weighted mean of the per-age rates and reads ownership at no single
    age. That needs no weight pin: δ_S is a MEDIANT of the two tail bands' contaminations
    (`_S_RIDES_BANDS`' comment carries the two-line proof), so bounding BOTH tail bands bounds
    every feasible weighting of the blend. The legs below therefore take the worst corner over
    the pair, which is strictly stronger than the retired single-label form and does not have to
    be re-derived if the 75+ population mix moves.
    """
    prov = _artifact()["_provenance"]
    env = prov["suppression"]["envelope"]
    assert env["band_spread_pp"] == pytest.approx(_BAND_SPREAD_PP, rel=1e-12)
    assert env["all_bands_same_signed_across_the_box"] is True

    spread = env["band_spread_pp"]
    assert spread["narrowest_feasible"] > 1.0, (
        "the band spread's WORST feasible case has collapsed below a percentage point — "
        "#12(B)'s band-uniformity premise would need re-measuring, not restoring")
    # The narrowest and the served corner COINCIDE under the refined lattice, and that is a
    # property of the data rather than an accident: the most contaminated band (25-34)
    # withholds nothing, so its interval is a point and no feasible configuration of the
    # withheld cells can narrow the spread from the top end. `<=` below therefore holds with
    # equality — stated here so a future reader does not read it as slack.
    assert spread["narrowest_feasible"] == spread["at_served_corner"], (
        "the most contaminated band now carries withheld cells, so the narrowest feasible "
        "spread has parted from the served corner — re-derive which band bounds the spread")
    # ONLY THE UPPER HALF REMAINS. `narrowest_feasible <= at_served_corner` is entailed by the
    # `==` asserted five lines above (2026-08-21 audit), so it could not red while that one was
    # green; `at_served_corner <= widest_feasible` is NOT entailed by anything here and is the
    # half that says the served corner sits inside its own box.
    assert spread["at_served_corner"] <= spread["widest_feasible"], (
        "the served corner is above the box it is meant to sit in")
    assert spread["narrowest_feasible"] <= spread["at_subtract_most_corner"] <= \
        spread["widest_feasible"]

    # ADVERSARIAL ARRANGEMENT, at the worst corner: the band D_native is built from must remain
    # more contaminated than ANYTHING S can read, or the sign of (δ_D − δ_S) — not just its
    # size — would be a function of the suppression. S reads a mediant of the two tail bands
    # (ruling X1), so the worst corner over the PAIR bounds every feasible weighting.
    bands = prov["bands"]
    worst_for_d = min(bands[_D_NATIVE_BAND]["relative_delta_envelope_low_pct"],
                      bands[_D_NATIVE_BAND]["relative_delta_envelope_high_pct"])
    best_for_s = max(bands[b][k] for b in _S_RIDES_BANDS
                     for k in ("relative_delta_envelope_low_pct",
                               "relative_delta_envelope_high_pct"))
    assert worst_for_d > best_for_s, (
        f"at the corner least favourable to the finding, {_D_NATIVE_BAND} is no longer more "
        f"contaminated than every band in {_S_RIDES_BANDS} ({worst_for_d} vs {best_for_s}) — "
        "the adverse arrangement is not robust to the suppression")
    # AND D's band is the MOST contaminated of all seven while BOTH bands S reads are BELOW
    # every band it does not — the strong form, and the form that survives X1: a mediant of the
    # two smallest SERVED deltas is smaller than every other band's, whatever the weights, so
    # δ_D − δ_S is LARGE and same-signed rather than merely positive.
    #
    # TWO THINGS THIS COMMENT CLAIMED AND NO LONGER DOES (2026-08-21). It said the difference
    # "sits at or near the FULL spread" (operator ruling X7): measured on D_native's own weights
    # it is 1.999 pp against the 3.318 pp served spread, ~60% of it — large, same-signed and
    # adversarially arranged, which is all #12(B)'s band-uniformity premise needs, but never the
    # whole spread. And the ordering asserted below is a SERVED-VALUE property (operator ruling
    # X6): at the 85+ envelope-HIGH corner that band alone rises to +0.384%, above 45-54's
    # +0.273%, so the corner ordering is NOT weight-free — and its weighting is OWNER-POPULATION,
    # `pop(a)*rho(a)`, never households. Both are gated in `tests/test_pipeline.py`
    # (`test_x7_the_band_difference_is_MEASURED_and_is_not_the_FULL_spread` and
    # `test_x6_the_tail_ordering_is_a_SERVED_property_and_the_weighting_is_OWNER_POPULATION`),
    # which is where the ISQ population frame the owner-population weighting needs is reachable.
    served = {b: bands[b]["relative_delta_pct"] for b in _BAND_ORDER}
    assert max(served, key=served.get) == _D_NATIVE_BAND, (
        f"the adverse arrangement no longer runs D-band-most: {served}")
    s_side = [served[b] for b in _S_RIDES_BANDS]
    others = [served[b] for b in _BAND_ORDER if b not in _S_RIDES_BANDS]
    assert max(s_side) < min(others), (
        f"the bands S reads {_S_RIDES_BANDS} are no longer the LEAST contaminated of the seven "
        f"AT SERVED VALUES ({s_side} against {others}) — a weighted blend of them could then "
        "exceed another band's contamination at the served point too, and the S half of the "
        "arrangement would depend on the 75+ age mix rather than on the lattice. (At the 85+"
        " suppression HIGH corner it already does; that limit is documented and gated in "
        "`tests/test_pipeline.py`, not here.)")
    # THE BLEND'S VALUE. It is the quantity the module docstring and `_provenance.supersedes`
    # both restate, and a restated number with no gate under it is how the pre-X1 sentence went
    # stale. The rel=1e-12 pin is the whole gate here: it moves if either tail band's delta or
    # either household weight moves.
    #
    # THE MEDIANT CONTAINMENT `min(s_side) <= blend <= max(s_side)` STOOD HERE AND WAS DELETED
    # (2026-08-21 audit). `blend` is a convex combination of `s_side` whose weights are HOUSEHOLD
    # COUNTS — strictly positive at 110,150 / 30,605 — so the containment is entailed by
    # arithmetic at every nonneg weight pair and the assert could not fail under any artifact
    # this suite would otherwise accept: a self-documenting no-op of the class this arc deleted
    # at three other sites. THE ENTAILMENT WORTH RECORDING is that the claim the argument
    # actually rests on is STRICTER and is asserted weight-independently a few lines above —
    # `max(s_side) < min(others)`, which entails `blend < min(others)` because a mediant of
    # `s_side` cannot exceed `max(s_side)`. Deleting the weaker restatement loses no coverage.
    weights = [bands[b]["aligned_households"] for b in _S_RIDES_BANDS]
    blend = sum(w * d for w, d in zip(weights, s_side)) / sum(weights)
    assert blend == pytest.approx(0.2441105582854595, rel=1e-12), (
        f"the household-weighted tail blend is {blend}, not the +0.2441106% the module docstring "
        "and `supersedes` restate — re-derive both")
    # THE REFINEMENT STRENGTHENED THE REVERSAL, checked against P10's four-band measurement.
    assert spread["narrowest_feasible"] > _P10_FOUR_BAND_SPREAD_PP, (
        f"the refined lattice's WORST feasible spread {spread['narrowest_feasible']} no longer "
        f"exceeds P10's four-band measurement {_P10_FOUR_BAND_SPREAD_PP} — the claim that "
        "splitting the coarse bands sharpened the #12(B) refutation needs re-measuring")
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
    # ONE DISJUNCT, because the second WIDENED this gate rather than case-folding it. A sweep
    # table recorded `"not bracket" in bound.lower()` as a case-insensitive restatement of the
    # first clause; it is not — it drops the OBJECT. Measured 2026-08-21: rewriting the note to
    # "...and they do not bracket the SUBTRACTION..." satisfied the second disjunct and shipped
    # GREEN while stating a falsehood, because those two corners ARE the subtraction extremes
    # and the claim this line exists to require — that they are not the RATE's bracket — was
    # absent from the note entirely.
    assert "do NOT bracket the rate" in bound, (
        "`suppression.bound` still presents the subtraction corners as the rate's bracket")
    note = prov["suppression"]["envelope"]["note"]
    assert "OFF-DIAGONAL" in note, "the envelope note never states OFF-DIAGONAL"
    # ATTAINABLE and OUTER are NOT interchangeable and were gated as bare fragments until
    # 2026-08-21: with both words merely PRESENT, swapping which corner carries which — the LOW
    # corner "exactly ATTAINABLE", the HIGH one "a CONSERVATIVE OUTER bound" — passed, and that
    # swap is the exact falsehood this paragraph exists to prevent (the HIGH corner is attained
    # because no cell withholds a household field while publishing its owner field; the LOW one
    # needs positive withheld owners inside cells whose withheld households are zero, so it is
    # an outer bound and nothing more). Bound to the corner, and to one corner each.
    corners = bound_map(note, {"the HIGH corner": r"The HIGH corner is",
                               "the LOW corner": r"The LOW corner is"},
                        r"exactly ATTAINABLE|a CONSERVATIVE OUTER bound",
                        after=r" ", before=None)
    assert corners == {"the HIGH corner": {"exactly ATTAINABLE"},
                       "the LOW corner": {"a CONSERVATIVE OUTER bound"}}, (
        f"the envelope note attaches {corners} to the two corners. The HIGH corner is the "
        "ATTAINABLE one and the LOW corner is the CONSERVATIVE OUTER bound; either word on the "
        "wrong corner, or a second claim adding the other word to a corner that already has "
        "one, states an envelope this extract does not have")
    assert "every corner" in prov["supersedes"], (
        "the reversal record does not say the spread survives the whole feasible box")

    # The MODULE DOCSTRING's own figures, traced to the computed ones. It states the box range
    # in prose, and prose does not move when the extract is re-pinned — this is the gate that
    # makes it move.
    doc = flat(hors_aligned.__doc__)
    spread = prov["suppression"]["envelope"]["band_spread_pp"]
    # THE BOX RANGE AS AN ORDERED CLAUSE, not two digit strings anywhere in the text. Under the
    # retired `f"{spread[key]:.3f}" in doc` loop the docstring could print the range BACKWARDS —
    # "runs 3.499-3.318 pp" — and stay green with both endpoints present; and `narrowest_feasible`
    # equals the served corner here, so its digits occur three more times in the paragraph, which
    # is the occurrence-selective hole: dropping the one that states the RANGE left the others.
    # The f-string fixes the order and the clause fixes the site.
    assert f"runs {spread['narrowest_feasible']:.3f}-{spread['widest_feasible']:.3f} pp" in doc, (
        f"the module docstring no longer states the feasible box as the ordered range "
        f"{spread['narrowest_feasible']:.3f}-{spread['widest_feasible']:.3f} pp — a narrative "
        "figure has parted from the measurement, or the endpoints have been transposed")
    # And the two corners the same sentence names, each bound to ITS corner. `at_served_corner`
    # and `at_subtract_most_corner` were quoted in the prose and gated by nothing.
    named = bound_map(doc, {"the served corner": r"the served corner",
                            "the subtract-most corner": r"the subtract-most corner"},
                      PP_ABS, after=None)
    assert named == {"the served corner": {f"{spread['at_served_corner']:.3f} pp"},
                     "the subtract-most corner":
                         {f"{spread['at_subtract_most_corner']:.3f} pp"}}, (
        f"the docstring attaches {named} to the two named corners; this extract measures "
        f"{spread['at_served_corner']:.3f} pp at the served corner and "
        f"{spread['at_subtract_most_corner']:.3f} pp at the subtract-most one")
    # The docstring's worked example of the envelope defect. Since ruling W the illustrative
    # band is `85+` — the only band that still withholds BOTH fields, so it is the only one
    # where the off-diagonal corner can sit outside the diagonal pair at all. `75-84`'s
    # one-sided suppression cannot produce that shape, which is why the example moved rather
    # than being restated at the retired union.
    example_band = "85+"
    tail = _artifact()["_provenance"]["bands"][example_band]
    hi_85 = tail["relative_delta_envelope_high_pct"]
    served_85 = tail["relative_delta_pct"]
    # BOUND TO THE ROLE EACH PLAYS IN THE EXAMPLE. `+{hi} in doc and +{served} in doc` was
    # satisfied by the two figures appearing anywhere, so transposing them — the feasible MAXIMUM
    # reported as the diagonal pair's upper END and vice versa — inverted the whole worked example
    # and stayed green. That inversion says the off-diagonal corner sits INSIDE the diagonal pair,
    # which is the defect the example exists to show.
    # THE BAND IS PART OF THE EXAMPLE, not context around it. With the two figures bound to
    # their roles but the band free, RELABELLING the example to `75-84` shipped GREEN (measured
    # 2026-08-21) — and 75-84 is the band whose envelope is one-sided, so the relabelled example
    # is contradicted by this same docstring two lines later ("`75-84`'s one-sided suppression
    # cannot produce this shape at all") and by the artifact, whose 75-84 envelope has no
    # off-diagonal corner to sit outside anything. The band is named once here and required
    # inside the label, so the prose cannot move the example without moving the measurement.
    example = bound_map(doc, {"the feasible maximum":
                                  rf"at `{re.escape(example_band)}`, whose feasible maximum",
                              "the diagonal pair's upper end": r"pair's upper end"},
                        PCT_SIGNED)
    assert example == {"the feasible maximum": {f"+{hi_85:.3f}%"},
                       "the diagonal pair's upper end": {f"+{served_85:.3f}%"}}, (
        f"the docstring's worked example of the envelope defect attaches {example}; 85+'s "
        f"feasible maximum is +{hi_85:.3f}% and the diagonal pair's upper end is "
        f"+{served_85:.3f}%, and the example only says anything if the first EXCEEDS the second")
    assert hi_85 > served_85, (
        f"85+'s feasible maximum {hi_85} no longer exceeds the diagonal pair's upper end "
        f"{served_85} — the worked example has to move to a band where it does")
    # AND THE DIRECTION WORD OF THE COMPARISON, which no map on this page can read. With both
    # figures bound to their roles and the band pulled inside the label, "lies well above" ->
    # "lies well below" still shipped the FULL SUITE GREEN (measured 2026-08-21). That
    # comparison IS the warrant: it is why the 85+ corner is TWO-SIDED and why the diagonal pair
    # is not the envelope, so BELOW there deletes the entire reason four corners are published
    # while leaving every figure correctly attributed and the assert above still passing. The
    # word is DERIVED from that assert.
    lies = "above" if hi_85 > served_85 else "below"
    defect = (rf"at `{re.escape(example_band)}`, whose feasible maximum "
              rf"\({re.escape(f'+{hi_85:.3f}%')}\) lies well {lies} the "
              rf"subtract-most/subtract-least pair's upper end "
              rf"\({re.escape(f'+{served_85:.3f}%')}\)")
    assert re.search(defect, doc), (
        f"the docstring's worked example no longer states that {example_band}'s feasible maximum "
        f"+{hi_85:.3f}% lies well {lies} the subtract-most/subtract-least pair's upper end "
        f"+{served_85:.3f}%. The direction word carries the warrant for publishing the "
        "OFF-diagonal corners at all; with it free the sentence reads as the diagonal pair being "
        "a sound bracket, which is the exact defect this example exists to show")
    # AND THE ENVELOPE'S COVERAGE LIMIT, in BOTH copies of that claim. OUTSIDE is the whole
    # content of "Publishing only the diagonal pair would state an interval the true value can
    # sit OUTSIDE", and it was gated by nothing: -> INSIDE shipped the FULL SUITE GREEN in the
    # docstring and the emitted note together (measured 2026-08-21), converting the REASON the
    # off-diagonal pair exists into a claim that the diagonal pair already covers the true
    # value. Both copies are required — the emitted one is what a reader of the artifact meets,
    # and it is the copy no compiler ever loads.
    sits = "OUTSIDE" if hi_85 > served_85 else "INSIDE"
    limit = f"would state an interval the true value can sit {sits}"
    for whose, text in (("the module docstring", doc),
                        ("the emitted `_provenance.suppression.envelope.note`", note)):
        assert limit in flat(text), (
            f"{whose} no longer states the envelope's coverage limit as {limit!r}. The worked "
            f"example in this same record puts {example_band}'s feasible maximum +{hi_85:.3f}% "
            f"beyond the diagonal pair's upper end +{served_85:.3f}%, so INSIDE is refuted by "
            "the record's own figures — and that limit is the only reason "
            "`aligned_envelope_high_rate` and `aligned_envelope_low_rate` are published beside "
            "the subtraction pair")
    # AND THE MONOTONICITY THE CORNER CHOICE IS DERIVED FROM — the same pivot-word class as the
    # `NUMERATOR` leg in `tests/test_pipeline.py`'s X6 test, found by this run's sweep rather
    # than in its ranked list. `rate = (S_o - s_o)/(S_t - s_t)` FALLS in the subtracted owners
    # and RISES in the subtracted households, and THAT PAIR is what puts the rate's extremes at
    # the OFF-DIAGONAL corners. Swapping the two verbs derives the DIAGONAL corners instead —
    # the exact defect run 25 review measured — while the "OFF-DIAGONAL" conclusion stands in
    # the same sentence, so the record hands a reader a derivation that refutes its own
    # conclusion. Measured 2026-08-21: the docstring copy alone shipped GREEN across all 63
    # tests in this file, and it changes no emitted byte, so no golden or vintage gate can reach
    # it. Both copies are required; the verbs are LITERAL because the monotonicity is a property
    # of a FIXED formula, not a measured datum that can drift — the behavioural half is
    # `test_p11_11c`, which re-derives the four corners from the artifact's own counts.
    for whose, text in (("the module docstring", doc),
                        ("the emitted `_provenance.suppression.envelope.note`", note)):
        assert re.search(r"(?:FALLS|falls) in the subtracted owners and (?:RISES|rises) in the "
                         r"subtracted households, so the rate's extremes sit at the "
                         r"OFF-DIAGONAL corners", flat(text)), (
            f"{whose} no longer derives the envelope from the rate's monotonicity — expected "
            "`falls in the subtracted owners and rises in the subtracted households, so the "
            "rate's extremes sit at the OFF-DIAGONAL corners` (either case). Those two verbs "
            "ARE the derivation: subtracting owners cuts the numerator and subtracting "
            "households cuts the denominator, so the extremes are the OFF-diagonal pair. "
            "Swapped, the same sentence derives the DIAGONAL pair — the run-25 defect — and "
            "then contradicts itself in its own final clause")

    # THE ADVERSE-ARRANGEMENT FIGURES the docstring restates in prose, since operator ruling X1
    # made S's read a blend of both tail bands. This gate exists because that paragraph went
    # STALE exactly once: it published "the least (75-84) is the one S rides through
    # initialize_households AT pipeline.ROLL_AGE" after X1 had removed that read, and nothing
    # moved when the mechanism did. Every figure the paragraph now states is computed here.
    all_bands = _artifact()["_provenance"]["bands"]
    served = {b: all_bands[b]["relative_delta_pct"] for b in _BAND_ORDER}
    next_lowest = min(v for b, v in served.items() if b not in _S_RIDES_BANDS)
    # EVERY BAND, BOUND TO ITS OWN CONTAMINATION — and the bands the paragraph states no figure
    # for asserted to state none. The retired `f"+{served[band]:.3f}%" in doc` loop asked only
    # whether each figure appeared SOMEWHERE, so swapping 75-84's +0.242% with 85+'s +0.253%
    # shipped green, as did adding a false pair for a band the paragraph never mentions. Which
    # band carries which contamination is the whole adverse-arrangement argument: the most
    # contaminated band is the one D_native weights most, the two least are the two S reads.
    bands_pct = {b: rf"`?{re.escape(b)}`?" for b in _BAND_ORDER}
    want = {b: set() for b in _BAND_ORDER}
    for band in (*_S_RIDES_BANDS, "45-54", "25-34"):
        want[band] = {f"+{served[band]:.3f}%"}
    observed = bound_map(doc, bands_pct, PCT_SIGNED)
    assert observed == want, (
        f"the docstring's adverse-arrangement paragraph attaches "
        f"{ {k: sorted(v) for k, v in observed.items() if v != want[k]} } to those bands; this "
        f"extract measures { {k: sorted(v) for k, v in want.items() if v != observed[k]} }. The "
        "S half of the arrangement rests on WHICH bands are least contaminated, so a figure on "
        "the wrong band, a dropped one and an added false pair are all the same defect")
    assert next_lowest == served["45-54"], (
        f"the next-lowest non-tail band is no longer 45-54 — the figure the tail blend has to "
        f"stay below is {next_lowest} and 45-54 carries {served['45-54']}, so the paragraph "
        "names the wrong band and the expected map above is about a different claim")
    # THE TAIL BLEND AND THE TWO COUNTS IT IS FORMED AT are gated in
    # `tests/test_pipeline.py`'s ruling-X6 test, NOT here. The ordered clause stood at this line
    # against `hors_aligned.__doc__` alone, and the reversal record has THREE copies which
    # hard-wrap the sentence differently, so this one anchor reached exactly one of them: a
    # COORDINATED swap of 110,150 and 30,605 in `_SUPERSEDES` and in the emitted
    # `_provenance.supersedes` shipped GREEN (measured 2026-08-21 through `gen_hors_aligned.py`,
    # so the fresh-derivation and byte-for-byte gates were satisfied as well), and the PUBLISHED
    # record then formed the blend at 85+'s count first. The X6 test already loops over all
    # three copies of that record, which is why the clause belongs in that loop and not in a
    # single-surface assert here.


# --- P11-19: ruling X2's ALIGNED lumped-range aggregate -------------------------------------
#
# WHY THIS BLOCK EXISTS. `aligned_ownership_union` shipped with no test that asserted anything
# about it: two reviewers found the only mention of the name in the suite was a non-asserted
# shim inside another test's stub reader. It is the rate HORS_RMR's immigrant leg is MULTIPLIED
# BY once per (leg, geography, scenario) — so an unpinned value here is an unpinned decision-critical
# number.
# The golden would move if it moved, but `scripts/gen_golden.py` re-ratifies whatever the code
# emits, so the golden records the number and cannot gate it.
_ALIGNED_UNION_SPAN = (25, 54)
_ALIGNED_UNION_RATE = 0.6901488081776652
# The census-net residual over the same span, which HORS_RMR does NOT read. Named as a NEGATIVE:
# both are plausible HORS_RMR ownership fractions ~1 pp apart, and serving the wrong one is the
# exact defect the whole operand-alignment surface exists to remove.
_CENSUS_NET_UNION_RATE = 0.6804520271369382


def test_p11_19_the_aligned_lumped_range_union_is_the_SERVED_counts_divided_once():
    """The union over whole bands, from this artifact's own SERVED counts — never a bound corner
    and never a mean of the band rates.

    THE ORACLE IS ARITHMETIC ON THE PUBLISHED CELLS, so the leg cannot be satisfied by a
    plausible fraction: a producer that averaged the three band rates, tiled a different span,
    or reached for `aligned_bound_*` reds against the counts rather than against a literal.
    """
    lo, hi = _ALIGNED_UNION_SPAN
    bands = _artifact()["_provenance"]["bands"]
    labels = [b[0] for b in census.bands_spanning(lo, hi)]
    assert labels == ["25-34", "35-44", "45-54"], labels
    owner = sum(bands[b]["aligned_owner_households"] for b in labels)
    total = sum(bands[b]["aligned_households"] for b in labels)
    served = hors_aligned.aligned_ownership_union(lo, hi)
    assert served == pytest.approx(owner / total, rel=1e-15)
    assert served == pytest.approx(_ALIGNED_UNION_RATE, rel=1e-15)

    # NOT the bound pair — the served subtraction, the same one the band rates beside it use.
    bound_owner = sum(bands[b]["aligned_bound_owner_households"] for b in labels)
    bound_total = sum(bands[b]["aligned_bound_households"] for b in labels)
    assert (bound_owner, bound_total) == (owner, total), (
        "the 25-54 span now carries withheld cells, so served and bound have parted — the "
        "union must still be the SERVED pair and this leg needs re-deriving, not relaxing")

    # NOT a mean of the three band rates, and NOT the census-net territory.
    mean_of_rates = sum(bands[b]["aligned_rate"] for b in labels) / len(labels)
    assert served != pytest.approx(mean_of_rates, rel=1e-9), (
        f"the aligned union is the unweighted mean of its band rates ({mean_of_rates})")
    assert served != pytest.approx(_CENSUS_NET_UNION_RATE, rel=1e-9), (
        "HORS_RMR's aligned union equals the CENSUS-NET union — the 16 Québec-side "
        "Ottawa-Gatineau subdivisions are no longer being subtracted from the span")
    assert served > _CENSUS_NET_UNION_RATE, (
        "the aligned union sits BELOW the census-net one, reversing the measured direction of "
        "the contamination on every band of this span")


def test_p11_19b_the_aligned_union_REFUSES_rather_than_serving_a_shorter_span(tmp_path):
    """The refusal branches, which were hand-verified and gated by nothing.

    Each one is a DIFFERENT silent failure: a span the lattice does not tile would be measured
    over the wrong population; a missing `bands` object or a missing constituent band would make
    the union a shorter span rather than a smaller number, and a shorter span is still a
    plausible fraction. The messages are discriminated, not merely counted as raises.
    """
    lo, hi = _ALIGNED_UNION_SPAN
    # The span guard is `census.bands_spanning`'s, reached THROUGH this accessor.
    with pytest.raises(LoaderError, match="EXACT union"):
        hors_aligned.aligned_ownership_union(25, 50)
    with pytest.raises(LoaderError, match="no modeled ownership band"):
        hors_aligned.aligned_ownership_union(26, 33)

    cases = {
        "no bands object": (lambda p: p["_provenance"].pop("bands"), "not an object"),
        "bands not an object": (lambda p: p["_provenance"].__setitem__("bands", []),
                                "not an object"),
        "a constituent band missing": (lambda p: p["_provenance"]["bands"].pop("35-44"),
                                       "is absent"),
        "a count missing": (lambda p: p["_provenance"]["bands"]["45-54"].pop(
            "aligned_owner_households"), "not a count"),
        "a count is a float": (lambda p: p["_provenance"]["bands"]["25-34"].__setitem__(
            "aligned_households", 123760.0), "not a count"),
    }
    for name, (mutate, expected) in cases.items():
        out = tmp_path / name.replace(" ", "_")
        out.mkdir()
        where = _artifact_in(out, mutate)
        with pytest.raises(LoaderError, match=expected):
            hors_aligned.aligned_ownership_union(lo, hi, data_dir=where)
        # ... and it is not a lucky raise from the verification that runs first.
        assert hors_aligned.aligned_ownership_union(lo, hi) == pytest.approx(
            _ALIGNED_UNION_RATE, rel=1e-15), f"{name}: the committed artifact stopped serving"


# --- P11-20: the MECHANISM sentence, tripwired ---------------------------------------------
#
# WHY THIS BLOCK EXISTS, and it is this arc's signature failure mode rather than a new one.
# `test_p11_11e` gates every FIGURE the #12(B) reversal paragraph restates — the band deltas,
# the tail blend, the household weights, the envelope endpoints — so a stale NUMBER reds. It
# gates no SENTENCE. The paragraph's MECHANISM clause went stale exactly once, on 2026-08-21:
# it published "the least (75-84) is the one S rides through initialize_households AT
# pipeline.ROLL_AGE" after operator ruling X1 had removed that read, and NOTHING MOVED WHEN THE
# MECHANISM DID. Two reviewers then grepped the suite for that sentence's vocabulary and found
# the only test-side hits were inside a COMMENT — a note describing the staleness, with no
# assertion under it. The remedy landed for numbers and not for prose, so this is the prose half.
#
# WHAT IS IN SCOPE: `hors_aligned`'s module docstring, its `_SUPERSEDES` source constant, and
# the string `_SUPERSEDES` is EMITTED as — `_provenance.supersedes` in the committed artifact,
# which is the copy a downstream reader actually meets and the reason this is not merely a
# docstring hygiene test.
#
# WHAT IS DELIBERATELY OUT OF SCOPE, so this cannot false-positive on correct history. The
# module docstring's four-band paragraph SAYS the retired thing in the PAST TENSE and marks it
# ("the least (75+) the one S then RODE through `initialize_households` at `pipeline.ROLL_AGE`
# — a read operator ruling X1 has since removed, so that clause is HISTORY and not mechanism").
# `probes/run_p10.py` likewise writes "S rides ρ(75+) through `initialize_households`" into its
# own 2026-08-15 report, which is a DATED WARRANT measured on the four-band lattice and must
# keep saying what it measured. Neither is scanned. A reversal whose warrant has been
# overwritten cannot be audited, so the history is protected here rather than forbidden.
_MECHANISM_PRESENT = (
    # The correction itself, in the emitted string and in the source constant.
    "S does NOT read a band at pipeline.ROLL_AGE",
    "POPULATION-WEIGHTED mean of the per-age rates over the ages it holds",
    "ROLL_AGE still carries the hazard",
)
# The PRESENT-TENSE spellings that would put the retired read back. The first is the exact
# sentence that shipped stale; the rest are the other ways the same claim gets written here.
_MECHANISM_FORBIDDEN = (
    "S rides the 75-84 band at pipeline.ROLL_AGE",
    "is the one S rides through initialize_households",
    "S rides ρ(75+)",
    "S reads ownership at pipeline.ROLL_AGE",
    "S reads a band at pipeline.ROLL_AGE",
    "the one S rides through",
)


def _normalized(text: str) -> str:
    """Whitespace collapsed to single spaces, so a forbidden sentence cannot hide in a LINE
    BREAK. Every string scanned here is hard-wrapped prose — `_SUPERSEDES` is a parenthesized
    concatenation of ~40 source lines and the module docstring wraps at 96 columns — so a raw
    substring test would be evaded by the reflow that any edit to this prose causes anyway.
    That is not a hypothetical: the sentence this tripwire exists for spanned two source lines
    in both of the places it was written."""
    return " ".join(text.split())


def test_p11_20_the_mechanism_sentence_cannot_reacquire_the_retired_ROLL_AGE_READ():
    """The MECHANISM half of the reversal record, in all three copies of it.

    TWO LEGS, AND THE POSITIVE ONE IS THE LOAD-BEARING HALF. The forbidden-spelling leg is a
    REVERT TRIPWIRE in `tests/test_constants.py`'s sense — it names the exact sentences the
    claim has actually been written as, and a mutant spelled some other way walks past it. The
    REQUIRED leg is what makes rewording and DELETION red too: the correction has to still be
    stated, so an edit that drops it rather than reverting it does not pass by saying nothing.
    Prose cannot be gated behaviourally — the string IS the artifact here; what IS gated
    behaviourally is the read itself, by ruling X1's wiring pins in `tests/test_pipeline.py`.
    """
    emitted = _artifact()["_provenance"]["supersedes"]
    surfaces = {
        "hors_aligned.__doc__": _normalized(hors_aligned.__doc__),
        "hors_aligned._SUPERSEDES": _normalized(hors_aligned._SUPERSEDES),
        "artifact _provenance.supersedes": _normalized(emitted),
    }
    # The emitted copy must BE the source constant, or the tripwire guards the wrong bytes.
    assert surfaces["artifact _provenance.supersedes"] == surfaces["hors_aligned._SUPERSEDES"], (
        "the committed artifact's `supersedes` is no longer the string `_SUPERSEDES` builds — "
        "re-mint with `uv run python scripts/gen_hors_aligned.py`")

    for name, text in surfaces.items():
        for gone in _MECHANISM_FORBIDDEN:
            # `says` rather than `_normalized(...) not in ...` (run 48): this list is a REVERT
            # TRIPWIRE, and a revert re-typed in the emphasis capitals this corpus uses
            # everywhere — "S RIDES ρ(75+)" — walked past every one of the six. Case folding is
            # safe for this list SPECIFICALLY because each member is a PRESENT-TENSE sentence
            # and the history the message below asks for is past-tense: the four-band paragraph
            # that quotes retired wordings does not spell any of these six, in any casing
            # (measured on the ratified bytes before this was widened).
            assert not says(text, gone), (
                f"{name} states {gone!r} in the PRESENT TENSE. Operator ruling X1 (2026-08-21) "
                "removed that read: `_standing_stock` values the lumped 75+ bucket at the "
                "population-weighted mean over the ages it holds, so no single age selects an "
                "ownership band and `ROLL_AGE` carries the hazard and the living-arrangement "
                "read alone. If this is HISTORY, mark it past-tense and say which ruling "
                "retired it, the way the four-band paragraph does")

    for required in _MECHANISM_PRESENT:
        for name in ("hors_aligned._SUPERSEDES", "artifact _provenance.supersedes"):
            assert _normalized(required) in surfaces[name], (
                f"{name} no longer states {required!r} — the reversal record has stopped saying "
                "HOW S reads ownership. A future editor meeting this note would have to infer "
                "it, and the inference it invites is the read ruling X1 removed")
    assert "stopped `_standing_stock` reading ownership at `pipeline.ROLL_AGE`" in (
        surfaces["hors_aligned.__doc__"]), (
        "the module docstring no longer names the ruling-X1 change in its adverse-arrangement "
        "paragraph — the figures around it are gated by test_p11_11e and would stay green")


def test_p11_20b_D_native_reads_FIVE_bands_and_the_record_says_so():
    """The other exclusivity this record carried: "the most contaminated band (25-34) is THE ONE
    D_native is built from", corrected 2026-08-21.

    IT IS FALSE AS EXCLUSIVITY AND TRUE AS WEIGHT CONCENTRATION. `native_formation` sums ages
    `AGE_MIN`..`AGE_BOUNDARY`-1 (18..74), so it reads FIVE of the seven bands — 25-34 through
    65-74 — and never either tail band. The band set is DERIVED here from the model's own
    constants rather than typed, so a lattice or floor change moves this assertion instead of
    quietly invalidating the sentence it defends.

    WHY 25-34 CARRIES THE WEIGHT is a separate, documented mechanism and not an exclusivity:
    `formation._ownership` returns 0.0 below `OWNERSHIP_LATTICE_FLOOR`, so ages 18-24 contribute
    EXACTLY zero and the formation gains pile on the first ages the lattice admits. That is
    stated in `demand/formation.py` and pinned there; this gate holds the band COUNT, which is
    what the reversal record's sentence gets wrong when it gets it wrong.
    """
    from demoflow.demand.formation import AGE_BOUNDARY, AGE_MIN, OWNERSHIP_LATTICE_FLOOR
    from demoflow.loaders.census import bands_spanning

    assert (AGE_MIN, AGE_BOUNDARY) == (18, 75), "D_native's age span moved — re-derive below"
    read_bands = [b[0] for b in bands_spanning(OWNERSHIP_LATTICE_FLOOR, AGE_BOUNDARY - 1)]
    # ONE EXACT LIST EQUALITY, and nothing may be restated after it. `len(read_bands) == 5` and
    # `not ({"75-84", "85+"} & set(read_bands))` stood below and were DELETED (2026-08-21 audit).
    # THE ENTAILMENT: a list equality fixes the length AND the membership, so neither could red
    # while this line was green — self-documenting no-ops of exactly the class this run deleted
    # at four other sites, introduced in the same commit that deleted those. What they SAID is
    # folded into the message, because the why is the part a future reader needs: five is the
    # count the reversal record gets wrong when it gets it wrong, and disjointness from the two
    # tail bands S reads is what the adverse-arrangement argument rests on.
    assert read_bands == ["25-34", "35-44", "45-54", "55-64", "65-74"], (
        f"the bands D_native reads are now {read_bands} — the reversal record names FIVE, and it "
        "needs them DISJOINT from the two tail bands S reads (75-84, 85+). A tail band in that "
        "list means the adverse-arrangement argument needs re-measuring, not re-wording")

    for name, text in (("_SUPERSEDES", hors_aligned._SUPERSEDES),
                       ("artifact", _artifact()["_provenance"]["supersedes"]),
                       ("module docstring", hors_aligned.__doc__)):
        flat = _normalized(text)
        assert "five bands" in flat.lower(), (
            f"{name} no longer says, in words, that D_native reads FIVE bands — the count is the "
            "thing the retired sentence got wrong, so it is the thing that has to be stated")
        # CASE-FOLDED, mirroring the `"five bands" in flat.lower()` leg two lines up — that
        # asymmetry was the defect: the REQUIRED half of this pair tolerated any casing while
        # the FORBID half did not, so "25-34 IS THE ONE D_NATIVE IS BUILT FROM," satisfied both.
        assert not says(flat, "is the one D_native is built from,"), (
            f"{name} states the 25-34 band as THE ONE D_native is built from. It reads FIVE "
            f"({read_bands}); 25-34 is the most heavily WEIGHTED of them, which is a "
            "concentration and not an exclusivity")


def test_the_withheld_field_bound_states_WHICH_DIRECTION_it_bounds_in():
    """The suppression bound's DIRECTION, in both records that state it.

    "Each withheld field is bounded ABOVE by ..." was gated by nothing: flipping ABOVE to BELOW
    shipped the FULL SUITE GREEN (measured 2026-08-21, 1187 passed). That one word is the premise
    of everything downstream of it — `SUPPRESSION IS BOUNDED, NEVER DROPPED` needs the bound to
    CONTAIN the missing cell, `aligned_bound_rate` is the subtract-MOST corner only because the
    charge is an upper bound, and the four-corner envelope is built by pairing that corner
    against the served one. BELOW there leaves the whole construction resting on a quantity the
    withheld cell could exceed.

    THE DIRECTION IS A TEST-OWNED LITERAL, and that is deliberate rather than lazy: it CANNOT be
    derived from the artifact, because the unpublished remainder is the SAME NUMBER under either
    reading of it. What makes it an UPPER bound is a fact about the withheld cell and not about
    the remainder — StatCan withholds SMALL counts, so ZERO is feasible for every suppressed
    cell, and a strictly positive charge therefore cannot be a lower bound on it. Pinning the
    word here follows this file's standing convention (see the module docstring's TEST-OWNED
    ORACLE note) and it is what closes the flip.

    WHAT THE THREE NUMERIC LEGS ADD, since the word alone would be a bare literal match. They
    make the claim NON-VACUOUS and they can each fail: the charge is non-negative (a negative one
    would make the bound corner subtract LESS than the served one, which contradicts its
    definition), it is strictly positive somewhere (a bound on an identically-zero quantity
    claims nothing, and an extract that published every cell would need the paragraph rewritten
    rather than gated), and the two DIAGONAL corners sit inside the OFF-DIAGONAL envelope at
    every band — which is the observable consequence of the charge bounding the cell at all.

    AND THE SAME WORD IN THE PUBLISHED RECORD. `_provenance.suppression.bound` states it as
    `FIELD-WISE upper bound` and was also ungated, so both copies are required: a flip in either
    one alone reds here, and a coordinated flip in both is a REGENERATION, which is PR-visible as
    artifact byte changes.
    """
    DIRECTION, WORD = "ABOVE", "upper"          # TEST-OWNED — see the docstring above
    prov = _artifact()["_provenance"]
    bands = prov["bands"]
    charges = {label: (row["aligned_households"] - row["aligned_bound_households"],
                       row["aligned_owner_households"] - row["aligned_bound_owner_households"])
               for label, row in bands.items()}
    assert all(h >= 0 and o >= 0 for h, o in charges.values()), (
        f"a withheld-field charge is NEGATIVE ({charges}) — the bound corner would then "
        "subtract LESS than the served one, and it is defined as the subtract-MOST corner")
    positive = {label: pair for label, pair in charges.items() if max(pair) > 0}
    assert positive, (
        "no band charges anything for a withheld field, so the direction claim below is about a "
        "quantity that is identically zero and this gate would assert nothing. If the extract "
        "now publishes every cell, rewrite the suppression paragraph rather than this leg")
    clause = (f"Each withheld field is bounded {DIRECTION} by a quantity the same cube DOES "
              "publish")
    assert clause in flat(hors_aligned.__doc__), (
        f"the module docstring no longer states {clause!r}. The bands that withhold charge a "
        f"strictly positive remainder ({positive}) and ZERO is feasible for every suppressed "
        "cell, so the charge can only be an UPPER bound on it. The other direction inverts the "
        "premise the four-corner envelope and `SUPPRESSION IS BOUNDED, NEVER DROPPED` both rest "
        "on — restate the source, not this line")
    assert f"FIELD-WISE {WORD} bound" in prov["suppression"]["bound"], (
        f"the PUBLISHED `suppression.bound` no longer states the charge as a `FIELD-WISE {WORD} "
        "bound`. That is the same claim as the docstring clause above; stating one direction in "
        "the emitted record and the other in the docstring is the shape a reader cannot resolve")

    # THE CONSEQUENCE THAT MAKES THE DIRECTION LOAD-BEARING, measured rather than restated:
    # because the charge is an UPPER bound, the two DIAGONAL corners (served = subtract least on
    # both fields, bound = subtract most on both) are INTERIOR to the OFF-DIAGONAL envelope at
    # every band. A charge that did not bound the cell would put the feasible rate outside that
    # bracket, which is the defect FOUR CORNERS exists to document.
    for label, row in bands.items():
        lo, hi = row["aligned_envelope_low_rate"], row["aligned_envelope_high_rate"]
        diagonal = (row["aligned_rate"], row["aligned_bound_rate"])
        assert lo <= min(diagonal) and max(diagonal) <= hi, (
            f"{label}: the diagonal pair {diagonal} is not inside the off-diagonal envelope "
            f"[{lo}, {hi}]. The envelope is the RATE's extremes only if each withheld field is "
            "bounded above by the charge the bound corner subtracts")
