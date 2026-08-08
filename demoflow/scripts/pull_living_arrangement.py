#!/usr/bin/env python3
"""Pull the committed living-arrangement EXTRACT from the StatCan WDS (cube 98100134).

    cd demoflow && uv run python scripts/pull_living_arrangement.py

This is the ACQUISITION leg of the PIT chain (live response -> filter predicate ->
committed extract -> derived rates). It writes `data/living_arrangement_98100134.json`
and NOTHING else: no rate is computed here, and no rate is ever hand-typed
(steering ruling B). `demoflow.loaders.living_arrangement.derive_living_arrangement`
is the only producer of rates; `scripts/gen_living_arrangement.py` runs it.

RE-PULLING IS A PINNED-VINTAGE CHANGE. The extract's sha256 lives in
`demoflow.loaders.pins.WORKBOOK_SHA256`, the derivation verifies it before reading a
single cell, and the artifact records it. So a re-pull is: run this, recompute the
digest, update the pin, regenerate the artifact, and re-run the suite — never just
this script. The `--out` flag exists so a re-pull can be inspected BEFORE it lands on
the committed path.

Four WDS traps this script is written against, the first three confirmed live (probe P3 §5b)
and the fourth measured 2026-08-08:

  1. **Bulk responses do NOT preserve request order.** Every value is keyed off the
     coordinate the RESPONSE carries; `zip(requests, responses)` mislabels cells (a
     province count lands on a CMA) and the output still looks entirely plausible.
  2. **A cell can return `status: FAILED` with an EMPTY `vectorDataPoint`.** A blind
     `[0]` raises mid-pull. Every response is checked for a data point and its status
     is recorded in the extract, so a suppressed cell is VISIBLE rather than absent.
  3. **Random rounding to base 5.** Components do not sum exactly to their totals.
     Nothing here corrects for it; the derivation reconciles with a tolerance.
  4. **A NEW wholly-Québec CMA is invisible downstream of this script.** The request set is
     built from `SOURCE_GEOGRAPHIES`, unrequested coordinates are refused and missing ones
     are refused, so every extract this script can write carries exactly
     `set(SOURCE_GEOGRAPHIES)` — the derivation's geography-set gate cannot fire on one. A
     CA promoted to a CMA (Drummondville's own 2021 history) would therefore stay un-netted
     inside the HORS_RMR residual with every rate still a plausible fraction. The live member
     list is the only place that fact exists, so `assert_netted_cma_universe` checks it here,
     before a single data call.

Member IDS are resolved from LIVE cube metadata by member NAME, never hardcoded: a
re-indexed cube must fail loudly rather than silently read the wrong geography. The
resolved ids and dimension positions are recorded in the extract, so a re-index is
visible in the diff even when the values happen to land in range.
"""
import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from demoflow.loaders.living_arrangement import (
    AGE_MEMBERS,
    ARRANGEMENT_MEMBERS,
    EXTRACT,
    GENDER_MEMBERS,
    PRODUCT_ID,
    SOURCE_GEOGRAPHIES,
    TOTAL_HOUSEHOLD_TYPE,
    assert_netted_cma_universe,
)
from demoflow.loaders.pins import DATA_DIR

WDS_META = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
WDS_DATA = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
TIMEOUT = 120
CHUNK = 40
CENSUS_YEAR = "2021"


def _post(url: str, payload: list) -> list:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())


def _member_id(dim: dict, name: str) -> int:
    for m in dim.get("member", []):
        if (m.get("memberNameEn") or "") == name:
            return int(m["memberId"])
    raise LookupError(
        f"member {name!r} absent from dimension {dim.get('dimensionNameEn')!r} — the cube has "
        "been re-indexed; this puller refuses to guess a member id")


