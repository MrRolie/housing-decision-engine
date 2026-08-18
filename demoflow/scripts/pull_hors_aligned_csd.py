#!/usr/bin/env python3
"""Pull the committed CSD extract behind the OPERAND-ALIGNED HORS_RMR ownership curve.

    cd demoflow && uv run python scripts/pull_hors_aligned_csd.py

This is the ACQUISITION leg of the PIT chain (live response -> filter predicate -> committed
extract -> derived rates). It writes `data/hors_aligned_csd_98100232.json` and NOTHING else:
no rate is computed here and no rate is ever hand-typed (steering ruling B).
`demoflow.loaders.hors_aligned.derive_aligned_ownership` is the only producer of aligned
rates; `scripts/gen_hors_aligned.py` runs it.

RE-PULLING IS A PINNED-VINTAGE CHANGE. The extract's sha256 lives in
`demoflow.loaders.pins.WORKBOOK_SHA256`, the derivation verifies it before reading a single
cell, and the artifact records it. So a re-pull is: run this, recompute the digest, update the
pin, regenerate the artifact, re-run the suite — never just this script. `--out` exists so a
re-pull can be inspected BEFORE it lands on the committed path.

THE MEMBERSHIP IS RE-DERIVED HERE, LIVE, NOT COPIED. The territory is the Ottawa-Gatineau
CMA's Québec-side census subdivisions, and it is resolved the way probe P10 resolved it —
from 98-10-0003-01's own geography children of that CMA — rather than re-discovered or
transcribed:

  * CLOSURE. The CMA's children must sum EXACTLY to the CMA's own published population. A
    child list that did not close would make "the Québec side of this CMA" a slice of an
    unknown whole, so this is a refusal condition rather than a remark.
  * TWO INDEPENDENT CLASSIFICATIONS. Every child is classified Québec-side twice — by SGC
    prefix, and STRUCTURALLY, by asking whether the same SGC code resolves in 98-10-0232-01 to
    a geoLevel-5 member whose census division descends from that cube's Quebec member. A
    disagreement on any child refuses the pull.
  * THE PINNED SET. The resolved codes must equal `hors_aligned.QC_PART_CSDS`. A live
    derivation that silently returned 15 or 17 members would still produce a perfectly
    plausible curve; the pinned tuple is what a drift REDS against, and moving it is a
    deliberate, reviewed act.
  * DISJOINTNESS — the SCOPE FENCE, checked at the source. None of the resolved subdivisions
    may also be a constituent of any of the six wholly-Québec CMAs that the shipped residual
    already nets out. One that sat in both would be netted out TWICE and would move a CMA's own
    denotation, which is exactly the "any other geography moving is a FINDING" case.

FIVE WDS TRAPS this script is written against:

  1. **Bulk responses do NOT preserve request order.** Every value is keyed off the coordinate
     the RESPONSE carries; `zip(requests, responses)` mislabels cells (a province count lands
     on a subdivision) and the output still looks entirely plausible.
  2. **A withheld small count comes back with an EMPTY `vectorDataPoint`** — MEASURED, in the
     extract this script wrote: 259 published cells carry `status: SUCCESS` with a value, and
     all 13 withheld ones carry `status: FAILED` with a null `statusCode` and no data point.
     There is no SUCCESS-with-empty-points cell and no null-valued point. `_fetch` therefore
     keys off the ABSENCE of data points and never reads `status` — which is the only safe
     rule, because WDS supplies NO signal separating a withheld cell from a transient
     per-coordinate failure: both are an empty `vectorDataPoint` under `status: FAILED`. What
     bounds a re-pull is consequently not a status check but trap 3's declared SCOPE plus the
     address-level footprint gate (`test_p11_4c`), which reds if the withheld set moves.
     A withheld cell is recorded as `value: null` WITH its status, never elided — a dict that
     simply lacks the key cannot tell suppression from a hole.
  3. **Suppression has a SCOPE, and outside it an outage would read as a publication rule.**
     Only CSD BAND cells may be withheld. A withheld province cell, or a withheld CSD all-ages
     cell (the denominator of the unpublished-remainder bound), REFUSES the pull.
  4. **This cube has no census-year dimension** — its period axis is TIME, so `latestN: 1` is
     only safe behind a refPer guard. Every point is checked for refPer 2021.
  5. **Two adjacent cubes, two spellings of one member.** 98-10-0232-01's household-type total
     is `Total - Household type including family structure` — WITHOUT "census", unlike its CMA
     sibling. Resolving by the sibling's spelling returns a different, plausible number, so
     every member id is resolved from LIVE metadata by exact name and an absent name raises.
"""
import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from demoflow.loaders import census
from demoflow.loaders.hors_aligned import (
    AGE_MEMBERS,
    AGE_TOTAL_MEMBER,
    CSD_GEO_LEVEL,
    CMA_GEO_LEVEL,
    DIMENSION_POSITIONS,
    EXTRACT,
    HOUSEHOLD_TOTAL,
    MEMBERSHIP_PRODUCT_ID,
    MEMBERSHIP_TABLE,
    OG_CMA_MEMBER_NAME,
    PRODUCT_ID,
    PROVINCE_CODE,
    PROVINCE_GEO_LEVEL,
    QC_PART_CSDS,
    QC_SGC_PREFIX,
    SOURCE_GEOGRAPHIES,
    STATCAN_TABLE,
    STATISTIC,
    STRUCT_TOTAL,
    TENURES,
    assert_band_lattice,
)
from demoflow.loaders.pins import DATA_DIR

