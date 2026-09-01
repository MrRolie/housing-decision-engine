"""P7 — the closed-cohort 75+ net-migration evidence probe (spec §5 r3-F2, rulings J + K).

Writes `probes/closed-cohort-migration.md`. This module is that file's ONLY writer: it owns
the title, the provenance header, the measured StatCan evidence, and the compo section
(whose lines come from `demoflow.loaders.compo.compo_evidence_lines`, which returns lines and
writes nothing). Two writers for one artifact is a hand-edit surface by another name — the
one that ran last would silently define the file.

WHY THIS PROBE EXISTS. Spec §5 r3-F2 closes the 75+ owner cohort after band entry: post-entry
net migration at ages 75+ is OMITTED. The spec's original evidence prescription pointed at the
ISQ `compo-*` workbooks; steering ruling J REFUTED that (those workbooks carry no age axis at
all) and RE-POINTED the leg at an age-structured migration source, with a MATERIALITY TRIPWIRE:
a measured rate above 1%/yr in any modeled geography escalates the altitude call to the
operator. This probe supplies that measurement.

WHAT IS MEASURED, exactly:

    net_migration(g, t) = Σ over the four 75+ bands of
        Immigrants − Net emigration + Net interprovincial migration
                   + Net intraprovincial migration + Net non-permanent residents
    rate(g, t) = |net_migration(g, t)| / P75plus(g, t) , P75plus = the July-1 START-of-period
                 75+ population of the SAME geography, summed over the same four bands.

`Net emigration` (component 4) is used WHOLE. Components 5/6/7 (`Emigrants`, `Returning
emigrants`, `Net temporary emigration`) are its CHILDREN — adding them alongside it would
double-count, and MEASURED 2026-08-07 `Net temporary emigration` is unpublished from 2016/17
onward, so a build-it-from-the-parts form would also silently lose the last nine periods.

MEMBER IDS ARE RESOLVED BY NAME, EVERY RUN. The components cubes carry 114 age members and the
population cubes 115 (the population cubes add `Average age` and `Median age`; the components
cubes add `-1 year`), so the SAME age band sits at DIFFERENT member ids across the pair —
MEASURED: `75 to 79 years` is id 93 in the components cubes and id 92 in the population cubes.
A hardcoded id table would silently divide one age band's migration by another age band's
population and publish the quotient as a rate.

RESPONSES ARE KEYED BY (productId, coordinate), NEVER BY REQUEST ORDER. MEASURED 2026-08-07:
`getDataFromCubePidCoordAndLatestNPeriods` returns its objects sorted by coordinate STRING, not
in request order, so a positional read pairs every series with the wrong one.

THE FLOOR GUARDS (each raises `ProbeRefusal`, which routes the run to UNKNOWN-PROBE-FAILED —
never to a friendlier verdict). `ProbeRefusal` is deliberately NOT a network-class exception
name, so a refusal can never launder itself into `pytest.skip`:

  * `_guard_meta`      — the four cubes answered with the dimensions this run reads.
  * `_guard_coverage`  — every modeled `Geography` member is either MEASURED here or recorded
                         NOT-COVERED. A geography that silently dropped out of the loop could
                         hide the very exceedance the tripwire exists to catch.
  * `_guard_response`  — every requested series came back, non-empty.
  * `_guard_span`      — every series covers the cube's FULL published span, contiguous. This
                         is ruling K's window rule as code: "a window whose sole visible effect
                         is to remove the exceedance is not evidence."
  * `_guard_published` — no null datapoint outside the ONE series measured to carry nulls
                         (`Residual deviation`, unpublished for the last four periods). An
                         all-null response would otherwise read as a rate of exactly zero.
  * `_guard_identity`  — the All-ages demographic accounting identity closes EXACTLY:
                         P(t+1) − P(t) = Births − Deaths + Immigrants − Net emigration
                         + Net interprovincial + Net intraprovincial + Net non-permanent
                         residents + Residual deviation. MEASURED exact (max |difference| = 0
                         persons) across all 7 geographies × 24 periods. This is the alignment
                         guard: it fails if the geography junction, the period pairing, the
                         cube pairing or the component signs are wrong, none of which any
                         single-series check can see.
"""
import contextlib
from dataclasses import dataclass
from pathlib import Path

from _wds import (
    WDS_DATA,
    WDS_META,
    Fact,
    new_run,
    post,
    provenance_header,
    table_number,
    table_url,
)

from demoflow.geography import RA_PROXY_MEMBERS, Geography
from demoflow.loaders.compo import compo_evidence_lines, load_immigrant_flows

OUT = Path(__file__).resolve().parent / "closed-cohort-migration.md"

_WRITTEN_BY = Path(__file__).name
_SCOPE = (
    "Scope: spec §5 r3-F2's closed-cohort omission — the 75+ net-migration rate it omits, "
    "measured over the FULL published span of StatCan's components-of-population-change and "
    "population-estimate cubes, per modeled geography."
)
_CITED_LABEL = "Externally cited figures (NOT computed by this run):"

_TITLE = "# Closed-cohort migration assumption — evidence (spec §5 r3-F2)"


def _summary(*, total: int, derived: int, cited: int) -> str:
    return (
        f"This run registered {total} provenance-tagged figures: {derived} DERIVED (computed "
        f"here from the live responses named beside them) and {cited} CITED (published "
        f"elsewhere, quoted with their source)."
    )


# --- boundaries this run can attribute a failure to -------------------------------------
BOUNDARIES = ("wds-meta", "wds-data", "compo-workbook")
_UNATTRIBUTED = "unattributed"

