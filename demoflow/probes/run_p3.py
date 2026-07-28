"""P3 — hunt a Census living-arrangement cross-tab (living arrangements x age x
GENDER, CMA level) via the StatCan WDS, and RESOLVE the decision from what the
live service actually returns.

THE QUESTION, precisely: does a free StatCan cube publish, at CMA granularity,
both rates the cohort initialization needs — `living_alone` AND `couple_share`
— broken out by age AND by sex? Spec §5 needs SEX-SPECIFIC rates (codex
r3-F1/r4-F1: a pooled couple rate is not sex-conserving), and spec §11.3 gives
`couple_share` NO invented default: cross-tab, or a cited province-level value,
or initialization RAISES.

WHY THE SCRIPT RESOLVES ITS OWN DECISION: the note this writes IS the recorded
observation, and Task 15b consumes its numbers. A template with `[FILL:]` slots
for a human to complete is an invitation to fabricate — the operator ruling on
this task is that the committed note must carry a decision computed from live
responses, never a hand-edited one. So every DECISION token below is derived,
and the script writes `NOT-FOUND` just as readily as a hit.

HUNT PROCEDURE (three stages, each recorded):
  1. Catalogue sweep — GET getAllCubesListLite and shortlist every cube whose
     title mentions living arrangements / household type of person. This is
     what makes the answer a HUNT rather than a guess-and-check against three
     product IDs: a NOT-FOUND is only credible if the catalogue was searched.
     Non-fatal — on failure the static candidate list still runs.
  2. Metadata probe — getCubeMetadata on every candidate; the full dimension
     list is written verbatim, and a STRUCTURAL predicate (not a hardcoded
     product ID) decides which cubes qualify and records why the others do not.
  3. Live data probe — a qualifying cube's dimensions only prove the table is
     SHAPED right; they do not prove values survive at CMA x age x sex (small
     cells get suppressed). So the verdict token is written only after real,
     non-suppressed values come back for every required cell.

THREE TRAPS THIS CODE HANDLES (each bites Task 15b's loader too — see the note):
  * WDS bulk responses come back in a DIFFERENT ORDER than the request array.
    Observed live on this cube. `zip(requests, responses)` therefore silently
    mis-labels values — province numbers land on a CMA, 85+ on 65-74 — and the
    result looks plausible. Every value here is keyed on the `coordinate` the
    RESPONSE carries.
  * Some cells return `status: FAILED` with an EMPTY `vectorDataPoint` (e.g.
    women 85+ who are "Children in census families"). Blind `[0]` indexing
    raises IndexError mid-pull.
  * Census counts are randomly rounded to base 5, so component sums reconcile
    to the total only within a small tolerance. Exact-equality reconciliation
    would false-fail on correct data.

Member IDs are resolved BY NAME from the live metadata rather than hardcoded:
if StatCan ever re-indexes the cube, this refuses (KeyError-style guard) rather
than silently reading the wrong geography.

Run:  cd demoflow && uv run python probes/run_p3.py
"""

import json
import re
import urllib.request
from pathlib import Path

# Flat, NOT `probes._wds`: probes/ is deliberately not a package, so in script mode
# sys.path[0] IS probes/ and this resolves natively. See probes/_wds.py.
from _wds import (
    WDS_DATA,
    WDS_LIST,
    WDS_META,
    WDS_TIMEOUT,
    Fact,
    new_run,
    post as _post,
    provenance_header,
    table_number as _table_number,
    table_url as _table_url,
)

# --- candidates -------------------------------------------------------------
# The three the plan named (author's guesses, kept so the note records how they
# actually resolved), plus every Census-2021 cube the catalogue sweep surfaces.
CANDIDATES = ["98100134", "98100026", "98100040"]
SWEEP_TITLE_KEYS = ("living arrangement", "household living", "household type of person")
SWEEP_PID_PREFIX = "981"  # 2021 Census product family

OUT = Path(__file__).resolve().parent / "P3-living-arrangement.md"

