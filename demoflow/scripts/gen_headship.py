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
    # Deterministic bytes: member order comes from `_HEADSHIP_MEMBER_SPEC` and age order from
    # `range(0, 101)` (never a set iteration, whose order is per-process randomized), so
    # re-running this must reproduce the file byte-for-byte.
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    prov = payload["_provenance"]
    print(f"  central shape: {payload['central_shape']}   "
          f"carried: {', '.join(payload['headship'])}")
    for member, (lo, hi) in prov["member_spec"].items():
        if not prov["member_maintainers"][member]:
            continue
        residuals = "  ".join(
            f"{shape} {prov['per_member_closure']['residuals'][shape][member]:.3g}"
            for shape in payload["headship"])
        print(f"  {member:20s} {lo:>3d}-{hi:<3d} {prov['member_rates'][member]:.6f}   "
              f"{prov['member_maintainers'][member]:>9,d} maintainers / "
              f"{prov['member_persons'][member]:>12,.0f} persons   closure {residuals}")
    for band, rate in prov["band_maintainers"].items():
        print(f"  legacy {band:6s} {rate:>9,d} maintainers / "
              f"{prov['band_persons'][band]:>12,.0f} persons")
    for shape, sup in prov["range_certificate"].items():
        print(f"  range certificate sup dY/dX [{shape}]: {sup:.10f} <= 1")
    print(f"  closure: {prov['numerator_closure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