# --- the cubes ---------------------------------------------------------------------------
COMPONENTS_CMA_PID = 17100149
COMPONENTS_ER_PID = 17100151
POPULATION_CMA_PID = 17100148
POPULATION_ER_PID = 17100150
PIDS = (COMPONENTS_CMA_PID, COMPONENTS_ER_PID, POPULATION_CMA_PID, POPULATION_ER_PID)

# Dimension positions. The components cubes carry a Components axis the population cubes do
# not, so Gender and Age sit one position later there.
_POS_GEO = 1
_POS_COMPONENT = 2
_POS_GENDER_COMPONENTS, _POS_AGE_COMPONENTS = 3, 4
_POS_GENDER_POPULATION, _POS_AGE_POPULATION = 2, 3

_ALL_AGES = "All ages"
_TOTAL_GENDER = "Total - gender"
BANDS_75_PLUS = ("75 to 79 years", "80 to 84 years", "85 to 89 years", "90 years and older")

# The migration decomposition, with the sign each term enters net migration with.
MIGRATION_COMPONENTS = {
    "Immigrants": +1,
    "Net emigration": -1,
    "Net interprovincial migration": +1,
    "Net intraprovincial migration": +1,
    "Net non-permanent residents": +1,
}
# The accounting identity adds natural increase to the same migration terms.
IDENTITY_COMPONENTS = {"Births": +1, "Deaths": -1, **MIGRATION_COMPONENTS}
RESIDUAL_COMPONENT = "Residual deviation"
# The ONE series measured to carry nulls (unpublished for the most recent periods). Every
# other datapoint this run reads must be published, or `_guard_published` refuses.
NULLABLE_COMPONENTS = frozenset({RESIDUAL_COMPONENT})

# Spec §5 r3-F2 (steering ruling J): the materiality threshold, in percent per year.
TRIPWIRE_PCT = 1.0

_DATA_CHUNK = 60
_LATEST_WINDOW = 5


@dataclass(frozen=True)
class GeoSource:
    """A modeled geography's DECLARED junction into the StatCan cubes.

    `declared_class` is the independent witness: the classification code this run expects
    beside the resolved member name. Declaring it makes a renumbered or re-boundaried edition
    VISIBLE (`_guard_coverage` compares it against what the live metadata carries) instead of
    silently re-pointing a modeled geography at a different territory.
    """

    tag: str
    components_pid: int
    population_pid: int
    member_name: str
    declared_class: str
    axis: str


# Québec's economic regions are the administrative regions, which is what makes the ER cubes
# usable for the RA-indexed modeled members. That correspondence is DECLARED here, not
# measured — the recorded classification code is what makes a drift in it visible.
GEOGRAPHY_SOURCES = (
    GeoSource(Geography.MTL_RMR.value, COMPONENTS_CMA_PID, POPULATION_CMA_PID,
              "Montréal (CMA), Quebec", "462", "census metropolitan area"),
    GeoSource(Geography.QC_RMR.value, COMPONENTS_CMA_PID, POPULATION_CMA_PID,
              "Québec (CMA), Quebec", "421", "census metropolitan area"),
    GeoSource(Geography.MTL_ISLAND_RA06.value, COMPONENTS_ER_PID, POPULATION_ER_PID,
              "Montréal, Quebec", "2440", "economic region (= RA06)"),
    GeoSource(Geography.LAVAL_RA13.value, COMPONENTS_ER_PID, POPULATION_ER_PID,
              "Laval, Quebec", "2445", "economic region (= RA13)"),
    GeoSource(Geography.LANAUDIERE_RA14_PROXY.value, COMPONENTS_ER_PID, POPULATION_ER_PID,
              "Lanaudière, Quebec", "2450", "economic region (= RA14)"),
    GeoSource(Geography.LAURENTIDES_RA15_PROXY.value, COMPONENTS_ER_PID, POPULATION_ER_PID,
              "Laurentides, Quebec", "2455", "economic region (= RA15)"),
    GeoSource(Geography.MONTEREGIE_RA16_PROXY.value, COMPONENTS_ER_PID, POPULATION_ER_PID,
              "Montérégie, Quebec", "2435", "economic region (= RA16)"),
)

# Recorded as NOT-COVERED, never approximated (ruling K). A province-minus-CMAs residual would
# manufacture an age-structured migration series neither cube publishes.
NOT_COVERED = {
    Geography.HORS_RMR.value: (
        "the residual 'territory outside the CMAs' is neither a census metropolitan area nor "
        "an economic region, so NEITHER cube publishes it; a province-minus-CMAs residual "
        "would manufacture an age-structured migration series no source published"
    ),
}

COMPO_WORKBOOK = "compo-rmr-base.xlsx"


class ProbeRefusal(RuntimeError):
    """A floor guard refusing to publish an unearned verdict.

    The TYPE NAME matters as much as the message: `tests/_probe_asserts.NETWORK_EXCEPTIONS`
    decides fail-vs-skip from the exception type a note records, and `ProbeRefusal` is
    deliberately outside it. A refusal must redden the suite even while StatCan is down —
    an outage may excuse a missing measurement, never a broken one.
    """

    def __init__(self, boundary: str, message: str) -> None:
        super().__init__(message)
        _require_known_boundary(boundary)
        self.boundary = boundary


def _require_known_boundary(boundary: str) -> None:
    """Refuse a boundary name outside `BOUNDARIES`.

    A typo'd boundary does not fail on its own — it publishes `LIVE PROBE FAILED-AT: wsd-data`,
    which the skip gate cannot parse, so it reports "no parseable boundary" and the reader
    learns the note is malformed rather than which host went down. Failing here names the
    real defect at the point it is introduced.
    """
    if boundary not in BOUNDARIES:
        raise ValueError(f"boundary {boundary!r} is not one of {list(BOUNDARIES)}; a failure "
                         f"attributed to an unknown boundary cannot be checked against a host")