# The 7 wholly-Québec geographies — the same set P2 pinned, so the two probes
# describe one geography universe. Ottawa-Gatineau is excluded (not wholly QC).
TARGET_GEOS = [
    "Quebec",
    "Montréal (CMA), Que.",
    "Québec (CMA), Que.",
    "Saguenay (CMA), Que.",
    "Sherbrooke (CMA), Que.",
    "Trois-Rivières (CMA), Que.",
    "Drummondville (CMA), Que.",
]
# 65-74 is pulled for context only: it is the band the ISQ vitrine's 65+
# living-alone figure covers, so it is the cross-check on the spec's fallback
# band. The cohort itself is 75+.
TARGET_AGES = ["65 to 74 years", "75 to 84 years", "85 years and over"]
TARGET_SEXES = ["Men+", "Women+"]
# Numerators/denominator, by living-arrangement member name.
STAT_TOTAL = "Total - Census family status and household living arrangements"
STAT_ALONE = "Persons living alone"
STAT_COUPLE = "Married spouses and common-law partners"
# The rest of the living-arrangements hierarchy, used by the additivity check.
STAT_IN_FAM = "Persons in census families"
STAT_LONE_PARENT = "Parents in one-parent families"
STAT_CHILDREN = "Children in census families"
STAT_NOT_IN_FAM = "Persons not in census families"
STAT_OTHER_REL = "Persons living with other relatives"
STAT_NON_REL = "Persons living with non-relatives only"
STAT_COMPONENTS = (
    STAT_IN_FAM,
    STAT_COUPLE,
    STAT_LONE_PARENT,
    STAT_CHILDREN,
    STAT_NOT_IN_FAM,
    STAT_OTHER_REL,
    STAT_NON_REL,
    STAT_ALONE,
)
TOTAL_HH = "Total - Household type of person"
HH_ONE_PERSON = "In a one-person household"
# Second cube, for the published total population the main cube cannot contain.
POP_CUBE = 98100001  # Population and dwelling counts: Canada, provinces and territories

# NOT the same constant as run_p4.py's `META_CHUNK = 30`: different endpoint,
# different batch semantics. Never merge them.
CHUNK = 40

# Spec §11.3 named fallback for living_alone (ISQ vitrine, 65+, QC-wide).
VITRINE_POINT = 0.28
VITRINE_BAND = (0.24, 0.34)


# --- this note's provenance prose (the shared header skeleton lives in _wds) ---
# The filename this note must attribute itself to. DERIVED from __file__, never
# typed: `written_by` is the one header field a copy-pasted call block carries
# forward silently — a p6 cloned from p5 would publish "Written by run_p5.py"
# over p6's own computed body, which is exactly the untied claim this registry
# exists to stop. Module-level so the golden-equivalence test can read it.
_WRITTEN_BY = Path(__file__).name
_SCOPE = ("Every table in §2-§4 is generated row by row from the live WDS responses of the run "
          "that wrote this file.")
_CITED_LABEL = "Externally cited figures:"


def _summary(*, total: int, derived: int, cited: int) -> str:
    """The §5 provenance sentence, sized to what this run actually registered.

    States exactly what it counts: registered Fact objects. Saying "the narrative
    figures in §5" would be a category substitution — §5 also carries product ids,
    member counts and labels that never enter the registry, so that count would be
    false as written.
    """
    return (
        f"§5 additionally tags its measured figures with provenance. This run registered "
        f"{total} such figures: {derived} DERIVED (computed from live responses "
        f"in this same run, each naming its source) and {cited} CITED (external to "
        f"this run, printed with the citation inline). Untagged numerals in the surrounding "
        f"prose are product ids, dimension labels and counts of what was checked."
    )


def _sweep() -> tuple[list[str], str]:
    """Shortlist Census cubes whose titles mention living arrangements."""
    raw = urllib.request.urlopen(WDS_LIST, timeout=WDS_TIMEOUT).read()
    cubes = json.loads(raw)
    hits = []
    for c in cubes:
        pid = str(c.get("productId") or "")
        title = (c.get("cubeTitleEn") or "").lower()
        if pid.startswith(SWEEP_PID_PREFIX) and any(k in title for k in SWEEP_TITLE_KEYS):
            hits.append(pid)
    return sorted(set(hits)), f"{len(cubes)} cubes in catalogue"


def _dims(obj: dict) -> list[dict]:
    return obj.get("dimension", []) or []


def _find_dim(obj: dict, *name_starts: str) -> dict | None:
    for d in _dims(obj):
        n = (d.get("dimensionNameEn") or "").lower()
        if any(n.startswith(s.lower()) for s in name_starts):
            return d
    return None


def _members(dim: dict | None) -> list[str]:
    return [m.get("memberNameEn") or "" for m in (dim or {}).get("member", [])]


def _qualify(obj: dict) -> tuple[bool, list[str]]:
    """STRUCTURAL test — is this cube shaped like the input the spec needs?

    Deliberately not `pid == 98100134`: the note must show WHY a cube qualifies
    or fails, so that a NOT-FOUND is auditable and a future re-run against a
    changed catalogue re-derives the answer instead of trusting this one.
    """
    reasons = []
    geo = _find_dim(obj, "Geography")
    has_cma = any("(CMA)" in m for m in _members(geo))
    reasons.append(f"geography dimension with CMA members: {has_cma}")

    sex = _find_dim(obj, "Gender", "Sex")
    has_sex = len([m for m in _members(sex) if not m.lower().startswith("total")]) >= 2
    reasons.append(
        f"sex/gender dimension with >=2 non-total members: {has_sex} "
        f"({_members(sex) or 'dimension absent'})"
    )

    age = _find_dim(obj, "Age")
    age_members = _members(age)
    has_75 = any("75" in m for m in age_members)
    has_85 = any("85" in m for m in age_members)
    reasons.append(f"age dimension resolving 75+ (a '75' band and an '85' band): {has_75 and has_85}")

    alone_dim = couple_dim = None
    for d in _dims(obj):
        ms = [m.lower() for m in _members(d)]
        if any(STAT_ALONE.lower() == m for m in ms):
            alone_dim = d
        if any(STAT_COUPLE.lower() == m for m in ms):
            couple_dim = d
    has_alone = alone_dim is not None
    has_couple = couple_dim is not None
    reasons.append(f"a member {STAT_ALONE!r} (living_alone numerator): {has_alone}")
    reasons.append(f"a member {STAT_COUPLE!r} (couple_share numerator): {has_couple}")

    ok = bool(has_cma and has_sex and has_75 and has_85 and has_alone and has_couple)
    return ok, reasons


