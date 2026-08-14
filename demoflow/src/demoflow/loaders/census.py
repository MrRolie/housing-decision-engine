"""Census ownership + headship loaders (spec §8/§7). Ownership: owner-maintainer
rate by geography x age band, STRICT full-geography join, fractions asserted in
[0,1]; HORS_RMR is province net of ALL SIX WHOLLY-QUÉBEC CMAs (codex r4-F2) — the
precise denotation, and NOT the same territory as ISQ's literal hors-RMR population
row, both recorded in _provenance. Headship: base-year households/person by age band
(PIT-fixed, §7 r3-F3).

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
scenario POPULATION, so headship(a) is
    QC private-household PRIMARY MAINTAINERS in band a  (committed P2 Census extract)
    ÷ ISQ 2021 Le Québec Référence (A2026) PERSONS in band a  (committed pop-as-qc-base.xlsx)
and nothing else. Both sources are sha256-pinned and read at derivation.

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

# Headship band -> (lo, hi, maintainer-age members). SAME shape as _AGE_BAND_SPEC and for the
# same reason (one source of truth: a band present for lookup but absent from the derivation is
# unrepresentable). The 0-19 band carries ONE constituent because the table publishes no
# maintainer member under 15 — see _ZERO_SUPPORT_NOTE for why the band is kept anyway.
_HEADSHIP_BAND_SPEC = (
    ("0-19", 0, 19, ("15 to 19 years",)),
    ("20-34", 20, 34, ("20 to 24 years", "25 to 29 years", "30 to 34 years")),
    ("35-54", 35, 54, ("35 to 39 years", "40 to 44 years",
                       "45 to 49 years", "50 to 54 years")),
    ("55-64", 55, 64, ("55 to 59 years", "60 to 64 years")),
    ("65-74", 65, 74, ("65 to 69 years", "70 to 74 years")),
    ("75+", 75, 200, ("75 to 84 years", "85 years and over")),
)
_HEADSHIP_BANDS = tuple((label, lo, hi) for label, lo, hi, _ in _HEADSHIP_BAND_SPEC)

# The extract's own published all-ages maintainer count — an INDEPENDENT aggregate the banded
# sum must close against (a dropped or duplicated constituent moves the sum by >= 10,920, the
# smallest member, while every rate stays a plausible fraction).
_MAINTAINER_TOTAL_MEMBER = "Total - Age of primary household maintainer"

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
    "the other surface is a silent double-count or a silent undercount."
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
    """Ownership is nested one level deeper than headship ({geography: {band: rate}}), so it
    types per geography — every one of them, borrowed members included: five of the eight
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
        prov_owner, prov_total = _band_counts(cube, _PROVINCE, members, ctx)
        for cma in _QC_CMAS:
            cma_owner, cma_total = _band_counts(cube, cma, members, ctx)
            prov_owner -= cma_owner
            prov_total -= cma_total
        hors[label] = _rate(prov_owner, prov_total, ctx)
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
        "statcan_table": "98-10-0231-01",
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


def _headship_value(maintainers: int, persons: float, ctx: str) -> float:
    """maintainers / persons with every degenerate named BEFORE the division."""
    if not math.isfinite(persons) or persons <= 0:
        raise LoaderError(f"{ctx}: non-positive person denominator {persons}")
    if maintainers < 0:
        raise LoaderError(f"{ctx}: negative maintainer count {maintainers}")
    if maintainers > persons:
        raise LoaderError(
            f"{ctx}: {maintainers} maintainers exceed {persons} persons — a headship rate "
            "above 1 means the numerator and denominator are not the same population")
    return assert_fraction(ctx, maintainers / persons)


def _zero_support_note(maintainers: int, persons: float) -> str:
    return (
        "THE 0-19 BAND, KEPT DELIBERATELY (T13b 2026-08-08): its numerator has support only at "
        "15-19 — there is no published maintainer member under 15 in 98-10-0231-01 — so the "
        f"band rate is {maintainers:,} maintainers aged 15-19 over {persons:,.0f} persons aged "
        "0-19. That IS the use-site rate and it is aggregate-consistent: spec:395 sums pop(a) x "
        "headship(a) x ownership(a) over ages, so this rate multiplied by the band's own "
        "population reproduces the published maintainer count exactly. It is NOT an "
        "age-resolved rate — a consumer multiplying a SINGLE age inside the band (spec §6's "
        "age-18 D_native term) must land an age-resolved curve rather than reuse this one. The "
        "band is kept rather than dropped because the pipeline builds a per-single-year curve "
        "over range(0, 101) (plan:4675), where a missing band RAISES, and because every "
        "consumer today pairs it with ownership(a) — undefined, hence contributing nothing, "
        "below the ownership lattice's floor of 25."
    )


