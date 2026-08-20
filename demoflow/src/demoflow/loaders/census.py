"""Census ownership + headship loaders (spec §8/§7). Ownership: owner-maintainer
rate by geography x age band, STRICT full-geography join, fractions asserted in
[0,1]; HORS_RMR is province net of ALL SIX WHOLLY-QUÉBEC CMAs (codex r4-F2) — the
precise denotation, and NOT the same territory as ISQ's literal hors-RMR population
row, both recorded in _provenance. Headship: base-year households/person at every SINGLE
YEAR of age 0-100, graduated from the 14 published maintainer-age members (operator ruling V,
2026-08-19; PIT-fixed, §7 r3-F3).

DERIVATION, NEVER TRANSCRIPTION (steering ruling B, 2026-07-25): every rate is computed —
ownership by `derive_ownership_from_csv` from the pinned P2 extract, headship by
`derive_headship_from_sources` from that extract AND the pinned ISQ QC-total pop workbook.
Both JSONs under `data/` are BUILD ARTIFACTS of `scripts/gen_ownership.py` /
`scripts/gen_headship.py`, never hand-edited, and a regen-equality gate proves each equals a
fresh derivation. NO rate is hand-written anywhere in this package.

HEADSHIP IS DERIVED AT ITS USE SITE (T13b, 2026-08-08 — DIV F1 was a LIVE DEFECT). Until
then `data/headship_by_age.json` carried six TYPED `borrowed_prior` rates, on the theory that
their persons-denominator was out of ruling B's reach until the pop loader landed (plan Task 13
Step 1b). Measured against the pinned sources they did not reproduce: 35-54 was 16.9% low, the
65-74 -> 75+ shape was INVERTED, and the aggregate understated QC households by 9.5%
(3,393,953 vs the published 3,749,035) — adverse in BOTH directions, overstating 75+ release
while understating the absorbers. The USE SITE settles the semantics: spec:395
`OwnerStock(g,t,s) = Σ_over_all_ages pop(a,g,t,s) × headship(a) × ownership(a)` multiplies ISQ
scenario POPULATION, so headship is
    QC private-household PRIMARY MAINTAINERS  (committed P2 Census extract)
    ÷ ISQ 2021 Le Québec Référence (A2026) PERSONS  (committed pop-as-qc-base.xlsx)
and nothing else. T13b read BOTH sides at the six model bands and served the band rate flat at
every age inside it; since operator ruling V (2026-08-19) each side is read at its FINEST
published resolution — the 14 maintainer-age MEMBERS against the 101 single-year person
denominators — and the value at a single age is a GRADUATION that closes exactly on every
member, never a band rate reused at each age (`derive_headship_from_sources`). Both sources are
sha256-pinned and read at derivation.

STALENESS REFUSES AT LOAD (steering ruling L, 2026-08-08): a no-drift gate is a TEST — it
defends the repo, not a runtime load. So `load_ownership_rates` and `load_headship_rates`
independently check the artifact's recorded source digests against the pins registry on EVERY
load and raise on an absent or mismatched one. Two legs, neither subsuming the other: CI
compares CONTENT (artifact vs fresh derivation), the load path compares IDENTITY (recorded
source digests vs the pins). A stale or unprovenanced artifact never serves rates.

THE UPSTREAM RAW ANCHOR (T13b PART 2, DIV F2): all of the above compares CO-MOVING objects —
re-cut the extract and its pin, the artifacts and a fresh derivation all move with it. So both
artifacts also carry `pins.raw_anchor(CENSUS_EXTRACT)`, the digest of the 850MB raw StatCan
member the extract was filtered from, which a re-extract CANNOT move without a deliberate
re-pin (pins.py carries the full argument).

ANCHOR-TYPED PROVENANCE: constants.py's charter rule — "every constant carries its documented
anchor (source + figure + date); a constant without an anchor is a defect" — is ENFORCED here,
not stated: every headship AND ownership rate is instantiated as a `constants.Anchor` built
from the artifact's OWN `as_of`/`source`, at derivation and again at load, so an undated or
uncited curve serves nothing. Ownership joined the rule on 2026-08-13 (DIV carry: it was the
one rate surface without it, recording a `ref_date` that nothing read and typing nothing);
`as_of` REPLACED that key rather than joining it — one date, spelled the way `Anchor` spells
it, because two spellings of one field is a second declaration site and only one of them
would have been load-bearing.

VINTAGE AT THE BOUNDARY (run-6 carry, 2026-08-13): both loaders return their rate sub-tree
and DROP `_provenance`, which is fine for a test and not fine for the first production
consumer — spec §7's artifact envelope has to publish `data_vintage.source_hashes` for these
exact surfaces. `load_ownership_vintage` / `load_headship_vintage` hand back the typed
`RateVintage` for what was loaded, running the SAME verification the rate loaders run so the
two can never disagree about a stale artifact (a stateable vintage for rates that would be
refused is worse than no vintage at all).
"""
import csv
import json
import math
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.constants import Anchor
from demoflow.loaders.isq_ages import build_single_year_long
from demoflow.loaders.pins import (
    DATA_DIR,
    RAW_SOURCE_MEMBER,
    WORKBOOK_SHA256,
    raw_anchor,
    raw_member,
    verify_pin,
)
from demoflow.loaders.validate import assert_fraction
from demoflow.loaders.vintage import RateVintage, vintage_from_provenance

CENSUS_EXTRACT = "census_tenure_age_98100231.csv"
# The cube the extract was cut from. PUBLIC because the operand-aligned surface
# (`loaders/hors_aligned.py`) names this table beside its own CD/CSD sibling in one provenance
# block, and two spellings of one table number is a drift vector.
STATCAN_TABLE = "98-10-0231-01"
POP_QC_WORKBOOK = "pop-as-qc-base.xlsx"
OWNERSHIP_ARTIFACT = "ownership_by_geo_age.json"
HEADSHIP_ARTIFACT = "headship_by_age.json"

# --- P2 extract structure -----------------------------------------------------------
# POSITIONAL bindings, never csv.DictReader: the extract re-emits StatCan's raw header
# verbatim, which carries FOUR duplicate `Symbol` columns — a dict reader collapses them
# and mangles the tenure columns. Positions are asserted against the LIVE header at read
# time (`_check_header`); that assertion IS the schema-drift gate.
_COL_GEO = 1
_COL_STRUCT = 3
_COL_CONDO = 4
_COL_HHTYPE = 5
_COL_STAT = 6
_COL_AGE = 7
_COL_TOTAL = 9
_COL_OWNER = 11

_EXPECTED_HEADER = {
    _COL_GEO: "GEO",
    _COL_STRUCT: "Structural type of dwelling (10)",
    _COL_CONDO: "Condominium status (3)",
    _COL_HHTYPE: "Household type including census family structure (16)",
    _COL_STAT: "Statistics (3C)",
    _COL_AGE: "Age of primary household maintainer (15)",
    _COL_TOTAL: "Tenure (4):Total - Tenure[1]",
    _COL_OWNER: "Tenure (4):Owner[2]",
}

# The rate's cell is the `Total -` member of every non-age dimension, at the single
# household-count statistic — the same slice the spec oracle (113,730 / 202,535) names.
_TOTAL_MEMBERS = {
    _COL_STRUCT: "Total - Structural type of dwelling",
    _COL_CONDO: "Total - Condominium status",
    _COL_HHTYPE: "Total - Household type including census family structure",
}
_STATISTIC = "Number of private households"

_PROVINCE = "Quebec"
_MTL_CMA = "Montréal (CMA), Que."
_QC_CMA = "Québec (CMA), Que."
# The six WHOLLY-QUÉBEC CMAs (children of the Québec member in 98-10-0231-01's own metadata;
# probe P2 §3/§4). HORS_RMR = province NET OF ALL OF THESE (codex r4-F2): netting only MTL+QC
# would fold the other four RMRs into hors-RMR. Ottawa-Gatineau is NOT here and is NOT netted —
# it is parented to Ontario and publishes no separable Québec-part row, so its Québec side is
# INSEPARABLE and sits inside the residual (see _CA_CAVEAT / _ISQ_TERRITORY_NOTE). This tuple is
# therefore load-bearing, and `_read_totals_cube` asserts the extract's GEO set equals exactly
# {province} | these — a NEW CMA appearing upstream reds rather than silently un-netted.
_QC_CMAS = (
    "Drummondville (CMA), Que.",
    _MTL_CMA,
    _QC_CMA,
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
)

# Model band -> (lo, hi, fine cube members). SUM owner and total counts across the
# constituents THEN divide — never an average of rates. `75+` has NO single member in the
# cube: it is `75 to 84 years` + `85 years and over`, and both must be present or the
# derivation raises.
_AGE_BAND_SPEC = (
    ("25-54", 25, 54, ("25 to 29 years", "30 to 34 years", "35 to 39 years",
                       "40 to 44 years", "45 to 49 years", "50 to 54 years")),
    ("55-64", 55, 64, ("55 to 59 years", "60 to 64 years")),
    ("65-74", 65, 74, ("65 to 69 years", "70 to 74 years")),
    ("75+", 75, 200, ("75 to 84 years", "85 years and over")),
)
# Lookup bands derive FROM the derivation spec (one source of truth: a band label present
# for lookup but absent from the derivation, or vice versa, is unrepresentable).
_AGE_BANDS = tuple((label, lo, hi) for label, lo, hi, _ in _AGE_BAND_SPEC)

# (the headship member spec lives below `_POP_TERMINAL_AGE`, which closes its open member)

# The extract's own published all-ages maintainer count — an INDEPENDENT aggregate the banded
# sum must close against (a dropped or duplicated constituent moves the sum by >= 10,920, the
# smallest member, while every rate stays a plausible fraction). PUBLIC because the
# operand-aligned extraction (`loaders/hors_aligned.py`) reads the same member off the same
# cube: two spellings of one member label in one package is a drift vector.
MAINTAINER_TOTAL_MEMBER = "Total - Age of primary household maintainer"

# ISQ denominator selection. The base year is the PIT anchor (spec §7 r3-F3: base-year Census
# rates held constant), and `Référence (A2026)` is the reference fan; sex code 3 is ISQ's
# published both-sexes row and is cross-checked against codes 1+2 at read time.
_POP_LABEL = "Le Québec"
_POP_SCENARIO = "Référence (A2026)"
_POP_BASE_YEAR = 2021
_POP_BASE_STATUS = "r"                      # réel — measured 2026-08-08 for 2021
_POP_SEX_TOTAL = 3
_POP_SEX_PARTS = (1, 2)
_POP_TERMINAL_AGE = 100                     # single-year block span (isq_ages: 100+ capped)

# --- the AGE-RESOLVED headship curve (operator ruling V, 2026-08-19) -----------------------
#
# WHAT THIS REPLACED AND WHY. Until this change the curve was SIX bands materialised flat at
# single years of age, and `_zero_support_note` forbade that reuse in its own words. The
# pre-PR quant gate measured the cost: 68-100% of `D_native` at MTL_RMR was band-step
# artifact, ~2.5x the entire ranked signal, and the 0-19 band asserted 8,304 private
# households maintained by someone aged 0-14 while understating 15-19 by 4.17x. Both are pure
# INTRA-band misallocation, which is why `numerator_closure` stayed green throughout.
#
# THE PUBLISHED GRANULARITY, AND THE ONE FACT EVERY CLASSICAL METHOD BREAKS ON. The extract's
# `Age of primary household maintainer (15)` dimension carries a total plus FOURTEEN age
# members. TWELVE are five-year (15-19 … 70-74); `75 to 84 years` is TEN-year and
# `85 years and over` is OPEN-ENDED — it closes at `_POP_TERMINAL_AGE` only because the ISQ
# denominator closes there (both open ends coincide; the curve is NOT extended past 100).
# Sprague, Beers and Karup-King-Newton are defined for UNIFORM five-year panels, so all three
# are refused here rather than applied to a panel they do not fit — the granularity degrades
# exactly where the supply side lives.
_HEADSHIP_MEMBER_SPEC = (
    ("15 to 19 years", 15, 19),
    ("20 to 24 years", 20, 24),
    ("25 to 29 years", 25, 29),
    ("30 to 34 years", 30, 34),
    ("35 to 39 years", 35, 39),
    ("40 to 44 years", 40, 44),
    ("45 to 49 years", 45, 49),
    ("50 to 54 years", 50, 54),
    ("55 to 59 years", 55, 59),
    ("60 to 64 years", 60, 64),
    ("65 to 69 years", 65, 69),
    ("70 to 74 years", 70, 74),
    ("75 to 84 years", 75, 84),                 # TEN-year
    ("85 years and over", 85, _POP_TERMINAL_AGE),   # open-ended; closed by the denominator
)
# The DECLARED under-15 member. It is not published: it is the only value the closure residual
# admits (see `_zero_support_note`), and it enters as a member so the zero floor is a property
# of the construction rather than a value bolted on after it.
_HEADSHIP_ZERO_MEMBER = ("under 15 (declared, closure-bounded)", 0, 14)

