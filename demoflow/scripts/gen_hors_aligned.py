#!/usr/bin/env python3
"""Generate `demoflow/data/ownership_hors_aligned.json` — the OPERAND-ALIGNED HORS_RMR curve.

Thin wrapper by design (steering ruling B): all derivation lives in
`demoflow.loaders.hors_aligned.derive_aligned_ownership`, so the shipped artifact and the
no-drift gate exercise the SAME code path. This file hardcodes no rate.

    cd demoflow && uv run python scripts/gen_hors_aligned.py

The output is a BUILD ARTIFACT: never hand-edit it — re-run this and commit what it emits.
`test_p11_5_committed_artifact_equals_a_fresh_derivation` reds if the two ever part, and
`test_p11_6_...byte_for_byte` reds if this script stops being deterministic. The CSD extract it
reads is acquired by `scripts/pull_hors_aligned_csd.py`, which is a separate, pinned step.
"""
import argparse
import json
import sys
from pathlib import Path

from demoflow.loaders.census import CENSUS_EXTRACT
from demoflow.loaders.hors_aligned import (
    ALIGNED_GEOGRAPHY,
    ARTIFACT,
    BAND_ORDER,
    EXTRACT,
    derive_aligned_ownership,
)
from demoflow.loaders.pins import DATA_DIR


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DATA_DIR / ARTIFACT,
                    help="where to write the artifact (default: the committed path)")
    args = ap.parse_args()

    payload = derive_aligned_ownership(DATA_DIR / CENSUS_EXTRACT, DATA_DIR / EXTRACT)
    # Deterministic bytes: band order comes from `CD_BAND_SPEC` and the join's geography order
    # from the Geography enum (never a set iteration, whose order is per-process randomized),
    # so re-running this must reproduce the file byte-for-byte.
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {args.out}")
    bands = payload["_provenance"]["bands"]
    for label in BAND_ORDER:
        row = bands[label]
        print(f"  {ALIGNED_GEOGRAPHY.value} {label:6s} shipped={row['shipped_rate']:.6f} "
              f"aligned={row['aligned_rate']:.6f} ({row['relative_delta_pct']:+.3f}%) "
              f"bound={row['aligned_bound_rate']:.6f} withheld={row['withheld_cells']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
