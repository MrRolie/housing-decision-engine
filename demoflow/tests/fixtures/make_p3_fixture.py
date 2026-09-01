"""Regenerate `p3_wds_capture.json` from the live boundaries `probes/run_p3.py` reads.

NOT a test (pytest collects `test_*.py` only) and not part of any suite — a build tool kept
beside its output so the fixture is DERIVED DATA with a recorded recipe rather than an opaque
blob nobody can re-cut, the same treatment `make_p10_fixture.py` and `make_p9_fixture.py` give
their outputs. `tests/test_probe_p3.py` reads the output; nothing reads this file at test time.

WHAT THE FIXTURE IS: one recording of every boundary response the probe consumed on a live run
— the `getCubeMetadata` object of every candidate cube it probed (including the second cube it
reads the published Québec population from), and every
`getDataFromCubePidCoordAndLatestNPeriods` value keyed by `productId|coordinate`. The probe then
runs end to end against it with no network, and
`test_p3_note_regenerates_byte_identically_from_the_fixture` compares the result with the
committed note byte for byte.

THE ONE FIELD THAT IS NOT A LIVE CAPTURE, stated plainly because everything else is.
`sweep.catalogue_size` is PINNED to the count the run that wrote the committed note observed
(8212). The StatCan catalogue GROWS: measured live 2026-08-21 it answers 8226, and it will be a
different number again next quarter. A live capture of that count therefore cannot reproduce a
point-in-time record, and the note's §1 line is exactly such a record. Nothing else here is
pinned: on the same 2026-08-21 capture the pristine probe reproduced the committed note byte for
byte at EVERY OTHER LINE — all 42 rate rows, both derived population totals, the definition-
agreement and additivity readings and every DECISION token — so §5's "a re-pull must reproduce
these counts" was verified, not assumed. The seven sweep HITS are live-captured, not pinned.

WHAT IS TRIMMED, and why that is a sizing decision rather than a claim. The candidate cubes
publish geography and age dimensions with thousands of members; the raw capture is 5.8 MB. So a
dimension keeps EVERY member the probe resolves by name or prints, and drops the rest:

  * a dimension that is PRINTED VERBATIM keeps all of its members — the gender/sex dimension
    (`_qualify` writes the member list into the note) and any dimension carrying
    `Persons living alone` (the living-arrangement members of the qualifying cube are listed
    row by row);
  * every member whose name the probe ever looks up (`_member_id`) is kept verbatim;
  * one member carrying `(CMA)`, one carrying `75` and one carrying `85` are kept per cube, so
    `_qualify`'s three structural predicates read what they read live. Dropping a member can
    only turn one of those `any(...)` tests from True to False, never the reverse, so a trim
    that was too aggressive cannot manufacture a qualification — it reds the byte-equality gate.

Unlike `make_p10_fixture.py` this does NOT pad the trimmed lists back to their live size: P3's
note prints no member COUNT anywhere, so there is nothing for filler to reproduce and filler
names could only perturb the three predicates above. The trim is over members the probe never
resolves and never prints.

Nothing about WHICH cells are withheld is trimmed: a cell absent from `cells` is a cell StatCan
withheld, and the offline `_post` returns it exactly as the live endpoint does — `status: FAILED`
with an EMPTY `vectorDataPoint`.

Run:  cd demoflow && uv run python tests/fixtures/make_p3_fixture.py
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "probes" / "run_p3.py"
NOTE = ROOT / "probes" / "P3-living-arrangement.md"
DEST = Path(__file__).resolve().parent / "p3_wds_capture.json"

# The catalogue size the committed note records. See the docstring: this is the ONE pinned
# field, because the live count moves and the note is a point-in-time observation.
COMMITTED_CATALOGUE_SIZE = 8212


def _load_probe():
    sys.path.insert(0, str(ROOT / "probes"))
    spec = importlib.util.spec_from_file_location("p3_fixture_capture", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _record(mod, out_path: Path) -> tuple:
    """Run the probe live with its output redirected, recording both boundaries."""
    meta_raw, cells, sweep = {}, {}, {}
    live_post, live_catalogue, live_sweep = mod._post, mod._catalogue, mod._sweep

    def post(url, payload):
        out = live_post(url, payload)
        if url == mod.WDS_META:
            for item in out:
                obj = (item or {}).get("object") or {}
                if obj:
                    meta_raw[int(obj["productId"])] = obj
        elif url == mod.WDS_DATA:
            for item in out:
                obj = item.get("object") or {}
                points = obj.get("vectorDataPoint") or []
                if points:
                    cells[f"{int(obj['productId'])}|{obj['coordinate']}"] = points[0]["value"]
        return out

    def catalogue():
        cubes = live_catalogue()
        sweep["live_size"] = len(cubes)
        return cubes

    def probe_sweep():
        hits, size = live_sweep()
        sweep["hits"] = hits
        return hits, size

    mod._post, mod._catalogue, mod._sweep = post, catalogue, probe_sweep
    mod.new_run()
    mod.OUT = out_path
    mod.main()
    return meta_raw, cells, sweep


# Every member NAME `run_p3.py` resolves through `_member_id`, gathered from the probe itself
# rather than retyped: a probe-side change that widens what it resolves then FAILS LOUDLY at
# regen time (the member is missing and the note cannot be rebuilt) instead of being silently
# carried by a stale literal here.
def _looked_up(mod) -> set:
    return ({*mod.TARGET_GEOS, *mod.TARGET_SEXES, *mod.TARGET_AGES, mod.STAT_TOTAL,
             *mod.STAT_COMPONENTS, mod.TOTAL_HH, mod.HH_ONE_PERSON}
            | {"2021", "Total - Gender", "Total - All ages", "Quebec", "Population, 2021"})


def _trim_cubes(mod, meta_raw: dict) -> dict:
    looked_up = _looked_up(mod)
    cubes = {}
    for pid, obj in meta_raw.items():
        dimensions = []
        for dim in sorted(obj["dimension"], key=lambda d: d["dimensionPositionId"]):
            members = dim.get("member") or []
            names = [m.get("memberNameEn") or "" for m in members]
            printed = ((dim.get("dimensionNameEn") or "").lower().startswith(("gender", "sex"))
                       or mod.STAT_ALONE in names)
            if printed:
                kept = members
            else:
                keep = {i for i, name in enumerate(names) if name in looked_up}
                for token in ("(CMA)", "75", "85"):
                    hit = next((i for i, name in enumerate(names) if token in name), None)
                    if hit is not None:
                        keep.add(hit)
                kept = [m for i, m in enumerate(members) if i in keep]
            dimensions.append({
                "pos": dim["dimensionPositionId"], "name": dim["dimensionNameEn"],
                "members": [{"id": m["memberId"], "name": m["memberNameEn"]} for m in kept]})
        cubes[str(pid)] = {"title": obj["cubeTitleEn"], "release": obj["releaseTime"],
                           "archive": obj["archiveStatusEn"], "dimensions": dimensions}
    return cubes


def main() -> None:
    before = hashlib.sha256(NOTE.read_bytes()).hexdigest()
    mod = _load_probe()
    with tempfile.TemporaryDirectory() as tmp:
        meta_raw, cells, sweep = _record(mod, Path(tmp) / "P3-capture.md")
    after = hashlib.sha256(NOTE.read_bytes()).hexdigest()
    # The committed note is the thing the gate CHECKS. A build tool that rewrote it would
    # turn the byte-equality gate into a tautology on the very run that cut its fixture.
    assert before == after, f"the committed note moved during capture: {before} -> {after}"
    payload = {"sweep": {"catalogue_size": COMMITTED_CATALOGUE_SIZE, "hits": sweep["hits"]},
               "cubes": _trim_cubes(mod, meta_raw), "cells": cells}
    DEST.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=0),
                    encoding="utf-8")
    print(f"{DEST.name}: {len(cells)} cells, {len(payload['cubes'])} cubes, "
          f"{DEST.stat().st_size:,} bytes | catalogue pinned at {COMMITTED_CATALOGUE_SIZE}, "
          f"live answered {sweep['live_size']}")


if __name__ == "__main__":
    main()
