#!/usr/bin/env python3
"""Mint the COMMITTED golden — `demoflow/artifacts/rankings.json` and
`demoflow/artifacts/tripwire_baseline.json` (spec §10).

    cd demoflow && uv run python scripts/gen_golden.py

Thin wrapper by design (the `gen_headship.py` rule): the pin and the pipeline call both live in
`demoflow.golden`, so the committed bytes and the bytes `tests/test_golden.py` re-derives come
off the SAME code path. This file hardcodes no input.

THE OUTPUT IS A BUILD ARTIFACT: never hand-edit it — re-run this and commit what it emits.
`tests/test_golden.py` reds if the committed bytes and a fresh run ever part, and
`artifacts/README.md` says which kind of red a reader is looking at.

THIS SCRIPT'S EXIT CODE IS THE EMITTER'S, NOT THE TRIPWIRE VERDICT — the same split `demoflow
run` states: 0 means both documents were built, validated and written. The tripwire verdict is
printed beside it because it is 1 on the committed tree (every indicator honestly UNKNOWN) and
an operator who reads a minting run's exit 0 as "the tripwires are green" has been misled by a
gate that was never claiming it.
"""
import sys

from demoflow.golden import (
    GOLDEN_DATA_DIR,
    GOLDEN_DIR,
    GOLDEN_NOW_MONTH,
    GOLDEN_NOW_YEAR,
    generate_golden,
)


def main() -> int:
    print(f"data_dir={GOLDEN_DATA_DIR}  now={GOLDEN_NOW_YEAR:04d}-{GOLDEN_NOW_MONTH:02d}  "
          f"out={GOLDEN_DIR}")
    result = generate_golden()
    for name in result["artifacts"]:
        print(f"wrote {result['out_dir'] / name}")
    verdict = result["exit_code"]
    print(f"tripwire verdict: {verdict} "
          f"({'all required indicators OK' if verdict == 0 else 'NOT all OK'}) — "
          "the EVALUATION's code, not this script's; see artifacts/README.md")
    for line in result["tripwire_log"]:
        print(f"  log: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