def derive_headship_from_sources(csv_path: Path | str, workbook_path: Path | str) -> dict:
    """Compute the base-year headship curve from the TWO pinned sources.

    The ONLY producer of headship rates in this package. USE-SITE SEMANTICS (spec:395):
    `OwnerStock = Σ pop(a,g,t,s) × headship(a) × ownership(a)` multiplies ISQ scenario
    POPULATION, so headship(a) = QC private-household primary maintainers in band a ÷ ISQ
    persons in band a. Both sources are verified against their pins before a single value is
    computed — a curve derived from an unpinned vintage breaks the PIT chain while emitting
    perfectly plausible fractions (that is precisely how the retired typed curve survived).
    """
    csv_path, workbook_path = Path(csv_path), Path(workbook_path)
    verify_pin(csv_path, csv_path.name)
    cube = _read_totals_cube(csv_path)
    persons_by_age = _qc_persons_by_age(workbook_path)      # verifies its own pin

    maintainers: dict[str, int] = {}
    for label, _lo, _hi, members in _HEADSHIP_BAND_SPEC:
        ctx = f"headship[{label}]"
        total = 0
        for member in members:
            try:
                # index 1 = `Tenure (4):Total - Tenure[1]`: ALL private households in the cell.
                # The age dimension IS the maintainer's age, so that count is the numerator;
                # index 0 (owner households) belongs to the ownership rate, never to headship.
                total += cube[(_PROVINCE, member)][1]
            except KeyError as exc:
                raise LoaderError(
                    f"{ctx}: age member {member!r} absent for {_PROVINCE!r} — the band cannot "
                    "be summed (schema drift?)") from exc
        maintainers[label] = total

    published = cube.get((_PROVINCE, _MAINTAINER_TOTAL_MEMBER))
    if published is None:
        raise LoaderError(
            f"{csv_path.name}: the published {_MAINTAINER_TOTAL_MEMBER!r} member is absent for "
            f"{_PROVINCE!r} — the banded numerator has nothing independent to close against")
    published_total = published[1]
    banded = sum(maintainers.values())
    # StatCan rounds every cell to the nearest 5, so the banded constituents and the published
    # total each carry <= 2.5 of rounding error: the bound is 2.5 x (members + 1), DERIVED from
    # the member count rather than tuned to the observed delta (5 on the 2026-07-21 vintage) —
    # a gate tuned to today's value reds on a legitimate re-extract. It still catches a dropped
    # or duplicated constituent by three orders of magnitude (smallest member: 10,920).
    n_members = sum(len(members) for *_, members in _HEADSHIP_BAND_SPEC)
    tolerance = 2.5 * (n_members + 1)
    closure = (f"banded maintainers {banded:,} vs the extract's published "
               f"{_MAINTAINER_TOTAL_MEMBER!r} member {published_total:,}; delta "
               f"{banded - published_total:+,} inside the round-to-5 bound 2.5 x "
               f"({n_members} members + 1 total) = {tolerance:g}")
    if abs(banded - published_total) > tolerance:
        raise LoaderError(f"{csv_path.name}: headship numerator does not close — {closure}")

    rates: dict[str, float] = {}
    band_persons: dict[str, float] = {}
    for label, lo, hi, _members in _HEADSHIP_BAND_SPEC:
        band_persons[label] = sum(p for age, p in persons_by_age.items() if lo <= age <= hi)
        rates[label] = _headship_value(maintainers[label], band_persons[label],
                                       f"headship[{label}]")

    provenance = {
        "as_of": str(_POP_BASE_YEAR),
        "source": (
            f"Census 2021 QC private-household PRIMARY MAINTAINERS by age (StatCan "
            f"98-10-0231-01, committed extract {CENSUS_EXTRACT}, `Total -` member of every "
            f"non-age dimension at statistic {_STATISTIC!r}) DIVIDED BY ISQ "
            f"{_POP_BASE_YEAR} {_POP_LABEL} {_POP_SCENARIO} persons by single year of age "
            f"(committed {POP_QC_WORKBOOK}, both sexes) — DERIVED, never transcribed "
            "(steering ruling B); the denominator is PERSONS because the use site (spec:395 "
            "OwnerStock) multiplies ISQ scenario population"),
        "sources": {
            CENSUS_EXTRACT: WORKBOOK_SHA256[CENSUS_EXTRACT],
            POP_QC_WORKBOOK: WORKBOOK_SHA256[POP_QC_WORKBOOK],
        },
        "raw_source_sha256": raw_anchor(CENSUS_EXTRACT),
        "raw_source_member": raw_member(CENSUS_EXTRACT),
        "statcan_table": "98-10-0231-01",
        "isq_scenario": _POP_SCENARIO,
        "isq_geography": _POP_LABEL,
        "base_year_status": f"{_POP_BASE_STATUS} (réel — an observation, not a projection)",
        "extracted_at": "2026-07-21",
        "derived_by": "demoflow.loaders.census.derive_headship_from_sources",
        "generator": "demoflow/scripts/gen_headship.py",
        "measure": ("private-household primary maintainers in the band / persons in the SAME "
                    "band — households formed per PERSON, PIT-fixed at the base year (spec §7 "
                    "r3-F3)"),
        "multiplicand_note": _HEADSHIP_MULTIPLICAND_NOTE,
        "band_members": {label: list(members) for label, _lo, _hi, members in _HEADSHIP_BAND_SPEC},
        "band_persons": {label: band_persons[label] for label, *_ in _HEADSHIP_BAND_SPEC},
        "band_maintainers": {label: maintainers[label] for label, *_ in _HEADSHIP_BAND_SPEC},
        "numerator_closure": closure,
        "zero_support_note": _zero_support_note(maintainers["0-19"], band_persons["0-19"]),
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
            "the six TYPED rates carried until 2026-08-08 (0-19 0.02, 20-34 0.40, 35-54 0.48, "
            "55-64 0.52, 65-74 0.56, 75+ 0.62). The DIV re-triage measured them at this use "
            "site: 35-54 was 16.9% low, the 65-74 -> 75+ shape was INVERTED, and the aggregate "
            "understated QC households by 9.5%. Their `borrowed_prior` flag is RETIRED — these "
            "values are derived, not borrowed"),
    }
    _assert_anchor_typed(rates, provenance, "derive_headship_from_sources", kind="headship")
    return {"_provenance": provenance, "headship": rates}


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

    _assert_anchor_typed(payload["headship"], provenance, path.name, kind="headship")


