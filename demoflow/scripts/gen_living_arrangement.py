#!/usr/bin/env python3
"""Generate `demoflow/data/living_arrangement.json` from the pinned WDS extract.

Thin wrapper by design (steering ruling B): all derivation lives in
`demoflow.loaders.living_arrangement.derive_living_arrangement`, so the shipped artifact and
the no-drift gate exercise the SAME code path. This file hardcodes no rate.

    cd demoflow && uv run python scripts/gen_living_arrangement.py

The output is a BUILD ARTIFACT: never hand-edit it — re-run this and commit what it emits.
`test_committed_artifact_equals_generator_output` reds if the two ever part. The extract
itself is acquired by `scripts/pull_living_arrangement.py`, which is a separate, pinned step.
"""
import json
import sys

from demoflow.loaders.living_arrangement import (
    ARTIFACT,
    EXTRACT,
    SEXES,
    derive_living_arrangement,
)
from demoflow.loaders.pins import DATA_DIR


def main() -> int:
    payload = derive_living_arrangement(DATA_DIR / EXTRACT)
    out = DATA_DIR / ARTIFACT
    # Deterministic bytes: geography order comes from the Geography enum, band order from
    # _AGE_BAND_SPEC and sex order from SEXES (never a set iteration, whose order is
    # per-process randomized), so re-running this reproduces the file byte-for-byte.
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for geo, bands in payload["rates"].items():
        flag = "  [borrowed_prior]" if bands.get("_flag") else ""
        shown = "  ".join(
            f"{label}/{sex} la={cells[sex]['living_alone']:.4f} cs={cells[sex]['couple_share']:.4f}"
            for label, cells in bands.items() if label != "_flag" for sex in SEXES)
        print(f"  {geo:26s} {shown}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