def _member_id(dim: dict, name: str) -> int:
    for m in dim.get("member", []):
        if (m.get("memberNameEn") or "") == name:
            return int(m["memberId"])
    raise LookupError(
        f"member {name!r} absent from dimension "
        f"{dim.get('dimensionNameEn')!r} — the cube has been re-indexed; "
        "this probe refuses to guess a member id"
    )


def _coord_builder(obj: dict):
    """Return `(coord_fn, productId)`; `coord_fn` maps member NAMES to a coordinate.

    Names, never hardcoded ids: if StatCan re-indexes the cube, `_member_id`
    refuses rather than silently reading the wrong geography.
    """
    geo_d = _find_dim(obj, "Geography")
    sex_d = _find_dim(obj, "Gender", "Sex")
    age_d = _find_dim(obj, "Age")
    year_d = _find_dim(obj, "Census year")
    stat_d = next(d for d in _dims(obj) if STAT_ALONE in _members(d))
    hh_d = _find_dim(obj, "Household type of person")

    npos = max(int(d["dimensionPositionId"]) for d in _dims(obj))
    width = max(npos, 10)
    pid = int(obj["productId"])

    def coord(geo: str, sex: str, age: str, stat: str, hh: str = TOTAL_HH) -> str:
        slots = ["0"] * width
        slots[int(geo_d["dimensionPositionId"]) - 1] = str(_member_id(geo_d, geo))
        slots[int(sex_d["dimensionPositionId"]) - 1] = str(_member_id(sex_d, sex))
        slots[int(age_d["dimensionPositionId"]) - 1] = str(_member_id(age_d, age))
        slots[int(stat_d["dimensionPositionId"]) - 1] = str(_member_id(stat_d, stat))
        if year_d is not None:
            slots[int(year_d["dimensionPositionId"]) - 1] = str(_member_id(year_d, "2021"))
        if hh_d is not None:
            slots[int(hh_d["dimensionPositionId"]) - 1] = str(_member_id(hh_d, hh))
        return ".".join(slots)

    return coord, pid


def _fetch(pid: int, wanted: dict) -> dict:
    """Pull `{coordinate: key}` and return `{key: value|None}`.

    Keyed on the coordinate the RESPONSE carries: the service does not preserve
    request order, and zipping request to response would mis-label every value.
    """
    coords = list(wanted)
    out: dict = {}
    for i in range(0, len(coords), CHUNK):
        batch = coords[i : i + CHUNK]
        res = _post(WDS_DATA, [{"productId": pid, "coordinate": c, "latestN": 1} for c in batch])
        for r in res:
            o = r.get("object") or {}
            c = o.get("coordinate")
            if c not in wanted:
                raise ValueError(f"WDS returned an unrequested coordinate {c!r}")
            dps = o.get("vectorDataPoint") or []
            out[wanted[c]] = float(dps[0]["value"]) if dps else None
    missing = [k for k in wanted.values() if k not in out]
    if missing:
        raise ValueError(f"{len(missing)} requested cells never came back, e.g. {missing[:3]}")
    return out


def _live_probe(obj: dict) -> dict:
    """Pull real values at CMA x age x sex. Returns {(geo, sex, age, stat): value}."""
    coord, pid = _coord_builder(obj)
    wanted = {
        coord(g, s, a, st): (g, s, a, st)
        for g in TARGET_GEOS
        for s in TARGET_SEXES
        for a in TARGET_AGES
        for st in (STAT_TOTAL, STAT_ALONE, STAT_COUPLE)
    }
    return _fetch(pid, wanted)


def _definition_agreement(obj: dict) -> tuple[int, int, list]:
    """COMPUTE whether the cube's two living-alone definitions agree.

    `Persons living alone` (living-arrangements dimension) vs `In a one-person
    household` (household-type dimension). Returns (cells compared, mismatches,
    examples) — the ACTUAL result, so a future run where they diverge says so.
    """
    coord, pid = _coord_builder(obj)
    keys = [(g, s, a) for g in TARGET_GEOS for s in TARGET_SEXES for a in TARGET_AGES]
    alone = _fetch(pid, {coord(g, s, a, STAT_ALONE): (g, s, a) for g, s, a in keys})
    one_person = _fetch(
        pid, {coord(g, s, a, STAT_TOTAL, hh=HH_ONE_PERSON): (g, s, a) for g, s, a in keys}
    )
    mismatches = [
        (k, alone[k], one_person[k]) for k in keys if (alone[k] or 0) != (one_person[k] or 0)
    ]
    return len(keys), len(mismatches), mismatches[:3]


