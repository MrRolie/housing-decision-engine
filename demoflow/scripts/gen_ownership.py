#!/usr/bin/env python3
"""Generate `demoflow/data/ownership_by_geo_age.json` from the pinned P2 Census extract.

Thin wrapper by design (steering ruling B): all derivation lives in
`demoflow.loaders.census.derive_ownership_from_csv`, so the shipped artifact and the
no-drift gate exercise the SAME code path. This file hardcodes no rate.

    cd demoflow && uv run python scripts/gen_ownership.py

The output is a BUILD ARTIFACT: never hand-edit it: re-run this and commit what it emits.
`test_committed_ownership_json_equals_generator_output` reds if the two ever part.
"""
import json
import sys

from demoflow.loaders.census import (
    CENSUS_EXTRACT,
    OWNERSHIP_ARTIFACT,
    derive_ownership_from_csv,
)
from demoflow.loaders.pins import DATA_DIR


def main() -> int:
    payload = derive_ownership_from_csv(DATA_DIR / CENSUS_EXTRACT)
    out = DATA_DIR / OWNERSHIP_ARTIFACT
    # Deterministic bytes: geography order comes from the Geography enum and band order
    # from _AGE_BAND_SPEC (never a set iteration, whose order is per-process randomized),
    # so re-running this must reproduce the file byte-for-byte.
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for geo, bands in payload["rates"].items():
        shown = " ".join(f"{b}={v:.6f}" for b, v in bands.items() if b != "_flag")
        flag = "  [borrowed_prior]" if bands.get("_flag") else ""
        print(f"  {geo:24s} {shown}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
