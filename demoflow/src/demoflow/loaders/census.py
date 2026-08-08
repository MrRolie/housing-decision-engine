"""Census ownership + headship loaders (spec §8/§7). Ownership: owner-maintainer
rate by geography x age band, STRICT full-geography join, fractions asserted in
[0,1]; HORS_RMR is province net of ALL SIX WHOLLY-QUÉBEC CMAs (codex r4-F2) — the
precise denotation, and NOT the same territory as ISQ's literal hors-RMR population
row, both recorded in _provenance. Headship: base-year households/person by age band
(PIT-fixed, §7 r3-F3).

DERIVATION, NEVER TRANSCRIPTION (steering ruling B, 2026-07-25): every rate is computed
by `derive_ownership_from_csv` from the pinned P2 extract; `data/ownership_by_geo_age.json`
is a BUILD ARTIFACT of `scripts/gen_ownership.py`, never hand-edited, and
`test_committed_ownership_json_equals_generator_output` proves the two equal. No OWNERSHIP
rate is hand-written anywhere in this package. Headship is explicitly OUT of ruling B's scope
(plan §Task 13 Step 1b — its persons-denominator comes from the ISQ pop loader, not the P2
CSV): `data/headship_by_age.json` carries six TYPED rates and is the one rate surface here
that is still transcription — a `borrowed_prior` input a later task derives once the pop
loader lands.

STALENESS REFUSES AT LOAD (steering ruling L, 2026-08-08): that no-drift gate is a TEST —
it defends the repo, not a runtime load. So `load_ownership_rates` independently checks the
artifact's recorded `_provenance.sha256` against the pins registry on EVERY load and raises
on an absent or mismatched digest. Two legs, neither subsuming the other: CI compares
CONTENT (artifact vs fresh derivation), the load path compares IDENTITY (recorded source
digest vs the pin). A stale or unprovenanced artifact never serves rates.
"""
import csv
import json
from pathlib import Path

from demoflow.errors import LoaderError
from demoflow.geography import Geography
from demoflow.loaders.pins import DATA_DIR, WORKBOOK_SHA256, verify_pin
from demoflow.loaders.validate import assert_fraction

CENSUS_EXTRACT = "census_tenure_age_98100231.csv"
OWNERSHIP_ARTIFACT = "ownership_by_geo_age.json"

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

_HEADSHIP_BANDS = (("0-19", 0, 19), ("20-34", 20, 34), ("35-54", 35, 54),
                   ("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 200))

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


def _read_totals_cube(csv_path: Path) -> dict[tuple[str, str], tuple[int, int]]:
    """{(GEO, age member): (owner, total)} over the `Total -` member of every non-age
    dimension. Positional read; duplicate keys raise (a duplicated or copied row would
    otherwise be silently absorbed into a rate)."""
    cube: dict[tuple[str, str], tuple[int, int]] = {}
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
            if row[_COL_STAT] != _STATISTIC:
                continue
            if any(row[col] != member for col, member in _TOTAL_MEMBERS.items()):
                continue
            key = (row[_COL_GEO], row[_COL_AGE])
            if key in cube:
                raise LoaderError(
                    f"{csv_path.name}:{lineno}: duplicate cell for {key} — the extract's "
                    "dimension address is not unique (row duplicated or payload copied?)")
            ctx = f"{csv_path.name}:{lineno} {key}"
            cube[key] = (_count(row[_COL_OWNER], ctx), _count(row[_COL_TOTAL], ctx))
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

    return {
        "_provenance": {
            "source": CENSUS_EXTRACT,
            "sha256": WORKBOOK_SHA256[CENSUS_EXTRACT],
            "statcan_table": "98-10-0231-01",
            "ref_date": "2021",
            "extracted_at": "2026-07-21",
            "derived_by": "demoflow.loaders.census.derive_ownership_from_csv",
            "generator": "demoflow/scripts/gen_ownership.py",
            "measure": "owner-maintainer households / total private households, at the "
                       "`Total -` member of every non-age dimension",
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
        },
        # The borrow flags live INSIDE `rates` because they are part of the rate table a
        # CONSUMER reads: `load_ownership_rates` returns this sub-tree and nothing else, so a
        # flag recorded only in `_provenance` prose would be invisible to every caller. (The
        # no-drift gate compares the WHOLE payload, `_provenance` included — it is not what
        # scopes this.)
        "rates": {geo.value: rates[geo.value] for geo in Geography},
    }


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


def load_ownership_rates(data_dir: Path | None = None) -> dict:
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
    return rates


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


def load_headship_rates(data_dir: Path | None = None) -> dict:
    path = (data_dir or DATA_DIR) / "headship_by_age.json"
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
    return payload["headship"]


def headship_rate(headship: dict, age: int) -> float:
    band = _band_for(age, _HEADSHIP_BANDS)
    if band not in headship:
        raise LoaderError(f"no headship rate for band {band}")
    return assert_fraction(f"headship[{band}]", headship[band])
