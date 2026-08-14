"""Regenerate the P9 fixture cache and its expected index from a full catalogue pull.

NOT a test (pytest collects `test_*.py` only) and not part of any suite — a build tool kept
beside its output so the fixture is DERIVED DATA with a recorded recipe rather than an opaque
blob nobody can re-cut. The gates in `tests/test_probe_p9.py` read the output; nothing reads
this file at test time.

WHAT THE FIXTURE IS: six WHOLE, UNMODIFIED `getCubeMetadata` responses copied byte-for-byte
out of the 2026-08-14 full-catalogue pull (canonical sha256
ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a), with the matching six rows
of that pull's `getAllCubesListLite` catalogue and that pull's own manifest.

WHOLE cubes, never trimmed: the fixture is what the floor guards and the regen-equality gate
run against, so a cube with members deleted to save bytes would make every one of those gates
an assertion about data StatCan never published. The SELECTION is a fixture-sizing decision
(the full pull is 5.29 GB and cannot be committed) and it is a selection over CUBES, not over
what is read inside them — the closure claim itself selects nothing, which is the whole point
of the probe and must not be confused with this file's cheapness rule.

WHY THESE SIX. Both positive controls, then the smallest real cube found in each remaining
class, so every branch of `classify` is exercised and the mutation battery has something to
mutate:

  98100621  flagged      — the ruling-S cube: immigrant vocabulary MEMBER-only under a
                           `Population characteristics (46)` dimension, maintainer dimension,
                           CMA reach. Carries the maintainer cross. Positive control.
  43100060  flagged      — the ruling-Q cube and the MIRROR shape: immigrant at dimension
                           level, household vocabulary member-only. CMA reach. Positive
                           control.
  33100532  flagged      — a NAICS-vocabulary coincidence with no CMA reach, so the
                           flagged-and-reaches-CMA subset is a real filter in the fixture
                           rather than the whole listing.
  46100032  both-dimension-level
  25100070  single-vocabulary
  18100042  none

The manifest is the SOURCE pull's, copied verbatim: every field in it (dates, wall clock,
catalogue_rows 8226) truthfully describes the pull these six cubes were cut from, not the
excerpt, and the added `_fixture` key says so in the file itself rather than in a comment a
reader of the JSON never sees.

Run:
    cd demoflow && uv run python tests/fixtures/make_p9_fixture.py --cache DIR
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "probes"))

import run_p9 as p9  # noqa: E402

SOURCE_PULL_SHA256 = "ca18fcc7444ec5ec4de1fc01bd600f4c2bb0d86d83c55423009fa5b5cd46ff7a"
FIXTURE_PIDS = (18100042, 25100070, 33100532, 43100060, 46100032, 98100621)
OUT_CACHE = HERE / "p9_cache"
OUT_INDEX = HERE / "p9_index_expected.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", required=True, type=Path,
                        help="a FULL p9 cache directory (catalogue.json/meta.jsonl/manifest.json)")
    args = parser.parse_args()

    offsets = p9.index_cache(args.cache)
    missing = [pid for pid in FIXTURE_PIDS if pid not in offsets]
    if missing:
        raise SystemExit(f"source cache does not carry {missing}")

    OUT_CACHE.mkdir(parents=True, exist_ok=True)
    catalogue = json.loads((args.cache / "catalogue.json").read_text(encoding="utf-8"))
    rows = sorted((c for c in catalogue if c["productId"] in FIXTURE_PIDS),
                  key=lambda c: c["productId"])
    if len(rows) != len(FIXTURE_PIDS):
        raise SystemExit(f"catalogue carries {len(rows)} of {len(FIXTURE_PIDS)} fixture rows")
    (OUT_CACHE / "catalogue.json").write_text(p9._canonical(rows), encoding="utf-8")

    with (OUT_CACHE / "meta.jsonl").open("w", encoding="utf-8") as fh:
        for pid in sorted(FIXTURE_PIDS):
            fh.write(p9._canonical(p9.read_cube(args.cache, offsets[pid])) + "\n")

    manifest = json.loads((args.cache / "manifest.json").read_text(encoding="utf-8"))
    manifest["_fixture"] = (
        f"Every field above describes the FULL pull these {len(FIXTURE_PIDS)} cubes were "
        f"excerpted from (canonical sha256 {SOURCE_PULL_SHA256}), not this excerpt — it is "
        "the excerpt's provenance, and catalogue_rows is the source catalogue's count."
    )
    (OUT_CACHE / "manifest.json").write_text(p9._canonical(manifest), encoding="utf-8")

    payload = p9.build_index(p9.sweep(OUT_CACHE))
    OUT_INDEX.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8")
    prov = payload["_provenance"]
    print(f"fixture cache: {OUT_CACHE} ({sum(p.stat().st_size for p in OUT_CACHE.iterdir())} B)")
    print(f"classes: {prov['class_counts']}")
    print(f"maintainer cross: {prov['maintainer_cross']['product_ids']}")
    print(f"fixture raw sha256: {prov['raw_pull_sha256']}")


if __name__ == "__main__":
    main()
