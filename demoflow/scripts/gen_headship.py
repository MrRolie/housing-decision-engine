#!/usr/bin/env python3
"""Generate `demoflow/data/headship_by_age.json` from the TWO pinned sources.

Thin wrapper by design (steering ruling B): all derivation lives in
`demoflow.loaders.census.derive_headship_from_sources`, so the shipped artifact and the
regen-equality gate exercise the SAME code path. This file hardcodes no rate.

    cd demoflow && uv run python scripts/gen_headship.py

The output is a BUILD ARTIFACT: never hand-edit it — re-run this and commit what it emits.
`test_committed_headship_json_equals_generator_output` reds if the two ever part.
"""
import json
import sys

from demoflow.loaders.census import (
    CENSUS_EXTRACT,
    HEADSHIP_ARTIFACT,
    POP_QC_WORKBOOK,
    derive_headship_from_sources,
)
from demoflow.loaders.pins import DATA_DIR


def main() -> int:
    payload = derive_headship_from_sources(DATA_DIR / CENSUS_EXTRACT,
                                          DATA_DIR / POP_QC_WORKBOOK)
    out = DATA_DIR / HEADSHIP_ARTIFACT
    # Deterministic bytes: band order comes from `_HEADSHIP_BAND_SPEC` (never a set
    # iteration, whose order is per-process randomized), so re-running this must reproduce
    # the file byte-for-byte.
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    prov = payload["_provenance"]
    for band, rate in payload["headship"].items():
        print(f"  {band:6s} {rate:.6f}   "
              f"{prov['band_maintainers'][band]:>9,d} maintainers / "
              f"{prov['band_persons'][band]:>12,.0f} persons")
    print(f"  closure: {prov['numerator_closure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