@contextlib.contextmanager
def _at(boundary: str, where: list):
    """Record which boundary the run is touching, so a raised exception can be attributed.

    The exception TYPE is left untouched (the skip gate reads it), so the boundary rides
    beside it rather than inside a wrapper class that would erase `URLError` into something
    the gate cannot recognise as an outage.

    The reset on NORMAL exit is load-bearing: without it, a defect raised in the note-assembly
    that runs after the last boundary closes would be attributed to that boundary — a code
    fault wearing the label of a live surface it never touched. An exception skips the reset,
    which is exactly the case where the label is true.
    """
    _require_known_boundary(boundary)
    where[0] = boundary
    yield
    where[0] = _UNATTRIBUTED


# --- live boundaries (the two patchable seams) -------------------------------------------
def _meta(pids) -> list:
    """POST getCubeMetadata for every cube this run reads. Boundary: wds-meta."""
    return post(WDS_META, [{"productId": pid} for pid in pids])


def _data(requests: list) -> list:
    """POST getDataFromCubePidCoordAndLatestNPeriods, chunked. Boundary: wds-data.

    No try/except, no retry, no sentinel: a swallowed HTTP error here would reach
    `_guard_response` as a missing series and be reported as StatCan not publishing it.
    """
    out = []
    for start in range(0, len(requests), _DATA_CHUNK):
        out += post(WDS_DATA, requests[start:start + _DATA_CHUNK])
    return out


# --- guards -------------------------------------------------------------------------------
def _guard_meta(pids, response) -> dict:
    """Every cube answered SUCCESS and carries the dimensions this run reads."""
    if not isinstance(response, list):
        raise ProbeRefusal("wds-meta", f"getCubeMetadata returned "
                                       f"{type(response).__name__}, not a list")
    if len(response) != len(pids):
        raise ProbeRefusal("wds-meta", f"getCubeMetadata returned {len(response)} object(s) "
                                       f"for {len(pids)} requested cube(s)")
    metas = {}
    for item in response:
        if item.get("status") != "SUCCESS":
            raise ProbeRefusal("wds-meta", f"getCubeMetadata status {item.get('status')!r}")
        obj = item["object"]
        metas[int(obj["productId"])] = obj
    missing = [pid for pid in pids if pid not in metas]
    if missing:
        raise ProbeRefusal("wds-meta", f"getCubeMetadata answered for {sorted(metas)}, missing {missing}")
    for pid, obj in sorted(metas.items()):
        dims = {d["dimensionPositionId"]: d for d in obj.get("dimension", [])}
        needed = (_POS_GEO, _POS_COMPONENT, _POS_GENDER_COMPONENTS, _POS_AGE_COMPONENTS) \
            if pid in (COMPONENTS_CMA_PID, COMPONENTS_ER_PID) \
            else (_POS_GEO, _POS_GENDER_POPULATION, _POS_AGE_POPULATION)
        for pos in needed:
            if pos not in dims or not dims[pos].get("member"):
                raise ProbeRefusal("wds-meta", f"{table_number(pid)} carries no populated "
                                               f"dimension at position {pos}")
    return metas


def _dimension(metas: dict, pid: int, position: int) -> dict:
    """The cube's dimension at `position`, from the metadata `_guard_meta` already screened.

    Shared with the note assembly on purpose: every age-member COUNT the note prints is read
    from the same live dimension the resolver walks, so the sentence justifying name
    resolution moves with the cube instead of quoting an edition someone once measured.
    """
    return next(d for d in metas[pid]["dimension"] if d["dimensionPositionId"] == position)


def _member(metas: dict, pid: int, position: int, name: str) -> dict:
    """Resolve a member BY NAME. Raises rather than falling back to an id.

    The fallback a probe is tempted to write here — "use the id that worked last time" — is
    exactly what the age-member offset between the two cube families punishes.
    """
    dim = _dimension(metas, pid, position)
    for member in dim["member"]:
        if member["memberNameEn"] == name:
            return member
    raise ProbeRefusal(
        "wds-meta",
        f"{table_number(pid)} dimension {position} publishes no member named {name!r} "
        f"({len(dim['member'])} members present) — resolving it by a remembered id instead "
        f"would divide one band's migration by another band's population")


def _guard_coverage(metas: dict) -> list:
    """Every modeled Geography is MEASURED here or recorded NOT-COVERED, and each measured
    member's live classification code matches the declared one.

    A geography that silently dropped out of the source junction would be absent from the
    maximum the tripwire is evaluated on — an unevaluated geography reads as a passing one.
    """
    declared = {source.tag for source in GEOGRAPHY_SOURCES}
    modeled = {geography.value for geography in Geography}
    overlap = declared & set(NOT_COVERED)
    if overlap:
        raise ProbeRefusal("wds-meta", f"geographies declared BOTH measured and NOT-COVERED: "
                                       f"{sorted(overlap)}")
    unhandled = modeled - declared - set(NOT_COVERED)
    if unhandled:
        raise ProbeRefusal("wds-meta", f"modeled geographies with no declared source and no "
                                       f"NOT-COVERED record: {sorted(unhandled)} — an "
                                       f"unevaluated geography is not a passing one")
    stray = (declared | set(NOT_COVERED)) - modeled
    if stray:
        raise ProbeRefusal("wds-meta", f"declared geographies outside the modeled enum: "
                                       f"{sorted(stray)}")
    resolved = []
    for source in GEOGRAPHY_SOURCES:
        member = _member(metas, source.components_pid, _POS_GEO, source.member_name)
        live_class = str(member.get("classificationCode"))
        if live_class != source.declared_class:
            raise ProbeRefusal(
                "wds-meta",
                f"{source.tag}: {source.member_name!r} carries classification code "
                f"{live_class!r}, declared {source.declared_class!r} — the member name now "
                f"points at a different territory")
        resolved.append((source, member))
    return resolved