def _additivity(obj: dict) -> tuple[int, float, int]:
    """COMPUTE how closely the living-arrangements hierarchy reconciles.

    Three identities per cell: families + non-families == total;
    couples + lone-parents + children == families; other-relatives +
    non-relatives + living-alone == non-families. Returns (identities checked,
    worst absolute deviation in persons, cells with no published value).
    Census random-rounds to base 5, so the expectation is a small non-zero
    residual — the point is to MEASURE it, not to assume it.
    """
    coord, pid = _coord_builder(obj)
    keys = [(g, s, a) for g in TARGET_GEOS for s in TARGET_SEXES for a in TARGET_AGES]
    members = [STAT_TOTAL, *STAT_COMPONENTS]
    vals = _fetch(
        pid,
        {coord(g, s, a, m): (g, s, a, m) for g, s, a in keys for m in members},
    )
    suppressed = sum(1 for v in vals.values() if v is None)
    v = lambda k, m: vals[(*k, m)] or 0.0  # noqa: E731 - suppressed cell == no persons
    worst = 0.0
    checked = 0
    for k in keys:
        identities = [
            (v(k, STAT_IN_FAM) + v(k, STAT_NOT_IN_FAM), v(k, STAT_TOTAL)),
            (v(k, STAT_COUPLE) + v(k, STAT_LONE_PARENT) + v(k, STAT_CHILDREN), v(k, STAT_IN_FAM)),
            (
                v(k, STAT_OTHER_REL) + v(k, STAT_NON_REL) + v(k, STAT_ALONE),
                v(k, STAT_NOT_IN_FAM),
            ),
        ]
        for lhs, rhs in identities:
            worst = max(worst, abs(lhs - rhs))
            checked += 1
    return checked, worst, suppressed


def _published_qc_population() -> tuple[float, str]:
    """Fetch Québec's published 2021 Census population from a NAMED second cube.

    The main cube's universe is private-household persons; establishing that
    requires a total-population figure it does not contain. Fetching it live
    keeps the comparison DERIVED rather than a hand-typed literal.
    """
    payload = _post(WDS_META, [{"productId": POP_CUBE}])
    obj = payload[0]["object"]
    geo_d, stat_d = obj["dimension"][0], obj["dimension"][1]
    coord = f"{_member_id(geo_d, 'Quebec')}.{_member_id(stat_d, 'Population, 2021')}"
    coord += ".0" * 8
    got = _fetch(POP_CUBE, {coord: "qc"})
    return got["qc"], obj.get("cubeTitleEn", "")


def _rates(vals: dict) -> dict:
    """living_alone = alone/pop; couple_share = coupled / (pop - alone).

    couple_share is CONDITIONAL on not living alone — that is the spec's
    decomposition (§5): coupled_s = pop_s x (1 - living_alone_s) x couple_share_s.
    The two Census members are disjoint by construction ("Persons living alone"
    sits under "Persons not in census families"; "Married spouses and common-law
    partners" under "Persons in census families"), so the conditional share is
    well-defined and <= 1.
    """
    rates = {}
    for g in TARGET_GEOS:
        for s in TARGET_SEXES:
            for a in TARGET_AGES:
                pop = vals[(g, s, a, STAT_TOTAL)]
                alone = vals[(g, s, a, STAT_ALONE)]
                coupled = vals[(g, s, a, STAT_COUPLE)]
                if not pop:
                    continue
                la = alone / pop if alone is not None else None
                not_alone = pop - (alone or 0)
                cs = (coupled / not_alone) if (coupled is not None and not_alone) else None
                rates[(g, s, a)] = {
                    "pop": pop,
                    "alone": alone,
                    "coupled": coupled,
                    "living_alone": la,
                    "couple_share": cs,
                }
    return rates