def _dim(meta: dict, prefix: str) -> dict:
    for d in meta.get("dimension", []):
        if (d.get("dimensionNameEn") or "").lower().startswith(prefix.lower()):
            return d
    raise LookupError(f"no dimension named {prefix!r} in cube {meta.get('productId')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DATA_DIR / EXTRACT,
                    help="where to write the extract (default: the committed path)")
    args = ap.parse_args()

    meta = _post(WDS_META, [{"productId": PRODUCT_ID}])[0]["object"]
    dims = {
        "Geography": _dim(meta, "Geography"),
        "Gender": _dim(meta, "Gender"),
        "Age group": _dim(meta, "Age group"),
        "Census year": _dim(meta, "Census year"),
        "Arrangement": _dim(meta, "Census family status"),
        "Household type": _dim(meta, "Household type of person"),
    }
    # Trap 4 (see the module docstring): the request set is built FROM `SOURCE_GEOGRAPHIES`,
    # so no extract this script can write will ever disagree with it — a newly promoted
    # wholly-Québec CMA is simply never asked for, and lands un-netted inside HORS_RMR. The
    # live member list is the only place that fact exists. Checked before a single data call.
    assert_netted_cma_universe(
        (m.get("memberNameEn") or "" for m in dims["Geography"].get("member", [])),
        source=f"cube {PRODUCT_ID} @ {meta.get('releaseTime')}")

    width = max(10, max(int(d["dimensionPositionId"]) for d in meta["dimension"]))

    def coord(geo: str, gender: str, age: str, arrangement: str) -> str:
        slots = ["0"] * width
        for dim, member in ((dims["Geography"], geo), (dims["Gender"], gender),
                            (dims["Age group"], age), (dims["Census year"], CENSUS_YEAR),
                            (dims["Arrangement"], arrangement),
                            (dims["Household type"], TOTAL_HOUSEHOLD_TYPE)):
            slots[int(dim["dimensionPositionId"]) - 1] = str(_member_id(dim, member))
        return ".".join(slots)

    wanted = {
        coord(g, s, a, m): (g, s, a, m)
        for g in SOURCE_GEOGRAPHIES for s in GENDER_MEMBERS
        for a in AGE_MEMBERS for m in ARRANGEMENT_MEMBERS
    }
    if len(wanted) != len(SOURCE_GEOGRAPHIES) * len(GENDER_MEMBERS) * len(AGE_MEMBERS) * len(
            ARRANGEMENT_MEMBERS):
        raise SystemExit("two requested cells collided on one coordinate — dimension mapping is wrong")

    cells: dict[tuple, dict] = {}
    coords = list(wanted)
    for i in range(0, len(coords), CHUNK):
        batch = coords[i:i + CHUNK]
        for r in _post(WDS_DATA, [{"productId": PRODUCT_ID, "coordinate": c, "latestN": 1}
                                  for c in batch]):
            obj = r.get("object") or {}
            got = obj.get("coordinate")
            # Trap 1: key off the RESPONSE's coordinate, never the request order.
            if got not in wanted:
                raise SystemExit(f"WDS returned an unrequested coordinate {got!r}")
            points = obj.get("vectorDataPoint") or []
            # Trap 2: an empty vectorDataPoint is a real shape; refuse rather than index [0].
            if not points:
                raise SystemExit(
                    f"cell {wanted[got]} came back with status {r.get('status')!r} and an EMPTY "
                    "vectorDataPoint — the extract would carry a hole; refusing to write it")
            geo, gender, age, arrangement = wanted[got]
            cells[wanted[got]] = {
                "geography": geo, "gender": gender, "age_group": age,
                "arrangement": arrangement, "coordinate": got,
                "value": int(points[0]["value"]), "status": r.get("status"),
                "ref_per": points[0].get("refPer"), "status_code": points[0].get("statusCode"),
            }
    missing = [k for k in wanted.values() if k not in cells]
    if missing:
        raise SystemExit(f"{len(missing)} requested cells never came back, e.g. {missing[:3]}")

    payload = {
        "_pull": {
            "product_id": PRODUCT_ID,
            "statcan_table": "98-10-0134-01",
            "endpoint": WDS_DATA,
            "release_time": meta.get("releaseTime"),
            "census_year": CENSUS_YEAR,
            "pulled_at": date.today().isoformat(),
            "puller": "demoflow/scripts/pull_living_arrangement.py",
            "cube_title": meta.get("cubeTitleEn"),
            "citation": (
                "Statistics Canada. Table 98-10-0134-01, \"Census family status and household "
                "living arrangements, household type of person, age group and gender: Canada, "
                "provinces and territories, census metropolitan areas and census "
                "agglomerations\", 2021 Census, released 2022-07-13T08:30. "
                "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810013401"),
            "universe": (
                "Persons in PRIVATE households. MEASURED, not assumed (probe P3 §5): this cube's "
                "Québec all-ages/all-genders total is 8,308,475 against the published 2021 Census "
                "Québec population of 8,501,833 — the 2.27% gap is the collective / "
                "non-private-household population. Collectives are therefore already excluded "
                "from these denominators, which is what spec §5's partition requires."),
            "held_members": {"Census year": CENSUS_YEAR,
                             "Household type of person": TOTAL_HOUSEHOLD_TYPE},
            "dimension_positions": {
                (d.get("dimensionNameEn") or ""): int(d["dimensionPositionId"])
                for d in meta["dimension"]},
            "member_ids": {
                name: {m: _member_id(dim, m) for m in members}
                for name, dim, members in (
                    ("Geography", dims["Geography"], SOURCE_GEOGRAPHIES),
                    ("Gender", dims["Gender"], GENDER_MEMBERS),
                    ("Age group", dims["Age group"], AGE_MEMBERS),
                    ("Census year", dims["Census year"], (CENSUS_YEAR,)),
                    ("Arrangement", dims["Arrangement"], ARRANGEMENT_MEMBERS),
                    ("Household type", dims["Household type"], (TOTAL_HOUSEHOLD_TYPE,)),
                )},
        },
        # Sorted, flattened, projected — NOT the raw response objects. The pin must be stable
        # against response metadata that moves without the data moving (per-request ids,
        # server-side ordering); what the digest protects is the CELL VALUES and their
        # coordinates. Sorting makes the file byte-reproducible across pulls.
        "cells": [cells[k] for k in sorted(cells)],
    }
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}  ({len(payload['cells'])} cells)")
    print("NEXT: recompute the sha256, update pins.WORKBOOK_SHA256, then "
          "`uv run python scripts/gen_living_arrangement.py`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