def _coord(*ids: int) -> str:
    return ".".join(str(i) for i in ids) + ".0" * (10 - len(ids))


def _build_requests(metas: dict, resolved: list) -> tuple[list, dict]:
    """One request per series, plus the key map that pairs each series back to its meaning."""
    requests, keys = [], {}

    def add(pid: int, coordinate: str, key: tuple) -> None:
        keys[key] = (pid, coordinate)
        requests.append({"productId": pid, "coordinate": coordinate, "latestN": 40})

    for source, geo_member in resolved:
        cpid, ppid = source.components_pid, source.population_pid
        gender_c = _member(metas, cpid, _POS_GENDER_COMPONENTS, _TOTAL_GENDER)["memberId"]
        gender_p = _member(metas, ppid, _POS_GENDER_POPULATION, _TOTAL_GENDER)["memberId"]
        geo_p = _member(metas, ppid, _POS_GEO, source.member_name)["memberId"]
        all_ages_c = _member(metas, cpid, _POS_AGE_COMPONENTS, _ALL_AGES)["memberId"]
        all_ages_p = _member(metas, ppid, _POS_AGE_POPULATION, _ALL_AGES)["memberId"]

        for component in (*IDENTITY_COMPONENTS, RESIDUAL_COMPONENT):
            cid = _member(metas, cpid, _POS_COMPONENT, component)["memberId"]
            add(cpid, _coord(geo_member["memberId"], cid, gender_c, all_ages_c),
                (source.tag, "identity", component))
        for component in MIGRATION_COMPONENTS:
            cid = _member(metas, cpid, _POS_COMPONENT, component)["memberId"]
            for band in BANDS_75_PLUS:
                aid = _member(metas, cpid, _POS_AGE_COMPONENTS, band)["memberId"]
                add(cpid, _coord(geo_member["memberId"], cid, gender_c, aid),
                    (source.tag, "migration", component, band))
        add(ppid, _coord(geo_p, gender_p, all_ages_p), (source.tag, "population", _ALL_AGES))
        for band in BANDS_75_PLUS:
            aid = _member(metas, ppid, _POS_AGE_POPULATION, band)["memberId"]
            add(ppid, _coord(geo_p, gender_p, aid), (source.tag, "population", band))
    return requests, keys


def _guard_response(requests: list, response) -> dict:
    """Key every returned series by (productId, coordinate) and prove none is missing.

    Keying by POSITION is the defect this refuses: MEASURED 2026-08-07, WDS returns its
    objects sorted by coordinate string, not in request order, so a positional read pairs
    every series with the wrong one — and the identity guard downstream would then fail for
    a reason that has nothing to do with the data.
    """
    if not isinstance(response, list):
        raise ProbeRefusal("wds-data", f"getData returned {type(response).__name__}, not a list")
    series = {}
    for item in response:
        if item.get("status") != "SUCCESS":
            raise ProbeRefusal("wds-data", f"getData status {item.get('status')!r}")
        obj = item["object"]
        points = obj.get("vectorDataPoint") or []
        if not points:
            raise ProbeRefusal("wds-data", f"{table_number(obj['productId'])} coordinate "
                                           f"{obj['coordinate']} returned zero data points")
        series[(int(obj["productId"]), obj["coordinate"])] = {
            point["refPer"][:4]: point["value"] for point in points}
    wanted = {(request["productId"], request["coordinate"]) for request in requests}
    missing = sorted(wanted - set(series))
    if missing:
        raise ProbeRefusal("wds-data", f"{len(missing)} of {len(wanted)} requested series did "
                                       f"not come back (first: {missing[0]})")
    return series


def _published_span(meta_obj: dict) -> list:
    """The contiguous reference years the cube DECLARES it publishes."""
    start = int(str(meta_obj["cubeStartDate"])[:4])
    end = int(str(meta_obj["cubeEndDate"])[:4])
    if end < start:
        raise ProbeRefusal("wds-meta", f"{table_number(meta_obj['productId'])} declares "
                                       f"cubeEndDate before cubeStartDate")
    return [str(year) for year in range(start, end + 1)]


def _observed_spans(series: dict, keys: dict) -> dict:
    """The periods each cube's series ACTUALLY carry — derivation only, no check.

    Deliberately separate from `_guard_span`, and deliberately what every downstream
    computation reads. If the span check lived in here, neutering it in a mutation test would
    also delete the derivation and the run would die on a KeyError instead of publishing the
    fabricated verdict the guard exists to prevent — which would "prove" the guard load-bearing
    for the wrong reason.
    """
    spans: dict = {}
    for _key, (pid, coordinate) in sorted(keys.items()):
        spans.setdefault(pid, sorted(series[(pid, coordinate)]))
    return spans


def _guard_span(metas: dict, series: dict, keys: dict) -> None:
    """Every series must cover its cube's FULL declared span, contiguously.

    Ruling K as code: the tripwire is evaluated on the full published span, and "a window
    whose sole visible effect is to remove the exceedance is not evidence." A silently
    truncated response is exactly that window, arriving without anyone choosing it.
    """
    declared = {pid: _published_span(meta_obj) for pid, meta_obj in metas.items()}
    for key, (pid, coordinate) in sorted(keys.items()):
        got = sorted(series[(pid, coordinate)])
        if got != declared[pid]:
            raise ProbeRefusal(
                "wds-data",
                f"{key} ({table_number(pid)} {coordinate}) covers {len(got)} periods "
                f"{got[:1]}..{got[-1:]}, but the cube declares {len(declared[pid])} periods "
                f"{declared[pid][0]}..{declared[pid][-1]} — a window that removes periods is "
                f"not evidence about the full span")