def main() -> None:  # noqa: C901 - a probe: linear narrative beats decomposition
    # Per-run registry, bound here rather than at module scope: `_wds` is one cached
    # module shared by every probe, so a module-global list would make a second run in
    # one process report "12 figures" while §5 still showed 6.
    facts = new_run()
    # The provenance paragraph is GENERATED from the facts the body actually
    # carries (see `_wds.provenance_header`), so it is spliced in after the body
    # is built rather than asserted up front.
    title = ["# P3 — Census living-arrangement cross-tab hunt (RECORDED OBSERVATION)", ""]
    note: list[str] = []
    candidates = list(CANDIDATES)

    # --- stage 1: catalogue sweep -------------------------------------------
    note += ["## 1. Catalogue sweep (so a NOT-FOUND would be credible)", ""]
    try:
        hits, size = _sweep()
        note.append(f"- `getAllCubesListLite` -> {size}.")
        note.append(
            f"- Census-2021 (`{SWEEP_PID_PREFIX}*`) cubes whose title mentions "
            f"{list(SWEEP_TITLE_KEYS)}: `{hits}`"
        )
        for pid in hits:
            if pid not in candidates:
                candidates.append(pid)
    except Exception as exc:
        note.append(f"- sweep FAILED ({type(exc).__name__}: {exc}) — only the plan's static "
                    "candidate list was probed; a NOT-FOUND from this run would be WEAK evidence.")
    note.append("")
    note.append(f"Candidates probed (plan's three first, then sweep hits): `{candidates}`")
    note.append("")

    # --- stage 2: metadata probe --------------------------------------------
    # `meta_ok` guards the difference between "the catalogue has no such cube"
    # and "the service did not answer". Collapsing the two would let an outage
    # publish a NOT-FOUND — the cheap all-clear, inverted: a false NOT-FOUND
    # sends Task 15b to a fallback the real data does not need.
    note += ["## 2. Metadata probe — dimension lists verbatim", ""]
    qualified: list[tuple[str, dict]] = []
    meta_ok = 0
    probe_error: str | None = None
    for pid in candidates:
        try:
            payload = _post(WDS_META, [{"productId": int(pid)}])
            obj = payload[0].get("object", {}) if isinstance(payload, list) and payload else {}
            if not obj:
                note.append(f"- **{pid}**: no `object` in response — {json.dumps(payload)[:200]}")
                continue
            meta_ok += 1
            dims = [d.get("dimensionNameEn") for d in _dims(obj)]
            ok, reasons = _qualify(obj)
            note.append(f"### {pid} — {'QUALIFIES' if ok else 'does not qualify'}")
            note.append(f"- title: {obj.get('cubeTitleEn')}")
            note.append(f"- release: {obj.get('releaseTime')} | status: {obj.get('archiveStatusEn')}")
            note.append(f"- dimensions = {dims}")
            for r in reasons:
                note.append(f"  - {r}")
            note.append("")
            if ok:
                qualified.append((pid, obj))
                note.append(f"  Living-arrangement members of {pid}:")
                stat_d = next(d for d in _dims(obj) if STAT_ALONE in _members(d))
                for m in _members(stat_d):
                    note.append(f"    - {m}")
                note.append("")
        except Exception as exc:
            probe_error = probe_error or f"{type(exc).__name__}: {exc}"
            note.append(f"- **{pid}**: probe error {type(exc).__name__}: {exc}")
            note.append("")

    # --- stage 3: live data probe -------------------------------------------
    note += [
        "## 3. Live data probe — values at CMA x age x SEX",
        "",
        "A cube being SHAPED right does not prove values survive at this granularity; small",
        "cells get suppressed. The verdict below is written only after real values return for",
        "every required cell across all 7 wholly-Québec geographies.",
        "",
    ]
    outcome = "NOT-FOUND"  # one of FOUND / NOT-FOUND / FAILED
    found_pid = None
    found_obj: dict = {}
    rates: dict = {}
    for pid, obj in qualified:
        try:
            vals = _live_probe(obj)
            rates = _rates(vals)
            expected = len(TARGET_GEOS) * len(TARGET_SEXES) * len(TARGET_AGES)
            complete = [
                k for k, v in rates.items()
                if v["living_alone"] is not None and v["couple_share"] is not None
            ]
            note.append(
                f"- **{pid}**: pulled {len(vals)} coordinates; "
                f"{len(complete)}/{expected} (geo x sex x age) cells resolve BOTH rates."
            )
            if len(complete) == expected:
                outcome = "FOUND"
                found_pid = pid
                found_obj = obj
                note.append(f"- `LIVE PROBE VERDICT: FOUND-AT-CMA` on productId {pid}.")
                break
            # Rejected cube: DROP its rates. Leaving them behind publishes a §4
            # table of measured numbers under `productId None` beside a recorded
            # DECISION of NO — a note that simultaneously reports rates and says
            # none was found.
            rates = {}
            note.append(f"- **{pid}**: incomplete coverage — not accepted as the source.")
        except Exception as exc:
            # An exception is NOT evidence of absence. It downgrades the run to
            # FAILED so the gate can refuse rather than publish a false NOT-FOUND.
            # Records the exception that ACTUALLY aborted the pull, overwriting any
            # earlier metadata-stage error: first-error-wins would let a transient
            # URLError on an earlier candidate stand in for a code fault here, and
            # the gate excuses network-class names when the source is unreachable.
            rates = {}
            probe_error = f"{type(exc).__name__}: {exc}"
            outcome = "FAILED"
            note.append(f"- **{pid}**: `LIVE PROBE FAILED: {probe_error}`")
            break
    if not qualified:
        note.append("- no candidate qualified structurally; no live pull attempted.")
    if meta_ok == 0:
        # Nothing answered at all — the catalogue was never actually consulted.
        outcome = "FAILED"
        probe_error = probe_error or "NoResponse: no candidate returned cube metadata"
        note.append(
            "- NO candidate returned metadata, so the catalogue was never actually read: "
            "this run cannot distinguish absence from an outage."
        )
    if outcome == "FAILED":
        note.append(f"- `LIVE PROBE FAILED: {probe_error}`")
    elif outcome == "NOT-FOUND":
        note.append("- `LIVE PROBE VERDICT: NOT-FOUND-AT-CMA`")
    note.append("")

    # --- derived rates -------------------------------------------------------
    # Gated on found_pid, never on `rates` alone: §4 may only exist when a cube
    # was actually ACCEPTED as the source.
    if found_pid and rates:
        note += [
            f"## 4. Derived per-sex rates — Census 2021, productId {found_pid}",
            "",
            "`living_alone = alone / pop`; `couple_share = coupled / (pop - alone)` — conditional",
            "on NOT living alone, matching spec §5 "
            "`coupled_s = pop_s x (1 - living_alone_s) x couple_share_s`.",
            "Universe is persons in PRIVATE households (see §5 below), which is the denominator",
            "the spec's partition requires.",
            "",
            "| geography | sex | age | pop | living alone | coupled | living_alone | couple_share |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for g in TARGET_GEOS:
            for s in TARGET_SEXES:
                for a in TARGET_AGES:
                    r = rates.get((g, s, a))
                    if not r:
                        continue
                    note.append(
                        f"| {g} | {s} | {a} | {r['pop']:,.0f} | {r['alone']:,.0f} | "
                        f"{r['coupled']:,.0f} | {r['living_alone']:.4f} | {r['couple_share']:.4f} |"
                    )
        note.append("")

        # couple-balance observation (recorded, NOT resolved here)
        note += [
            "### 4b. Couple-balance observation — a finding for Task 15b, recorded RAW",
            "",
            "Spec §5 carries a data-sanity gate `|coupled_m - coupled_f| / max <= 0.25`",
            "(breach => CalibrationError). Evaluated on these RAW Census counts:",
            "",
            "| geography | age | coupled_m | coupled_f | \\|diff\\|/max | vs 0.25 gate |",
            "|---|---|---:|---:|---:|---|",
        ]
        breaches = 0
        for g in TARGET_GEOS:
            for a in TARGET_AGES:
                m = rates.get((g, "Men+", a))
                f = rates.get((g, "Women+", a))
                if not m or not f:
                    continue
                cm, cf = m["coupled"], f["coupled"]
                mx = max(cm, cf)
                ratio = abs(cm - cf) / mx if mx else 0.0
                bad = ratio > 0.25
                breaches += bool(bad)
                note.append(
                    f"| {g} | {a} | {cm:,.0f} | {cf:,.0f} | {ratio:.4f} | "
                    f"{'BREACH' if bad else 'ok'} |"
                )
        note += [
            "",
            f"{breaches} of the rows above breach the gate. This is NOT a data defect and is NOT",
            "resolved here: at 75+ the male coupled count genuinely exceeds the female one",
            "(older men partner with younger women; women outlive men), so the surplus is real",
            "population structure — exactly what spec §5's `Couple(a) = min(coupled_m, coupled_f)`",
            "matching plus `max - min -> Other` was written to absorb.",
            "",
            "**Open for Task 15b — stated, deliberately NOT resolved here.** The rows above are",
            "the raw cited Census values; P3 neither calibrates them nor rules on where the gate",
            "belongs. The tension 15b inherits: the gate is a TOLERANCE (<= 0.25), not an",
            "equality, so it is satisfiable from either side within [0, 1] — but every such",
            "adjustment moves a rate away from the cited Census figure, which sits against",
            "§11.3's cited-or-raise rule. Choosing among calibrating, re-placing the gate, and",
            "accepting the breach is 15b's call, not this probe's.",
            "",
        ]

        # vitrine cross-check
        num = den = 0.0
        for s in TARGET_SEXES:
            for a in TARGET_AGES:
                r = rates.get(("Quebec", s, a))
                if r:
                    num += r["alone"]
                    den += r["pop"]
        if den:
            qc65 = num / den
            inside = VITRINE_BAND[0] <= qc65 <= VITRINE_BAND[1]
            # The verdict must follow the boolean. Printed unconditionally it once
            # emitted "inside that band: **False** — the widened band was correctly
            # specified", which is the note contradicting its own measurement.
            band_verdict = (
                "the widened band CONTAINS the direct Census measurement, so the spec's "
                "fallback was correctly specified"
                if inside
                else "the direct Census measurement falls OUTSIDE the widened band — the "
                "spec's fallback band does NOT cover the observed value, which is a finding "
                "for Task 15b wherever that fallback is still applied"
            )
            note += [
                "### 4c. Cross-check against the spec's named living_alone fallback",
                "",
                "Census-derived Québec-province 65+ living-alone rate (both sexes pooled, the",
                f"vitrine's own universe): **{qc65:.4f}** ({qc65 * 100:.1f}%).",
                f"The spec's ISQ vitrine point estimate is {VITRINE_POINT:.2f} with widened band",
                f"[{VITRINE_BAND[0]}, {VITRINE_BAND[1]}]. Observed value inside that band: "
                f"**{inside}** — {band_verdict}.",
                "The direct Census measurement supersedes the fallback for every geography in",
                "the table above either way.",
                "",
            ]

    # --- universe + re-derivation recipe ------------------------------------
    if found_pid:
        # Each figure below is COMPUTED here and tagged with its provenance; none
        # is a literal typed into the prose. If a future run finds the cube
        # revised, these lines report the new result rather than the old claim.
        coord, _pid = _coord_builder(found_obj)
        priv = _fetch(
            int(found_obj["productId"]),
            {coord("Quebec", "Total - Gender", "Total - All ages", STAT_TOTAL): "qc_private"},
        )["qc_private"]
        published, pop_title = _published_qc_population()
        gap = (published - priv) / published * 100.0
        cells, mismatches, examples = _definition_agreement(found_obj)
        identities, worst, suppressed = _additivity(found_obj)
        release = found_obj.get("releaseTime")

        f_priv = Fact.derived(f"{priv:,.0f}", f"productId {found_pid}, Québec x all ages x all genders")
        f_pub = Fact.derived(
            f"{published:,.0f}", f"StatCan Table {_table_number(POP_CUBE)} ({pop_title})"
        )
        f_gap = Fact.derived(f"{gap:.2f}%", "computed from the two figures above")
        f_agree = Fact.derived(
            f"{cells - mismatches}/{cells}", "cells where the two living-alone definitions agree"
        )
        f_add = Fact.derived(
            f"{worst:,.0f} persons", f"worst deviation across {identities} hierarchy identities"
        )
        f_rel = Fact.derived(release, f"`releaseTime` from the productId {found_pid} metadata")
        f_ident = Fact.derived(identities, "hierarchy identities evaluated")
        f_supp = Fact.derived(suppressed, "component cells with no published value, counted as zero")

        agree_verdict = (
            "AGREE on every cell compared"
            if mismatches == 0
            else f"DISAGREE on {mismatches} cell(s), e.g. {examples}"
        )
        note += [
            "## 5. Universe, vintage, and the re-derivation recipe (for Task 15b)",
            "",
            f"- productId `{found_pid}` = StatCan Table **{_table_number(found_pid)}**, 2021",
            f"  Census, released {f_rel}. Vintage pinned here; a re-pull must reproduce these counts.",
            "- **Universe is persons in PRIVATE households.** Measured, not assumed: this cube's",
            f"  Québec all-ages/all-genders total is {f_priv} against the published 2021 Census",
            f"  Québec population of {f_pub} — a {f_gap} gap that is the collective /",
            "  non-private-household population. So the rate denominators already exclude",
            "  collectives, which is what spec §5's partition requires. (A 75+-SPECIFIC collective",
            "  share is NOT derivable from this cube alone — it needs total population BY AGE — so",
            "  Task 15's `collective_share_75plus` keeps its existing flag; P3 does not land it.)",
            "- The cube's two independent definitions of living-alone "
            f"**{agree_verdict}**: `{STAT_ALONE}`",
            f"  (living-arrangements dimension) vs `{HH_ONE_PERSON}` (household-type dimension)",
            f"  — compared cell by cell, {f_agree} geography x sex x age cells match.",
            f"- Living-arrangements hierarchy additivity: worst deviation {f_add} across the",
            f"  {f_ident} identities checked ({f_supp} component cells carry no published",
            "  value and were counted as zero). Census random-rounds to base 5, so a small non-zero",
            "  residual is EXPECTED — Task 15b must reconcile with a tolerance, never exact sums.",
            "- Recipe: POST `getDataFromCubePidCoordAndLatestNPeriods` with a coordinate whose",
            "  slots are the dimension-position-ordered member ids; hold `Census year` = 2021 and",
            "  `Household type of person` = its Total member; vary geography, gender, age group,",
            "  and the living-arrangements member across the three rows named in §4.",
            "",
            "### 5b. Traps confirmed live (they bite the Task 15b loader too)",
            "",
            "1. **Response order != request order.** Observed on this cube: keying results by",
            "   `zip(requests, responses)` mislabels values (a province count lands on a CMA)",
            "   and the output still looks plausible. Key on the coordinate the RESPONSE carries.",
            "2. **`status: FAILED` cells with an empty `vectorDataPoint`** exist (e.g. women 85+",
            "   under `Children in census families`). Blind `[0]` indexing raises mid-pull.",
            "3. **Random rounding to base 5** — reconcile with a tolerance, never exact equality.",
            "",
        ]

    # --- DECISION ------------------------------------------------------------
    found_yes = outcome == "FOUND"
    decision_token = {"FOUND": "YES", "NOT-FOUND": "NO"}.get(outcome, "UNRESOLVED-PROBE-FAILED")
    note += [
        "## DECISION — SEX-SPECIFIC rates required "
        "(living_alone AND couple_share by age x sex; r3-F1/r4-F1)",
        "",
        f"- `DECISION-FOUND-AT-CMA: {decision_token}`",
    ]
    if outcome == "FAILED":
        note += [
            "  The probe could not reach the WDS, so this run answers NOTHING about whether the",
            "  cross-tab exists. It is deliberately NOT recorded as a NOT-FOUND: an outage must",
            "  not send Task 15b to a fallback. Re-run `probes/run_p3.py` against a live service.",
            "",
            "- `DECISION-COUPLE-SHARE-SOURCE: UNRESOLVED-PROBE-FAILED`",
            "- `DECISION-COUPLE-SHARE-CITATION: UNRESOLVED-PROBE-FAILED`",
        ]
    elif found_yes:
        note += [
            f"  FOUND at CMA granularity: productId `{found_pid}` "
            f"(StatCan Table {_table_number(found_pid)})",
            "  publishes living arrangements x age group x GENDER x geography, and the live pull",
            "  returned non-suppressed values for all 7 wholly-Québec geographies at 75-84 and 85+",
            "  for both Men+ and Women+. Both required rates come from this ONE table.",
            "",
            "- PER-INPUT fallbacks (codex r4-F6 — the living-alone fallback CANNOT supply "
            "couple_share):",
            f"  * `living_alone` -> spec's named fallback is the ISQ vitrine "
            f"{VITRINE_POINT:.2f} (65+, QC), widened band "
            f"[{VITRINE_BAND[0]}, {VITRINE_BAND[1]}] PER-SEX, flagged `borrowed_prior`.",
            "    **NOT NEEDED** — §4 supplies directly measured per-sex, per-age, per-CMA rates,",
            "    so the `borrowed_prior` flag does not attach to `living_alone` for any geography",
            "    in that table. The constant stays defined for geographies outside it.",
            "  * `couple_share` -> pinned at probe time WITH CITATION, below. The province-level",
            "    fallback is likewise not needed: the cross-tab resolves at CMA granularity.",
            "",
            f"- `DECISION-COUPLE-SHARE-SOURCE: StatCan Table {_table_number(found_pid)} "
            f'(WDS productId {found_pid}), member "{STAT_COUPLE}" over the not-living-alone '
            "population, by age group x gender x geography, 2021 Census`",
            # Every element of this citation is derived: title and release date from the
            # metadata fetched in §2, table number and URL from found_pid. No literal here
            # can name a different cube than the one the run actually accepted.
            f"- `DECISION-COUPLE-SHARE-CITATION: Statistics Canada. Table {_table_number(found_pid)}, "
            f'"{found_obj.get("cubeTitleEn")}", 2021 Census, '
            f"released {found_obj.get('releaseTime')}. "
            f"{_table_url(found_pid)}`",
        ]
        for g in ("Quebec", "Montréal (CMA), Que.", "Québec (CMA), Que."):
            for a in ("75 to 84 years", "85 years and over"):
                m = rates.get((g, "Men+", a))
                f = rates.get((g, "Women+", a))
                if m and f:
                    note.append(
                        f"  * {g} / {a}: couple_share M={m['couple_share']:.4f} "
                        f"F={f['couple_share']:.4f} | living_alone M={m['living_alone']:.4f} "
                        f"F={f['living_alone']:.4f}"
                    )
    else:
        note += [
            "  NOT FOUND at CMA granularity. The catalogue sweep and every candidate above are",
            "  the full record of what was tried.",
            "",
            "- PER-INPUT fallbacks (codex r4-F6 — the living-alone fallback CANNOT supply "
            "couple_share):",
            f"  * `living_alone` -> vitrine {VITRINE_POINT:.2f} (65+, QC), widened band "
            f"[{VITRINE_BAND[0]}, {VITRINE_BAND[1]}] PER-SEX, `borrowed_prior`",
            "    (constant `living_alone_vitrine`; the living-arrangement loader applies it per sex).",
            "- `DECISION-COUPLE-SHARE-SOURCE: NOT-FOUND`",
            "- `DECISION-COUPLE-SHARE-CITATION: NOT-FOUND`",
            "  No citable province-level per-sex couple_share was pinned by this probe, and no",
            "  number is invented in its place.",
        ]
    note += [
        "",
        "- Standing rule either way: if NEITHER the cross-tab NOR a citable couple_share exists,",
        "  initialization RAISES (LoaderError). `couple_share` has NO invented default "
        "(spec §11.3).",
        "",
    ]

    header = provenance_header(facts, written_by=_WRITTEN_BY, scope=_SCOPE,
                               summary=_summary, cited_label=_CITED_LABEL)
    text = "\n".join(title + header + note) + "\n"
    if "[FILL:" in text:  # belt-and-braces: this script must never emit a placeholder
        raise AssertionError("run_p3.py emitted an unresolved [FILL:] placeholder")
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