WDS_META = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
WDS_DATA = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
TIMEOUT = 180
CHUNK = 40
REF_YEAR = "2021"
POPULATION_MEMBER = "Population, 2021"
# 98-10-0003-01 names its geography dimension differently from every other cube in this tree.
MEMBERSHIP_GEO_DIMENSION = "Geographic name"
# The six netted CMAs, as 98-10-0003-01 spells them. `census._QC_CMAS` carries the
# 98-10-0231-01 spelling (`Drummondville (CMA), Que.`); the two are joined here explicitly
# rather than by string surgery, because a suffix-stripping rule that silently matched nothing
# would turn the disjointness gate into a check that cannot fail.
NETTED_CMA_NAMES = {
    "Drummondville (CMA), Que.": "Drummondville",
    "Montréal (CMA), Que.": "Montréal",
    "Québec (CMA), Que.": "Québec",
    "Saguenay (CMA), Que.": "Saguenay",
    "Sherbrooke (CMA), Que.": "Sherbrooke",
    "Trois-Rivières (CMA), Que.": "Trois-Rivières",
}


class PullRefusal(RuntimeError):
    """A live boundary contradicted a condition this extract must satisfy. Deliberately NOT a
    network-class error: a refusal must never launder itself into a retry or a skip."""


def _post(url: str, payload: list) -> list:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())


def _meta(product_id: int) -> dict:
    response = _post(WDS_META, [{"productId": product_id}])[0]
    if response.get("status") != "SUCCESS" or not response.get("object", {}).get("dimension"):
        raise PullRefusal(f"cube {product_id} metadata came back {response.get('status')!r} "
                          "with no dimension list")
    return response["object"]


def _dimension(meta: dict, name: str) -> dict:
    matches = [d for d in meta["dimension"] if (d.get("dimensionNameEn") or "").startswith(name)]
    if len(matches) != 1:
        raise PullRefusal(
            f"cube {meta.get('productId')}: {len(matches)} dimensions start with {name!r} "
            f"(have: {[d.get('dimensionNameEn') for d in meta['dimension']]})")
    return matches[0]


def _member_id(dim: dict, name: str) -> int:
    matches = [m for m in dim.get("member", []) if (m.get("memberNameEn") or "") == name]
    if len(matches) != 1:
        raise PullRefusal(
            f"member {name!r} resolves to {len(matches)} candidates in dimension "
            f"{dim.get('dimensionNameEn')!r} — the cube has been re-indexed; this puller "
            "refuses to guess a member id")
    return int(matches[0]["memberId"])


def _one_geo_member(dim: dict, name: str, geo_level: int) -> dict:
    matches = [m for m in dim.get("member", [])
               if (m.get("memberNameEn") or "") == name and m.get("geoLevel") == geo_level]
    if len(matches) != 1:
        raise PullRefusal(
            f"geography {name!r} at geoLevel {geo_level} resolves to {len(matches)} members — "
            "refusing to guess (a CD and the city inside it can share a name)")
    return matches[0]