# The SIX legacy bands, kept for provenance and for the C3 identity gate — never a lookup path.
# Their members are DERIVED by containment from the member spec above (one source of truth), so
# a member cannot exist for the curve and be missing from `band_members`. Every band is an
# EXACT union of published members, which is why per-member closure SUBSUMES the band identity
# instead of merely coexisting with it.
_HEADSHIP_LEGACY_BAND_SPEC = (
    ("0-19", 0, 19), ("20-34", 20, 34), ("35-54", 35, 54),
    ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, _POP_TERMINAL_AGE),
)

# The two CARRIED shape arms, one `rule` argument apart, both member-exact. They are a SWEEP
# AXIS, not a preference: the design panel measured the tangent-rule arm spread at 0.00026 …
# 0.00052 of ED per geography — LARGER than the whole cross-family spread — and
# non-common-mode, so a `rank_stable` verdict blind to it would be a verdict over a grid it
# never varied. `constants.SWEEP_GRID` declares the SELECTION; this tuple declares the
# CONSTRUCTION, and `tests/test_pipeline.py` binds the two.
# (artifact shape key, tangent rule) — ONE declaration, so the rule can never be inferred from
# the key by string surgery and then silently disagree with it.
_HEADSHIP_SHAPE_SPEC = (("expo_cum_fc", "fc"), ("expo_cum_fb", "fb"))
HEADSHIP_SHAPES = tuple(shape for shape, _rule in _HEADSHIP_SHAPE_SPEC)
HEADSHIP_CENTRAL_SHAPE = HEADSHIP_SHAPES[0]
# WHY THERE IS NO THIRD ARM — the 85-100 interior is priced by NO sweep leg, and that is a
# DECISION with a measurement behind it, not an omission. The design panel also carried a
# TERMINAL-KNOT arm (flat/central/steep declared end knot for the open member, which is where
# the whole 85-100 shape assumption lives) and dropped it on measured grounds: those arms move
# OwnerStock 0% (2021) -> 0.11% (2051) -> 0.15% (2071) and move D_native NOT AT ALL — the
# `formation.AGE_BOUNDARY = 75` cut means no formation term ever reads that interior — for a
# resulting ΔED <= 1e-5, 30-50x below the shape-family effect and below the tangent-rule spread
# recorded above. A sweep leg costs a full pipeline run, so an axis that cannot move the ranked
# quantity buys cost and no verdict. THAT FIGURE IS CITED, NOT COMPUTED HERE, and it therefore
# stays OUT of the artifact deliberately: it is the panel's, measured at its stated probe
# fidelity (raw ISQ in place of P_resident, ~7% scale, no immigrant leg), whereas `_shape_note`
# rides the artifact digest and carries ONLY figures this generator computes on this vintage —
# and this generator has no ED machinery to recompute it. What the artifact does state, in
# `_shape_note`'s own words, is the consequence: the 85-100 interior is a stated, accepted
# exposure whose weight GROWS across the horizon. Re-derive this figure before ever citing it
# as a live-pipeline result; the direction is robust, the level is not.
# The construction is EXACT, so this is not a tuned tolerance: it is the float-noise band a
# refactor may move within. It is deliberately NOT bit-equality — the measured 0.0 is an
# observation about this vintage's arithmetic, not an IEEE theorem (the design panel's P2
# proposed a 1e-15 relative gate that FAILED on P2's own curve at 3.99e-15; a gate that cannot
# pass its own construction is worse than no gate).
_HEADSHIP_CLOSURE_TOLERANCE = 1e-6

# RA-level rows are not in this CMA-level table, so each borrows its parent CMA's COMPUTED
# rate (spec §8). All five borrow MTL_RMR: this understates island vs overstates couronne
# ownership, a known v0 imprecision the flag documents (couronne precision deferred —
# §11.6 / P6 MRC hunt).
_BORROWS_FROM = {
    Geography.MTL_ISLAND_RA06: Geography.MTL_RMR,
    Geography.LAVAL_RA13: Geography.MTL_RMR,
    Geography.LANAUDIERE_RA14_PROXY: Geography.MTL_RMR,
    Geography.LAURENTIDES_RA15_PROXY: Geography.MTL_RMR,
    Geography.MONTEREGIE_RA16_PROXY: Geography.MTL_RMR,
}

_CA_CAVEAT = (
    "HORS_RMR here denotes: Québec outside the six WHOLLY-QUÉBEC CMAs — INCLUDING all 23 "
    "Census Agglomerations AND the Québec side of Ottawa-Gatineau, plus the Québec parts of "
    "the two cross-border CAs (Campbellton, N.B./Que.; Hawkesbury, Ont./Que.). Ottawa-Gatineau "
    "is parented to Ontario in 98-10-0231-01's own metadata and the table publishes no "
    "separable Québec-part row, so its Québec side is INSEPARABLE here and falls inside the "
    "residual; the same holds for the two cross-border CAs. A published StatCan 'non-CMA/CA' "
    "row would EXCLUDE the Census Agglomerations, but no such row is carried for Québec, so "
    "the residual is COMPUTED and the sentence above is the geography HORS_RMR actually "
    "denotes (spec §11 item 2, codex r5-F7; probe P2 §4 verbatim denotation)."
)
_ISQ_TERRITORY_NOTE = (
    "TERRITORY MISMATCH, MEASURED 2026-08-08 — this rate's territory is NOT the territory of "
    "the HORS_RMR population it will multiply. ISQ's pop-as-rmr-base.xlsx publishes "
    "\"RMR d'Ottawa-Gatineau\" as Québec-part-only (workbook footnote 2, 'Partie québécoise "
    "uniquement'), so its literal 'Territoire hors des RMR' row EXCLUDES the Québec side of "
    "Ottawa-Gatineau — while this Census residual INCLUDES it, because the Census table cannot "
    "separate it. Ottawa-Gatineau is therefore SEPARABLE on the ISQ side and INSEPARABLE on the "
    "Census side: the mismatch is structural, not incidental. Magnitudes (2021, Référence "
    "(A2026), both sexes, pop-as-rmr-base.xlsx): Le Québec 8,572,020 minus the six wholly-QC "
    "RMRs 5,831,474 = 2,740,546 persons (this rate's territory) vs the ISQ literal row "
    "2,384,575 persons (the population the rate multiplies); the 355,971-person gap is exactly "
    "the ISQ Ottawa-Gatineau Québec-part row = 12.99% of the Census residual territory / "
    "14.93% of the ISQ hors-RMR population. RECORDED, NOT RESOLVED: the rate x population join "
    "is downstream of this loader, and reconciling the two territories is a decision for that "
    "task, not a silent correction here."
)
_ROUNDING_NOTE = (
    "StatCan rounds counts to the nearest 5, so dimension components do not reconcile "
    "exactly to their totals. Owner/Total is computed directly from the banded sums; no "
    "reconciliation is asserted and no correction is applied."
)

# --- multiplicand notes (run-6 carry, 2026-08-13) -------------------------------------
# THREE rate surfaces in this package take THREE different multiplicands, and every
# difference is invisible in the numbers: each product stays a plausible magnitude under the
# wrong operand. Demand (spec §6) is the first production consumer of two of them, so the
# rule is recorded ON the artifacts rather than in a reader's head, and every use site states
# which one it is using.
_HEADSHIP_MULTIPLICAND_NOTE = (
    "WHAT THIS CURVE MAY MULTIPLY: its denominator is RAW ISQ published persons by single "
    "year of age (pop-as-qc-base.xlsx, Le Québec, Référence (A2026), base year 2021), which "
    "INCLUDES COLLECTIVE/institutional residents — ISQ publishes them, and this rate was "
    "derived over that denominator. So headship(a) must multiply population on that SAME raw "
    "basis: the ISQ scenario population, or spec §6's P_resident decomposition of it (P_ISQ "
    "minus surviving arrival cohorts, still raw). The collective share MUST NOT BE REMOVED "
    "first — removing it understates households by construction, since those residents sit in "
    "the denominator that produced the rate. This DIFFERS BY DESIGN from "
    "living_arrangement.json, whose per-sex partition rates are denominated in "
    "PRIVATE-HOUSEHOLD PERSONS and whose consumer therefore strips "
    "CONSTANTS['collective_share_75plus'] FIRST (see that artifact's own multiplicand_note "
    "and cohort/init.py). Two adjacent surfaces, two multiplicands: applying either rule to "
    "the other surface is a silent double-count or a silent undercount. "
    "AGE-RESOLVING THIS CURVE MADE THAT UNIFICATION MORE TEMPTING, AND IT IS STILL REFUSED: "
    "since operator ruling V the tail is single-year across 75-100, finer than "
    "living_arrangement.json's 75+ cohort rather than coarser than it, so the two surfaces "
    "now share an age grid and the last superficial reason to keep them apart is gone — but "
    "the reason that always mattered is the DENOMINATOR, not the granularity, and it did not "
    "move: a shared grid does not make raw-ISQ persons and private-household persons the same "
    "multiplicand."
)
_OWNERSHIP_MULTIPLICAND_NOTE = (
    "WHAT THIS RATE MAY MULTIPLY: owner-maintainer HOUSEHOLDS / total private HOUSEHOLDS — a "
    "household-denominated rate, so its multiplicand is a household count, never a person "
    "count (spec §6, codex r2-F2: persons never multiply a household rate directly; the "
    "person -> household step is headship's job, immigrant headship's on the arrival leg). "
    "Both legs of demand hold to that: native formation multiplies a headship-converted "
    "household gain, and the immigrant chain converts arriving PERSONS to HOUSEHOLDS before "
    "any ownership propensity is applied."
)


# --- derivation (ruling B) ----------------------------------------------------------

def _count(raw: str, ctx: str) -> int:
    """Parse one StatCan count cell under THIS module's error taxonomy. A bare int()
    leaks ValueError — a class no `except LoaderError` catches — on exactly the
    malformation (a suppressed or blanked cell) the gate exists to surface."""
    text = str(raw).strip()
    try:
        value = int(text)
    except (TypeError, ValueError) as exc:
        raise LoaderError(f"{ctx}: non-integer household count {raw!r}") from exc
    if value < 0:
        raise LoaderError(f"{ctx}: negative household count {value}")
    return value


def _check_header(header: list[str], csv_path: Path) -> None:
    """Assert the positional bindings against the live header — schema drift is fail-loud."""
    for position, expected in _EXPECTED_HEADER.items():
        if position >= len(header):
            raise LoaderError(
                f"{csv_path.name}: header has {len(header)} columns, expected column "
                f"{position} to be {expected!r} (schema drift?)")
        if header[position] != expected:
            raise LoaderError(
                f"{csv_path.name}: header position {position} is {header[position]!r}, "
                f"expected {expected!r} (schema drift?)")