def _read_verified_headship(data_dir: Path | None) -> tuple[dict, Path]:
    """Read + verify the headship artifact ONCE, for both the curve and the vintage accessor
    (the ownership sibling above carries the argument for sharing the path)."""
    path = (data_dir or DATA_DIR) / HEADSHIP_ARTIFACT
    if not path.exists():
        raise LoaderError(f"headship fixture not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # STRICT key — deliberately NOT `load_ownership_rates`'s `.get("rates", {})`, which is
    # plan-verbatim and whose renamed-key path reports a missing-GEOGRAPHY error instead of a
    # file-level one (measured 2026-08-08). A `.get("headship", {})` here would degrade a
    # renamed or absent top-level key into an empty curve, which then surfaces downstream as
    # "no headship rate for band 35-54" — a message that reads as a BAND bug and sends the
    # reader to the lattice instead of to the file.
    if "headship" not in payload:
        raise LoaderError(f"{path.name}: no 'headship' key (keys: {sorted(payload)})")
    _verify_headship_provenance(payload, path)
    # Strict join on the SHARED path, for the reason the ownership sibling records: a
    # completeness check that runs only in the rate accessor lets the vintage accessor state a
    # confident vintage for a curve no run may use (measured 2026-08-14 on a dropped band).
    missing = [label for label, _lo, _hi in _HEADSHIP_BANDS if label not in payload["headship"]]
    if missing:
        raise LoaderError(f"{path.name}: headship rate missing for bands: {missing} (strict join)")
    return payload, path


def load_headship_rates(data_dir: Path | None = None) -> dict:
    return _read_verified_headship(data_dir)[0]["headship"]


def load_headship_vintage(data_dir: Path | None = None) -> RateVintage:
    """The vintage of the headship curve a consumer just loaded (run-6 carry).

    TWO sources, not one: the Census extract (maintainer numerator) AND the ISQ QC population
    workbook (person denominator). The record carries both, because an envelope that named
    only the Census vintage would describe half of what produced the curve — and it is exactly
    this two-source case that makes `raw_source_name` load-bearing: only the Census extract is
    cut from an uncommittable upstream member, while the byte-pinned ISQ workbook IS its own
    raw response, so the two entries of §7's map take their digests from different places.
    """
    payload, _path = _read_verified_headship(data_dir)
    return vintage_from_provenance(HEADSHIP_ARTIFACT, payload["_provenance"],
                                   raw_source_name=CENSUS_EXTRACT)


def headship_rate(headship: dict, age: int) -> float:
    band = _band_for(age, _HEADSHIP_BANDS)
    if band not in headship:
        raise LoaderError(f"no headship rate for band {band}")
    return assert_fraction(f"headship[{band}]", headship[band])