def _coord(width: int, slots: dict[int, int]) -> str:
    out = ["0"] * width
    for position, member in slots.items():
        out[position - 1] = str(member)
    return ".".join(out)


def _fetch(product_id: int, coordinates: list[str]) -> dict[str, dict]:
    """{coordinate: {'value': int|None, 'status': str, 'ref_per': str}} — keyed off the
    RESPONSE's own coordinate (trap 1), with an empty data point kept as None (trap 2)."""
    wanted = set(coordinates)
    out: dict[str, dict] = {}
    for i in range(0, len(coordinates), CHUNK):
        batch = coordinates[i:i + CHUNK]
        for response in _post(WDS_DATA, [{"productId": product_id, "coordinate": c, "latestN": 1}
                                         for c in batch]):
            obj = response.get("object") or {}
            got = obj.get("coordinate")
            if got not in wanted:
                raise PullRefusal(f"WDS returned an unrequested coordinate {got!r}")
            points = obj.get("vectorDataPoint") or []
            if not points:
                out[got] = {"value": None, "status": response.get("status"), "ref_per": None,
                            "status_code": None}
                continue
            point = points[0]
            ref_per = str(point.get("refPer") or "")
            if not ref_per.startswith(REF_YEAR):
                raise PullRefusal(
                    f"cube {product_id} coordinate {got} came back at refPer {ref_per!r}, not "
                    f"{REF_YEAR} — this cube's period axis is TIME, so latestN=1 is only safe "
                    "behind this guard (trap 4)")
            out[got] = {"value": int(point["value"]), "status": response.get("status"),
                        "ref_per": ref_per, "status_code": point.get("statusCode")}
    missing = sorted(wanted - set(out))
    if missing:
        raise PullRefusal(f"{len(missing)} requested cells never came back, e.g. {missing[:3]}")
    return out


# --- the membership, re-derived live -------------------------------------------------------