def _guard_published(series: dict, keys: dict) -> int:
    """No null datapoint outside the ONE series measured to carry them.

    An all-null migration response coerced to zero publishes a rate of exactly 0.0000%/yr for
    every geography — a clean, fabricated no-exceedance. MEASURED 2026-08-07: all 1440 of the
    75+ band migration datapoints are published; only `Residual deviation` carries nulls (the
    last four periods), and it enters the identity alone.
    """
    nullable = 0
    for key, (pid, coordinate) in sorted(keys.items()):
        component = key[2] if len(key) > 2 else None
        for year, value in sorted(series[(pid, coordinate)].items()):
            if value is None:
                if component in NULLABLE_COMPONENTS:
                    nullable += 1
                    continue
                raise ProbeRefusal("wds-data", f"{key} is unpublished at {year} — a null "
                                               f"coerced to zero would read as a measured zero")
    return nullable


def _value(series: dict, keys: dict, key: tuple, year: str) -> float:
    raw = series[keys[key]][year]
    return 0.0 if raw is None else float(raw)


def _guard_identity(series: dict, keys: dict, resolved: list, spans: dict) -> dict:
    """The All-ages accounting identity must close EXACTLY, every geography, every period.

    P(t+1) − P(t) = Births − Deaths + Immigrants − Net emigration + Net interprovincial
                  + Net intraprovincial + Net non-permanent residents + Residual deviation

    This is the alignment guard, and it is the only one that can see a WRONG-BUT-WELL-FORMED
    response: a mis-resolved geography, a mis-paired cube, an off-by-one period join or a
    flipped component sign all leave every single-series check perfectly happy. MEASURED
    2026-08-07 exact — max |difference| = 0 persons over 7 geographies × 24 periods — so the
    tolerance is ZERO and no epsilon is available to absorb a real defect.
    """
    worst, checked = 0.0, 0
    for source, _ in resolved:
        years = spans[source.components_pid]
        population = spans[source.population_pid]
        for year in years:
            following = str(int(year) + 1)
            if following not in population:
                raise ProbeRefusal(
                    "wds-data",
                    f"{source.tag}: the components period {year} has no {following} "
                    f"population to close against — the cubes' spans do not overlap the way "
                    f"a start-of-period denominator requires")
            change = (_value(series, keys, (source.tag, "population", _ALL_AGES), following)
                      - _value(series, keys, (source.tag, "population", _ALL_AGES), year))
            components = sum(
                sign * _value(series, keys, (source.tag, "identity", component), year)
                for component, sign in IDENTITY_COMPONENTS.items())
            components += _value(series, keys, (source.tag, "identity", RESIDUAL_COMPONENT),
                                 year)
            difference = components - change
            checked += 1
            worst = max(worst, abs(difference))
            if difference != 0:
                raise ProbeRefusal(
                    "wds-data",
                    f"{source.tag} {year}: the accounting identity is off by {difference:+.0f} "
                    f"persons (components {components:+.0f} vs population change "
                    f"{change:+.0f}) — the geography junction, the cube pairing, the period "
                    f"join or a component sign is wrong")
    return {"max_abs_difference": worst, "checked": checked}


# --- measurement --------------------------------------------------------------------------
def _period(year: str) -> str:
    return f"{year}/{str(int(year) + 1)[2:]}"


def _rates(series: dict, keys: dict, resolved: list, spans: dict) -> list:
    """One (geography, period, net migration, 75+ population, |rate| %/yr) row per cell."""
    rows = []
    for source, _ in resolved:
        for year in spans[source.components_pid]:
            net = sum(
                sign * _value(series, keys, (source.tag, "migration", component, band), year)
                for component, sign in MIGRATION_COMPONENTS.items()
                for band in BANDS_75_PLUS)
            population = sum(
                _value(series, keys, (source.tag, "population", band), year)
                for band in BANDS_75_PLUS)
            if population <= 0:
                raise ProbeRefusal("wds-data", f"{source.tag} {year}: 75+ population is "
                                               f"{population} — no rate is defined on it")
            rows.append((source.tag, year, net, population, abs(net) / population * 100.0))
    return rows


def _sections(where: list) -> list:
    """Every measured section of the note. Raises to the UNKNOWN branch on any refusal."""
    with _at("wds-meta", where):
        meta_response = _meta(PIDS)
    metas = _guard_meta(PIDS, meta_response)
    resolved = _guard_coverage(metas)

    requests, keys = _build_requests(metas, resolved)
    with _at("wds-data", where):
        data_response = _data(requests)
    series = _guard_response(requests, data_response)
    spans = _observed_spans(series, keys)
    _guard_span(metas, series, keys)
    nullable = _guard_published(series, keys)
    identity = _guard_identity(series, keys, resolved, spans)
    rows = _rates(series, keys, resolved, spans)

    with _at("compo-workbook", where):
        compo_lines = compo_evidence_lines(load_immigrant_flows(COMPO_WORKBOOK))

    return _evidence_lines(metas, resolved, keys, spans, nullable, identity, rows,
                           compo_lines)