def _raise_for_empty_slice(csv_path: Path, seen_statistics: set, seen_members: dict) -> None:
    """The slice predicate matched NOTHING — name the member that is actually absent.

    MEASURED 2026-08-08 (DIV F3): a renamed `Statistics (3C)` member or a renamed `Total -`
    member skips every row, and the only surviving check was the GEO-set gate, which then
    raised "GEO set is [], expected [the seven geographies]" — sending the reader to the
    geography map and the netting rule for a fault in a DIFFERENT dimension's member label.
    Diagnosis order follows the filter order: the statistic gates the member observations, so
    a renamed statistic must be reported as itself and not as an absent `Total -` member.
    """
    if _STATISTIC not in seen_statistics:
        raise LoaderError(
            f"{csv_path.name}: no row carries the statistic {_STATISTIC!r} — the extract's "
            f"'Statistics (3C)' members are {sorted(seen_statistics)}. The rate slice is empty "
            "because THAT member is absent (renamed upstream?), not because a geography is "
            "missing")
    for col, member in _TOTAL_MEMBERS.items():
        if member not in seen_members[col]:
            observed = sorted(seen_members[col])
            raise LoaderError(
                f"{csv_path.name}: no row carries {member!r} in column {col} "
                f"({_EXPECTED_HEADER[col]!r}) — {len(observed)} member(s) seen there, e.g. "
                f"{observed[:4]}. The rate slice is empty because THAT `Total -` member is "
                "absent (renamed upstream?), not because a geography is missing")
    raise LoaderError(
        f"{csv_path.name}: the rate slice matched no rows although every slice member IS "
        "present — the extract carries no data rows for that cell (truncated extract?)")


def _read_totals_cube(csv_path: Path) -> dict[tuple[str, str], tuple[int, int]]:
    """{(GEO, age member): (owner, total)} over the `Total -` member of every non-age
    dimension. Positional read; duplicate keys raise (a duplicated or copied row would
    otherwise be silently absorbed into a rate)."""
    cube: dict[tuple[str, str], tuple[int, int]] = {}
    # Slice-member observations, kept so an EMPTY cube can name its own cause rather than
    # surfacing as an absent-geography error (see `_raise_for_empty_slice`). Cardinality is
    # bounded by the dimensions' member counts (3 statistics, 10/3/16 members), not by rows.
    seen_statistics: set[str] = set()
    seen_members: dict[int, set[str]] = {col: set() for col in _TOTAL_MEMBERS}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = csv.reader(fh)
        try:
            header = next(rows)
        except StopIteration as exc:
            raise LoaderError(f"{csv_path.name}: empty extract (no header row)") from exc
        _check_header(header, csv_path)
        for lineno, row in enumerate(rows, start=2):
            if len(row) <= _COL_OWNER:
                raise LoaderError(
                    f"{csv_path.name}:{lineno}: ragged row ({len(row)} fields, need "
                    f"> {_COL_OWNER})")
            seen_statistics.add(row[_COL_STAT])
            if row[_COL_STAT] != _STATISTIC:
                continue
            for col in _TOTAL_MEMBERS:
                seen_members[col].add(row[col])
            if any(row[col] != member for col, member in _TOTAL_MEMBERS.items()):
                continue
            key = (row[_COL_GEO], row[_COL_AGE])
            if key in cube:
                raise LoaderError(
                    f"{csv_path.name}:{lineno}: duplicate cell for {key} — the extract's "
                    "dimension address is not unique (row duplicated or payload copied?)")
            ctx = f"{csv_path.name}:{lineno} {key}"
            cube[key] = (_count(row[_COL_OWNER], ctx), _count(row[_COL_TOTAL], ctx))
    if not cube:
        _raise_for_empty_slice(csv_path, seen_statistics, seen_members)
    found_geos = {geo for geo, _ in cube}
    expected_geos = {_PROVINCE, *_QC_CMAS}
    if found_geos != expected_geos:
        raise LoaderError(
            f"{csv_path.name}: GEO set is {sorted(found_geos)}, expected "
            f"{sorted(expected_geos)} — HORS_RMR nets province against all six wholly-Québec "
            "CMAs, so an added/removed geography changes what the residual denotes "
            "(codex r4-F2)")
    return cube


def _band_counts(cube, geo: str, members, ctx: str) -> tuple[int, int]:
    owner = total = 0
    for member in members:
        try:
            member_owner, member_total = cube[(geo, member)]
        except KeyError as exc:
            raise LoaderError(
                f"{ctx}: age member {member!r} absent for {geo!r} — the band cannot be "
                "summed (schema drift?)") from exc
        owner += member_owner
        total += member_total
    return owner, total


def read_totals_cube(csv_path: Path | str) -> dict[tuple[str, str], tuple[int, int]]:
    """PUBLIC seam onto the pinned P2 extract: verify the pin, then read the totals cube.

    Exists because the operand-aligned extraction (`loaders/hors_aligned.py`) needs the SAME
    counts this module derives the shipped curve from, and a second reader of the same CSV
    would be a second place for the positional bindings and the GEO-set gate to drift. Ruling
    B's "one producer" argument applies to the READ as well as to the rate: two readers of one
    extract can disagree while both emit plausible numbers.
    """
    csv_path = Path(csv_path)
    verify_pin(csv_path, csv_path.name)
    return _read_totals_cube(csv_path)


def net_of_qc_cmas(cube, members, ctx: str) -> tuple[int, int]:
    """(owner, total) for the province NET of all six wholly-Québec CMAs, over `members`.

    THE HORS_RMR RESIDUAL, derived in exactly one place. Owner and total are netted
    SEPARATELY and the division happens at the call site — never a difference of rates, which
    is not a rate. The operand-aligned extraction subtracts further territory from this same
    pair, so the two constructions cannot diverge on what "the residual" means.
    """
    owner, total = _band_counts(cube, _PROVINCE, members, ctx)
    for cma in _QC_CMAS:
        cma_owner, cma_total = _band_counts(cube, cma, members, ctx)
        owner -= cma_owner
        total -= cma_total
    return owner, total


def _rate(owner: int, total: int, ctx: str) -> float:
    """Owner/Total with every degenerate named. Guards precede the division so a zero or
    inverted denominator surfaces as LoaderError, never ZeroDivisionError."""
    if total <= 0:
        raise LoaderError(f"{ctx}: non-positive household total {total}")
    if owner < 0:
        raise LoaderError(f"{ctx}: negative owner count {owner}")
    if owner > total:
        raise LoaderError(f"{ctx}: owner households {owner} exceed total {total}")
    return assert_fraction(ctx, owner / total)


def _assert_anchor_typed(rates: dict, provenance: dict, where: str, kind: str) -> None:
    """Instantiate every rate as a `constants.Anchor` built from the payload's OWN as_of and
    source — constants.py's "an undated/uncited constant is a defect" rule, enforced instead of
    stated. Runs at derivation AND at load for BOTH rate surfaces, so a de-dated artifact
    serves nothing. `_flag` is skipped: the borrow marker lives inside `rates` (it is part of
    what a consumer reads) and is not a rate."""
    for band, value in rates.items():
        if band == "_flag":
            continue
        try:
            Anchor(value=value, as_of=provenance.get("as_of", ""),
                   source=provenance.get("source", ""), unit="fraction")
        except LoaderError as exc:
            raise LoaderError(f"{where}: {kind}[{band}] is not a valid Anchor — {exc}") from exc


def _assert_ownership_anchor_typed(rates: object, provenance: dict, where: str) -> None:
    """BOTH anchor surfaces are two-level since ruling V — ownership {geography: {band: rate}}
    against headship {shape: {age: rate}} — so each types per OUTER key: this one per
    geography, headship per carried shape (`_assert_headship_anchor_typed`, which walks the
    identical two levels). Every geography, borrowed members included: five of the eight
    modeled surfaces are borrows, and skipping them would leave most of the table untyped."""
    if not isinstance(rates, dict):
        raise LoaderError(f"{where}: `rates` is {type(rates).__name__}, expected an object")
    for geo, bands in rates.items():
        if not isinstance(bands, dict):
            raise LoaderError(f"{where}: rates[{geo}] is {type(bands).__name__}, expected an object")
        _assert_anchor_typed(bands, provenance, where, kind=f"ownership[{geo}]")


def derive_ownership_from_csv(csv_path: Path | str) -> dict:
    """Compute the ownership rate table from the pinned P2 Census extract.

    The ONLY producer of ownership rates in this package (ruling B). Verifies the extract
    against its sha256 pin first — a derivation run on an unpinned or drifted vintage would
    break the PIT chain (raw response -> filter predicate -> committed extract -> rates)
    while emitting perfectly plausible numbers.
    """
    csv_path = Path(csv_path)
    verify_pin(csv_path, csv_path.name)
    cube = _read_totals_cube(csv_path)

    rates: dict[str, dict] = {}
    for geo, source in ((Geography.MTL_RMR, _MTL_CMA), (Geography.QC_RMR, _QC_CMA)):
        rates[geo.value] = {
            label: _rate(*_band_counts(cube, source, members, f"ownership[{geo.value},{label}]"),
                         ctx=f"ownership[{geo.value},{label}]")
            for label, _lo, _hi, members in _AGE_BAND_SPEC
        }

    # HORS_RMR: owner and total each netted across ALL QC CMAs, THEN divided — never a
    # difference of rates (a rate difference is not a rate).
    hors: dict[str, float] = {}
    for label, _lo, _hi, members in _AGE_BAND_SPEC:
        ctx = f"ownership[{Geography.HORS_RMR.value},{label}]"
        hors[label] = _rate(*net_of_qc_cmas(cube, members, ctx), ctx=ctx)
    rates[Geography.HORS_RMR.value] = hors

    for geo, parent in _BORROWS_FROM.items():
        rates[geo.value] = dict(rates[parent.value], _flag="borrowed_prior")

    missing = [g.value for g in Geography if g.value not in rates]
    if missing:
        raise LoaderError(f"derivation emitted no rate for: {missing} (strict join)")

    provenance = {
        "source": CENSUS_EXTRACT,
        "sha256": WORKBOOK_SHA256[CENSUS_EXTRACT],
        # The one anchor a re-extract cannot move with (DIV F2). BOTH accessors RAISE on an
        # unregistered extract, so the derivation refuses rather than emitting an artifact
        # whose upstream vintage is unpinned — or half-pinned: a digest with no member name
        # records a hash of an unidentified object.
        "raw_source_sha256": raw_anchor(CENSUS_EXTRACT),
        "raw_source_member": raw_member(CENSUS_EXTRACT),
        "statcan_table": STATCAN_TABLE,
        # `as_of` (was `ref_date` until 2026-08-13): the Census reference year, now spelled the
        # way `constants.Anchor` spells it because every rate below is typed against it. One
        # date field, and it is load-bearing — a de-dated artifact serves nothing.
        "as_of": "2021",
        "extracted_at": "2026-07-21",
        "derived_by": "demoflow.loaders.census.derive_ownership_from_csv",
        "generator": "demoflow/scripts/gen_ownership.py",
        "measure": "owner-maintainer households / total private households, at the "
                   "`Total -` member of every non-age dimension",
        "multiplicand_note": _OWNERSHIP_MULTIPLICAND_NOTE,
        "hors_rmr_method": "Québec-province counts NET of all six WHOLLY-QUÉBEC CMA counts; "
                           "owner and total netted separately THEN divided (codex r4-F2)",
        "netted_cmas": list(_QC_CMAS),
        "ca_caveat": _CA_CAVEAT,
        "isq_territory_note": _ISQ_TERRITORY_NOTE,
        "rounding_note": _ROUNDING_NOTE,
        "borrowed_prior": "RA-level members are absent from this CMA-level table; each "
                          "reuses its parent CMA's computed rate and carries "
                          "`_flag: borrowed_prior` inline (spec §8). All five borrow "
                          "MTL_RMR — understates island, overstates couronne (v0).",
    }
    # The borrow flags live INSIDE `rates` because they are part of the rate table a
    # CONSUMER reads: `load_ownership_rates` returns this sub-tree and nothing else, so a
    # flag recorded only in `_provenance` prose would be invisible to every caller. (The
    # no-drift gate compares the WHOLE payload, `_provenance` included — it is not what
    # scopes this.)
    payload_rates = {geo.value: rates[geo.value] for geo in Geography}
    # Headship's typing rule, now on this surface too (DIV carry 2026-08-13): derivation leg.
    _assert_ownership_anchor_typed(payload_rates, provenance, "derive_ownership_from_csv")
    return {"_provenance": provenance, "rates": payload_rates}


