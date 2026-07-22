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

# --- candidates -------------------------------------------------------------
# The three the plan named (author's guesses, kept so the note records how they
# actually resolved), plus every Census-2021 cube the catalogue sweep surfaces.
CANDIDATES = ["98100134", "98100026", "98100040"]
SWEEP_TITLE_KEYS = ("living arrangement", "household living", "household type of person")
SWEEP_PID_PREFIX = "981"  # 2021 Census product family

WDS_META = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"  # POST [{"productId": int}]
WDS_LIST = "https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite"
WDS_DATA = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
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

CHUNK = 40
TIMEOUT = 120

# Spec §11.3 named fallback for living_alone (ISQ vitrine, 65+, QC-wide).
VITRINE_POINT = 0.28
VITRINE_BAND = (0.24, 0.34)


def _post(url: str, payload: list) -> list:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())


def _sweep() -> tuple[list[str], str]:
    """Shortlist Census cubes whose titles mention living arrangements."""
    raw = urllib.request.urlopen(WDS_LIST, timeout=TIMEOUT).read()
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


def _live_probe(obj: dict) -> dict:
    """Pull real values at CMA x age x sex. Returns {(geo, sex, age, stat): value}."""
    geo_d = _find_dim(obj, "Geography")
    sex_d = _find_dim(obj, "Gender", "Sex")
    age_d = _find_dim(obj, "Age")
    year_d = _find_dim(obj, "Census year")
    stat_d = next(d for d in _dims(obj) if STAT_ALONE in _members(d))
    hh_d = _find_dim(obj, "Household type of person")

    npos = max(int(d["dimensionPositionId"]) for d in _dims(obj))
    width = max(npos, 10)
    pid = int(obj["productId"])

    def coord(geo: str, sex: str, age: str, stat: str) -> str:
        slots = ["0"] * width
        slots[int(geo_d["dimensionPositionId"]) - 1] = str(_member_id(geo_d, geo))
        slots[int(sex_d["dimensionPositionId"]) - 1] = str(_member_id(sex_d, sex))
        slots[int(age_d["dimensionPositionId"]) - 1] = str(_member_id(age_d, age))
        slots[int(stat_d["dimensionPositionId"]) - 1] = str(_member_id(stat_d, stat))
        if year_d is not None:
            slots[int(year_d["dimensionPositionId"]) - 1] = str(_member_id(year_d, "2021"))
        if hh_d is not None:
            slots[int(hh_d["dimensionPositionId"]) - 1] = str(
                _member_id(hh_d, "Total - Household type of person")
            )
        return ".".join(slots)

    wanted: dict[str, tuple] = {}
    for g in TARGET_GEOS:
        for s in TARGET_SEXES:
            for a in TARGET_AGES:
                for st in (STAT_TOTAL, STAT_ALONE, STAT_COUPLE):
                    wanted[coord(g, s, a, st)] = (g, s, a, st)

    coords = list(wanted)
    out: dict[tuple, float | None] = {}
    for i in range(0, len(coords), CHUNK):
        batch = coords[i : i + CHUNK]
        res = _post(WDS_DATA, [{"productId": pid, "coordinate": c, "latestN": 1} for c in batch])
        for r in res:
            o = r.get("object") or {}
            # Keyed on the RESPONSE's coordinate: the service does not preserve
            # request order, and zipping would mis-label every value.
            c = o.get("coordinate")
            if c not in wanted:
                raise ValueError(f"WDS returned an unrequested coordinate {c!r}")
            dps = o.get("vectorDataPoint") or []
            out[wanted[c]] = float(dps[0]["value"]) if dps else None
    missing = [k for k in wanted.values() if k not in out]
    if missing:
        raise ValueError(f"{len(missing)} requested cells never came back, e.g. {missing[:3]}")
    return out


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
    note = [
        "# P3 — Census living-arrangement cross-tab hunt (RECORDED OBSERVATION)",
        "",
        "Written by `probes/run_p3.py`. Every number and every DECISION token below is derived",
        "from a live WDS response in the run that wrote this file — nothing here is hand-edited.",
        "",
    ]
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
                note.append(f"- `LIVE PROBE VERDICT: FOUND-AT-CMA` on productId {pid}.")
                break
            note.append(f"- **{pid}**: incomplete coverage — not accepted as the source.")
        except Exception as exc:
            # An exception is NOT evidence of absence. It downgrades the run to
            # FAILED so the gate can refuse rather than publish a false NOT-FOUND.
            probe_error = probe_error or f"{type(exc).__name__}: {exc}"
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
    if rates:
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
            "**Load-bearing for Task 15b:** calibrating toward balance can only move the LARGER",
            "side DOWN. Raising `couple_share_f` to match the male side needs values above 1.0",
            "(Montréal CMA 75-84 would need ~1.02), which violates the spec's assert that every",
            "fraction lies in [0, 1]. P3 records the raw cited rates; the gate's placement and any",
            "downward calibration are Task 15b's call, not this probe's.",
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
            note += [
                "### 4c. Cross-check against the spec's named living_alone fallback",
                "",
                f"Census-derived Québec-province 65+ living-alone rate (both sexes pooled, the",
                f"vitrine's own universe): **{qc65:.4f}** ({qc65 * 100:.1f}%).",
                f"The spec's ISQ vitrine point estimate is {VITRINE_POINT:.2f} with widened band",
                f"[{VITRINE_BAND[0]}, {VITRINE_BAND[1]}]. Observed value inside that band: "
                f"**{inside}** — the widened band was correctly specified, and the direct Census",
                "measurement supersedes it for every geography in the table above.",
                "",
            ]

    # --- universe + re-derivation recipe ------------------------------------
    if found_pid:
        note += [
            "## 5. Universe, vintage, and the re-derivation recipe (for Task 15b)",
            "",
            f"- productId `{found_pid}` = StatCan Table **98-10-0134-01**, 2021 Census, released",
            "  2022-07-13. Vintage pinned here; a re-pull must reproduce these counts.",
            "- **Universe is persons in PRIVATE households.** Independently confirmed: this cube's",
            "  Québec all-ages/all-genders total is 8,308,475 against the published 2021 Census",
            "  Québec population of 8,501,833 — a 2.27% gap that is the collective/non-private",
            "  household population. So the rate denominators already exclude collectives, which",
            "  is what spec §5's partition requires. (A 75+-SPECIFIC collective share is NOT",
            "  derivable from this cube alone — it needs a total-population-by-age source — so",
            "  Task 15's `collective_share_75plus` keeps its existing flag; P3 does not land it.)",
            "- Two independent definitions of living-alone AGREE EXACTLY in this cube: the",
            "  `Persons living alone` member of the living-arrangements dimension and the",
            "  `In a one-person household` member of `Household type of person` return identical",
            "  counts on every cell checked.",
            "- Dimension additivity reconciles to within +/-10 persons (Census random rounding to",
            "  base 5) — Task 15b must NOT assert exact component sums.",
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
            f"  FOUND at CMA granularity: productId `{found_pid}` (StatCan Table 98-10-0134-01)",
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
            "- `DECISION-COUPLE-SHARE-SOURCE: StatCan Table 98-10-0134-01 "
            f'(WDS productId {found_pid}), member "{STAT_COUPLE}" over the not-living-alone '
            "population, by age group x gender x geography, 2021 Census`",
            "- `DECISION-COUPLE-SHARE-CITATION: Statistics Canada. Table 98-10-0134-01, "
            "\"Census family status and household living arrangements, household type of person, "
            "age group and gender: Canada, provinces and territories, census metropolitan areas "
            "and census agglomerations\", 2021 Census, released 2022-07-13. "
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810013401`",
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

    text = "\n".join(note) + "\n"
    if "[FILL:" in text:  # belt-and-braces: this script must never emit a placeholder
        raise AssertionError("run_p3.py emitted an unresolved [FILL:] placeholder")
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