def _resolve_membership(m3: dict, m232: dict) -> dict:
    """98-10-0003-01's Québec-side children of the Ottawa-Gatineau CMA, resolved and gated."""
    geo3 = _dimension(m3, MEMBERSHIP_GEO_DIMENSION)
    stat3 = _dimension(m3, "Population and dwelling counts")
    width3 = max(int(d["dimensionPositionId"]) for d in m3["dimension"])
    width3 = max(width3, 10)
    population_member = _member_id(stat3, POPULATION_MEMBER)

    cma = _one_geo_member(geo3, OG_CMA_MEMBER_NAME, CMA_GEO_LEVEL)
    children = [m for m in geo3["member"] if m.get("parentMemberId") == cma["memberId"]]
    if not children:
        raise PullRefusal(
            f"{MEMBERSHIP_TABLE} member {cma['memberId']} ({OG_CMA_MEMBER_NAME}) publishes no "
            "geography children — the membership cannot be resolved from this cube")

    coords = {int(m["memberId"]): _coord(width3, {1: int(m["memberId"]),
                                                  int(stat3["dimensionPositionId"]): population_member})
              for m in [cma] + children}
    fetched = _fetch(MEMBERSHIP_PRODUCT_ID, list(coords.values()))
    populations = {}
    for member_id, coordinate in coords.items():
        value = fetched[coordinate]["value"]
        if value is None:
            raise PullRefusal(
                f"{MEMBERSHIP_TABLE} withholds the 2021 population of member {member_id} — the "
                "closure that makes the Québec side a PARTITION cannot be computed")
        populations[member_id] = value

    cma_population = populations[int(cma["memberId"])]
    children_sum = sum(populations[int(m["memberId"])] for m in children)
    if children_sum != cma_population:
        raise PullRefusal(
            f"{MEMBERSHIP_TABLE}: the {len(children)} children of {OG_CMA_MEMBER_NAME} sum to "
            f"{children_sum:,} against the CMA's own {cma_population:,} — the child list is not "
            "a PARTITION, so 'the Québec side of this CMA' would be a slice of an unknown whole")

    # SECOND classification: structural ancestry inside 98-10-0232-01's own geography tree.
    geo232 = _dimension(m232, "Geography")
    by_id = {int(m["memberId"]): m for m in geo232["member"]}
    by_code_level = {}
    for m in geo232["member"]:
        by_code_level.setdefault((str(m.get("classificationCode")), m.get("geoLevel")), []).append(m)
    quebec = _one_geo_member(geo232, "Quebec", PROVINCE_GEO_LEVEL)
    if str(quebec.get("classificationCode")) != PROVINCE_CODE:
        raise PullRefusal(f"{STATCAN_TABLE}: the Quebec member carries classification code "
                          f"{quebec.get('classificationCode')!r}, expected {PROVINCE_CODE!r}")

    def descends_from_quebec(code: str) -> bool | None:
        """True/False by census-tree ancestry; None when the cube publishes no such CSD."""
        candidates = by_code_level.get((code, CSD_GEO_LEVEL), [])
        if len(candidates) != 1:
            return None
        node = candidates[0]
        for _hop in range(6):                       # CSD -> CD -> province, with slack
            parent = node.get("parentMemberId")
            if parent is None:
                return False
            node = by_id.get(int(parent))
            if node is None:
                return False
            if int(node["memberId"]) == int(quebec["memberId"]):
                return True
        return False

    quebec_side, ontario_side, disagreements = [], [], []
    for child in sorted(children, key=lambda m: str(m.get("classificationCode"))):
        code = str(child.get("classificationCode"))
        by_prefix = code.startswith(QC_SGC_PREFIX)
        structural = descends_from_quebec(code)
        if structural is None or structural != by_prefix:
            disagreements.append({"code": code, "name": child.get("memberNameEn"),
                                  "by_sgc_prefix": by_prefix, "by_census_ancestry": structural})
        (quebec_side if by_prefix else ontario_side).append(child)
    if disagreements:
        raise PullRefusal(
            f"the two independent Québec-side classifications disagree on "
            f"{len(disagreements)} of {len(children)} children: {disagreements} — a membership "
            "only one method supports is not resolved")

    resolved = tuple(str(m.get("classificationCode")) for m in quebec_side)
    if resolved != QC_PART_CSDS:
        raise PullRefusal(
            f"the live membership {resolved} is not the pinned "
            f"{QC_PART_CSDS} (probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP) — a "
            "changed territory is a DELIBERATE re-pin, never a silent re-pull")

    # DISJOINTNESS — the scope fence at the source.
    shared, checked = [], {}
    for census_label, cube_name in NETTED_CMA_NAMES.items():
        netted = _one_geo_member(geo3, cube_name, CMA_GEO_LEVEL)
        codes = {str(m.get("classificationCode")) for m in geo3["member"]
                 if m.get("parentMemberId") == netted["memberId"]}
        if not codes:
            raise PullRefusal(
                f"{MEMBERSHIP_TABLE}: netted CMA {cube_name!r} publishes no constituent "
                "subdivisions, so the disjointness check would be a check that cannot fail")
        checked[census_label] = len(codes)
        shared.extend(sorted(codes & set(resolved)))
    if shared:
        raise PullRefusal(
            f"Québec-part subdivisions {sorted(set(shared))} are ALSO constituents of a netted "
            "CMA — subtracting them would net that territory out twice and would move a "
            "geography this task must leave untouched")

    return {
        "source_product_id": MEMBERSHIP_PRODUCT_ID,
        "source_table": MEMBERSHIP_TABLE,
        "anchor": "probes/P10-hors-operand-alignment.md DECISION-MEMBERSHIP",
        "cma_member_id": int(cma["memberId"]),
        "cma_member_name": cma.get("memberNameEn"),
        "cma_classification_code": str(cma.get("classificationCode")),
        "cma_geo_level": cma.get("geoLevel"),
        "cma_population": cma_population,
        "children_count": len(children),
        "children_population_sum": children_sum,
        "quebec_side_codes": list(resolved),
        "quebec_side_population": sum(populations[int(m["memberId"])] for m in quebec_side),
        "ontario_side_count": len(ontario_side),
        "ontario_side_population": sum(populations[int(m["memberId"])] for m in ontario_side),
        "classification_methods": [
            f"SGC classification-code prefix {QC_SGC_PREFIX!r}",
            f"census-tree ancestry in {STATCAN_TABLE} (geoLevel-{CSD_GEO_LEVEL} member whose "
            f"census division descends from that cube's Quebec member)"],
        "classification_disagreements": disagreements,
        "netted_cmas_checked": sorted(NETTED_CMA_NAMES),
        "netted_cma_constituent_counts": checked,
        "shared_csd_codes": sorted(set(shared)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DATA_DIR / EXTRACT,
                    help="where to write the extract (default: the committed path)")
    args = ap.parse_args()

    assert_band_lattice()
    meta = _meta(PRODUCT_ID)
    membership_meta = _meta(MEMBERSHIP_PRODUCT_ID)
    membership = _resolve_membership(membership_meta, meta)

    positions = {(d.get("dimensionNameEn") or ""): int(d["dimensionPositionId"])
                 for d in meta["dimension"]}
    for name, expected in DIMENSION_POSITIONS.items():
        actual = next((p for label, p in positions.items() if label.startswith(name)), None)
        if actual != expected:
            raise PullRefusal(
                f"{STATCAN_TABLE}: dimension {name!r} sits at position {actual}, expected "
                f"{expected} — the coordinate builder would address a different dimension")

    geo = _dimension(meta, "Geography")
    held = {
        DIMENSION_POSITIONS["Structural type of dwelling"]:
            _member_id(_dimension(meta, "Structural type of dwelling"), STRUCT_TOTAL),
        DIMENSION_POSITIONS["Household type including census family structure"]:
            _member_id(_dimension(meta, "Household type"), HOUSEHOLD_TOTAL),
        DIMENSION_POSITIONS["Statistics"]:
            _member_id(_dimension(meta, "Statistics"), STATISTIC),
    }
    age_dim = _dimension(meta, "Age of primary household maintainer")
    tenure_dim = _dimension(meta, "Tenure")
    age_ids = {name: _member_id(age_dim, name) for name in AGE_MEMBERS}
    tenure_ids = {name: _member_id(tenure_dim, name) for name in TENURES}

    geo_members = {}
    for code in SOURCE_GEOGRAPHIES:
        level = PROVINCE_GEO_LEVEL if code == PROVINCE_CODE else CSD_GEO_LEVEL
        matches = [m for m in geo["member"]
                   if str(m.get("classificationCode")) == code and m.get("geoLevel") == level]
        if len(matches) != 1:
            raise PullRefusal(
                f"{STATCAN_TABLE}: SGC {code} at geoLevel {level} resolves to {len(matches)} "
                "members — refusing to guess (`Gatineau` names both a census division and the "
                "city inside it, so code AND level are both required)")
        geo_members[code] = matches[0]

    width = max(10, max(int(d["dimensionPositionId"]) for d in meta["dimension"]))
    wanted: dict[str, tuple[str, str, str]] = {}
    for code in SOURCE_GEOGRAPHIES:
        for age in AGE_MEMBERS:
            for tenure in TENURES:
                slots = dict(held)
                slots[DIMENSION_POSITIONS["Geography"]] = int(geo_members[code]["memberId"])
                slots[DIMENSION_POSITIONS["Age of primary household maintainer"]] = age_ids[age]
                slots[DIMENSION_POSITIONS["Tenure"]] = tenure_ids[tenure]
                coordinate = _coord(width, slots)
                if coordinate in wanted:
                    raise PullRefusal(
                        f"two requested cells collided on coordinate {coordinate} — the "
                        "dimension mapping is wrong")
                wanted[coordinate] = (code, age, tenure)
    expected_cells = len(SOURCE_GEOGRAPHIES) * len(AGE_MEMBERS) * len(TENURES)
    if len(wanted) != expected_cells:
        raise PullRefusal(f"built {len(wanted)} coordinates, expected {expected_cells}")

    fetched = _fetch(PRODUCT_ID, list(wanted))

    # Trap 3 — suppression SCOPE. Outside the declared scope a withheld cell would let an
    # outage read as a publication rule, and the bound has no denominator without the all-ages
    # row, so both refuse here rather than being absorbed downstream.
    for coordinate, (code, age, tenure) in wanted.items():
        if fetched[coordinate]["value"] is not None:
            continue
        if code == PROVINCE_CODE:
            raise PullRefusal(
                f"the province {age}/{tenure} cell is unpublished — suppression is a property "
                "of tiny geographies; refusing to write an extract whose province row has a hole")
        if age == AGE_TOTAL_MEMBER:
            raise PullRefusal(
                f"subdivision {code} withholds its all-ages {tenure} row, so the unpublished "
                "remainder that bounds its withheld bands cannot be computed — an interval with "
                "no upper end is not one")

    cells = [
        {"geography_code": code, "geography_name": geo_members[code].get("memberNameEn"),
         "geo_level": geo_members[code].get("geoLevel"), "age_member": age, "tenure": tenure,
         "coordinate": coordinate, "value": fetched[coordinate]["value"],
         "status": fetched[coordinate]["status"], "ref_per": fetched[coordinate]["ref_per"],
         "status_code": fetched[coordinate]["status_code"]}
        for coordinate, (code, age, tenure) in wanted.items()
    ]
    withheld = sum(1 for c in cells if c["value"] is None)

    payload = {
        "_pull": {
            "product_id": PRODUCT_ID,
            "statcan_table": STATCAN_TABLE,
            "endpoint": WDS_DATA,
            "release_time": meta.get("releaseTime"),
            "archive_status": meta.get("archiveStatusEn"),
            "census_year": REF_YEAR,
            "pulled_at": date.today().isoformat(),
            "puller": "demoflow/scripts/pull_hors_aligned_csd.py",
            "cube_title": meta.get("cubeTitleEn"),
            "citation": (
                f"Statistics Canada. Table {STATCAN_TABLE}, \"{meta.get('cubeTitleEn')}\", 2021 "
                f"Census, released {meta.get('releaseTime')}. "
                "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810023201"),
            "purpose": (
                "The operand-aligned HORS_RMR ownership curve (spec §6, the amendment-#12(B) "
                "reversal): these subdivisions are SUBTRACTED from the shipped residual that "
                f"{census.STATCAN_TABLE} produces, so that the rate's territory matches the "
                "territory of the ISQ hors-RMR flow it multiplies."),
            "universe": (
                "Private households, primary-household-maintainer denominated. Same universe as "
                f"{census.STATCAN_TABLE} at one finer geography grain: the two cubes' Québec "
                "province all-ages rows are asserted BIT-IDENTICAL by the derivation."),
            "held_members": {"Structural type of dwelling": STRUCT_TOTAL,
                             "Household type including census family structure": HOUSEHOLD_TOTAL,
                             "Statistics": STATISTIC},
            "dimension_positions": positions,
            "member_ids": {
                "Geography": {code: int(geo_members[code]["memberId"])
                              for code in SOURCE_GEOGRAPHIES},
                "Age of primary household maintainer": age_ids,
                "Tenure": tenure_ids,
                "held": {name: member for name, member in
                         zip(("Structural type of dwelling",
                              "Household type including census family structure", "Statistics"),
                             (held[DIMENSION_POSITIONS["Structural type of dwelling"]],
                              held[DIMENSION_POSITIONS[
                                  "Household type including census family structure"]],
                              held[DIMENSION_POSITIONS["Statistics"]]))},
            },
            "membership": membership,
            "suppression": {
                "withheld_cells": withheld,
                "scope": ("CSD BAND cells only. A withheld province cell or a withheld CSD "
                          "all-ages cell refuses this pull: the all-ages row is the denominator "
                          "of the unpublished-remainder bound, and accepting suppression "
                          "cube-wide would let an outage read as a publication rule."),
            },
        },
        # Sorted, flattened, projected — NOT the raw response objects. What the pin protects is
        # the CELL VALUES and their coordinates; per-request ids and server-side ordering move
        # without the data moving. Sorting makes the file byte-reproducible across pulls.
        "cells": sorted(cells, key=lambda c: (c["geography_code"], c["age_member"], c["tenure"])),
    }
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}  ({len(cells)} cells, {withheld} withheld)")
    print(f"  membership: {membership['children_count']} children closing on "
          f"{membership['cma_population']:,}; {len(membership['quebec_side_codes'])} Québec-side; "
          f"shared with netted CMAs: {membership['shared_csd_codes'] or 'none'}")
    print("NEXT: recompute the sha256, update pins.WORKBOOK_SHA256, then "
          "`uv run python scripts/gen_hors_aligned.py`")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PullRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(2)