# --- loaders ------------------------------------------------------------------------

def _verify_artifact_provenance(payload, path: Path) -> None:
    """STEERING RULING L — always-on load-path staleness check.

    The no-drift gate proves the COMMITTED artifact equals a fresh derivation, but it is a
    TEST: it defends the repo, not a runtime load. Nothing stopped `load_ownership_rates`
    from serving rates out of an artifact that had gone stale against the extract, or that
    carried no source digest at all — and rates are exactly the kind of payload whose
    wrongness is invisible downstream (every value still a plausible fraction). So identity
    is checked at load, and a failure REFUSES rather than serving.

    The two legs are deliberately independent: CI compares CONTENT (artifact vs a fresh
    derivation from the CSV), this compares IDENTITY (the artifact's recorded source digest
    vs the pins registry). Neither subsumes the other — CI cannot run at load time, and this
    cannot see a hand-edited RATE under an otherwise-correct digest.
    """
    expected = WORKBOOK_SHA256.get(CENSUS_EXTRACT)
    if expected is None:
        # A dropped registry row unpins the whole PIT chain. `.get` + raise, never a bare
        # subscript: a KeyError is a class no `except LoaderError` catches (the taxonomy
        # argument in `_count`), so the loudest failure would be the least catchable one.
        raise LoaderError(
            f"{path.name}: no sha256 pin registered for {CENSUS_EXTRACT!r} — the ownership "
            "artifact cannot be checked against its source (PIT chain unpinned)")

    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    if not isinstance(provenance, dict) or "sha256" not in provenance:
        raise LoaderError(
            f"{path.name}: no `_provenance.sha256` — an artifact that records no source "
            "digest cannot be shown to derive from the pinned extract, so it is "
            "indistinguishable from a hand-authored rate table (steering ruling B) and its "
            "rates are refused (steering ruling L)")

    recorded = provenance["sha256"]
    if recorded != expected:
        raise LoaderError(
            f"{path.name}: STALE ownership artifact — recorded `_provenance.sha256` "
            f"{recorded} does not match the pinned {CENSUS_EXTRACT} digest {expected}. "
            "Regenerate with `uv run python scripts/gen_ownership.py`; never hand-edit it.")

    # The UPSTREAM leg (DIV F2): the extract's own digest co-moves with a re-extract, the raw
    # member's does not. An artifact recording a different upstream vintage than the registry
    # pins was cut from a table this repo has not reviewed.
    raw_expected = raw_anchor(CENSUS_EXTRACT)
    raw_recorded = provenance.get("raw_source_sha256")
    if raw_recorded != raw_expected:
        raise LoaderError(
            f"{path.name}: recorded `_provenance.raw_source_sha256` {raw_recorded} does not "
            f"match the pinned upstream anchor {raw_expected} for "
            # `.get`, never the raising accessor: this message is already refusing for the
            # better reason (vintage drift), and a half-registered member must not replace it.
            f"{RAW_SOURCE_MEMBER.get(CENSUS_EXTRACT, '?')} — this artifact was derived from an "
            "extract cut from a DIFFERENT upstream vintage (or the anchor was dropped); "
            "regenerate with `uv run python scripts/gen_ownership.py`")

    # Typing leg (DIV carry 2026-08-13): the identity checks above prove WHICH extract the
    # artifact came from; this proves the artifact still states a date and a citation and that
    # every rate it serves is a valid fraction under them. A digest-only check passes an
    # artifact whose provenance was hand-trimmed of its date, or whose rates were hand-edited
    # out of unit under an otherwise-correct digest.
    _assert_ownership_anchor_typed(payload.get("rates", {}), provenance, path.name)


