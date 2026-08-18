"""Regenerate `p10_boundary_capture.json` from the live boundaries `probes/run_p10.py` reads.

NOT a test (pytest collects `test_*.py` only) and not part of any suite — a build tool kept
beside its output so the fixture is DERIVED DATA with a recorded recipe rather than an opaque
blob nobody can re-cut, the same treatment `make_p9_fixture.py` gives P9's cache. The gates in
`tests/test_probe_p10.py` read the output; nothing reads this file at test time.

WHAT THE FIXTURE IS: one recording of every boundary response the probe consumed on a live run
— eight `getCubeMetadata` objects, every `getDataFromCubePidCoordAndLatestNPeriods` value keyed
by (productId, coordinate), and the two pinned ISQ workbooks' rows as the reader consumes them.
The probe then runs end to end against it with no network, and `test_p10_note_regenerates_byte_
identically_from_the_fixture` compares the result with the committed note byte for byte.

WHAT IS TRIMMED, and why that is a sizing decision rather than a claim. Two of these cubes
publish 5,468 geography members and a third 1,159; committing four such lists would be
megabytes. So each geography dimension keeps only the members the run can reach — those named
in a coordinate, their ancestors, the Ottawa-Gatineau CMA's children, every member at CMA-PART
grain (geoLevel 505), and every member whose name carries `Gatineau` — beside the dimension's
TRUE member count. The test pads the difference with inert filler, so the note's printed member
counts and the geoLevel-505 scan reproduce at their real sizes while the bytes stay reviewable.
The trim is over members the probe never resolves; every member it does resolve is here
verbatim. Nothing about WHICH cells are withheld is trimmed: a cell absent from `cells` is a
cell StatCan withheld, and the offline `_data` returns it exactly as the live endpoint does —
`status: FAILED` with an empty `vectorDataPoint`.

The ISQ rows are stored SPARSELY (`{column index: value}`) at the sheet's true width, because
the compo sheet is 38 columns wide and 34 of them are empty in every row the reader touches.
The header block is kept whole, since `_flow_column` resolves the operand's column from the
stacked header text and a trimmed header would let a wrong column pass.

Run:  cd demoflow && uv run python tests/fixtures/make_p10_fixture.py
"""
import collections
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "probes" / "run_p10.py"
DEST = Path(__file__).resolve().parent / "p10_boundary_capture.json"

# The scenario labels and the columns the ISQ reader touches. Kept here rather than imported so
# a probe-side change that widens what the reader reads FAILS LOUDLY at regen time (a missing
# column reaches the note as a refusal) instead of being silently carried by a shared constant.
SCENARIOS = ("Référence (A2026)", "Faible (D2026)", "Fort (E2026)")
POP_BOOK, FLOW_BOOK = "pop-as-rmr-base.xlsx", "compo-rmr-base.xlsx"
KEEP_COLUMNS = (0, 1, 2, 3, 4, 5, 6, 16)
MEMBERSHIP_PID = 98100003
CMA_PART_GEO_LEVEL = 505


def _load_probe():
    sys.path.insert(0, str(ROOT / "probes"))
    spec = importlib.util.spec_from_file_location("p10_fixture_capture", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _record(mod) -> tuple:
    meta_raw, cells, isq_raw = {}, {}, {}
    live_meta, live_data, live_isq = mod._meta, mod._data, mod._isq_rows

    def meta(pids):
        out = live_meta(pids)
        for item in out:
            meta_raw[int(item["object"]["productId"])] = item["object"]
        return out

    def data(requests):
        out = live_data(requests)
        for item in out:
            obj = item.get("object") or {}
            points = obj.get("vectorDataPoint") or []
            if item.get("status") == "SUCCESS" and points:
                cells[f"{int(obj['productId'])}|{obj['coordinate']}"] = points[0]["value"]
        return out

    def isq(name):
        rows = live_isq(name)
        isq_raw[name] = rows
        return rows

    mod._meta, mod._data, mod._isq_rows = meta, data, isq
    mod.new_run()
    mod._sections(["-"])           # raises if any floor guard fires — no fixture from a refusal
    return meta_raw, cells, isq_raw


def _trim_cubes(meta_raw: dict, cells: dict) -> dict:
    referenced = collections.defaultdict(set)
    for key in cells:
        pid, coordinate = key.split("|")
        referenced[int(pid)].add(int(coordinate.split(".")[0]))
    cubes = {}
    for pid, obj in meta_raw.items():
        dimensions = []
        for dim in sorted(obj["dimension"], key=lambda d: d["dimensionPositionId"]):
            members = dim.get("member") or []
            if dim["dimensionPositionId"] == 1 and len(members) > 60:
                by_id = {m["memberId"]: m for m in members}
                keep = set(referenced[pid])
                for member in members:
                    name = member.get("memberNameEn") or ""
                    if (member.get("geoLevel") == CMA_PART_GEO_LEVEL or "Gatineau" in name
                            or name in ("Quebec", "Ontario")):
                        keep.add(member["memberId"])
                for member in members:                  # the CMA's own constituent children
                    if pid == MEMBERSHIP_PID and member.get("parentMemberId") in keep:
                        keep.add(member["memberId"])
                for _ in range(4):                      # and every ancestor of a kept member
                    for member_id in list(keep):
                        parent = by_id.get(member_id, {}).get("parentMemberId")
                        if parent in by_id:
                            keep.add(parent)
                kept = [m for m in members if m["memberId"] in keep]
            else:
                kept = members
            dimensions.append({
                "pos": dim["dimensionPositionId"], "name": dim["dimensionNameEn"],
                "total": len(members),
                "members": [{"id": m["memberId"], "name": m["memberNameEn"],
                             "geoLevel": m.get("geoLevel"), "parent": m.get("parentMemberId"),
                             "code": m.get("classificationCode")} for m in kept]})
        cubes[str(pid)] = {"title": obj["cubeTitleEn"], "release": obj["releaseTime"],
                           "archive": obj["archiveStatusEn"], "dimensions": dimensions}
    return cubes


def _trim_isq(isq_raw: dict) -> dict:
    out = {}
    for name, rows in isq_raw.items():
        header = next(i for i, row in enumerate(rows)
                      if row and str(row[0]).strip() == "Scénario")
        width = max(len(row) for row in rows)

        def sparse(row, columns=None):
            cells = list(row) + [None] * (width - len(row))
            return {str(i): (c if isinstance(c, (int, float, str)) else str(c))
                    for i, c in enumerate(cells)
                    if c is not None and (columns is None or i in columns)}

        body = []
        for row in rows[header + 1:]:
            if not row or row[0] not in SCENARIOS:
                continue
            if name == POP_BOOK and not (row[3] == 2021 and row[5] == 3):
                continue
            if name == FLOW_BOOK and row[0] != SCENARIOS[0]:
                continue
            body.append(sparse(row, KEEP_COLUMNS))
        out[name] = {"width": width, "header": header,
                     "head": [sparse(row) for row in rows[:header + 4]], "body": body}
    return out


def main() -> None:
    mod = _load_probe()
    meta_raw, cells, isq_raw = _record(mod)
    payload = {"cubes": _trim_cubes(meta_raw, cells), "cells": cells,
               "isq": _trim_isq(isq_raw)}
    DEST.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=0),
                    encoding="utf-8")
    print(f"{DEST.name}: {len(cells)} cells, {len(payload['cubes'])} cubes, "
          f"{DEST.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