def _evidence_lines(metas, resolved, keys, spans, nullable, identity, rows,
                    compo_lines) -> list:
    component_span = spans[COMPONENTS_CMA_PID]
    n_periods = Fact.derived(len(component_span),
                             f"count of reference periods {table_number(COMPONENTS_CMA_PID)} "
                             f"declares, and that every series read from it returned")
    span_fact = Fact.derived(f"{_period(component_span[0])}–{_period(component_span[-1])}",
                             "cubeStartDate..cubeEndDate of the components cubes, rendered as "
                             "flow intervals")
    n_series = Fact.derived(len(keys), "count of distinct WDS series this run requested and "
                                       "matched back by (productId, coordinate)")
    # A span is a PER-CUBE quantity and the two families do not share one, so the total series
    # count cannot be quoted beside a single period figure: 24 periods is true of the
    # components cubes and false of every population series requested. The breakdown states
    # each cube's own pair, and decomposes `n_series` while it is at it.
    per_cube = {pid: sum(1 for cube, _ in keys.values() if cube == pid) for pid in PIDS}
    span_breakdown = Fact.derived(
        "; ".join(f"{table_number(pid)} ({per_cube[pid]} series, {len(spans[pid])} periods)"
                  for pid in PIDS),
        "series requested per cube, each beside THAT cube's own returned span length — the "
        "per-cube pair `_guard_span` checks every series against")
    n_cells = Fact.derived(len(rows), "count of geography-periods a rate was computed on")
    nulls_fact = Fact.derived(nullable, f"count of null datapoints found, all of them in "
                                        f"`{RESIDUAL_COMPONENT}`")
    identity_fact = Fact.derived(
        f"{identity['max_abs_difference']:.0f}",
        f"max |components + residual − population change|, in persons, over "
        f"{identity['checked']} All-ages geography-periods")

    exceedances = sorted((row for row in rows if row[4] > TRIPWIRE_PCT),
                         key=lambda row: (row[0], row[1]))
    exceeding = sorted({row[0] for row in exceedances})
    fired = bool(exceedances)
    verdict = "EVIDENCED-WITH-NAMED-EXCEEDANCE" if fired else "EVIDENCED-NO-EXCEEDANCE"

    per_geography = []
    for source, _ in resolved:
        mine = [row for row in rows if row[0] == source.tag]
        per_geography.append((source, max(mine, key=lambda row: row[4]),
                              sum(1 for row in mine if row[4] > TRIPWIRE_PCT)))

    overall = max(rows, key=lambda row: row[4])
    max_fact = Fact.derived(f"{overall[4]:.4f} %/yr",
                            f"max |75+ net migration| / 75+ population over all "
                            f"{len(rows)} geography-periods")
    n_exceed = Fact.derived(len(exceedances),
                            "count of geography-periods strictly above the cited tripwire")

    latest_years = component_span[-_LATEST_WINDOW:]
    latest_top = max((row for row in rows if row[1] in latest_years), key=lambda row: row[4])
    latest_fact = Fact.derived(f"{latest_top[4]:.4f} %/yr",
                               f"max over the LATEST {_LATEST_WINDOW} periods ONLY "
                               f"({_period(latest_years[0])}–{_period(latest_years[-1])})")
    quiet = [row for row in rows if row[0] not in set(exceeding)]
    quiet_top = max(quiet, key=lambda row: row[4]) if quiet else None
    quiet_fact = Fact.derived(f"{quiet_top[4]:.4f} %/yr" if quiet_top else "not defined",
                              "max across every geography that never exceeds the tripwire")

    # The age-member counts and band ids that JUSTIFY resolution-by-name, read from the same
    # live dimensions the resolver walks. Printed as literals they were the one figure in this
    # note tied to nothing the run computed — correct on the measured edition, silently stale
    # on the next one, under prose asserting the very lookup they exist to motivate.
    band = BANDS_75_PLUS[0]
    n_ages_components = Fact.derived(
        len(_dimension(metas, COMPONENTS_CMA_PID, _POS_AGE_COMPONENTS)["member"]),
        f"count of age members {table_number(COMPONENTS_CMA_PID)} publishes at dimension "
        f"position {_POS_AGE_COMPONENTS}")
    n_ages_population = Fact.derived(
        len(_dimension(metas, POPULATION_CMA_PID, _POS_AGE_POPULATION)["member"]),
        f"count of age members {table_number(POPULATION_CMA_PID)} publishes at dimension "
        f"position {_POS_AGE_POPULATION}")
    band_id_components = Fact.derived(
        _member(metas, COMPONENTS_CMA_PID, _POS_AGE_COMPONENTS, band)["memberId"],
        f"live memberId of {band!r} in {table_number(COMPONENTS_CMA_PID)}")
    band_id_population = Fact.derived(
        _member(metas, POPULATION_CMA_PID, _POS_AGE_POPULATION, band)["memberId"],
        f"live memberId of {band!r} in {table_number(POPULATION_CMA_PID)}")

    covered = Fact.derived(len(resolved), "modeled geographies resolved to a live cube member")
    uncovered = Fact.derived(len(NOT_COVERED),
                             "modeled geographies published by NEITHER cube")
    threshold = Fact.cited(f"{TRIPWIRE_PCT:.3f} %/yr",
                           "spec §5 r3-F2 MATERIALITY TRIPWIRE (steering ruling J, 2026-08-07)")
    resolution = Fact.cited(
        "THE OMISSION STANDS for Tranche 1",
        "spec §5 r3-F2 STEERING RULING K (operator-ruled at the tripwire escalation, "
        "2026-08-07)")
    titles = [Fact.cited(metas[pid]["cubeTitleEn"], f"{table_number(pid)} live cube metadata")
              for pid in PIDS]

    lines = [
        "",
        "## Decision block",
        "",
        f"- `DECISION-VERDICT: {verdict}`",
        f"- `DECISION-SPAN: {span_fact}, {n_periods} periods (the FULL published span)`",
        f"- `DECISION-COVERAGE: {covered} of {len(Geography)} modeled geographies MEASURED, "
        f"{uncovered} NOT-COVERED ({', '.join(sorted(NOT_COVERED))})`",
        f"- `DECISION-IDENTITY: EXACT — max |difference| {identity_fact} person`",
        f"- `DECISION-MAX-RATE: {max_fact} at {overall[0]} {_period(overall[1])}`",
        f"- `DECISION-TRIPWIRE: {'FIRED' if fired else 'NOT FIRED'} — {n_exceed} "
        f"geography-period(s) above {threshold}"
        + (f", in {len(exceeding)} of {covered.text} measured geographies "
           f"({', '.join(exceeding)})`" if fired else "`"),
        f"- `DECISION-WINDOW-CONTRAST: latest-{_LATEST_WINDOW}-period max {latest_fact} vs "
        f"full-span max {max_fact.text} — the FULL SPAN rules`",
        f"- `DECISION-RESOLUTION: {resolution}`",
        "",
        "## 1. What the omission is",
        "",
        "The 75+ owner roll-forward is CLOSED after band entry: post-entry net migration at",
        "ages 75+ is OMITTED. That is a STATED ASSUMPTION with a sensitivity remark in",
        "outputs — not a modeled mechanism. Spec §5 r3-F2 attaches a MATERIALITY TRIPWIRE to",
        f"it: a measured 75+ net-migration rate above {threshold} in any modeled geography",
        "escalates the altitude call back to the operator. The spec's stated rationale for",
        "that level: 75+ all-cause exit hazards run ≥10%/yr, so a 1%/yr cap keeps the",
        "omission's relative distortion near or under 10%.",
        "",
        "## 2. The measured 75+ net-migration rate",
        "",
        "### 2a. Sources (titles quoted verbatim from live cube metadata)",
        "",
        "| table | productId | title | role in this measurement |",
        "|---|---|---|---|",
    ]
    roles = {
        COMPONENTS_CMA_PID: "components numerator, CMA axis",
        COMPONENTS_ER_PID: "components numerator, economic-region axis",
        POPULATION_CMA_PID: "July-1 population denominator, CMA axis",
        POPULATION_ER_PID: "July-1 population denominator, economic-region axis",
    }
    for pid, title in zip(PIDS, titles):
        lines.append(f"| [{table_number(pid)}]({table_url(pid)}) | `{pid}` | {title} | "
                     f"{roles[pid]} |")
    lines += [
        "",
        f"Release stamp carried by the components cubes' metadata: "
        f"`{metas[COMPONENTS_CMA_PID].get('releaseTime')}`. MEASURED on this run's own "
        f"metadata: {table_number(COMPONENTS_CMA_PID)} publishes {n_ages_components} age "
        f"members and {table_number(POPULATION_CMA_PID)} publishes {n_ages_population} age "
        f"members, and `{band}` resolves to member {band_id_components} in the first against "
        f"{band_id_population} in the second. Member ids are therefore resolved BY NAME on "
        f"every run: `_member` raises rather than falling back to a remembered id.",
        "",
        "### 2b. What the rate is",
        "",
        "```",
        "net_migration(g, t) = Σ over {" + ", ".join(BANDS_75_PLUS) + "} of",
        "    Immigrants − Net emigration + Net interprovincial migration",
        "               + Net intraprovincial migration + Net non-permanent residents",
        "rate(g, t)          = |net_migration(g, t)| / P75plus(g, t)",
        "P75plus(g, t)       = July-1 START-of-period 75+ population, same geography,",
        "                      summed over the same four bands",
        "```",
        "",
        "`Net emigration` enters WHOLE. `Emigrants`, `Returning emigrants` and `Net temporary",
        "emigration` are its CHILDREN in the cube's own component hierarchy — adding them",
        "beside it double-counts, and `Net temporary emigration` is unpublished from 2016/17",
        "onward, so a build-from-the-parts form would also silently lose the last nine",
        "periods.",
        "",
        "### 2c. The floor guards that had to pass first",
        "",
        f"- **Span** — each of the {n_series} requested series covers ITS OWN cube's full",
        "  declared span, contiguously; a span is a per-cube quantity, so it is recorded per",
        "  cube:",
        f"  {span_breakdown}.",
        "  Every components period's FOLLOWING July 1 is present in the population span —",
        "  `_guard_identity` refuses without it. This is ruling K's window rule as code.",
        f"- **Published** — no null datapoint outside `{RESIDUAL_COMPONENT}`, which carries",
        f"  {nulls_fact} of them and enters the identity alone. A null coerced to zero would",
        "  read as a measured zero, and an all-null response as a clean no-exceedance.",
        "- **Identity** — the All-ages demographic accounting identity closes EXACTLY:",
        "  `P(t+1) − P(t) = Births − Deaths + Immigrants − Net emigration + Net",
        "  interprovincial + Net intraprovincial + Net non-permanent residents + Residual",
        f"  deviation`. Max |difference| **{identity_fact} person** over",
        f"  {identity['checked']} geography-periods. This is what a mis-resolved geography, a",
        "  mis-paired cube, an off-by-one period join or a flipped component sign fails —",
        "  none of which a single-series check can see.",
        "- **Coverage** — every modeled geography resolves to a live member whose",
        "  classification code matches the declared one, or is recorded NOT-COVERED below.",
        "",
        "### 2d. Full published span, per modeled geography",
        "",
        f"Span **{span_fact}** ({n_periods} periods), {n_cells} geography-periods measured.",
        "`at-period` is the flow interval 1 July t → 1 July t+1.",
        "",
        "| modeled geography | role | source axis | live member (class code) | max \\|rate\\| "
        "%/yr | at-period | n > tripwire |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for source, top, count in per_geography:
        role = ("ranking proxy (`ra_proxy`)"
                if Geography(source.tag) in RA_PROXY_MEMBERS else "modeled member")
        lines.append(
            f"| {source.tag} | {role} | {source.axis} | {source.member_name} "
            f"(`{source.declared_class}`) | {top[4]:.4f} | {_period(top[1])} | {count} |")
    for tag in sorted(NOT_COVERED):
        lines.append(f"| {tag} | modeled member | **NOT-COVERED** | — | — | — | — |")
    lines.append("")
    for tag in sorted(NOT_COVERED):
        lines += [
            f"**{tag} is NOT-COVERED, never approximated:** {NOT_COVERED[tag]}. It is",
            "therefore NOT evaluated against the tripwire, and is recorded as unevaluated —",
            "an unevaluated geography is not a passing one.",
            "",
        ]
    lines += ["### 2e. The named exceedances", ""]
    if exceedances:
        lines += [
            f"{n_exceed} geography-period(s) exceed the tripwire, all in "
            f"{', '.join(exceeding)}:",
            "",
            "| geography | period | 75+ net migration | 75+ population (1 July, start) | "
            "rate %/yr |",
            "|---|---|---:|---:|---:|",
        ]
        for tag, year, net, population, rate in exceedances:
            lines.append(f"| {tag} | {_period(year)} | {net:+,.0f} | {population:,.0f} | "
                         f"**{rate:.4f}** |")
        # `quiet_top` is None when EVERY measured geography exceeds. Dereferencing it there
        # raised a TypeError that `main()` would have recorded as a probe failure — a code
        # fault wearing an outage's clothes, on the one branch a real escalation would take.
        lines += ["", (
            f"Every geography that never exceeds the tripwire peaks at **{quiet_fact}** "
            f"({quiet_top[0]} {_period(quiet_top[1])})." if quiet_top else
            f"NO measured geography stays under the tripwire, so a quiet-geography maximum is "
            f"{quiet_fact}.")]
    else:
        lines.append(f"None. The full-span maximum is {max_fact} ({overall[0]} "
                     f"{_period(overall[1])}), at or below the tripwire everywhere.")
    lines += [
        "",
        "## 3. Tripwire evaluation and the OPERATOR RESOLUTION (steering ruling K)",
        "",
        f"**Evaluated on the FULL published span** ({span_fact}, {n_periods} periods): the",
        f"tripwire **{'FIRED' if fired else 'did NOT fire'}** — {n_exceed} geography-period(s)",
        "above it.",
        "",
        f"The same measurement restricted to the latest {_LATEST_WINDOW} periods",
        f"({_period(latest_years[0])}–{_period(latest_years[-1])}) peaks at {latest_fact},",
        f"against a full-span peak of {max_fact.text}. That window is RECORDED and REFUSED as",
        "evidence, per ruling K: a window whose sole visible effect is to remove the",
        "exceedance is not evidence. The full span rules.",
        "",
        f"**OPERATOR RESOLUTION (2026-08-07):** {resolution}. The verdict form is",
        "`EVIDENCED-WITH-NAMED-EXCEEDANCE` — the omission is evidenced rather than",
        "unevidenced-pending, and the exceedance it carries is named rather than smoothed by a",
        "window. Every ranking row of an exceeding geography carries the",
        "`closed_cohort_exceedance` flag (added to the closed flags enum by the same",
        "amendment). That flag's WIRING is the rankings task's job; this note records the",
        "ruling, not its implementation. The omission remains a stated assumption with a",
        "sensitivity remark in outputs, not a modeled mechanism; adding a reconciled",
        "post-entry migration term without reintroducing ISQ-embedded mortality is a v1 item.",
        "",
        "## 4. What the ISQ compo source cannot establish (ruling J's refuted prescription)",
        "",
        "The spec's ORIGINAL evidence prescription pointed here. Ruling J refuted it for the",
        "committed vintage; the section is kept because that refutation is the record of why",
        "§2's source had to be found at all.",
        "",
    ] + compo_lines + [""]
    return lines


def _failure_sections(exc: BaseException, where: list) -> list:
    """The UNKNOWN branch. Records the exception TYPE and the boundary it happened at.

    Both are load-bearing for the gate in tests/test_probe_p7.py: the type decides
    fail-vs-skip (a `ProbeRefusal` must never skip), and the boundary decides which host the
    skip gate probes for liveness.
    """
    boundary = getattr(exc, "boundary", where[0])
    return [
        "",
        "## Decision block",
        "",
        "- `DECISION-VERDICT: UNKNOWN-PROBE-FAILED`",
        f"- `LIVE PROBE FAILED: {type(exc).__name__}: {exc}`",
        f"- `LIVE PROBE FAILED-AT: {boundary}`",
        "",
        "## 1. What the omission is",
        "",
        "The 75+ owner roll-forward is CLOSED after band entry: post-entry net migration at",
        "ages 75+ is OMITTED. This run could not measure the rate that omission discards, so",
        "it records NOTHING about its magnitude — an unmeasured omission is unevidenced, never",
        "small.",
        "",
    ]


def _assert_no_placeholder(text: str) -> None:
    if "[FILL" in text:
        raise ProbeRefusal("wds-data", "an unresolved [FILL placeholder survived into the "
                                       "note — every value must be COMPUTED, never invited")


def main() -> None:
    log = new_run()
    where = [_UNATTRIBUTED]
    try:
        sections = _sections(where)
    except Exception as exc:                      # noqa: BLE001 — every failure is recorded
        sections = _failure_sections(exc, where)
    header = provenance_header(log, written_by=_WRITTEN_BY, scope=_SCOPE, summary=_summary,
                               cited_label=_CITED_LABEL)
    text = "\n".join([_TITLE, ""] + header + sections) + "\n"
    _assert_no_placeholder(text)
    OUT.write_text(text, encoding="utf-8")
    print("\n".join(line for line in sections if line.startswith("- `")))


if __name__ == "__main__":
    main()