def _read_verified_ownership(data_dir: Path | None) -> tuple[dict, Path]:
    """Read + FULLY verify the ownership artifact ONCE, for both the rate and vintage accessors.

    Shared deliberately: a vintage accessor with its own lighter read could state a vintage for
    an artifact `load_ownership_rates` refuses, which is worse than stating none. That
    rationale only holds if EVERY refusal cause lives on the shared path — measured 2026-08-14,
    with the strict join sitting in `load_ownership_rates`, a dropped geography (or a dropped
    `rates` key) refused the rates and handed back a confident `RateVintage`, so three of the
    four causes split the legs apart. The completeness check therefore lives HERE, not in the
    rate accessor.
    """
    path = (data_dir or DATA_DIR) / OWNERSHIP_ARTIFACT
    if not path.exists():
        raise LoaderError(f"ownership fixture not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Provenance BEFORE the strict join: a stale artifact whose `rates` also happen to be
    # thin would otherwise report a missing-geography error, sending the reader to the
    # geography map instead of to the vintage that is actually wrong.
    _verify_artifact_provenance(payload, path)
    rates = payload.get("rates", {})
    missing = [g.value for g in Geography if g.value not in rates]
    if missing:
        raise LoaderError(f"ownership rate missing for geographies: {missing} (strict join)")
    return payload, path


def load_ownership_rates(data_dir: Path | None = None) -> dict:
    return _read_verified_ownership(data_dir)[0]["rates"]


def load_ownership_vintage(data_dir: Path | None = None) -> RateVintage:
    """The vintage of the ownership surface a consumer just loaded (run-6 carry).

    `load_ownership_rates` returns rates and nothing else, so a consumer holding them cannot
    say what produced them — and spec §7's envelope must publish exactly that. Read from the
    artifact's OWN `_provenance`, so it names the upstream Census vintage rather than a hash
    of the derived file. `raw_source_name` states WHICH source the recorded upstream anchor
    belongs to, at the same site that verified it against `pins.raw_anchor` above.
    """
    payload, _path = _read_verified_ownership(data_dir)
    return vintage_from_provenance(OWNERSHIP_ARTIFACT, payload["_provenance"],
                                   raw_source_name=CENSUS_EXTRACT)


def _band_for(age: int, bands) -> str:
    for label, lo, hi in bands:
        if lo <= age <= hi:
            return label
    raise LoaderError(f"no modeled age band for age {age}")


def ownership_rate(rates: dict, geography: Geography, age: int) -> float:
    band = _band_for(age, _AGE_BANDS)   # 25+ only -> raises "age band" for younger ages
    geo_rates = rates.get(geography.value)
    if geo_rates is None or band not in geo_rates:
        raise LoaderError(f"no ownership rate for {geography.value} band {band}")
    return assert_fraction(f"ownership[{geography.value},{band}]", geo_rates[band])


# --- headship derivation (T13b: ruling B applied at the use site) --------------------

def _qc_persons_by_age(workbook_path: Path) -> dict[int, float]:
    """{single year of age: persons} — the base-year QC reference population denominator.

    Reads the pinned QC-total workbook through the shared single-year builder (header-GROUP
    selection, spec §8), then gates the SELECTION hard: the workbook is a fan of
    scenarios x years x statuses x sexes, and quietly picking or pooling the wrong slice would
    produce a perfectly plausible denominator and a wrong curve. `load_population` cannot serve
    this file — every one of its rows classifies IGNORED under the modeled-geography map, so
    that loader refuses it by design (isq.py gate 3).
    """
    verify_pin(workbook_path, workbook_path.name)
    frame = build_single_year_long(workbook_path)
    selected = frame[(frame["label"] == _POP_LABEL)
                     & (frame["scenario_label"] == _POP_SCENARIO)
                     & (frame["year"] == _POP_BASE_YEAR)]
    if selected.empty:
        raise LoaderError(
            f"{workbook_path.name}: no rows for {_POP_LABEL!r} / {_POP_SCENARIO!r} / "
            f"{_POP_BASE_YEAR} — the headship denominator's slice is absent (edition drift?)")

    # The base year must still be OBSERVED. A vintage in which 2021 becomes provisoire or
    # projeté changes what the denominator IS (spec §7 pins base-year rates to an observation),
    # and nothing else in this function could notice.
    statuses = sorted({str(s).strip() for s in selected["status"]})
    if statuses != [_POP_BASE_STATUS]:
        raise LoaderError(
            f"{workbook_path.name}: base year {_POP_BASE_YEAR} carries status(es) {statuses}, "
            f"expected exactly ['{_POP_BASE_STATUS}'] (réel) — the headship denominator would "
            "no longer be a base-year observation")

    by_code: dict[int, dict[int, float]] = {}
    for code in (_POP_SEX_TOTAL, *_POP_SEX_PARTS):
        rows = selected[selected["sex_code"] == code]
        ages = {int(a): float(p) for a, p in zip(rows["age"], rows["population"])}
        if sorted(ages) != list(range(0, _POP_TERMINAL_AGE + 1)):
            raise LoaderError(
                f"{workbook_path.name}: sex code {code} covers {len(ages)} single-year ages, "
                f"expected the full 0..{_POP_TERMINAL_AGE} span (schema drift)")
        for age, persons in ages.items():
            if not math.isfinite(persons) or persons < 0:
                raise LoaderError(
                    f"{workbook_path.name}: sex code {code} age {age} population {persons} is "
                    "not finite and non-negative")
        by_code[code] = ages

    # Sex additivity — the same guard isq.py applies to the modeled workbooks (gate 7). Here it
    # is the ONLY check on the both-sexes row this function returns.
    total = by_code[_POP_SEX_TOTAL]
    for age, persons in total.items():
        parts = sum(by_code[code][age] for code in _POP_SEX_PARTS)
        if not math.isclose(persons, parts, rel_tol=1e-9, abs_tol=1e-6):
            raise LoaderError(
                f"{workbook_path.name}: sex additivity fails at age {age} — code "
                f"{_POP_SEX_TOTAL} is {persons} but codes {list(_POP_SEX_PARTS)} sum to {parts}")
    return total


def _legacy_band_members() -> dict[str, tuple[str, ...]]:
    """{legacy band: its published members}, DERIVED by containment from `_HEADSHIP_MEMBER_SPEC`.

    One source of truth. A member list typed here beside the member spec is a second
    declaration, and the first thing it stops catching is a member that moved between bands.
    """
    out: dict[str, tuple[str, ...]] = {}
    for band, band_lo, band_hi in _HEADSHIP_LEGACY_BAND_SPEC:
        out[band] = tuple(label for label, lo, hi in _HEADSHIP_MEMBER_SPEC
                          if band_lo <= lo and hi <= band_hi)
    return out


def _headship_value(maintainers: float, persons: float, ctx: str) -> float:
    """maintainers / persons with every degenerate named BEFORE the division. Runs per
    published MEMBER and again per single year of age — the same three refusals either way."""
    if not math.isfinite(persons) or persons <= 0:
        raise LoaderError(f"{ctx}: non-positive person denominator {persons}")
    if maintainers < 0:
        raise LoaderError(f"{ctx}: negative maintainer count {maintainers}")
    if maintainers > persons:
        raise LoaderError(
            f"{ctx}: {maintainers} maintainers exceed {persons} persons — a headship rate "
            "above 1 means the numerator and denominator are not the same population")
    return assert_fraction(ctx, maintainers / persons)


# --- the graduation: monotone cubic Hermite on the EXPOSURE abscissa ----------------------
#
# THE OBJECT SMOOTHED IS THE CUMULATIVE MAINTAINER COUNT AGAINST CUMULATIVE PERSONS, never the
# count against age. Write `X(a) = Σ_{b≤a} P(b)` and `Y` for the cumulative maintainers; then
# `h(a) = [Y(X(a)) − Y(X(a−1))] / P(a) = ΔY/ΔX` is a divided difference of Y IN X — the mean
# `dY/dX` over one age's worth of exposure. Smoothing in AGE instead imports the denominator's
# single-year irregularity straight into the rate's FIRST DIFFERENCE, which is precisely the
# quantity `demand/formation.native_formation` reads. That failure is not asserted here, it is
# MEASURED by `_age_abscissa_refutation` on every derivation and recorded in the artifact.
#
# WHY CLOSURE IS ALGEBRAIC AND NOT NUMERICAL. Each member's endpoints X(lo−1) and X(hi) ARE
# interpolation knots, and a cubic Hermite evaluated at a knot returns the knot value exactly,
# so `Σ_{a∈m} P(a)·h(a) = Y(X(hi)) − Y(X(lo−1)) = M_m` TELESCOPES — independently of the
# tangent rule, of a refactor, of a seed, and of whether any iteration converged. There is no
# iteration, no seed and no convergence gate in this construction, so byte-reproducibility is
# structural rather than pinned. Pure arithmetic throughout: numpy is NOT a declared demoflow
# dependency (pandas, openpyxl, actuarial-system — it arrives transitively), and reaching for
# it here would put a BLAS-dependent optimum inside a generated artifact.
#
# WHAT CLOSURE DOES *NOT* BUY, stated because it is the one hole a green gate leaves: the
# terminal end tangent. Closure telescopes under any end rule, so an under-specified one ships
# clean. It is PINNED below, and `tests/test_census_ownership.py` pins the tail it produces.

def _hermite_tangents(x: list[float], y: list[float], rule: str) -> list[float]:
    """Monotone tangents at every knot. `rule` selects the INTERIOR estimator only.

    `"fc"` — three-point width-weighted initial tangents (the derivative at x_k of the parabola
            through the three surrounding knots) filtered by the Fritsch-Carlson (1980)
            radius-3 circle projection.
    `"fb"` — Fritsch-Butland weighted harmonic mean of the two adjacent secants, which is
            monotone-safe by construction in the interior.

    END RULE, PINNED, AND IT IS A SHAPE ASSUMPTION CONFINED TO THE OPEN MEMBER'S INTERIOR: the
    one-sided three-point estimate, zeroed on sign disagreement with the adjacent secant and
    clamped to 3x it on a sign reversal. A PLAIN LAST-SECANT terminal slope produces an
    h(90) -> h(100) RISE — demographically backwards, since institutionalisation keeps pushing
    maintainership down — and this rule refuses it. Closure is identical under either.
    """
    n = len(x)
    width = [x[k + 1] - x[k] for k in range(n - 1)]
    secant = [(y[k + 1] - y[k]) / width[k] for k in range(n - 1)]
    m = [0.0] * n
    for k in range(1, n - 1):
        left, right = secant[k - 1], secant[k]
        if left == 0.0 or right == 0.0 or left * right < 0.0:
            m[k] = 0.0                      # a flat or reversing secant pair pins the knot flat
        elif rule == "fc":
            m[k] = ((width[k] * left + width[k - 1] * right) / (width[k - 1] + width[k]))
        elif rule == "fb":
            w_left = 2.0 * width[k] + width[k - 1]
            w_right = width[k] + 2.0 * width[k - 1]
            m[k] = (w_left + w_right) / (w_left / left + w_right / right)
        else:
            raise LoaderError(
                f"unknown headship tangent rule {rule!r} — carried shapes are "
                f"{list(HEADSHIP_SHAPES)}")
    m[0] = _hermite_end_tangent(width[0], width[1], secant[0], secant[1])
    m[n - 1] = _hermite_end_tangent(width[n - 2], width[n - 3], secant[n - 2], secant[n - 3])
    # The circle projection runs on EVERY interval for `fc` (it is that rule's monotonicity
    # filter) and on the two END intervals for `fb` (whose harmonic mean already bounds the
    # interior but says nothing about the one-sided end estimate).
    intervals = range(n - 1) if rule == "fc" else (0, n - 2)
    for k in intervals:
        if secant[k] == 0.0:
            m[k] = m[k + 1] = 0.0
            continue
        alpha, beta = m[k] / secant[k], m[k + 1] / secant[k]
        radius = alpha * alpha + beta * beta
        if radius > 9.0:
            scale = 3.0 / math.sqrt(radius)
            m[k], m[k + 1] = scale * alpha * secant[k], scale * beta * secant[k]
    return m


def _hermite_end_tangent(w0: float, w1: float, d0: float, d1: float) -> float:
    """The PINNED one-sided three-point end slope (see `_hermite_tangents`)."""
    estimate = ((2.0 * w0 + w1) * d0 - w0 * d1) / (w0 + w1)
    if estimate * d0 <= 0.0:
        return 0.0
    if d0 * d1 < 0.0 and abs(estimate) > 3.0 * abs(d0):
        return 3.0 * d0
    return estimate


def _hermite_at(x: list[float], y: list[float], m: list[float], q: float) -> float:
    """The interpolant at `q`. Exact at every knot — which is what makes closure telescope."""
    if q <= x[0]:
        return y[0]
    if q >= x[-1]:
        return y[-1]
    lo, hi = 0, len(x) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if x[mid] <= q:
            lo = mid
        else:
            hi = mid
    width = x[lo + 1] - x[lo]
    t = (q - x[lo]) / width
    secant = (y[lo + 1] - y[lo]) / width
    return y[lo] + width * (m[lo] * t
                            + (3.0 * secant - 2.0 * m[lo] - m[lo + 1]) * t * t
                            + (m[lo] + m[lo + 1] - 2.0 * secant) * t * t * t)


def _hermite_derivative_sup(x: list[float], y: list[float], m: list[float]) -> float:
    """The RANGE CERTIFICATE: sup dY/dX over the whole continuum, in closed form.

    `h >= 0` is true by construction (a monotone cumulative cannot difference negative), but
    `h <= 1` is NOT a theorem of the method — the monotonicity filter bounds a tangent only by
    3x the largest secant. So the bound is CERTIFIED per run rather than assumed: the
    derivative on each segment is a quadratic in t, and its maximum is at an endpoint or at the
    interior vertex. A sampled maximum would only bound the 101 evaluated ages; this bounds the
    continuum, and it RAISES rather than shipping if a future re-extract breaks it.
    """
    sup = 0.0
    for k in range(len(x) - 1):
        width = x[k + 1] - x[k]
        secant = (y[k + 1] - y[k]) / width
        a = 3.0 * (m[k] + m[k + 1] - 2.0 * secant)
        b = 2.0 * (3.0 * secant - 2.0 * m[k] - m[k + 1])
        c = m[k]
        candidates = [c, a + b + c]
        if a < 0.0:
            vertex = -b / (2.0 * a)
            if 0.0 < vertex < 1.0:
                candidates.append(a * vertex * vertex + b * vertex + c)
        sup = max(sup, max(candidates))
    return sup


def _headship_members(member_maintainers: dict[str, int]) -> tuple[tuple[str, int, int, int], ...]:
    """(label, lo, hi, maintainers) for the DECLARED under-15 member plus the 14 published
    ones, in published order — the order the knots are built in, never a set iteration."""
    label, lo, hi = _HEADSHIP_ZERO_MEMBER
    return ((label, lo, hi, 0),
            *((name, m_lo, m_hi, member_maintainers[name])
              for name, m_lo, m_hi in _HEADSHIP_MEMBER_SPEC))


def _headship_knots(persons_by_age: dict[int, float],
                    members: tuple[tuple[str, int, int, int], ...]) -> tuple[list, list, dict]:
    """The 16 knots on the exposure abscissa, plus X(a) for every age."""
    cumulative_persons: dict[int, float] = {}
    running = 0.0
    for age in sorted(persons_by_age):
        running += persons_by_age[age]
        cumulative_persons[age] = running
    x, y = [0.0], [0.0]
    accumulated = 0
    for _label, _lo, hi, count in members:
        accumulated += count
        x.append(cumulative_persons[hi])
        y.append(float(accumulated))
    return x, y, cumulative_persons


def _headship_curve(persons_by_age: dict[int, float],
                    members: tuple[tuple[str, int, int, int], ...],
                    rule: str) -> tuple[dict[int, float], float]:
    """{age: rate} over 0..`_POP_TERMINAL_AGE` plus the range certificate, for one arm."""
    x, y, cumulative_persons = _headship_knots(persons_by_age, members)
    tangents = _hermite_tangents(x, y, rule)
    curve: dict[int, float] = {}
    previous = 0.0
    for age in sorted(persons_by_age):
        value = _hermite_at(x, y, tangents, cumulative_persons[age])
        maintainers = value - previous
        if maintainers < 0.0:
            # G7. It follows from a monotone cumulative; it is asserted anyway because it is
            # the property the exposure abscissa was chosen to buy, and a future tangent rule
            # that broke monotonicity would otherwise surface as a negative RATE downstream.
            raise LoaderError(
                f"headship[{rule}][{age}]: the graduated cumulative fell by {maintainers} "
                "over one year of age — the interpolant is not monotone, so the curve would "
                "carry a negative maintainer count")
        curve[age] = _headship_value(maintainers, persons_by_age[age], f"headship[{rule}][{age}]")
        previous = value
    return curve, _hermite_derivative_sup(x, y, tangents)


def _age_abscissa_refutation(persons_by_age: dict[int, float],
                             members: tuple[tuple[str, int, int, int], ...],
                             rule: str) -> dict[str, float]:
    """The MEASURED anchor for the abscissa assumption — computed here on THIS vintage.

    Same construction with the AGE abscissa (this is the published textbook recipe, DemoTools
    `graduate_mono`, applied literally). It is deliberately NOT gated: it is the refuted
    variant, and gating it would raise instead of recording the refutation. Every figure the
    `shape_note` cites comes from this function; none is transcribed from a design document —
    the panel's own judge could not reproduce one of the figures its winning proposal quoted,
    which is exactly why the generator computes its own.
    """
    x, y = [-1.0], [0.0]
    accumulated = 0
    for _label, _lo, hi, count in members:
        accumulated += count
        x.append(float(hi))
        y.append(float(accumulated))
    tangents = _hermite_tangents(x, y, rule)
    rates: dict[int, float] = {}
    previous = 0.0
    for age in sorted(persons_by_age):
        value = _hermite_at(x, y, tangents, float(age))
        rates[age] = (value - previous) / persons_by_age[age]
        previous = value
    peak = max(rates, key=lambda age: rates[age])
    return {
        "max_rate": rates[peak],
        "max_rate_age": peak,
        "rate_at_55": rates[55],
        "rate_at_56": rates[56],
        "rate_step_at_56": rates[56] - rates[55],
        "persons_ratio_56_over_55": persons_by_age[56] / persons_by_age[55],
    }


def _ownership_spec_omitted_members(cube: dict[tuple[str, str], tuple[int, int]]
                                    ) -> tuple[tuple[str, int, int], ...]:
    """Published maintainer-age members the headship curve reads and `_AGE_BAND_SPEC` drops,
    each with the (owner, total) counts the extract publishes for the province.

    DERIVED from the two specs rather than typed, in the order the member spec declares them,
    so the sentence below cannot outlive the choice it describes: extend `_AGE_BAND_SPEC`
    downward and the clause retires itself instead of becoming a museum label.
    """
    owned = {member for *_, members in _AGE_BAND_SPEC for member in members}
    out = []
    for member, _lo, _hi in _HEADSHIP_MEMBER_SPEC:
        if member not in owned:
            owner, total = cube[(_PROVINCE, member)]
            out.append((member, owner, total))
    return tuple(out)


def _shape_note(refutation: dict[str, dict[str, float]],
                certificate: dict[str, float],
                overshoot: dict[str, float]) -> str:
    """The F6 HONESTY CLAUSE, written INTO the artifact so it rides the artifact digest and
    therefore `data_vintage.source_hashes` — a shape constant living only as a Python literal
    in this module would sit outside BOTH that map and `assumptions_hash()`.

    LEVEL IS PUBLISHED, SHAPE IS ASSUMED. Per-member closure pins ONE linear functional per
    member and leaves 4, 9 or 15 degrees of freedom; calling the within-member shape "derived"
    would be a false derivation claim in a package whose charter is derivation-never-
    transcription. Every figure below is computed by this generator on this vintage.
    """
    # The arms are named by MEASUREMENT, not by literal key: the out-of-range citation goes to
    # whichever arm actually measured the largest rate under the age abscissa, and the step
    # citation to the CENTRAL arm. A hard-coded key here would be a fourth place the shape
    # names are spelled.
    worst = max(HEADSHIP_SHAPES, key=lambda shape: refutation[shape]["max_rate"])
    out_of_range, central = refutation[worst], refutation[HEADSHIP_CENTRAL_SHAPE]
    return (
        "LEVEL IS PUBLISHED, SHAPE IS ASSUMED. Per-member closure pins exactly ONE linear "
        "functional per published member and leaves 4, 9 or 15 degrees of freedom inside it, "
        "so the single-year curve is published aggregate PLUS a declared shape assumption. The "
        "assumption is: monotone cubic Hermite on the CUMULATIVE MAINTAINER COUNT against the "
        "CUMULATIVE-PERSONS abscissa, with the tangent rule named by the shape key "
        f"({', '.join(HEADSHIP_SHAPES)}; central {HEADSHIP_CENTRAL_SHAPE!r}) and the terminal "
        "end tangent PINNED to the one-sided three-point rule. "
        "THE ABSCISSA IS THE ASSUMPTION, AND ITS ANCHOR IS MEASURED, NOT CITED: re-run on the "
        "AGE abscissa (the textbook recipe applied literally) this same vintage yields "
        f"max h = {out_of_range['max_rate']:.4f} at age {out_of_range['max_rate_age']:.0f} on "
        f"the {worst!r} tangent rule — OUT OF RANGE, a rate above 1 — and on "
        f"{HEADSHIP_CENTRAL_SHAPE!r} a spurious NEGATIVE rate step at age 56 "
        f"({central['rate_at_55']:.4f} -> {central['rate_at_56']:.4f}, "
        f"{central['rate_step_at_56']:+.4f}) driven by nothing but "
        f"P(56)/P(55) = {central['persons_ratio_56_over_55']:.4f}, a real cohort bulge. "
        "Graduating "
        "the COUNT smoothly in age imports the denominator's single-year irregularity into the "
        "rate's FIRST DIFFERENCE — the exact quantity native formation reads. "
        "RANGE IS CERTIFIED, NOT ASSUMED: the closed-form supremum of dY/dX over the whole "
        "continuum is "
        + "; ".join(f"{shape} {certificate[shape]:.10f}" for shape in HEADSHIP_SHAPES)
        + " against the bound 1.0. "
        "THE MEMBER RATES ARE THE PUBLISHED ONES; THE CURVE'S PER-AGE VALUES ARE NEITHER THOSE "
        "NOR KNOT VALUES — a reviewer diffing h(a) against `member_rates` is comparing a "
        "single-year rate with a member-mean and must not read the difference as a bug. "
        "ONE MEASURED DEFECT, RECORDED RATHER THAN PAPERED OVER: an osculatory overshoot at "
        "the 74/75 boundary, where the member width changes 5 -> 10 AND the rate reverses. "
        + "; ".join(
            f"{shape} peaks at {overshoot[shape]['peak_rate']:.5f} at age "
            f"{overshoot[shape]['peak_age']:.0f}, "
            f"{overshoot[shape]['excess_over_hull_pct']:+.2f}% over the member-rate hull "
            f"({overshoot[shape]['hull_max']:.5f})" for shape in HEADSHIP_SHAPES)
        + ". It touches OwnerStock ALONE (`formation.AGE_BOUNDARY` stops D_native at 75), it is "
        "inside the range certificate, and it cannot be removed without either dropping to the "
        "refuted member-step curve or adding an unanchored hull clamp — which was measured to "
        "produce a NEGATIVE rate at 15. "
        "THE 85-100 INTERIOR IS PURE ASSUMPTION on the open member's population: nothing but "
        "the member total constrains it, only the ED denominator reads it, and its exposure "
        "GROWS over the projection horizon. That is a stated, accepted exposure."
    )


def _zero_support_note(under_15_persons: float, youngest_member: tuple[str, int],
                       omitted: tuple[tuple[str, int, int], ...],
                       members: int, tolerance: float, delta: int) -> str:
    """THREE claims about three different lines, kept distinct (falsifier F11).

    (i) the under-15 zero, as a POSITIVE BOUND rather than an absence claim;
    (ii) the age-resolved warning this note used to carry, explicitly DISCHARGED;
    (iii) the sub-25 ownership clause, STILL STANDING, its figures still computed from the
          extract via `_ownership_spec_omitted_members` — whose empty-set RAISE therefore
          stays armed as the coupling guard on the ordering constraint. The clause names TWO
          guards that FIRE (that RAISE, and the `OWNERSHIP_LATTICE_FLOOR` pin, which catches
          the PARTIAL extensions the RAISE cannot see) and names the one obligation neither
          can check — run 15's lesson: a trigger nobody checks is not a condition.

    Silently deleting (ii) — the clause that ORDERED this work — is the failure this package's
    commenting discipline exists to prevent, so it is retired in writing and says what retired
    it.
    """
    if not omitted:
        # The day `_AGE_BAND_SPEC` reaches the youngest published member, clause (iii) has no
        # subject and would render as a grammatically broken sentence with no figures in it.
        # RAISE rather than emit that: an extension of the ownership lattice is a supervised
        # change (spec §7's ordering constraint gates it), so a loud stop with an instruction
        # is cheaper than a malformed provenance record shipped inside a green suite.
        raise LoaderError(
            "the ownership band spec no longer omits any published maintainer-age member, so "
            "`zero_support_note`'s sub-25 clause has retired itself — rewrite the clause (and "
            "spec §7's ordering constraint, which it cites) instead of generating an empty one")
    published = "; ".join(f"{member!r} {owner:,} owners of {total:,} households"
                          for member, owner, total in omitted)
    dropped = ", ".join(repr(member) for member, _owner, _total in omitted)
    youngest_label, youngest_count = youngest_member
    # The bound an unpublished 15th age member would have to satisfy, computed from the SAME
    # closure arithmetic the numerator gate uses — never a typed number.
    bound = tolerance + 2.5 - abs(delta)
    rate_bound = bound / under_15_persons
    return (
        "UNDER-15 MAINTAINERS ARE PINNED AT ZERO BY CLOSURE, NOT BY THE TABLE'S SILENCE "
        f"(operator ruling V, 2026-08-19). The extract's age dimension DECLARES ITS OWN "
        f"CARDINALITY — one total plus {members} age members, the youngest of which is "
        f"{youngest_label!r} at {youngest_count:,} households — so an unpublished under-15 "
        f"member of size X would have to satisfy the closure residual "
        f"|{delta:+d} + X| <= 2.5 x ({members} members + 1 total + 1 hypothetical) = "
        f"{tolerance + 2.5:g}, giving X <= {bound:g} households against "
        f"{under_15_persons:,.0f} persons aged 0-14 — a rate below {rate_bound:.1e}, i.e. "
        "BELOW ROUNDING SCALE. Closure pins under-15 maintainers below rounding scale, so 0.0 "
        "is the only admissible value. This is a bound, not a proof of exact zero, and it is "
        "NOT the claim that the source says nothing. "
        "THE AGE-RESOLVED WARNING THIS NOTE CARRIED IS DISCHARGED. Until ruling V it read "
        "\"It is NOT an age-resolved rate — a consumer multiplying a SINGLE age inside the "
        "band (spec §6's age-18 D_native term) must land an age-resolved curve rather than "
        "reuse this one\", and the six-band curve it described asserted phantom households "
        "under 15 while understating 15-19 several-fold — pure intra-band misallocation, which "
        "is why the aggregate closure stayed green throughout. The curve is now resolved at "
        "every single year of age 0..100 against per-MEMBER closure, so the consumer that "
        "sentence addressed multiplies a PER-SINGLE-YEAR rate and is no longer reusing a band "
        "rate. That sentence is retired by commit `c83595e` (operator ruling V, 2026-08-19); "
        "it is recorded here rather than deleted because it is the clause that ordered the "
        "work. "
        "THE SUB-25 OWNERSHIP CLAUSE STILL STANDS, AND IT IS A CHOICE IN `_AGE_BAND_SPEC`, NOT "
        f"THE DATA'S SILENCE (spec §7 amendment #12): for {_PROVINCE} the extract publishes "
        f"{published}. `_HEADSHIP_MEMBER_SPEC` reads {dropped} off the SAME age dimension of "
        "the SAME extract while `_AGE_BAND_SPEC` starts the ownership lattice at 25-54, so the two "
        "youngest PUBLISHED members are dropped by the ownership derivation and by nothing "
        "upstream of it. THE OMISSION STANDS FOR NOW, under spec §7 amendment #12's binding "
        "ordering constraint — age-resolved headship FIRST, then the floor — and this curve is "
        "the first of those two steps. "
        "THE REOPENING TRIGGER IS MECHANICAL, AND ITS LIMIT IS STATED IN THE SAME BREATH: a "
        "condition whose trigger nobody checks is not a condition (run 15 recorded \"it "
        "reopens when Task 29 lands an age-resolved headship curve\"; Task 29 landed WITHOUT "
        "one, nothing reopened, and the defect survived three review rounds until a pre-PR "
        "gate caught it). TWO GUARDS FIRE ON THE MOVE ITSELF, with nobody required to notice a "
        "milestone. (a) THE FLOOR TRIPWIRE: "
        "`test_the_ownership_LATTICE_FLOOR_IS_A_TRIPWIRE_that_reds_when_the_floor_moves` "
        "(demoflow/tests/test_census_ownership.py) pins `min(census._AGE_BANDS) == "
        "OWNERSHIP_LATTICE_FLOOR == 25` and REDS on any move of the lattice floor — "
        "consistently made or not — with the re-measurement below named in its failure "
        "message; the twin pins in demoflow/tests/test_owner_stock.py and "
        "demoflow/tests/test_demand.py separately stop `demand/formation.py`'s mirrored "
        "literal from parting from this spec quietly. (b) THE DERIVE-TIME RAISE: an extension "
        "that REACHES the youngest published member empties "
        "`_ownership_spec_omitted_members` and this function RAISES before a subject-less "
        "clause can ship. WHAT NEITHER GUARD CHECKS is that the re-measurement was actually "
        "DONE: (a) forces the obligation into the DIFF and is satisfied by editing the "
        "tripwire, (b) fires only at FULL extension, and both fire on the EXTENSION rather "
        "than on the measurement. The re-measurement is therefore UNENFORCED by construction "
        "and recorded here as such rather than dressed as a guarantee. "
        "WHAT THE FLOOR NOW DISCARDS HAS CHANGED CHARACTER: the "
        "old curve put the entire 0-19 -> 20-34 rise at the single age 20, where "
        "ownership(20) = 0 zeroed it; the resolved curve spreads that rise across ages 20..34, "
        "most of it ABOVE the floor, so the floor discards a SLOPE rather than a STEP. "
        "Amendment #12's quantified-floor-effect legs were measured on the banded curve and "
        "MUST BE RE-MEASURED against this one BEFORE the ownership lattice is extended "
        "downward, or a stale measurement stands as the warrant for an irreversible ordering "
        "decision."
    )


def _assert_headship_anchor_typed(curves: dict, provenance: dict, where: str) -> None:
    """Anchor-typing for a curve carried at TWO shapes: every age of every arm, not only the
    central one — a sweep leg reads the other arm and would otherwise ride untyped rates."""
    if not isinstance(curves, dict):
        raise LoaderError(f"{where}: `headship` is {type(curves).__name__}, expected an object")
    for shape, curve in curves.items():
        if not isinstance(curve, dict):
            raise LoaderError(
                f"{where}: headship[{shape}] is {type(curve).__name__}, expected an object")
        _assert_anchor_typed(curve, provenance, where, kind=f"headship[{shape}]")


def derive_headship_from_sources(csv_path: Path | str, workbook_path: Path | str) -> dict:
    """Compute the base-year AGE-RESOLVED headship curve from the TWO pinned sources.

    The ONLY producer of headship rates in this package. USE-SITE SEMANTICS (spec:395):
    `OwnerStock = Σ pop(a,g,t,s) × headship(a) × ownership(a)` multiplies ISQ scenario
    POPULATION, so headship(a) = QC private-household primary maintainers ÷ ISQ persons, and
    since ruling V both sides of that ratio are read at the finest published resolution: the
    14 published maintainer-age members against the 101 single-year person denominators. Both
    sources are verified against their pins before a single value is computed — a curve derived
    from an unpinned vintage breaks the PIT chain while emitting perfectly plausible fractions
    (that is precisely how the retired typed curve survived).

    EVERY GATE BELOW IS A COMPUTED PROOF THAT RAISES, never an assertion that documents.
    """
    csv_path, workbook_path = Path(csv_path), Path(workbook_path)
    verify_pin(csv_path, csv_path.name)
    cube = _read_totals_cube(csv_path)
    persons_by_age = _qc_persons_by_age(workbook_path)      # verifies its own pin

    member_maintainers: dict[str, int] = {}
    for label, _lo, _hi in _HEADSHIP_MEMBER_SPEC:
        try:
            # index 1 = `Tenure (4):Total - Tenure[1]`: ALL private households in the cell.
            # The age dimension IS the maintainer's age, so that count is the numerator;
            # index 0 (owner households) belongs to the ownership rate, never to headship.
            member_maintainers[label] = cube[(_PROVINCE, label)][1]
        except KeyError as exc:
            raise LoaderError(
                f"headship[{label}]: age member {label!r} absent for {_PROVINCE!r} — the "
                "published member cannot be read (schema drift?)") from exc

    published = cube.get((_PROVINCE, MAINTAINER_TOTAL_MEMBER))
    if published is None:
        raise LoaderError(
            f"{csv_path.name}: the published {MAINTAINER_TOTAL_MEMBER!r} member is absent for "
            f"{_PROVINCE!r} — the banded numerator has nothing independent to close against")
    published_total = published[1]
    banded = sum(member_maintainers.values())
    # G2, THE DATA BOUND, unchanged in arithmetic and in wording. StatCan rounds every cell to
    # the nearest 5, so the constituents and the published total each carry <= 2.5 of rounding
    # error: the bound is 2.5 x (members + 1), DERIVED from the member count rather than tuned
    # to the observed delta — a gate tuned to today's value reds on a legitimate re-extract. It
    # still catches a dropped or duplicated constituent by three orders of magnitude (smallest
    # member: 10,920). The sentence keeps the word "banded" deliberately: it is the SAME 14
    # published members either way (each legacy band is an exact union of them), and the string
    # is the provenance-continuity anchor a reviewer diffs the re-mint against.
    n_members = len(_HEADSHIP_MEMBER_SPEC)
    tolerance = 2.5 * (n_members + 1)
    closure = (f"banded maintainers {banded:,} vs the extract's published "
               f"{MAINTAINER_TOTAL_MEMBER!r} member {published_total:,}; delta "
               f"{banded - published_total:+,} inside the round-to-5 bound 2.5 x "
               f"({n_members} members + 1 total) = {tolerance:g}")
    if abs(banded - published_total) > tolerance:
        raise LoaderError(f"{csv_path.name}: headship numerator does not close — {closure}")

    members = _headship_members(member_maintainers)
    member_persons = {label: sum(p for age, p in persons_by_age.items() if lo <= age <= hi)
                      for label, lo, hi, _count in members}
    # G8, per member: the degenerate guards that used to run per band.
    member_rates = {label: _headship_value(count, member_persons[label], f"headship[{label}]")
                    for label, _lo, _hi, count in members}

    curves: dict[str, dict[int, float]] = {}
    certificate: dict[str, float] = {}
    per_member_closure: dict[str, dict[str, float]] = {}
    overshoot: dict[str, dict[str, float]] = {}
    refutation: dict[str, dict[str, float]] = {}
    hull_max = max(member_rates.values())
    for shape, rule in _HEADSHIP_SHAPE_SPEC:
        curve, sup = _headship_curve(persons_by_age, members, rule)
        # G5, SUPPORT: exactly the integer ages the denominator publishes, no more and no less.
        if sorted(curve) != list(range(0, _POP_TERMINAL_AGE + 1)):
            raise LoaderError(
                f"headship[{shape}]: curve covers {len(curve)} ages, expected the full "
                f"0..{_POP_TERMINAL_AGE} span")
        # G6, ZERO FLOOR: identity, not a rounded small number.
        for age in range(0, _HEADSHIP_ZERO_MEMBER[2] + 1):
            if curve[age] != 0.0:
                raise LoaderError(
                    f"headship[{shape}][{age}]: {curve[age]!r} is not exactly 0.0 — closure "
                    "admits no under-15 maintainer mass, so a nonzero value there is a "
                    "construction defect, not a small number")
        # G1, THE CONSTRUCTION GATE: per-member closure, computed, at an absolute household
        # tolerance. It covers the DECLARED (0, 14, 0) member too — that member is what makes
        # the zero floor a property of the construction rather than a value bolted on.
        residuals = {}
        for label, lo, hi, count in members:
            residual = abs(sum(persons_by_age[a] * curve[a] for a in range(lo, hi + 1)) - count)
            residuals[label] = residual
            if residual > _HEADSHIP_CLOSURE_TOLERANCE:
                raise LoaderError(
                    f"headship[{shape}][{label}]: per-member closure residual {residual} "
                    f"exceeds {_HEADSHIP_CLOSURE_TOLERANCE} households — the graduated curve "
                    f"does not reproduce the published member count {count:,}")
        per_member_closure[shape] = residuals
        # G3, THE LEGACY-BAND IDENTITY: C1 AND C2 imply C3, PROVED rather than asserted. Every
        # legacy band is an exact union of published members, so this also proves that
        # `band_maintainers`, `band_persons` and the six band rates below still derive.
        for band, lo, hi in _HEADSHIP_LEGACY_BAND_SPEC:
            expected = sum(member_maintainers[m] for m in _legacy_band_members()[band])
            got = sum(persons_by_age[a] * curve[a] for a in range(lo, hi + 1))
            if abs(got - expected) > _HEADSHIP_CLOSURE_TOLERANCE:
                raise LoaderError(
                    f"headship[{shape}]: legacy band {band} sums to {got} from the fine curve "
                    f"against {expected:,} from its published members — the six-band "
                    "provenance this artifact carries no longer derives from the curve")
        # G4, THE RANGE CERTIFICATE.
        if not (0.0 <= sup <= 1.0):
            raise LoaderError(
                f"headship[{shape}]: the closed-form supremum of dY/dX is {sup}, outside "
                "[0, 1] — a headship rate above 1 is not a rate, and a sampled maximum would "
                "not have seen it between the evaluated ages")
        curves[shape] = curve
        certificate[shape] = sup
        peak_age = max(curve, key=lambda age: curve[age])
        overshoot[shape] = {
            "peak_age": peak_age, "peak_rate": curve[peak_age], "hull_max": hull_max,
            "excess_over_hull_pct": 100.0 * (curve[peak_age] / hull_max - 1.0)}
        refutation[shape] = _age_abscissa_refutation(persons_by_age, members, rule)

    band_persons = {band: sum(p for age, p in persons_by_age.items() if lo <= age <= hi)
                    for band, lo, hi in _HEADSHIP_LEGACY_BAND_SPEC}
    band_maintainers = {band: sum(member_maintainers[m] for m in _legacy_band_members()[band])
                        for band, _lo, _hi in _HEADSHIP_LEGACY_BAND_SPEC}

    provenance = {
        "as_of": str(_POP_BASE_YEAR),
        "source": (
            f"Census 2021 QC private-household PRIMARY MAINTAINERS by published age member "
            f"(StatCan {STATCAN_TABLE}, committed extract {CENSUS_EXTRACT}, `Total -` member "
            f"of every non-age dimension at statistic {_STATISTIC!r}) GRADUATED TO SINGLE "
            f"YEARS OF AGE against ISQ {_POP_BASE_YEAR} {_POP_LABEL} {_POP_SCENARIO} persons "
            f"by single year of age (committed {POP_QC_WORKBOOK}, both sexes) — DERIVED, never "
            "transcribed (steering ruling B); the denominator is PERSONS because the use site "
            "(spec:395 OwnerStock) multiplies ISQ scenario population"),
        "sources": {
            CENSUS_EXTRACT: WORKBOOK_SHA256[CENSUS_EXTRACT],
            POP_QC_WORKBOOK: WORKBOOK_SHA256[POP_QC_WORKBOOK],
        },
        "raw_source_sha256": raw_anchor(CENSUS_EXTRACT),
        "raw_source_member": raw_member(CENSUS_EXTRACT),
        "statcan_table": STATCAN_TABLE,
        "isq_scenario": _POP_SCENARIO,
        "isq_geography": _POP_LABEL,
        "base_year_status": f"{_POP_BASE_STATUS} (réel — an observation, not a projection)",
        "extracted_at": "2026-07-21",
        "derived_by": "demoflow.loaders.census.derive_headship_from_sources",
        "generator": "demoflow/scripts/gen_headship.py",
        "measure": ("private-household primary maintainers per PERSON at a single year of age "
                    "— households formed per person, PIT-fixed at the base year (spec §7 "
                    "r3-F3); the LEVEL is published per member, the within-member SHAPE is the "
                    "declared assumption in shape_note"),
        "multiplicand_note": _HEADSHIP_MULTIPLICAND_NOTE,
        "member_spec": {label: [lo, hi] for label, lo, hi, _c in members},
        "member_persons": member_persons,
        "member_maintainers": {label: count for label, _lo, _hi, count in members},
        "member_rates": member_rates,
        "per_member_closure": {
            "residuals": per_member_closure,
            "construction_tolerance": _HEADSHIP_CLOSURE_TOLERANCE,
            "admissible_bound_note": (
                "TWO DIFFERENT TOLERANCES, and conflating them is a design error. The "
                "CONSTRUCTION residual above is asserted at "
                f"{_HEADSHIP_CLOSURE_TOLERANCE} households because per-member closure is "
                "solvable EXACTLY (it is one linear constraint over 5, 10 or 16 free values), "
                "and it is measured at 0.0 on both arms. The ADMISSIBLE bound a legitimate "
                "RE-EXTRACT must survive is different and larger: published counts are "
                "round-to-5, so each member carries <= 2.5 households of rounding error. No "
                "correction is applied to either side."),
        },
        "range_certificate": certificate,
        "shape_note": _shape_note(refutation, certificate, overshoot),
        "abscissa_refutation": refutation,
        "osculatory_overshoot": overshoot,
        "band_members": {band: list(members)
                         for band, members in _legacy_band_members().items()},
        "band_persons": band_persons,
        "band_maintainers": band_maintainers,
        "numerator_closure": closure,
        "zero_support_note": _zero_support_note(
            sum(p for age, p in persons_by_age.items() if age <= _HEADSHIP_ZERO_MEMBER[2]),
            (_HEADSHIP_MEMBER_SPEC[0][0], member_maintainers[_HEADSHIP_MEMBER_SPEC[0][0]]),
            _ownership_spec_omitted_members(cube),
            n_members, tolerance, banded - published_total),
        # NOT `_ROUNDING_NOTE`: that sentence describes the OWNERSHIP rate's numerator and
        # denominator, both of which are round-to-5 household counts. Here only the numerator
        # is — the ISQ person denominators are not rounded that way, and a reader told
        # otherwise would mis-attribute the +5 delta.
        "rounding_note": (
            "StatCan rounds household counts to the nearest 5, so the banded maintainer "
            "constituents do not reconcile exactly to their published total (see "
            "numerator_closure). The ISQ person denominators carry no such rounding. No "
            "correction is applied to either side."),
        "supersedes": (
            "the SIX-BAND curve carried until 2026-08-19, materialised flat at single years of "
            "age. It was aggregate-consistent and wrong at every age inside a band: the 0-19 "
            "band rate asserted 8,304 private households maintained by someone aged 0-14 and "
            "understated 15-19 by 4.17x — pure intra-band misallocation, which is why "
            "numerator_closure stayed green. Operator ruling V, 2026-08-19. Before it, the six "
            "TYPED rates carried until 2026-08-08 (0-19 0.02, 20-34 0.40, 35-54 0.48, 55-64 "
            "0.52, 65-74 0.56, 75+ 0.62), retired by the DIV re-triage as not reproducible "
            "from their stated source"),
    }
    payload_curves = {shape: {str(age): curves[shape][age] for age in sorted(curves[shape])}
                      for shape in HEADSHIP_SHAPES}
    _assert_headship_anchor_typed(payload_curves, provenance,
                                  "derive_headship_from_sources")
    return {"_provenance": provenance, "headship": payload_curves,
            "central_shape": HEADSHIP_CENTRAL_SHAPE}


# --- headship loaders ----------------------------------------------------------------

def _verify_headship_provenance(payload: dict, path: Path) -> None:
    """STEERING RULING L for headship — identity checked on EVERY load, all three digests.

    Headship has TWO committed sources plus the upstream raw anchor, and an artifact derived
    from a stale POP workbook is exactly as wrong as one derived from a stale extract — so a
    single-digest check (ownership's shape) would leave two of the three unexecuted. Every
    message NAMES the digest at fault: "this artifact is stale" without saying which source
    moved sends the reader to the wrong file.
    """
    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    if not isinstance(provenance, dict):
        raise LoaderError(
            f"{path.name}: no `_provenance` block — an artifact that records no source sha256 "
            "cannot be shown to derive from the pinned sources, so it is indistinguishable "
            "from a hand-authored curve (steering ruling B) and is refused (ruling L)")
    sources = provenance.get("sources")
    if not isinstance(sources, dict):
        raise LoaderError(
            f"{path.name}: no `_provenance.sources` map of source file -> sha256 — the "
            "artifact records no source identity at all and is refused (steering ruling L)")
    for name in (CENSUS_EXTRACT, POP_QC_WORKBOOK):
        expected = WORKBOOK_SHA256.get(name)
        if expected is None:
            raise LoaderError(
                f"{path.name}: no sha256 pin registered for {name!r} — the headship artifact "
                "cannot be checked against its source (PIT chain unpinned)")
        recorded = sources.get(name)
        if recorded is None:
            raise LoaderError(
                f"{path.name}: `_provenance.sources` records no sha256 for {name!r} — one of "
                "the two derivation inputs is unaccounted for, so a stale vintage of it could "
                "not be detected (steering ruling L)")
        if recorded != expected:
            raise LoaderError(
                f"{path.name}: STALE headship artifact — recorded sha256 for {name} "
                f"{recorded} does not match the pinned digest {expected}. Regenerate with "
                "`uv run python scripts/gen_headship.py`; never hand-edit it.")

    raw_expected = raw_anchor(CENSUS_EXTRACT)
    if provenance.get("raw_source_sha256") != raw_expected:
        raise LoaderError(
            f"{path.name}: recorded `_provenance.raw_source_sha256` "
            f"{provenance.get('raw_source_sha256')} does not match the pinned upstream anchor "
            # `.get` for the same reason as the ownership leg above: drift is the finding.
            f"{raw_expected} for {RAW_SOURCE_MEMBER.get(CENSUS_EXTRACT, '?')} — the numerator "
            "was cut from a DIFFERENT upstream vintage (or the anchor was dropped); regenerate "
            "with `uv run python scripts/gen_headship.py`")

    _assert_headship_anchor_typed(payload["headship"], provenance, path.name)


def _read_verified_headship(data_dir: Path | None) -> tuple[dict, Path, dict[str, dict[int, float]]]:
    """Read, verify AND strictly join the headship artifact ONCE, for both the curves and the
    vintage accessor.

    THE STRICT JOIN RUNS ON THE SHARED PATH, not inside the rate accessor (measured
    2026-08-14 on a dropped band, and again at ruling V on a dropped SHAPE): a completeness
    check that ran only where the rates are read lets `load_headship_vintage` state a confident
    vintage for a curve no run may use, and a stateable vintage for rates that would be refused
    is worse than no vintage at all.
    """
    path = (data_dir or DATA_DIR) / HEADSHIP_ARTIFACT
    if not path.exists():
        raise LoaderError(f"headship fixture not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # STRICT key — deliberately NOT `load_ownership_rates`'s `.get("rates", {})`, which is
    # plan-verbatim and whose renamed-key path reports a missing-GEOGRAPHY error instead of a
    # file-level one (measured 2026-08-08). A `.get("headship", {})` here would degrade a
    # renamed or absent top-level key into an empty curve, which then surfaces downstream as
    # "no headship rate for age 35" — a message that reads as a CURVE bug and sends the
    # reader to the model instead of to the file.
    for key in ("headship", "central_shape"):
        if key not in payload:
            raise LoaderError(f"{path.name}: no {key!r} key (keys: {sorted(payload)})")
    _verify_headship_provenance(payload, path)
    return payload, path, _headship_curves(payload, path)


def _headship_curves(payload: dict, path: Path) -> dict[str, dict[int, float]]:
    """{shape: {int age: rate}} for EVERY carried shape, strictly joined over 0..100.

    BOTH SHAPES, NOT ONLY THE CENTRAL ONE. A holed `expo_cum_fb` curve would break a robustness
    sweep leg silently — exactly the class `owner_stock._headship`'s message exists to prevent
    — and a completeness check that ran only on the shape the headline reads would never see
    it (the same argument the ownership sibling records for the SHARED read path).

    THE JSON-STR / IN-MEMORY-INT ASYMMETRY IS CLOSED HERE, ONCE. Artifact keys are strings
    because JSON has no integer keys; every consumer wants ints. `"07"` and `"3.0"` both cast
    into an age that already exists, so the cast is followed by an equality check against the
    full expected age set rather than a length check — a collision loses a key silently and a
    length check alone would then pass on the wrong 101.
    """
    curves = payload["headship"]
    if not isinstance(curves, dict):
        raise LoaderError(
            f"{path.name}: `headship` is {type(curves).__name__}, expected an object keyed by "
            f"shape (carried shapes: {list(HEADSHIP_SHAPES)})")
    missing_shapes = [shape for shape in HEADSHIP_SHAPES if shape not in curves]
    if missing_shapes:
        raise LoaderError(
            f"{path.name}: headship curve missing for shapes: {missing_shapes} (strict join) "
            "— the robustness sweep varies this axis, so an absent arm makes `rank_stable` a "
            "verdict over a grid the run could not evaluate")
    expected = set(range(0, _POP_TERMINAL_AGE + 1))
    out: dict[str, dict[int, float]] = {}
    for shape in HEADSHIP_SHAPES:
        typed: dict[int, float] = {}
        for raw_age, value in curves[shape].items():
            try:
                age = int(str(raw_age))
            except (TypeError, ValueError) as exc:
                raise LoaderError(
                    f"{path.name}: headship[{shape}] carries the non-integer age key "
                    f"{raw_age!r} — an age key that does not parse cannot be joined against "
                    "the population lattice") from exc
            if str(raw_age) != str(age):
                raise LoaderError(
                    f"{path.name}: headship[{shape}] age key {raw_age!r} is not the canonical "
                    f"spelling of {age} — two spellings of one age collide silently on cast")
            typed[age] = value
        got = set(typed)
        if got != expected:
            raise LoaderError(
                f"{path.name}: headship[{shape}] covers {len(typed)} ages; missing "
                f"{sorted(expected - got)}, unexpected {sorted(got - expected)} (strict join)")
        out[shape] = typed
    if payload["central_shape"] not in HEADSHIP_SHAPES:
        raise LoaderError(
            f"{path.name}: `central_shape` is {payload['central_shape']!r}, which is not one "
            f"of the carried shapes {list(HEADSHIP_SHAPES)}")
    return out


def load_headship_curves(data_dir: Path | None = None) -> dict[str, dict[int, float]]:
    """EVERY carried shape, int-keyed — what the pipeline holds, because the robustness sweep
    evaluates the axis and re-reading the artifact per leg would re-verify the same bytes."""
    return _read_verified_headship(data_dir)[2]


def load_headship_rates(data_dir: Path | None = None, shape: str | None = None) -> dict[int, float]:
    """ONE shape's curve as {int age: rate}.

    `shape=None` falls back to the artifact's own `central_shape`. THE PIPELINE NEVER RELIES
    ON THAT DEFAULT — it passes the shape explicitly from `CENTRAL_ASSUMPTIONS`, so the run's
    shape selection lives in exactly one place and `assumptions_hash()` covers it. A second
    selection site reachable by a default is how a model choice moves the numbers under a
    byte-identical identity token.
    """
    payload, _path, curves = _read_verified_headship(data_dir)
    return headship_curve(curves, payload["central_shape"] if shape is None else shape)


def headship_curve(curves: dict[str, dict[int, float]], shape: str) -> dict[int, float]:
    """Select one arm, fail-loud. An unknown shape is a MIS-WIRED sweep leg, not a missing
    rate, and it must not degrade into an empty curve."""
    if shape not in curves:
        raise LoaderError(
            f"no headship curve for shape {shape!r} — carried shapes are "
            f"{sorted(curves)}; regenerate with `uv run python scripts/gen_headship.py`")
    return curves[shape]


def load_headship_vintage(data_dir: Path | None = None) -> RateVintage:
    """The vintage of the headship curve a consumer just loaded (run-6 carry).

    TWO sources, not one: the Census extract (maintainer numerator) AND the ISQ QC population
    workbook (person denominator). The record carries both, because an envelope that named
    only the Census vintage would describe half of what produced the curve — and it is exactly
    this two-source case that makes `raw_source_name` load-bearing: only the Census extract is
    cut from an uncommittable upstream member, while the byte-pinned ISQ workbook IS its own
    raw response, so the two entries of §7's map take their digests from different places.
    """
    payload, _path, _curves = _read_verified_headship(data_dir)
    return vintage_from_provenance(HEADSHIP_ARTIFACT, payload["_provenance"],
                                   raw_source_name=CENSUS_EXTRACT)


def headship_rate(headship: dict[int, float], age: int) -> float:
    """THE accessor — a DIRECT per-age read since ruling V; the band lookup is gone.

    ABSENT IS NOT ZERO at any age (falsifier F15): the curve is defined at every integer age
    0..100 and has no undefined region, so a missing age can only mean a holed or partially
    built curve — which would silently shrink the ED DENOMINATOR and scale |ED| AWAY FROM
    ZERO. `LoaderError` and never a bare `KeyError`, per `_count`'s taxonomy rule, and the
    message names the age and the generator that produces the curve.
    """
    if age not in headship:
        raise LoaderError(
            f"no headship rate for age {age} — the curve is age-resolved over 0..100 with no "
            "undefined region, so this is a holed curve; regenerate with `uv run python "
            "scripts/gen_headship.py`")
    return assert_fraction(f"headship[{age}]", headship[age])
